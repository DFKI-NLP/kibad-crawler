"""Kibad crawler: Semantic Scholar datasets, diffs, recommendations, and relevance filter."""

from .relevance import filter_papers
from .s2_api import (
    S2Client,
    chunker,
    download_all_papers,
    download_bulk_paper,
    download_dataset,
    download_file,
    download_paper_batch,
)
from .s2_models import (
    DiffEntry,
    DiffRequest,
    DiffResponse,
    PaperBatchRequest,
    RecommendationsResponse,
    RelevanceFilter,
)

__all__ = [
    "DiffEntry",
    "DiffRequest",
    "DiffResponse",
    "PaperBatchRequest",
    "RecommendationsResponse",
    "RelevanceFilter",
    "S2Client",
    "chunker",
    "download_all_papers",
    "download_bulk_paper",
    "download_dataset",
    "download_file",
    "download_paper_batch",
    "filter_papers",
]
