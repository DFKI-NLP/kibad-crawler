from collections.abc import Callable

import pytest
import requests


@pytest.fixture
def make_response() -> Callable[..., requests.Response]:
    """Returns a function to create `requests.Response` objects so that tests
    do not call the Semantic Scholar API."""

    def _make_response(
        status_code: int = 200, content: bytes = b"{}", headers: dict | None = None
    ) -> requests.Response:
        """Create a response with the given status code, content and headers.

        Args:
            status_code (int, optional): HTTP status code. Defaults to 200.
            content (bytes, optional): Body of the response. Defaults to b"{}".
            headers (dict | None, optional): Headers of the response. Defaults
                to None.

        Returns:
            requests.Response: Response object.
        """
        response = requests.Response()
        response.status_code = status_code
        response._content = content
        # mark the content as already read so that `iter_content` uses it
        response._content_consumed = True  # type: ignore[attr-defined]
        response.headers.update(headers or {})
        return response

    return _make_response


@pytest.fixture
def no_retry_delay(monkeypatch):
    """Skip the waiting time between attempts of the `@retry` decorator."""
    monkeypatch.setattr("retry.api.time.sleep", lambda _: None)
