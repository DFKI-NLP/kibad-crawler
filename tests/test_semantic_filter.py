"""Test the semantic filter with made up embeddings, without API calls."""

import json

import numpy as np
import pytest

from kibad_crawler import semantic_filter
from kibad_crawler.semantic_filter import SemanticFilter

# relevant papers point along the first axis, not relevant ones along the second
EMBEDDINGS = {
    "r1": [1.0, 0.1, 0.0],
    "r2": [1.0, 0.2, 0.1],
    "r3": [0.9, 0.0, 0.2],
    "r4": [1.0, 0.15, 0.05],
    "n1": [0.1, 1.0, 0.0],
    "n2": [0.2, 1.0, 0.1],
    "n3": [0.0, 0.9, 0.2],
    "missing": None,
}
DOIS = ["r1", "n1", "r2", "n2", "r3", "n3", "r4"]
LABELS = [doi.startswith("r") for doi in DOIS]


@pytest.fixture
def embeddings(monkeypatch):
    """Answer `get_embeddings` from `EMBEDDINGS`."""
    monkeypatch.setattr(
        semantic_filter, "get_embeddings", lambda dois: {doi: EMBEDDINGS[doi] for doi in dois}
    )


def test_get_embeddings_requests_only_new_dois(tmp_path, monkeypatch):
    requested = []

    def fake_batch(ids, fields):
        requested.extend(ids)
        answers = {
            "DOI:10.1/a": {
                "paperId": "a",
                "embedding": {"model": "specter_v2", "vector": [1.0, 2.0]},
            },
            "DOI:10.1/b": {"paperId": "b", "embedding": None},
        }
        return [answers.get(paper_id) for paper_id in ids]

    monkeypatch.setattr(semantic_filter.academic_graph, "batch", fake_batch)
    monkeypatch.setattr(semantic_filter, "DELAY_BETWEEN_BATCHES", 0)
    cache_path = tmp_path / "embeddings.json"

    first = semantic_filter.get_embeddings(["10.1/a", "10.1/b", "10.1/c"], cache_path)
    second = semantic_filter.get_embeddings(["10.1/a", "10.1/c"], cache_path)

    assert first == {"10.1/a": [1.0, 2.0], "10.1/b": None, "10.1/c": None}
    assert second == {"10.1/a": [1.0, 2.0], "10.1/c": None}
    assert sorted(requested) == ["DOI:10.1/a", "DOI:10.1/b", "DOI:10.1/c"]
    assert json.loads(cache_path.read_text())["10.1/a"] == [1.0, 2.0]


def test_get_vectors(embeddings):
    vectors, available = semantic_filter.get_vectors(["r1", "missing", "n1"])

    assert available.tolist() == [True, False, True]
    assert vectors.tolist() == [EMBEDDINGS["r1"], EMBEDDINGS["n1"]]


def test_get_metrics():
    predictions = np.array([True, True, False, False])
    labels = np.array([True, False, True, True])

    assert semantic_filter.get_metrics(predictions, labels) == pytest.approx(
        {
            "accuracy": 0.25,
            "precision": 0.5,
            "recall": 1 / 3,
            "f1": 0.4,
        }
    )


def test_get_training_scores():
    vectors = np.array([[1.0, 0.0], [0.6, 0.8], [0.0, 1.0]])
    relevant = np.array([True, True, False])

    positive_scores, negative_scores = semantic_filter.get_training_scores(vectors, relevant)

    # each relevant paper only sees the other relevant one, the cosine 0.6
    assert positive_scores.tolist() == pytest.approx([0.6, 0.6, 0.8])
    assert negative_scores.tolist() == pytest.approx([0.0, 0.8, -np.inf])


def test_keep():
    model = SemanticFilter(alpha=1.0, min_positive_similarity=0.6, min_margin=0.3)

    kept = model.keep(np.array([0.9, 0.5, 0.9]), np.array([0.2, 0.0, 0.8]))

    # the second fails the similarity, the third the margin 0.9 - 1.0 * 0.8
    assert kept.tolist() == [True, False, False]


def test_predict(embeddings):
    model = SemanticFilter(
        alpha=1.0,
        min_positive_similarity=0.5,
        min_margin=0.0,
        positive_vectors=np.array([EMBEDDINGS["r1"]]),
        negative_vectors=np.array([EMBEDDINGS["n1"]]),
    )

    assert model.predict(["r2", "missing", "n2"]) == [True, None, False]


def test_predict_without_embeddings(embeddings):
    assert SemanticFilter().predict(["missing", "missing"]) == [None, None]


def test_train_compares_with_the_other_papers(embeddings):
    model = SemanticFilter.train(DOIS, LABELS)

    # without leaving a paper out, every relevant paper has a similarity of 1
    # and the threshold would be the highest possible
    assert model.min_positive_similarity < 1.0
    assert model.predict(DOIS) == LABELS
    assert model.positive_vectors.shape == (4, 3)
    assert model.negative_vectors.shape == (3, 3)


def test_train_maximizes_selected_metric(embeddings, monkeypatch):
    labels = [True, True, False, False, False, False, False]
    positive_scores = np.array([0.4, 0.3, 0.8, 0.7, 0.6, 0.5, 0.2])
    negative_scores = np.zeros(len(labels))
    monkeypatch.setattr(
        semantic_filter, "get_training_scores", lambda *_: (positive_scores, negative_scores)
    )

    accuracy_model = SemanticFilter.train(DOIS, labels)
    f1_model = SemanticFilter.train(DOIS, labels, objective="f1")
    accuracy_kept = accuracy_model.keep(positive_scores, negative_scores)
    f1_kept = f1_model.keep(positive_scores, negative_scores)

    assert accuracy_kept.sum() == 0
    assert f1_kept.sum() == 6


