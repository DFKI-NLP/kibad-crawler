"""Compare the keyword searches with the screening tables of the literature review.

Takes the papers that the crawler downloaded for a release, runs the search
queries with `sifts` and compares the results with the papers of the screening
tables, which are identified by the DOIs resolved in `map_dois.py`.

Reports per query how many of the reference papers are found, how the found
papers were screened (`included`) and how the recall develops over the ranking
of `sifts`. See https://github.com/DFKI-NLP/kibad-crawler/issues/42.
"""

import os
import sys

from loguru import logger
import pandas as pd

from kibad_crawler.basic_filter import (
    get_papers_from_search_with_sifts,
    load_documents_to_database,
)
from kibad_crawler.config import RAW_DATA_DIR
from kibad_crawler.search_queries import ALL_SEARCH_QUERIES

BASE_DIR = "/netscratch/asafari/kibad-crawler/data/external/40_evaluation"
DOIS_FILE = os.path.join(BASE_DIR, "wald_dois_s2.csv")
TOP_N = [100, 500, 1000, 5000]


def get_paper_ids_of_release(release_id: str) -> set:
    """Return the ids of the papers that the crawler downloaded for a release.

    Args:
        release_id (str): Release version from Semantic Scholar with format
            'YYYY-MM-DD'.

    Returns:
        set: Semantic Scholar paper ids of the downloaded papers.
    """
    files_path = RAW_DATA_DIR / "semantic_scholar" / "release" / release_id / "papers"
    paper_ids = set()
    for json_file in files_path.glob("**/json/*.json"):
        df = pd.read_json(json_file)
        if "paperId" in df.columns:
            paper_ids.update(df["paperId"].dropna().to_list())
    logger.info(f"{len(paper_ids):,} papers downloaded for release '{release_id}'")
    return paper_ids


def get_reference_papers() -> pd.DataFrame:
    """Return the papers of the screening tables with their Semantic Scholar id.

    Returns:
        pd.DataFrame: One row per paper id with the screening decision.
    """
    df = pd.read_csv(DOIS_FILE)
    df = df[df["paperId"].notna()]
    # the two halves of the Forest search contain each paper once, the decision
    # of a paper is the same in all tables it appears in
    df = df.sort_values("included").drop_duplicates(subset=["paperId"], keep="first")
    logger.info(f"{df.shape[0]:,} reference papers with a Semantic Scholar id")
    logger.info(f"screening decisions: {df['included'].value_counts(dropna=False).to_dict()}")
    return df


def report_query(query_name: str, ranked_paper_ids: list, df_reference: pd.DataFrame):
    """Print how many reference papers a query result contains.

    Args:
        query_name (str): Name of the query.
        ranked_paper_ids (list): Paper ids of the result, best match first.
        df_reference (pd.DataFrame): Reference papers that the crawler downloaded.
    """
    reference_ids = set(df_reference["paperId"])
    included = dict(zip(df_reference["paperId"], df_reference["included"]))

    hits = [paper_id for paper_id in ranked_paper_ids if paper_id in reference_ids]
    relevant = [paper_id for paper_id in hits if included.get(paper_id) == 1]
    not_relevant = [paper_id for paper_id in hits if included.get(paper_id) == 0]

    print("=" * 70)
    print(f"{query_name}: {len(ranked_paper_ids):,} papers returned")
    print(f"  reference papers found: {len(hits):,} of {len(reference_ids):,}")
    print(f"  of those screened as relevant: {len(relevant):,}")
    print(f"  of those screened as not relevant: {len(not_relevant):,}")
    print(f"  of those not screened: {len(hits) - len(relevant) - len(not_relevant):,}")
    for n in TOP_N:
        top_hits = [paper_id for paper_id in ranked_paper_ids[:n] if paper_id in reference_ids]
        print(f"  reference papers in the top {n:,}: {len(top_hits):,}")


def main():
    release_id = sys.argv[1] if len(sys.argv) > 1 else "2024-12-31"

    paper_ids_of_release = get_paper_ids_of_release(release_id)
    df_reference = get_reference_papers()

    # only the reference papers that the crawler downloaded can be found by a query
    df_reference = df_reference[df_reference["paperId"].isin(paper_ids_of_release)]
    logger.info(f"{df_reference.shape[0]:,} reference papers are in the downloaded papers")
    if df_reference.empty:
        logger.info("no reference paper was downloaded, nothing to compare")
        return

    collection = load_documents_to_database(release_id=release_id)
    if collection is None:
        logger.info(f"no papers found for release '{release_id}'")
        return

    for query in ALL_SEARCH_QUERIES:
        paper_ids = get_papers_from_search_with_sifts(query=query, collection=collection)
        report_query(query_name=query.name, ranked_paper_ids=paper_ids, df_reference=df_reference)


if __name__ == "__main__":
    main()
