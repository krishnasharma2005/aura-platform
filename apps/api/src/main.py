"""FastAPI application factory for the AURA API."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from src.api.v1.admin import router as admin_router
from src.api.v1.agents import router as agents_router
from src.api.v1.analytics import router as analytics_router
from src.api.v1.approvals import router as approvals_router
from src.api.v1.audit import router as audit_router
from src.api.v1.auth import router as auth_router
from src.api.v1.business_context import router as business_context_router
from src.api.v1.conversations import router as conversations_router
from src.api.v1.integrations import router as integrations_router
from src.api.v1.knowledge import router as knowledge_router
from src.api.v1.organizations import router as organizations_router
from src.api.v1.packs import router as packs_router
from src.api.v1.public import router as public_router
from src.api.v1.workflows import router as workflows_router
from src.core.config import get_settings
from src.core.exceptions import register_exception_handlers
from src.core.logging import configure_logging
from src.events.audit import register_audit_subscriber
from src.workflows import runner as workflow_runner


# Routes a website visitor's browser reaches directly from the customer's own
# domain — see the CORS note in create_app().
PUBLIC_API_PREFIX = "/api/v1/public/"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Starts the scheduled-workflow runner alongside the API.

    This is the deliberate alternative to Celery: an asyncio task in the app
    process, made safe to run on several instances by DB-level claims rather
    than by a broker. See src/workflows/runner.py for the full reasoning, and
    `WORKFLOWS_RUNNER_ENABLED=false` + `python -m scripts.run_workflows` if you
    would rather cron owned the schedule.
    """
    workflow_runner.start()
    try:
        yield
    finally:
        await workflow_runner.stop()


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()

    if settings.ENV == "production" and settings.JWT_SECRET == "dev-secret-change-me":
        raise RuntimeError(
            "Refusing to start in production with the default JWT_SECRET. Set a real, random JWT_SECRET."
        )

    if settings.ENV == "production" and not settings.ENCRYPTION_KEY:
        raise RuntimeError(
            "Refusing to start in production without ENCRYPTION_KEY: integration access tokens "
            "(Google, WhatsApp, Slack, HubSpot, Shopify) would be written to the database in "
            'plaintext. Generate one with: python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"'
        )

    app = FastAPI(title="AURA API", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def public_endpoint_cors(request: Request, call_next):
        """The embeddable web-chat widget runs on the customer's own website,
        so its endpoints must answer any origin — an allowlist can't work when
        every customer has a different domain.

        Scoped strictly to `/api/v1/public/`, and deliberately without
        `Access-Control-Allow-Credentials`: these endpoints authenticate by
        opaque public id and signed conversation token, never by cookie, so a
        wildcard origin grants a caller nothing it couldn't already do with
        curl. Every other route keeps the strict allowlist above.

        Registered after CORSMiddleware, which makes it the outer layer — it
        has to answer the preflight itself, since the inner middleware would
        reject an unknown origin with a 400 before the widget ever got a reply.
        """
        if not request.url.path.startswith(PUBLIC_API_PREFIX):
            return await call_next(request)

        if request.method == "OPTIONS":
            response = Response(status_code=200)
        else:
            response = await call_next(request)

        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Max-Age"] = "600"
        # The strict middleware may have set this for an allowlisted origin;
        # "*" plus credentials is rejected outright by browsers.
        if "access-control-allow-credentials" in response.headers:
            del response.headers["access-control-allow-credentials"]
        return response

    register_exception_handlers(app)
    register_audit_subscriber()
    # Event-triggered workflows subscribe to the same bus the audit log uses.
    workflow_runner.register_event_triggers()

    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(organizations_router, prefix="/api/v1")
    app.include_router(agents_router, prefix="/api/v1")
    app.include_router(knowledge_router, prefix="/api/v1")
    app.include_router(integrations_router, prefix="/api/v1")
    app.include_router(admin_router, prefix="/api/v1")
    app.include_router(audit_router, prefix="/api/v1")
    app.include_router(approvals_router, prefix="/api/v1")
    app.include_router(conversations_router, prefix="/api/v1")
    app.include_router(workflows_router, prefix="/api/v1")
    app.include_router(analytics_router, prefix="/api/v1")
    app.include_router(business_context_router, prefix="/api/v1")
    app.include_router(packs_router, prefix="/api/v1")
    # The only unauthenticated router in the product — see api/v1/public.py.
    app.include_router(public_router, prefix="/api/v1")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
