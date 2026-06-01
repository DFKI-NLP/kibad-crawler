"""Relevance filter for Semantic Scholar papers (additional input for selection)."""

from .s2_models import RelevanceFilter


def filter_papers(
    papers: list[dict],
    criteria: RelevanceFilter,
) -> list[dict]:
    """Filter a list of paper dicts (S2 bulk API shape) by relevance criteria.

    Papers must pass every non-empty criterion. If criteria.is_empty(), all papers are returned.

    Args:
        papers (list): List of paper objects as returned by the S2 Graph API (e.g. bulk paper).
        criteria (RelevanceFilter): Optional min_citation_count, venue_ids, fields_of_study, keywords.

    Returns:
        list: Subset of papers that satisfy all criteria.
    """
    if not papers or criteria.is_empty():
        return list(papers)

    out: list[dict] = []
    for p in papers:
        if not isinstance(p, dict):
            continue
        if not _passes_citation_filter(p, criteria):
            continue
        if not _passes_venue_filter(p, criteria):
            continue
        if not _passes_fields_of_study_filter(p, criteria):
            continue
        if not _passes_keywords_filter(p, criteria):
            continue
        out.append(p)
    return out


def _passes_citation_filter(paper: dict, criteria: RelevanceFilter) -> bool:
    """Check citationCount >= min_citation_count when criterion is set."""
    if criteria.min_citation_count is None:
        return True
    count = paper.get("citationCount")
    if count is None:
        return False
    try:
        return int(count) >= criteria.min_citation_count
    except (TypeError, ValueError):
        return False


def _passes_venue_filter(paper: dict, criteria: RelevanceFilter) -> bool:
    """Check publicationVenue.id or venue.id is in the whitelist when set."""
    if not criteria.venue_ids:
        return True
    venue = paper.get("publicationVenue") or paper.get("venue")
    if isinstance(venue, dict):
        vid = venue.get("id") or venue.get("venueId")
    else:
        vid = None
    if vid is None:
        return False
    return str(vid) in criteria.venue_ids


def _passes_fields_of_study_filter(paper: dict, criteria: RelevanceFilter) -> bool:
    """Check at least one of the requested fields in fieldsOfStudy / s2FieldsOfStudy."""
    if not criteria.fields_of_study:
        return True
    fos = paper.get("fieldsOfStudy") or paper.get("s2FieldsOfStudy") or []
    if not isinstance(fos, list):
        return False
    want = {s.strip().lower() for s in criteria.fields_of_study if s}
    if not want:
        return True
    for f in fos:
        if isinstance(f, str) and f.lower() in want:
            return True
    return False


def _passes_keywords_filter(paper: dict, criteria: RelevanceFilter) -> bool:
    """Check at least one keyword in title or abstract (case-insensitive)."""
    if not criteria.keywords:
        return True
    title = (paper.get("title") or "") or ""
    abstract = (paper.get("abstract") or "") or ""
    text = f"{title} {abstract}".lower()
    for kw in criteria.keywords:
        if kw and kw.lower() in text:
            return True
    return False
