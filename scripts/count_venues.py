"""Count the publication venues that the ISSN codes of a file resolve to.

Uses the publication venues dataset that the crawler already downloaded for a
release, so no request and no download is needed. Call it with the release and
one or more CSV files with ISSN codes:

    uv run python scripts/count_venues.py 2024-12-31 data/raw/journals.csv data/raw/ISSN.csv

See https://github.com/DFKI-NLP/kibad-crawler/issues/42.
"""

import sys

from loguru import logger

from kibad_crawler.config import RAW_DATA_DIR
from kibad_crawler.semantic_scholar import datasets
from kibad_crawler.utils import get_issn_codes


def main():
    release_id = sys.argv[1]
    files_with_issn = sys.argv[2:]

    venues_path = RAW_DATA_DIR / "semantic_scholar" / "release" / release_id / "publication_venues"
    files = sorted(venues_path.glob("*.gz"))
    if not files:
        logger.info(f"no publication venues downloaded for release '{release_id}'")
        return

    for file_path in files:
        df_venues = datasets.read_publication_venues(file_path=file_path)
        for file_with_issn in files_with_issn:
            issn = get_issn_codes(file_with_issn)
            df_matched = df_venues[df_venues["issn"].isin(issn)]
            print(
                f"{file_with_issn}: {len(issn):,} ISSN codes, "
                f"{df_matched.id.nunique():,} publication venues, "
                f"{df_matched['issn'].nunique():,} of the codes matched"
            )


if __name__ == "__main__":
    main()
