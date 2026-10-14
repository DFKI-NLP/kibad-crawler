"""Get the publication venue of the papers of the Forest screening tables.

The metadata resolved by `map_dois.py` has the venue name but not the id that
the crawler filters on, so the reference papers are requested again from the
batch endpoint with the `publicationVenue` field. The ids are needed to
restrict the reference papers to the publication venues of an ISSN file, see
https://github.com/DFKI-NLP/kibad-crawler/issues/47.

Writes `wald_venues_s2.csv` next to `wald_dois_s2.csv` with one row per paper.
"""

import os
import time

from loguru import logger
import pandas as pd

from kibad_crawler.semantic_scholar import academic_graph
from kibad_crawler.utils import chunker

BASE_DIR = "/netscratch/asafari/kibad-crawler/data/external/40_evaluation"
DOIS_FILE = os.path.join(BASE_DIR, "wald_dois_s2.csv")
OUTPUT_FILE = os.path.join(BASE_DIR, "wald_venues_s2.csv")
FIELDS = "paperId,publicationVenue,venue,year,publicationDate"
DELAY_BETWEEN_BATCHES = 3


def get_reference_paper_ids() -> list[str]:
    """Return the Semantic Scholar ids of the reference papers.

    Returns:
        list[str]: Paper ids of the screening tables, without duplicates.
    """
    df = pd.read_csv(DOIS_FILE)
    paper_ids = df.loc[df["paperId"].notna(), "paperId"].unique().tolist()
    logger.info(f"{len(paper_ids):,} reference papers with a Semantic Scholar id")
    return paper_ids


def get_venues(paper_ids: list[str]) -> pd.DataFrame:
    """Query the Academic Graph API for the publication venue of the papers.

    Args:
        paper_ids (list[str]): Semantic Scholar ids of the papers.

    Returns:
        pd.DataFrame: One row per paper with the publication venue id, name
            and ISSN code, empty where the API returns no venue.
    """
    records = []
    for i, group in enumerate(chunker(paper_ids, 500)):
        papers = academic_graph.batch(group, fields=FIELDS)
        for paper_id, paper in zip(group, papers):
            if paper is None:
                continue
            venue = paper.get("publicationVenue") or {}
            records.append(
                {
                    "paperId": paper_id,
                    "publication_venue_id": venue.get("id"),
                    "publication_venue_name": venue.get("name"),
                    "publication_venue_issn": venue.get("issn"),
                    "venue": paper.get("venue"),
                    "year": paper.get("year"),
                    "publication_date": paper.get("publicationDate"),
                }
            )
        logger.info(f"batch {i}: {len(records):,} of {len(paper_ids):,} papers")
        time.sleep(DELAY_BETWEEN_BATCHES)
    return pd.DataFrame(records)


def main():
    paper_ids = get_reference_paper_ids()
    df_venues = get_venues(paper_ids)
    df_venues.to_csv(OUTPUT_FILE, index=False)

    with_venue_id = df_venues["publication_venue_id"].notna().sum()
    logger.info(f"{df_venues.shape[0]:,} papers saved to '{OUTPUT_FILE}'")
    logger.info(f"{with_venue_id:,} of them have a publication venue id")


if __name__ == "__main__":
    main()
