import gzip
import json
from pathlib import Path

import pandas as pd
import pytest

from kibad_crawler import papers
from kibad_crawler.semantic_scholar import academic_graph

FILE_URL = "https://ai2-s2ag.s3.amazonaws.com/staging/2026-09-01/papers/file-0.gz?AWSAccessKeyId=abc&Expires=123"

# lines of a paper dataset file with the structure of the Semantic Scholar `papers` dataset
PAPERS_DATASET = [
    # from a selected venue, inside the date range, with citations
    {
        "corpusid": 1,
        "url": "https://www.semanticscholar.org/paper/paper-1",
        "title": "Paper 1",
        "publicationvenueid": "venue-1",
        "publicationdate": "2024-03-01",
        "citationcount": 5,
    },
    # from another selected venue, inside the date range, without citations
    {
        "corpusid": 2,
        "url": "https://www.semanticscholar.org/paper/paper-2",
        "title": "Paper 2",
        "publicationvenueid": "venue-2",
        "publicationdate": "2026-09-11",
        "citationcount": 0,
    },
    # from a selected venue, before the minimum publication date
    {
        "corpusid": 3,
        "url": "https://www.semanticscholar.org/paper/paper-3",
        "title": "Paper 3",
        "publicationvenueid": "venue-1",
        "publicationdate": "2023-12-31",
        "citationcount": 10,
    },
    # from a selected venue, after the maximum publication date
    {
        "corpusid": 4,
        "url": "https://www.semanticscholar.org/paper/paper-4",
        "title": "Paper 4",
        "publicationvenueid": "venue-1",
        "publicationdate": "2026-09-12",
        "citationcount": 10,
    },
    # from a selected venue, without publication date
    {
        "corpusid": 5,
        "url": "https://www.semanticscholar.org/paper/paper-5",
        "title": "Paper 5",
        "publicationvenueid": "venue-1",
        "publicationdate": None,
        "citationcount": 10,
    },
    # from a venue that is not selected
    {
        "corpusid": 6,
        "url": "https://www.semanticscholar.org/paper/paper-6",
        "title": "Paper 6",
        "publicationvenueid": "venue-3",
        "publicationdate": "2025-01-01",
        "citationcount": 10,
    },
]


@pytest.fixture
def downloads(monkeypatch):
    """Replace the download of the paper dataset file with a local file and
    return the list of calls."""
    calls = []

    def fake_download_dataset_from_semantic_scholar(url, output_path, overwrite):
        calls.append({"url": url, "output_path": output_path, "overwrite": overwrite})
        output_path.mkdir(parents=True, exist_ok=True)
        file_path = output_path / "file-0.gz"
        with gzip.open(file_path, "wt") as f:
            f.write("\n".join(json.dumps(paper) for paper in PAPERS_DATASET))
        return file_path

    monkeypatch.setattr(
        papers.datasets,
        "download_dataset_from_semantic_scholar",
        fake_download_dataset_from_semantic_scholar,
    )
    return calls


@pytest.fixture
def abstracts(monkeypatch):
    """Replace `get_abstracts` and return the list of calls it got."""
    calls = []
    monkeypatch.setattr(papers, "get_abstracts", lambda **kwargs: calls.append(kwargs))
    return calls


@pytest.fixture
def batch_requests(monkeypatch) -> list[list[str]]:
    """Replace the batch call to the Academic Graph API and return the list of
    requested paper ids."""
    requests: list[list[str]] = []

    def fake_batch(ids):
        requests.append(ids)
        return [{"paperId": paper_id, "abstract": f"Abstract of {paper_id}"} for paper_id in ids]

    monkeypatch.setattr(academic_graph, "batch", fake_batch)
    return requests


def make_papers_csv(csv_path: Path, n_papers: int = 5):
    """Save a CSV file with papers as it is written by `get_papers`."""
    pd.DataFrame(
        {
            "corpusid": list(range(1, n_papers + 1)),
            "url": [
                f"https://www.semanticscholar.org/paper/paper-{i}" for i in range(1, n_papers + 1)
            ],
        }
    ).to_csv(csv_path, index=False)


