"""Dataclasses for Semantic Scholar API: diff metadata, recommendations, and relevance criteria."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DiffRequest:
    """Parameters for requesting an incremental diff between two releases."""

    from_release: str
    to_release: str
    dataset_name: str


@dataclass
class DiffFileInfo:
    """Single file entry in a diff (update or delete)."""

    url: str


@dataclass
class DiffEntry:
    """One diff entry: lists of update and deleted file URLs/info."""

    update_files: list[DiffFileInfo] = field(default_factory=list)
    deleted_files: list[DiffFileInfo] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DiffEntry":
        def to_file_infos(items: list[Any]) -> list[DiffFileInfo]:
            out: list[DiffFileInfo] = []
            for x in items or []:
                url = x.get("url") if isinstance(x, dict) else (x if isinstance(x, str) else None)
                if url:
                    out.append(DiffFileInfo(url=url))
            return out

        return cls(
            update_files=to_file_infos(data.get("update_files") or []),
            deleted_files=to_file_infos(data.get("deleted_files") or []),
        )


@dataclass
class DiffResponse:
    """Parsed response from the incremental diff endpoint."""

    dataset: str = ""
    start_release: str = ""
    end_release: str = ""
    diffs: list[DiffEntry] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DiffResponse":
        diffs = [
            DiffEntry.from_dict(entry) if isinstance(entry, dict) else DiffEntry()
            for entry in (data.get("diffs") or [])
        ]
        return cls(
            dataset=data.get("dataset", ""),
            start_release=data.get("start_release", ""),
            end_release=data.get("end_release", ""),
            diffs=diffs,
        )


@dataclass
class RecommendationsResponse:
    """Parsed response from the Recommendations API (paper-based)."""

    recommendations: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RecommendationsResponse":
        recs = data.get("recommendations") or data.get("papers") or []
        if isinstance(recs, list):
            return cls(recommendations=[r for r in recs if isinstance(r, dict)])
        return cls()


@dataclass
class PaperBatchRequest:
    """Parameters for a bulk paper metadata request."""

    paper_ids: list[str]
    fields: str = (
        "corpusId,url,title,abstract,venue,publicationVenue,year,citationCount,"
        "isOpenAccess,openAccessPdf,publicationDate,journal,fieldsOfStudy,"
        "s2FieldsOfStudy,authors,tldr,publicationTypes,textAvailability"
    )


@dataclass
class RelevanceFilter:
    """Criteria to filter papers by relevance (additional input for selection).

    All criteria are optional. A paper is kept only if it passes every criterion
    that is set (non-empty / not None). Empty or None means "do not filter on this".
    """

    min_citation_count: int | None = None
    """Keep only papers with citationCount >= this."""

    venue_ids: list[str] | None = None
    """Keep only papers whose venue ID is in this whitelist (e.g. publicationVenue.id)."""

    fields_of_study: list[str] | None = None
    """Keep only papers that have at least one of these in fieldsOfStudy or s2FieldsOfStudy."""

    keywords: list[str] | None = None
    """Keep only papers where at least one keyword appears in title or abstract (case-insensitive)."""

    def is_empty(self) -> bool:
        """True if no filter criterion is set."""
        return (
            self.min_citation_count is None
            and (self.venue_ids is None or len(self.venue_ids) == 0)
            and (self.fields_of_study is None or len(self.fields_of_study) == 0)
            and (self.keywords is None or len(self.keywords) == 0)
        )
