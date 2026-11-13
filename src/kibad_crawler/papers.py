from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
import gzip
import json
import os
from pathlib import Path

from loguru import logger
import pandas as pd
from pypdf import PdfReader
from pypdf.errors import PdfReadError
import requests
from retry import retry
from tqdm import tqdm

from kibad_crawler.config import MAX_NUM_BATCH_PAPERS, RAW_DATA_DIR
from kibad_crawler.semantic_scholar import academic_graph, datasets
from kibad_crawler.utils import (
    chunker,
    get_file_name,
    get_human_readable_size,
    get_issn_codes,
)


@dataclass
class PaperSearch:
    """Data structure to filter search of papers downloaded with the API."""

    publication_venue_ids: list
    min_publication_date: str = field(default="2024-01-01")
    max_publication_date: str = field(default=datetime.now().strftime("%Y-%m-%d"))
    min_citation_count: int = field(default=0)

    def __repr__(self):
        return f"Paper search criteria: (publication_venue_ids={len(self.publication_venue_ids):,} venues, min_publication_date='{self.min_publication_date}', max_publication_date='{self.max_publication_date}', min_citation_count={self.min_citation_count})"


def get_publication_venue_ids(release_id: str, file_with_issn: Path | str) -> list[str]:
    """Return the ids of the publication venues of a release whose ISSN codes
    are listed in a CSV file. The publication venues dataset of the release is
    downloaded if it is not already on disk.

    Args:
        release_id (str): Release version from Semantic Scholar with format
            'YYYY-MM-DD'.
        file_with_issn (Path | str): CSV file with ISSN codes of publication
            venues used to filter publications from those venues.

    Returns:
        list[str]: Ids of the matched publication venues.
    """
    links_publication_venues = datasets.download_links(release_id, "publication-venues")
    output_path = datasets.download_dataset_from_semantic_scholar(
        url=links_publication_venues["files"][0],
        output_path=RAW_DATA_DIR
        / "semantic_scholar"
        / "release"
        / release_id
        / "publication_venues",
    )
    df_venues = datasets.read_publication_venues(file_path=output_path)

    issn = get_issn_codes(file_with_issn)
    return df_venues[df_venues["issn"].isin(issn)].id.unique().tolist()


def get_papers_from_files(
    file_names: list[str],
    get_url: Callable[[str], str],
    output_path: Path,
    search_params: PaperSearch,
    overwrite: bool = False,
    persistent: bool = False,
    with_abstracts: bool = True,
):
    """Download and filter paper dataset files with `get_papers`. The files can
    be the files of a full release or the update files of a diff between two
    releases, since both have the same structure.

    The download links of Semantic Scholar are pre-signed and stop working
    after a few hours, which is longer than one file takes but shorter than a
    run over all files of a release. The link of a file is therefore requested
    with `get_url` right before the file is downloaded.

    Args:
        file_names (list[str]): Names of the paper dataset files to download.
        get_url (Callable[[str], str]): Returns the current download link of a
            file name.
        output_path (Path): Storage path to save the downloaded files.
        search_params (PaperSearch): Search and filter criteria.
        overwrite (bool, optional): Whether or not to overwrite a file that is
            already processed. Defaults to False.
        persistent (bool, optional): Whether or not to keep the original files
            after filtering papers. Defaults to False.
        with_abstracts (bool, optional): Include the abstracts in the
            downloading process. Defaults to True.
    """
    logger.info(f"{len(file_names)} paper dataset files to process in '{output_path}'")
    for file_name in file_names:
        get_papers(
            url=get_url(file_name),
            output_path=output_path,
            search_params=search_params,
            overwrite=overwrite,
            persistent=persistent,
            with_abstracts=with_abstracts,
        )


