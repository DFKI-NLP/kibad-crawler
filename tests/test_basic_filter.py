"""Test keyword filtering, saved search results, and SQLite search workflows."""

from dataclasses import replace
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from sifts.core import CollectionBase  # type: ignore

from kibad_crawler import basic_filter
from kibad_crawler.search_queries import Habitat, Query, Topic

RELEASE_ID = "2026-09-01"
PAPERS = [
    {
        "paperId": "paper-1",
        "title": "  FOREST diversity  ",
        "abstract": "  Species richness in Germany.  ",
        "citationCount": 12,
    },
    {
        "paperId": "paper-2",
        "title": "German woodland diversity",
        "abstract": None,
        "citationCount": 3,
    },
    {
        "paperId": "paper-3",
        "title": "Forest diversity in Canada",
        "abstract": "Species richness.",
        "citationCount": 7,
    },
    {
        "paperId": "paper-4",
        "title": "German agriculture",
        "abstract": "",
        "citationCount": 0,
    },
]


@pytest.fixture
def data_dirs(tmp_path: Path, monkeypatch):
    """Redirect raw and interim data to isolated temporary directories."""
    raw_dir = tmp_path / "raw"
    interim_dir = tmp_path / "interim"
    monkeypatch.setattr(basic_filter, "RAW_DATA_DIR", raw_dir)
    monkeypatch.setattr(basic_filter, "INTERIM_DATA_DIR", interim_dir)
    return raw_dir, interim_dir


@pytest.fixture
def paper_files(data_dirs):
    """Write metadata across multiple files, including a nested directory."""
    raw_dir, _ = data_dirs
    papers_dir = raw_dir / "semantic_scholar" / "release" / RELEASE_ID / "papers"
    nested_dir = papers_dir / "batch"
    nested_dir.mkdir(parents=True)
    (papers_dir / "first.json").write_text(json.dumps(PAPERS[:2]), encoding="utf-8")
    (nested_dir / "second.json").write_text(json.dumps(PAPERS[2:]), encoding="utf-8")
    (papers_dir / "ignored.txt").write_text("Not paper metadata", encoding="utf-8")
    return papers_dir


@pytest.fixture
def queries():
    """Provide two queries with distinct expected paper selections."""
    return [
        Query(
            "Q1",
            "German forests",
            '(forest OR woodland) AND ("German*" OR "central Europe")',
            Habitat.FOREST,
            Topic.TRENDS,
        ),
        Query(
            "Q2",
            "Canadian forests",
            '(forest OR woodland) AND (Canada OR "North America")',
            Habitat.FOREST,
            Topic.DRIVERS,
        ),
    ]


@pytest.mark.parametrize(
    "query, expected",
    [
        (
            '(forest OR woodland) AND ("species richness" OR "biodivers*")',
            [["forest", "woodland"], ["species richness", "biodivers*"]],
        ),
        (
            "(forest or woodland) and (Germany Or Austria)",
            [["forest", "woodland"], ["Germany", "Austria"]],
        ),
    ],
)
def test_get_processing_or_steps(query, expected):
    """Extract OR alternatives while preserving phrases and wildcard terms."""
    assert basic_filter.get_processing_or_steps(query) == expected


def test_get_papers_from_search(paper_files, queries):
    """Match each AND group across titles and abstracts, ignoring case."""
    assert sorted(basic_filter.get_papers_from_search(queries[0].query, paper_files)) == [
        "paper-1",
        "paper-2",
    ]
    assert basic_filter.get_papers_from_search(queries[1].query, paper_files) == ["paper-3"]


@pytest.mark.parametrize("with_papers", [True, False])
def test_get_papers_from_search_no_matches(paper_files, tmp_path, with_papers):
    """Return no IDs when papers do not match or the directory is empty."""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    assert (
        basic_filter.get_papers_from_search(
            "(ocean OR coast) AND (Germany OR Canada)",
            paper_files if with_papers else empty_dir,
        )
        == []
    )


