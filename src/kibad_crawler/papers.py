from dataclasses import dataclass, field
from datetime import datetime
import gzip
from io import StringIO
import os
from pathlib import Path

from loguru import logger
import pandas as pd
from tqdm import tqdm

from kibad_crawler.semantic_scholar import datasets


@dataclass
class PaperSearch:
    """Data structure to filter search of papers downloaded with the API."""

    publication_venue_ids: list
    min_publication_date: str = field(default="2024-01-01")
    max_publication_date: str = field(default=datetime.now().strftime("%Y-%m-%d"))
    min_citation_count: int = field(default=0)


def get_papers(
    url: str,
    output_path: Path,
    search_params: PaperSearch,
    overwrite: bool = False,
    persistent: bool = False,
):

    file_name = url.split("?")[0].split("/")[-1]
    csv_path = output_path / f"{file_name}.csv"
    if csv_path.exists():
        logger.debug(f"Skipping existing {csv_path}")
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
        logger.info(f"Removed {file_path}")
