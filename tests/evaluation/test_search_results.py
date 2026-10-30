"""Test the comparison of the search queries with the screening tables."""

import json
from pathlib import Path

import pandas as pd
import pytest

from kibad_crawler.evaluation import search_results
from kibad_crawler.search_queries import Habitat, Query, Topic

PAPERS = [
    {"paperId": "p-1", "title": "Forest", "abstract": "trend", "publicationDate": "2020-01-01"},
    {"paperId": "p-2", "title": "Forest", "abstract": None, "publicationDate": None},
    {"paperId": "p-3", "title": "Forest", "abstract": "trend", "publicationDate": "2020-05-01"},
    {"paperId": "p-4", "title": "Forest", "abstract": "trend", "publicationDate": "2023-01-01"},
]
REFERENCE = pd.DataFrame(
    {
        "paperId": ["p-1", "p-2", "p-3", "p-9"],
        "included": [1, 0, 1, 1],
        "publication_venue_id": ["v-1", "v-1", None, "v-1"],
    }
)
QUERIES = [
    Query("Q1", "Forest - Trends", "Forest AND trend", Habitat.FOREST, Topic.TRENDS),
    Query("Q2", "Forest - All", "Forest", Habitat.FOREST, Topic.MEASURES),
]


@pytest.fixture
def papers_path(tmp_path: Path) -> Path:
    """Write the papers like the crawler does, with a null entry for a paper
    the API did not know."""
    json_dir = tmp_path / "papers" / "file-1" / "json"
    json_dir.mkdir(parents=True)
    (json_dir / "papers-metadata-0.json").write_text(json.dumps(PAPERS[:2] + [None]))
    (json_dir / "papers-metadata-1.json").write_text(json.dumps(PAPERS[2:]))
    return tmp_path / "papers"


@pytest.mark.parametrize(
    "max_publication_date, expected",
    [(None, ["p-1", "p-2", "p-3", "p-4"]), ("2022-12-31", ["p-1", "p-2", "p-3"])],
)
def test_get_documents_of_crawl(papers_path, max_publication_date, expected):
    documents = search_results.get_documents_of_crawl(papers_path, max_publication_date)

    assert sorted(paper_id for paper_id, _ in documents) == expected
    assert ("p-2", "Forest ") in documents


def test_build_collection(tmp_path, monkeypatch):
    monkeypatch.setenv("SLURM_TMPDIR", str(tmp_path))
    documents = [("p-1", "a"), ("p-2", "b"), ("p-1", "a"), ("p-3", "c")]

    collection = search_results.build_collection(documents, name="test", batch_size=2)

    assert collection.count() == 3
    assert (tmp_path / "kibad_crawler_sifts" / "test" / "papers.db").exists()


def test_get_coverage():
    df = search_results.get_coverage(REFERENCE, crawled_ids={"p-1", "p-2", "p-3"}, venue_ids={"v-1"})

    assert df.to_dict("records") == [
        {
            "reference papers": "all reference papers",
            "papers": 4,
            "in the crawl": 3,
            "relevant": 3,
            "relevant in the crawl": 2,
        },
        {
            "reference papers": "in the publication venues",
            "papers": 3,
            "in the crawl": 2,
            "relevant": 2,
            "relevant in the crawl": 1,
        },
    ]


def test_get_query_results():
    results = {"Q1": ["p-1", "p-5"], "Q2": ["p-2", "p-1", "p-6"]}

    df = search_results.get_query_results(results, REFERENCE[REFERENCE["paperId"] != "p-9"])

    assert df[["query", "returned", "reference papers", "relevant", "not relevant"]].values.tolist() == [
        ["Q1", 2, 1, 1, 0],
        ["Q2", 3, 2, 1, 1],
        ["all queries", 4, 2, 1, 1],
    ]
    assert df.loc[1, "top 100"] == 2


def test_evaluate_queries(papers_path, tmp_path, monkeypatch):
    monkeypatch.setenv("SLURM_TMPDIR", str(tmp_path))
    documents = search_results.get_documents_of_crawl(papers_path, "2022-12-31")
    collection = search_results.build_collection(documents, name="evaluate")

    df_coverage, df_queries = search_results.evaluate_queries(
        QUERIES,
        collection,
        crawled_ids={paper_id for paper_id, _ in documents},
        df_reference=REFERENCE,
        venue_ids={"v-1"},
    )

    # p-3 is returned but has no venue and p-9 is not in the crawl, so only
    # p-1 and p-2 count
    assert df_coverage["in the crawl"].tolist() == [3, 2]
    assert df_queries[["query", "returned", "reference papers", "relevant"]].values.tolist() == [
        ["Forest - Trends", 2, 1, 1],
        ["Forest - All", 3, 2, 1],
        ["all queries", 3, 2, 1],
    ]
