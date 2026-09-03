"""Single entry point for all LLM calls. Routes to a provider (OpenAI today),
tracks token usage, and retries transient errors with backoff. Adding a second
provider means writing one new providers/*.py module and adding it to
`_PROVIDERS` below — no changes required in any caller."""

from typing import Any

from openai import APIConnectionError, APITimeoutError, RateLimitError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.ai_gateway.providers.base import LLMProvider, LLMResponse
from src.ai_gateway.providers.openai_provider import OpenAIProvider
from src.core.logging import get_logger

logger = get_logger(__name__)

_PROVIDERS: dict[str, type[LLMProvider]] = {
    "openai": OpenAIProvider,
}

_RETRYABLE_ERRORS = (APIConnectionError, APITimeoutError, RateLimitError)


class AIGateway:
    def __init__(self, provider_name: str = "openai") -> None:
        if provider_name not in _PROVIDERS:
            raise ValueError(f"Unknown AI provider: {provider_name}")
        self._provider: LLMProvider = _PROVIDERS[provider_name]()

    @retry(
        retry=retry_if_exception_type(_RETRYABLE_ERRORS),
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
        retry=retry_if_exception_type(_RETRYABLE_ERRORS),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=8),
        reraise=True,
    )
    async def embed(self, texts: list[str]) -> list[list[float]]:
        embeddings = await self._provider.embed(texts)
        logger.info("ai_gateway_embed", extra={"extra_fields": {"count": len(texts)}})
        return embeddings
