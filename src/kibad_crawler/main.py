from datetime import datetime
from typing import Annotated, Literal

from loguru import logger
from rich import print as print_rich
import typer

from kibad_crawler.basic_filter import (
    execute_all_search_queries,
    execute_all_search_queries_sift,
)
from kibad_crawler.config import RAW_DATA_DIR
from kibad_crawler.papers import PaperSearch, get_papers
from kibad_crawler.search_queries import ALL_SEARCH_QUERIES
from kibad_crawler.semantic_scholar import datasets
from kibad_crawler.utils import get_issn_codes

app = typer.Typer()


@app.command()
def list_releases(
    top_n: Annotated[
        int, typer.Option(help="Number of release names to show in descending order.")
    ] = 10,
):
    """Shows the latest top_n releases from the datasets"""
    available_releases = datasets.get_available_releases()
    logger.info(
        f"Latest {top_n} of {len(available_releases)} releases: {sorted(available_releases[-top_n:], reverse=True)}"
    )


@app.command()
def download_publication_venues(
    release: Annotated[
        str | None,
        typer.Option(
            help="Release version from Semantic Scholar with format 'YYYY-MM-DD'. It will use the latest release in case it is not provided."
        ),
    ] = None,
) -> None:
    """Downloads the publication venues of a given Semantic Scholar release"""
    available_releases = datasets.get_available_releases()
    release_id = release or available_releases[-1]

    assert (
        release_id in available_releases
    ), f"'{release_id}' must be a valid release id. i.e.: {[x for x in reversed(available_releases[-3:])]}"

    links_publication_venues = datasets.download_links(release_id, "publication-venues")
    output_path = datasets.download_dataset_from_semantic_scholar(
        url=links_publication_venues["files"][0],
        output_path=RAW_DATA_DIR
        / "semantic_scholar"
        / "release"
        / release_id
        / "publication_venues",
    )
    _ = datasets.read_publication_venues(file_path=output_path)


@app.command()
def download_paper_metadata(
    file_with_issn: Annotated[
        str,
        typer.Option(
            help="CSV file with ISSN codes of publication venues used to filter publications from those venues."
        ),
    ] = str(RAW_DATA_DIR / "journals.csv"),
    release: Annotated[
        str | None,
        typer.Option(
            help="Release version from Semantic Scholar with format 'YYYY-MM-DD'. The latest release is used in case no release is provided."
        ),
    ] = None,
    n_files: Annotated[
        int,
        typer.Option(
            help="Number of 1GB compressed files with metadata of papers to download. Zero means it will download all the ~60 files available per release."
        ),
    ] = 0,
    min_publication_date: Annotated[
        str,
        typer.Option(help="Minimum publiction date to search papers."),
    ] = "2024-01-01",
    max_publication_date: Annotated[
        str,
        typer.Option(help="Maximum publiction date to search papers."),
    ] = datetime.now().strftime("%Y-%m-%d"),
    min_citation_count: Annotated[
        int,
        typer.Option(help="Minimum citation count to select a paper."),
    ] = 0,
    overwrite: Annotated[
        bool,
        typer.Option(help="Whether or not to overwrite files already processed."),
    ] = False,
    persistent: Annotated[
        bool,
        typer.Option(
            help="Whether or not to keep original 1GB files of metadata after filtering papers."
        ),
    ] = False,
):
    """Download metadata of papers from Semantic Scholar.

    Workflow:

    1. Load publication venues for the selected release, reusing the local
    download if present. Match CSV ISSN values to Semantic Scholar venue IDs.

    2. Download or reuse paper dataset files. Keep records containing a
    matched venue ID, then filter by publication date and citation count.
    Papers without a publication date are excluded. Save results as CSVs.

    3. Use the matching papers' IDs to request metadata, including abstracts,
    from the Graph API in batches of up to 500. Save each batch as JSON.
    These responses come from the live API, not the selected dataset release.

    Download size: historically about 60 files per release, roughly 1 GB
    compressed each. Actual file counts and sizes vary by release.

    On repeat runs, existing CSVs bypass downloading and filtering, even if
    filter options change. API metadata is fetched again, overwriting JSON
    files with matching names regardless of --overwrite.

    Output (under the project root):
    data/raw/semantic_scholar/release/<release>/papers/ contains the filtered
    CSVs. JSON batches are saved beneath it as
    <archive-name-without-.gz>/json/papers-metadata-<batch>.json.

    The resulting metadata will contain the following fields: corpusId, url,
    title, abstract, venue, publicationVenue, year, citationCount, isOpenAccess,
    openAccessPdf, publicationDate, journal, fieldsOfStudy, s2FieldsOfStudy,
    authors, tldr, publicationTypes, textAvailability.

    See the available fields in the data section of the Response Schema here:
    https://api.semanticscholar.org/api-docs/graph#tag/Paper-Data/operation/get_graph_paper_bulk_search
    """

    # Set release_id
    available_releases = datasets.get_available_releases()
    release_id = release or available_releases[-1]
    assert (
        release_id in available_releases
    ), f"'{release_id}' must be a valid release id. i.e.: {[x for x in reversed(available_releases[-3:])]}"

    # Get publication venues from the release
    links_publication_venues = datasets.download_links(release_id, "publication-venues")
    output_path = datasets.download_dataset_from_semantic_scholar(
        url=links_publication_venues["files"][0],
        output_path=RAW_DATA_DIR
        / "semantic_scholar"
        / "release"
        / release_id
        / "publication_venues",
    )
    df_venues = datasets.read_publication_venues(file_path=output_path)

    # Get publication ids from ISSN code to filter publication venues
    issn = get_issn_codes(file_with_issn)
    publication_venue_ids = df_venues[df_venues["issn"].isin(issn)].id.unique()

    # Get the links to the metadata files of the papers
    links_papers = datasets.download_links(release_id=release_id, dataset_name="papers")
    search_params = PaperSearch(
        publication_venue_ids=publication_venue_ids,  # type: ignore
        min_publication_date=min_publication_date,
        max_publication_date=max_publication_date,
        min_citation_count=min_citation_count,
    )
    logger.info(f"{search_params}")

    # Downloads files with the actual metadata of the papers
    output_path_papers = RAW_DATA_DIR / "semantic_scholar" / "release" / release_id / "papers"
    for url in links_papers["files"][: len(links_papers) if n_files == 0 else n_files]:
        get_papers(
            url=url,
            output_path=output_path_papers,
            search_params=search_params,
            overwrite=overwrite,
            persistent=persistent,
        )
    logger.info("finished successfully")


