# Semantic filter: agricultural

2,207 screened papers, 1,365 of them relevant, 5 random 80:20 splits.
Training maximized `accuracy`.

Embedding coverage (mean ± standard deviation) is 0.907 ± 0.011.

| Method    | Accuracy      | Precision     | Recall        | F1            |
| --------- | ------------- | ------------- | ------------- | ------------- |
| filter    | 0.628 ± 0.013 | 0.647 ± 0.014 | 0.829 ± 0.026 | 0.726 ± 0.012 |
| keep_all  | 0.595 ± 0.012 | 0.595 ± 0.012 | 1.000 ± 0.000 | 0.746 ± 0.010 |
| keep_none | 0.405 ± 0.012 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| random    | 0.556 ± 0.020 | 0.599 ± 0.018 | 0.767 ± 0.031 | 0.672 ± 0.019 |
