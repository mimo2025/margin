import pytest

from app.core import DocumentError, iter_matches, replace_target
from app.models import Document, Target


def document(text: str) -> Document:
    return Document(id="example", title="Example", text=text)


@pytest.mark.parametrize(
    ("text", "query", "spans"),
    [
        ("aaaaa", "aa", [(0, 2), (2, 4)]),
        ("Term term Term", "Term", [(0, 4), (10, 14)]),
        ("a.*b.*", ".*", [(1, 3), (4, 6)]),
        ("a b", " ", [(1, 2)]),
        ("😀30 days", "30 days", [(1, 8)]),
        ("cafe\u0301", "café", []),  # No Unicode normalization.
        ("nothing here", "missing", []),
        ("", "missing", []),
    ],
)
def test_search_is_literal_case_sensitive_and_nonoverlapping(text, query, spans):
    matches = list(iter_matches(document(text), query))
    assert [(match.target.start, match.target.end) for match in matches] == spans
    assert all(text[m.target.start : m.target.end] == m.target.text == query for m in matches)


def test_context_is_bounded_and_excludes_selected_text():
    matches = list(iter_matches(document("hit abc hit xyz hit"), "hit", context_chars=2))
    assert [(m.context_before, m.context_after) for m in matches] == [
        ("", " a"),
        ("c ", " x"),
        ("z ", ""),
    ]
    assert matches[0].document_id == "example"
    assert matches[0].title == "Example"
    assert matches[0].version == 1
    match = next(iter_matches(document("before hit after"), "hit", context_chars=0))
    assert match.context_before == match.context_after == ""


@pytest.mark.parametrize("query", ["", "x" * 1001])
def test_search_rejects_invalid_query(query):
    with pytest.raises(DocumentError) as failure:
        list(iter_matches(document("text"), query))
    assert failure.value.status_code == 422


@pytest.mark.parametrize("context_chars", [-1, 201])
def test_search_rejects_invalid_context_size(context_chars):
    with pytest.raises(DocumentError) as failure:
        list(iter_matches(document("text"), "text", context_chars=context_chars))
    assert failure.value.status_code == 422


@pytest.mark.parametrize("replacement", ["sixty (60) days", "now", "", "  later\n"])
def test_only_the_selected_occurrence_changes(replacement):
    text = "Pay in 30 days. End in 30 days."
    target = list(iter_matches(document(text), "30 days"))[1].target
    assert replace_target(text, target, replacement) == f"Pay in 30 days. End in {replacement}."


@pytest.mark.parametrize(
    ("start", "end", "original", "expected"),
    [(0, 3, "abc", "X def"), (4, 7, "def", "abc X"), (0, 7, "abc def", "X")],
)
def test_replacement_at_boundaries(start, end, original, expected):
    assert replace_target("abc def", Target(start=start, end=end, text=original), "X") == expected


@pytest.mark.parametrize(("start", "end"), [(1, 1), (2, 1), (0, 4)])
def test_invalid_ranges_fail_before_slicing(start, end):
    with pytest.raises(DocumentError) as failure:
        replace_target("abc", Target(start=start, end=end, text="a"), "X")
    assert failure.value.status_code == 422


def test_target_text_must_match():
    with pytest.raises(DocumentError) as failure:
        replace_target("abc", Target(start=0, end=1, text="b"), "X")
    assert failure.value.status_code == 409


def test_search_and_precise_replacement_on_ten_mib_document():
    # ASCII makes the byte size unambiguous. This is correctness, not a timing SLA.
    size = 10 * 1024 * 1024
    needle = "30 days"
    half = size // 2
    text = "a" * half + needle + "b" * (size - half - 2 * len(needle)) + needle
    assert len(text.encode("utf-8")) == size
    matches = list(iter_matches(document(text), needle))
    assert [(m.target.start, m.target.end) for m in matches] == [
        (half, half + len(needle)),
        (size - len(needle), size),
    ]
    updated = replace_target(text, matches[0].target, "60 days")
    assert updated == text[:half] + "60 days" + text[half + len(needle) :]
    assert updated.count(needle) == 1
    assert updated.endswith(needle)
