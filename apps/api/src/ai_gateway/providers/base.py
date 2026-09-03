"""Abstract LLM provider interface. Every provider (OpenAI now, others later)
implements this so the AIGateway and callers never need to change when a new
provider is added — only a new one-file provider module + a registration line."""

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any]


class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class LLMResponse(BaseModel):
    content: str | None = None
    tool_calls: list[ToolCall] = []
    usage: Usage = Usage()
    finish_reason: str | None = None


class LLMProvider(ABC):
    """Abstract base for a chat-completion-capable LLM provider."""

    @abstractmethod
    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Send `messages` (OpenAI chat-message-shaped dicts) and optional
        `tools` (JSON-schema tool definitions) to the provider and return a
        normalized LLMResponse."""
        raise NotImplementedError

    @abstractmethod
    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text."""
        raise NotImplementedError
