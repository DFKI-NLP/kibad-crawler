"""Probe the Recommendations API of Semantic Scholar with the Forest reference papers.

Part of the Forest papers screened as relevant are sent as positive examples,
optionally with papers screened as not relevant as negative examples, and the
recommended papers are compared with the held out relevant papers, with the
reference papers in general and with the papers of the given crawls.

The Recommendations API returns at most 500 papers from its own pool and does
not score papers given by the caller, so this shows what it recommends, not
how it would rank the hits of the string searches.

Call it with the folders under `data/raw/semantic_scholar/release/` to compare:

    uv run python scripts/probe_recommendations.py 2024-12-31_journals_csv 2026-10-13
"""

import os
import sys

from loguru import logger
import pandas as pd
from tqdm import tqdm

from kibad_crawler.config import RAW_DATA_DIR, S2_API_KEY
from kibad_crawler.utils import api_call_post

BASE_DIR = "/netscratch/asafari/kibad-crawler/data/external/40_evaluation"
DOIS_FILE = os.path.join(BASE_DIR, "wald_dois_s2.csv")
OUTPUT_FILE = os.path.join(BASE_DIR, "recommendations_probe.csv")
URL = "https://api.semanticscholar.org/recommendations/v1/papers/"
FIELDS = "title,year,venue,publicationDate"
LIMIT = 500
N_POSITIVE = 100
N_NEGATIVE = 100
SEED = 0


def get_reference_papers() -> pd.DataFrame:
    """Return the reference papers with their screening decision.

    Returns:
        pd.DataFrame: One row per paper id of the screening tables.
    """
    df = pd.read_csv(DOIS_FILE)
    df = df[df["paperId"].notna()]
    # same as in the other scripts: a decision wins over no decision
    df = df.sort_values("included").drop_duplicates(subset=["paperId"], keep="first")
    return df[["paperId", "included"]]


def get_crawled_paper_ids(folder: str) -> set[str]:
    """Return the paper ids of a crawl, read from its CSV files.

    Args:
        folder (str): Folder under `release/` that holds the crawl.

    Returns:
        set[str]: Paper ids of the crawl.
    """
    papers_path = RAW_DATA_DIR / "semantic_scholar" / "release" / folder / "papers"
    paper_ids: set[str] = set()
    for csv_path in tqdm(sorted(papers_path.glob("*.gz.csv")), desc=f"Reading {folder}"):
        df = pd.read_csv(csv_path, usecols=["url"], dtype=str)
        paper_ids.update(df["url"].str.split("/").str[-1])
    return paper_ids


def recommend(positive: list[str], negative: list[str]) -> pd.DataFrame:
    """Return the papers that the Recommendations API recommends for the examples.

    Args:
        positive (list[str]): Paper ids of positive examples.
        negative (list[str]): Paper ids of negative examples.

    Returns:
        pd.DataFrame: One row per recommended paper, in the order of the API.
    """
    response = api_call_post(
        url=URL,
        params={"fields": FIELDS, "limit": LIMIT},
        payload={"positivePaperIds": positive, "negativePaperIds": negative},
        api_key=S2_API_KEY,
    )
    return pd.DataFrame(response.json()["recommendedPapers"])


def main():
    folders = sys.argv[1:]

    df_reference = get_reference_papers()
    # a fixed seed keeps the split of the papers reproducible
    shuffled = df_reference.sort_values("paperId").sample(frac=1, random_state=SEED)
    relevant = shuffled.loc[shuffled["included"] == 1, "paperId"].tolist()
    not_relevant = shuffled.loc[shuffled["included"] == 0, "paperId"].tolist()
    positive, held_out = relevant[:N_POSITIVE], set(relevant[N_POSITIVE:])
    decision = dict(zip(df_reference["paperId"], df_reference["included"]))
    logger.info(
        f"{len(relevant):,} relevant reference papers: {len(positive)} as positive examples, "
        f"{len(held_out):,} held out"
    )

    crawled = {folder: get_crawled_paper_ids(folder) for folder in folders}

    results = []
    for name, negative in [
        ("positive only", []),
        (f"positive and {N_NEGATIVE} negative", not_relevant[:N_NEGATIVE]),
    ]:
        df = recommend(positive=positive, negative=negative)
        df["probe"] = name
        df["rank"] = range(1, len(df) + 1)
        df["reference"] = df["paperId"].isin(decision)
        df["included"] = df["paperId"].map(decision)
        df["held_out_relevant"] = df["paperId"].isin(held_out)
        for folder, paper_ids in crawled.items():
            df[f"in_{folder}"] = df["paperId"].isin(paper_ids)
        results.append(df)

        years = pd.to_numeric(df["year"], errors="coerce")
        print("=" * 70)
        print(f"{name}: {len(df)} recommended papers")
        print(
            f"  reference papers: {df['reference'].sum()}, of them screened as relevant "
            f"{df['included'].eq(1).sum()}, not relevant {df['included'].eq(0).sum()}"
        )
        print(
            f"  held out relevant papers found: {df['held_out_relevant'].sum()} of {len(held_out):,}"
        )
        print(
            f"  held out relevant in the top 100: {df.loc[df['rank'] <= 100, 'held_out_relevant'].sum()}"
        )
        print(
            f"  publication years: min {years.min():.0f}, median {years.median():.0f}, max {years.max():.0f}"
        )
        print(f"  per year: {years.value_counts().sort_index().astype(int).to_dict()}")
        for folder in folders:
            print(f"  in '{folder}': {df[f'in_{folder}'].sum()}")
        print(
            f"  most frequent venues: {df['venue'].replace('', None).value_counts().head(8).to_dict()}"
        )

    pd.concat(results).to_csv(OUTPUT_FILE, index=False)
    print("=" * 70)
    print(f"recommended papers saved to '{OUTPUT_FILE}'")


if __name__ == "__main__":
    main()
