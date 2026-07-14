from dataclasses import dataclass
from pathlib import Path
import time

from loguru import logger
from pandas import DataFrame
import requests
from retry import retry
from tqdm import tqdm

from kibad_crawler.utils import get_human_readable_size


def download_open_access_pdfs(df_pdfs: DataFrame, path: Path):
    """Download the PDF from the URLs in the DataFrame.

    Args:
        df_pdfs (DataFrame): DataFrame with list of URLs and paperId for names.
        path (Path): Path to save the downloaded files.
    """
    for _, r in tqdm(df_pdfs.iterrows(), total=df_pdfs.shape[0], desc="Downloading PDFs"):
        crawler = Crawler(
            url=r["openAccessPdf.url"],
            path=path / "pdf",
            file_name=f'{r["paperId"]}.pdf',
        )
        crawler.download_file()


@dataclass
class Crawler:
    """Handles the downloading of files.

    It is expected to handle more complex scenarios than direct requests of the
    files from a website.
    """

    def __init__(self, url: str, path: Path, file_name: str):
        self.url = url
        self.path = path
        self.file_name = file_name

    def _verify_download(self, file_path: Path, file_size: float):
        """Verifies is a file was correctly downloaded by comparing the bytes
        in the requests call with the byte size on disk. If they are not equal
        the downloaded file is deleted."""
        size = file_path.stat().st_size
        if size == file_size:
            logger.info(
                f"'{file_path}' downloaded and verified: {get_human_readable_size(int(size))}"
            )
        else:
            logger.info(
                f"Downloaded file: {get_human_readable_size(int(size))} and requested file: {get_human_readable_size(file_size)} are not the same. File {file_path} deleted."
            )
            file_path.unlink()

    @retry(delay=2, tries=3)
    def download_file(
        self,
        delay: int = 1,
        chunk_size: int = 10 * 1024,
        overwrite: bool = False,
    ) -> Path:
        """Download file from a `url` and stores it to a `path`.

        Args:
            chunk_size (int, optional): Size of chunks to store. Defaults to 10*1024.
            file_name (str): Name of the file without path.
            overwrite (bool, optional): Whether or not overwrite a file that
                has been already downloaded. Defaults to False.
            delay (float): Seconds to wait when downloading files. Defaults to DELAY_S2_API,

        Returns:
            Path: Path to the stored file.
        """
        self.path.mkdir(parents=True, exist_ok=True)
        out_path = self.path / self.file_name

        if not overwrite and out_path.exists():
            logger.info(f"File '{self.file_name}' already downloaded")
            return out_path

        logger.debug(f"Downloading: '{self.url}' -> '{out_path}'")
        with requests.get(self.url, stream=True, allow_redirects=True, timeout=10) as response:
            file_size = (
                int(response.headers["Content-Length"])
                if "Content-Length" in response.headers
                else 0
            )
            if response.ok:
                with open(out_path, mode="wb") as f:
                    for chunk in response.iter_content(chunk_size=chunk_size):
                        f.write(chunk)
                self._verify_download(out_path, file_size)
            elif response.status_code == 403:
                logger.warning(f"{response.status_code} code: Access Denied to {self.url}")
            else:
                response.raise_for_status()

        time.sleep(delay)

        return out_path
