"""Helpers for the evaluation of the keyword searches.

Loading papers into a `sifts` database is slow when `add` is called once per
paper, and it gets slower as the database grows: locally 122 documents per
second at 5,000 documents and 64 at 20,000, and 4.9 per second at 200,000 on
the cluster. Adding 500 documents per call gives 10,000 to 22,000 per second.
The database is also built on the local disk of the compute node, which is
faster than `/netscratch` for many small writes.

See https://github.com/DFKI-NLP/kibad-crawler/issues/42.
"""

import os
from pathlib import Path
import tempfile

from loguru import logger
import sifts  # type: ignore
from sifts.core import CollectionBase  # type: ignore
from tqdm import tqdm


def get_database_path(name: str) -> Path:
    """Return the path of a database on the local disk of the compute node.

    Args:
        name (str): Name to separate the databases of different evaluations.

    Returns:
        Path: Path of the database file.
    """
    base_dir = os.environ.get("SLURM_TMPDIR") or tempfile.gettempdir()
    database_dir = Path(base_dir) / "kibad_crawler_sifts" / name
    database_dir.mkdir(parents=True, exist_ok=True)
    return database_dir / "papers.db"


def build_collection(documents: list, name: str, batch_size: int = 500) -> CollectionBase:
    """Load documents into a new `sifts` database, `batch_size` per call.

    Args:
        documents (list): Tuples of paper id and the text to index.
        name (str): Name of the database, see `get_database_path`.
        batch_size (int, optional): Documents per `add` call. Defaults to 500.

    Returns:
        CollectionBase: Database with the documents loaded.
    """
    database_path = get_database_path(name)
    if database_path.exists():
        database_path.unlink()

    collection = sifts.Collection(db_url=f"sqlite:///{database_path}", name="papers")
    loaded_ids: set = set()
    ids: list = []
    contents: list = []
    duplicates = 0

    for paper_id, text in tqdm(documents, desc="Loading papers"):
        # a paper id can only be added once
        if paper_id in loaded_ids:
            duplicates += 1
            continue
        loaded_ids.add(paper_id)
        ids.append(paper_id)
        contents.append(text)
        if len(ids) == batch_size:
            collection.add(contents=contents, ids=ids)
            ids, contents = [], []
    if ids:
        collection.add(contents=contents, ids=ids)

    if duplicates:
        logger.info(f"{duplicates:,} papers skipped because their id was added before")
    logger.info(f"{collection.count():,} papers loaded to '{database_path}'")
    return collection


def report_overlap(results: dict, relevant_ids: set):
    """Print how much the results of the queries have in common.

    Args:
        results (dict): Paper ids returned per query name.
        relevant_ids (set): Paper ids that were screened as relevant.
    """
    print("=" * 70)
    print("overlap of the queries")
    names = list(results)
    for i, name in enumerate(names):
        for other in names[i + 1 :]:
            papers, other_papers = set(results[name]), set(results[other])
            union = len(papers | other_papers)
            shared = len(papers & other_papers)
            print(f"  {name} and {other}: {shared:,} shared of {union:,} ({shared / union:.0%})")

    union_of_queries = set().union(*[set(ids) for ids in results.values()])
    found_relevant = union_of_queries & relevant_ids
    print(f"  all queries together: {len(union_of_queries):,} papers")
    print(f"  screened as relevant in at least one result: {len(found_relevant):,}")
    print(f"  of {len(relevant_ids):,} papers screened as relevant")
