from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Annotated

from loguru import logger
from rich import print as print_rich
import typer

from kibad_crawler.basic_filter import execute_all_search_queries_sift
from kibad_crawler.config import INTERIM_DATA_DIR, PROJ_ROOT, RAW_DATA_DIR
from kibad_crawler.evaluation.reference_papers import (
    SCREENING_TABLES,
    SCREENING_TABLES_DIR,
    get_reference_papers,
    read_screening_tables,
)
from kibad_crawler.evaluation.search_results import (
    build_collection,
    evaluate_queries,
    get_documents_of_crawl,
)
from kibad_crawler.papers import (
    PaperSearch,
    download_open_access_pdfs,
    get_papers,
    get_papers_from_files,
    get_publication_venue_ids,
)
from kibad_crawler.search_queries import ALL_SEARCH_QUERIES
from kibad_crawler.semantic_filter import SemanticFilter
from kibad_crawler.semantic_scholar import datasets
from kibad_crawler.utils import get_file_name

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
    with_abstracts: Annotated[
        bool,
        typer.Option(
            help="Whether or not to request the metadata with the abstracts from the Graph API, which takes most of the time of a run."
        ),
    ] = True,
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
    filter options change, and JSON batches that are already stored are not
    requested again. Use --overwrite to download them again, e.g. to update
    the citation counts of papers that are already stored.

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

    # Get publication venue ids from the ISSN codes to filter papers
    publication_venue_ids = get_publication_venue_ids(
        release_id=release_id, file_with_issn=file_with_issn
    )
    search_params = PaperSearch(
        publication_venue_ids=publication_venue_ids,
        min_publication_date=min_publication_date,
        max_publication_date=max_publication_date,
        min_citation_count=min_citation_count,
    )
    logger.info(f"{search_params}")

    # Get the names of the metadata files of the papers
    file_names = sorted(
        datasets.download_links_by_file_name(release_id=release_id, dataset_name="papers")
    )
    if n_files != 0:
        file_names = file_names[:n_files]

    def get_url(file_name: str) -> str:
        """Returns the current download link of a file of the release."""
        links = datasets.download_links_by_file_name(release_id=release_id, dataset_name="papers")
        return links[file_name]

    # Downloads files with the actual metadata of the papers
    get_papers_from_files(
        file_names=file_names,
        get_url=get_url,
        output_path=RAW_DATA_DIR / "semantic_scholar" / "release" / release_id / "papers",
        search_params=search_params,
        overwrite=overwrite,
        persistent=persistent,
        with_abstracts=with_abstracts,
    )
    logger.info("finished successfully")


