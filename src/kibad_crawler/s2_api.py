"""Semantic Scholar API client: datasets, incremental diffs, and recommendations."""

from dataclasses import dataclass
from datetime import datetime
import gzip
import os
import time
from io import StringIO
from pathlib import Path
from typing import Any, Literal

import pandas as pd
import requests
from retry import retry
from tqdm import tqdm

from .config import MAX_NUM_BULK_PAPERS, RAW_DATA_DIR, S2_API_KEY, DELAY_S2_API
from .relevance import filter_papers
from .s2_models import DiffResponse, RecommendationsResponse, RelevanceFilter
from kibad_crawler.utils import get_human_readable_size

try:
    from loguru import logger
except ImportError:
    import logging

    logger = logging.getLogger(__name__)


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

BASE_URL_DATASETS = "https://api.semanticscholar.org/datasets/v1"
BASE_URL_GRAPH = "https://api.semanticscholar.org/graph/v1"
BASE_URL_RECOMMENDATIONS = "https://api.semanticscholar.org/recommendations/v1"


def chunker(seq: list, size: int):
    """Divide a large list into lists of the given size."""
    return (seq[pos : pos + size] for pos in range(0, len(seq), size))


def get_publication_venue_id_from_issn_codes(
    file_path: Path | str, df_venues: pd.DataFrame
) -> list[str]:
    """Returns a list of publication_venue_id codes that is the results from
    combining the ISSN codes of journals and the S2 publication_venues dataset.

    For the FA project the private file can be found in the following link and
    it is called "Übersicht relevante Journals und Archive":
    - https://docs.google.com/spreadsheets/d/1ugPuiRNmcVYWcV98TvXsyqVwJYhmk2iZjZ4o9estM2Y/edit?gid=1647072097#gid=1647072097

    It is expected that the file contains the following two columns:
    - Online ISSN
    - Print ISSN

    Args:
        file_path (Path | str): Path to the file with journals and ISSN codes.
        df_venues (pd.DataFrame): Dataset with publication_venues.

    Returns:
        list[str]: List with publication_venue_id codes to filter the
        publication venues dataset.
    """
    file_path = Path(file_path)
    df_journals = pd.read_csv(file_path)
    issn = [x for x in df_journals["Online ISSN"].unique() if isinstance(x, str)] + [
        x for x in df_journals["Print ISSN"].unique() if isinstance(x, str)
    ]
    publication_venue_ids = df_venues[df_venues["issn"].isin(issn)].id.unique()
    if df_journals is not None:
        logger.info(
            f"{df_journals.shape[0]} journals in the file | {len(issn)} ISSN codes | {len(publication_venue_ids)} S2 'publication_venue_id' found."
        )
    return list(publication_venue_ids)


