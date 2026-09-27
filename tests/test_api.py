"""Exercise HTTP validation and the search-to-edit contract with isolated state."""

from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from app.core import DocumentError
from app.main import create_app
from app.models import (
    MAX_CONTEXT_CHARS,
    MAX_QUERY_LENGTH,
    MAX_REPLACEMENT_LENGTH,
    MAX_RESULTS,
    Document,
    EditRequest,
    Suggestion,
)
from app.store import DocumentStore


@pytest.fixture
def store():
    return DocumentStore(
        [
            Document(id="agreement-a", title="Agreement A", text="😀 Alpha alpha Alpha."),
            Document(id="agreement-b", title="Agreement B", text="Alpha beta."),
        ]
    )


@pytest.fixture
def client(store):
    with TestClient(create_app(store)) as client:
        yield client


def edit_payload():
    return {
        "expected_version": 1,
        "target": {"start": 2, "end": 7, "text": "Alpha"},
        "replacement": "Updated",
    }


def assert_error(response, status):
    assert response.status_code == status
    body = response.json()
    assert set(body) == {"error", "code"}
    assert body["code"] == status
    assert isinstance(body["error"], str) and body["error"]


def test_page_and_assets_are_served_without_exposing_project_files(client):
    page = client.get("/")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "<title>Margin</title>" in page.text
    for path in ("/static/styles.css", "/static/app.js"):
        assert client.get(path).status_code == 200
    for path in ("/.env", "/static/.env", "/static/../.env"):
        assert client.get(path).status_code == 404


def test_list_and_read_documents(client):
    response = client.get("/documents")
    assert response.status_code == 200
    assert response.json() == [
        {"id": "agreement-a", "title": "Agreement A", "version": 1},
        {"id": "agreement-b", "title": "Agreement B", "version": 1},
    ]
    response = client.get("/documents/agreement-a")
    assert response.status_code == 200
    assert response.json() == {
        "id": "agreement-a",
        "title": "Agreement A",
        "version": 1,
        "text": "😀 Alpha alpha Alpha.",
    }


def test_search_one_document_with_separate_context(client):
    response = client.get(
        "/documents/search",
        params={"q": "Alpha", "document_id": "agreement-a", "limit": 2, "context_chars": 2},
    )
    assert response.status_code == 200
    assert response.json() == {
        "matches": [
            {
                "document_id": "agreement-a",
                "title": "Agreement A",
                "version": 1,
                "target": {"start": 2, "end": 7, "text": "Alpha"},
                "context_before": "😀 ",
                "context_after": " a",
            },
            {
                "document_id": "agreement-a",
                "title": "Agreement A",
                "version": 1,
                "target": {"start": 14, "end": 19, "text": "Alpha"},
                "context_before": "a ",
                "context_after": ".",
            },
        ],
        "truncated": False,
    }


def test_search_all_documents_applies_a_global_limit(client):
    response = client.get("/documents/search", params={"q": "Alpha", "limit": 2})
    assert response.status_code == 200
    body = response.json()
    assert len(body["matches"]) == 2
    assert body["truncated"] is True

    body = client.get("/documents/search", params={"q": "Alpha", "limit": 3}).json()
    assert [match["document_id"] for match in body["matches"]] == [
        "agreement-a",
        "agreement-a",
        "agreement-b",
    ]
    assert body["truncated"] is False


def test_search_without_matches_is_an_empty_success(client):
    response = client.get("/documents/search", params={"q": "absent"})
    assert response.status_code == 200
    assert response.json() == {"matches": [], "truncated": False}


def test_search_target_after_emoji_can_be_sent_unchanged_to_patch(client):
    result = client.get(
        "/documents/search", params={"q": "Alpha", "document_id": "agreement-a"}
    ).json()["matches"][0]
    assert result["target"] == {"start": 2, "end": 7, "text": "Alpha"}

    response = client.patch(
        f"/documents/{result['document_id']}",
        json={
            "expected_version": result["version"],
            "target": result["target"],
            "replacement": "Updated",
        },
    )
    assert response.status_code == 200
    assert response.json() == {
        "id": "agreement-a",
        "title": "Agreement A",
        "version": 2,
        "text": "😀 Updated alpha Alpha.",
    }
    assert client.get("/documents/agreement-a").json() == response.json()


