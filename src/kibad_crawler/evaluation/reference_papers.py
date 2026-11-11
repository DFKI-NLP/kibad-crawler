"""Reference papers from the screening tables of the literature review.

The screening tables identify papers by DOI and hold the screening decision in
the `included` column (1 relevant, 0 not relevant, empty not screened), the
Soil tables as free text in a column `Relevant (Ja/Nein/Unsicher)`, and the
RIS exports of ASReview as a note `ASReview_relevant`. The
metadata downloaded by the crawler has no DOI, so the DOIs are resolved to
Semantic Scholar paper ids with the batch endpoint of the Academic Graph API,
together with the publication venue id that the crawler filters on.

The tables are described in https://github.com/DFKI-NLP/kibad-crawler/issues/42.
"""

from dataclasses import dataclass
from pathlib import Path
import re
import time

from loguru import logger
import pandas as pd

from kibad_crawler.config import EXTERNAL_DATA_DIR
from kibad_crawler.semantic_scholar import academic_graph
from kibad_crawler.utils import chunker

SCREENING_TABLES_DIR = EXTERNAL_DATA_DIR / "screening_tables"
# first word of a free text decision
DECISIONS = {"ja": 1, "relevant": 1, "nein": 0, "nei": 0, "no": 0, "nicht": 0}
FIELDS = "paperId,publicationVenue"
DELAY_BETWEEN_BATCHES = 3
ASREVIEW_LABELS = {"ASReview_relevant": 1, "ASReview_irrelevant": 0}


@dataclass
class ScreeningTables:
    """Screening tables of one literature search and the queries that
    replicate that search."""

    name: str
    file_names: list[str]
    query_ids: list[str]
    sheet: str | int = 0
    # a table that lists only the selected papers of the hits in `file_names`
    selected_file: str | None = None


SCREENING_TABLES = [
    ScreeningTables(
        "forest",
        [
            "Wald-asreview-erste-haelfte.xlsx",
            "Wald-asreview-zweite-haelfte.xlsx",
            "Wald-ÖSL-zusätzlich.csv",
        ],
        ["Q1", "Q2", "Q3", "Q4"],
    ),
    ScreeningTables("soil_trends", ["Boden-Trend.xlsx"], ["Q5"]),
    ScreeningTables("soil_drivers", ["Boden-Treiber.xlsx"], ["Q6"]),
    ScreeningTables("soil_measures", ["Boden-Maßnahmen.xlsx"], ["Q7"]),
    ScreeningTables(
        "agricultural",
        ["Agrar- und Offenland/asreview_dataset_ALL_sorted.xlsx"],
        ["Q9", "Q10", "Q11", "Q12"],
        sheet="dup_rmvd",
    ),
    ScreeningTables(
        "agricultural_drivers",
        ["Agrar- und Offenland/asreview_result_agrar-treiber-final2.xlsx"],
        ["Q10"],
    ),
    ScreeningTables(
        "agricultural_ecosystem_services",
        ["Agrar- und Offenland/asreview_result_agrar-ösl-final2.xlsx"],
        ["Q12"],
    ),
    ScreeningTables(
        "inland_waters",
        ["Binnengewässer und Auen/Merged_Wos_Scopus.ris"],
        ["Q13", "Q14", "Q15", "Q16"],
        selected_file="Binnengewässer und Auen/630 selected from 875hits_S.P.H_fin.xlsx",
    ),
    ScreeningTables("coast_trends", ["Küste/asreview_result_trends_AdrianDoro.xlsx"], ["Q17"]),
    # lists only the papers screened as relevant
    ScreeningTables(
        "coast_measures", ["Küste/Faktencheck_Massnahmen_screening_Ergebnisse.ris"], ["Q19"]
    ),
    ScreeningTables(
        "urban_trends", ["Urban/asreview_dataset_status-trends-nico-final.ris"], ["Q21"]
    ),
    ScreeningTables("ecosystem_services_cross_section", ["ÖSL-Querschnitt.xlsx"], ["Q25"]),
    ScreeningTables("ecosystem_services_habitats", ["ÖSL-lebensräume.xlsx"], ["Q26"]),
]


