# Semantic filter: ecosystem_services_habitats

283 screened papers, 212 of them relevant, 5 random 80:20 splits.
Training maximized `accuracy`.

Embedding coverage (mean ± standard deviation) is 0.919 ± 0.018.

| Method    | Accuracy      | Precision     | Recall        | F1            |
| --------- | ------------- | ------------- | ------------- | ------------- |
| filter    | 0.771 ± 0.068 | 0.782 ± 0.066 | 0.952 ± 0.032 | 0.858 ± 0.044 |
| keep_all  | 0.729 ± 0.044 | 0.729 ± 0.044 | 1.000 ± 0.000 | 0.843 ± 0.029 |
| keep_none | 0.271 ± 0.044 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| random    | 0.672 ± 0.041 | 0.726 ± 0.045 | 0.885 ± 0.042 | 0.796 ± 0.031 |