def test_empty_replacement_deletes_only_the_selected_span(client):
    payload = edit_payload()
    payload["replacement"] = ""
    response = client.patch("/documents/agreement-a", json=payload)
    assert response.status_code == 200
    assert response.json()["text"] == "😀  alpha Alpha."
    assert response.json()["version"] == 2


def test_stale_save_returns_conflict_without_mutating_current_document(client):
    payload = edit_payload()
    saved = client.patch("/documents/agreement-a", json=payload)
    assert saved.status_code == 200
    response = client.patch("/documents/agreement-a", json=payload)
    assert_error(response, 409)
    assert client.get("/documents/agreement-a").json() == saved.json()


def test_target_mismatch_returns_conflict_without_mutation(client):
    before = client.get("/documents/agreement-a").json()
    payload = edit_payload()
    payload["target"]["text"] = "Wrong"
    response = client.patch("/documents/agreement-a", json=payload)
    assert_error(response, 409)
    assert client.get("/documents/agreement-a").json() == before


def test_missing_document_errors_are_structured(client):
    responses = [
        client.get("/documents/missing"),
        client.get("/documents/search", params={"q": "Alpha", "document_id": "missing"}),
        client.patch("/documents/missing", json=edit_payload()),
    ]
    for response in responses:
        assert_error(response, 404)


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"q": ""},
        {"q": "x" * (MAX_QUERY_LENGTH + 1)},
        {"q": "Alpha", "limit": 0},
        {"q": "Alpha", "limit": MAX_RESULTS + 1},
        {"q": "Alpha", "context_chars": -1},
        {"q": "Alpha", "context_chars": MAX_CONTEXT_CHARS + 1},
        {"q": "Alpha", "document_id": ""},
    ],
)
def test_search_rejects_invalid_inputs(client, params):
    assert_error(client.get("/documents/search", params=params), 422)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("expected_version", True),
        ("start", "2"),
        ("end", 7.0),
    ],
)
def test_edit_rejects_integer_coercion(client, field, value):
    payload = edit_payload()
    if field == "expected_version":
        payload[field] = value
    else:
        payload["target"][field] = value
    assert_error(client.patch("/documents/agreement-a", json=payload), 422)
    assert client.get("/documents/agreement-a").json()["version"] == 1


@pytest.mark.parametrize("target_text", ["", "x" * (MAX_QUERY_LENGTH + 1)])
def test_edit_rejects_empty_or_oversized_target(client, target_text):
    payload = edit_payload()
    payload["target"]["text"] = target_text
    assert_error(client.patch("/documents/agreement-a", json=payload), 422)


def test_edit_rejects_oversized_replacement(client):
    payload = edit_payload()
    payload["replacement"] = "x" * (MAX_REPLACEMENT_LENGTH + 1)
    assert_error(client.patch("/documents/agreement-a", json=payload), 422)


@pytest.mark.parametrize(("start", "end"), [(-1, 7), (7, 2), (2, 2), (2, 100)])
def test_edit_rejects_invalid_ranges_without_mutation(client, start, end):
    before = client.get("/documents/agreement-a").json()
    payload = edit_payload()
    payload["target"].update(start=start, end=end)
    assert_error(client.patch("/documents/agreement-a", json=payload), 422)
    assert client.get("/documents/agreement-a").json() == before


def test_edit_rejects_unrecognized_fields(client):
    payload = edit_payload()
    payload["replace_all"] = True
    assert_error(client.patch("/documents/agreement-a", json=payload), 422)


def test_malformed_json_returns_structured_error_without_echoing_body(client):
    response = client.patch(
        "/documents/agreement-a",
        content='{"private_sentinel":',
        headers={"Content-Type": "application/json"},
    )
    assert_error(response, 422)
    assert "private_sentinel" not in response.text


def test_unsupported_method_preserves_allow_header(client):
    response = client.post("/documents/agreement-a", json=edit_payload())
    assert_error(response, 405)
    assert response.headers["allow"]


