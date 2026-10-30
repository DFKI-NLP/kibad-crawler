"""Reference papers from the screening tables of the literature review.

The screening tables identify papers by DOI and hold the screening decision in
the `included` column (1 relevant, 0 not relevant, empty not screened). The
metadata downloaded by the crawler has no DOI, so the DOIs are resolved to
Semantic Scholar paper ids with the batch endpoint of the Academic Graph API,
together with the publication venue id that the crawler filters on.

The tables are described in https://github.com/DFKI-NLP/kibad-crawler/issues/42.
"""

from pathlib import Path
import time

from loguru import logger
import pandas as pd

from kibad_crawler.config import EXTERNAL_DATA_DIR
from kibad_crawler.search_queries import Habitat
from kibad_crawler.semantic_scholar import academic_graph
from kibad_crawler.utils import chunker

SCREENING_TABLES_DIR = EXTERNAL_DATA_DIR / "screening_tables"
SCREENING_TABLES = {
    Habitat.FOREST: [
        "Wald-ASReview-Alle.xlsx",
        "Wald-asreview-erste-haelfte.xlsx",
        "Wald-asreview-zweite-haelfte.xlsx",
        "Wald-ÖSL-zusätzlich.csv",
    ],
}
FIELDS = "paperId,publicationVenue"
DELAY_BETWEEN_BATCHES = 3


def read_screening_tables(tables_dir: Path, file_names: list[str]) -> pd.DataFrame:
    """Return the rows of the screening tables that have a DOI.

    Args:
        tables_dir (Path): Folder with the screening tables.
        file_names (list[str]): Excel or CSV files to read.

    Returns:
        pd.DataFrame: One row per DOI and source file with the screening
            decision and the publication year.
    """
    frames = []
    for name in file_names:
        path = tables_dir / name
        df = pd.read_csv(path) if name.endswith(".csv") else pd.read_excel(path, sheet_name=0)
        df["doi"] = df["doi"].astype(str).str.strip().str.lower()
        df = df[~df["doi"].isin(["", "nan", "none"])]
        logger.info(f"'{name}' has {df.shape[0]:,} rows with a DOI")
        frames.append(df[["doi", "included", "year"]].assign(source_file=name))
    return pd.concat(frames, ignore_index=True).drop_duplicates(subset=["doi", "source_file"])


def resolve_dois(dois: list[str]) -> pd.DataFrame:
    """Query the Academic Graph API for the paper id and publication venue id
    of the given DOIs.

    Args:
        dois (list[str]): DOIs of the papers.

    Returns:
        pd.DataFrame: One row per DOI known to Semantic Scholar, the venue id
            is empty for papers without a publication venue.
    """
    records = []
    for i, group in enumerate(chunker(dois, 500)):
        papers = academic_graph.batch([f"DOI:{doi}" for doi in group], fields=FIELDS)
        for doi, paper in zip(group, papers):
            if paper is None:
                continue
            venue: dict = paper.get("publicationVenue") or {}
            records.append(
                {
                    "doi": doi,
                    "paperId": paper.get("paperId"),
                    "publication_venue_id": venue.get("id"),
                }
            )
        logger.info(f"batch {i}: {len(records):,} of {len(dois):,} DOIs resolved")
        time.sleep(DELAY_BETWEEN_BATCHES)
    return pd.DataFrame(records, columns=["doi", "paperId", "publication_venue_id"])


def get_reference_papers(habitat: Habitat, tables_dir: Path = SCREENING_TABLES_DIR) -> pd.DataFrame:
    """Return the reference papers of a habitat, one row per paper id.

    The resolved DOIs are stored next to the tables, so that the API is only
    called once per habitat.

    Args:
        habitat (Habitat): Habitat with screening tables in `SCREENING_TABLES`.
        tables_dir (Path, optional): Folder with the screening tables.
            Defaults to `SCREENING_TABLES_DIR`.

    Returns:
        pd.DataFrame: Reference papers with the screening decision, the
            publication year and the publication venue id.
    """
    resolved_path = tables_dir / f"{habitat.name.lower()}_dois_s2.csv"
    if resolved_path.exists():
        df = pd.read_csv(resolved_path)
    else:
        df = read_screening_tables(tables_dir, SCREENING_TABLES[habitat])
        df = df.merge(resolve_dois(sorted(set(df["doi"]))), on="doi", how="left")
        df.to_csv(resolved_path, index=False)
        logger.info(f"{df.shape[0]:,} rows saved to '{resolved_path}'")

    dois = df["doi"].nunique()
    resolved = df.loc[df["paperId"].notna(), "doi"].nunique()
    logger.info(f"{habitat.value}: {dois:,} DOIs, {dois - resolved:,} unknown to Semantic Scholar")

    df = df[df["paperId"].notna()]
    # a paper can be in more than one table, a decision wins over no decision
    df = df.sort_values("included").drop_duplicates(subset=["paperId"], keep="first")
    return df.reset_index(drop=True)
