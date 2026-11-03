from pathlib import Path

import pandas as pd
import requests
from retry import retry

from kibad_crawler.config import DELAY_S2_API


def get_human_readable_size(size: float, index: int = 0) -> str:
    """Returns the size given in bytes in a human readable unit.

    Args:
        size (float): Size of the file in bytes.
        index (int, optional): Index to navigate the list of units. Defaults
            to 0.

    Returns:
        str: Human readable size of the file like 3Gb.
    """
    SIZE_UNITS = ["B", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB", "ZiB"]
    if abs(size) < 1024.0:
        hr_size = f"{size:.1f} {SIZE_UNITS[index]}"
        return hr_size
    else:
        hr_size = get_human_readable_size(size / 1024.0, index + 1)
    return hr_size


class RetryableHTTPError(requests.HTTPError):
    """HTTP error that is worth retrying after waiting: 429 Too Many Requests
    or a server error (5xx) of the Semantic Scholar API."""


def raise_for_status(response: requests.Response):
    """Raise an HTTP error for a failed response. Errors due to the rate
    limit (429) or the server (5xx) are raised as `RetryableHTTPError`.

    Args:
        response (requests.Response): Response of the API call.
    """
    try:
        response.raise_for_status()
    except requests.HTTPError as e:
        if response.status_code == 429 or response.status_code >= 500:
            raise RetryableHTTPError(*e.args, response=response) from e
        raise


# errors to retry and the waiting time between attempts: 3, 6, 12, 24 and 48 seconds
RETRY_EXCEPTIONS = (RetryableHTTPError, requests.ConnectionError, requests.Timeout)
RETRY_TRIES = 6


@retry(exceptions=RETRY_EXCEPTIONS, tries=RETRY_TRIES, delay=DELAY_S2_API, backoff=2)
def api_call_post(
    url: str, params: dict, payload: dict, timeout: int = 60, api_key: str | None = None
) -> requests.Response:
    """POST request to the Semantic Scholar API. Requests that fail because of
    the rate limit (429), the server (5xx) or the connection are retried with
    an increasing waiting time. Other errors, e.g. 401 for a missing API key,
    are raised directly.

    Args:
        url (str): URL of the API endpoint.
        params (dict): Query parameters.
        payload (dict): JSON body of the request.
        timeout (int, optional): Timeout of the request in seconds. Defaults to 60.
        api_key (str | None, optional): Semantic Scholar API key, sent in the
            `x-api-key` header if given. Defaults to None.

    Returns:
        requests.Response: Response of the API.
    """
    if isinstance(api_key, str):
        headers = {"x-api-key": api_key}
        response = requests.post(
            url=url, headers=headers, timeout=timeout, params=params, json=payload
        )
    else:
        response = requests.post(url=url, timeout=timeout, params=params, json=payload)
    raise_for_status(response)
    return response


@retry(exceptions=RETRY_EXCEPTIONS, tries=RETRY_TRIES, delay=DELAY_S2_API, backoff=2)
def api_call_get(url: str, timeout: int = 60, api_key: str | None = None) -> requests.Response:
    """GET request to the Semantic Scholar API. Requests that fail because of
    the rate limit (429), the server (5xx) or the connection are retried with
    an increasing waiting time. Other errors, e.g. 401 for a missing API key,
    are raised directly.

    Args:
        url (str): URL of the API endpoint.
        timeout (int, optional): Timeout of the request in seconds. Defaults to 60.
        api_key (str | None, optional): Semantic Scholar API key, sent in the
            `x-api-key` header if given. Defaults to None.

    Returns:
        requests.Response: Response of the API.
    """
    if isinstance(api_key, str):
        headers = {"x-api-key": api_key}
        response = requests.get(url=url, headers=headers, timeout=timeout)
    else:
        response = requests.get(url=url, timeout=timeout)
    raise_for_status(response)
    return response


def get_issn_codes(path_journals_csv: Path | str) -> list:
    """Return a list of ISSN code to filter journals. It reads a CSV with ISSN
    column names and filter it's content.

    Args:
        file_path (Path): CSV file with ISSN codes to filter publication venues.

    Returns:
        list: ISSN codes to filter publication venues.
    """
    df_journals = pd.read_csv(path_journals_csv)
    columns = [x for x in df_journals.columns if "issn" in str(x).lower()]
    issn = []
    for column in columns:
        issn += [x for x in df_journals[column].unique() if isinstance(x, str)]
    return issn


def get_file_name(url: str) -> str:
    """Return the name of the file a download link points to, without the
    query string that signs the link.

    Args:
        url (str): URL of the file.

    Returns:
        str: Name of the file.
    """
    return url.split("?")[0].split("/")[-1]


def chunker(seq: list, size: int):
    """Divide a large list into lists of the given size."""
    return (seq[pos : pos + size] for pos in range(0, len(seq), size))
