"""Coverage of the Forest reference papers in the papers of a crawl.

Reports the coverage without the screening decision, by publication decade,
and restricted to the publication venues of an ISSN file, so that the same
journals are used on both sides. The paper ids come from the CSV files of the
crawl, which is faster than reading the JSON files with the abstracts, and the
publication venues of the reference papers come from `map_reference_venues.py`.

Call it with the release, a CSV file with ISSN codes and the folder under
`data/raw/semantic_scholar/release/` that holds the crawl:

    uv run python scripts/coverage_of_reference_papers.py \
        2024-12-31 data/raw/journals.csv 2024-12-31_journals_csv

See https://github.com/DFKI-NLP/kibad-crawler/issues/47.
"""

import os
import sys

from loguru import logger
import pandas as pd
from tqdm import tqdm

from kibad_crawler.config import RAW_DATA_DIR
from kibad_crawler.semantic_scholar import datasets
from kibad_crawler.utils import get_issn_codes

BASE_DIR = "/netscratch/asafari/kibad-crawler/data/external/40_evaluation"
DOIS_FILE = os.path.join(BASE_DIR, "wald_dois_s2.csv")
VENUES_FILE = os.path.join(BASE_DIR, "wald_venues_s2.csv")


def get_reference_papers() -> pd.DataFrame:
    """Return the reference papers with their publication venue.

    Returns:
        pd.DataFrame: One row per paper id with the screening decision, the
            publication year and the publication venue id.
    """
    df = pd.read_csv(DOIS_FILE)
    dois = df["doi"].nunique()
    resolved = df.loc[df["paperId"].notna(), "doi"].nunique()
    logger.info(f"{dois:,} unique DOIs, {resolved:,} resolved, {dois - resolved:,} unknown to S2")

    df = df[df["paperId"].notna()]
    # same as in `compare_search_with_screening.py`: a paper keeps the decision
    # of the tables it appears in, a decision wins over no decision
    df = df.sort_values("included").drop_duplicates(subset=["paperId"], keep="first")

    df_venues = pd.read_csv(VENUES_FILE)
    df = df.merge(
        df_venues[["paperId", "publication_venue_id", "publication_venue_name"]],
        on="paperId",
        how="left",
    )
    logger.info(f"{df.shape[0]:,} reference papers, {df['included'].sum():,.0f} screened relevant")
    return df


def get_publication_venue_ids(release_id: str, file_with_issn: str) -> set[str]:
    """Return the venue ids of the ISSN codes, from the downloaded dataset.

    Args:
        release_id (str): Release whose publication venues are on disk.
        file_with_issn (str): CSV file with the ISSN codes.

    Returns:
        set[str]: Ids of the matched publication venues.
    """
    venues_path = RAW_DATA_DIR / "semantic_scholar" / "release" / release_id / "publication_venues"
    files = sorted(venues_path.glob("*.gz"))
    if not files:
        raise FileNotFoundError(f"no publication venues downloaded for release '{release_id}'")

    issn = get_issn_codes(file_with_issn)
    df_venues = datasets.read_publication_venues(file_path=files[0])
    venue_ids = set(df_venues[df_venues["issn"].isin(issn)].id.unique())
    logger.info(f"'{file_with_issn}': {len(issn):,} ISSN codes, {len(venue_ids):,} venues")
    return venue_ids


def get_crawled_papers(folder: str) -> pd.DataFrame:
    """Return the paper ids and publication dates of a crawl.

    Args:
        folder (str): Folder under `release/` that holds the crawl.

    Returns:
        pd.DataFrame: One row per paper of the filtered CSV files.
    """
    papers_path = RAW_DATA_DIR / "semantic_scholar" / "release" / folder / "papers"
    csv_files = sorted(papers_path.glob("*.gz.csv"))
    logger.info(f"{len(csv_files)} CSV files in '{papers_path}'")

    frames = []
    for csv_path in tqdm(csv_files, desc="Reading papers"):
        df = pd.read_csv(csv_path, usecols=["url", "publicationdate"], dtype=str)
        frames.append(df)

    df_papers = pd.concat(frames, ignore_index=True)
    df_papers["paperId"] = df_papers["url"].str.split("/").str[-1]
    df_papers = df_papers.drop_duplicates(subset=["paperId"])
    logger.info(f"{df_papers.shape[0]:,} papers in the crawl")
    return df_papers


def report_coverage(df_reference: pd.DataFrame, crawled: set[str], label: str):
    """Print how many reference papers are in the crawl, of the ones screened
    as relevant and per publication decade.

    Args:
        df_reference (pd.DataFrame): Reference papers with a publication year.
        crawled (set[str]): Paper ids of the crawl.
        label (str): Name of the set of reference papers.
    """
    total = df_reference.shape[0]
    if not total:
        print(f"{label}: no reference papers")
        return

    found = df_reference["paperId"].isin(crawled)
    print(f"{label}: {found.sum():,} of {total:,} papers in the crawl ({found.mean():.0%})")

    relevant = df_reference["included"] == 1
    if relevant.any():
        print(
            f"  screened as relevant: {found[relevant].sum():,} of {relevant.sum():,} "
            f"({found[relevant].mean():.0%})"
        )

    years = pd.to_numeric(df_reference["year"], errors="coerce")
    decades = (years // 10 * 10).astype("Int64")
    for decade in sorted(decades.dropna().unique()):
        in_decade = decades == decade
        share = found[in_decade].mean()
        print(f"  {int(decade)}s: {found[in_decade].sum():,} of {in_decade.sum():,} ({share:.0%})")
    without_year = years.isna().sum()
    if without_year:
        print(f"  without a year: {found[years.isna()].sum():,} of {without_year:,}")


def main():
    release_id, file_with_issn, folder = sys.argv[1], sys.argv[2], sys.argv[3]

    df_reference = get_reference_papers()
    venue_ids = get_publication_venue_ids(release_id=release_id, file_with_issn=file_with_issn)
    crawled = set(get_crawled_papers(folder)["paperId"])

    print("=" * 70)
    report_coverage(df_reference, crawled, "all reference papers")

    print("=" * 70)
    in_venues = df_reference[df_reference["publication_venue_id"].isin(venue_ids)]
    report_coverage(in_venues, crawled, f"reference papers of the venues of '{file_with_issn}'")

    # a paper without a publication venue id cannot be reached by any ISSN
    # list, since the crawler filters the papers by that id
    print("=" * 70)
    has_venue_id = df_reference["publication_venue_id"].notna()
    relevant = df_reference["included"] == 1
    print(
        f"publication venue id: {has_venue_id.sum():,} of {df_reference.shape[0]:,} "
        f"reference papers ({has_venue_id.mean():.0%})"
    )
    print(
        f"  screened as relevant: {(has_venue_id & relevant).sum():,} of {relevant.sum():,} "
        f"({(has_venue_id & relevant).sum() / relevant.sum():.0%})"
    )


if __name__ == "__main__":
    main()
