"""Filter papers using Semantic Scholar's SPECTER2 embeddings.

The ridge classifier learns a linear score from the embeddings of screened
papers. The similarity classifier uses the maximum cosine similarity to each
class. Train a filter per screening task.
"""

from dataclasses import dataclass, field
from enum import StrEnum
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import time
from typing import Self, TypedDict

from loguru import logger
import numpy as np
from numpy.typing import NDArray

from kibad_crawler.config import INTERIM_DATA_DIR
from kibad_crawler.semantic_scholar import academic_graph
from kibad_crawler.utils import chunker

EMBEDDINGS_FILE = INTERIM_DATA_DIR / "semantic_filter" / "embeddings.json"
FIELDS = "paperId,embedding.specter_v2"
DELAY_BETWEEN_BATCHES = 3
ALPHAS = [0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0]
N_THRESHOLDS = 21
RIDGE_PENALTY = 0.3


class FilterMethod(StrEnum):
    """Scoring methods for the semantic filter."""

    RIDGE = "ridge"
    SIMILARITY = "similarity"


class CrossValidationResult(TypedDict):
    """Mean and standard deviation of coverage and the metrics for each method."""

    coverage: tuple[float, float]
    metrics: dict[str, dict[str, tuple[float, float]]]


def _get_embeddings(
    dois: list[str], cache_path: Path = EMBEDDINGS_FILE
) -> dict[str, list[float] | None]:
    """Return cached SPECTER2 embeddings and request any uncached DOIs.

    Args:
        dois: Paper DOIs.
        cache_path: JSON file used to read and store embeddings.

    Returns:
        Each DOI mapped to its embedding vector or `None` if unavailable.
    """
    cache: dict[str, list[float] | None] = (
        json.loads(cache_path.read_text()) if cache_path.exists() else {}
    )
    missing = sorted(set(dois) - set(cache))
    for i, group in enumerate(chunker(missing, 500)):
        papers = academic_graph.batch([f"DOI:{doi}" for doi in group], fields=FIELDS)
        for doi, paper in zip(group, papers):
            embedding: dict = (paper or {}).get("embedding") or {}
            cache[doi] = embedding.get("vector")
        logger.info(f"batch {i}: embeddings of {len(group):,} papers requested")
        time.sleep(DELAY_BETWEEN_BATCHES)
    if missing:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache))
    return {doi: cache[doi] for doi in dois}


def _get_vectors(dois: list[str]) -> tuple[NDArray[np.floating], NDArray[np.bool_]]:
    """Return the embeddings of the papers that have one.

    Args:
        dois: Paper DOIs.

    Returns:
        A matrix with one row per available embedding, in input order, and a
        Boolean mask aligned with `dois`. The matrix has shape (0, 0) when
        no embeddings are available.
    """
    embeddings = _get_embeddings(dois)
    available = np.array([embeddings[doi] is not None for doi in dois], dtype=bool)
    if not available.all():
        logger.info(f"{(~available).sum():,} of {len(dois):,} papers without an embedding skipped")
    vectors = [embeddings[doi] for doi in dois if embeddings[doi] is not None]
    return (np.array(vectors) if vectors else np.empty((0, 0))), available


def _normalize(vectors: NDArray[np.floating]) -> NDArray[np.floating]:
    """Scale each row to unit length for cosine similarity.

    Args:
        vectors: A matrix with one nonzero embedding per row.

    Returns:
        The normalized matrix with the same shape as `vectors`.
    """
    return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)


def _scorable_predictions_and_labels(
    predictions: list[bool | None], labels: list[bool]
) -> tuple[NDArray[np.bool_], NDArray[np.bool_]]:
    """Keep the aligned predictions and labels for papers with embeddings.

    Args:
        predictions: One decision per paper, with `None` for missing embeddings.
        labels: Relevance labels in the same order as `predictions`.

    Returns:
        Two one-dimensional Boolean arrays containing the scorable decisions
        and their corresponding labels, in input order.

    Raises:
        ValueError: If no test papers have embeddings.
    """
    available = np.array([prediction is not None for prediction in predictions], dtype=bool)
    if not available.any():
        raise ValueError("No test papers have embeddings")
    scorable_predictions = np.array(predictions, dtype=bool)[available]
    return scorable_predictions, np.array(labels, dtype=bool)[available]


