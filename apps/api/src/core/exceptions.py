"""Application exception hierarchy and the FastAPI handler that turns them into
clean JSON responses. User-facing messages are written in plain language per the
AURA customer profile (no stack traces, no jargon like "RAG"/"token" surfaced to
end users) — internal logs may use standard technical terms."""

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from src.core.logging import get_logger

logger = get_logger(__name__)


class AuraError(Exception):
    """Base class for all application errors that should produce a clean,
    user-safe JSON response instead of a raw 500."""

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    default_message: str = "Something went wrong on our end. Please try again."

    def __init__(self, message: str | None = None):
        self.message = message or self.default_message
        super().__init__(self.message)


class NotFoundError(AuraError):
    status_code = status.HTTP_404_NOT_FOUND
    default_message = "We couldn't find what you were looking for."


class PermissionError(AuraError):
    status_code = status.HTTP_403_FORBIDDEN
    default_message = "You don't have permission to do that."


class ValidationError(AuraError):
    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    default_message = "Some of the information provided isn't valid."


class ProviderNotConfiguredError(AuraError):
    """Raised when a required external service (AI provider, integration, etc.)
    hasn't been connected/configured for this organization yet."""

    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_message = "This feature isn't set up yet. Please connect it first."


class AuthenticationError(AuraError):
    status_code = status.HTTP_401_UNAUTHORIZED
    default_message = "Please sign in again."


class ConflictError(AuraError):
    status_code = status.HTTP_409_CONFLICT
    default_message = "That already exists."


async def aura_error_handler(request: Request, exc: AuraError) -> JSONResponse:
    logger.warning(
        "aura_error",
        extra={"extra_fields": {"path": request.url.path, "error_type": type(exc).__name__}},
    )
    return JSONResponse(status_code=exc.status_code, content={"error": exc.message})


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "unhandled_error",
        exc_info=exc,
        extra={"extra_fields": {"path": request.url.path}},
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "Something went wrong on our end. Please try again."},
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """FastAPI's default 422 body is a list of pydantic error dicts full of
    field paths and type jargon — not something a salon owner should ever read,
    and it uses a different envelope from every other error we return. This
    normalizes it to the same {"error": "..."} shape in plain language."""
    logger.info(
        "request_validation_error",
        extra={"extra_fields": {"path": request.url.path, "error_count": len(exc.errors())}},
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"error": "Some of the information provided isn't valid. Please check it and try again."},
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AuraError, aura_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)
