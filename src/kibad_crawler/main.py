from datetime import datetime
from typing import Annotated

from loguru import logger
import typer

from kibad_crawler.config import RAW_DATA_DIR
from kibad_crawler.papers import (
    PaperSearch,
    get_papers_from_files,
    get_publication_venue_ids,
)
from kibad_crawler.semantic_scholar import datasets

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

    # Get the links to the metadata files of the papers
    links_papers = datasets.download_links(release_id=release_id, dataset_name="papers")
    urls = links_papers["files"] if n_files == 0 else links_papers["files"][:n_files]

    # Downloads files with the actual metadata of the papers
    get_papers_from_files(
        urls=urls,
        output_path=RAW_DATA_DIR / "semantic_scholar" / "release" / release_id / "papers",
        search_params=search_params,
        overwrite=overwrite,
        persistent=persistent,
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
    for diff in diff_list["diffs"]:
        from_release, to_release = diff["from_release"], diff["to_release"]
        logger.info(
            f"diff '{from_release}' to '{to_release}': {len(diff['update_files'])} update files, "
            f"{len(diff['delete_files'])} delete files (not applied)"
        )
        get_papers_from_files(
            urls=diff["update_files"],
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
        )
    logger.info("finished successfully")


if __name__ == "__main__":
    app()
