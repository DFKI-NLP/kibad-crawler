# Semantic filter: agricultural

2,207 screened papers, 1,365 of them relevant, 5 random 80:20 splits.
Training maximized `f1`.

Embedding coverage (mean ± standard deviation) is 0.907 ± 0.011.

| Method    | Accuracy      | Precision     | Recall        | F1            |
| --------- | ------------- | ------------- | ------------- | ------------- |
| trained   | 0.627 ± 0.011 | 0.628 ± 0.014 | 0.921 ± 0.032 | 0.746 ± 0.010 |
| keep_all  | 0.595 ± 0.012 | 0.595 ± 0.012 | 1.000 ± 0.000 | 0.746 ± 0.010 |
| keep_none | 0.405 ± 0.012 | 0.000 ± 0.000 | 0.000 ± 0.000 | 0.000 ± 0.000 |
| random    | 0.577 ± 0.011 | 0.599 ± 0.011 | 0.879 ± 0.039 | 0.712 ± 0.014 |
