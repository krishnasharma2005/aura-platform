"""OpenAI implementation of LLMProvider. The API key is read lazily from
settings at call time (not import time) so the module imports cleanly even
when OPENAI_API_KEY is unset — only actually calling it raises."""

import json
from typing import Any

from openai import AsyncOpenAI

from src.ai_gateway.providers.base import LLMProvider, LLMResponse, ToolCall, Usage
from src.core.config import get_settings
from src.core.exceptions import ProviderNotConfiguredError


class OpenAIProvider(LLMProvider):
    def __init__(self) -> None:
        self._client: AsyncOpenAI | None = None

    def _get_client(self) -> AsyncOpenAI:
        settings = get_settings()
        if not settings.OPENAI_API_KEY:
            raise ProviderNotConfiguredError(
                "AI features aren't set up yet. Please add an OpenAI API key to enable them."
            )
        if self._client is None:
            self._client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        return self._client

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        client = self._get_client()
        settings = get_settings()

        request_kwargs: dict[str, Any] = {
            "model": kwargs.pop("model", settings.OPENAI_CHAT_MODEL),
            "messages": messages,
        }
        if tools:
            request_kwargs["tools"] = [{"type": "function", "function": t} for t in tools]
        request_kwargs.update(kwargs)

        response = await client.chat.completions.create(**request_kwargs)
        choice = response.choices[0]

        tool_calls = [
            ToolCall(id=tc.id, name=tc.function.name, arguments=json.loads(tc.function.arguments or "{}"))
            for tc in (choice.message.tool_calls or [])
        ]

        usage = response.usage
        return LLMResponse(
            content=choice.message.content,
            tool_calls=tool_calls,
            usage=Usage(
                prompt_tokens=usage.prompt_tokens if usage else 0,
                completion_tokens=usage.completion_tokens if usage else 0,
                total_tokens=usage.total_tokens if usage else 0,
            ),
            finish_reason=choice.finish_reason,
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        client = self._get_client()
        settings = get_settings()
        response = await client.embeddings.create(model=settings.OPENAI_EMBEDDING_MODEL, input=texts)
        return [item.embedding for item in response.data]
