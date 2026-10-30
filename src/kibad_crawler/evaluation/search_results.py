"""Compare the results of the search queries on a crawl with the screening
tables of the literature review.

The reference papers are restricted to the publication venues that the crawl
was filtered on, so that both sides use the same venues. Reports per habitat
how many of those reference papers are in the crawl, and per query how many of
them the query returns and how they were screened. See
https://github.com/DFKI-NLP/kibad-crawler/issues/47 and
https://github.com/DFKI-NLP/kibad-crawler/issues/51.
"""

import json
import os
from pathlib import Path
import tempfile

from loguru import logger
import pandas as pd
import sifts  # type: ignore
from sifts.core import CollectionBase  # type: ignore
from tqdm import tqdm

from kibad_crawler.basic_filter import get_papers_from_search_with_sifts
from kibad_crawler.search_queries import Query

TOP_N = [100, 500, 1000, 5000]


def get_documents_of_crawl(
    papers_path: Path, max_publication_date: str | None = None
) -> list[tuple[str, str]]:
    """Return the papers of a crawl with the text to index.

    Args:
        papers_path (Path): `papers` folder of the crawl with the JSON files
            of the abstracts.
        max_publication_date (str | None, optional): Keep only the papers
            published up to this date, with format 'YYYY-MM-DD'. Papers without
            a publication date are kept. Defaults to None.

    Returns:
        list[tuple[str, str]]: Paper id with the title and abstract.
    """
    documents = []
    missing = 0
    after_cut_date = 0
    for json_file in papers_path.glob("**/json/*.json"):
        with open(json_file, encoding="utf-8") as f:
            papers = json.load(f)
        for paper in papers:
            # the API returns null for the papers it does not know
            if paper is None or not paper.get("paperId"):
                missing += 1
                continue
            publication_date = paper.get("publicationDate")
            if (
                max_publication_date
                and publication_date
                and publication_date > max_publication_date
            ):
                after_cut_date += 1
                continue
            title = paper.get("title") or ""
            abstract = paper.get("abstract") or ""
            documents.append((paper["paperId"], f"{title.strip()} {abstract.strip()}"))
    logger.info(f"{len(documents):,} papers in '{papers_path}' to index")
    logger.info(f"{missing:,} entries without metadata from the API")
    if max_publication_date:
        logger.info(f"{after_cut_date:,} papers published after {max_publication_date} left out")
    return documents


def build_collection(
    documents: list[tuple[str, str]], name: str, batch_size: int = 500
) -> CollectionBase:
    """Load documents into a new `sifts` database, `batch_size` per call.

    Adding one paper per call gets slower as the database grows, 4.9 papers per
    second at 200,000 papers, while 500 per call loads 10,000 to 22,000 per
    second. The database is written to the local disk of the compute node,
    which is faster than `/netscratch` for many small writes.

    Args:
        documents (list[tuple[str, str]]): Paper id with the text to index.
        name (str): Name of the database, to separate different evaluations.
        batch_size (int, optional): Papers per `add` call. Defaults to 500.

    Returns:
        CollectionBase: Database with the papers loaded.
    """
    base_dir = os.environ.get("SLURM_TMPDIR") or tempfile.gettempdir()
    database_path = Path(base_dir) / "kibad_crawler_sifts" / name / "papers.db"
    database_path.parent.mkdir(parents=True, exist_ok=True)
    database_path.unlink(missing_ok=True)

    collection = sifts.Collection(db_url=f"sqlite:///{database_path}", name="papers")
    loaded_ids: set[str] = set()
    ids: list[str] = []
    contents: list[str] = []
    for paper_id, text in tqdm(documents, desc="Loading papers"):
        # a paper id can only be added once, some papers are in two files
        if paper_id in loaded_ids:
            continue
        loaded_ids.add(paper_id)
        ids.append(paper_id)
        contents.append(text)
        if len(ids) == batch_size:
            collection.add(contents=contents, ids=ids)
            ids, contents = [], []
    if ids:
        collection.add(contents=contents, ids=ids)

    logger.info(f"{collection.count():,} papers loaded to '{database_path}'")
    return collection