@app.command()
def download_paper_metadata_diff(
    start_release: Annotated[
        str,
        typer.Option(
            help="Release version from Semantic Scholar with format 'YYYY-MM-DD' that is already downloaded, e.g. with download-paper-metadata."
        ),
    ],
    end_release: Annotated[
        str | None,
        typer.Option(
            help="Release version from Semantic Scholar with format 'YYYY-MM-DD' to update to. The latest release is used in case no release is provided."
        ),
    ] = None,
    file_with_issn: Annotated[
        str,
        typer.Option(
            help="CSV file with ISSN codes of publication venues used to filter publications from those venues."
        ),
    ] = str(RAW_DATA_DIR / "journals.csv"),
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
            help="Whether or not to keep original files of metadata after filtering papers."
        ),
    ] = False,
    with_abstracts: Annotated[
        bool,
        typer.Option(
            help="Whether or not to request the metadata with the abstracts from the Graph API, which takes most of the time of a run."
        ),
    ] = True,
):
    """Download metadata of the papers that changed between two releases.

    Instead of processing all the files of a new release again, this uses the
    incremental diffs from Semantic Scholar. Each diff covers two consecutive
    releases and contains update files (new or changed papers) and delete
    files (removed papers).

    Workflow:

    1. Get the diffs between --start-release and --end-release.

    2. Load publication venues of the end release and match CSV ISSN values
    to Semantic Scholar venue IDs.

    3. Filter the update files of each diff the same way as
    download-paper-metadata (venue, publication date and citation count) and
    request the metadata, including abstracts, of the matching papers.

    Delete files are only reported, they are not applied. Changed papers that
    were already downloaded with the full release are saved again.

    Output (under the project root), one folder per diff:
    data/raw/semantic_scholar/release/<to_release>/diffs/<from_release>_to_<to_release>/papers/
    with the same structure as the output of download-paper-metadata.
    """

    # Set start and end release
    available_releases = datasets.get_available_releases()
    end_release_id = end_release or available_releases[-1]
    for release_id in [start_release, end_release_id]:
        assert (
            release_id in available_releases
        ), f"'{release_id}' must be a valid release id. i.e.: {[x for x in reversed(available_releases[-3:])]}"
    assert (
        start_release < end_release_id
    ), f"--start-release '{start_release}' must be older than --end-release '{end_release_id}'"

    # Get the links to the diff files between both releases
    diff_list = datasets.download_links_incremental_diffs(
        dataset_name="papers", end_release_id=end_release_id, start_release_id=start_release
    )
    logger.info(f"{len(diff_list['diffs'])} diffs from '{start_release}' to '{end_release_id}'")

    # Get publication venue ids from the ISSN codes to filter papers
    publication_venue_ids = get_publication_venue_ids(
        release_id=end_release_id, file_with_issn=file_with_issn
    )
    search_params = PaperSearch(
        publication_venue_ids=publication_venue_ids,
        min_publication_date=min_publication_date,
        max_publication_date=max_publication_date,
        min_citation_count=min_citation_count,
    )
    logger.info(f"{search_params}")

    # Downloads the update files of each diff into its own folder
    def get_url_of_update_file(from_release: str, to_release: str, file_name: str) -> str:
        """Returns the current download link of an update file of a diff."""
        diffs = datasets.download_links_incremental_diffs(
            dataset_name="papers", end_release_id=end_release_id, start_release_id=start_release
        )["diffs"]
        for diff in diffs:
            if (diff["from_release"], diff["to_release"]) == (from_release, to_release):
                return {get_file_name(url): url for url in diff["update_files"]}[file_name]
        raise KeyError(f"no diff from '{from_release}' to '{to_release}'")

    for diff in diff_list["diffs"]:
        from_release, to_release = diff["from_release"], diff["to_release"]
        logger.info(
            f"diff '{from_release}' to '{to_release}': {len(diff['update_files'])} update files, "
            f"{len(diff['delete_files'])} delete files (not applied)"
        )
        get_papers_from_files(
            file_names=sorted(get_file_name(url) for url in diff["update_files"]),
            get_url=partial(get_url_of_update_file, from_release, to_release),
            output_path=RAW_DATA_DIR
            / "semantic_scholar"
            / "release"
            / to_release
            / "diffs"
            / f"{from_release}_to_{to_release}"
            / "papers",
            search_params=search_params,
            overwrite=overwrite,
            persistent=persistent,
            with_abstracts=with_abstracts,
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
    release_diff: Annotated[
        str | None,
        typer.Option(help="Start release of a downloaded diff to search (YYYY-MM-DD)."),
    ] = None,
):
    """
    Select papers based on keyword search. This filters a Semantic Scholar release
    by executing all the string searches available in the `search_queries.py` module.
    The results (paper selection based on keyword searches) are saved to
    `INTERIM_DATA_DIR/semantic_scholar/release/<YYYY-MM-DD>/papers/sifts`.

    Pass --release-diff with the start release of a downloaded diff to search
    its new and changed papers with sifts. --release identifies the end release.

    The workflow is as follows:
    1. Given a release, it searches the paper metadata downloaded based on
        publication venues, publication dates, and citation count.
    2. Using all the search queries defined in `search_queries.py` it applies
        one by one to each paper.
    3. Save the papers's metadata results to
        `INTERIM_DATA_DIR/semantic_scholar/release/<YYYY-MM-DD>/papers/sifts`
        by query, with file names such as: `Q1 - Forest - Trends.json`,
        `Q2 - Forest - Drivers.json`, `Q3 - Forest - Measures.json`,
        `Q4 - Forest - Ecosystem Services.json`, etc.

    Use `uv run kibad-crawler string-search-info` to get an overview of the queries.
    """
    release_id = release or datasets.get_available_releases()[-1]
    execute_all_search_queries_sift(release_id=release_id, release_diff=release_diff)


