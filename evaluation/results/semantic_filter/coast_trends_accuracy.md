# Semantic filter: coast_trends

3,356 screened papers, 225 of them relevant, 5 random 80:20 splits.
Training maximized `accuracy`.

Embedding coverage (mean ± standard deviation) is 0.956 ± 0.007.

| Method    | Accuracy      | Precision     | Recall        | F1            |
| --------- | ------------- | ------------- | ------------- | ------------- |
| filter    | 0.931 ± 0.011 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| keep_all  | 0.069 ± 0.011 | 0.069 ± 0.011 | 1.000 ± 0.000 | 0.130 ± 0.019 |
| keep_none | 0.931 ± 0.011 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| random    | 0.931 ± 0.011 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
