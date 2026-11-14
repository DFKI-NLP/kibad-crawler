# Comparing semantic filters on four screening tasks

The ridge filter improved mean F1 over [the filter from #57](README.md) on
ÖSL Querschnitt, Agrar All, and Küste Trends. F1 fell slightly on ÖSL
Lebensraum in both runs. The command now defaults to ridge with an
F1-tuned cutoff. Use `--method similarity` for the original classifier.

## Methods

Every classifier uses the same `embedding.specter_v2` vectors from the
Semantic Scholar Academic Graph API. The SciRepEval benchmark uses linear
classifiers on frozen scientific document embeddings. We tried a regularized
linear model using NumPy, plus two cosine scores that average information
from multiple labeled papers. [Academic Graph API](https://api.semanticscholar.org/api-docs/graphs) · [SciRepEval](https://aclanthology.org/2023.emnlp-main.338/)

- **#57** uses the maximum cosine similarity to each class and tunes the
    negative-class weight and two cutoffs on leave-one-out similarities.
- **Class centroids** subtracts the cosine to the irrelevant class mean
    from the cosine to the relevant class mean. It averages unit embeddings
    within each class before normalizing the means.
- **Five neighbors per class** subtracts the mean of the top five irrelevant
    cosine similarities from the mean of the top five relevant ones.
- **Ridge** fits scores to the 0/1 labels on unit-length embeddings, with
    a penalty of 0.3 on the squared norm of the weights and an unpenalized
    intercept. Prediction needs one dot product and a cutoff per paper.

Each method trains separately per workbook. We use the same papers, row order,
embedding cache and five random 80:20 DOI splits (seeds 0–4) as #57. For ridge,
centroids and five neighbors, every scorable paper in the 80% training set is
scored once by a model fitted on the other folds of a stratified three-fold
split. The cutoff maximizes the objective on these out-of-fold scores. Among
tied cutoffs, we use the one that keeps the most papers. The final model uses
all scorable training papers and is evaluated on the untouched 20% for that
split.

We chose the model and penalty using exploratory runs on seeds 0–4. A
second run checks the same settings on seeds 5–24. These splits use the same
labeled workbooks, and their test sets can overlap. The results describe
performance on the screened subset of these workbooks. Statistical
significance and performance on later searches remain open questions.

## Original splits (seeds 0–4)

The table reports means across splits. Scores and kept fractions use only
held-out papers with embeddings. Keep all has 100% recall on those papers.
The random baseline samples without replacement and keeps the same number
of papers as ridge in each split. Keep none has zero F1 on all four tables.

| Screening table | Embedding coverage | Keep-all F1 | Random F1 | #57 F1 | Ridge F1 | #57 recall | Ridge recall | #57 kept | Ridge kept |
| --------------- | -----------------: | ----------: | --------: | -----: | -------: | ---------: | -----------: | -------: | ---------: |
| ÖSL Lebensraum  |              0.919 |       0.843 |     0.820 |  0.864 |    0.856 |      0.979 |        0.984 |    92.4% |      94.7% |
| ÖSL Querschnitt |              0.944 |       0.217 |     0.170 |  0.529 |    0.637 |      0.650 |        0.810 |    18.1% |      18.9% |
| Agrar All       |              0.907 |       0.746 |     0.715 |  0.746 |    0.766 |      0.921 |        0.956 |    87.4% |      89.1% |
| Küste Trends    |              0.956 |       0.130 |     0.090 |  0.277 |    0.354 |      0.330 |        0.439 |     9.9% |      10.3% |

For **accuracy tuning**, mean accuracy for #57 and ridge respectively was
0.771 and 0.771 on Lebensraum, 0.887 and 0.917 on Querschnitt, 0.628 and
0.671 on Agrar All, and 0.931 and 0.930 on Küste Trends. Ridge tuned for
accuracy kept only 3.4% of the relevant Küste Trends papers. The high
accuracy there largely reflects the low prevalence of relevant papers.

## Ablation and alternatives

**Mean F1 on seeds 0–4.** The fixed-cutoff row removes threshold tuning from
ridge by using a score of 0.5 as the cutoff on the fitted 0/1 scale. The
matched-workload row ranks test papers by ridge score and keeps exactly as
many as the #57 F1 filter kept in each split. This measures ranking quality
at the same screening effort.

| Method                                  | ÖSL Lebensraum | ÖSL Querschnitt | Agrar All | Küste Trends |
| --------------------------------------- | -------------: | --------------: | --------: | -----------: |
| #57 with F1 tuning                      |          0.864 |           0.529 |     0.746 |        0.277 |
| Class centroids with F1 tuning          |          0.850 |           0.582 |     0.756 |        0.245 |
| Five neighbors per class with F1 tuning |          0.846 |           0.561 |     0.761 |        0.255 |
| Ridge with fixed 0.5 cutoff             |          0.865 |           0.414 |     0.756 |        0.000 |
| Ridge at #57's workload                 |          0.864 |           0.620 |     0.771 |        0.318 |
| Ridge with F1 tuning                    |          0.856 |           0.637 |     0.766 |        0.354 |

Ridge's gains on Querschnitt, Agrar All, and Küste Trends persisted at the
same screening workload. Cutoff tuning mattered most on Querschnitt and
Küste Trends. A fixed 0.5 cutoff kept very few papers on Querschnitt and
rejected every paper on Küste Trends. Averaging neighbors or using class
centroids helped on Querschnitt and Agrar All, but both underperformed #57
on Küste Trends in the original splits.

## Additional splits (seeds 5–24)

Mean ± standard deviation of split F1. Precision, recall, and kept are means
for F1-tuned ridge.

| Screening table |   Keep-all F1 |     Random F1 |        #57 F1 |      Ridge F1 | Ridge precision | Ridge recall | Ridge kept |
| --------------- | ------------: | ------------: | ------------: | ------------: | --------------: | -----------: | ---------: |
| ÖSL Lebensraum  | 0.864 ± 0.041 | 0.834 ± 0.053 | 0.874 ± 0.032 | 0.866 ± 0.038 |           0.786 |        0.969 |      94.0% |
| ÖSL Querschnitt | 0.221 ± 0.030 | 0.144 ± 0.064 | 0.526 ± 0.063 | 0.634 ± 0.072 |           0.561 |        0.760 |      17.2% |
| Agrar All       | 0.760 ± 0.013 | 0.719 ± 0.018 | 0.762 ± 0.019 | 0.781 ± 0.016 |           0.669 |        0.941 |      86.4% |
| Küste Trends    | 0.122 ± 0.018 | 0.069 ± 0.025 | 0.271 ± 0.043 | 0.322 ± 0.058 |           0.266 |        0.427 |      10.6% |

Querschnitt gained 0.108 F1 in both runs. Küste Trends also improved, but
ridge still missed more than half of its scorable relevant papers. On
Lebensraum, ridge kept more papers and recovered slightly more relevant
papers than #57, at lower precision. The F1-tuned cutoff is a trade-off
between precision and recall. Papers without embeddings receive no
decision and are excluded from these metrics.

## Reproduce

Run `uv sync --locked` from the repository root. Use the four screening
workbooks at the paths in [`SCREENING_TABLES`](../../../src/kibad_crawler/evaluation/reference_papers.py).
Agrar All uses the `dup_rmvd` sheet. The [original evaluation](README.md#notes)
describes how the loader handles conflicting screening decisions.

Reuse the original `data/interim/semantic_filter/embeddings.json` snapshot
for identical embedding coverage. Its SHA-256 was
`973eaf582d6a6643491454a7a9720a7890af6ab380d36ef34d12d2071782042c`.
If the cache is absent, configure `S2_API_KEY` as described in the [project
setup](../../../README.md#setup). Refetching from Semantic Scholar may change
vectors or coverage.

The [evaluation script](../../../scripts/evaluate_semantic_filter.py) prints
accuracy, precision, recall, F1, and the kept fraction as mean ± standard
deviation for all methods on each table. Use the same thread count and
locked dependencies for reproduction.

```bash
OPENBLAS_NUM_THREADS=1 uv run --locked python scripts/evaluate_semantic_filter.py > original-splits.md
OPENBLAS_NUM_THREADS=1 uv run --locked python scripts/evaluate_semantic_filter.py --start-seed 5 --n-splits 20 > additional-splits.md
```