@app.command()
def string_search_info():
    """Show all string search queries available.

    The search queries are composed by keywords and logical operators representing
    the combination of six Habitats: "Forest", "Soil", "Agricultural and Open
    Land", "Inland waters & Floodplains", and "Coasts & Coastal Waters"; and
    four Topic Areas: "Trends", "Drivers", "Measures", and "Ecosystem Services".

    For example, a search query to filter by trends in forest habitats in Germany would be:

    `("species richness" OR "species abundance") AND ("German*" OR "Lower Saxony") AND ("Forest*" OR "wood*") AND ("trend*" OR "decrease*" OR "gain*)`

    > Note: Real search queries extend beyond two words per concept.
    > Note: Queries are pre-loaded and cannot be modified by a user.
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


@app.command()
def download_open_access_files(
    input_path: Annotated[
        Path,
        typer.Argument(
            help="Directory containing JSON files with Semantic Scholar paper metadata."
        ),
    ],
):
    """Download open-access PDFs for the papers listed in a metadata directory.

    Run download-paper-metadata and then run-string-searches to select papers
    by title and abstract. Pass the search-results directory to this command.
    Other Semantic Scholar metadata directories with paper IDs and open-access
    PDF URLs can also be used.

    PDFs are saved in the open_access_pdf subdirectory of the input directory.
    """
    logger.info(f"Searching for paper metadata in '{input_path}'")
    download_open_access_pdfs(input_path=input_path)


if __name__ == "__main__":
    app()


@app.command()
def evaluate_search_queries(
    release: Annotated[
        str,
        typer.Option(
            help="Release version from Semantic Scholar with format 'YYYY-MM-DD' that is already downloaded with download-paper-metadata."
        ),
    ],
    file_with_issn: Annotated[
        str,
        typer.Option(help="CSV file with the ISSN codes the release was downloaded with."),
    ] = str(RAW_DATA_DIR / "journals.csv"),
    max_publication_date: Annotated[
        str | None,
        typer.Option(
            help="Leave out the papers published after this date, with format 'YYYY-MM-DD'. Papers without a publication date are kept."
        ),
    ] = None,
):
    """Compare the search queries with the screening tables of the literature review.

    Workflow:

    1. Load the papers of the release with their title and abstract into a
    `sifts` database.

    2. For each literature search with screening tables, resolve the DOIs of
    the tables to Semantic Scholar paper ids and publication venue ids. The
    result is stored next to the tables in `data/external/screening_tables/`,
    so the API is only called once per search.

    3. Restrict the reference papers to the publication venues of
    --file-with-issn and run the queries that replicate the search.

    Output (under the project root): `evaluation/results/<search>.md` with how
    many reference papers are in the crawl and, per query, how many of them it
    returns and how they were screened.
    """
    documents = get_documents_of_crawl(
        papers_path=RAW_DATA_DIR / "semantic_scholar" / "release" / release / "papers",
        max_publication_date=max_publication_date,
    )
    crawled_ids = {paper_id for paper_id, _ in documents}
    collection = build_collection(documents, name=f"{release}_until_{max_publication_date}")
    venue_ids = set(get_publication_venue_ids(release_id=release, file_with_issn=file_with_issn))

    results_dir = PROJ_ROOT / "evaluation" / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    for tables in SCREENING_TABLES:
        df_coverage, df_queries = evaluate_queries(
            queries=[query for query in ALL_SEARCH_QUERIES if query.id in tables.query_ids],
            collection=collection,
            crawled_ids=crawled_ids,
            df_reference=get_reference_papers(tables),
            venue_ids=venue_ids,
        )
        output_path = results_dir / f"{tables.name}.md"
        output_path.write_text(
            f"# {tables.name}\n\n"
            f"Screening tables: {', '.join(f'`{name}`' for name in tables.file_names)}.\n\n"
            f"Release `{release}`, {len(crawled_ids):,} papers, publication venues of "
            f"`{Path(file_with_issn).name}`, papers published until {max_publication_date or 'the release'}.\n\n"
            f"## Reference papers in the crawl\n\n{df_coverage.to_markdown(index=False)}\n\n"
            f"## Reference papers of the publication venues returned by the queries\n\n"
            f"{df_queries.fillna('').to_markdown(index=False)}\n",
            encoding="utf-8",
        )
        logger.info(f"results of {tables.name} saved to '{output_path}'")


@app.command()
def cross_validate_semantic_filter(
    table: Annotated[
        str,
        typer.Option(
            help="Name of the screening tables in `SCREENING_TABLES`, e.g. 'ecosystem_services_habitats'."
        ),
    ],
    n_splits: Annotated[int, typer.Option(help="Number of random 80:20 splits.")] = 5,
):
    """Train and evaluate the semantic filter on the screened papers of one
    screening table.

    Workflow:

    1. Read the papers of the table that have a DOI and a screening decision.

    2. Request their SPECTER2 embeddings from the Academic Graph API, reusing
    the ones in `data/interim/semantic_filter/embeddings.json`.

    3. For each of --n-splits random splits, estimate the hyperparameters on 80
    per cent of the papers and evaluate on the other 20 per cent.

    Output (under the project root): the filter of each split in
    `data/interim/semantic_filter/<table>/`, and the mean and standard deviation of
    the metrics in `evaluation/results/semantic_filter_<table>.md`.
    Coverage is the percentage of test papers with an embedding.
    """
    tables = next(tables for tables in SCREENING_TABLES if tables.name == table)
    df = read_screening_tables(SCREENING_TABLES_DIR, tables)
    df = df[df["included"].notna()].drop_duplicates(subset=["doi"])
    dois, labels = df["doi"].tolist(), (df["included"] == 1).tolist()
    logger.info(f"{len(dois):,} screened papers, {sum(labels):,} of them relevant")

    results = SemanticFilter.cross_validation(
        dois, labels, model_dir=INTERIM_DATA_DIR / "semantic_filter" / table, n_splits=n_splits
    )
    rows = "\n".join(
        (
            f"| {name} | {mean:.3%} | {std:.3%} |"
            if name == "coverage"
            else f"| {name} | {mean:.3f} | {std:.3f} |"
        )
        for name, (mean, std) in results.items()
    )
    output_path = PROJ_ROOT / "evaluation" / "results" / f"semantic_filter_{table}.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        f"# Semantic filter: {table}\n\n"
        f"{len(dois):,} screened papers, {sum(labels):,} of them relevant, "
        f"{n_splits} random 80:20 splits.\n\n"
        f"| metric | mean | standard deviation |\n|---|---|---|\n{rows}\n",
        encoding="utf-8",
    )
    logger.info(f"results saved to '{output_path}'")
