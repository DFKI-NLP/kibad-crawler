from dataclasses import dataclass, field
from datetime import datetime
import gzip
from io import StringIO
import json
import os
from pathlib import Path

from loguru import logger
import pandas as pd
from tqdm import tqdm

from kibad_crawler.config import MAX_NUM_BATCH_PAPERS
from kibad_crawler.semantic_scholar import academic_graph, datasets
from kibad_crawler.utils import chunker


@dataclass
class PaperSearch:
    """Data structure to filter search of papers downloaded with the API."""

    publication_venue_ids: list
    min_publication_date: str = field(default="2024-01-01")
    max_publication_date: str = field(default=datetime.now().strftime("%Y-%m-%d"))
    min_citation_count: int = field(default=0)

    def __repr__(self):
        return f"Paper search criteria: (publication_venue_ids={len(self.publication_venue_ids):,} venues, min_publication_date='{self.min_publication_date}', max_publication_date='{self.max_publication_date}', min_citation_count={self.min_citation_count})"


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
            get_abstracts(csv_path)
        return

    file_path = datasets.download_dataset_from_semantic_scholar(
        url=url, output_path=output_path, overwrite=overwrite
    )
    file_content = ""
    with gzip.open(file_path, "r") as f:
        for line in tqdm(f.readlines(), leave=True):
            if any(x in line.decode() for x in search_params.publication_venue_ids):
                file_content += line.decode()

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
        get_abstracts(csv_path)


def get_abstracts(file_path: Path):
    """Download abstracts of papers from Semantic Scholar.

    Args:
        file_path (Path): File path to a single CSV file with papers
            filtered from the Semantic Scholar API.
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
        total=int(len(paper_ids) / MAX_NUM_BATCH_PAPERS),
        desc="Downloading abstracts",
    ):
        response_batch = academic_graph.batch(group)

        json_file = json_path / f"papers-metadata-{i}.json"
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(response_batch, f)