def _get_metrics(predictions: NDArray[np.bool_], labels: NDArray[np.bool_]) -> dict[str, float]:
    """Return accuracy, precision, recall and F1 of binary predictions.

    Args:
        predictions: Nonempty one-dimensional array with `True` for kept papers.
        labels: One-dimensional relevance labels aligned with `predictions`.

    Returns:
        Accuracy, precision, recall, and F1. Precision, recall, and F1 are
        zero when their respective denominators are zero.
    """
    true_positives = (predictions & labels).sum()
    precision = true_positives / predictions.sum() if predictions.any() else 0.0
    recall = true_positives / labels.sum() if labels.any() else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "accuracy": float((predictions == labels).mean()),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
    }


def _matched_random_predictions(predictions: NDArray[np.bool_], seed: int) -> NDArray[np.bool_]:
    """Keep the same number of papers using a separate random stream from splitting."""
    rng = np.random.default_rng([seed, 1])
    chosen = rng.choice(len(predictions), size=int(predictions.sum()), replace=False)
    random_predictions = np.zeros_like(predictions)
    random_predictions[chosen] = True
    return random_predictions


def _get_training_scores(
    vectors: NDArray[np.floating], relevant: NDArray[np.bool_]
) -> tuple[NDArray[np.floating], NDArray[np.floating]]:
    """Compute the highest similarity to another paper in each class.

    Args:
        vectors: Normalized embeddings with one paper per row.
        relevant: Boolean relevance labels aligned with the rows.

    Returns:
        Two one-dimensional arrays with the highest similarities to another
        relevant and another irrelevant paper, respectively. A paper without
        another example in its own class has a score of negative infinity
        for that class.

    Raises:
        ValueError: If either class has no examples.
    """
    similarities = vectors @ vectors.T
    np.fill_diagonal(similarities, -np.inf)
    return similarities[:, relevant].max(axis=1), similarities[:, ~relevant].max(axis=1)


def _fit_ridge(
    vectors: NDArray[np.floating], relevant: NDArray[np.bool_]
) -> tuple[NDArray[np.floating], float]:
    """Fit ridge regression to the 0/1 labels with an unpenalized intercept."""
    center = vectors.mean(axis=0)
    prevalence = float(relevant.mean())
    centered = vectors - center
    gram = centered.T @ centered + RIDGE_PENALTY * np.eye(centered.shape[1])
    weights = np.linalg.solve(gram, centered.T @ (relevant - prevalence))
    return weights, prevalence - float(center @ weights)


def _calibration_folds(relevant: NDArray[np.bool_]) -> list[NDArray[np.bool_]]:
    """Return held-out masks for up to three stratified training folds."""
    n_folds = min(3, int(relevant.sum()), int((~relevant).sum()))
    rng = np.random.default_rng(0)
    folds = np.empty(len(relevant), dtype=int)
    for label_mask in (relevant, ~relevant):
        indices = rng.permutation(np.flatnonzero(label_mask))
        folds[indices] = np.arange(len(indices)) % n_folds
    return [folds == fold for fold in range(n_folds)]


def _out_of_fold_ridge_scores(
    vectors: NDArray[np.floating], relevant: NDArray[np.bool_]
) -> NDArray[np.floating]:
    """Score each training paper with a ridge model fitted on other folds."""
    scores = np.empty(len(relevant))
    for held_out in _calibration_folds(relevant):
        weights, intercept = _fit_ridge(vectors[~held_out], relevant[~held_out])
        scores[held_out] = vectors[held_out] @ weights + intercept
    return scores


def _select_threshold(
    scores: NDArray[np.floating], relevant: NDArray[np.bool_], objective: str
) -> float:
    """Find the best score cutoff, keeping more papers when cutoffs tie."""
    order = np.argsort(scores)[::-1]
    sorted_scores = scores[order]
    # Only evaluate cutoffs at which every paper with the same score is kept together.
    ends = np.flatnonzero(np.r_[sorted_scores[:-1] != sorted_scores[1:], True])
    kept = np.r_[0, ends + 1]
    true_positives = np.r_[0, np.cumsum(relevant[order])[ends]]
    n_relevant = int(relevant.sum())
    values = {
        "accuracy": (len(relevant) - n_relevant + 2 * true_positives - kept) / len(relevant),
        "precision": true_positives / np.maximum(kept, 1),
        "recall": true_positives / n_relevant,
        "f1": 2 * true_positives / (kept + n_relevant),
    }[objective]
    thresholds = np.r_[np.inf, sorted_scores[ends]]
    return float(thresholds[np.flatnonzero(values == values.max())[-1]])