@pytest.mark.parametrize("paper_ids", [["paper-1", "paper-3", "unknown"], []])
def test_save_selected_papers(paper_files, queries, tmp_path, paper_ids):
    """Save only selected records from every file, preserving all metadata."""
    output_dir = tmp_path / "selected"
    output_dir.mkdir()

    basic_filter.save_selected_papers(paper_ids, queries[0], RELEASE_ID, output_dir)

    output_file = output_dir / "Q1 - German forests.json"
    saved = json.loads(output_file.read_text(encoding="utf-8"))
    assert sorted(saved, key=lambda paper: paper["paperId"]) == [
        paper for paper in PAPERS if paper["paperId"] in paper_ids
    ]


@pytest.mark.parametrize("exists", [True, False])
def test_check_papers_exist(data_dirs, exists):
    """Report whether the requested release has a paper directory."""
    raw_dir, _ = data_dirs
    if exists:
        (raw_dir / "semantic_scholar" / "release" / RELEASE_ID / "papers").mkdir(parents=True)

    assert basic_filter._check_papers_exist(RELEASE_ID) is exists
    assert basic_filter._check_papers_exist("another-release") is False


def test_execute_all_search_queries(paper_files, data_dirs, queries, monkeypatch):
    """Create the output directory and save matching records for every query."""
    monkeypatch.setattr(basic_filter, "ALL_SEARCH_QUERIES", queries)

    basic_filter.execute_all_search_queries(RELEASE_ID)

    _, interim_dir = data_dirs
    output_dir = interim_dir / "semantic_scholar" / "release" / RELEASE_ID / "papers"
    output_dir /= "query_search"
    assert sorted(path.name for path in output_dir.iterdir()) == [
        "Q1 - German forests.json",
        "Q2 - Canadian forests.json",
    ]
    for query, expected in zip(queries, [PAPERS[:2], [PAPERS[2]]], strict=True):
        saved = json.loads((output_dir / f"{query.id} - {query.name}.json").read_text())
        assert sorted(saved, key=lambda paper: paper["paperId"]) == expected


def test_execute_search_query(paper_files, data_dirs, queries):
    """Execute a single query and save its full matching paper records."""
    basic_filter.execute_search_query(RELEASE_ID, queries[1])

    _, interim_dir = data_dirs
    output_dir = interim_dir / "semantic_scholar" / "release" / RELEASE_ID / "papers"
    output_dir /= "query_search"
    assert [path.name for path in output_dir.iterdir()] == ["Q2 - Canadian forests.json"]
    assert json.loads((output_dir / "Q2 - Canadian forests.json").read_text()) == [PAPERS[2]]


@pytest.mark.parametrize(
    "operation",
    [
        "execute_all_search_queries",
        "execute_search_query",
        "load_documents_to_database",
        "execute_all_search_queries_sift",
    ],
)
def test_missing_release(data_dirs, queries, monkeypatch, operation):
    """Skip searching, saving, and database creation when metadata is absent."""
    search = Mock()
    save = Mock()
    collection_factory = Mock()
    monkeypatch.setattr(basic_filter, "get_papers_from_search", search)
    monkeypatch.setattr(basic_filter, "save_selected_papers", save)
    monkeypatch.setattr(basic_filter.sifts, "Collection", collection_factory)
    kwargs = {"query": queries[0]} if operation == "execute_search_query" else {}

    assert getattr(basic_filter, operation)(RELEASE_ID, **kwargs) is None

    search.assert_not_called()
    save.assert_not_called()
    collection_factory.assert_not_called()
    assert not data_dirs[1].exists()