def make_search_params(min_citation_count: int = 0) -> papers.PaperSearch:
    return papers.PaperSearch(
        publication_venue_ids=["venue-1", "venue-2"],
        min_publication_date="2024-01-01",
        max_publication_date="2026-09-11",
        min_citation_count=min_citation_count,
    )


def test_get_publication_venue_ids(tmp_path: Path, monkeypatch):
    venues_url = (
        "https://ai2-s2ag.s3.amazonaws.com/staging/2026-09-01/publication-venues/venues-0.gz"
    )
    download_calls: list[dict] = []

    def fake_download_dataset_from_semantic_scholar(url, output_path):
        download_calls.append({"url": url, "output_path": output_path})
        file_path = tmp_path / "venues-0.gz"
        venues = [
            {"id": "venue-1", "name": "Forests", "issn": "1999-4907"},
            {"id": "venue-2", "name": "PLOS ONE", "issn": "1932-6203"},
            {"id": "venue-3", "name": "Other Journal", "issn": "0000-0000"},
            {"id": "venue-4", "name": "Journal without ISSN", "issn": None},
        ]
        with gzip.open(file_path, "wt") as f:
            f.write("\n".join(json.dumps(venue) for venue in venues))
        return file_path

    monkeypatch.setattr(
        papers.datasets,
        "download_links",
        lambda release_id, dataset_name: {"files": [venues_url]},
    )
    monkeypatch.setattr(
        papers.datasets,
        "download_dataset_from_semantic_scholar",
        fake_download_dataset_from_semantic_scholar,
    )
    csv_path = tmp_path / "journals.csv"
    csv_path.write_text(
        "Journal,Online ISSN,Print ISSN\nForests,1999-4907,\nPLOS ONE,,1932-6203\n"
    )

    publication_venue_ids = papers.get_publication_venue_ids(
        release_id="2026-09-01", file_with_issn=csv_path
    )

    assert sorted(publication_venue_ids) == ["venue-1", "venue-2"]
    # the publication venues are stored with the release they belong to
    assert download_calls == [
        {
            "url": venues_url,
            "output_path": papers.RAW_DATA_DIR
            / "semantic_scholar"
            / "release"
            / "2026-09-01"
            / "publication_venues",
        }
    ]


def test_get_papers_from_files(tmp_path: Path, monkeypatch):
    calls = []
    monkeypatch.setattr(papers, "get_papers", lambda **kwargs: calls.append(kwargs))
    search_params = make_search_params()
    urls = [FILE_URL, FILE_URL.replace("file-0", "file-1")]

    papers.get_papers_from_files(
        urls=urls, output_path=tmp_path, search_params=search_params, persistent=True
    )

    # each file is processed with the same output path and search parameters
    assert calls == [
        {
            "url": url,
            "output_path": tmp_path,
            "search_params": search_params,
            "overwrite": False,
            "persistent": True,
        }
        for url in urls
    ]


@pytest.mark.parametrize(
    "min_citation_count, expected_corpus_ids",
    [
        (0, [1, 2]),
        (1, [1]),
    ],
)
def test_get_papers(
    tmp_path: Path, downloads, abstracts, min_citation_count: int, expected_corpus_ids: list
):
    papers.get_papers(
        url=FILE_URL,
        output_path=tmp_path,
        search_params=make_search_params(min_citation_count=min_citation_count),
        overwrite=True,
    )

    # papers are filtered by venue, publication date and citation count
    csv_path = tmp_path / "file-0.gz.csv"
    df_papers = pd.read_csv(csv_path)
    assert df_papers["corpusid"].to_list() == expected_corpus_ids

    assert downloads == [{"url": FILE_URL, "output_path": tmp_path, "overwrite": True}]
    # the dataset file is removed after filtering and the abstracts are downloaded
    assert not (tmp_path / "file-0.gz").exists()
    assert abstracts == [{"file_path": csv_path, "overwrite": True}]


