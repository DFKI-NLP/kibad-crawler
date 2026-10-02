"""Describe the screening tables of the literature review.

Prints per table the number of rows, how many have a DOI, the publication
years, the screening decisions of the `included` column and how many papers
are published in a venue of `journals.csv`. The numbers reported in
https://github.com/DFKI-NLP/kibad-crawler/issues/42 come from this script.
"""

import os

from loguru import logger
import pandas as pd

from kibad_crawler.utils import get_issn_codes

BASE_DIR = "/netscratch/asafari/kibad-crawler/data/external/40_evaluation"
TABLES_DIR = os.path.join(BASE_DIR, "dois", "Screening Tabellen")
TABLES = [
    "Wald-ASReview-Alle.xlsx",
    "Wald-asreview-erste-haelfte.xlsx",
    "Wald-asreview-zweite-haelfte.xlsx",
    "Wald-ÖSL-zusätzlich.csv",
    "ÖSL-Querschnitt.xlsx",
    "ÖSL-lebensräume.xlsx",
]
FILE_WITH_ISSN = "data/raw/journals.csv"


def normalize_issn(value) -> str:
    """Return an ISSN code without the dash and in upper case."""
    return str(value).replace("-", "").strip().upper()


def main():
    issn_of_journals = {normalize_issn(x) for x in get_issn_codes(FILE_WITH_ISSN)}
    logger.info(f"{len(issn_of_journals)} ISSN codes in '{FILE_WITH_ISSN}'")

    for name in TABLES:
        path = os.path.join(TABLES_DIR, name)
        if name.endswith(".csv"):
            df = pd.read_csv(path)
        else:
            df = pd.read_excel(path, sheet_name=0)
        print("=" * 70)
        print(f"{name}: {df.shape[0]:,} rows")

        doi = df["doi"].astype(str).str.strip().str.lower()
        doi = doi[~doi.isin(["", "nan", "none"])]
        print(f"  with DOI: {len(doi):,}, unique: {doi.nunique():,}")

        for column in ["included", "Screened"]:
            if column in df.columns:
                print(f"  {column}: {df[column].value_counts(dropna=False).head(6).to_dict()}")

        if "year" in df.columns:
            years = pd.to_numeric(df["year"], errors="coerce").dropna().astype(int)
            if len(years) > 0:
                print(f"  years: {years.min()} to {years.max()}")
                print(f"  published 2024 or later: {int((years >= 2024).sum()):,}")

        if "issn" in df.columns:
            issn = df["issn"].astype(str).map(normalize_issn)
            issn = issn[~issn.isin(["NAN", "NONE", ""])]
            print(f"  with ISSN: {len(issn):,}, unique: {issn.nunique():,}")
            print(f"  in '{FILE_WITH_ISSN}': {int(issn.isin(issn_of_journals).sum()):,}")


if __name__ == "__main__":
    main()
