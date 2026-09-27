"""Deterministic search and replacement; no HTTP, storage, or network calls."""

from collections.abc import Iterator

from app.models import MAX_CONTEXT_CHARS, MAX_QUERY_LENGTH, Document, SearchMatch, Target


class DocumentError(Exception):
    """An expected failure with a safe, content-free message for the caller."""

    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code


def iter_matches(
    document: Document, query: str, *, context_chars: int = 60
) -> Iterator[SearchMatch]:
    """Yield literal, case-sensitive, nonoverlapping matches in document order.

    Iteration lets the caller stop once its global result limit is reached.
    Each match uses one immutable document snapshot, including its version.
    """
    if not 1 <= len(query) <= MAX_QUERY_LENGTH:
        raise DocumentError(f"Query must contain 1–{MAX_QUERY_LENGTH} characters.", 422)
    if not 0 <= context_chars <= MAX_CONTEXT_CHARS:
        raise DocumentError(f"Context must be between 0 and {MAX_CONTEXT_CHARS} characters.", 422)

    cursor = 0
    while (start := document.text.find(query, cursor)) != -1:
        end = start + len(query)
        yield SearchMatch(
            document_id=document.id,
            title=document.title,
            version=document.version,
            target=Target(start=start, end=end, text=query),
            context_before=document.text[max(0, start - context_chars) : start],
            context_after=document.text[end : end + context_chars],
        )
        cursor = end  # Moving past the match deliberately excludes overlaps.


def replace_target(text: str, target: Target, replacement: str) -> str:
    """Replace exactly one validated span, allowing an empty replacement."""
    if not 0 <= target.start < target.end <= len(text):
        raise DocumentError("Target range must be nonempty and within the document.", 422)
    if text[target.start : target.end] != target.text:
        raise DocumentError("Target text does not match. Search again before saving.", 409)
    return text[: target.start] + replacement + text[target.end :]
