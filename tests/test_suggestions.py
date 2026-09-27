"""Exercise the real SDK parser against fake HTTP responses; no paid/network calls."""

import json

import httpx2
import pytest
from openai import OpenAI

from app import suggestions
from app.core import DocumentError
from app.models import MAX_REPLACEMENT_LENGTH


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-a-real-secret")
    state = {
        "calls": [],
        "status_code": 200,
        "failure": None,
        "body": {
            "id": "resp_test",
            "object": "response",
            "created_at": 0,
            "model": suggestions.MODEL,
            "status": "completed",
            "output": [
                {
                    "id": "msg_test",
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [
                        {
                            "type": "output_text",
                            "text": '{"replacement":"sixty (60) days"}',
                            "annotations": [],
                        }
                    ],
                }
            ],
        },
    }

    def handle(request):
        state["calls"].append(request)
        if state["failure"] is not None:
            raise state["failure"]("private provider detail", request=request)
        return httpx2.Response(state["status_code"], json=state["body"])

    def make_client(**options):
        assert options == {"timeout": 15.0, "max_retries": 0}
        return OpenAI(
            **options,
            http_client=httpx2.Client(transport=httpx2.MockTransport(handle)),
        )

    monkeypatch.setattr(suggestions, "OpenAI", make_client)
    return state


def test_valid_suggestion_sends_only_selected_text_and_instruction(provider):
    original = "thirty (30) days"
    instruction = "Change this to sixty days, preserving the number format."
    result = suggestions.suggest_replacement(original, instruction)
    assert result.model_dump() == {"replacement": "sixty (60) days"}
    assert len(provider["calls"]) == 1
    request = provider["calls"][0]
    assert request.url.path == "/v1/responses"
    body = json.loads(request.content)
    assert json.loads(body["input"]) == {"selected_text": original, "instruction": instruction}
    assert body["store"] is False
    assert body["max_output_tokens"] == 512
    assert "tools" not in body
    assert body["text"]["format"]["strict"] is True
    assert body["text"]["format"]["schema"]["additionalProperties"] is False


@pytest.mark.parametrize("replacement", ["", "  sixty days\n"])
def test_suggestion_preserves_empty_replacement_and_whitespace(provider, replacement):
    provider["body"]["output"][0]["content"][0]["text"] = json.dumps({"replacement": replacement})
    assert suggestions.suggest_replacement("30 days", "Rewrite").replacement == replacement


@pytest.mark.parametrize(
    "model_text",
    [
        "not JSON",
        "{}",
        '{"replacement":42}',
        '{"replacement":"60 days","start":0}',
        json.dumps({"replacement": "x" * (MAX_REPLACEMENT_LENGTH + 1)}),
    ],
)
def test_malformed_suggestions_fail_with_safe_message(provider, model_text):
    provider["body"]["output"][0]["content"][0]["text"] = model_text
    with pytest.raises(DocumentError) as failure:
        suggestions.suggest_replacement("30 days", "Rewrite")
    assert failure.value.status_code == 502
    assert str(failure.value) == "AI returned an invalid suggestion. Please edit manually."


@pytest.mark.parametrize("case", ["refusal", "incomplete", "empty"])
def test_refused_or_incomplete_responses_are_not_treated_as_success(provider, case):
    if case == "refusal":
        provider["body"]["output"][0]["content"] = [
            {"type": "refusal", "refusal": "private provider detail"}
        ]
    elif case == "incomplete":
        provider["body"]["status"] = "incomplete"
    else:
        provider["body"]["output"] = []
    with pytest.raises(DocumentError) as failure:
        suggestions.suggest_replacement("30 days", "Rewrite")
    assert failure.value.status_code == 502
    assert "private provider detail" not in str(failure.value)


@pytest.mark.parametrize("status_code", [401, 429, 500])
def test_provider_errors_do_not_leak_details_or_retry(provider, status_code):
    provider["status_code"] = status_code
    provider["body"] = {"error": {"message": "private provider detail"}}
    with pytest.raises(DocumentError) as failure:
        suggestions.suggest_replacement("30 days", "Rewrite")
    assert failure.value.status_code == 503
    assert "private provider detail" not in str(failure.value)
    assert len(provider["calls"]) == 1


@pytest.mark.parametrize(
    ("error", "status_code"), [(httpx2.ReadTimeout, 504), (httpx2.ConnectError, 503)]
)
def test_network_failures_are_reported_without_retry(provider, error, status_code):
    provider["failure"] = error
    with pytest.raises(DocumentError) as failure:
        suggestions.suggest_replacement("30 days", "Rewrite")
    assert failure.value.status_code == status_code
    assert len(provider["calls"]) == 1


@pytest.mark.parametrize(
    ("selected_text", "instruction"),
    [("", "Rewrite"), ("x" * 1001, "Rewrite"), ("text", "  "), ("text", "x" * 1001)],
)
def test_invalid_inputs_do_not_contact_provider(provider, selected_text, instruction):
    with pytest.raises(DocumentError) as failure:
        suggestions.suggest_replacement(selected_text, instruction)
    assert failure.value.status_code == 422
    assert provider["calls"] == []


def test_missing_key_gives_clear_failure_without_contacting_provider(provider, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY")
    with pytest.raises(DocumentError) as failure:
        suggestions.suggest_replacement("30 days", "Rewrite")
    assert failure.value.status_code == 503
    assert str(failure.value) == "AI is not configured. You can still edit manually."
    assert provider["calls"] == []
