# Semantic Scholar client and new features

This document describes the changes made to the kibad-crawler Semantic Scholar integration: the new class-based client, incremental diffs, recommendations, logging, dataclasses, and the relevance filter. It is written for humans reading or maintaining the code.

______________________________________________________________________

## Why a class-based client?

Previously, the code used standalone functions (e.g. `download_dataset`, `download_bulk_paper`) that all relied on a global API key. To add new features (diffs, recommendations) and keep the code testable, we introduced a single **`S2Client`** that holds the API key and timeouts and exposes everything as methods. Existing code (including the notebook) still works: the old functions remain and simply call the default client under the hood. So you can either use `S2Client()` for new code or keep using `s2_api.download_dataset(...)` as before.

______________________________________________________________________

## What the client does

- **Full datasets** — Download a full release dataset (e.g. `publication-venues`, `papers`) by release date. Same behaviour as before, now as `client.download_dataset(release_id, dataset_name)`.
- **File download** — Download a single file from a URL to a directory; used internally for dataset chunks and diff files.
- **Paper batches** — Filter large paper dataset files by venue and date, then save filtered rows as CSV. Used to get paper IDs for the bulk API.
- **Bulk paper metadata** — Request detailed metadata for up to 500 paper IDs at once (Graph API). Used after you have a list of IDs from the dataset pipeline.
- **Releases** — Fetch the list of all release IDs (dates). Useful to pick “latest” or “last two” for diffs.
- **Incremental diffs** — Get the list of *changed* files between two releases instead of re-downloading everything. We also support downloading those diff files into a fixed subfolder and a helper that automatically uses the last two releases.
- **Recommendations** — Ask Semantic Scholar for papers similar to a given paper ID. Returns a structured list you can use for discovery or filtering.
- **Relevance filter** — After you have a list of papers (e.g. from the bulk API), you can filter them by citation count, venue whitelist, fields of study, and keywords. All criteria are optional; together they form the “additional input” for selecting relevant papers.

______________________________________________________________________

## Incremental diffs (what and where)

Semantic Scholar publishes *releases* (e.g. `2026-01-27`, `2026-02-03`). Each release is a full snapshot. The **incremental diff** API tells you only which files *changed* between two releases, so you can download just those instead of re-downloading hundreds of GB.

- **`get_diff(from_release, to_release, dataset_name)`** — Returns the raw API response (JSON with download links).
- **`get_diff_parsed(...)`** — Same call but returns a **`DiffResponse`** dataclass (with `diffs` as a list of `DiffEntry`, each containing `update_files` and `deleted_files`).
- **`download_diff_files(from_release, to_release, dataset_name, base_path=None)`** — Calls the diff API, then downloads every update/delete file into a **subfolder** so you always know which diff you have:
    - `base_path / to_release / diffs / {from_release}_to_{to_release} / {dataset_name}`
    - Example: `data/raw/semantic_scholar/release/2026-02-03/diffs/2026-01-27_to_2026-02-03/papers/`
- **`download_last_two_releases_diff(dataset_name="papers", base_path=None)`** — Fetches the list of releases, takes the latest two, and runs `download_diff_files` for them. No need to look up release dates yourself.

______________________________________________________________________

## Recommendations API

We use the **paper-based** recommendation endpoint: “given this paper ID, what else is similar?”. Useful for expanding a reading list or finding related work.

- **`get_recommendations_for_paper(paper_id, limit=10)`** — Returns a **`RecommendationsResponse`** with a `.recommendations` list (each item is a paper-like dict). The API may cap the number of results regardless of `limit`. We do not currently call the list-based (user/topic) recommendation endpoint; that could be added later if needed.

______________________________________________________________________

## Logging

All client methods that call the API or write files use **loguru** (or standard `logging` if loguru is not installed). We log at **debug** for URLs and small details, **info** for completed downloads and important steps, **warning** when something is skipped or missing (e.g. no diffs, fewer than two releases), and **error** when a download fails. This makes it easier to see what the crawler did without printing everything. Log level can be configured via your logging setup (e.g. environment or loguru configuration).

