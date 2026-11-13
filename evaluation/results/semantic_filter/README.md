# Semantic filter cross-validation

The semantic filter uses SPECTER2 embeddings to find relevant papers while
reducing the number of papers reviewers need to screen. We compared tuning its
thresholds for accuracy and F1 on four screening tables. Relevant papers are
the positive class, so recall measures how many relevant papers the filter
keeps.

## Screening tables

| `--table`                          | Screened papers with DOI | Relevant | Without embedding |
| ---------------------------------- | -----------------------: | -------: | ----------------: |
| `ecosystem_services_habitats`      |                      283 |      212 |                20 |
| `ecosystem_services_cross_section` |                      840 |      104 |                45 |
| `agricultural`                     |                    2,207 |    1,365 |               198 |
| `coast_trends`                     |                    3,356 |      225 |               149 |

## Results

Each objective used five random 80:20 train/test splits per table, with seeds
0 through 4. The tables show means across the held-out splits. The linked
reports also give standard deviations. Metrics and accuracy baselines are
computed on papers with embeddings. Coverage is the fraction of all held-out
papers with an embedding.

### Accuracy objective

| Screening table                                                 | Accuracy | Keep-all accuracy | Keep-none accuracy | Precision | Recall |    F1 | Coverage |
| --------------------------------------------------------------- | -------: | ----------------: | -----------------: | --------: | -----: | ----: | -------: |
| [ÖSL Lebensraum](ecosystem_services_habitats_accuracy.md)       |    0.771 |             0.729 |              0.271 |     0.782 |  0.952 | 0.858 |    0.919 |
| [ÖSL Querschnitt](ecosystem_services_cross_section_accuracy.md) |    0.887 |             0.122 |              0.878 |     0.569 |  0.347 | 0.423 |    0.944 |
| [Agrar All](agricultural_accuracy.md)                           |    0.628 |             0.595 |              0.405 |     0.647 |  0.829 | 0.726 |    0.907 |
| [Küste Trends](coast_trends_accuracy.md)                        |    0.931 |             0.069 |              0.931 |     0.000 |  0.000 | 0.000 |    0.956 |

### F1 objective

| Screening table                                           | Accuracy | Keep-all accuracy | Keep-none accuracy | Precision | Recall |    F1 | Coverage |
| --------------------------------------------------------- | -------: | ----------------: | -----------------: | --------: | -----: | ----: | -------: |
| [ÖSL Lebensraum](ecosystem_services_habitats_f1.md)       |    0.775 |             0.729 |              0.271 |     0.775 |  0.979 | 0.864 |    0.919 |
| [ÖSL Querschnitt](ecosystem_services_cross_section_f1.md) |    0.858 |             0.122 |              0.878 |     0.454 |  0.650 | 0.529 |    0.944 |
| [Agrar All](agricultural_f1.md)                           |    0.627 |             0.595 |              0.405 |     0.628 |  0.921 | 0.746 |    0.907 |
| [Küste Trends](coast_trends_f1.md)                        |    0.878 |             0.069 |              0.931 |     0.247 |  0.330 | 0.277 |    0.956 |

## Reproduce the reports

Follow the [project setup](../../../README.md#setup) and put the four workbooks
under `data/external/screening_tables/` using the paths defined in
[`SCREENING_TABLES`](../../../src/kibad_crawler/evaluation/reference_papers.py).
Agrar All uses the `dup_rmvd` sheet. Configure `S2_API_KEY` for the first run,
which fetches missing embeddings from Semantic Scholar and caches them in
`data/interim/semantic_filter/embeddings.json`.

Run both objectives from the repository root.

```bash
for objective in accuracy f1; do
    for table in ecosystem_services_habitats ecosystem_services_cross_section agricultural coast_trends; do
        uv run kibad-crawler cross-validate-semantic-filter --table "$table" --objective "$objective"
    done
done
```

The command writes `evaluation/results/semantic_filter/<table>_<objective>.md`.

## Discussion

Accuracy tuning beat both accuracy baselines on ÖSL Lebensraum and Agrar All.
On ÖSL Querschnitt, it narrowly beat the keep-none baseline (0.887 versus
0.878) and retrieved about a third of the relevant papers. On Küste Trends,
where about 7% of scorable test papers were relevant, it matched the keep-none
baseline and retrieved no relevant papers.

F1 tuning increased mean recall and F1 on all four tables. The biggest
recall gains came on Küste Trends (0.000 to 0.330) and ÖSL Querschnitt
(0.347 to 0.650). Accuracy fell below the keep-none baseline on both.
For screening, the higher recall means fewer relevant papers are missed.
Küste Trends still missed about two thirds of relevant papers with embeddings.

## Notes

- Julia's email listed 73 irrelevant and 223 relevant decisions for ÖSL
    Lebensraum. The shared workbook and the older copy both contain 72
    irrelevant and 222 relevant decisions. Eleven of those rows lack a DOI,
    leaving 283 papers.
- Five DOIs in Agrar All have conflicting screening decisions. These reports
    use the current loader, which keeps the first row for each of those DOIs.
- The held-out sets overlap across the five random splits.
- Semantic Scholar can add embeddings over time. Reruns that fetch embeddings
    from the API may give slightly different results.
