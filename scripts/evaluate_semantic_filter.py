"""Reproduce the comparisons for issue #61 on the four screening workbooks."""

import argparse
from collections.abc import Callable

from loguru import logger
import numpy as np
from numpy.typing import NDArray
from tabulate import tabulate

from kibad_crawler.evaluation.reference_papers import (
    SCREENING_TABLES,
    SCREENING_TABLES_DIR,
    ScreeningTables,
    read_screening_tables,
)
from kibad_crawler.semantic_filter import (
    FilterMethod,
    SemanticFilter,
    _calibration_folds,
    _fit_ridge,
    _get_metrics,
    _get_vectors,
    _matched_random_predictions,
    _normalize,
    _out_of_fold_ridge_scores,
    _select_threshold,
)

TABLE_NAMES = (
    "ecosystem_services_habitats",
    "ecosystem_services_cross_section",
    "agricultural",
    "coast_trends",
)


def centroid_scores(
    train: NDArray[np.floating], relevant: NDArray[np.bool_], test: NDArray[np.floating]
) -> NDArray[np.floating]:
    """Subtract cosine similarity to the irrelevant centroid from the relevant one."""
    centroids = _normalize(np.stack([train[relevant].mean(0), train[~relevant].mean(0)]))
    return test @ (centroids[0] - centroids[1])


def neighbor_scores(
    train: NDArray[np.floating], relevant: NDArray[np.bool_], test: NDArray[np.floating]
) -> NDArray[np.floating]:
    """Subtract mean similarity to the five closest examples of each class."""
    similarities = test @ train.T
    means = []
    for mask in (relevant, ~relevant):
        class_scores = similarities[:, mask]
        count = min(5, class_scores.shape[1])
        means.append(np.partition(class_scores, -count, axis=1)[:, -count:].mean(axis=1))
    return means[0] - means[1]


def tune_f1(
    score: Callable[
        [NDArray[np.floating], NDArray[np.bool_], NDArray[np.floating]], NDArray[np.floating]
    ],
    train: NDArray[np.floating],
    relevant: NDArray[np.bool_],
    test: NDArray[np.floating],
) -> NDArray[np.bool_]:
    """Tune a candidate's cutoff with the same training folds as ridge."""
    scores = np.empty(len(train))
    for held_out in _calibration_folds(relevant):
        scores[held_out] = score(train[~held_out], relevant[~held_out], train[held_out])
    return score(train, relevant, test) >= _select_threshold(scores, relevant, "f1")


def evaluate(table: ScreeningTables, seeds: range) -> None:
    """Print held-out metrics and threshold ablations for a screening table."""
    df = read_screening_tables(SCREENING_TABLES_DIR, table).dropna(subset=["included"])
    dois = df["doi"].tolist()
    labels = (df["included"] == 1).tolist()
    vectors, available = _get_vectors(dois)
    embedding_by_doi = dict(zip(np.asarray(dois)[available], vectors, strict=True))
    labels_by_doi = dict(zip(dois, labels, strict=True))
    results: dict[str, list[list[float]]] = {}
    coverage = []

    for seed in seeds:
        train_dois, _, test_dois, _ = SemanticFilter.create_splits(dois, labels, seed=seed)
        scorable_train = [doi for doi in train_dois if doi in embedding_by_doi]
        scorable_test = [doi for doi in test_dois if doi in embedding_by_doi]
        train = np.array([embedding_by_doi[doi] for doi in scorable_train])
        relevant = np.array([labels_by_doi[doi] for doi in scorable_train])
        test = np.array([embedding_by_doi[doi] for doi in scorable_test])
        expected = np.array([labels_by_doi[doi] for doi in scorable_test])
        coverage.append(len(expected) / len(test_dois))

        normalized_train, normalized_test = _normalize(train), _normalize(test)
        weights, intercept = _fit_ridge(normalized_train, relevant)
        test_scores = normalized_test @ weights
        training_scores = _out_of_fold_ridge_scores(normalized_train, relevant)
        predictions = {
            "Keep all": np.ones_like(expected),
            "Keep none": np.zeros_like(expected),
            "Ridge (fixed 0.5)": test_scores >= 0.5 - intercept,
            "Class centroids (f1)": tune_f1(
                centroid_scores, normalized_train, relevant, normalized_test
            ),
            "Five neighbors per class (f1)": tune_f1(
                neighbor_scores, normalized_train, relevant, normalized_test
            ),
        }
        for objective in ("f1", "accuracy"):
            baseline = SemanticFilter._fit(train, relevant, objective, FilterMethod.SIMILARITY)
            predictions[f"#57 ({objective})"] = baseline._predict_vectors(test)
            threshold = _select_threshold(training_scores, relevant, objective) - intercept
            predictions[f"Ridge ({objective})"] = test_scores >= threshold

        baseline_f1 = predictions["#57 (f1)"]
        at_baseline_workload = np.zeros_like(expected)
        ranked = np.argsort(-test_scores, kind="stable")
        at_baseline_workload[ranked[: baseline_f1.sum()]] = True
        predictions["Ridge (same count as #57 F1)"] = at_baseline_workload
        predictions["Random (same count as #57 F1)"] = _matched_random_predictions(
            baseline_f1, seed
        )
        predictions["Random (same count as ridge F1)"] = _matched_random_predictions(
            predictions["Ridge (f1)"], seed
        )

        for name, kept in predictions.items():
            metrics = _get_metrics(kept, expected)
            results.setdefault(name, []).append([*metrics.values(), float(kept.mean())])

    print(f"## {table.name}\n")
    print(f"{len(seeds)} splits, coverage {np.mean(coverage):.3f} ± {np.std(coverage):.3f}.\n")
    rows = [
        [name, *(f"{m:.3f} ± {s:.3f}" for m, s in zip(np.mean(values, 0), np.std(values, 0)))]
        for name, values in results.items()
    ]
    print(
        tabulate(
            rows,
            headers=["Method", "Accuracy", "Precision", "Recall", "F1", "Kept"],
            tablefmt="pipe",
        )
    )
    print()


def main() -> None:
    """Run the requested train/test splits for each screening table."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-seed", type=int, default=0)
    parser.add_argument("--n-splits", type=int, default=5)
    args = parser.parse_args()
    if args.start_seed < 0 or args.n_splits < 1:
        parser.error("start-seed must be nonnegative and n-splits must be positive")
    # Keep the Markdown on stdout so it can be redirected to a file.
    logger.remove()
    seeds = range(args.start_seed, args.start_seed + args.n_splits)
    for name in TABLE_NAMES:
        evaluate(next(table for table in SCREENING_TABLES if table.name == name), seeds)


if __name__ == "__main__":
    main()