def get_papers(
    url: str,
    output_path: Path,
    search_params: PaperSearch,
    overwrite: bool = False,
    persistent: bool = False,
    with_abstracts: bool = True,
):
    """Download paper metadata from Semantic Scholar and filter downloaded
    files based on publication venues, minimum and maximum publication dates
    and citation count.

    Args:
        url (str): URL of the paper dataset to download.
        output_path (Path): Storage path to save the downloaded file.
        search_params (PaperSearch): Search and filter criteria based on:
            - publication_venue_ids
            - min_publication_date
            - max_publication_date
            - min_citation_count
        overwrite (bool, optional): Whether or not to overwrite a file that is
            already processed. Defaults to False.
        persistent (bool, optional): Whether or not to keep the original file
            of more than 1GB after filtering papers based on `search_params`.
            Defaults to False. This option saves storage space.
        with_abstracts (bool, optional) = Include the abstracts in the
            downloading process. Default to True.
    """

    csv_path = output_path / f"{get_file_name(url)}.csv"
    if csv_path.exists():
        logger.debug(f"Skipping existing {csv_path}")
        if with_abstracts:
            get_abstracts(file_path=csv_path, overwrite=overwrite)
        return

    file_path = datasets.download_dataset_from_semantic_scholar(
        url=url, output_path=output_path, overwrite=overwrite
    )
    # a set keeps the filter independent of the number of venues, and reading the
    # file line by line keeps the whole archive out of memory
    publication_venue_ids = set(search_params.publication_venue_ids)
    papers = []
    with gzip.open(file_path, "rt", encoding="utf-8") as f:
        for line in tqdm(f, leave=True):
            if not line.strip():
                continue
            paper = json.loads(line)
            if paper.get("publicationvenueid") in publication_venue_ids:
                papers.append(paper)

    # a file can have no papers from the selected venues, e.g. a small update file of a diff
    if papers:
        df_papers = pd.DataFrame(papers)
    else:
        df_papers = pd.DataFrame(columns=["url", "publicationdate", "citationcount"])

    min_publication_date_filter = datetime.strptime(search_params.min_publication_date, "%Y-%m-%d")
    max_publication_date_filter = datetime.strptime(search_params.max_publication_date, "%Y-%m-%d")

    df_papers["publicationdate"] = pd.to_datetime(df_papers["publicationdate"])
    df_papers = df_papers[df_papers["publicationdate"] >= min_publication_date_filter]
    df_papers = df_papers[df_papers["publicationdate"] <= max_publication_date_filter]

    df_papers = df_papers[df_papers["citationcount"] >= search_params.min_citation_count]

    df_papers.to_csv(csv_path, index=False)
    logger.info(f"'{csv_path}' filtered with ({len(df_papers)} papers)")

    if not persistent:
        os.remove(file_path)
        logger.info(f"Removing {file_path}")

    if with_abstracts:
        get_abstracts(file_path=csv_path, overwrite=overwrite)


def get_abstracts(file_path: Path, overwrite: bool = False):
    """Download abstracts of papers from Semantic Scholar. Batches that are
    already stored as JSON files are skipped, so a run that was interrupted
    continues where it stopped.

    Args:
        file_path (Path): File path to a single CSV file with papers
            filtered from the Semantic Scholar API.
        overwrite (bool, optional): Whether or not to download the batches
            that are already stored again. Defaults to False.
    """
    df = pd.read_csv(file_path)
    logger.info(f"{df.shape[0]:,} abstracts to download")

    paper_ids = []
    for i, r in df.iterrows():
        paper_ids.append(r["url"].split("/")[-1])

    # use  [:-7] to remove ".gz.csv" from the file name
    json_path = file_path.parent / file_path.name[:-7] / "json"
    json_path.mkdir(parents=True, exist_ok=True)

    groups = list(chunker(paper_ids, MAX_NUM_BATCH_PAPERS))
    stored_batches = [
        i for i in range(len(groups)) if (json_path / f"papers-metadata-{i}.json").exists()
    ]
    if stored_batches and not overwrite:
        logger.info(f"Skipping {len(stored_batches):,} batches already stored in {json_path}")

    logger.info(f"Downloading abstracts to {json_path} ...")
    for i, group in tqdm(enumerate(groups), total=len(groups), desc="Downloading abstracts"):
        json_file = json_path / f"papers-metadata-{i}.json"
        if i in stored_batches and not overwrite:
            continue

        response_batch = academic_graph.batch(group)

        # write to a temporary file first, so that an interrupted run does not
        # leave an incomplete file that would be skipped by the next run
        tmp_file = json_file.with_name(f"{json_file.name}.tmp")
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(response_batch, f)
        tmp_file.replace(json_file)


