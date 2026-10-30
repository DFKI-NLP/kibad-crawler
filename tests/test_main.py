from pathlib import Path

import pandas as pd
import pytest
from typer.testing import CliRunner

from kibad_crawler import main

runner = CliRunner()

RELEASES = ["2026-08-25", "2026-09-01", "2026-09-09"]


@pytest.fixture
def crawler(tmp_path: Path, monkeypatch):
    """Replace the calls to Semantic Scholar and the processing of the paper
    files in the main module, and return the calls to `get_papers_from_files`."""
    calls: dict[str, list] = {"publication_venue_ids": [], "get_papers_from_files": []}

    def fake_get_publication_venue_ids(release_id, file_with_issn):
        calls["publication_venue_ids"].append(release_id)
        return ["venue-1", "venue-2"]

    def no_api_call(**kwargs):
        raise RuntimeError("tests must not call the Semantic Scholar API")

    monkeypatch.setattr(main.datasets, "download_links", no_api_call)
    monkeypatch.setattr(main.datasets, "download_links_incremental_diffs", no_api_call)
    monkeypatch.setattr(main.datasets, "get_available_releases", lambda: RELEASES)
    monkeypatch.setattr(main, "get_publication_venue_ids", fake_get_publication_venue_ids)
    monkeypatch.setattr(
        main,
        "get_papers_from_files",
        lambda **kwargs: calls["get_papers_from_files"].append(kwargs),
    )
    monkeypatch.setattr(main, "RAW_DATA_DIR", tmp_path)
    return calls


def test_list_releases():
    pass


def test_download_publication_venues():
    pass


@pytest.mark.parametrize(
    "abstracts_args, with_abstracts",
    [([], True), (["--with-abstracts"], True), (["--no-with-abstracts"], False)],
)
def test_download_paper_metadata_abstracts(
    crawler, monkeypatch, abstracts_args: list, with_abstracts: bool
):
    monkeypatch.setattr(
        main.datasets,
        "download_links_by_file_name",
        lambda release_id, dataset_name: {
            "file-0.gz": "https://ai2-s2ag.s3.amazonaws.com/file-0.gz"
        },
    )

    result = runner.invoke(
        main.app,
        ["download-paper-metadata", "--release", "2026-09-01", *abstracts_args],
    )

    assert result.exit_code == 0, result.output
    # the abstracts are requested unless the option turns them off
    [call] = crawler["get_papers_from_files"]
    assert call["with_abstracts"] is with_abstracts


@pytest.mark.parametrize(
    "n_files_args, expected_files",
    [
        ([], ["file-0.gz", "file-1.gz", "file-2.gz"]),
        (["--n-files", "0"], ["file-0.gz", "file-1.gz", "file-2.gz"]),
        (["--n-files", "2"], ["file-0.gz", "file-1.gz"]),
    ],
)
def test_download_paper_metadata(
    tmp_path: Path, crawler, monkeypatch, n_files_args: list, expected_files: list
):
    links_requested: list[str] = []

    def fake_download_links_by_file_name(release_id, dataset_name):
        links_requested.append(release_id)
        return {
            f"file-{i}.gz": f"https://ai2-s2ag.s3.amazonaws.com/file-{i}.gz?Expires=123"
            for i in range(3)
        }

    monkeypatch.setattr(
        main.datasets, "download_links_by_file_name", fake_download_links_by_file_name
    )

    result = runner.invoke(
        main.app,
        ["download-paper-metadata", "--release", "2026-09-01", *n_files_args],
    )

    assert result.exit_code == 0, result.output
    assert crawler["publication_venue_ids"] == ["2026-09-01"]
    # --n-files 0 (default) means all the files of the release
    [call] = crawler["get_papers_from_files"]
    assert call["file_names"] == expected_files
    assert (
        call["output_path"] == tmp_path / "semantic_scholar" / "release" / "2026-09-01" / "papers"
    )
    assert call["search_params"].publication_venue_ids == ["venue-1", "venue-2"]
    # the link of a file is requested from the release when the file is needed
    assert call["get_url"]("file-1.gz") == (
        "https://ai2-s2ag.s3.amazonaws.com/file-1.gz?Expires=123"
    )


