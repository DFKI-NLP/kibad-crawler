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
    """Replace `get_abstracts` and return the list of CSV files it was called with."""
    csv_paths = []
    monkeypatch.setattr(papers, "get_abstracts", lambda file_path: csv_paths.append(file_path))
    return csv_paths


def make_search_params(min_citation_count: int = 0) -> papers.PaperSearch:
    return papers.PaperSearch(
        publication_venue_ids=["venue-1", "venue-2"],
        min_publication_date="2024-01-01",
        max_publication_date="2026-09-11",
        min_citation_count=min_citation_count,
    )


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
    assert abstracts == [csv_path]


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
    assert abstracts == ([csv_path] if with_abstracts else [])


def test_get_abstracts(tmp_path: Path, monkeypatch):
    batches: list[list[str]] = []

    def fake_batch(ids):
        batches.append(ids)
        return [{"paperId": paper_id, "abstract": f"Abstract of {paper_id}"} for paper_id in ids]

    monkeypatch.setattr(academic_graph, "batch", fake_batch)
    monkeypatch.setattr(papers, "MAX_NUM_BATCH_PAPERS", 2)

    csv_path = tmp_path / "file-0.gz.csv"
    pd.DataFrame(
        {
            "corpusid": [1, 2, 3, 4, 5],
            "url": [f"https://www.semanticscholar.org/paper/paper-{i}" for i in range(1, 6)],
        }
    ).to_csv(csv_path, index=False)

    papers.get_abstracts(csv_path)

    # the paper ids are taken from the url and requested in batches
    assert batches == [["paper-1", "paper-2"], ["paper-3", "paper-4"], ["paper-5"]]

    # each batch is saved to a JSON file in a directory named after the CSV file
    json_path = tmp_path / "file-0" / "json"
    assert sorted(x.name for x in json_path.glob("*.json")) == [
        "papers-metadata-0.json",
        "papers-metadata-1.json",
        "papers-metadata-2.json",
    ]
    with open(json_path / "papers-metadata-2.json", encoding="utf-8") as f:
        assert json.load(f) == [{"paperId": "paper-5", "abstract": "Abstract of paper-5"}]
