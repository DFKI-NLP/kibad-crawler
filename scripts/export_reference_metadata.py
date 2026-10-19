"""Export the publication venue and the open access info of the reference papers.

Writes one CSV with the papers of the Forest screening tables, their
publication venue and their open access fields, and a column per crawl that
says whether the crawl holds the paper, for the statistics of
https://github.com/DFKI-NLP/kibad-crawler/issues/46.

The metadata comes from the batch endpoint, 12 requests for the 5,873 papers,
which is much faster than reading the JSON files of a crawl from `/netscratch`.
Whether a crawl holds a paper is read from its CSV files.

Call it with the folders under `data/raw/semantic_scholar/release/` to flag:

    uv run python scripts/export_reference_metadata.py 2024-12-31_journals_csv 2024-12-31
"""

import os
import sys
import time

from loguru import logger
import pandas as pd
from tqdm import tqdm

from kibad_crawler.config import RAW_DATA_DIR
from kibad_crawler.semantic_scholar import academic_graph
from kibad_crawler.utils import chunker

BASE_DIR = "/netscratch/asafari/kibad-crawler/data/external/40_evaluation"
DOIS_FILE = os.path.join(BASE_DIR, "wald_dois_s2.csv")
OUTPUT_FILE = os.path.join(BASE_DIR, "reference_papers_venue_and_open_access.csv")
FIELDS = (
    "paperId,title,year,publicationDate,venue,publicationVenue,"
    "isOpenAccess,openAccessPdf,publicationTypes"
)
DELAY_BETWEEN_BATCHES = 3


def get_reference_papers() -> pd.DataFrame:
    """Return the reference papers with their screening decision.

    Returns:
        pd.DataFrame: One row per paper id of the screening tables.
    """
    df = pd.read_csv(DOIS_FILE)
    df = df[df["paperId"].notna()]
    # same as in the other scripts: a decision wins over no decision
    df = df.sort_values("included").drop_duplicates(subset=["paperId"], keep="first")
    logger.info(f"{df.shape[0]:,} reference papers with a Semantic Scholar id")
    return df[["paperId", "doi", "included", "source_file"]]


def get_metadata(paper_ids: list[str]) -> pd.DataFrame:
    """Query the Academic Graph API for the venue and open access fields.

    Args:
        paper_ids (list[str]): Semantic Scholar ids of the papers.

    Returns:
        pd.DataFrame: One row per paper the API returned.
    """
    records = []
    for i, group in enumerate(chunker(paper_ids, 500)):
        papers = academic_graph.batch(group, fields=FIELDS)
        for paper in papers:
            if paper is None:
                continue
            venue = paper.get("publicationVenue") or {}
            open_access = paper.get("openAccessPdf") or {}
            records.append(
                {
                    "paperId": paper.get("paperId"),
                    "title": paper.get("title"),
                    "year": paper.get("year"),
                    "publication_date": paper.get("publicationDate"),
                    "venue": paper.get("venue"),
                    "publication_venue_id": venue.get("id"),
                    "publication_venue_name": venue.get("name"),
                    "publication_venue_type": venue.get("type"),
                    "publication_venue_issn": venue.get("issn"),
                    "publication_venue_url": venue.get("url"),
                    "publication_venue_alternate_urls": "; ".join(
                        venue.get("alternate_urls") or []
                    ),
                    "is_open_access": paper.get("isOpenAccess"),
                    "open_access_status": open_access.get("status"),
                    "open_access_license": open_access.get("license"),
                    "open_access_url": open_access.get("url"),
                    "publication_types": "; ".join(paper.get("publicationTypes") or []),
                }
            )
        logger.info(f"batch {i}: {len(records):,} of {len(paper_ids):,} papers")
        time.sleep(DELAY_BETWEEN_BATCHES)
    return pd.DataFrame(records)


def get_crawled_paper_ids(folder: str) -> set[str]:
    """Return the paper ids of a crawl, read from its CSV files.

    Args:
        folder (str): Folder under `release/` that holds the crawl.

    Returns:
        set[str]: Paper ids of the crawl.
    """
    papers_path = RAW_DATA_DIR / "semantic_scholar" / "release" / folder / "papers"
    csv_files = sorted(papers_path.glob("*.gz.csv"))
    logger.info(f"{len(csv_files)} CSV files in '{papers_path}'")

    paper_ids: set[str] = set()
    for csv_path in tqdm(csv_files, desc=f"Reading {folder}"):
        df = pd.read_csv(csv_path, usecols=["url"], dtype=str)
        paper_ids.update(df["url"].str.split("/").str[-1])
    logger.info(f"{len(paper_ids):,} papers in '{folder}'")
    return paper_ids


def main():
    folders = sys.argv[1:]

    df_reference = get_reference_papers()
    df = df_reference.merge(
        get_metadata(df_reference["paperId"].tolist()), on="paperId", how="left"
    )

    for folder in folders:
        crawled = get_crawled_paper_ids(folder)
        df[f"in_{folder}"] = df["paperId"].isin(crawled)

    df.to_csv(OUTPUT_FILE, index=False)

    print("=" * 70)
    print(f"{df.shape[0]:,} reference papers saved to '{OUTPUT_FILE}'")
    print(f"  with a publication venue id: {df['publication_venue_id'].notna().sum():,}")
    print(f"  open access: {df['is_open_access'].eq(True).sum():,}")
    print(f"  open access status: {df['open_access_status'].value_counts(dropna=False).to_dict()}")
    for folder in folders:
        in_crawl = df[f"in_{folder}"]
        print(
            f"  in '{folder}': {in_crawl.sum():,} papers, "
            f"{df.loc[in_crawl, 'is_open_access'].eq(True).sum():,} of them open access, "
            f"{df.loc[in_crawl, 'included'].eq(1).sum():,} screened as relevant"
        )


if __name__ == "__main__":
    main()
