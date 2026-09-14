"""GeminiProvider tests. No network access or API key needed — the real
`genai.Client` is never constructed; `_get_client()` is monkeypatched to
return a stub whose async methods are AsyncMocks returning real
google-genai response objects (so response-parsing code is exercised against
the actual SDK's shapes, not a hand-rolled fake)."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from google.genai import errors as genai_errors
from google.genai import types

from src.ai_gateway.gateway import AIGateway, _is_retryable
from src.ai_gateway.providers.gemini_provider import GeminiProvider, _convert_messages
from src.core.exceptions import ProviderNotConfiguredError


def _fake_client(generate_content_response=None, embed_response=None):
    client = MagicMock()
    client.aio.models.generate_content = AsyncMock(return_value=generate_content_response)
    client.aio.models.embed_content = AsyncMock(return_value=embed_response)
    return client


async def test_complete_without_a_configured_key_raises_cleanly(monkeypatch):
    monkeypatch.setattr("src.ai_gateway.providers.gemini_provider.get_settings", lambda: _settings(gemini_key=None))
    provider = GeminiProvider()
    with pytest.raises(ProviderNotConfiguredError):
        await provider.complete([{"role": "user", "content": "hi"}])


async def test_complete_returns_plain_text(monkeypatch):
    response = types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(role="model", parts=[types.Part(text="We're open 9 to 5.")]),
                finish_reason=types.FinishReason.STOP,
            )
        ],
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=10, candidates_token_count=6, total_token_count=16
        ),
    )
    provider = GeminiProvider()
    monkeypatch.setattr(provider, "_get_client", lambda: _fake_client(generate_content_response=response))

    result = await provider.complete([{"role": "system", "content": "sys"}, {"role": "user", "content": "hours?"}])

    assert result.content == "We're open 9 to 5."
    assert result.tool_calls == []
    assert result.usage.total_tokens == 16


async def test_complete_translates_a_tool_call_request(monkeypatch):
    response = types.GenerateContentResponse(
        candidates=[
            types.Candidate(
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            function_call=types.FunctionCall(
                                id="call_1", name="calendar", args={"action": "list_events"}
                            )
                        )
                    ],
                ),
                finish_reason=types.FinishReason.STOP,
            )
        ],
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=10, candidates_token_count=6, total_token_count=16
        ),
    )
    provider = GeminiProvider()
    fake_client = _fake_client(generate_content_response=response)
    monkeypatch.setattr(provider, "_get_client", lambda: fake_client)

    tools = [{"name": "calendar", "description": "Manage the calendar.", "parameters": {"type": "object"}}]
    result = await provider.complete([{"role": "user", "content": "what's on tomorrow?"}], tools=tools)

    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].id == "call_1"
    assert result.tool_calls[0].name == "calendar"
    assert result.tool_calls[0].arguments == {"action": "list_events"}

    # The tool schema was translated into a Gemini FunctionDeclaration.
    call_kwargs = fake_client.aio.models.generate_content.call_args.kwargs
    sent_tools = call_kwargs["config"].tools
    assert sent_tools[0].function_declarations[0].name == "calendar"


async def test_embed_requests_the_shared_dimension(monkeypatch):
    from src.memory.models import EMBEDDING_DIM

    response = types.EmbedContentResponse(embeddings=[types.ContentEmbedding(values=[0.1] * EMBEDDING_DIM)])
    provider = GeminiProvider()
    fake_client = _fake_client(embed_response=response)
    monkeypatch.setattr(provider, "_get_client", lambda: fake_client)

    vectors = await provider.embed(["hello"])

    assert len(vectors) == 1
    assert len(vectors[0]) == EMBEDDING_DIM
    call_kwargs = fake_client.aio.models.embed_content.call_args.kwargs
    assert call_kwargs["config"].output_dimensionality == EMBEDDING_DIM


def test_convert_messages_round_trips_a_tool_call_and_result():
    """The exact shape agents/runtime/pipeline.py builds: an assistant turn
    carrying tool_calls (arguments JSON-stringified, per _serialize_tool_calls),
    followed by a tool-role result keyed by tool_call_id. The provider must
    recover the function *name* for the result since Gemini correlates by name,
    not by an OpenAI-style call id."""
    messages = [
        {"role": "system", "content": "You are the Receptionist."},
        {"role": "user", "content": "what's on tomorrow?"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {"id": "call_1", "type": "function", "function": {"name": "calendar", "arguments": json.dumps({"action": "list_events"})}}
            ],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": "no events found"},
    ]

    system_instruction, contents = _convert_messages(messages)

    assert system_instruction == "You are the Receptionist."
    assert len(contents) == 3  # user, assistant/model, tool-result
    assert contents[0].role == "user"
    assert contents[1].role == "model"
    assert contents[1].parts[0].function_call.name == "calendar"
    assert contents[1].parts[0].function_call.args == {"action": "list_events"}
    # The tool result comes back as a user-role function_response, matched by name.
    assert contents[2].role == "user"
    assert contents[2].parts[0].function_response.name == "calendar"
    assert contents[2].parts[0].function_response.response == {"content": "no events found"}


def test_ai_gateway_defaults_to_the_configured_provider(monkeypatch):
    from src.ai_gateway.providers.gemini_provider import GeminiProvider
    from src.ai_gateway.providers.openai_provider import OpenAIProvider

    monkeypatch.setattr("src.ai_gateway.gateway.get_settings", lambda: _settings(ai_provider="gemini"))
    gateway = AIGateway()
    assert isinstance(gateway._provider, GeminiProvider)

    monkeypatch.setattr("src.ai_gateway.gateway.get_settings", lambda: _settings(ai_provider="openai"))
    gateway = AIGateway()
    assert isinstance(gateway._provider, OpenAIProvider)


def test_ai_gateway_rejects_an_unknown_provider():
    with pytest.raises(ValueError):
        AIGateway(provider_name="not-a-real-provider")


@pytest.mark.parametrize(
    "exc,expected",
    [
        (genai_errors.ServerError(code=503, response_json={}), True),
        (genai_errors.ClientError(code=429, response_json={}), True),
        (genai_errors.ClientError(code=400, response_json={}), False),
        (ValueError("unrelated"), False),
    ],
)
def test_is_retryable_handles_gemini_error_shapes(exc, expected):
    assert _is_retryable(exc) is expected


class _Settings:
    def __init__(self, gemini_key="test-key", ai_provider="gemini"):
        self.GEMINI_API_KEY = gemini_key
        self.AI_PROVIDER = ai_provider
        self.GEMINI_CHAT_MODEL = "gemini-2.0-flash"
        self.GEMINI_EMBEDDING_MODEL = "gemini-embedding-001"


def _settings(gemini_key="test-key", ai_provider="gemini"):
    return _Settings(gemini_key=gemini_key, ai_provider=ai_provider)