@dataclass
class S2Client:
    """Client for Semantic Scholar Datasets API, incremental diffs, and Recommendations API."""

    def __init__(
        self,
        api_key: str | None = None,
        timeout_download: int = 60,
        timeout_request: int = 30,
        storage_path: str | None = None,
    ):
        self._api_key = api_key or S2_API_KEY
        self._timeout_download = timeout_download
        self._timeout_request = timeout_request
        self._headers = {"x-api-key": self._api_key} if self._api_key else {}
        self._releases = self.get_releases()
        if storage_path:
            self._storage_path = Path(storage_path)
        else:
            self._storage_path = RAW_DATA_DIR / "semantic_scholar" / "release"

        if self._api_key is not None:
            logger.info("Semantic Scholar API key found")
            logger.info(f"'{self.latest_release}' is the latest release")
        else:
            logger.info(
                "Semantic Scholar API not key found. Please add an API key or go to https://www.semanticscholar.org/product/api to request an API key."
            )

    @property
    def releases(self) -> list[str]:
        """Returns a list of releases in format `YYYY-MM-DD`"""
        return self._releases

    @property
    def latest_release(self) -> str:
        """Returns the latest release `YYYY-MM-DD`"""
        return self._releases[-1]

    def get_publication_venues(self, release_id: str | None = None) -> pd.DataFrame:
        """Returns a pd.DataFrame with all the publication venues of the given
        `release_id`. If no `release_id` is provided, it uses the latest one.

        Args:
            release_id (str | None): Release id in the format of 'YYYY-MM-DD'.
                Defaults to None.

        Returns:
            pd.DataFrame: Publication venues of the given `release_id`.
        """
        release_id = release_id or self.latest_release
        publication_venues_file_path = self.download_publication_venues(release_id=release_id)
        with gzip.open(
            publication_venues_file_path,
            "r",
        ) as f:
            file_content = f.read()

        df_venues = pd.read_json(StringIO(file_content.decode()), lines=True)
        return df_venues

    def get_dataset_url(
        self, dataset_name: DatasetName, release_id: str | None = None
    ) -> requests.Response:
        """Download dataset from Semantic Scholar API.

        Args:
            release_id (str): Release id with format `YYYY-MM-DD`.
            dataset_name (str): Dataset name i.e.: `publication-venues`, `papers`.

        Returns:
            requests.Response: Response from the API.
        """
        release_id = release_id or self.latest_release
        url = f"{BASE_URL_DATASETS}/release/{release_id}/dataset/{dataset_name}"
        logger.debug(
            f"Acquiring links for dataset: release='{release_id}' dataset='{dataset_name}'"
        )
        time.sleep(DELAY_S2_API)
        response = requests.get(url, headers=self._headers, timeout=self._timeout_download)
        time.sleep(DELAY_S2_API)
        response.raise_for_status()
        if response.ok:
            logger.info(
                f"{len(response.json()['files'])} files for '{release_id}' '{dataset_name}' dataset"
            )
        return response

    def download_publication_venues(
        self, release_id: str | None = None, overwrite: bool = False
    ) -> Path:
        """Download the publication venues of a given release. It uses the
        latest release as default value.

        Args:
            release_id (str | None, optional): Release id in the format of
                'YYYY-MM-DD'. Defaults to None.
            overwrite (bool, optional): Overwrite already downloaded files.
                Defaults to False.

        Returns:
            Path: Path to the publication venues file.
        """
        release = release_id or self.latest_release
        response_publication_venues = self.get_dataset_url(
            release_id=release, dataset_name="publication-venues"
        )

        # publication-venues provides is a single url
        url = response_publication_venues.json()["files"][0]
        path = self._storage_path / f"{release_id}" / "publication_venues"

        out_path = self.download_file(url=url, path=path, overwrite=overwrite)

        return out_path

    @retry(delay=10, tries=3)
    def download_file(
        self, url: str, path: Path, chunk_size: int = 10 * 1024, overwrite: bool = False
    ) -> Path:
        """Download file from a `url` and stores it to a `path`.

        Args:
            url (str): URL to the file.
            path (Path): Path where to store the downloaded file.
            chunk_size (int, optional): Size of chunks to store. Defaults to 10*1024.
            overwrite (bool, optional): Whether or not overwrite a file that
                has been already downlaoded. Defaults to False.

        Returns:
            Path: Path to the stored file.
        """
        path.mkdir(parents=True, exist_ok=True)
        file_name = url.split("?")[0].split("/")[-1]
        out_path = path / file_name

        if not overwrite and out_path.exists():
            logger.info(f"File '{file_name}' already downloaded")
            return out_path

        logger.debug(f"Downloading file: '{file_name}' -> '{path}'")

        time.sleep(DELAY_S2_API)
        with requests.get(url, stream=True, allow_redirects=True, timeout=10) as response:
            response.raise_for_status()
            with open(out_path, mode="wb") as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    f.write(chunk)

        time.sleep(DELAY_S2_API)

        logger.info(
            f"Downloaded {out_path} {get_human_readable_size(int(response.headers['Content-Length']))}"
        )

        return out_path

    def download_paper_batch(
        self,
        url: str,
        release_path: Path,
        publication_venue_ids: list[str],
        *,
        persistant: bool = False,
        start_date: str = "2023-01-01",
    ) -> None:
        """Download a single file of the papers dataset.

        Args:
            url (str): URL of the papers dataset file.
            release_path (Path): Base path for this release (papers and CSV go under here).
            publication_venue_ids (list): List of venue IDs to keep.
            persistant (bool, optional): If False, remove the downloaded .gz after filtering.
            start_date (str, optional): Only keep papers with publication date >= this (YYYY-MM-DD).
        """
        file_name = url.split("?")[0].split("/")[-1]
        csv_path = release_path / "papers" / f"{file_name}.csv"
        if csv_path.exists():
            logger.debug(f"Skipping existing {csv_path}")
            return

        file_path = self.download_file(url=url, path=release_path / "papers")
        file_content = ""
        with gzip.open(file_path, "r") as f:
            for line in tqdm(f.readlines(), leave=True):
                if any(x in line.decode() for x in publication_venue_ids):
                    file_content += line.decode()

        df_papers = pd.read_json(StringIO(file_content), lines=True)
        date_filter = datetime.strptime(start_date, "%Y-%m-%d")
        df_papers["publicationdate"] = pd.to_datetime(df_papers["publicationdate"])
        df_papers = df_papers[df_papers["publicationdate"] >= date_filter]
        df_papers.to_csv(csv_path, index=False)
        logger.info(f"Wrote {csv_path} ({len(df_papers)} rows)")

        if not persistant:
            os.remove(file_path)
            logger.debug(f"Removed {file_path}")

    def _download_all_papers(
        self,
        publication_venue_ids: list[str],
        release_id: str | None = None,
        n_pages: int = 0,
        *,
        start_date: str = "2023-01-01",
        # end_date: str | None = None,
        persistant: bool = False,
    ) -> Path:
        """Download all the files from a list of urls.

        It generates a CSV file with the paper selection and deletes the .gz file.
        The CSV files will be used to extract the `paperid` to query the API for
        the rest of metadata of the paper.

        Args:
            file_list (list): List of urls.
            release_path (Path): Base path for this release.
            publication_venue_ids (list): List of publication venue ids.
            start_date (str, optional): Only keep papers with publication date >= this.
            persistant (bool, optional): If False, delete each .gz after filtering.
        """
        # Get a list of paper url
        # Download and save the to disk
        # Open and filter the content
        # Export the selected list
        # Return path to the files to generate a dataframe with them

        release_id = release_id or self.latest_release
        release_path = self._storage_path / f"{release_id}"
        response_papers = self.get_dataset_url(dataset_name="papers", release_id=release_id)
        file_list = response_papers.json()["files"]
        if n_pages > 0:
            file_list = file_list[:n_pages]
        logger.info(f"Downloading {len(file_list)} paper files to {release_path}")
        for url in tqdm(file_list, total=len(file_list)):
            self.download_paper_batch(
                url=url,
                release_path=release_path,
                publication_venue_ids=publication_venue_ids,
                start_date=start_date,
                persistant=persistant,
            )

        return release_path / "papers"

    def download_all_papers(
        self,
        file_list: list[str],
        release_path: Path,
        publication_venue_ids: list[str],
        release_id: str | None = None,
        *,
        start_date: str = "2023-01-01",
        persistant: bool = False,
    ) -> None:
        """Download all the files from a list of urls.

        It generates a CSV file with the paper selection and deletes the .gz file.
        The CSV files will be used to extract the `paperid` to query the API for
        the rest of metadata of the paper.

        Args:
            file_list (list): List of urls.
            release_path (Path): Base path for this release.
            publication_venue_ids (list): List of publication venue ids.
            start_date (str, optional): Only keep papers with publication date >= this.
            persistant (bool, optional): If False, delete each .gz after filtering.
        """
        # Get a list of paper url
        # Download and save the to disk
        # Open and filter the content
        # Export the selected list
        # Return path to the files to generate a dataframe with them

        release_path = self._storage_path / f"{release_id}"
        response_papers = self.get_dataset_url(dataset_name="papers", release_id=release_id)
        file_list = response_papers.json()["files"]
        logger.info(f"Downloading {len(file_list)} paper files to {release_path}")
        for url in tqdm(file_list, total=len(file_list)):
            self.download_paper_batch(
                url=url,
                release_path=release_path,
                publication_venue_ids=publication_venue_ids,
                start_date=start_date,
                persistant=persistant,
            )

    def download_bulk_paper(
        self,
        paper_ids: list[str],
        fields: str = "corpusId,url,title,abstract,venue,publicationVenue,year,citationCount,isOpenAccess,openAccessPdf,publicationDate,journal,fieldsOfStudy,s2FieldsOfStudy,authors,tldr,publicationTypes,textAvailability",
    ) -> requests.Response:
        """Bulk query to the S2 API.

        Limitations: up to 500 paper ids at a time; up to 10 MB of data; up to 9999 citations.

        Args:
            paper_ids (list): List with the `paperid`s to request.
            fields (str, optional): Fields to request from the API.

        Returns:
            requests.Response: API response.
        """
        url = f"{BASE_URL_GRAPH}/paper/batch"
        ids = paper_ids[:MAX_NUM_BULK_PAPERS]
        logger.debug(f"Bulk paper request: {len(ids)} IDs")
        time.sleep(DELAY_S2_API)
        response = requests.post(
            url,
            headers=self._headers,
            params={"fields": fields},
            json={"ids": ids},
            timeout=self._timeout_request,
        )
        time.sleep(DELAY_S2_API)
        response.raise_for_status()
        return response

    # Releases

    def get_releases(self) -> list[str]:
        """Return list of release IDs (YYYY-MM-DD), oldest first. Latest is last."""
        url = f"{BASE_URL_DATASETS}/release"
        logger.debug(f"Fetching releases: {url}")
        time.sleep(DELAY_S2_API)
        response = requests.get(url, headers=self._headers, timeout=self._timeout_request)
        time.sleep(DELAY_S2_API)
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, list) else list(data)

    # Incremental diff

    def get_diff(
        self,
        from_release: str,
        to_release: str,
        dataset_name: DatasetName,
    ) -> requests.Response:
        """Get download links for incremental diff between two releases.

        Args:
            from_release (str): Start release ID (YYYY-MM-DD).
            to_release (str): End release ID (YYYY-MM-DD).
            dataset_name (str): Dataset name e.g. `papers`, `publication-venues`.

        Returns:
            requests.Response: Response with JSON containing 'diffs' (update_files, etc.).
        """
        url = f"{BASE_URL_DATASETS}/diffs/{from_release}/to/{to_release}/{dataset_name}"
        logger.info(f"Fetching diff: {from_release} -> {to_release} ({dataset_name})")
        time.sleep(DELAY_S2_API)
        response = requests.get(
            url,
            headers=self._headers,
            timeout=self._timeout_download,
        )
        time.sleep(DELAY_S2_API)
        response.raise_for_status()
        return response

    def get_diff_parsed(
        self,
        from_release: str,
        to_release: str,
        dataset_name: DatasetName,
    ) -> DiffResponse:
        """Get incremental diff and return a parsed DiffResponse."""
        response = self.get_diff(from_release, to_release, dataset_name)
        return DiffResponse.from_dict(response.json())

    def download_diff_files(
        self,
        from_release: str,
        to_release: str,
        dataset_name: DatasetName,
        base_path: Path | None = None,
    ) -> list[Path]:
        """Get diff metadata, then download all update files into a subfolder.

        Subfolder pattern: base_path / to_release / diffs / {from_release}_to_{to_release} / dataset_name

        Args:
            from_release (str): Start release ID.
            to_release (str): End release ID.
            dataset_name (str): Dataset name.
            base_path (Path, optional): Base directory. Defaults to RAW_DATA_DIR / semantic_scholar / release.

        Returns:
            list[Path]: List of paths to downloaded files.
        """
        if base_path is None:
            base_path = RAW_DATA_DIR / "semantic_scholar" / "release"
        diff_dir = (
            base_path / to_release / "diffs" / f"{from_release}_to_{to_release}" / dataset_name
        )
        diff_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Diff files will be saved to {diff_dir}")

        parsed = self.get_diff_parsed(from_release, to_release, dataset_name)
        if not parsed.diffs:
            logger.warning(
                f"No diffs in response for '{from_release}' -> '{to_release}' '{dataset_name}'"
            )
            return []

        downloaded: list[Path] = []
        for entry in parsed.diffs:
            for file_info in entry.update_files + entry.deleted_files:
                try:
                    path = self.download_file(file_info.url, diff_dir)
                    downloaded.append(path)
                except Exception as e:
                    logger.error(f"Failed to download {file_info.url}: {e}")
        return downloaded

    def download_last_two_releases_diff(
        self,
        dataset_name: DatasetName = "papers",
        base_path: Path | None = None,
    ) -> list[Path]:
        """Resolve the latest two releases, then download their diff into a subfolder.

        Args:
            dataset_name (str): Dataset to diff.
            base_path (Path, optional): Base directory for release/diffs.

        Returns:
            list[Path]: List of paths to downloaded diff files.
        """
        releases = self.get_releases()
        if len(releases) < 2:
            logger.warning("Fewer than 2 releases; cannot compute diff")
            return []
        from_release = releases[-2]
        to_release = releases[-1]
        logger.info(f"Last two releases: {from_release} -> {to_release}")
        return self.download_diff_files(
            from_release=from_release,
            to_release=to_release,
            dataset_name=dataset_name,
            base_path=base_path,
        )

    # Recommendations API

    def get_recommendations_for_paper(
        self,
        paper_id: str,
        limit: int = 10,
    ) -> RecommendationsResponse:
        """Get recommended papers for a given paper (Recommendations API).

        Args:
            paper_id (str): S2 paper ID (e.g. from paperId or from URL).
            limit (int, optional): Max number of recommendations. Defaults to 10.

        Returns:
            RecommendationsResponse: Parsed response with .recommendations list.
        """
        url = f"{BASE_URL_RECOMMENDATIONS}/paper/{paper_id}"
        logger.debug(f"Recommendations for paper {paper_id} (limit={limit})")
        time.sleep(DELAY_S2_API)
        response = requests.get(
            url,
            headers=self._headers,
            params={"limit": limit},
            timeout=self._timeout_request,
        )
        time.sleep(DELAY_S2_API)
        response.raise_for_status()
        return RecommendationsResponse.from_dict(response.json())

    # Relevance filter

    def filter_by_relevance(
        self,
        papers: list[dict[str, Any]],
        criteria: RelevanceFilter,
    ) -> list[dict[str, Any]]:
        """Filter paper dicts (S2 bulk API shape) by relevance criteria.

        Args:
            papers (list): List of paper objects as returned by download_bulk_paper().json().
            criteria (RelevanceFilter): min_citation_count, venue_ids, fields_of_study, keywords.

        Returns:
            list: Subset of papers that satisfy all criteria.
        """
        return filter_papers(papers, criteria)


