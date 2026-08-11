"""Entrypoints for Datasets API
https://api.semanticscholar.org/api-docs/datasets
"""

from typing import Literal

from kibad_crawler.config import S2_API_KEY
from kibad_crawler.utils import api_call_get

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
    """Releases are identified by a date stamp such as "2023-08-01". Each
    release contains full data for each dataset."""
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
    response = api_call_get(url=URL_BASE + route, api_key=S2_API_KEY)
    return response.json()


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
        - from_release (str): Basline release for this diff.
        - to_release (str): Target release for this diff.
        - update_files (list[str]): List of files that contain updates to the
            dataset. Each record in these files needs to be insterted or updated.
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
