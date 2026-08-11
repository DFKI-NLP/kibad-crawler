import requests
from retry import retry


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


@retry(tries=3, delay=3)
def api_call_post(
    url: str, params: dict, payload: dict, timeout: int = 60, api_key: str | None = None
) -> requests.Response:
    """_summary_

    Args:
        url (str): _description_
        timeout (int, optional): _description_. Defaults to 60.
        api_key (str | None, optional): _description_. Defaults to None.

    Returns:
        requests.Response: _description_
    """
    if isinstance(api_key, str):
        headers = {"x-api-key": api_key}
        response = requests.post(
            url=url, headers=headers, timeout=timeout, params=params, json=payload
        )
    else:
        response = requests.post(url=url, timeout=timeout, params=params, json=payload)
    response.raise_for_status()
    return response


@retry(tries=3, delay=3)
def api_call_get(url: str, timeout: int = 60, api_key: str | None = None) -> requests.Response:
    """_summary_

    Args:
        url (str): _description_
        timeout (int, optional): _description_. Defaults to 60.
        api_key (str | None, optional): _description_. Defaults to None.

    Returns:
        requests.Response: _description_
    """
    if isinstance(api_key, str):
        headers = {"x-api-key": api_key}
        response = requests.get(url=url, headers=headers, timeout=timeout)
    else:
        response = requests.get(url=url, timeout=timeout)
    response.raise_for_status()
    return response
