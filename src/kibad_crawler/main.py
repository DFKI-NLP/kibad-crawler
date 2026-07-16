from pathlib import Path
from typing import Annotated

from loguru import logger
import typer

from kibad_crawler import s2_api
from kibad_crawler.crawler import download_open_access_pdfs

app = typer.Typer()


@app.command()
def download_publication_venues(
    release: Annotated[
        str | None,
        typer.Option(
            help="Release version from Semantic Scholar with format 'YYYY-MM-DD'. It will use the latest release in case it is not provided."
        ),
    ] = None,
    storage_path: Annotated[
        str | None,
        typer.Option(
            help="Absolute or relative path to store data from Semantic Scholar. Publication venues will be stored in 'storage_path/release/YYYY-MM-DD/publication_venues'. It will use the './data/raw/' folder in the root folder of the repository if not provided."
        ),
    ] = None,
):
    """Downloads the publication venues of a given Semantic Scholar release"""
    s2_client = s2_api.S2Client(storage_path=storage_path)
    release = release or s2_client.latest_release
    _ = s2_client.get_publication_venues(release_id=release)


@app.command()
def list_releases(
    top_n: Annotated[
        int, typer.Option(help="Number of release names to show in descending order.")
    ] = 10,
):
    """Shows the latest top_n releases from the datasets"""
    s2_client = s2_api.S2Client()
    logger.info(
        f"Latest {top_n} of {len(s2_client.releases)} releases: {sorted(s2_client.releases[-top_n:], reverse=True)}"
    )


@app.command()
def download_papers(
    file_with_issn: Annotated[
        str | None,
        typer.Option(
            help="CSV file with ISSN codes of publication venues used to filter publications from those venues. It will search it in './data/raw/Journals.csv' if it is not provided."
        ),
    ] = None,
    release: Annotated[
        str | None,
        typer.Option(
            help="Release version from Semantic Scholar with format 'YYYY-MM-DD'. The latest release is used in case no release is provided."
        ),
    ] = None,
    n_pages: Annotated[
        int,
        typer.Option(
            help="Number of 1GB compressed files with metadata of papers to download. Zero means it will download all the ~60 files available per release."
        ),
    ] = 0,
    storage_path: Annotated[
        str | None,
        typer.Option(
            help="Absolute or relative path to store data from Semantic Scholar. Publication venues will be stored in 'storage_path/release/YYYY-MM-DD/publication_venues'. It will use the './data/raw/' folder in the root folder of the repository if not provided."
        ),
    ] = None,
    download_open_access: Annotated[
        bool,
        typer.Option(
            help="Whether or not to download the PDF files of the available open access URLs. The PDF files will be stored in the 'storage_path'."
        ),
    ] = False,
):
    """Download papers from Semantic Scholar"""
    if file_with_issn:
        assert Path(file_with_issn).exists()

    # initialization of the client
    s2_client = s2_api.S2Client(storage_path=storage_path)
    release = release or s2_client.latest_release

    # publication venues dataset
    df_venues = s2_client.get_publication_venues(release_id=release)
    if file_with_issn:
        publication_venue_ids = s2_api.get_publication_venue_id_from_issn_codes(
            file_path=file_with_issn,
            df_venues=df_venues,
        )

        # download paper information from Semantic Scholar
        release_path = s2_client._download_all_papers(
            publication_venue_ids=publication_venue_ids, n_pages=n_pages, persistent_storage=True
        )

        # download papers metadata
        s2_client.download_paper_metadata(path=release_path)

        # download open access PDFs
        if download_open_access:
            df_pdfs = s2_client.get_open_access_urls(path=release_path)
            download_open_access_pdfs(df_pdfs=df_pdfs, path=release_path)


if __name__ == "__main__":
    app()
