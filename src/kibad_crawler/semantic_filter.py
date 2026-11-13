"""Semantic filter that keeps the papers that are similar to papers screened as
relevant and not similar to papers screened as not relevant.

Papers are represented by the SPECTER2 embeddings that the Academic Graph API
of Semantic Scholar provides. A paper is scored by its highest cosine
similarity to the relevant examples minus `alpha` times its highest similarity
to the not relevant examples. The thresholds are estimated on screened papers
of one screening table, since the examples of one table encode its own task.
"""

from dataclasses import dataclass, field
import json
from pathlib import Path
import time
from typing import TypedDict

from loguru import logger
import numpy as np

from kibad_crawler.config import INTERIM_DATA_DIR
from kibad_crawler.semantic_scholar import academic_graph
from kibad_crawler.utils import chunker

EMBEDDINGS_FILE = INTERIM_DATA_DIR / "semantic_filter" / "embeddings.json"
FIELDS = "paperId,embedding.specter_v2"
DELAY_BETWEEN_BATCHES = 3
ALPHAS = [0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0]
N_THRESHOLDS = 21


class CrossValidationResult(TypedDict):
    """Mean and standard deviation of coverage and the metrics for each method."""

    coverage: tuple[float, float]
    metrics: dict[str, dict[str, tuple[float, float]]]


