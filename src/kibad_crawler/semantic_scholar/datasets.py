"""Entrypoints for Datasets API
https://api.semanticscholar.org/api-docs/datasets
"""

import gzip
from io import StringIO
from pathlib import Path
from typing import Literal

from loguru import logger
import pandas as pd
import requests
from retry import retry

from kibad_crawler.config import S2_API_KEY
from kibad_crawler.utils import api_call_get, get_file_name, get_human_readable_size

URL_BASE: str = "https://api.semanticscholar.org/datasets/v1"

DatasetName = Literal[
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
]


def get_available_releases() -> list[str]:
    """Returns a list with all the available releases.Rreleases are identified
    by a date stamp such as "2023-08-01". Each release contains full data for
    each dataset."""
    route = "/release/"
    response = api_call_get(url=URL_BASE + route)
    if response.ok:
        releases = response.json()
        return releases
    else:
        return []


def get_latest_release():
    """Return the latest of the releases."""
    releases = get_available_releases()
    return releases[-1]


def list_datasets(release_id: str):
    """Metadata describing a particular release, including a list of
    datasets available.

    Args:
        release_id (str): ID of the release.

    Returns:
        _type_: _description_
    """
    route = f"/release/{release_id}"
    response = api_call_get(url=URL_BASE + route)
    return response.json()


@retry(tries=3, delay=2)
def download_links(release_id: str, dataset_name: DatasetName) -> dict:
    """Datasets are partitioned and stored on S3. Clients can retrieve them
    by requesting this list of pre-signed download urls and fetching all
    the partitions.

    Returns the following data structure:
    - name (str): Name of the dataset
    - description (str): Description of the data contained in this dataset.
    - README (str): License and usage
    - files (list[str]): Temporary, pre-signed download links for dataset files.

    Args:
        dataset_name (DatasetName): Name of the dataset.
        release_id (str): ID of the release

    Returns:
        (dict): dict from the response of the API.
    """
    route = f"/release/{release_id}/dataset/{dataset_name}"
    logger.info(f"links - Downloading links from: {URL_BASE + route}")
    response = api_call_get(url=URL_BASE + route, api_key=S2_API_KEY)
    if response.ok:
        logger.info(f"links - {len(response.json()['files'])} links for `{dataset_name}` dataset")
    return response.json()


def download_links_by_file_name(release_id: str, dataset_name: DatasetName) -> dict:
    """Returns the current download link of every file of a dataset, by file
    name. The links are pre-signed and stop working after a few hours, while
    the files themselves keep their name, so a file is addressed by its name
    and its link is requested when it is needed.

    Args:
        release_id (str): ID of the release.
        dataset_name (DatasetName): Name of the dataset.

    Returns:
        dict: Download link per file name.
    """
    links = download_links(release_id=release_id, dataset_name=dataset_name)
    return {get_file_name(url): url for url in links["files"]}


def download_links_incremental_diffs(
    dataset_name: DatasetName, end_release_id: str, start_release_id: str
):
    """Full datasets can be updated from one release to another to avoid
    downloading and processing data that hasn't changed. This method returns
    a list of all the "diffs" that are required to catch a given dataset up
    from its current release to a newer one.

    Each "diff" represents changes between two sequential releases, and
    contains two lists of files, an "updated" list and a "deleted" list.
    Records in the "updated" list need to be inserted or replaced by their
    primary key. Records in the "deleted" list should be removed.

    - dataset (str): Dataset these diffs are for.
    - start_release	(str): Beginning release, i.e. the release currently held
        by the client.
    - end_release (str): Ending release, i.e. the release the client wants to
        update to.
    - diffs	(list): List of diffs that need to be applied to bring the dataset
        at 'start_release' up to date with 'end_release'.
        - from_release (str): Baseline release for this diff.
        - to_release (str): Target release for this diff.
        - update_files (list[str]): List of files that contain updates to the
            dataset. Each record in these files needs to be inserted or updated.
        - delete_files (list[str]): List of files that contain deletes from the
            dataset. Each record in these files needs to be deleted.

    Args:
        dataset_name (DatasetName): Name of the dataset.
        end_release_id (str): ID of the release the client wishes to update to,
            or 'latest' for the most recent release.
        start_release_id (str): ID of the release held by the client.

    Returns:
        _type_: _description_
    """
    route = f"/diffs/{start_release_id}/to/{end_release_id}/{dataset_name}"
    response = api_call_get(url=URL_BASE + route, api_key=S2_API_KEY)
    return response.json()


@retry(tries=3, delay=2)
def download_dataset_from_semantic_scholar(
    url: str,
    output_path: Path,
    chunk_size: int = 1024 * 1024 * 8,
    overwrite: bool = False,
) -> Path:
    """Download file from a `url` and stores it to a `output_path`.

    The file is written to a temporary file that is renamed after the download,
    so that an interrupted download does not leave a file behind that the next
    call would reuse as if it was complete. The temporary file is renamed only
    when it has the size that the server announced.

    Args:
        url (str): URL to the file.
        output_path (Path): Path where to store the downloaded file.
        chunk_size (int, optional): Size of chunks to store.
            Defaults to 1024 * 1024 * 8 or 8MiB.
        overwrite (bool, optional): Whether or not overwrite a file that
            has been already downloaded. Defaults to False.

    Returns:
        Path: Path to the stored file.

    Raises:
        OSError: If fewer bytes were downloaded than the server announced.
    """

    output_path.mkdir(parents=True, exist_ok=True)
    file_name = get_file_name(url)
    out_path = output_path / file_name
    tmp_path = out_path.with_name(f"{file_name}.tmp")

    if not overwrite and out_path.exists():
        logger.info(f"{out_path} already downloaded.")
        return out_path

    with requests.get(url, stream=True, allow_redirects=True, timeout=10) as response:
        response.raise_for_status()
        file_size = int(response.headers["Content-Length"])
        logger.info(f"Downloading {out_path} {get_human_readable_size(file_size)}")
        try:
            with open(tmp_path, mode="wb") as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    f.write(chunk)
        except BaseException:
            tmp_path.unlink(missing_ok=True)
            raise

    # a download can end without an error and still be short, so the file is
    # kept only when it has the size that the server announced
    downloaded_size = tmp_path.stat().st_size
    if downloaded_size != file_size:
        tmp_path.unlink()
        raise OSError(
            f"'{out_path}' is incomplete, {downloaded_size} of {file_size} bytes downloaded"
        )

    tmp_path.replace(out_path)
    return out_path


def read_publication_venues(file_path: Path) -> pd.DataFrame:
    """Returns a dataframe with publication venues from the given path.

    Args:
        file_path (Path): Path to the compressed file with publication venues.

    Returns:
        pd.DataFrame: Publication venues DataFrame.
    """
    with gzip.open(
        file_path,
        "r",
    ) as f:
        file_content = f.read()

    df_venues = pd.read_json(StringIO(file_content.decode()), lines=True)
    logger.info(f"`{file_path}` has {df_venues.shape[0]:,} publication venues in total")
    return df_venues
