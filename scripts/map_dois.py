"""Resolve the DOIs of the Forest screening tables to Semantic Scholar ids.

The screening tables of the literature review are described in
https://github.com/DFKI-NLP/kibad-crawler/issues/42. They identify papers by
DOI, while the metadata downloaded by the crawler does not contain the DOI, so
the DOIs are resolved with the batch endpoint of the Academic Graph API, which
accepts identifiers of the form `DOI:10.xxxx/yyyy`.

Writes `wald_dois_s2.csv` next to the tables with one row per DOI and source
file, the screening decision and the Semantic Scholar ids.
"""

import os
import time

from loguru import logger
import pandas as pd

from kibad_crawler.semantic_scholar import academic_graph
from kibad_crawler.utils import chunker

BASE_DIR = "/netscratch/asafari/kibad-crawler/data/external/40_evaluation"
TABLES_DIR = os.path.join(BASE_DIR, "dois", "Screening Tabellen")
FOREST_TABLES = [
    "Wald-ASReview-Alle.xlsx",
    "Wald-asreview-erste-haelfte.xlsx",
    "Wald-asreview-zweite-haelfte.xlsx",
    "Wald-ÖSL-zusätzlich.csv",
]
FIELDS = "paperId,corpusId,externalIds,title,year,venue,publicationDate"
DELAY_BETWEEN_BATCHES = 3


def read_screening_tables() -> pd.DataFrame:
    """Return the rows of the Forest screening tables that have a DOI.

    Returns:
        pd.DataFrame: One row per DOI and source file with the screening
            decision of the `included` column and the publication year.
    """
    records = []
    for name in FOREST_TABLES:
        path = os.path.join(TABLES_DIR, name)
        if name.endswith(".csv"):
            df = pd.read_csv(path)
        else:
            df = pd.read_excel(path, sheet_name=0)
        df["doi"] = df["doi"].astype(str).str.strip().str.lower()
        df = df[~df["doi"].isin(["", "nan", "none"])]
        logger.info(f"'{name}' has {df.shape[0]:,} rows with a DOI")
        for _, row in df.iterrows():
            records.append(
                {
                    "doi": row["doi"],
                    "source_file": name,
                    "included": row.get("included"),
                    "year": row.get("year"),
                }
            )
    return pd.DataFrame(records).drop_duplicates(subset=["doi", "source_file"])


def resolve_dois(dois: list) -> pd.DataFrame:
    """Query the Academic Graph API for the given DOIs in batches.

    Args:
        dois (list): DOIs of the papers to resolve.

    Returns:
        pd.DataFrame: Semantic Scholar ids of the DOIs that were found.
    """
    resolved = {}
    for i, group in enumerate(chunker(dois, 500)):
        papers = academic_graph.batch([f"DOI:{doi}" for doi in group], fields=FIELDS)
        for doi, paper in zip(group, papers):
            if paper is None:
                continue
            resolved[doi] = {
                "paperId": paper.get("paperId"),
                "corpusId": paper.get("corpusId"),
                "s2_year": paper.get("year"),
                "s2_venue": paper.get("venue"),
                "s2_publication_date": paper.get("publicationDate"),
            }
        logger.info(f"batch {i}: {len(resolved):,} of {len(dois):,} DOIs resolved")
        time.sleep(DELAY_BETWEEN_BATCHES)
    return pd.DataFrame.from_dict(resolved, orient="index").rename_axis("doi").reset_index()


def main():
    df_refs = read_screening_tables()
    dois = sorted(set(df_refs["doi"]))
    logger.info(f"{df_refs.shape[0]:,} rows with {len(dois):,} unique DOIs")

    df_s2 = resolve_dois(dois)
    df_refs = df_refs.merge(df_s2, on="doi", how="left")

    output_path = os.path.join(BASE_DIR, "wald_dois_s2.csv")
    df_refs.to_csv(output_path, index=False)

    found = df_refs["paperId"].notna().sum()
    logger.info(f"{df_refs.shape[0]:,} rows saved to '{output_path}'")
    logger.info(f"{df_s2.shape[0]:,} of {len(dois):,} DOIs are known to Semantic Scholar")
    logger.info(f"{df_refs.shape[0] - found:,} rows without a Semantic Scholar id")


if __name__ == "__main__":
    main()
