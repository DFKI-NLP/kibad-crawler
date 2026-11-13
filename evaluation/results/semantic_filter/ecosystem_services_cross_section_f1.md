# Semantic filter: ecosystem_services_cross_section

840 screened papers, 104 of them relevant, 5 random 80:20 splits.
Training maximized `f1`.

Embedding coverage (mean ± standard deviation) is 0.944 ± 0.020.

| Method    | Accuracy      | Precision     | Recall        | F1            |
| --------- | ------------- | ------------- | ------------- | ------------- |
| filter    | 0.858 ± 0.036 | 0.454 ± 0.087 | 0.650 ± 0.081 | 0.529 ± 0.073 |
| keep_all  | 0.122 ± 0.023 | 0.122 ± 0.023 | 1.000 ± 0.000 | 0.217 ± 0.037 |
| keep_none | 0.878 ± 0.023 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| random    | 0.745 ± 0.055 | 0.126 ± 0.041 | 0.198 ± 0.102 | 0.152 ± 0.059 |