def test_get_papers_persistent(tmp_path: Path, downloads, abstracts):
    papers.get_papers(
        url=FILE_URL,
        output_path=tmp_path,
        search_params=make_search_params(),
        persistent=True,
        with_abstracts=False,
    )

    assert (tmp_path / "file-0.gz").exists()
    assert (tmp_path / "file-0.gz.csv").exists()
    assert abstracts == []


@pytest.mark.parametrize("with_abstracts", [True, False])
def test_get_papers_existing_csv(tmp_path: Path, downloads, abstracts, with_abstracts: bool):
    csv_path = tmp_path / "file-0.gz.csv"
    csv_path.write_text("corpusid,url\n1,https://www.semanticscholar.org/paper/paper-1\n")

    papers.get_papers(
        url=FILE_URL,
        output_path=tmp_path,
        search_params=make_search_params(),
        with_abstracts=with_abstracts,
    )

    # the file is not downloaded again, only the abstracts are downloaded
    assert downloads == []
    assert abstracts == ([{"file_path": csv_path, "overwrite": False}] if with_abstracts else [])


def test_get_papers_no_matching_papers(tmp_path: Path, downloads, monkeypatch):
    batches: list[list[str]] = []
    monkeypatch.setattr(academic_graph, "batch", lambda ids: batches.append(ids))

    # none of the papers in the file is from this venue
    papers.get_papers(
        url=FILE_URL,
        output_path=tmp_path,
        search_params=papers.PaperSearch(
            publication_venue_ids=["venue-9"], max_publication_date="2026-09-11"
        ),
    )

    # an empty CSV is saved, so the file is skipped in the next run, and no abstracts are requested
    df_papers = pd.read_csv(tmp_path / "file-0.gz.csv")
    assert df_papers.empty
    assert batches == []
    assert list((tmp_path / "file-0" / "json").glob("*.json")) == []


def test_get_abstracts(tmp_path: Path, monkeypatch, batch_requests):
    monkeypatch.setattr(papers, "MAX_NUM_BATCH_PAPERS", 2)
    csv_path = tmp_path / "file-0.gz.csv"
    make_papers_csv(csv_path)

    papers.get_abstracts(file_path=csv_path)

    # the paper ids are taken from the url and requested in batches
    assert batch_requests == [["paper-1", "paper-2"], ["paper-3", "paper-4"], ["paper-5"]]

    # each batch is saved to a JSON file in a directory named after the CSV file
    json_path = tmp_path / "file-0" / "json"
    assert sorted(x.name for x in json_path.iterdir()) == [
        "papers-metadata-0.json",
        "papers-metadata-1.json",
        "papers-metadata-2.json",
    ]
    with open(json_path / "papers-metadata-2.json", encoding="utf-8") as f:
        assert json.load(f) == [{"paperId": "paper-5", "abstract": "Abstract of paper-5"}]


@pytest.mark.parametrize("overwrite", [False, True])
def test_get_abstracts_with_existing_batches(
    tmp_path: Path, monkeypatch, batch_requests, overwrite: bool
):
    monkeypatch.setattr(papers, "MAX_NUM_BATCH_PAPERS", 2)
    csv_path = tmp_path / "file-0.gz.csv"
    make_papers_csv(csv_path)
    json_path = tmp_path / "file-0" / "json"
    json_path.mkdir(parents=True)
    (json_path / "papers-metadata-0.json").write_text('[{"paperId": "from a previous run"}]')

    papers.get_abstracts(file_path=csv_path, overwrite=overwrite)

    # the batches that are already stored are only downloaded again with overwrite
    if overwrite:
        assert batch_requests == [["paper-1", "paper-2"], ["paper-3", "paper-4"], ["paper-5"]]
    else:
        assert batch_requests == [["paper-3", "paper-4"], ["paper-5"]]

    with open(json_path / "papers-metadata-0.json", encoding="utf-8") as f:
        papers_of_first_batch = json.load(f)
    assert papers_of_first_batch[0]["paperId"] == (
        "paper-1" if overwrite else "from a previous run"
    )

    # the JSON files are written through a temporary file that is renamed
    assert list(json_path.glob("*.tmp")) == []
