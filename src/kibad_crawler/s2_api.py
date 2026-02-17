from datetime import datetime
import gzip
from io import StringIO
import os
from pathlib import Path
from typing import Literal

import pandas as pd
import requests
from tqdm import tqdm

from .config import MAX_NUM_BULK_PAPERS, S2_API_KEY


def download_dataset(
    release_id: str,
    dataset_name: Literal[
        "abstracts",
        "authors",
        "citations",
        "embeddings-specter_v1",
        "embeddings-specter_v2",
        "paper-ids",
        "papers",
        "publication-venues",
        "s2orc",
        "s2orc_v2",
        "tldrs",
    ],
) -> requests.Response:
    """Download dataset from Semantic Scholar API.

    Args:
        release_id (str): Release id with format `YYYY-MM-DD`
        dataset_name (str): Dataset name i.e.: `publication-venues`, `papers`.

    Returns:
        requests.Response: Response from the API
    """
    url = (
        f"https://api.semanticscholar.org/datasets/v1/release/{release_id}/dataset/{dataset_name}"
    )

    headers = {"x-api-key": S2_API_KEY}
    response = requests.get(url, headers=headers, timeout=60)
    return response


def download_file(url: str, path: Path, chunk_size: int = 10 * 1024) -> Path:
    """Download file from a `url` and stores it to a `path`.

    Args:
        url (str): URL to the file.
        path (Path): Path where to store the downloaded file.
        chunk_size (int, optional): Size of chunks to store. Defaults to 10*1024.

    Returns:
        Path: Path to the stored file.
    """
    path.mkdir(parents=True, exist_ok=True)
    file_name = url.split("?")[0].split("/")[-1]
    with requests.get(
        url, stream=True, allow_redirects=True, timeout=10
    ) as response:  # type:ignore
        with open(path / file_name, mode="wb") as file:
            for chunk in response.iter_content(chunk_size=chunk_size):
                file.write(chunk)
    return path / file_name


def download_paper_batch(
    url: str,
    release_path: Path,
    publication_venue_ids: list,
    persistant: bool = False,
    start_date: str = "2023-01-01",
) -> None:
    """Download a single file of the papers dataset.

    Args:
        url (str): _description_
        publication_venue_ids (list): _description_
        persistant (bool, optional): _description_. Defaults to False.
        start_date (str, optional): _description_. Defaults to "2023-01-01".
    """
    file_name = url.split("?")[0].split("/")[-1]
    if (release_path / "papers" / str(file_name + ".csv")).exists():
        return

    file_path = download_file(url=url, path=release_path / "papers")
    file_content = ""
    with gzip.open(
        file_path,
        "r",
    ) as f:
        for line in tqdm(f.readlines(), leave=True):
            if any(x in line.decode() for x in publication_venue_ids):
                file_content += line.decode()

    df_papers = pd.read_json(StringIO(file_content), lines=True)

    date_filter = datetime.strptime(start_date, "%Y-%m-%d")
    df_papers["publicationdate"] = pd.to_datetime(df_papers["publicationdate"])
    df_papers = df_papers[df_papers["publicationdate"] >= date_filter]

    df_papers.to_csv(release_path / "papers" / str(file_name + ".csv"), index=False)

    if not persistant:
        os.remove(file_path)


def download_all_papers(
    file_list: list[str],
    release_path: Path,
    publication_venue_ids: list[str],
    start_date: str = "2023-01-01",
    persistant: bool = False,
) -> None:
    """Download all the files from a list of urls.

    It generates a CSV file with the paper selection and deletes the .gz file.
    The CSV files will be used to extract the `paperid` to query the API for
    the rest of metadata of the paper.

    Args:
        file_list (list): List of urls.
        publication_venue_ids (list): List of publication venue ids.
        persistant (bool, optional): There are many files of several GBs in the
            datasets, so by default, it filters the papers by venue and start
            date and then deletes the complete dataset. Defaults to False.
    """
    for url in tqdm(file_list, total=len(file_list)):
        download_paper_batch(
            url=url,
            release_path=release_path,
            publication_venue_ids=publication_venue_ids,
            start_date=start_date,
            persistant=persistant,
        )


def download_bulk_paper(
    paper_ids: list,
    fields: str = "corpusId,url,title,abstract,venue,publicationVenue,year,citationCount,isOpenAccess,openAccessPdf,publicationDate,journal,fieldsOfStudy,s2FieldsOfStudy,authors,tldr,publicationTypes,textAvailability",
) -> requests.Response:
    """Bulk query to the S2 API.

    Limitations:
    - Can only process 500 paper ids at a time.
    - Can only return up to 10 MB of data at a time.
    - Can only return up to 9999 citations at a time.
    - For a list of supported IDs reference the "Details about a paper"
        endpoint.

    Args:
        paper_ids (list): List with the `paperid`s to request.
        fields (str, optional): Fields to request from the API. Defaults to "corpusId,url,title,abstract,venue,publicationVenue,year,citationCount,isOpenAccess,openAccessPdf,publicationDate,journal,fieldsOfStudy,s2FieldsOfStudy,authors,tldr,publicationTypes,textAvailability".

    Returns:
        requests.Response: API response.
    """
    headers = {"x-api-key": S2_API_KEY}
    url = "https://api.semanticscholar.org/graph/v1/paper/batch"
    response_batch = requests.post(
        url,
        headers=headers,
        params={"fields": fields},
        json={"ids": paper_ids[:MAX_NUM_BULK_PAPERS]},
        timeout=30,
    )
    return response_batch


def chunker(seq: list, size: int):
    """Divide a large list into lists of the given size."""
    return (seq[pos : pos + size] for pos in range(0, len(seq), size))
