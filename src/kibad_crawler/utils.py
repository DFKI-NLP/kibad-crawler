from pathlib import Path

import requests
from loguru import logger
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


@retry(delay=2, tries=5)
def download_file(url: str, file_path: Path):
    response = requests.get(url=url, timeout=60, allow_redirects=True)
    logger.info(
        f"Downloaded {url} {get_human_readable_size(int(response.headers['Content-Length']))}"
    )
    # save it to file_path
    ...
