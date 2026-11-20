# Keyword filter and semantic filter evaluation

Evaluation of the keyword filter (Tabelle 3) and the semantic filter (Tabelle 4) in the report "Dokumentation Teilleistung 5 (AP 2)".

## Data

Follow the [project setup](../../README.md#setup). The crawl and the first run of the semantic filter need `S2_API_KEY`.

### Screening tables

The screening tables are in the Google Drive folder [ASReview Faktencheck](https://drive.google.com/drive/folders/1v-vkFmrz2BpB0z3OeH9bjgYN6PJiUKcZ).
`Boden-Maßnahmen.xlsx` is not in that folder. It is in `Screening Tabellen/` of the [ownCloud share](https://cloud.dfki.de/owncloud/index.php/s/emiJLtgSqA4xMcP).

Copy them to `data/external/screening_tables/` using the paths in [`SCREENING_TABLES`](../../src/kibad_crawler/evaluation/reference_papers.py).
Two files are named differently in the Drive folder:

| Drive folder                | `data/external/screening_tables/` |
| :-------------------------- | :-------------------------------- |
| `ÖSL-Querschnitt_mark.xlsx` | `ÖSL-Querschnitt.xlsx`            |
| `Boden-Treiber_mark.xlsx`   | `Boden-Treiber.xlsx`              |

### Publication venues

[`data/raw/ISSN.csv`](../../data/raw/ISSN.csv) has 1,280 ISSN codes, which match 1,139 publication venues in release `2024-12-31`.

## Keyword filter (Tabelle 3)

Crawl of release `2024-12-31` with the venues of `ISSN.csv` and papers published from 1977-01-01 to 2022-12-31:

```sh
uv run kibad-crawler download-paper-metadata \
--release 2024-12-31 \
--n-files 0 \
--file-with-issn data/raw/ISSN.csv \
--min-publication-date 1977-01-01 \
--max-publication-date 2022-12-31 \
--persistent
```

Evaluation of the queries against the screening tables:

```sh
uv run kibad-crawler evaluate-search-queries \
--release 2024-12-31 \
--file-with-issn data/raw/ISSN.csv \
--max-publication-date 2022-12-31
```

Saved to `evaluation/results/<search>.md`.

| Tabelle 3 row                                                  | Queries    |
| :------------------------------------------------------------- | :--------- |
| [Wald](forest.md)                                              | Q1 to Q4   |
| [Boden Trends](soil_trends.md)                                 | Q5         |
| [Boden Treiber](soil_drivers.md)                               | Q6         |
| [Boden Maßnahmen](soil_measures.md)                            | Q7         |
| [Agrar- und Offenland](agricultural.md)                        | Q9 to Q12  |
| [Agrar- und Offenland Treiber](agricultural_drivers.md)        | Q10        |
| [Agrar- und Offenland ÖSL](agricultural_ecosystem_services.md) | Q12        |
| [Binnengewässer und Auen](inland_waters.md)                    | Q13 to Q16 |
| [Küste Trends](coast_trends.md)                                | Q17        |
| [Küste Maßnahmen](coast_measures.md)                           | Q19        |
| [Urbane Räume Trends](urban_trends.md)                         | Q21        |
| [ÖSL Querschnitt](ecosystem_services_cross_section.md)         | Q25        |
| [ÖSL Lebensräume](ecosystem_services_habitats.md)              | Q26        |

Notes

- Tabelle 3 uses the rows `all reference papers`, `in the publication venues` and `all queries` of these files
- "Anteil" is `relevant` of `all queries` divided by `relevant in the crawl`
- "Anzahl Referenzartikel Web of Science & Scopus" is not computed here
- `download-paper-metadata` skips files that are already in `data/raw/semantic_scholar/release/2024-12-31/papers/`, so start with an empty folder
- The metadata and the DOIs come from the Semantic Scholar API, so a new run can give slightly different numbers. The DOIs were resolved 2026-10-30 to 2026-11-11 and are in `<search>_dois_s2.csv` next to the screening tables

## Semantic filter (Tabelle 4)

Screening tables: `ÖSL-lebensräume.xlsx`, `ÖSL-Querschnitt.xlsx`, `Agrar- und Offenland/asreview_dataset_ALL_sorted.xlsx` (sheet `dup_rmvd`) and `Küste/asreview_result_trends_AdrianDoro.xlsx`.

Cross-validation with the accuracy objective:

```sh
for table in ecosystem_services_habitats ecosystem_services_cross_section agricultural coast_trends; do
    uv run kibad-crawler cross-validate-semantic-filter --table "$table" --objective accuracy
done
```

Saved to `evaluation/results/semantic_filter/<table>_accuracy.md`.

Notes

- Tabelle 4 uses the row `trained`
- "Accuracy ohne behaltene Artikel" is the accuracy of `keep_none`
- See the [semantic filter README](semantic_filter/README.md) for details
