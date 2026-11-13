# Semantic filter: ecosystem_services_habitats

283 screened papers, 212 of them relevant, 5 random 80:20 splits.
Training maximized `f1`.

Embedding coverage (mean ± standard deviation) is 0.919 ± 0.018.

| Method    | Accuracy      | Precision     | Recall        | F1            |
| --------- | ------------- | ------------- | ------------- | ------------- |
| filter    | 0.775 ± 0.065 | 0.775 ± 0.069 | 0.979 ± 0.010 | 0.864 ± 0.040 |
| keep_all  | 0.729 ± 0.044 | 0.729 ± 0.044 | 1.000 ± 0.000 | 0.843 ± 0.029 |
| keep_none | 0.271 ± 0.044 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| random    | 0.699 ± 0.023 | 0.733 ± 0.038 | 0.929 ± 0.039 | 0.818 ± 0.015 |
