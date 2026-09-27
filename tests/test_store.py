from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from pydantic import ValidationError

from app.core import DocumentError
from app.models import Document, EditRequest, Target
from app.store import DocumentStore


@pytest.fixture
def store():
    return DocumentStore(
        [
            Document(id="first", title="First", text="pay 30 days; end 30 days"),
            Document(id="second", title="Second", text="review in 30 days"),
        ]
    )


def edit_request(replacement="60 days", expected_version=1):
    return EditRequest(
        expected_version=expected_version,
        target=Target(start=4, end=11, text="30 days"),
        replacement=replacement,
    )


def test_search_filter_and_global_limit(store):
    result = store.search("30 days", limit=2)
    assert [match.document_id for match in result.matches] == ["first", "first"]
    assert result.truncated is True
    all_matches = store.search("30 days", limit=3)
    assert [match.document_id for match in all_matches.matches] == ["first", "first", "second"]
    assert all_matches.truncated is False  # Exactly at the cap, with no extra match.
    filtered = store.search("30 days", document_id="second")
    assert [match.document_id for match in filtered.matches] == ["second"]
    assert filtered.truncated is False
    missing = store.search("absent")
    assert missing.matches == []
    assert missing.truncated is False


def test_list_returns_metadata_only(store):
    assert [item.model_dump() for item in store.list_documents()] == [
        {"id": "first", "title": "First", "version": 1},
        {"id": "second", "title": "Second", "version": 1},
    ]


def test_edit_creates_new_snapshot_and_updates_search_version(store):
    before = store.get("first")
    updated = store.edit("first", edit_request())
    assert updated.text == "pay 60 days; end 30 days"
    assert updated.version == 2
    assert store.get("first") == updated
    assert before.text == "pay 30 days; end 30 days"
    assert before.version == 1
    assert store.search("60 days").matches[0].version == 2
    assert store.get("second").version == 1
    with pytest.raises(ValidationError):
        before.text = "external mutation"


@pytest.mark.parametrize(
    ("edit_case", "status_code"),
    [
        (edit_request(expected_version=2), 409),
        (
            EditRequest(expected_version=1, target=Target(start=4, end=11, text="90 days"), replacement=""),
            409,
        ),
        (
            EditRequest(expected_version=1, target=Target(start=4, end=999, text="30 days"), replacement=""),
            422,
        ),
    ],
)
def test_failed_edits_leave_text_and_version_unchanged(store, edit_case, status_code):
    before = store.get("first")
    with pytest.raises(DocumentError) as failure:
        store.edit("first", edit_case)
    assert failure.value.status_code == status_code
    assert store.get("first") == before


def test_stale_version_is_checked_before_content_dependent_range(store):
    store.edit("first", edit_request())
    request = EditRequest(
        expected_version=1, target=Target(start=4, end=999, text="30 days"), replacement=""
    )
    with pytest.raises(DocumentError) as failure:
        store.edit("first", request)
    assert failure.value.status_code == 409
    assert store.get("first").version == 2


@pytest.mark.parametrize("operation", ["get", "search", "edit"])
def test_missing_document_is_an_explicit_error(store, operation):
    with pytest.raises(DocumentError) as failure:
        if operation == "get":
            store.get("absent")
        elif operation == "search":
            store.search("text", document_id="absent")
        else:
            store.edit("absent", edit_request())
    assert failure.value.status_code == 404


@pytest.mark.parametrize("kwargs", [{"limit": 0}, {"limit": 101}, {"context_chars": -1}])
def test_invalid_search_options_fail_even_with_no_documents(kwargs):
    with pytest.raises(DocumentError) as failure:
        DocumentStore([]).search("term", **kwargs)
    assert failure.value.status_code == 422


def test_two_writers_with_same_version_only_one_succeeds(store):
    ready = Barrier(2)

    def save(replacement):
        ready.wait(timeout=5)
        try:
            return store.edit("first", edit_request(replacement))
        except DocumentError as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(save, ["60 days", "90 days"]))
    successes = [outcome for outcome in outcomes if isinstance(outcome, Document)]
    conflicts = [outcome for outcome in outcomes if isinstance(outcome, DocumentError)]
    assert len(successes) == len(conflicts) == 1
    assert conflicts[0].status_code == 409
    assert store.get("first") == successes[0]
    assert store.get("first").version == 2
    assert store.get("first").text in ("pay 60 days; end 30 days", "pay 90 days; end 30 days")
