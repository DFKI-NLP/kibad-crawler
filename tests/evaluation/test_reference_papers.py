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
    df = reference_papers.read_screening_tables(screening_tables, TABLES)

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


RIS = """TY  - JOUR\r
TI  - First\r
DO  - 10.1/A\r
N1  - ASReview_relevant\r
ER  - \r
\r
TY  - JOUR\r
DO  - 10.1/b\r
N1  - ASReview_irrelevant\r
ER  - \r
\r
TY  - JOUR\r
DO  - 10.1/c\r
N1  - ASReview_not_seen\r
ER  - \r
\r
TY  - JOUR\r
TI  - No DOI\r
ER  - \r
"""


def test_read_ris(tmp_path):
    (tmp_path / "export.ris").write_text(RIS, encoding="utf-8")

    df = reference_papers.read_ris(tmp_path / "export.ris")

    assert df.fillna(-1).values.tolist() == [
        ["10.1/A", 1],
        ["10.1/b", 0],
        ["10.1/c", -1],
        [-1, -1],
    ]


def test_read_table_sheet_and_header(tmp_path):
    with pd.ExcelWriter(tmp_path / "table.xlsx") as writer:
        pd.DataFrame({"doi": ["10.1/a"], "included": [0]}).to_excel(writer, sheet_name="first")
        pd.DataFrame({"doi": ["10.1/b"], "included": [1]}).to_excel(writer, sheet_name="second")
    # a row with group headers above the column names
    pd.DataFrame([["", "Study type"], ["DOI", "Review"], ["10.1/c", "x"]]).to_excel(
        tmp_path / "selected.xlsx", index=False, header=False
    )

    assert reference_papers.read_table(
        tmp_path / "table.xlsx", sheet="second"
    ).values.tolist() == [["10.1/b", 1]]
    selected = reference_papers.read_table(tmp_path / "selected.xlsx")
    assert selected["doi"].tolist() == ["10.1/c"]
    assert selected["included"].isna().all()


def test_read_screening_tables_with_selected_file(tmp_path):
    (tmp_path / "hits.ris").write_text(RIS, encoding="utf-8")
    pd.DataFrame({"DOI": ["10.1/b"]}).to_excel(tmp_path / "selected.xlsx", index=False)
    tables = reference_papers.ScreeningTables(
        "test", ["hits.ris"], ["Q1"], selected_file="selected.xlsx"
    )

    df = reference_papers.read_screening_tables(tmp_path, tables)

    # the selection decides, not the labels of the hits
    assert dict(zip(df["doi"], df["included"])) == {"10.1/a": 0, "10.1/b": 1, "10.1/c": 0}


def test_get_reference_papers_leaves_out_removed_tables(screening_tables, monkeypatch):
    monkeypatch.setattr(reference_papers.academic_graph, "batch", fake_batch)
    reference_papers.get_reference_papers(TABLES, tables_dir=screening_tables)

    tables = reference_papers.ScreeningTables("test", ["second.csv"], ["Q1"])
    df = reference_papers.get_reference_papers(tables, tables_dir=screening_tables)

    # p-a is only in the first table
    assert df["paperId"].tolist() == ["p-b"]
