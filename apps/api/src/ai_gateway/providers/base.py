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
    # Opaque, provider-specific data that must be echoed back verbatim when
    # this call (and its result) is replayed into a later turn's history —
    # e.g. Gemini's `thought_signature`, required on any function_call part
    # sent back to the API or it rejects the request. OpenAI leaves this
    # empty. Round-tripped through pipeline.py's _serialize_tool_calls() and
    # stored in Message.tool_calls, so it survives a conversation reload.
    raw: dict[str, Any] = {}


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
