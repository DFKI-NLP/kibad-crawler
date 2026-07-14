"""Tests for S2Client and backward-compat s2_api functions."""

from unittest.mock import MagicMock, patch

from kibad_crawler.s2_api import (
    S2Client,
    _client,
    chunker,
    download_bulk_paper,
    download_dataset,
    download_file,
)


def test_chunker():
    assert list(chunker([1, 2, 3, 4, 5], 2)) == [[1, 2], [3, 4], [5]]
    assert list(chunker([], 3)) == []


def test_client_singleton():
    """Default client is a singleton."""
    c1 = _client()
    c2 = _client()
    assert c1 is c2


@patch("kibad_crawler.s2_api.requests.get")
def test_download_dataset(mock_get):
    mock_get.return_value = MagicMock(status_code=200, raise_for_status=MagicMock())
    client = S2Client(api_key="test-key")
    client.get_dataset_url("2026-01-01", "publication-venues")
    mock_get.assert_called_once()
    call_url = mock_get.call_args[0][0]
    assert "2026-01-01" in call_url
    assert "publication-venues" in call_url
    assert mock_get.call_args[1]["headers"]["x-api-key"] == "test-key"


@patch("kibad_crawler.s2_api.requests.get")
def test_get_releases(mock_get):
    mock_get.return_value = MagicMock(
        status_code=200,
        raise_for_status=MagicMock(),
        json=lambda: ["2026-01-20", "2026-01-27", "2026-02-03"],
    )
    client = S2Client(api_key="test-key")
    releases = client.get_releases()
    assert releases == ["2026-01-20", "2026-01-27", "2026-02-03"]
    assert mock_get.call_args[0][0].endswith("/release")


@patch("kibad_crawler.s2_api.requests.get")
def test_get_diff(mock_get):
    mock_get.return_value = MagicMock(
        status_code=200,
        raise_for_status=MagicMock(),
        json=lambda: {
            "diffs": [
                {
                    "update_files": [{"url": "https://example.com/file1.gz"}],
                }
            ]
        },
    )
    client = S2Client(api_key="test-key")
    resp = client.get_diff("2026-01-27", "2026-02-03", "papers")
    data = resp.json()
    assert "diffs" in data
    assert len(data["diffs"]) == 1
    assert data["diffs"][0]["update_files"][0]["url"] == "https://example.com/file1.gz"
    call_url = mock_get.call_args[0][0]
    assert "diffs" in call_url
    assert "2026-01-27" in call_url
    assert "2026-02-03" in call_url


@patch("kibad_crawler.s2_api.requests.get")
def test_get_recommendations_for_paper(mock_get):
    mock_payload = {
        "recommendations": [
            {"paperId": "rec1", "title": "Recommended One"},
            {"paperId": "rec2", "title": "Recommended Two"},
        ]
    }
    mock_get.return_value = MagicMock(
        status_code=200,
        raise_for_status=MagicMock(),
        json=lambda: mock_payload,
    )
    client = S2Client(api_key="test-key")
    result = client.get_recommendations_for_paper("abc123", limit=10)
    assert result.recommendations == mock_payload["recommendations"]
    call_url = mock_get.call_args[0][0]
    assert "recommendations" in call_url
    assert "abc123" in call_url
    assert mock_get.call_args[1]["params"]["limit"] == 10


@patch("kibad_crawler.s2_api.requests.post")
def test_download_bulk_paper(mock_post):
    mock_post.return_value = MagicMock(
        status_code=200,
        raise_for_status=MagicMock(),
        json=lambda: [{"paperId": "p1", "title": "Paper 1"}],
    )
    result = download_bulk_paper(["id1", "id2"])
    assert result.json() == [{"paperId": "p1", "title": "Paper 1"}]
    mock_post.assert_called_once()
    assert mock_post.call_args[1]["json"]["ids"] == ["id1", "id2"]


@patch("kibad_crawler.s2_api.requests.get")
def test_backward_compat_download_dataset(mock_get):
    mock_get.return_value = MagicMock(status_code=200, raise_for_status=MagicMock())
    download_dataset("2026-01-01", "papers")
    mock_get.assert_called_once()


@patch("kibad_crawler.s2_api.requests.get")
def test_get_diff_parsed(mock_get):
    mock_get.return_value = MagicMock(
        status_code=200,
        raise_for_status=MagicMock(),
        json=lambda: {
            "dataset": "papers",
            "start_release": "2026-01-27",
            "end_release": "2026-02-03",
            "diffs": [{"update_files": [{"url": "https://example.com/f.gz"}]}],
        },
    )
    from kibad_crawler.s2_models import DiffResponse

    client = S2Client(api_key="test-key")
    parsed = client.get_diff_parsed("2026-01-27", "2026-02-03", "papers")
    assert isinstance(parsed, DiffResponse)
    assert len(parsed.diffs) == 1
    assert len(parsed.diffs[0].update_files) == 1
    assert parsed.diffs[0].update_files[0].url == "https://example.com/f.gz"


def test_relevance_filter_empty_returns_all():
    from kibad_crawler.relevance import filter_papers
    from kibad_crawler.s2_models import RelevanceFilter

    papers = [{"paperId": "1", "title": "A"}, {"paperId": "2", "title": "B"}]
    assert len(filter_papers(papers, RelevanceFilter())) == 2
    assert len(filter_papers(papers, RelevanceFilter(min_citation_count=None))) == 2


def test_relevance_filter_min_citations():
    from kibad_crawler.relevance import filter_papers
    from kibad_crawler.s2_models import RelevanceFilter

    papers = [
        {"paperId": "1", "citationCount": 5},
        {"paperId": "2", "citationCount": 100},
        {"paperId": "3"},
    ]
    criteria = RelevanceFilter(min_citation_count=10)
    result = filter_papers(papers, criteria)
    assert len(result) == 1
    assert result[0]["paperId"] == "2"


def test_relevance_filter_keywords():
    from kibad_crawler.relevance import filter_papers
    from kibad_crawler.s2_models import RelevanceFilter

    papers = [
        {"paperId": "1", "title": "Machine learning in NLP", "abstract": "We study transformers."},
        {"paperId": "2", "title": "Biology", "abstract": "Genes and proteins."},
    ]
    criteria = RelevanceFilter(keywords=["NLP", "transformers"])
    result = filter_papers(papers, criteria)
    assert len(result) == 1
    assert result[0]["paperId"] == "1"


def test_relevance_filter_venue():
    from kibad_crawler.relevance import filter_papers
    from kibad_crawler.s2_models import RelevanceFilter

    papers = [
        {"paperId": "1", "publicationVenue": {"id": "V1"}},
        {"paperId": "2", "publicationVenue": {"id": "V2"}},
    ]
    criteria = RelevanceFilter(venue_ids=["V1"])
    result = filter_papers(papers, criteria)
    assert len(result) == 1
    assert result[0]["paperId"] == "1"


def test_s2_client_filter_by_relevance():
    from kibad_crawler.s2_models import RelevanceFilter

    client = S2Client(api_key="test-key")
    papers = [{"paperId": "1", "citationCount": 3}, {"paperId": "2", "citationCount": 20}]
    filtered = client.filter_by_relevance(papers, RelevanceFilter(min_citation_count=10))
    assert len(filtered) == 1
    assert filtered[0]["paperId"] == "2"
