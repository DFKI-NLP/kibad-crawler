from pathlib import Path

import pytest
import requests

from kibad_crawler import utils


@pytest.mark.parametrize(
    "size, expected",
    [
        (0, "0.0 B"),
        (1023, "1023.0 B"),
        (1024, "1.0 KiB"),
        (1536, "1.5 KiB"),
        (1024**2, "1.0 MiB"),
        (1.8 * 1024**3, "1.8 GiB"),
        (-2048, "-2.0 KiB"),
    ],
)
def test_get_human_readable_size(size: float, expected: str) -> None:
    assert utils.get_human_readable_size(size) == expected


@pytest.mark.parametrize("api_key", [None, "test-key"])
def test_api_call_post(monkeypatch, make_response, api_key: str | None) -> None:
    calls: list[dict] = []

    def fake_post(**kwargs):
        calls.append(kwargs)
        return make_response(content=b'{"ok": true}')

    monkeypatch.setattr(utils.requests, "post", fake_post)

    response = utils.api_call_post(
        url="https://api.semanticscholar.org/graph/v1/paper/batch",
        params={"fields": "title"},
        payload={"ids": ["id-1", "id-2"]},
        api_key=api_key,
    )

    assert response.json() == {"ok": True}
    assert len(calls) == 1
    assert calls[0]["url"] == "https://api.semanticscholar.org/graph/v1/paper/batch"
    assert calls[0]["params"] == {"fields": "title"}
    assert calls[0]["json"] == {"ids": ["id-1", "id-2"]}
    assert calls[0]["timeout"] == 60
    # the API key is only sent in the header when it is given
    if api_key is None:
        assert "headers" not in calls[0]
    else:
        assert calls[0]["headers"] == {"x-api-key": "test-key"}


@pytest.fixture
def retry_delays(monkeypatch) -> list[float]:
    """Skip the waiting time between attempts of the `@retry` decorator and
    return the list of waiting times."""
    delays: list[float] = []
    monkeypatch.setattr("retry.api.time.sleep", lambda delay: delays.append(delay))
    return delays


@pytest.mark.parametrize(
    "status_code, expected_calls",
    [
        # rate limit and server errors are retried
        (429, 6),
        (500, 6),
        # other errors are raised directly, e.g. a missing API key
        (401, 1),
        (400, 1),
    ],
)
def test_api_call_post_http_error(
    monkeypatch, make_response, retry_delays, status_code: int, expected_calls: int
) -> None:
    calls: list[dict] = []

    def fake_post(**kwargs):
        calls.append(kwargs)
        return make_response(status_code=status_code)

    monkeypatch.setattr(utils.requests, "post", fake_post)

    with pytest.raises(requests.HTTPError):
        utils.api_call_post(url="https://api.semanticscholar.org", params={}, payload={})
    assert len(calls) == expected_calls
    # the waiting time between attempts doubles each time
    assert retry_delays == [3, 6, 12, 24, 48][: expected_calls - 1]


def test_api_call_post_rate_limit_then_ok(monkeypatch, make_response, retry_delays) -> None:
    responses = [make_response(status_code=429), make_response(content=b'{"ok": true}')]
    monkeypatch.setattr(utils.requests, "post", lambda **kwargs: responses.pop(0))

    response = utils.api_call_post(url="https://api.semanticscholar.org", params={}, payload={})

    assert response.json() == {"ok": True}
    assert retry_delays == [3]


@pytest.mark.parametrize("api_key", [None, "test-key"])
def test_api_call_get(monkeypatch, make_response, api_key: str | None) -> None:
    calls: list[dict] = []

    def fake_get(**kwargs):
        calls.append(kwargs)
        return make_response(content=b'["2026-08-25", "2026-09-01"]')

    monkeypatch.setattr(utils.requests, "get", fake_get)

    response = utils.api_call_get(
        url="https://api.semanticscholar.org/datasets/v1/release/", api_key=api_key
    )

    assert response.json() == ["2026-08-25", "2026-09-01"]
    assert len(calls) == 1
    assert calls[0]["url"] == "https://api.semanticscholar.org/datasets/v1/release/"
    assert calls[0]["timeout"] == 60
    # the API key is only sent in the header when it is given
    if api_key is None:
        assert "headers" not in calls[0]
    else:
        assert calls[0]["headers"] == {"x-api-key": "test-key"}


@pytest.mark.parametrize(
    "status_code, expected_calls",
    [
        (429, 6),
        (503, 6),
        (401, 1),
        (404, 1),
    ],
)
def test_api_call_get_http_error(
    monkeypatch, make_response, retry_delays, status_code: int, expected_calls: int
) -> None:
    calls: list[dict] = []

    def fake_get(**kwargs):
        calls.append(kwargs)
        return make_response(status_code=status_code)

    monkeypatch.setattr(utils.requests, "get", fake_get)

    with pytest.raises(requests.HTTPError):
        utils.api_call_get(url="https://api.semanticscholar.org")
    # only rate limit and server errors are retried, with a doubling waiting time
    assert len(calls) == expected_calls
    assert retry_delays == [3, 6, 12, 24, 48][: expected_calls - 1]


def test_get_issn_codes(tmp_path: Path) -> None:
    csv_path = tmp_path / "journals.csv"
    csv_path.write_text(
        "Journal,count,Online ISSN,Print ISSN\n"
        "PLOS ONE,56,1932-6203,\n"
        "Forests,14,1999-4907,\n"
        "Some Journal,3,,1234-5678\n"
        "Journal without ISSN,1,,\n"
    )

    # columns with "ISSN" in the name are used, empty values are ignored
    assert sorted(utils.get_issn_codes(csv_path)) == ["1234-5678", "1932-6203", "1999-4907"]
    assert sorted(utils.get_issn_codes(str(csv_path))) == ["1234-5678", "1932-6203", "1999-4907"]


def test_get_issn_codes_without_issn_columns(tmp_path: Path) -> None:
    csv_path = tmp_path / "journals.csv"
    csv_path.write_text("Journal,count\nForests,14\n")

    assert utils.get_issn_codes(csv_path) == []


@pytest.mark.parametrize(
    "seq, size, expected",
    [
        ([1, 2, 3, 4, 5], 2, [[1, 2], [3, 4], [5]]),
        ([1, 2, 3, 4], 2, [[1, 2], [3, 4]]),
        ([1, 2], 5, [[1, 2]]),
        ([], 3, []),
    ],
)
def test_chunker(seq: list, size: int, expected: list) -> None:
    assert list(utils.chunker(seq, size)) == expected
