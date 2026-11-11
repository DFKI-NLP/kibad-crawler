"""Test reading the screening tables and resolving their DOIs."""

from pathlib import Path

import pandas as pd
import pytest

from kibad_crawler.evaluation import reference_papers

TABLES = reference_papers.ScreeningTables("test", ["first.xlsx", "second.csv"], ["Q1"])


@pytest.fixture
def screening_tables(tmp_path: Path, monkeypatch) -> Path:
    """Write two screening tables that share a paper, and one row without DOI.
    The second one has the free text decisions and the column `DOI` of the
    Soil tables, and a paper labelled with another chapter that is left out."""
    pd.DataFrame({"doi": [" 10.1/A ", "10.1/b", None], "included": [1, None, 0]}).to_excel(
        tmp_path / "first.xlsx", index=False
    )
    pd.DataFrame(
        {
            "DOI": ["10.1/b", "10.1/c", "10.1/d"],
            "Relevant (Ja/Nein/Unsicher)": ["nein - nur physik", None, "Agrar"],
        }
    ).to_csv(tmp_path / "second.csv", index=False)
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

    assert df.fillna(-1).values.tolist() == [
        ["10.1/a", 1, "first.xlsx"],
        ["10.1/b", -1, "first.xlsx"],
        ["10.1/b", 0, "second.csv"],
        ["10.1/c", -1, "second.csv"],
    ]


@pytest.mark.parametrize(
    "label, expected",
    [
        ("Ja", 1),
        ("ja- Monitoring", 1),
        ("relevant", 1),
        ("nein\\", 0),
        ("Nei", 0),
        ("no", 0),
        ("nicht relevant", 0),
        (None, None),
        (" ", None),
    ],
)
def test_get_decisions(label, expected):
    decisions = reference_papers.get_decisions(pd.DataFrame({"Relevant": [label]}))

    assert decisions.fillna(-1).tolist() == [-1 if expected is None else expected]


def test_get_decisions_leaves_out_other_chapters():
    df = pd.DataFrame({"Relevant": ["Ja", "Treiber", "Nein", "Wald", None]})

    decisions = reference_papers.get_decisions(df)

    assert decisions.index.tolist() == [0, 2, 4]
    assert decisions.fillna(-1).tolist() == [1, 0, -1]


def test_resolve_dois(monkeypatch):
    monkeypatch.setattr(reference_papers.academic_graph, "batch", fake_batch)
    monkeypatch.setattr(reference_papers, "DELAY_BETWEEN_BATCHES", 0)

    df = reference_papers.resolve_dois(["10.1/a", "10.1/b", "10.1/c"])

    assert df["doi"].tolist() == ["10.1/a", "10.1/b"]
    assert df["paperId"].tolist() == ["p-a", "p-b"]
    assert df["publication_venue_id"].tolist() == ["venue-1", None]


def test_get_reference_papers(screening_tables, monkeypatch):
    monkeypatch.setattr(reference_papers.academic_graph, "batch", fake_batch)

    df = reference_papers.get_reference_papers(TABLES, tables_dir=screening_tables)

    # one row per paper, the unknown DOI is left out and the decision of the
    # second table wins over no decision in the first
    assert dict(zip(df["paperId"], df["included"])) == {"p-a": 1, "p-b": 0}
    assert (screening_tables / "test_dois_s2.csv").exists()


def test_get_reference_papers_reuses_resolved_dois(screening_tables, monkeypatch):
    monkeypatch.setattr(reference_papers.academic_graph, "batch", fake_batch)
    reference_papers.get_reference_papers(TABLES, tables_dir=screening_tables)

    def fail(ids, fields):
        raise AssertionError("the API must not be called again")

    monkeypatch.setattr(reference_papers.academic_graph, "batch", fail)
    df = reference_papers.get_reference_papers(TABLES, tables_dir=screening_tables)

    assert sorted(df["paperId"]) == ["p-a", "p-b"]