_default_client: S2Client | None = None


def _client() -> S2Client:
    global _default_client
    if _default_client is None:
        _default_client = S2Client()
    return _default_client


# Backward-compatible module-level API (notebook and existing code)


def download_dataset(
    release_id: str,
    dataset_name: DatasetName,
) -> requests.Response:
    """Download dataset from Semantic Scholar API. See S2Client.download_dataset."""
    return _client().get_dataset_url(release_id=release_id, dataset_name=dataset_name)


def download_file(url: str, path: Path, chunk_size: int = 10 * 1024) -> Path:
    """Download file from URL to path. See S2Client.download_file."""
    return _client().download_file(url=url, path=path, chunk_size=chunk_size)


def download_paper_batch(
    url: str,
    release_path: Path,
    publication_venue_ids: list,
    persistant: bool = False,
    start_date: str = "2023-01-01",
) -> None:
    """Download a single papers dataset file; filter by venue/date; save CSV. See S2Client.download_paper_batch."""
    _client().download_paper_batch(
        url=url,
        release_path=release_path,
        publication_venue_ids=publication_venue_ids,
        persistant=persistant,
        start_date=start_date,
    )


def download_all_papers(
    file_list: list[str],
    release_path: Path,
    publication_venue_ids: list[str],
    start_date: str = "2023-01-01",
    persistant: bool = False,
) -> None:
    """Download all paper files; filter by venue/date; save CSVs. See S2Client.download_all_papers."""
    _client().download_all_papers(
        file_list=file_list,
        release_path=release_path,
        publication_venue_ids=publication_venue_ids,
        start_date=start_date,
        persistant=persistant,
    )


def download_bulk_paper(
    paper_ids: list,
    fields: str = "corpusId,url,title,abstract,venue,publicationVenue,year,citationCount,isOpenAccess,openAccessPdf,publicationDate,journal,fieldsOfStudy,s2FieldsOfStudy,authors,tldr,publicationTypes,textAvailability",
) -> requests.Response:
    """Bulk query S2 API for paper metadata. See S2Client.download_bulk_paper."""
    return _client().download_bulk_paper(paper_ids=paper_ids, fields=fields)