def test_unexpected_error_has_safe_structured_response(store, monkeypatch):
    def fail_get(_document_id):
        raise RuntimeError("private_sentinel")

    monkeypatch.setattr(store, "get", fail_get)
    with TestClient(create_app(store), raise_server_exceptions=False) as client:
        response = client.get("/documents/agreement-a")
    assert_error(response, 500)
    assert response.json()["error"] == "Internal server error."
    assert "private_sentinel" not in response.text


@pytest.fixture
def mock_suggest(monkeypatch):
    mock = Mock(return_value=Suggestion(replacement="Suggested"))
    monkeypatch.setattr("app.main.suggest_replacement", mock)
    return mock


def suggestion_payload():
    return {
        "expected_version": 1,
        "target": {"start": 2, "end": 7, "text": "Alpha"},
        "instruction": "Rewrite the selected word.",
    }


def test_suggestion_uses_search_target_without_saving(client, store, mock_suggest):
    before = store.get("agreement-a")
    match = client.get(
        "/documents/search", params={"q": "Alpha", "document_id": "agreement-a"}
    ).json()["matches"][0]
    response = client.post(
        "/documents/agreement-a/suggest",
        json={
            "expected_version": match["version"],
            "target": match["target"],
            "instruction": "Rewrite the selected word.",
        },
    )
    assert response.status_code == 200
    assert response.json() == {"replacement": "Suggested"}
    mock_suggest.assert_called_once_with("Alpha", "Rewrite the selected word.")
    assert store.get("agreement-a") == before


@pytest.mark.parametrize(
    ("changes", "status_code"),
    [
        ({"expected_version": 2}, 409),
        ({"target": {"start": 2, "end": 7, "text": "Wrong"}}, 409),
        ({"target": {"start": 2, "end": 100, "text": "Alpha"}}, 422),
        ({"instruction": ""}, 422),
        ({"instruction": "x" * 1001}, 422),
        ({"expected_version": True}, 422),
    ],
)
def test_invalid_suggestion_request_never_calls_ai(
    client, store, mock_suggest, changes, status_code
):
    before = store.get("agreement-a")
    payload = suggestion_payload()
    payload.update(changes)
    response = client.post("/documents/agreement-a/suggest", json=payload)
    assert_error(response, status_code)
    mock_suggest.assert_not_called()
    assert store.get("agreement-a") == before


def test_suggestion_for_missing_document_never_calls_ai(client, mock_suggest):
    response = client.post("/documents/missing/suggest", json=suggestion_payload())
    assert_error(response, 404)
    mock_suggest.assert_not_called()


@pytest.mark.parametrize("status_code", [502, 503, 504])
def test_suggestion_failure_does_not_change_document(client, store, mock_suggest, status_code):
    before = store.get("agreement-a")
    mock_suggest.side_effect = DocumentError("Suggestion failed.", status_code)
    response = client.post("/documents/agreement-a/suggest", json=suggestion_payload())
    assert_error(response, status_code)
    assert store.get("agreement-a") == before


def test_manual_edit_still_works_without_ai_configuration(client, store, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    before = store.get("agreement-a")
    response = client.post("/documents/agreement-a/suggest", json=suggestion_payload())
    assert_error(response, 503)
    assert store.get("agreement-a") == before
    saved = client.patch("/documents/agreement-a", json=edit_payload())
    assert saved.status_code == 200
    assert saved.json()["version"] == 2


def test_edit_can_finish_during_suggestion_and_old_selection_cannot_be_saved(
    client, store, mock_suggest
):
    def edit_during_suggestion(_selected_text, _instruction):
        # This edit must be able to acquire the document lock while AI is working.
        store.edit("agreement-a", EditRequest(**edit_payload()))
        return Suggestion(replacement="Suggested")

    mock_suggest.side_effect = edit_during_suggestion
    response = client.post("/documents/agreement-a/suggest", json=suggestion_payload())
    assert response.status_code == 200
    after_edit = store.get("agreement-a")
    assert after_edit.version == 2

    payload = edit_payload()
    payload["replacement"] = response.json()["replacement"]
    assert_error(client.patch("/documents/agreement-a", json=payload), 409)
    assert store.get("agreement-a") == after_edit
