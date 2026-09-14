"""Gemini implementation of LLMProvider (Google AI Studio, free tier available).
Like OpenAIProvider, the API key is read lazily at call time so the module
imports cleanly even when GEMINI_API_KEY is unset.

Gemini's request/response shape differs from OpenAI's in three ways this
module translates, so nothing above AIGateway needs to know which provider is
active:

1. No "system" message in the turn list — it's a separate `system_instruction`.
2. Assistant turns are role "model", and a tool call is a `Part.function_call`
   inside that turn's parts, not a top-level `tool_calls` list.
3. A tool result is matched back to its call by function *name* (Gemini has no
   OpenAI-style `tool_call_id` concept the API itself uses for correlation),
   so this provider tracks id -> name as it walks the message history and
   reattaches it when converting the "tool" role message that follows.
"""

import json
from typing import Any

from google import genai
from google.genai import types

from src.ai_gateway.providers.base import LLMProvider, LLMResponse, ToolCall, Usage
from src.core.config import get_settings
from src.core.exceptions import ProviderNotConfiguredError
from src.memory.models import EMBEDDING_DIM


class GeminiProvider(LLMProvider):
    def __init__(self) -> None:
        self._client: genai.Client | None = None

    def _get_client(self) -> genai.Client:
        settings = get_settings()
        if not settings.GEMINI_API_KEY:
            raise ProviderNotConfiguredError(
                "AI features aren't set up yet. Please add a Gemini API key to enable them."
            )
        if self._client is None:
            self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
        return self._client

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        client = self._get_client()
        settings = get_settings()

        system_instruction, contents = _convert_messages(messages)

        config_kwargs: dict[str, Any] = {}
        if system_instruction:
            config_kwargs["system_instruction"] = system_instruction
        if tools:
            config_kwargs["tools"] = [
                types.Tool(
                    function_declarations=[
                        types.FunctionDeclaration(
                            name=t["name"], description=t.get("description"), parameters=t.get("parameters")
                        )
                        for t in tools
                    ]
                )
            ]

        model = kwargs.pop("model", settings.GEMINI_CHAT_MODEL)
        response = await client.aio.models.generate_content(
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(**config_kwargs) if config_kwargs else None,
        )

        tool_calls = [
            ToolCall(id=fc.id or f"call_{fc.name}_{i}", name=fc.name, arguments=fc.args or {})
            for i, fc in enumerate(response.function_calls or [])
        ]

        candidate = response.candidates[0] if response.candidates else None
        finish_reason = str(candidate.finish_reason.value) if candidate and candidate.finish_reason else None

        usage_metadata = response.usage_metadata
        usage = Usage(
            prompt_tokens=(usage_metadata.prompt_token_count or 0) if usage_metadata else 0,
            completion_tokens=(usage_metadata.candidates_token_count or 0) if usage_metadata else 0,
            total_tokens=(usage_metadata.total_token_count or 0) if usage_metadata else 0,
        )

        return LLMResponse(
            content=response.text,
            tool_calls=tool_calls,
            usage=usage,
            finish_reason=finish_reason,
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        client = self._get_client()
        settings = get_settings()
        response = await client.aio.models.embed_content(
            model=settings.GEMINI_EMBEDDING_MODEL,
            contents=texts,
            # Matches memory.models.EMBEDDING_DIM (the pgvector column's fixed
            # size) so knowledge search works the same under either provider —
            # see the note on GEMINI_EMBEDDING_MODEL in core/config.py.
            config=types.EmbedContentConfig(output_dimensionality=EMBEDDING_DIM),
        )
        return [list(e.values or []) for e in (response.embeddings or [])]


def _convert_messages(messages: list[dict[str, Any]]) -> tuple[str | None, list[types.Content]]:
    """OpenAI-chat-shaped messages (as built by agents/runtime/pipeline.py's
    _build_messages, the only caller) -> (system_instruction, Gemini contents).
    """
    system_instruction: str | None = None
    contents: list[types.Content] = []
    call_id_to_name: dict[str, str] = {}

    for msg in messages:
        role = msg["role"]

        if role == "system":
            # The pipeline sends exactly one, first — later ones (there are
            # none today, but nothing enforces it) would just overwrite.
            system_instruction = msg["content"]

        elif role == "user":
            contents.append(types.Content(role="user", parts=[types.Part(text=msg.get("content") or "")]))

        elif role == "assistant":
            parts = []
            if msg.get("content"):
                parts.append(types.Part(text=msg["content"]))
            for tc in msg.get("tool_calls") or []:
                call_id = tc["id"]
                name = tc["function"]["name"]
                args = json.loads(tc["function"]["arguments"] or "{}")
                call_id_to_name[call_id] = name
                parts.append(types.Part(function_call=types.FunctionCall(id=call_id, name=name, args=args)))
            contents.append(types.Content(role="model", parts=parts))

        elif role == "tool":
            call_id = msg["tool_call_id"]
            name = call_id_to_name.get(call_id, "unknown_tool")
            contents.append(
                types.Content(
                    role="user",
                    parts=[
                        types.Part(
                            function_response=types.FunctionResponse(
                                id=call_id, name=name, response={"content": msg["content"]}
                            )
                        )
                    ],
                )
            )

    return system_instruction, contents