def get_embeddings(dois: list[str], cache_path: Path = EMBEDDINGS_FILE) -> dict[str, list | None]:
    """Return the SPECTER2 embedding of each DOI, requesting only the ones that
    are not in the cache yet.

    Args:
        dois (list[str]): DOIs of the papers.
        cache_path (Path, optional): JSON file with the embeddings requested
            before. Defaults to `EMBEDDINGS_FILE`.

    Returns:
        dict[str, list | None]: Embedding per DOI, None where Semantic Scholar
            does not know the paper or has no embedding for it.
    """
    cache: dict[str, list | None] = (
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


def get_vectors(dois: list[str]) -> tuple[np.ndarray, np.ndarray]:
    """Return the embeddings of the papers that have one.

    Args:
        dois (list[str]): DOIs of the papers.

    Returns:
        tuple[np.ndarray, np.ndarray]: Embeddings as rows, and a boolean mask
            over `dois` that is True for the papers with an embedding.
    """
    embeddings = get_embeddings(dois)
    available = np.array([embeddings[doi] is not None for doi in dois], dtype=bool)
    if not available.all():
        logger.info(f"{(~available).sum():,} of {len(dois):,} papers without an embedding skipped")
    vectors = [embeddings[doi] for doi in dois if embeddings[doi] is not None]
    return (np.array(vectors) if vectors else np.empty((0, 0))), available


def normalize(vectors: np.ndarray) -> np.ndarray:
    """Return the vectors scaled to length 1, so that the dot product is the
    cosine similarity."""
    return vectors / np.linalg.norm(vectors, axis=1, keepdims=True)


def _scorable_predictions_and_labels(
    predictions: list[bool | None], labels: list[bool]
) -> tuple[np.ndarray, np.ndarray]:
    """Return the aligned predictions and labels for papers with embeddings."""
    available = np.array([prediction is not None for prediction in predictions], dtype=bool)
    if not available.any():
        raise ValueError("No test papers have embeddings")
    scorable_predictions = np.array(predictions, dtype=bool)[available]
    return scorable_predictions, np.array(labels, dtype=bool)[available]


def get_metrics(predictions: np.ndarray, labels: np.ndarray) -> dict[str, float]:
    """Return accuracy, precision, recall and F1 of binary predictions.

    Args:
        predictions (np.ndarray): True for the papers that are kept.
        labels (np.ndarray): True for the papers screened as relevant.

    Returns:
        dict[str, float]: Accuracy, precision, recall and F1.
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


def get_training_scores(
    vectors: np.ndarray, relevant: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """Return the highest similarity of each paper to the other relevant and
    the other not relevant papers.

    A paper is not compared with itself, otherwise a relevant paper has a
    similarity of 1 and the thresholds are estimated on that.

    Args:
        vectors (np.ndarray): Normalized embeddings of the papers as rows.
        relevant (np.ndarray): True for the papers screened as relevant.

    Returns:
        tuple[np.ndarray, np.ndarray]: Highest similarity to a relevant and to
            a not relevant paper.
    """
    similarities = vectors @ vectors.T
    np.fill_diagonal(similarities, -np.inf)
    return similarities[:, relevant].max(axis=1), similarities[:, ~relevant].max(axis=1)


@dataclass
class SemanticFilter:
    """Hyperparameters and examples of the semantic filter."""

    alpha: float = 1.0
    min_positive_similarity: float = -1.0
    min_margin: float = -3.0
    positive_vectors: np.ndarray = field(default_factory=lambda: np.empty((0, 0)))
    negative_vectors: np.ndarray = field(default_factory=lambda: np.empty((0, 0)))

    def keep(self, positive_scores: np.ndarray, negative_scores: np.ndarray) -> np.ndarray:
        """Return True for the papers whose similarity scores pass the thresholds."""
        scores = positive_scores - self.alpha * negative_scores
        return (positive_scores >= self.min_positive_similarity) & (scores >= self.min_margin)

    def predict(self, dois: list[str]) -> list[bool | None]:
        """Decide for each paper whether it is kept.

        Args:
            dois (list[str]): DOIs of the papers.

        Returns:
            list[bool | None]: True for the papers that are kept, None for the
                papers without an embedding.
        """
        vectors, available = get_vectors(dois)
        predictions: list[bool | None] = [None] * len(dois)
        if not available.any():
            return predictions
        vectors = normalize(vectors)
        positive_scores = (vectors @ normalize(self.positive_vectors).T).max(axis=1)
        negative_scores = (vectors @ normalize(self.negative_vectors).T).max(axis=1)
        scorable_predictions = self.keep(positive_scores, negative_scores)
        for index, decision in zip(np.flatnonzero(available), scorable_predictions):
            predictions[index] = bool(decision)
        return predictions

    @classmethod
    def train(
        cls, dois: list[str], labels: list[bool], objective: str = "accuracy"
    ) -> "SemanticFilter":
        """Estimate the hyperparameters that maximize the objective on the given
        papers, which also become the examples of the filter.

        Each paper is compared with the other papers only, see
        `get_training_scores`.

        Args:
            dois (list[str]): DOIs of the screened papers.
            labels (list[bool]): True for the papers screened as relevant.
            objective (str, optional): Metric from `get_metrics` to maximize.
                Defaults to "accuracy".

        Returns:
            SemanticFilter: Filter with the best hyperparameters and the
                embeddings of the papers as examples.

        Raises:
            ValueError: If either class has fewer than two papers with embeddings.
        """
        vectors, available = get_vectors(dois)
        relevant = np.array(labels, dtype=bool)[available]
        n_relevant = int(relevant.sum())
        n_irrelevant = relevant.size - n_relevant
        if min(n_relevant, n_irrelevant) < 2:
            raise ValueError(
                "Training requires at least two relevant and two irrelevant papers "
                f"with embeddings. Found {n_relevant} relevant and {n_irrelevant} irrelevant."
            )

        vectors = normalize(vectors)
        positive_scores, negative_scores = get_training_scores(vectors, relevant)

        best = cls(positive_vectors=vectors[relevant], negative_vectors=vectors[~relevant])
        best_score = -1.0
        quantiles = np.linspace(0, 1, N_THRESHOLDS)
        for alpha in ALPHAS:
            scores = positive_scores - alpha * negative_scores
            for min_positive_similarity in np.quantile(positive_scores, quantiles):
                for min_margin in np.quantile(scores, quantiles):
                    candidate = cls(alpha, float(min_positive_similarity), float(min_margin))
                    predictions = candidate.keep(positive_scores, negative_scores)
                    score = get_metrics(predictions, relevant)[objective]
                    if score > best_score:
                        best_score = score
                        best.alpha = alpha
                        best.min_positive_similarity = float(min_positive_similarity)
                        best.min_margin = float(min_margin)

        reject_all_score = get_metrics(np.zeros_like(relevant), relevant)[objective]
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

    def save(self, model_dir: Path):
        """Write the hyperparameters to `hyperparameters.json` and the examples
        to `vectors.npz` in `model_dir`."""
        model_dir.mkdir(parents=True, exist_ok=True)
        hyperparameters = {
            "alpha": self.alpha,
            "min_positive_similarity": self.min_positive_similarity,
            "min_margin": self.min_margin,
        }
        (model_dir / "hyperparameters.json").write_text(json.dumps(hyperparameters, indent=2))
        np.savez(
            model_dir / "vectors.npz",
            positive=self.positive_vectors,
            negative=self.negative_vectors,
        )

    @classmethod
    def load(cls, model_dir: Path) -> "SemanticFilter":
        """Read a filter written by `save`."""
        hyperparameters = json.loads((model_dir / "hyperparameters.json").read_text())
        vectors = np.load(model_dir / "vectors.npz")
        return cls(
            **hyperparameters,
            positive_vectors=vectors["positive"],
            negative_vectors=vectors["negative"],
        )

    def evaluate(self, dois: list[str], labels: list[bool]) -> dict[str, float]:
        """Compare the filter's predictions with the screening.

        Args:
            dois (list[str]): DOIs of the screened papers.
            labels (list[bool]): True for the papers screened as relevant.

        Returns:
            dict[str, float]: Metrics on the papers with an embedding, see
                `get_metrics`, and coverage as the fraction of test papers
                with an embedding.

        Raises:
            ValueError: If no test papers have embeddings.
        """
        predictions = self.predict(dois)
        scorable_predictions, scorable_labels = _scorable_predictions_and_labels(
            predictions, labels
        )
        metrics = get_metrics(scorable_predictions, scorable_labels)
        metrics["coverage"] = scorable_predictions.size / len(predictions)
        return metrics

    @staticmethod
    def create_splits(
        dois: list[str], labels: list[bool], test_size: float = 0.2, seed: int = 0
    ) -> tuple[list[str], list[bool], list[str], list[bool]]:
        """Split the papers randomly into a training and a test part.

        Args:
            dois (list[str]): DOIs of the screened papers.
            labels (list[bool]): True for the papers screened as relevant.
            test_size (float, optional): Share of the test part. Defaults to 0.2.
            seed (int, optional): Seed of the random split. Defaults to 0.

        Returns:
            tuple[list[str], list[bool], list[str], list[bool]]: DOIs and
                labels of the training part, then of the test part.

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
        objective: str = "accuracy",
    ) -> CrossValidationResult:
        """Train and evaluate on `n_splits` random splits.

        Args:
            dois (list[str]): DOIs of the screened papers.
            labels (list[bool]): True for the papers screened as relevant.
            n_splits (int, optional): Number of splits. Defaults to 5.
            objective (str, optional): Training metric to maximize. Defaults to "accuracy".

        Returns:
            CrossValidationResult: Mean and standard deviation of embedding
                coverage and of each metric for the filter and its baselines.
        """
        results = []
        coverage = []
        for seed in range(n_splits):
            logger.info(f"Starting split {seed}")
            train_dois, train_labels, test_dois, test_labels = cls.create_splits(
                dois, labels, seed=seed
            )
            model = cls.train(train_dois, train_labels, objective=objective)
            predictions = model.predict(test_dois)
            scorable_predictions, scorable_labels = _scorable_predictions_and_labels(
                predictions, test_labels
            )
            coverage.append(scorable_predictions.size / len(predictions))

            random_predictions = np.zeros_like(scorable_predictions)
            # Use a separate random stream from the train/test split.
            rng = np.random.default_rng([seed, 1])
            random_indices = rng.choice(
                scorable_predictions.size, size=int(scorable_predictions.sum()), replace=False
            )
            random_predictions[random_indices] = True
            results.append(
                {
                    "trained": get_metrics(scorable_predictions, scorable_labels),
                    "keep_all": get_metrics(np.ones_like(scorable_predictions), scorable_labels),
                    "keep_none": get_metrics(np.zeros_like(scorable_predictions), scorable_labels),
                    "random": get_metrics(random_predictions, scorable_labels),
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
