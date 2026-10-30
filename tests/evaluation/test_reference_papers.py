"""Test reading the screening tables and resolving their DOIs."""

from pathlib import Path

import pandas as pd
import pytest

from kibad_crawler.evaluation import reference_papers
from kibad_crawler.search_queries import Habitat


@pytest.fixture
def screening_tables(tmp_path: Path, monkeypatch) -> Path:
    """Write two screening tables that share a paper, and one row without DOI."""
    pd.DataFrame(
        {
            "doi": [" 10.1/A ", "10.1/b", None],
            "included": [1, None, 0],
            "year": [2001, 2002, 2003],
        }
    ).to_excel(tmp_path / "first.xlsx", index=False)
    pd.DataFrame({"doi": ["10.1/b", "10.1/c"], "included": [0, None], "year": [2002, 2004]}).to_csv(
        tmp_path / "second.csv", index=False
    )
    monkeypatch.setitem(
        reference_papers.SCREENING_TABLES, Habitat.FOREST, ["first.xlsx", "second.csv"]
    )
    monkeypatch.setattr(reference_papers, "DELAY_BETWEEN_BATCHES", 0)
    return tmp_path


def fake_batch(ids: list[str], fields: str) -> list[dict | None]:
    """Answer like the batch endpoint: `10.1/c` is unknown and `10.1/b` has no
    publication venue."""
    papers: dict[str, dict] = {
        "DOI:10.1/a": {"paperId": "p-a", "publicationVenue": {"id": "venue-1"}},
        "DOI:10.1/b": {"paperId": "p-b", "publicationVenue": None},
    }
    return [papers.get(paper_id) for paper_id in ids]


def test_read_screening_tables(screening_tables):
    df = reference_papers.read_screening_tables(screening_tables, ["first.xlsx", "second.csv"])

    assert df[["doi", "source_file"]].values.tolist() == [
        ["10.1/a", "first.xlsx"],
        ["10.1/b", "first.xlsx"],
        ["10.1/b", "second.csv"],
        ["10.1/c", "second.csv"],
    ]


def test_resolve_dois(monkeypatch):
    monkeypatch.setattr(reference_papers.academic_graph, "batch", fake_batch)
    monkeypatch.setattr(reference_papers, "DELAY_BETWEEN_BATCHES", 0)

    df = reference_papers.resolve_dois(["10.1/a", "10.1/b", "10.1/c"])

    assert df["doi"].tolist() == ["10.1/a", "10.1/b"]
    assert df["paperId"].tolist() == ["p-a", "p-b"]
    assert df["publication_venue_id"].tolist() == ["venue-1", None]


def test_get_reference_papers(screening_tables, monkeypatch):
    monkeypatch.setattr(reference_papers.academic_graph, "batch", fake_batch)

    df = reference_papers.get_reference_papers(Habitat.FOREST, tables_dir=screening_tables)

    # one row per paper, the unknown DOI is left out and the decision of the
    # second table wins over no decision in the first
    assert dict(zip(df["paperId"], df["included"])) == {"p-a": 1, "p-b": 0}
    assert (screening_tables / "forest_dois_s2.csv").exists()


def test_get_reference_papers_reuses_resolved_dois(screening_tables, monkeypatch):
    monkeypatch.setattr(reference_papers.academic_graph, "batch", fake_batch)
    reference_papers.get_reference_papers(Habitat.FOREST, tables_dir=screening_tables)

    def fail(ids, fields):
        raise AssertionError("the API must not be called again")

    monkeypatch.setattr(reference_papers.academic_graph, "batch", fail)
    df = reference_papers.get_reference_papers(Habitat.FOREST, tables_dir=screening_tables)

    assert sorted(df["paperId"]) == ["p-a", "p-b"]