@dataclass
class SemanticFilter:
    """Store a fitted ridge or similarity filter.

    Attributes:
        alpha: Weight of the maximum similarity to irrelevant examples in the similarity filter.
        min_positive_similarity: Minimum similarity to a relevant example.
        min_margin: Minimum score after subtracting weighted irrelevant similarity.
        positive_vectors: Relevant examples for the similarity filter.
        negative_vectors: Irrelevant examples for the similarity filter.
        weights: Ridge coefficients, or `None` for the similarity filter.
        threshold: Cutoff for the ridge dot product, with the intercept absorbed.
    """

    alpha: float = 1.0
    min_positive_similarity: float = -1.0
    min_margin: float = -3.0
    positive_vectors: NDArray[np.floating] = field(default_factory=lambda: np.empty((0, 0)))
    negative_vectors: NDArray[np.floating] = field(default_factory=lambda: np.empty((0, 0)))
    weights: NDArray[np.floating] | None = None
    threshold: float = 0.0

    def _keep(
        self, positive_scores: NDArray[np.floating], negative_scores: NDArray[np.floating]
    ) -> NDArray[np.bool_]:
        """Apply both thresholds to the similarity scores.

        Args:
            positive_scores: Maximum similarity to relevant examples per paper.
            negative_scores: Maximum similarity to irrelevant examples for the
                same papers, in the same order.

        Returns:
            One Boolean decision per paper, with `True` if both thresholds pass.
        """
        scores = positive_scores - self.alpha * negative_scores
        return (positive_scores >= self.min_positive_similarity) & (scores >= self.min_margin)

    def _predict_vectors(self, vectors: NDArray[np.floating]) -> NDArray[np.bool_]:
        """Classify papers with available embeddings."""
        vectors = _normalize(vectors)
        if self.weights is not None:
            return vectors @ self.weights >= self.threshold
        positive_scores = (vectors @ _normalize(self.positive_vectors).T).max(axis=1)
        negative_scores = (vectors @ _normalize(self.negative_vectors).T).max(axis=1)
        return self._keep(positive_scores, negative_scores)

    def predict(self, dois: list[str]) -> list[bool | None]:
        """Decide for each paper whether it is kept.

        Args:
            dois: Paper DOIs.

        Returns:
            One decision per DOI, in input order. `True` means keep, `False`
            means reject, and `None` means the embedding is unavailable.
        """
        vectors, available = _get_vectors(dois)
        predictions: list[bool | None] = [None] * len(dois)
        if not available.any():
            return predictions
        for index, decision in zip(np.flatnonzero(available), self._predict_vectors(vectors)):
            predictions[index] = bool(decision)
        return predictions

    @classmethod
    def train(
        cls,
        dois: list[str],
        labels: list[bool],
        objective: str = "f1",
        method: FilterMethod = FilterMethod.RIDGE,
    ) -> Self:
        """Fit a semantic filter using screened papers with embeddings.

        The ridge cutoff is selected on out-of-fold scores. The similarity
        filter tunes its thresholds by comparing each paper with the other
        examples. The returned model is fitted on all available training papers.

        Args:
            dois: DOIs of the screened papers.
            labels: Relevance labels aligned with `dois`.
            objective: Metric to maximize, one of `accuracy`, `precision`,
                `recall`, or `f1`.
            method: Scoring method.

        Returns:
            The fitted filter.

        Raises:
            KeyError: If `objective` is an unknown metric.
            ValueError: If either class has fewer than two papers with embeddings.
        """
        vectors, available = _get_vectors(dois)
        relevant = np.array(labels, dtype=bool)[available]
        return cls._fit(vectors, relevant, objective, method)

    @classmethod
    def _fit(
        cls,
        vectors: NDArray[np.floating],
        relevant: NDArray[np.bool_],
        objective: str,
        method: FilterMethod,
    ) -> Self:
        """Fit the requested filter on aligned embeddings and screening labels."""
        n_relevant = int(relevant.sum())
        n_irrelevant = relevant.size - n_relevant
        if min(n_relevant, n_irrelevant) < 2:
            raise ValueError(
                "Training requires at least two relevant and two irrelevant papers "
                f"with embeddings. Found {n_relevant} relevant and {n_irrelevant} irrelevant."
            )

        vectors = _normalize(vectors)
        if method == FilterMethod.RIDGE:
            scores = _out_of_fold_ridge_scores(vectors, relevant)
            threshold = _select_threshold(scores, relevant, objective)
            weights, intercept = _fit_ridge(vectors, relevant)
            return cls(weights=weights, threshold=threshold - intercept)
        if method == FilterMethod.SIMILARITY:
            return cls._fit_similarity(vectors, relevant, objective)
        raise ValueError(f"Unknown semantic filter method {method!r}")

    @classmethod
    def _fit_similarity(
        cls, vectors: NDArray[np.floating], relevant: NDArray[np.bool_], objective: str
    ) -> Self:
        """Fit the maximum-similarity classifier on normalized embeddings."""
        positive_scores, negative_scores = _get_training_scores(vectors, relevant)

        best = cls(positive_vectors=vectors[relevant], negative_vectors=vectors[~relevant])
        best_score = -1.0
        quantiles = np.linspace(0, 1, N_THRESHOLDS)
        for alpha in ALPHAS:
            scores = positive_scores - alpha * negative_scores
            for min_positive_similarity in np.quantile(positive_scores, quantiles):
                for min_margin in np.quantile(scores, quantiles):
                    candidate = cls(alpha, float(min_positive_similarity), float(min_margin))
                    predictions = candidate._keep(positive_scores, negative_scores)
                    score = _get_metrics(predictions, relevant)[objective]
                    if score > best_score:
                        best_score = score
                        best.alpha = alpha
                        best.min_positive_similarity = float(min_positive_similarity)
                        best.min_margin = float(min_margin)

        reject_all_score = _get_metrics(np.zeros_like(relevant), relevant)[objective]
        if reject_all_score > best_score:
            best_score = reject_all_score
            # A threshold above the cosine similarity range also rejects unseen papers.
            best.min_positive_similarity = 2.0

        logger.info(
            f"trained on {len(relevant):,} papers: alpha={best.alpha}, "
            f"min_positive_similarity={best.min_positive_similarity:.4f}, "
            f"min_margin={best.min_margin:.4f}, training {objective} {best_score:.3f}"
        )
        return best

    def save(self, model_dir: Path) -> None:
        """Write the ridge coefficients and cutoff or the similarity examples and thresholds.

        Args:
            model_dir: Directory for `vectors.npz` and the similarity filter's
                `hyperparameters.json`.

        Raises:
            OSError: If the directory or model files cannot be written.
        """
        model_dir.mkdir(parents=True, exist_ok=True)
        vectors_path = model_dir / "vectors.npz"
        if self.weights is not None:
            with TemporaryDirectory(dir=model_dir) as temporary:
                output = Path(temporary) / vectors_path.name
                np.savez(output, weights=self.weights, threshold=self.threshold)
                output.replace(vectors_path)
            return

        hyperparameters = {
            "alpha": self.alpha,
            "min_positive_similarity": self.min_positive_similarity,
            "min_margin": self.min_margin,
        }
        (model_dir / "hyperparameters.json").write_text(json.dumps(hyperparameters, indent=2))
        np.savez(
            vectors_path,
            positive=self.positive_vectors,
            negative=self.negative_vectors,
        )

    @classmethod
    def load(cls, model_dir: Path) -> Self:
        """Read a saved ridge or similarity filter, including models from #57.

        Args:
            model_dir: Directory containing the saved model files.

        Returns:
            A filter reconstructed from the saved files.

        Raises:
            OSError: If a model file cannot be opened.
        """
        with np.load(model_dir / "vectors.npz") as vectors:
            if "weights" in vectors:
                return cls(
                    weights=vectors["weights"], threshold=float(vectors["threshold"].item())
                )
            hyperparameters = json.loads((model_dir / "hyperparameters.json").read_text())
            return cls(
                **hyperparameters,
                positive_vectors=vectors["positive"],
                negative_vectors=vectors["negative"],
            )

    def evaluate(self, dois: list[str], labels: list[bool]) -> dict[str, float]:
        """Compare the filter's predictions with the screening.

        Args:
            dois: DOIs of the screened papers.
            labels: Relevance labels aligned with `dois`.

        Returns:
            Accuracy, precision, recall, and F1 on papers with embeddings,
            plus the fraction of all test papers with an embedding.

        Raises:
            ValueError: If no test papers have embeddings.
        """
        predictions = self.predict(dois)
        scorable_predictions, scorable_labels = _scorable_predictions_and_labels(
            predictions, labels
        )
        metrics = _get_metrics(scorable_predictions, scorable_labels)
        metrics["coverage"] = scorable_predictions.size / len(predictions)
        return metrics

    @staticmethod
    def create_splits(
        dois: list[str], labels: list[bool], test_size: float = 0.2, seed: int = 0
    ) -> tuple[list[str], list[bool], list[str], list[bool]]:
        """Split the papers randomly into a training and a test part.

        Args:
            dois: DOIs of the screened papers.
            labels: Relevance labels aligned with `dois`.
            test_size: Fraction of papers to put in the test set.
            seed: Random seed for the split.

        Returns:
            Training DOIs and labels followed by test DOIs and labels.

        Raises:
            ValueError: If DOIs repeat after trimming whitespace and lowercasing.
        """
        if len({doi.strip().lower() for doi in dois}) != len(dois):
            raise ValueError("Cannot split papers with duplicate DOIs")

        order = np.random.default_rng(seed).permutation(len(dois))
        n_test = round(len(dois) * test_size)
        test, train = order[:n_test], order[n_test:]
        return (
            [dois[i] for i in train],
            [labels[i] for i in train],
            [dois[i] for i in test],
            [labels[i] for i in test],
        )

    @classmethod
    def cross_validation(
        cls,
        dois: list[str],
        labels: list[bool],
        n_splits: int = 5,
        objective: str = "f1",
        method: FilterMethod = FilterMethod.RIDGE,
    ) -> CrossValidationResult:
        """Train and evaluate on `n_splits` random splits.

        Args:
            dois: DOIs of the screened papers.
            labels: Relevance labels aligned with `dois`.
            n_splits: Number of random splits.
            objective: Metric to maximize when fitting each split's model.
            method: Scoring method.

        Returns:
            Mean and standard deviation of embedding coverage and each metric
            for the trained filter and the keep-all, keep-none, and random
            baselines. The random baseline matches the number of papers kept
            by the filter within each split.

        Raises:
            KeyError: If `objective` is an unknown metric.
            ValueError: If DOIs repeat, a training class has fewer than two
                papers with embeddings, or a test split has no embeddings.
        """
        results = []
        coverage = []
        for seed in range(n_splits):
            logger.info(f"Starting split {seed}")
            train_dois, train_labels, test_dois, test_labels = cls.create_splits(
                dois, labels, seed=seed
            )
            model = cls.train(train_dois, train_labels, objective=objective, method=method)
            predictions = model.predict(test_dois)
            scorable_predictions, scorable_labels = _scorable_predictions_and_labels(
                predictions, test_labels
            )
            coverage.append(scorable_predictions.size / len(predictions))

            results.append(
                {
                    "trained": _get_metrics(scorable_predictions, scorable_labels),
                    "keep_all": _get_metrics(np.ones_like(scorable_predictions), scorable_labels),
                    "keep_none": _get_metrics(
                        np.zeros_like(scorable_predictions), scorable_labels
                    ),
                    "random": _get_metrics(
                        _matched_random_predictions(scorable_predictions, seed), scorable_labels
                    ),
                }
            )
            logger.info(f"split {seed}: {results[-1]}")
        return {
            "coverage": (float(np.mean(coverage)), float(np.std(coverage))),
            "metrics": {
                method: {
                    metric: (
                        float(np.mean([split[method][metric] for split in results])),
                        float(np.std([split[method][metric] for split in results])),
                    )
                    for metric in metrics
                }
                for method, metrics in results[0].items()
            },
        }
