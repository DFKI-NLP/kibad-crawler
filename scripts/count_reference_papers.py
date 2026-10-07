"""Count the papers of the screening tables in the downloaded metadata.

Compares the output of two crawls without running a query, so the effect of a
venue list can be measured on the files that both crawls processed. Call it with
the folders under `data/raw/semantic_scholar/release/` to compare:

    uv run python scripts/count_reference_papers.py 2024-12-31 2024-12-31_journals_csv

See https://github.com/DFKI-NLP/kibad-crawler/issues/42.
"""

import json
import sys

from loguru import logger
import pandas as pd

from kibad_crawler.config import RAW_DATA_DIR

DOIS_FILE = "/netscratch/asafari/kibad-crawler/data/external/40_evaluation/wald_dois_s2.csv"


def get_reference_papers() -> pd.DataFrame:
    """Return the papers of the screening tables with their Semantic Scholar id.

    Returns:
        pd.DataFrame: One row per paper id with the screening decision.
    """
    df = pd.read_csv(DOIS_FILE)
    df = df[df["paperId"].notna()]
    return df.sort_values("included").drop_duplicates(subset=["paperId"], keep="first")


def count_papers(folder: str, reference: dict) -> dict:
    """Count the papers and the reference papers per paper dataset file.

    Args:
        folder (str): Folder under `release/` with the downloaded metadata.
        reference (dict): Screening decision per reference paper id.

    Returns:
        dict: Papers, reference papers and relevant papers per file name.
    """
    papers_path = RAW_DATA_DIR / "semantic_scholar" / "release" / folder / "papers"
    counts: dict = {}
    for json_file in sorted(papers_path.glob("*/json/*.json")):
        name = json_file.parent.parent.name
        counts.setdefault(name, {"papers": 0, "reference": 0, "relevant": 0})
        with open(json_file, encoding="utf-8") as f:
            papers = json.load(f)
        for paper in papers:
            if paper is None or not paper.get("paperId"):
                continue
            counts[name]["papers"] += 1
            if paper["paperId"] in reference:
                counts[name]["reference"] += 1
                if reference[paper["paperId"]] == 1:
                    counts[name]["relevant"] += 1
    return counts


def main():
    folders = sys.argv[1:]
    df_reference = get_reference_papers()
    reference = dict(zip(df_reference["paperId"], df_reference["included"]))
    logger.info(f"{len(reference):,} reference papers with a Semantic Scholar id")

    counts_per_folder = {folder: count_papers(folder, reference) for folder in folders}

    # the files that all folders have in common can be compared directly
    shared = set.intersection(*[set(counts) for counts in counts_per_folder.values()])
    print(f"{len(shared)} paper dataset files processed in all folders")
    for folder, counts in counts_per_folder.items():
        papers = sum(counts[name]["papers"] for name in shared)
        reference_papers = sum(counts[name]["reference"] for name in shared)
        relevant = sum(counts[name]["relevant"] for name in shared)
        print(
            f"{folder}: {papers:,} papers, {reference_papers:,} reference papers, "
            f"{relevant:,} of them screened as relevant"
        )


if __name__ == "__main__":
    main()
