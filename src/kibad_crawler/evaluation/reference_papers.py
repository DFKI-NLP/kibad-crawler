"""Reference papers from the screening tables of the literature review.

The screening tables identify papers by DOI and hold the screening decision in
the `included` column (1 relevant, 0 not relevant, empty not screened), the
Soil tables as free text in a column `Relevant (Ja/Nein/Unsicher)`. The
metadata downloaded by the crawler has no DOI, so the DOIs are resolved to
Semantic Scholar paper ids with the batch endpoint of the Academic Graph API,
together with the publication venue id that the crawler filters on.

The tables are described in https://github.com/DFKI-NLP/kibad-crawler/issues/42.
"""

from dataclasses import dataclass
from pathlib import Path
import time

from loguru import logger
import pandas as pd

from kibad_crawler.config import EXTERNAL_DATA_DIR
from kibad_crawler.semantic_scholar import academic_graph
from kibad_crawler.utils import chunker

SCREENING_TABLES_DIR = EXTERNAL_DATA_DIR / "screening_tables"
# first word of a free text decision, anything else counts as not screened
DECISIONS = {"ja": 1, "relevant": 1, "nein": 0, "nei": 0, "no": 0, "nicht": 0}
FIELDS = "paperId,publicationVenue"
DELAY_BETWEEN_BATCHES = 3


@dataclass
class ScreeningTables:
    """Screening tables of one literature search and the queries that
    replicate that search."""

    name: str
    file_names: list[str]
    query_ids: list[str]


SCREENING_TABLES = [
    ScreeningTables(
        "forest",
        [
            "Wald-ASReview-Alle.xlsx",
            "Wald-asreview-erste-haelfte.xlsx",
            "Wald-asreview-zweite-haelfte.xlsx",
            "Wald-ÖSL-zusätzlich.csv",
        ],
        ["Q1", "Q2", "Q3", "Q4"],
    ),
    ScreeningTables("soil_drivers", ["Boden-Treiber.xlsx"], ["Q6"]),
    ScreeningTables("soil_measures", ["Boden-Maßnahmen.xlsx"], ["Q7"]),
    ScreeningTables("coast_trends", ["Küste/asreview_result_trends_AdrianDoro.xlsx"], ["Q17"]),
    ScreeningTables("ecosystem_services_cross_section", ["ÖSL-Querschnitt.xlsx"], ["Q25"]),
    ScreeningTables("ecosystem_services_habitats", ["ÖSL-lebensräume.xlsx"], ["Q26"]),
]


def get_decisions(df: pd.DataFrame) -> pd.Series:
    """Return the screening decision of each row of a screening table.

    Args:
        df (pd.DataFrame): Screening table with an `included` column or a
            free text column whose name starts with `Relevant`.

    Returns:
        pd.Series: 1 for relevant, 0 for not relevant, empty otherwise.
    """
    if "included" in df:
        return df["included"]
    column = next(name for name in df.columns if name.startswith("Relevant"))
    first_words = df[column].astype(str).str.strip().str.lower().str.split(r"[\s\\-]+").str[0]
    return first_words.map(DECISIONS)


def read_screening_tables(tables_dir: Path, file_names: list[str]) -> pd.DataFrame:
    """Return the rows of the screening tables that have a DOI.

    Args:
        tables_dir (Path): Folder with the screening tables.
        file_names (list[str]): Excel or CSV files to read.

    Returns:
        pd.DataFrame: One row per DOI and source file with the screening
            decision.
    """
    frames = []
    for name in file_names:
        path = tables_dir / name
        df = pd.read_csv(path) if name.endswith(".csv") else pd.read_excel(path, sheet_name=0)
        # the Soil tables name the column `DOI`
        doi_column = next(column for column in df.columns if column.lower() == "doi")
        df = pd.DataFrame(
            {
                "doi": df[doi_column].astype(str).str.strip().str.lower(),
                "included": get_decisions(df),
                "source_file": name,
            }
        )
        df = df[~df["doi"].isin(["", "nan", "none"])]
        logger.info(f"'{name}' has {df.shape[0]:,} rows with a DOI")
        frames.append(df)
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


def get_reference_papers(
    tables: ScreeningTables, tables_dir: Path = SCREENING_TABLES_DIR
) -> pd.DataFrame:
    """Return the reference papers of a literature search, one row per paper id.

    The resolved DOIs are stored next to the tables, so that the API is only
    called once per search.

    Args:
        tables (ScreeningTables): Screening tables of the search.
        tables_dir (Path, optional): Folder with the screening tables.
            Defaults to `SCREENING_TABLES_DIR`.

    Returns:
        pd.DataFrame: Reference papers with the screening decision and the
            publication venue id.
    """
    resolved_path = tables_dir / f"{tables.name}_dois_s2.csv"
    if resolved_path.exists():
        df = pd.read_csv(resolved_path)
    else:
        df = read_screening_tables(tables_dir, tables.file_names)
        df = df.merge(resolve_dois(sorted(set(df["doi"]))), on="doi", how="left")
        df.to_csv(resolved_path, index=False)
        logger.info(f"{df.shape[0]:,} rows saved to '{resolved_path}'")

    dois = df["doi"].nunique()
    resolved = df.loc[df["paperId"].notna(), "doi"].nunique()
    logger.info(f"{tables.name}: {dois:,} DOIs, {dois - resolved:,} unknown to Semantic Scholar")

    df = df[df["paperId"].notna()]
    # a paper can be in more than one table, a decision wins over no decision
    df = df.sort_values("included").drop_duplicates(subset=["paperId"], keep="first")
    return df.reset_index(drop=True)
