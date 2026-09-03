"""Application configuration, read from environment variables via pydantic-settings."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central settings object. Values are read from the process environment
    (and a local .env file in development). See .env.example for the full list."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    ENV: str = Field(default="development", description="development | test | staging | production")

    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://aura:aura_dev_password@localhost:5432/aura",
        description="Async SQLAlchemy connection string for Postgres (asyncpg driver).",
    )
    REDIS_URL: str = Field(default="redis://localhost:6379/0", description="Redis connection string.")

    JWT_SECRET: str = Field(default="dev-secret-change-me", description="Secret used to sign JWTs.")
    JWT_EXPIRE_MINUTES: int = Field(default=60 * 24, description="Access token lifetime in minutes.")
    JWT_ALGORITHM: str = Field(default="HS256")

    ENCRYPTION_KEY: str | None = Field(
        default=None,
        description=(
            "Fernet key (urlsafe base64, 32 bytes) used to encrypt integration access/refresh "
            "tokens at rest. Generate with: python -c \"from cryptography.fernet import Fernet; "
            'print(Fernet.generate_key().decode())". Required in production.'
        ),
    )

    OPENAI_API_KEY: str | None = Field(default=None, description="OpenAI API key. Unset disables AI features.")
    OPENAI_CHAT_MODEL: str = Field(default="gpt-4o-mini")
    OPENAI_EMBEDDING_MODEL: str = Field(default="text-embedding-3-small")

    MAX_UPLOAD_BYTES: int = Field(
        default=20 * 1024 * 1024,
        description="Largest knowledge-base document we accept, in bytes (default 20 MB).",
    )

    DEFAULT_TIMEZONE: str = Field(
        default="UTC",
        description="IANA timezone used for calendar reads/writes when an organization hasn't set its own.",
    )

    CORS_ORIGINS: list[str] = Field(default=["http://localhost:3000"])

    # --- Workflow engine (src/workflows/) ---
    WORKFLOWS_RUNNER_ENABLED: bool = Field(
        default=True,
        description=(
            "Run the scheduled-workflow loop as a background task inside the API process. "
            "Turn it off if you'd rather drive the schedule from cron via "
            "`python -m scripts.run_workflows --once`. Running both is harmless — claims are "
            "taken with a conditional UPDATE, so nothing double-fires."
        ),
    )
    WORKFLOW_TICK_SECONDS: int = Field(
        default=30, description="How often the runner looks for due workflows and resumable runs."
    )
    WORKFLOW_LOCK_TIMEOUT_SECONDS: int = Field(
        default=600,
        description=(
            "How long a claim held by an instance that died is respected before another "
            "instance may take the work over."
        ),
    )
    WORKFLOW_STEP_MAX_ATTEMPTS: int = Field(
        default=3, description="Attempts per workflow step before the run is marked failed."
    )
    WORKFLOW_RETRY_BACKOFF_SECONDS: float = Field(
        default=2.0, description="Base delay for the exponential backoff between step retries."
    )

    # --- Public web chat (the only unauthenticated surface in the product) ---
    PUBLIC_CHAT_MAX_MESSAGE_CHARS: int = Field(
        default=2000, description="Longest single message a website visitor may send."
    )
    PUBLIC_CHAT_MAX_MESSAGES: int = Field(
        default=60,
        description="Total stored turns after which a public conversation stops accepting new messages.",
    )
    PUBLIC_CHAT_IP_LIMIT: int = Field(default=20, description="Messages per IP per window.")
    PUBLIC_CHAT_IP_WINDOW_SECONDS: int = Field(default=300)
    PUBLIC_CHAT_CONVERSATION_LIMIT: int = Field(default=10, description="Messages per conversation per window.")
    PUBLIC_CHAT_CONVERSATION_WINDOW_SECONDS: int = Field(default=60)
    PUBLIC_CHAT_TOKEN_TTL_HOURS: int = Field(
        default=24, description="How long a visitor's conversation token stays valid."
    )
    TRUST_PROXY_HEADERS: bool = Field(
        default=False,
        description=(
            "Read the client IP from X-Forwarded-For instead of the socket. Only enable when the API "
            "sits behind a proxy that overwrites the header — otherwise any visitor can forge it and "
            "walk straight past the per-IP rate limit."
        ),
    )

    # --- WhatsApp inbound webhook (see docs/needs-founder-input.md) ---
    WHATSAPP_VERIFY_TOKEN: str | None = Field(
        default=None,
        description="Arbitrary shared string echoed back during Meta's webhook verification handshake.",
    )
    WHATSAPP_APP_SECRET: str | None = Field(
        default=None,
        description="Meta app secret, used to validate the X-Hub-Signature-256 header on inbound webhooks.",
    )

    # --- Notifications (see src/notifications/notifier.py) ---
    NOTIFY_CHANNEL: str = Field(
        default="console",
        description=(
            "Which Notifier delivers 'a new approval is waiting' alerts: 'console' (default, always "
            "works, no credentials needed) or 'email' (requires NOTIFY_EMAIL_PROVIDER_API_KEY)."
        ),
    )
    NOTIFY_EMAIL_PROVIDER_API_KEY: str | None = Field(
        default=None,
        description=(
            "FOUNDER MUST PROVIDE to enable email notifications: a transactional-email provider key "
            "(e.g. SendGrid, Postmark). Without it the email notifier logs and no-ops rather than "
            "pretending to send. See docs/needs-founder-input.md."
        ),
    )
    APP_URL: str = Field(
        default="http://localhost:3000",
        description="Base URL of the dashboard, used to build links inside notifications.",
    )

    @property
    def is_test(self) -> bool:
        return self.ENV == "test"


@lru_cache
def get_settings() -> Settings:
    return Settings()