def get_decisions(df: pd.DataFrame) -> pd.Series:
    """Return the screening decision of the rows of a screening table.

    A free text decision that is neither yes nor no names another chapter of
    the literature review, for example "Treiber" in the Soil trends table.
    These rows are left out, so the result can have fewer rows than `df`.

    Args:
        df (pd.DataFrame): Screening table with an `included` column, a
            free text column whose name starts with `Relevant`, or neither.

    Returns:
        pd.Series: 1 for relevant, 0 for not relevant, empty for not
            screened, with the index of the rows that are kept.
    """
    if "included" in df:
        return df["included"]
    column = next((name for name in df.columns if str(name).startswith("Relevant")), None)
    if column is None:
        # a table without decisions, for example a list of selected papers
        return pd.Series(None, index=df.index, dtype=float)
    labels = df[column].astype("string").str.strip().str.lower()
    decisions = labels.str.split(r"[\s\\-]+").str[0].map(DECISIONS)
    not_screened = labels.fillna("") == ""
    return decisions[not_screened | decisions.notna()]


def read_ris(path: Path) -> pd.DataFrame:
    """Return the DOI and the ASReview label of the records of a RIS file.

    Args:
        path (Path): RIS file.

    Returns:
        pd.DataFrame: One row per record with `doi` and `included`, empty
            where a record has no DOI or no label.
    """
    text = path.read_text(encoding="utf-8-sig").replace("\r", "")
    records = []
    for record in text.split("\nER  -"):
        if not record.strip():
            continue
        doi = re.search(r"^DO  - (.*)$", record, re.M)
        label = re.search(r"ASReview_\w+", record)
        records.append(
            {
                "doi": doi.group(1) if doi else None,
                "included": ASREVIEW_LABELS.get(label.group(0)) if label else None,
            }
        )
    return pd.DataFrame(records, columns=["doi", "included"])


def read_table(path: Path, sheet: str | int = 0) -> pd.DataFrame:
    """Return the DOI and the screening decision of the rows of a table.

    Args:
        path (Path): Excel, CSV or RIS file.
        sheet (str | int, optional): Sheet of an Excel file. Defaults to 0.

    Returns:
        pd.DataFrame: One row per paper with `doi` and `included`.
    """
    if path.suffix == ".ris":
        return read_ris(path)
    df = pd.read_csv(path) if path.suffix == ".csv" else pd.read_excel(path, sheet_name=sheet)
    if not any(str(column).lower() == "doi" for column in df.columns):
        # the Inland waters table has a row with group headers above the column names
        df = pd.read_excel(path, sheet_name=sheet, header=1)
    # the Soil tables name the column `DOI`
    doi_column = next(column for column in df.columns if str(column).lower() == "doi")
    decisions = get_decisions(df)
    return pd.DataFrame({"doi": df.loc[decisions.index, doi_column], "included": decisions})


def read_screening_tables(tables_dir: Path, tables: ScreeningTables) -> pd.DataFrame:
    """Return the rows of the screening tables of a search that have a DOI.

    With `selected_file`, a paper of the tables counts as relevant when it is
    in the selected file and as not relevant otherwise.

    Args:
        tables_dir (Path): Folder with the screening tables.
        tables (ScreeningTables): Screening tables of the search.

    Returns:
        pd.DataFrame: One row per DOI and source file with the screening
            decision.
    """
    frames = []
    for name in tables.file_names:
        df = read_table(tables_dir / name, sheet=tables.sheet).assign(source_file=name)
        df["doi"] = df["doi"].astype(str).str.strip().str.lower()
        df = df[~df["doi"].isin(["", "nan", "none"])]
        logger.info(f"'{name}' has {df.shape[0]:,} rows with a DOI")
        frames.append(df)
    df = pd.concat(frames, ignore_index=True).drop_duplicates(subset=["doi", "source_file"])

    if tables.selected_file:
        selected = read_table(tables_dir / tables.selected_file)["doi"]
        df["included"] = (
            df["doi"].isin(set(selected.astype(str).str.strip().str.lower())).astype(int)
        )
    return df


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
        df = read_screening_tables(tables_dir, tables)
        df = df.merge(resolve_dois(sorted(set(df["doi"]))), on="doi", how="left")
        df.to_csv(resolved_path, index=False)
        logger.info(f"{df.shape[0]:,} rows saved to '{resolved_path}'")

    # tables that were taken out of the search after the DOIs were resolved
    df = df[df["source_file"].isin(tables.file_names)]
    dois = df["doi"].nunique()
    resolved = df.loc[df["paperId"].notna(), "doi"].nunique()
    logger.info(f"{tables.name}: {dois:,} DOIs, {dois - resolved:,} unknown to Semantic Scholar")

    df = df[df["paperId"].notna()]
    # a paper can be in more than one table, a decision wins over no decision
    df = df.sort_values("included").drop_duplicates(subset=["paperId"], keep="first")
    return df.reset_index(drop=True)
