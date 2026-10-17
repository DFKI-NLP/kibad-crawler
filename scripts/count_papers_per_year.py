"""Count the papers of a crawl per publication year.

Quantifies how many new papers appear in the publication venues of a crawl,
which is the argument for monitoring new publications, see
https://github.com/DFKI-NLP/kibad-crawler/issues/47. The counts come from the
CSV files of the crawl, so no download and no API request is needed.

Call it with one or more folders under `data/raw/semantic_scholar/release/`:

    uv run python scripts/count_papers_per_year.py 2026-10-13 2024-12-31_journals_csv
"""

import sys

from loguru import logger
import pandas as pd
from tqdm import tqdm

from kibad_crawler.config import RAW_DATA_DIR

CUT_DATES = ["2022-12-31", "2024-12-31"]


def count_per_year(folder: str) -> pd.Series:
    """Return the number of papers per publication year of a crawl.

    Args:
        folder (str): Folder under `release/` that holds the crawl.

    Returns:
        pd.Series: Papers per year, the index `-1` holds the papers without a
            publication date.
    """
    papers_path = RAW_DATA_DIR / "semantic_scholar" / "release" / folder / "papers"
    csv_files = sorted(papers_path.glob("*.gz.csv"))
    logger.info(f"{len(csv_files)} CSV files in '{papers_path}'")

    frames = []
    for csv_path in tqdm(csv_files, desc=f"Reading {folder}"):
        df = pd.read_csv(csv_path, usecols=["url", "publicationdate"], dtype=str)
        frames.append(df)

    df_papers = pd.concat(frames, ignore_index=True)
    df_papers["paperId"] = df_papers["url"].str.split("/").str[-1]
    df_papers = df_papers.drop_duplicates(subset=["paperId"])
    logger.info(f"{df_papers.shape[0]:,} papers in '{folder}'")

    years = pd.to_datetime(df_papers["publicationdate"], errors="coerce").dt.year
    return years.fillna(-1).astype(int).value_counts().sort_index()


def main():
    folders = sys.argv[1:]
    counts = {folder: count_per_year(folder) for folder in folders}

    df = pd.DataFrame(counts).fillna(0).astype(int)
    print("=" * 70)
    print(f"papers per publication year, '-1' has no publication date\n\n{df.to_string()}")

    print("=" * 70)
    for folder, per_year in counts.items():
        with_date = per_year.drop(index=-1, errors="ignore")
        print(f"{folder}: {per_year.sum():,} papers, {per_year.get(-1, 0):,} without a date")
        for cut in CUT_DATES:
            until = with_date[with_date.index <= int(cut[:4])].sum()
            print(f"  published until {cut}: {until:,}")
        print(f"  published until today: {with_date.sum():,}")


if __name__ == "__main__":
    main()
