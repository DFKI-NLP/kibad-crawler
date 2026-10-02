"""Run the search queries on the papers of the screening tables.

The papers of the screening tables are resolved to Semantic Scholar ids by
`map_dois.py`. This script downloads their title and abstract from the Academic
Graph API, loads them into a `sifts` database and runs the search queries on
them. It reports per query how many of the screened papers are found.

Unlike `compare_search_with_screening.py` this does not depend on the papers
that the crawler downloaded, so it is not limited by the publication venues or
the publication dates of a release. It measures the queries, not the pipeline.
See https://github.com/DFKI-NLP/kibad-crawler/issues/42.
"""

import os
import time

from loguru import logger
import pandas as pd
import sifts  # type: ignore
from sifts.core import CollectionBase  # type: ignore
from tqdm import tqdm

from kibad_crawler.basic_filter import get_papers_from_search_with_sifts
from kibad_crawler.config import INTERIM_DATA_DIR
from kibad_crawler.search_queries import ALL_SEARCH_QUERIES
from kibad_crawler.semantic_scholar import academic_graph
from kibad_crawler.utils import chunker

BASE_DIR = "/netscratch/asafari/kibad-crawler/data/external/40_evaluation"
DOIS_FILE = os.path.join(BASE_DIR, "wald_dois_s2.csv")
METADATA_FILE = os.path.join(BASE_DIR, "screening_papers_metadata.json")
DATABASE_DIR = INTERIM_DATA_DIR / "semantic_scholar" / "screening_tables" / "database"
FIELDS = "paperId,title,abstract"
TOP_N = [100, 500, 1000, 2000]
DELAY_BETWEEN_BATCHES = 3


def get_reference_papers() -> pd.DataFrame:
    """Return the papers of the screening tables with their Semantic Scholar id.

    Returns:
        pd.DataFrame: One row per paper id with the screening decision of the
            `included` column and the table the paper comes from.
    """
    df = pd.read_csv(DOIS_FILE)
    df = df[df["paperId"].notna()]
    # a paper can be in more than one table, the tables with a decision come first
    df = df.sort_values("included").drop_duplicates(subset=["paperId"], keep="first")
    logger.info(f"{df.shape[0]:,} papers with a Semantic Scholar id")
    logger.info(f"screening decisions: {df['included'].value_counts(dropna=False).to_dict()}")
    return df


def download_metadata(paper_ids: list) -> pd.DataFrame:
    """Download title and abstract of the given papers, reusing a local copy.

    Args:
        paper_ids (list): Semantic Scholar paper ids.

    Returns:
        pd.DataFrame: Metadata of the papers that the API returned.
    """
    if os.path.exists(METADATA_FILE):
        df = pd.read_json(METADATA_FILE)
        logger.info(f"{df.shape[0]:,} papers read from '{METADATA_FILE}'")
        return df

    papers = []
    for i, group in enumerate(chunker(paper_ids, 500)):
        papers += [paper for paper in academic_graph.batch(group, fields=FIELDS) if paper]
        logger.info(f"batch {i}: {len(papers):,} of {len(paper_ids):,} papers downloaded")
        time.sleep(DELAY_BETWEEN_BATCHES)

    df = pd.DataFrame(papers)
    df.to_json(METADATA_FILE, orient="records")
    logger.info(f"{df.shape[0]:,} papers saved to '{METADATA_FILE}'")
    return df


def load_documents_to_database(df_papers: pd.DataFrame) -> CollectionBase:
    """Load title and abstract of the papers into an sqlite database.

    Args:
        df_papers (pd.DataFrame): Metadata of the papers with `paperId`,
            `title` and `abstract`.

    Returns:
        CollectionBase: Database with the papers loaded.
    """
    DATABASE_DIR.mkdir(parents=True, exist_ok=True)
    database_path = DATABASE_DIR / "papers.db"
    if database_path.exists():
        database_path.unlink()

    collection = sifts.Collection(db_url=f"sqlite:///{database_path}", name="papers")
    for _, r in tqdm(df_papers.iterrows(), total=df_papers.shape[0], desc="Loading papers"):
        title = r["title"] or ""
        abstract = r["abstract"] or ""
        collection.add(contents=[f"{title.strip()} {abstract.strip()}"], ids=[r["paperId"]])

    logger.info(f"{collection.count():,} papers loaded to '{database_path}'")
    return collection


def report_query(query_name: str, ranked_paper_ids: list, df_reference: pd.DataFrame):
    """Print how many of the screened papers a query result contains.

    Args:
        query_name (str): Name of the query.
        ranked_paper_ids (list): Paper ids of the result, best match first.
        df_reference (pd.DataFrame): Papers of the screening tables.
    """
    included = dict(zip(df_reference["paperId"], df_reference["included"]))
    n_relevant = sum(1 for value in included.values() if value == 1)
    n_not_relevant = sum(1 for value in included.values() if value == 0)

    relevant = [paper_id for paper_id in ranked_paper_ids if included.get(paper_id) == 1]
    not_relevant = [paper_id for paper_id in ranked_paper_ids if included.get(paper_id) == 0]
    not_screened = len(ranked_paper_ids) - len(relevant) - len(not_relevant)

    print("=" * 70)
    print(f"{query_name}: {len(ranked_paper_ids):,} of {df_reference.shape[0]:,} papers returned")
    print(f"  screened as relevant: {len(relevant):,} of {n_relevant:,}")
    print(f"  screened as not relevant: {len(not_relevant):,} of {n_not_relevant:,}")
    print(f"  not screened: {not_screened:,}")
    for n in TOP_N:
        top = ranked_paper_ids[:n]
        top_relevant = [paper_id for paper_id in top if included.get(paper_id) == 1]
        print(f"  screened as relevant in the top {n:,}: {len(top_relevant):,}")


def main():
    df_reference = get_reference_papers()
    df_papers = download_metadata(sorted(df_reference["paperId"]))

    # the API does not return every paper, only the papers in the database can be found
    df_reference = df_reference[df_reference["paperId"].isin(set(df_papers["paperId"]))]
    logger.info(f"{df_reference.shape[0]:,} papers are in the database")

    collection = load_documents_to_database(df_papers)
    for query in ALL_SEARCH_QUERIES:
        paper_ids = get_papers_from_search_with_sifts(query=query, collection=collection)
        report_query(query_name=query.name, ranked_paper_ids=paper_ids, df_reference=df_reference)


if __name__ == "__main__":
    main()
