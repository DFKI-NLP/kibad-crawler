# Semantic filter: coast_trends

3,356 screened papers, 225 of them relevant, 5 random 80:20 splits.
Training maximized `f1`.

Embedding coverage (mean ± standard deviation) is 0.956 ± 0.007.

| Method    | Accuracy      | Precision     | Recall        | F1            |
| --------- | ------------- | ------------- | ------------- | ------------- |
| trained   | 0.878 ± 0.017 | 0.247 ± 0.093 | 0.330 ± 0.071 | 0.277 ± 0.084 |
| keep_all  | 0.069 ± 0.011 | 0.069 ± 0.011 | 1.000 ± 0.000 | 0.130 ± 0.019 |
| keep_none | 0.931 ± 0.011 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| random    | 0.843 ± 0.013 | 0.056 ± 0.023 | 0.088 ± 0.055 | 0.067 ± 0.032 |
