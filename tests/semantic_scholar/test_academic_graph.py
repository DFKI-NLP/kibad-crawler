import pytest

from kibad_crawler.semantic_scholar import academic_graph


def test_batch(monkeypatch, make_response):
    calls = []

    def fake_api_call_post(**kwargs):
        calls.append(kwargs)
        return make_response(content=b'[{"paperId": "id-1"}, {"paperId": "id-2"}]')

    monkeypatch.setattr(academic_graph, "api_call_post", fake_api_call_post)
    monkeypatch.setattr(academic_graph, "S2_API_KEY", "test-key")

    papers = academic_graph.batch(["id-1", "id-2"], fields="paperId,title,abstract")

    assert papers == [{"paperId": "id-1"}, {"paperId": "id-2"}]
    assert calls == [
        {
            "url": "https://api.semanticscholar.org/graph/v1/paper/batch",
            "params": {"fields": "paperId,title,abstract"},
            "payload": {"ids": ["id-1", "id-2"]},
            "api_key": "test-key",
        }
    ]


def test_batch_default_fields(monkeypatch, make_response):
    calls = []

    def fake_api_call_post(**kwargs):
        calls.append(kwargs)
        return make_response(content=b"[]")

    monkeypatch.setattr(academic_graph, "api_call_post", fake_api_call_post)

    academic_graph.batch(["id-1"])

    # TODO: I think this is bad practice, we should not rely on defaults but explicitly request what we need later.
    #
    # assert that the fields needed by the next steps of the crawler are requested by default
    fields = calls[0]["params"]["fields"].split(",")
    required_fields = ["paperId", "title", "abstract", "openAccessPdf", "publicationDate"]
    assert set(fields).issuperset(required_fields)


def test_batch_more_than_500_ids(monkeypatch, no_retry_delay):
    calls = []
    monkeypatch.setattr(academic_graph, "api_call_post", lambda **kwargs: calls.append(kwargs))

    with pytest.raises(AssertionError, match="More than 500 paper IDs"):
        academic_graph.batch([f"id-{i}" for i in range(501)])
    assert calls == []
