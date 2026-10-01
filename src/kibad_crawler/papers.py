from dataclasses import dataclass, field
from datetime import datetime
import gzip
from io import StringIO
import json
import math
import os
from pathlib import Path

from loguru import logger
import pandas as pd
from tqdm import tqdm

from kibad_crawler.config import MAX_NUM_BATCH_PAPERS, RAW_DATA_DIR
from kibad_crawler.semantic_scholar import academic_graph, datasets
from kibad_crawler.utils import chunker, get_issn_codes


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
    urls: list[str],
    output_path: Path,
    search_params: PaperSearch,
    overwrite: bool = False,
    persistent: bool = False,
):
    """Download and filter a list of paper dataset files with `get_papers`.
    The list can be the files of a full release or the update files of a diff
    between two releases, since both have the same structure.

    Args:
        urls (list[str]): URLs of the paper dataset files to download.
        output_path (Path): Storage path to save the downloaded files.
        search_params (PaperSearch): Search and filter criteria.
        overwrite (bool, optional): Whether or not to overwrite a file that is
            already processed. Defaults to False.
        persistent (bool, optional): Whether or not to keep the original files
            after filtering papers. Defaults to False.
    """
    logger.info(f"{len(urls)} paper dataset files to process in '{output_path}'")
    for url in urls:
        get_papers(
            url=url,
            output_path=output_path,
            search_params=search_params,
            overwrite=overwrite,
            persistent=persistent,
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

    file_name = url.split("?")[0].split("/")[-1]
    csv_path = output_path / f"{file_name}.csv"
    if csv_path.exists():
        logger.debug(f"Skipping existing {csv_path}")
        if with_abstracts:
            get_abstracts(file_path=csv_path, overwrite=overwrite)
        return

    file_path = datasets.download_dataset_from_semantic_scholar(
        url=url, output_path=output_path, overwrite=overwrite
    )
    file_content = ""
    with gzip.open(file_path, "r") as f:
        for line in tqdm(f.readlines(), leave=True):
            if any(x in line.decode() for x in search_params.publication_venue_ids):
                file_content += line.decode()

    # a file can have no papers from the selected venues, e.g. a small update file of a diff
    if file_content == "":
        df_papers = pd.DataFrame(columns=["url", "publicationdate", "citationcount"])
    else:
        df_papers = pd.read_json(StringIO(file_content), lines=True)

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

    logger.info(f"Downloading abstracts to {json_path} ...")
    for i, group in tqdm(
        enumerate(chunker(paper_ids, MAX_NUM_BATCH_PAPERS)),
        total=math.ceil(len(paper_ids) / MAX_NUM_BATCH_PAPERS),
        desc="Downloading abstracts",
    ):
        json_file = json_path / f"papers-metadata-{i}.json"
        if json_file.exists() and not overwrite:
            logger.debug(f"Skipping existing {json_file}")
            continue

        response_batch = academic_graph.batch(group)

        # write to a temporary file first, so that an interrupted run does not
        # leave an incomplete file that would be skipped by the next run
        tmp_file = json_file.with_name(f"{json_file.name}.tmp")
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(response_batch, f)
        tmp_file.replace(json_file)
