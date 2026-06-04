from pathlib import Path

import typer

from kibad_crawler import s2_api

app = typer.Typer()


@app.command()
def download_publication_venues(release: str | None = None):
    """Downloads the publication venues of a given Semantic Scholar release"""
    s2_client = s2_api.S2Client()
    release = release or s2_client.latest_release
    _ = s2_client.get_publication_venues(release_id=release)


@app.command()
def download_papers_metadata(file_with_issn: str, release: str | None = None, n_pages: int = 0):
    """Download papers from Semantic Scholar"""
    assert Path(file_with_issn).exists()

    # initialization of the client
    s2_client = s2_api.S2Client()
    release = release or s2_client.latest_release

    # publication venues dataset
    df_venues = s2_client.get_publication_venues(release_id=release)
    publication_venue_ids = s2_api.get_publication_venue_id_from_issn_codes(
        file_path=file_with_issn,
        df_venues=df_venues,
    )

    # download paper information from Semantic Scholar
    release_path = s2_client._download_all_papers(
        publication_venue_ids=publication_venue_ids, n_pages=n_pages, persistant=True
    )


if __name__ == "__main__":
    app()
