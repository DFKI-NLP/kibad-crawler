"""Test that the registered search queries match the documentation and can be run."""

from pathlib import Path
import re

import pytest
import sifts  # type: ignore

from kibad_crawler.basic_filter import get_processing_or_steps
from kibad_crawler.search_queries import ALL_SEARCH_QUERIES

SEARCH_QUERIES_DOC = Path(__file__).parents[1] / "docs" / "SEARCH_QUERIES.md"


@pytest.fixture(scope="module")
def collection(tmp_path_factory):
    """Small database to run the queries against."""
    db_path = tmp_path_factory.mktemp("sifts") / "papers.db"
    collection = sifts.Collection(db_url=f"sqlite:///{db_path}", name="papers")
    collection.add(
        ["Species richness of soil fauna in German forests", "Carbon storage in grassland"],
        ["paper-1", "paper-2"],
    )
    return collection


def test_query_ids_are_unique():
    ids = [query.id for query in ALL_SEARCH_QUERIES]

    assert len(ids) == len(set(ids))


def test_query_names_match_the_documentation():
    # rows of the table in docs/SEARCH_QUERIES.md look like `| Q5  | Soil - Trends | ...`
    documented = dict(
        re.findall(r"^\| (Q\d+)\s+\| (.+?)\s+\|", SEARCH_QUERIES_DOC.read_text(), re.M)
    )

    assert len(documented) == 26
    assert {query.id: query.name for query in ALL_SEARCH_QUERIES} == {
        query_id: documented[query_id] for query_id in (q.id for q in ALL_SEARCH_QUERIES)
    }


@pytest.mark.parametrize("query", ALL_SEARCH_QUERIES, ids=lambda query: query.id)
def test_query_can_be_run(query, collection):
    # the plain text search and the sifts search must both accept the query
    assert get_processing_or_steps(query.query)
    assert collection.query(query.query)["total"] >= 0
