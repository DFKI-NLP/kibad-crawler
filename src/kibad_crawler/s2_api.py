"""Semantic Scholar API client: datasets, incremental diffs, and recommendations."""

from datetime import datetime
import gzip
from io import StringIO
import os
from pathlib import Path
from typing import Any, Literal

import pandas as pd
import requests
from tqdm import tqdm

from .config import MAX_NUM_BULK_PAPERS, RAW_DATA_DIR, S2_API_KEY
from .relevance import filter_papers
from .s2_models import DiffResponse, RecommendationsResponse, RelevanceFilter

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


class S2Client:
    """Client for Semantic Scholar Datasets API, incremental diffs, and Recommendations API."""

    def __init__(
        self,
        api_key: str | None = None,
        timeout_download: int = 60,
        timeout_request: int = 30,
    ):
        self._api_key = api_key or S2_API_KEY
        self._timeout_download = timeout_download
        self._timeout_request = timeout_request
        self._headers = {"x-api-key": self._api_key} if self._api_key else {}

    def download_dataset(
        self,
        release_id: str,
        dataset_name: DatasetName,
    ) -> requests.Response:
        """Download dataset from Semantic Scholar API.

        Args:
            release_id (str): Release id with format `YYYY-MM-DD`.
            dataset_name (str): Dataset name i.e.: `publication-venues`, `papers`.

        Returns:
            requests.Response: Response from the API.
        """
        url = f"{BASE_URL_DATASETS}/release/{release_id}/dataset/{dataset_name}"
        logger.debug("Downloading dataset: release=%s dataset=%s", release_id, dataset_name)
        response = requests.get(url, headers=self._headers, timeout=self._timeout_download)
        response.raise_for_status()
        return response

    def download_file(
        self,
        url: str,
        path: Path,
        chunk_size: int = 10 * 1024,
    ) -> Path:
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
        logger.debug("Downloading file: %s -> %s", file_name, path)
        with requests.get(
            url, stream=True, allow_redirects=True, timeout=10
        ) as response:
            response.raise_for_status()
            out_path = path / file_name
            with open(out_path, mode="wb") as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    f.write(chunk)
        logger.info("Downloaded %s", out_path)
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
            logger.debug("Skipping existing %s", csv_path)
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
        logger.info("Wrote %s (%d rows)", csv_path, len(df_papers))

        if not persistant:
            os.remove(file_path)
            logger.debug("Removed %s", file_path)

    def download_all_papers(
        self,
        file_list: list[str],
        release_path: Path,
        publication_venue_ids: list[str],
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
        logger.info("Downloading %d paper files to %s", len(file_list), release_path)
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
        logger.debug("Bulk paper request: %d IDs", len(ids))
        response = requests.post(
            url,
            headers=self._headers,
            params={"fields": fields},
            json={"ids": ids},
            timeout=self._timeout_request,
        )
        response.raise_for_status()
        return response

    # Releases

    def get_releases(self) -> list[str]:
        """Return list of release IDs (YYYY-MM-DD), oldest first. Latest is last."""
        url = f"{BASE_URL_DATASETS}/release"
        logger.debug("Fetching releases: %s", url)
        response = requests.get(url, headers=self._headers, timeout=self._timeout_request)
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
        logger.info("Fetching diff: %s -> %s (%s)", from_release, to_release, dataset_name)
        response = requests.get(
            url,
            headers=self._headers,
            timeout=self._timeout_download,
        )
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
        diff_dir = base_path / to_release / "diffs" / f"{from_release}_to_{to_release}" / dataset_name
        diff_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Diff files will be saved to %s", diff_dir)

        parsed = self.get_diff_parsed(from_release, to_release, dataset_name)
        if not parsed.diffs:
            logger.warning("No diffs in response for %s -> %s %s", from_release, to_release, dataset_name)
            return []

        downloaded: list[Path] = []
        for entry in parsed.diffs:
            for file_info in entry.update_files + entry.deleted_files:
                try:
                    path = self.download_file(file_info.url, diff_dir)
                    downloaded.append(path)
                except Exception as e:
                    logger.error("Failed to download %s: %s", file_info.url, e)
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
        logger.info("Last two releases: %s -> %s", from_release, to_release)
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
        logger.debug("Recommendations for paper %s (limit=%d)", paper_id, limit)
        response = requests.get(
            url,
            headers=self._headers,
            params={"limit": limit},
            timeout=self._timeout_request,
        )
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
    return _client().download_dataset(release_id=release_id, dataset_name=dataset_name)


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
