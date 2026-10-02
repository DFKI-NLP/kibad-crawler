"""Helpers for the evaluation of the keyword searches.

Loading papers into a `sifts` database writes one row at a time, which is slow
on the shared filesystem of the cluster: 5,873 papers took 19 minutes on
`/netscratch`, while #27 reports about 80 papers per second locally. The
database is therefore built on the local disk of the compute node.

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


def build_collection(documents: list, name: str) -> CollectionBase:
    """Load documents into a new `sifts` database.

    Args:
        documents (list): Tuples of paper id and the text to index.
        name (str): Name of the database, see `get_database_path`.

    Returns:
        CollectionBase: Database with the documents loaded.
    """
    database_path = get_database_path(name)
    if database_path.exists():
        database_path.unlink()

    collection = sifts.Collection(db_url=f"sqlite:///{database_path}", name="papers")
    for paper_id, text in tqdm(documents, desc="Loading papers"):
        collection.add(contents=[text], ids=[paper_id])

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