def _is_valid_pdf(pdf_path: Path) -> bool:
    """Check whether or not a downloaded pdf file is valid.

    Args:
        pdf_path (Path): Path to the PDF file.

    Returns:
        bool: False if not valid.
    """
    try:
        _ = PdfReader(pdf_path)
    except PdfReadError:
        return False
    else:
        return True


@retry(delay=3, tries=3)
def download_open_access_pdf(
    url: str,
    path: Path,
    file_name: str,
    chunk_size: int = 8 * 1024 * 1024,
    overwrite: bool = False,
) -> Path:
    """Download file from a `url` and stores it to a `path`.

    Args:
        url (str): URL to the file.
        path (Path): Path where to store the downloaded file.
        file_name (str): Name of the file which will be f"{paperId}.pdf"
        chunk_size (int, optional): Size of chunks to store. Defaults to 10*1024.
        overwrite (bool, optional): Whether or not overwrite a file that
            has been already downloaded. Defaults to False.

    Returns:
        Path: Path to the stored file.
    """
    path.mkdir(parents=True, exist_ok=True)
    out_path = path / file_name

    if not overwrite and out_path.exists():
        logger.info(f"{file_name} - already downloaded")
        return out_path

    logger.info(f"{file_name} - downloading '{url}' -> '{out_path}'")

    with requests.get(url, stream=True, allow_redirects=True, timeout=60) as response:
        logger.info(f"{file_name} - {response.status_code} status code")
        if response.status_code == 403:
            return out_path
        response.raise_for_status()
        with open(out_path, mode="wb") as f:
            for chunk in response.iter_content(chunk_size=chunk_size):
                f.write(chunk)

    logger.info(
        f"{file_name} - downloaded {get_human_readable_size(int(response.headers['Content-Length']))}"
    )
    if not _is_valid_pdf(pdf_path=out_path):
        out_path.unlink()
        logger.error(f"{file_name} - deleting '{out_path}' invalid PDF file.")

    return out_path


def download_open_access_pdfs(input_path: Path):
    """Handles the downloading of all the papers from in a directory. It
    expects JSON files with semantic scholar structure including columns such
    as: ["paperId", "openAccessPdf.url", "isOpenAccess", "openAccessPdf.url"]

    Args:
        input_path (Path): Path where to find JSON files with paper metadata.
        release_id (str): Release to generate then output folder to save the
            files.
    """
    # Find all the JSON files with paper metadata from semantic scholar
    files = [x for x in Path(input_path).glob("**/*.json")]

    if len(files) == 0:
        logger.info(f"Finished. No papers to download found in '{input_path}'")

    dfs = []
    papers_found = 0
    for file in files:
        with open(file, encoding="utf-8") as f:
            data = json.load(f)

        df_aux = pd.json_normalize(data)
        papers_found += df_aux.shape[0]
        dfs.append(df_aux)

    logger.info(f"{papers_found:,} papers found in '{input_path}'")

    # Expects semantic scholar columns ["paperId", "openAccessPdf.url", "isOpenAccess", "openAccessPdf.url"]
    df = pd.concat(dfs)
    df.reset_index(drop=True, inplace=True)
    df = df[
        (df["openAccessPdf.url"].map(lambda x: len(x) > 0)) & (df["isOpenAccess"].map(lambda x: x))
    ]
    df = df[["paperId", "openAccessPdf.url"]].drop_duplicates()
    df.reset_index(drop=True, inplace=True)

    logger.info(f"{df.shape[0]:,} open access papers to be downloaded")

    # directory to save the PDF files
    output_dir = input_path / "open_access_pdf"

    # sequential download of the files
    for _, r in df.iterrows():
        download_open_access_pdf(
            url=r["openAccessPdf.url"], path=output_dir, file_name=f'{r["paperId"]}.pdf'
        )

    logger.info(
        f"PDF Download successfully finished! {len(list(output_dir.glob("**/*.pdf"))):,} out of {df.shape[0]:,} papers downloaded"
    )
