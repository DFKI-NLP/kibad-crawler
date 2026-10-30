"""Test that the registered search queries match the documentation and can be run."""

from pathlib import Path
import re

import pytest
import sifts  # type: ignore

from kibad_crawler.basic_filter import get_processing_or_steps
from kibad_crawler.search_queries import (
    ALL_SEARCH_QUERIES,
    DRIVERS,
    HABITATS_AGRICULTURAL,
    HABITATS_COASTS,
    HABITATS_URBAN,
    HABITATS_WATER,
    METRICS,
    Habitat,
    Topic,
)

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
    assert {query.id: query.name for query in ALL_SEARCH_QUERIES} == documented


def test_habitat_queries_use_the_terms_of_their_habitat_and_topic():
    habitat_words = {
        Habitat.AGRI: HABITATS_AGRICULTURAL,
        Habitat.INLAND_WATER: HABITATS_WATER,
        Habitat.COAST: HABITATS_COASTS,
        Habitat.URBAN: HABITATS_URBAN,
    }
    topic_terms = {Topic.DRIVERS: DRIVERS, Topic.MEASURES: METRICS}

    queries = [query for query in ALL_SEARCH_QUERIES if query.habitat in habitat_words]

    assert len(queries) == 16
    for query in queries:
        assert habitat_words[query.habitat] in query.query
        if query.topic in topic_terms:
            assert topic_terms[query.topic] in query.query
        # no query contains the words of another habitat
        others = [words for habitat, words in habitat_words.items() if habitat != query.habitat]
        assert not any(words in query.query for words in others)


def test_endangered_species_extend_only_the_agricultural_trends():
    queries = {query.id: query.query for query in ALL_SEARCH_QUERIES}

    # Q9 is Agricultural and Open Land - Trends, Q13 is Inland waters & Floodplains - Trends
    assert '("endangered species" OR "extinct species" OR "trend*"' in queries["Q9"]
    assert '"endangered species" OR "extinct species" OR "trend*"' not in queries["Q13"]


@pytest.mark.parametrize("query", ALL_SEARCH_QUERIES, ids=lambda query: query.id)
def test_query_can_be_run(query, collection):
    # the plain text search and the sifts search must both accept the query
    assert get_processing_or_steps(query.query)
    assert collection.query(query.query)["total"] >= 0