@pytest.mark.parametrize("existing_database", [True, False])
def test_load_documents_to_database(paper_files, data_dirs, existing_database):
    """Index trimmed titles and abstracts in a new or replaced SQLite database."""
    _, interim_dir = data_dirs
    database_path = interim_dir / "semantic_scholar" / "release" / RELEASE_ID / "papers"
    database_path /= "database/papers.db"
    if existing_database:
        database_path.parent.mkdir(parents=True)
        database_path.write_text("Old database must be replaced", encoding="utf-8")

    collection = basic_filter.load_documents_to_database(RELEASE_ID)

    assert collection is not None
    assert database_path.is_file()
    assert collection.count() == len(PAPERS)
    documents = {row["id"]: row["content"] for row in collection.query("")["results"]}
    assert documents == {
        "paper-1": "FOREST diversity Species richness in Germany.",
        "paper-2": "German woodland diversity ",
        "paper-3": "Forest diversity in Canada Species richness.",
        "paper-4": "German agriculture ",
    }


@pytest.mark.parametrize(
    "top_n, expected",
    [
        (None, ["best", "middle", "worst"]),
        (1, ["best"]),
        (2, ["best", "middle"]),
        (10, ["best", "middle", "worst"]),
    ],
)
def test_get_papers_from_search_with_sifts(queries, top_n, expected):
    """Sort matches by ascending rank before applying the requested limit."""
    collection = Mock(spec=CollectionBase)
    collection.query.return_value = {
        "results": [
            {"id": "worst", "rank": -0.1},
            {"id": "best", "rank": -5.0},
            {"id": "middle", "rank": -1.0},
        ],
        "total": 3,
    }
    collection.count.return_value = 4

    assert basic_filter.get_papers_from_search_with_sifts(queries[0], collection, top_n) == (
        expected
    )
    collection.query.assert_called_once_with(queries[0].query)


def test_execute_all_search_queries_sift(paper_files, data_dirs, queries, monkeypatch):
    """Load real SQLite data and save matching metadata for all configured queries."""
    queries = [
        replace(queries[0], query="woodland OR Germany"),
        replace(queries[1], query="Canada"),
    ]
    monkeypatch.setattr(basic_filter, "ALL_SEARCH_QUERIES", queries)

    basic_filter.execute_all_search_queries_sift(RELEASE_ID)

    _, interim_dir = data_dirs
    output_dir = interim_dir / "semantic_scholar" / "release" / RELEASE_ID / "papers" / "sifts"
    assert sorted(path.name for path in output_dir.iterdir()) == [
        "Q1 - German forests.json",
        "Q2 - Canadian forests.json",
    ]
    for query, expected in zip(queries, [PAPERS[:2], [PAPERS[2]]], strict=True):
        saved = json.loads((output_dir / f"{query.id} - {query.name}.json").read_text())
        assert sorted(saved, key=lambda paper: paper["paperId"]) == expected


def test_search_release_diff_uses_only_diff_metadata(paper_files, data_dirs, queries, monkeypatch):
    start_release = "2026-08-25"
    diff_path = Path("diffs") / f"{start_release}_to_{RELEASE_ID}" / "papers"
    diff_dir = paper_files.parent / diff_path
    diff_dir.mkdir(parents=True)
    changed_paper = {**PAPERS[0], "citationCount": 99}
    (diff_dir / "papers.json").write_text(json.dumps([changed_paper]), encoding="utf-8")
    monkeypatch.setattr(
        basic_filter,
        "ALL_SEARCH_QUERIES",
        [replace(queries[0], query="forest"), replace(queries[1], query="Canada")],
    )

    basic_filter.execute_all_search_queries_sift(RELEASE_ID, release_diff=start_release)

    _, interim_dir = data_dirs
    diff_output = interim_dir / "semantic_scholar" / "release" / RELEASE_ID / diff_path
    assert (diff_output / "database" / "papers.db").is_file()
    assert json.loads((diff_output / "sifts" / "Q1 - German forests.json").read_text()) == [
        changed_paper
    ]
    assert json.loads((diff_output / "sifts" / "Q2 - Canadian forests.json").read_text()) == []


def test_search_release_diff_with_missing_metadata(paper_files, data_dirs):
    basic_filter.execute_all_search_queries_sift(RELEASE_ID, release_diff="2026-08-25")

    _, interim_dir = data_dirs
    assert not interim_dir.exists()
