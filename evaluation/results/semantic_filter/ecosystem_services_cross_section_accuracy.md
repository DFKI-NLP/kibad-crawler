# Semantic filter: ecosystem_services_cross_section

840 screened papers, 104 of them relevant, 5 random 80:20 splits.
Training maximized `accuracy`.

Embedding coverage (mean ± standard deviation) is 0.944 ± 0.020.

| Method    | Accuracy      | Precision     | Recall        | F1            |
| --------- | ------------- | ------------- | ------------- | ------------- |
| trained   | 0.887 ± 0.018 | 0.569 ± 0.101 | 0.347 ± 0.063 | 0.423 ± 0.057 |
| keep_all  | 0.122 ± 0.023 | 0.122 ± 0.023 | 1.000 ± 0.000 | 0.217 ± 0.037 |
| keep_none | 0.878 ± 0.023 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| random    | 0.826 ± 0.013 | 0.148 ± 0.073 | 0.089 ± 0.047 | 0.108 ± 0.054 |