______________________________________________________________________

## Dataclasses (`s2_models.py`)

We moved from “dicts and loose parameters” to **typed dataclasses** so that:

- It’s clear what each structure contains.
- IDEs and type checkers can help you.
- The API response shapes are parsed once and then used as objects (e.g. `DiffEntry.update_files` instead of `entry["update_files"]`).

Defined types:

- **`DiffRequest`** — Just the three parameters for a diff: `from_release`, `to_release`, `dataset_name`. Frozen.
- **`DiffFileInfo`** — A single file in a diff (only `url` for now).
- **`DiffEntry`** — One block of diff metadata: `update_files` and `deleted_files` (lists of `DiffFileInfo`). Built from the API dict via `from_dict`.
- **`DiffResponse`** — Top-level diff response: `dataset`, `start_release`, `end_release`, and a list of `DiffEntry`. Also has `from_dict`.
- **`RecommendationsResponse`** — Wraps the list of recommended papers; `from_dict` accepts either a `"recommendations"` or `"papers"` key so we’re resilient to small API changes.
- **`PaperBatchRequest`** — Groups `paper_ids` and the `fields` string for a bulk request. Useful if you want to pass one object instead of two arguments.
- **`RelevanceFilter`** — The “additional input” for the relevance filter: optional `min_citation_count`, `venue_ids`, `fields_of_study`, and `keywords`. If a field is not set (or empty), we don’t filter on it. `is_empty()` returns True when no criterion is set, so the filter can short-circuit and return all papers.

______________________________________________________________________

## Relevance filter (how it works)

The filter lives in **`relevance.py`** and is exposed as **`filter_papers(papers, criteria)`** and **`client.filter_by_relevance(papers, criteria)`**. It expects `papers` to be a list of dicts in the same shape as the S2 bulk API (e.g. from `download_bulk_paper(...).json()`).

- **Citation count** — Keep only papers with `citationCount >= criteria.min_citation_count`. Missing or invalid counts are treated as not passing.
- **Venue** — Keep only papers whose venue id (from `publicationVenue.id` or `venue.id`) is in `criteria.venue_ids`. So you can restrict to a known list of journal/venue IDs.
- **Fields of study** — Keep only papers that have at least one of `criteria.fields_of_study` in `fieldsOfStudy` or `s2FieldsOfStudy`. Comparison is case-insensitive.
- **Keywords** — Keep only papers where at least one of `criteria.keywords` appears in the title or abstract (case-insensitive substring).

A paper is **kept** only if it passes every criterion that you actually set. If you don’t set any criterion (`criteria.is_empty()`), the function returns all papers unchanged. This way you can start with “only high-citation” and later add keywords or venues without changing the API.

______________________________________________________________________

## Quick reference

| Need                               | Use                                                                                                                                        |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| Default client (e.g. in notebook)  | `from kibad_crawler import s2_api` then `s2_api.download_dataset(...)` etc.                                                                |
| New code with one client           | `from kibad_crawler import S2Client`; `client = S2Client()`                                                                                |
| List of release dates              | `client.get_releases()` — last element is latest                                                                                           |
| Diff between two releases          | `client.get_diff_parsed(from_release, to_release, "papers")` → `DiffResponse`                                                              |
| Download diff files into subfolder | `client.download_diff_files(from_release, to_release, "papers")`                                                                           |
| “Last two releases” diff           | `client.download_last_two_releases_diff("papers")`                                                                                         |
| Similar papers to one paper        | `client.get_recommendations_for_paper(paper_id, limit=10)` → `RecommendationsResponse`                                                     |
| Filter papers by relevance         | `from kibad_crawler import RelevanceFilter`; `client.filter_by_relevance(papers, RelevanceFilter(min_citation_count=5, keywords=["NLP"]))` |

If you want more detail on a method, read its docstring in `s2_api.py`, `s2_models.py`, or `relevance.py`; they are written to explain both “what” and “how” in human terms.