def test_download_paper_metadata_diff(tmp_path: Path, crawler, monkeypatch):
    diff_calls: list[tuple] = []

    def fake_download_links_incremental_diffs(dataset_name, end_release_id, start_release_id):
        diff_calls.append((dataset_name, start_release_id, end_release_id))
        return {
            "dataset": "papers",
            "start_release": "2026-08-25",
            "end_release": "2026-09-09",
            "diffs": [
                {
                    "from_release": "2026-08-25",
                    "to_release": "2026-09-01",
                    "update_files": ["https://ai2-s2ag.s3.amazonaws.com/update-0.gz"],
                    "delete_files": ["https://ai2-s2ag.s3.amazonaws.com/delete-0.gz"],
                },
                {
                    "from_release": "2026-09-01",
                    "to_release": "2026-09-09",
                    "update_files": [
                        "https://ai2-s2ag.s3.amazonaws.com/update-1.gz",
                        "https://ai2-s2ag.s3.amazonaws.com/update-2.gz",
                    ],
                    "delete_files": [],
                },
            ],
        }

    monkeypatch.setattr(
        main.datasets, "download_links_incremental_diffs", fake_download_links_incremental_diffs
    )

    result = runner.invoke(
        main.app,
        [
            "download-paper-metadata-diff",
            "--start-release",
            "2026-08-25",
            "--max-publication-date",
            "2026-09-11",
        ],
    )

    assert result.exit_code == 0, result.output
    # the latest release is used as end release and its publication venues are used to filter
    assert diff_calls == [("papers", "2026-08-25", "2026-09-09")]
    assert crawler["publication_venue_ids"] == ["2026-09-09"]

    # the update files of each diff are processed into their own folder
    release_path = tmp_path / "semantic_scholar" / "release"
    calls = crawler["get_papers_from_files"]
    assert [(call["file_names"], call["output_path"]) for call in calls] == [
        (
            ["update-0.gz"],
            release_path / "2026-09-01" / "diffs" / "2026-08-25_to_2026-09-01" / "papers",
        ),
        (
            ["update-1.gz", "update-2.gz"],
            release_path / "2026-09-09" / "diffs" / "2026-09-01_to_2026-09-09" / "papers",
        ),
    ]
    assert calls[0]["search_params"].max_publication_date == "2026-09-11"

    # the link of an update file is requested from the diff it belongs to
    assert calls[0]["get_url"]("update-0.gz") == "https://ai2-s2ag.s3.amazonaws.com/update-0.gz"
    assert calls[1]["get_url"]("update-2.gz") == "https://ai2-s2ag.s3.amazonaws.com/update-2.gz"


@pytest.mark.parametrize(
    "release_args",
    [
        ["--start-release", "2026-09-09"],
        ["--start-release", "2026-09-09", "--end-release", "2026-09-01"],
        ["--start-release", "2020-01-01"],
    ],
)
def test_download_paper_metadata_diff_invalid_releases(crawler, release_args: list):
    result = runner.invoke(main.app, ["download-paper-metadata-diff", *release_args])

    # the start release must be a valid release and older than the end release
    assert isinstance(result.exception, AssertionError)
    assert crawler["get_papers_from_files"] == []


def test_evaluate_search_queries(crawler, tmp_path, monkeypatch):
    papers = [{"paperId": "p-1", "title": "Forest", "abstract": "trend"}]
    json_dir = tmp_path / "semantic_scholar" / "release" / RELEASES[0] / "papers" / "f" / "json"
    json_dir.mkdir(parents=True)
    (json_dir / "papers-metadata-0.json").write_text(str(papers).replace("'", '"'))
    reference = {"paperId": ["p-1"], "included": [1], "publication_venue_id": ["venue-1"]}
    monkeypatch.setattr(main, "get_reference_papers", lambda habitat: pd.DataFrame(reference))
    monkeypatch.setattr(main, "PROJ_ROOT", tmp_path)
    # the real queries match no paper of this test
    monkeypatch.setattr(
        "kibad_crawler.evaluation.search_results.get_papers_from_search_with_sifts",
        lambda query, collection: ["p-1"],
    )
    monkeypatch.setenv("SLURM_TMPDIR", str(tmp_path))

    result = runner.invoke(main.app, ["evaluate-search-queries", "--release", RELEASES[0]])

    assert result.exit_code == 0, result.output
    report = (tmp_path / "evaluation" / "results" / "forest.md").read_text()
    assert "Release `2026-08-25`, 1 papers" in report
    assert "| in the publication venues |        1 |              1 |" in report
    assert "nan" not in report
