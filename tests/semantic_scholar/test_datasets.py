import gzip
import json
from pathlib import Path

import pandas as pd
import pytest
import requests

from kibad_crawler.semantic_scholar import datasets

# pre-signed download links have a query string that is not part of the file name
FILE_URL = "https://ai2-s2ag.s3.amazonaws.com/staging/2026-09-01/papers/file-0.gz?AWSAccessKeyId=abc&Expires=123"


@pytest.fixture
def api_calls(monkeypatch, make_response):
    """Replace `api_call_get` in the datasets module and return the list of
    calls. The content of the response can be set with `api_calls.content`."""

    class ApiCalls(list):
        content: bytes = b"{}"
        status_code: int = 200

    calls = ApiCalls()

    def fake_api_call_get(**kwargs):
        calls.append(kwargs)
        return make_response(status_code=calls.status_code, content=calls.content)

    monkeypatch.setattr(datasets, "api_call_get", fake_api_call_get)
    monkeypatch.setattr(datasets, "S2_API_KEY", "test-key")
    return calls


def test_get_available_releases(api_calls):
    api_calls.content = b'["2026-08-25", "2026-09-01"]'

    assert datasets.get_available_releases() == ["2026-08-25", "2026-09-01"]
    # listing the releases does not need an API key
    assert api_calls == [{"url": "https://api.semanticscholar.org/datasets/v1/release/"}]


def test_get_available_releases_not_ok(api_calls):
    api_calls.status_code = 500

    assert datasets.get_available_releases() == []


def test_get_latest_release(api_calls):
    api_calls.content = b'["2026-08-18", "2026-08-25", "2026-09-01"]'

    assert datasets.get_latest_release() == "2026-09-01"


def test_list_datasets(api_calls):
    api_calls.content = b'{"release_id": "2026-09-01", "datasets": [{"name": "papers"}]}'

    release = datasets.list_datasets("2026-09-01")

    assert release == {"release_id": "2026-09-01", "datasets": [{"name": "papers"}]}
    assert api_calls == [{"url": "https://api.semanticscholar.org/datasets/v1/release/2026-09-01"}]


def test_download_links(api_calls):
    links = {"name": "papers", "description": "", "README": "", "files": [FILE_URL]}
    api_calls.content = json.dumps(links).encode()

    assert datasets.download_links("2026-09-01", "papers") == links
    # the dataset links need the API key
    assert api_calls == [
        {
            "url": "https://api.semanticscholar.org/datasets/v1/release/2026-09-01/dataset/papers",
            "api_key": "test-key",
        }
    ]


def test_download_links_incremental_diffs(api_calls):
    api_calls.content = b'{"dataset": "papers", "diffs": []}'

    diffs = datasets.download_links_incremental_diffs(
        dataset_name="papers", end_release_id="2026-09-01", start_release_id="2026-08-25"
    )

    assert diffs == {"dataset": "papers", "diffs": []}
    assert api_calls == [
        {
            "url": "https://api.semanticscholar.org/datasets/v1/diffs/2026-08-25/to/2026-09-01/papers",
            "api_key": "test-key",
        }
    ]


@pytest.fixture
def get_requests(monkeypatch, make_response):
    """Replace `requests.get` in the datasets module and return the list of
    requested URLs. The status code of the response can be set with
    `get_requests.status_code`."""

    class GetRequests(list):
        status_code: int = 200

    urls = GetRequests()

    def fake_get(url, **kwargs):
        urls.append(url)
        return make_response(
            status_code=urls.status_code,
            content=b"file content",
            headers={"Content-Length": "12"},
        )

    monkeypatch.setattr(datasets.requests, "get", fake_get)
    return urls


def test_download_dataset_from_semantic_scholar(tmp_path: Path, get_requests):
    output_path = tmp_path / "release" / "2026-09-01" / "papers"

    out_path = datasets.download_dataset_from_semantic_scholar(
        url=FILE_URL, output_path=output_path, chunk_size=4
    )

    # the output directory is created and the query string is removed from the file name
    assert out_path == output_path / "file-0.gz"
    assert out_path.read_bytes() == b"file content"
    assert get_requests == [FILE_URL]
    # the temporary file of the download is renamed, not left behind
    assert [x.name for x in output_path.iterdir()] == ["file-0.gz"]


def test_download_dataset_from_semantic_scholar_already_downloaded(tmp_path: Path, get_requests):
    (tmp_path / "file-0.gz").write_bytes(b"old content")

    out_path = datasets.download_dataset_from_semantic_scholar(url=FILE_URL, output_path=tmp_path)

    assert out_path.read_bytes() == b"old content"
    assert get_requests == []

    out_path = datasets.download_dataset_from_semantic_scholar(
        url=FILE_URL, output_path=tmp_path, overwrite=True
    )

    assert out_path.read_bytes() == b"file content"
    assert get_requests == [FILE_URL]


def test_download_dataset_from_semantic_scholar_http_error(
    tmp_path: Path, get_requests, no_retry_delay
):
    # e.g. a pre-signed download link that is not valid anymore
    get_requests.status_code = 400

    with pytest.raises(requests.HTTPError):
        datasets.download_dataset_from_semantic_scholar(url=FILE_URL, output_path=tmp_path)
    # the download is retried 3 times and no incomplete file is left behind
    assert get_requests == [FILE_URL] * 3
    assert not (tmp_path / "file-0.gz").exists()


def test_download_dataset_from_semantic_scholar_interrupted(
    tmp_path: Path, monkeypatch, no_retry_delay
):
    class InterruptedResponse:
        """Response that stops sending data in the middle of the download."""

        headers = {"Content-Length": "12"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def raise_for_status(self):
            pass

        def iter_content(self, chunk_size):
            yield b"file"
            raise requests.ConnectionError("connection broken")

    monkeypatch.setattr(datasets.requests, "get", lambda url, **kwargs: InterruptedResponse())

    with pytest.raises(requests.ConnectionError):
        datasets.download_dataset_from_semantic_scholar(url=FILE_URL, output_path=tmp_path)

    # an interrupted download leaves no file that the next call would reuse
    assert list(tmp_path.iterdir()) == []


def test_read_publication_venues(tmp_path: Path):
    venues = [
        {"id": "venue-1", "name": "Forests", "issn": "1999-4907", "type": "journal"},
        {"id": "venue-2", "name": "PLOS ONE", "issn": "1932-6203", "type": "journal"},
    ]
    file_path = tmp_path / "publication-venues.gz"
    with gzip.open(file_path, "wt") as f:
        f.write("\n".join(json.dumps(venue) for venue in venues))

    df_venues = datasets.read_publication_venues(file_path=file_path)

    pd.testing.assert_frame_equal(df_venues, pd.DataFrame(venues))