@app.command()
def run_string_searches(
    release: Annotated[
        str | None,
        typer.Option(
            help="Release version from Semantic Scholar with format 'YYYY-MM-DD'. The string search will be applied on papers from the given release stored in `INTERIM_DATA_DIR/semantic_scholar/release/<YYY-MM-DD>/papers`. It will use the latest release in case it is not provided."
        ),
    ] = None,
    method: Annotated[
        Literal["sifts", "plain"],
        typer.Option(
            help="Search string with `sifts`, that implements search queries with SQLite FTS5 that handles special characters; or with `plain` that is an ad-hoc implementation that checks for the appearance of the keywords in the paper metadata, ignoring special characters. Defaults to `sifts`."
        ),
    ] = "sifts",
):
    """Execute all the string searches available in the `search_queries.py` module.
    The results (paper selection based on keyword searches) are saved to
    `INTERIM_DATA_DIR/semantic_scholar/release/<YYYY-MM-DD>/papers/<method>`.

    The workflow is as follows:
    1. Given a release, it searches the paper metadata downloaded based on
        publication venues, publication dates, and citation count.
    2. Using all the search queries defined in `search_queries.py` it applies
        one by one to each paper.
    3. Save the papers's metadata results to
        `INTERIM_DATA_DIR/semantic_scholar/release/<YYYY-MM-DD>/papers/<method>`
        by query, with file names such as: `Q1 - Forest - Trends.json`,
        `Q2 - Forest - Drivers.json`, `Q3 - Forest - Measures.json`,
        `Q4 - Forest - Ecosystem Services.json`, etc.

    Use `uv run kibad-crawler string-search-info` to get an overview of the queries.

    The search queries are composed by keywords and logical operators representing
    six Habitats: "Forest", "Soil", "Agricultural and Open Land", "Inland waters
    & Floodplains", and "Coasts & Coastal Waters"; and four Topic Areas:
    "Trends", "Drivers", "Measures", and "Ecosystem Services".

    For example, a search query to filter by trends in forest habitats in Germany would be:

    `("species richness" OR "species abundance") AND ("German*" OR "Lower Saxony") AND ("Forest*" OR "wood*") AND ("trend*" OR "decrease*" OR "gain*)`

    > Note: Search queries contain more extense than two words per concept.
    > Note: Queries are pre-loaded and cannot be modified by a user.

    Two methods to run the query searches. Defaults to `sifts`.
    - `sifts`: implements keywrod searches with SQLite FTS5 that handles special
        characters.
    - `plain`: that is an ad-hoc implementation that checks for the appearance
        of the keywords in the paper metadata, ignoring special characters.
    """
    release_id = release or datasets.get_available_releases()[-1]
    if method == "plain":
        execute_all_search_queries(release_id=release_id)
    elif method == "sifts":
        execute_all_search_queries_sift(release_id=release_id)


@app.command()
def string_search_info():
    """Show all string search queries available.

    The search queries are composed by keywords and logical operators representing
    the combination of six Habitats: "Forest", "Soil", "Agricultural and Open
    Land", "Inland waters & Floodplains", and "Coasts & Coastal Waters"; and
    four Topic Areas: "Trends", "Drivers", "Measures", and "Ecosystem Services".
    """

    logger.info(
        f"There are currently {len(ALL_SEARCH_QUERIES)} string search queries in the system."
    )
    for query in ALL_SEARCH_QUERIES:
        logger.info(f"Query: {query.id} - {query.name}")

    logger.info("")  # to generate a space between the query list and the detail

    for query in ALL_SEARCH_QUERIES:
        logger.info("=" * (len(query.name) + len(query.id) + 10))
        logger.info(f"Query: {query.id} - {query.name}")
        logger.info("=" * (len(query.name) + len(query.id) + 10))
        print_rich(
            f"{query.query.replace('OR', '[yellow]OR[/yellow]').replace('AND', '[red]\nAND\n[/red]').replace('(', '[yellow]([/yellow]').replace(')', '[yellow])[/yellow]')}"
        )


if __name__ == "__main__":
    app()