def get_coverage(
    df_reference: pd.DataFrame, crawled_ids: set[str], venue_ids: set[str]
) -> pd.DataFrame:
    """Count how many reference papers are in the crawl, for all of them and for
    the ones of the publication venues the crawl was filtered on.

    Args:
        df_reference (pd.DataFrame): Reference papers with the screening
            decision and the publication venue id.
        crawled_ids (set[str]): Paper ids of the crawl.
        venue_ids (set[str]): Publication venue ids the crawl was filtered on.

    Returns:
        pd.DataFrame: One row per set of reference papers.
    """
    in_venues = df_reference["publication_venue_id"].isin(venue_ids)
    rows = []
    for label, df in [
        ("all reference papers", df_reference),
        ("in the publication venues", df_reference[in_venues]),
    ]:
        in_crawl = df["paperId"].isin(crawled_ids)
        relevant = df["included"] == 1
        rows.append(
            {
                "reference papers": label,
                "papers": df.shape[0],
                "in the crawl": in_crawl.sum(),
                "relevant": relevant.sum(),
                "relevant in the crawl": (in_crawl & relevant).sum(),
            }
        )
    return pd.DataFrame(rows)


def get_query_results(results: dict[str, list[str]], df_reference: pd.DataFrame) -> pd.DataFrame:
    """Count per query how many reference papers it returns and how they were
    screened.

    Args:
        results (dict[str, list[str]]): Paper ids returned per query name,
            best match first.
        df_reference (pd.DataFrame): Reference papers that are in the crawl.

    Returns:
        pd.DataFrame: One row per query and one for all queries together.
    """
    included = dict(zip(df_reference["paperId"], df_reference["included"]))
    rows = []
    for name, paper_ids in results.items():
        hits = [paper_id for paper_id in paper_ids if paper_id in included]
        row = {
            "query": name,
            "returned": len(paper_ids),
            "reference papers": len(hits),
            "relevant": sum(1 for paper_id in hits if included[paper_id] == 1),
            "not relevant": sum(1 for paper_id in hits if included[paper_id] == 0),
        }
        for n in TOP_N:
            row[f"top {n}"] = sum(1 for paper_id in paper_ids[:n] if paper_id in included)
        rows.append(row)

    returned = set().union(*results.values())
    hits_of_all = [paper_id for paper_id in returned if paper_id in included]
    rows.append(
        {
            "query": "all queries",
            "returned": len(returned),
            "reference papers": len(hits_of_all),
            "relevant": sum(1 for paper_id in hits_of_all if included[paper_id] == 1),
            "not relevant": sum(1 for paper_id in hits_of_all if included[paper_id] == 0),
        }
    )
    return pd.DataFrame(rows)


def evaluate_queries(
    queries: list[Query],
    collection: CollectionBase,
    crawled_ids: set[str],
    df_reference: pd.DataFrame,
    venue_ids: set[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run the queries of a habitat on the crawl and compare the results with
    its reference papers of the same publication venues.

    Args:
        queries (list[Query]): Queries of the habitat.
        collection (CollectionBase): Database with the papers of the crawl.
        crawled_ids (set[str]): Paper ids of the crawl.
        df_reference (pd.DataFrame): Reference papers of the habitat.
        venue_ids (set[str]): Publication venue ids the crawl was filtered on.

    Returns:
        tuple[pd.DataFrame, pd.DataFrame]: Coverage of the reference papers
            and the results per query.
    """
    df_coverage = get_coverage(df_reference, crawled_ids, venue_ids)

    # a query only returns papers of the crawl, so restricting to the venues is enough
    df_reference = df_reference[df_reference["publication_venue_id"].isin(venue_ids)]
    results = {
        query.name: get_papers_from_search_with_sifts(query=query, collection=collection)
        for query in queries
    }
    return df_coverage, get_query_results(results, df_reference)
