"""Single entry point for all LLM calls. Routes to a provider (OpenAI or
Gemini today, selected by settings.AI_PROVIDER), tracks token usage, and
retries transient errors with backoff. Adding another provider means writing
one new providers/*.py module and adding it to `_PROVIDERS` below — no changes
required in any caller.

A future automatic-fallback chain (try the next provider if one is exhausted
or down) belongs here too: every provider already normalizes into the same
LLMResponse/ToolCall shape, so `complete`/`embed` could loop over a priority
list instead of a single `self._provider` without any caller-visible change.
Not built yet — deliberately kept to a single active provider for now, chosen
by AI_PROVIDER, since embeddings in particular can't safely fail over (see the
note on GEMINI_EMBEDDING_MODEL in core/config.py)."""

from typing import Any

from google.genai import errors as genai_errors
from openai import APIConnectionError, APITimeoutError, RateLimitError
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from src.ai_gateway.providers.base import LLMProvider, LLMResponse
from src.ai_gateway.providers.gemini_provider import GeminiProvider
from src.ai_gateway.providers.openai_provider import OpenAIProvider
from src.core.config import get_settings
from src.core.logging import get_logger

logger = get_logger(__name__)

_PROVIDERS: dict[str, type[LLMProvider]] = {
    "openai": OpenAIProvider,
    "gemini": GeminiProvider,
}

# OpenAI's SDK has dedicated exception types for these; google-genai instead
# carries an HTTP status code on a shared APIError, so a rate limit (429) or
# any 5xx is matched by inspecting `.code` rather than by exception type.
_OPENAI_RETRYABLE_ERRORS = (APIConnectionError, APITimeoutError, RateLimitError)


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, _OPENAI_RETRYABLE_ERRORS):
        return True
    if isinstance(exc, genai_errors.ServerError):
        return True
    if isinstance(exc, genai_errors.ClientError):
        return exc.code == 429
    return False


class AIGateway:
    def __init__(self, provider_name: str | None = None) -> None:
        provider_name = provider_name or get_settings().AI_PROVIDER
        if provider_name not in _PROVIDERS:
            raise ValueError(f"Unknown AI provider: {provider_name}")
        self._provider: LLMProvider = _PROVIDERS[provider_name]()

    @retry(
        retry=retry_if_exception(_is_retryable),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        response = await self._provider.complete(messages, tools=tools, **kwargs)
        logger.info(
            "ai_gateway_complete",
            extra={
                "extra_fields": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                    "tool_calls": len(response.tool_calls),
                }
            },
        )
        return response

    @retry(
        retry=retry_if_exception(_is_retryable),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    async def embed(self, texts: list[str]) -> list[list[float]]:
        embeddings = await self._provider.embed(texts)
        logger.info("ai_gateway_embed", extra={"extra_fields": {"count": len(texts)}})
        return embeddings