def test_train_considers_rejecting_all_when_scores_are_tied(monkeypatch):
    dois = ["a", "b", "c", "d", "e"]
    labels = [True, True, False, False, False]
    monkeypatch.setattr(
        semantic_filter, "get_embeddings", lambda dois: dict.fromkeys(dois, [1.0, 0.0])
    )

    accuracy_model = SemanticFilter.train(dois, labels)
    f1_model = SemanticFilter.train(dois, labels, objective="f1")

    assert accuracy_model.predict(dois) == [False] * len(dois)
    assert f1_model.predict(dois) == [True] * len(dois)


def test_save_and_load(tmp_path):
    model = SemanticFilter(0.5, 0.7, 0.1, np.ones((2, 3)), np.zeros((1, 3)))

    model.save(tmp_path / "model")
    loaded = SemanticFilter.load(tmp_path / "model")

    assert (loaded.alpha, loaded.min_positive_similarity, loaded.min_margin) == (0.5, 0.7, 0.1)
    assert np.array_equal(loaded.positive_vectors, model.positive_vectors)
    assert np.array_equal(loaded.negative_vectors, model.negative_vectors)


def test_evaluate(embeddings, tmp_path):
    SemanticFilter.train(DOIS, LABELS).save(tmp_path / "model")

    metrics = SemanticFilter.evaluate(
        tmp_path / "model", ["r1", "n1", "missing"], [True, False, True]
    )

    assert metrics == {"accuracy": 1.0, "precision": 1.0, "recall": 1.0, "f1": 1.0}


def test_evaluate_without_embeddings(embeddings, tmp_path):
    model_dir = tmp_path / "model"
    SemanticFilter().save(model_dir)

    with pytest.raises(ValueError, match="No test papers have embeddings"):
        SemanticFilter.evaluate(model_dir, ["missing"], [True])


def test_create_splits():
    dois = [f"d{i}" for i in range(10)]
    labels = [i % 2 == 0 for i in range(10)]

    train_dois, train_labels, test_dois, test_labels = SemanticFilter.create_splits(
        dois, labels, seed=1
    )

    assert (len(train_dois), len(test_dois)) == (8, 2)
    assert sorted(train_dois + test_dois) == sorted(dois)
    assert [labels[dois.index(doi)] for doi in test_dois] == test_labels
    assert SemanticFilter.create_splits(dois, labels, seed=1)[2] == test_dois
    assert SemanticFilter.create_splits(dois, labels, seed=2)[2] != test_dois


def test_create_splits_rejects_duplicate_dois():
    with pytest.raises(ValueError, match="duplicate DOIs"):
        SemanticFilter.create_splits(["10.1/paper", " 10.1/PAPER "], [True, False])


def test_cross_validation_requires_two_embeddings_per_class(embeddings, tmp_path):
    dois = ["r1", "missing", "n1", "n2", "n3"]
    labels = [True, True, False, False, False]

    with pytest.raises(ValueError, match=r"split 0.*Found 1 relevant and 2 irrelevant"):
        SemanticFilter.cross_validation(dois, labels, tmp_path, n_splits=1)

    assert not (tmp_path / "split_0").exists()


def test_cross_validation(embeddings, tmp_path):
    results = SemanticFilter.cross_validation(DOIS, LABELS, tmp_path, n_splits=3)

    assert results["coverage"] == (1.0, 0.0)
    assert set(results["metrics"]) == {"trained", "keep_all", "keep_none", "random"}
    for metrics in results["metrics"].values():
        assert set(metrics) == {"accuracy", "precision", "recall", "f1"}
        assert all(len(value) == 2 for value in metrics.values())
    assert sorted(path.name for path in tmp_path.iterdir()) == ["split_0", "split_1", "split_2"]


def test_cross_validation_scores_baselines_on_scorable_papers(monkeypatch, tmp_path):
    test_dois = ["a", "b", "c", "d", "missing"]
    test_labels = [True, True, False, False, True]
    monkeypatch.setattr(
        SemanticFilter, "create_splits", lambda *args, **kwargs: ([], [], test_dois, test_labels)
    )
    monkeypatch.setattr(SemanticFilter, "train", lambda *args, **kwargs: SemanticFilter())
    monkeypatch.setattr(
        SemanticFilter, "predict", lambda self, dois: [True, True, False, False, None]
    )

    results = SemanticFilter.cross_validation(test_dois, test_labels, tmp_path, n_splits=1)

    assert results["coverage"] == (0.8, 0.0)
    assert results["metrics"] == {
        "trained": {
            "accuracy": (1.0, 0.0),
            "precision": (1.0, 0.0),
            "recall": (1.0, 0.0),
            "f1": (1.0, 0.0),
        },
        "keep_all": {
            "accuracy": (0.5, 0.0),
            "precision": (0.5, 0.0),
            "recall": (1.0, 0.0),
            "f1": (2 / 3, 0.0),
        },
        "keep_none": {
            "accuracy": (0.5, 0.0),
            "precision": (0.0, 0.0),
            "recall": (0.0, 0.0),
            "f1": (0.0, 0.0),
        },
        "random": {
            "accuracy": (0.5, 0.0),
            "precision": (0.5, 0.0),
            "recall": (0.5, 0.0),
            "f1": (0.5, 0.0),
        },
    }
