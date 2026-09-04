# Semantic Scholar

## Data

[Semantic Scholar](https://api.semanticscholar.org/api-docs/) has the concept of `release` (i.e.: '2025-12-02', '2025-12-09',
'2026-01-20', '2026-01-27'). There are over 170 releases currently, the first
one is from: '2022-05-10'. Each release contains all the papers until the
requested date, so it is necessary to filter them by publication date and
publication venue.

Each `release`, has the following datasets:

- `publication-venues` Details about the venues in which papers are published.
    ~200k publication venues in the dataset.
- `papers` The core attributes of a paper (title, authors, date, etc.). 200M
    records in 30 1.5GB files.
- `abstracts`: Paper abstract text, where available. 100M records in 30 1.8GB
    files.
- `authors`: The core attributes of an author (name, affiliation, paper count,
    etc.). Authors have an "authorId" field, which can be joined to the
    "authorId" field of the members of a paper's "authors" field. 75M records in
    30 100MB files.
- `citations` Instances where the bibliography of one paper (the "citingPaper")
    mentions another paper (the "citedPaper"), where both papers are identified
    by the "paperId" field. Citations have attributes of their own, (influential
    classification, intent classification, and citation context). 2.4B records in
    30 8.5GB files.
- `embeddings-specter_v1` A dense vector embedding representing the contents of
    the paper. 120M records in 30 28GB files.
- `embeddings-specter_v2` A dense vector embedding representing the contents of
    the paper, generated with SPECTER2 120M records in 30 28GB files.
- `paper-ids` Mapping from sha-based ID to paper corpus ID. 450M records in 30
    500MB files
- `s2orc` Full-body paper text parsed from open-access PDFs. Identifies
    structural elements such as paragraphs, sections, and bibliography entries.
    10M records in 30 4GB files.
- `s2orc_v2` Full-body paper text parsed from open-access PDFs. Identifies
    structural elements such as sentences and paragraphs, and bibliographic
    references. 16M records in 30 6GB files.
- `tldrs` A short natural-language summary of the contents of a paper. 58M
    records in 30 200MB files.

## Download algorithm

To download new publications the process is the following:

1. Download the releases and select the most recent by default. The release has a format of date `2026-02-03`.
1. Download the `publication-venues` dataset of that `release`.
1. Filter the `publication-venues` by the `ISSN` codes obtained from [Übersicht relevante Journals und Archive](https://docs.google.com/spreadsheets/d/1ugPuiRNmcVYWcV98TvXsyqVwJYhmk2iZjZ4o9estM2Y/edit?gid=1647072097#gid=1647072097) and generate a list with specific venues.
1. Extract the `id` of those `publication-venues`.
1. Download the `papers` dataset. 60 files of 1,8GB each.
1. Select a publication date range to filter the papers.
1. Filter each batch of papers by the `venue_id` and publication date range.
    1. An additional filter by `citationCount` can be added.
1. Extract the `paperid` from the last part of the `url` field in the `papers` dataset
1. Use the list of `paperid`s to bulk query the API to download 500 papers on each call
1. The following fields are returned by the bulk API `"corpusId,url,title,abstract,venue,publicationVenue,year,citationCount,isOpenAccess,openAccessPdf,publicationDate,journal,fieldsOfStudy,s2FieldsOfStudy,authors,tldr,publicationTypes,textAvailability"`
1. The bulk of 500 papers each is stored in files with the following pattern `semantic_scholar/release/<release>/json/<release>-<batch_number>.json`