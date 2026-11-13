from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
import gzip
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

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
    """Check whether pypdf can open a downloaded PDF.

    Args:
        pdf_path: Path to the file to check.

    Returns:
        True if pypdf opens the file, or False if it raises PdfReadError.

    Raises:
        OSError: If the file cannot be accessed.
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
) -> Path | None:
    """Download and validate an open-access PDF before saving it.

    Stream the response to a temporary file in the destination directory and
    move it into place after validation. Reuse a valid existing file unless
    overwrite is enabled.

    Args:
        url: URL of the PDF to download.
        path: Destination directory, created if necessary.
        file_name: Filename to use in the destination directory.
        chunk_size: Number of bytes to request per streamed chunk. Defaults to
            8 MiB.
        overwrite: Whether to replace an existing valid PDF. Defaults to False.

    Returns:
        Path to the new or reused PDF, or None if the server returns HTTP 403
        or pypdf rejects the downloaded file.

    Raises:
        requests.exceptions.RequestException: If a request or transfer fails after
            retries.
        OSError: If accessing or writing a file fails after retries.
    """
    path.mkdir(parents=True, exist_ok=True)
    out_path = path / file_name

    if not overwrite and out_path.exists() and _is_valid_pdf(out_path):
        logger.info(f"{file_name} - already downloaded")
        return out_path

    logger.info(f"{file_name} - downloading '{url}' -> '{out_path}'")
    with requests.get(url, stream=True, allow_redirects=True, timeout=60) as response:
        if response.status_code == 403:
            logger.warning(f"{file_name} - HTTP 403 for '{url}'")
            return None
        response.raise_for_status()

        tmp_file = NamedTemporaryFile(
            dir=path, prefix=f".{file_name}.", suffix=".tmp", delete=False
        )
        tmp_path = Path(tmp_file.name)
        try:
            with tmp_file:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    tmp_file.write(chunk)
            if not _is_valid_pdf(tmp_path):
                logger.warning(f"{file_name} - response from '{url}' is not a valid PDF")
                return None
            tmp_path.replace(out_path)
        finally:
            tmp_path.unlink(missing_ok=True)

    logger.info(f"{file_name} - downloaded {get_human_readable_size(out_path.stat().st_size)}")
    return out_path


def download_open_access_pdfs(input_path: Path):
    """Download open-access PDFs listed in Semantic Scholar JSON metadata.

    Skip records without a paper ID or PDF URL and records whose isOpenAccess
    flag is false or missing. Try each distinct URL for a paper until a PDF
    is available. Save one file per paper as open_access_pdf/<paperId>.pdf
    within the input directory.

    Args:
        input_path: Directory to search recursively for JSON files. Each file
            must contain an array of Semantic Scholar paper records with
            paperId, isOpenAccess, and openAccessPdf.url fields where available.

    Raises:
        json.JSONDecodeError: If a metadata file contains invalid JSON.
        requests.exceptions.RequestException: If a request or transfer fails after
            retries.
        OSError: If reading metadata or writing a PDF fails.
    """
    urls_by_paper: dict[str, dict[str, None]] = {}
    for file in input_path.rglob("*.json"):
        with file.open(encoding="utf-8") as f:
            records = json.load(f)

        for record in records:
            if not isinstance(record, dict) or record.get("isOpenAccess") is not True:
                continue
            paper_id = record.get("paperId")
            pdf = record.get("openAccessPdf")
            url = pdf.get("url") if isinstance(pdf, dict) else None
            if isinstance(paper_id, str) and paper_id and isinstance(url, str) and url.strip():
                urls_by_paper.setdefault(paper_id, {})[url.strip()] = None

    if not urls_by_paper:
        logger.info(f"No open-access PDFs listed in '{input_path}'")
        return

    output_dir = input_path / "open_access_pdf"
    available = 0
    for paper_id, urls in urls_by_paper.items():
        for url in urls:
            if download_open_access_pdf(url=url, path=output_dir, file_name=f"{paper_id}.pdf"):
                available += 1
                break

    logger.info(
        f"{available:,} of {len(urls_by_paper):,} open-access PDFs available in '{output_dir}'"
    )
