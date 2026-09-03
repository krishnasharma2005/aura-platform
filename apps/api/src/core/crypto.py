"""Application-level encryption at rest for integration credentials.

Integration access/refresh tokens are the most sensitive rows we hold — they
grant access to a customer's calendar, inbox, CRM, and store — so they are
encrypted with a key that lives in the environment (`ENCRYPTION_KEY`) rather
than in the database. A database dump on its own is then not enough to take
over a customer's Google account.

Migration path: encrypted values are written with an `enc:v1:` prefix. Values
without that prefix are legacy plaintext and are still readable, so turning
encryption on requires no migration and no downtime — every token is
re-encrypted the next time it is written. Once `ENCRYPTION_KEY` is set,
`decrypt_secret` never silently drops a value.
"""

from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken

from src.core.config import get_settings
from src.core.exceptions import AuraError
from src.core.logging import get_logger

logger = get_logger(__name__)

_PREFIX = "enc:v1:"


class EncryptionNotConfiguredError(AuraError):
    """Raised when an encrypted value must be read but no key is configured."""

    default_message = "This connection can't be used right now. Please reconnect it."


@lru_cache
def _get_fernet() -> Fernet | None:
    """Returns the configured Fernet, or None when no key is set (development).
    A malformed key is a hard error — failing loudly beats silently storing
    every customer's credentials in the clear."""
    key = get_settings().ENCRYPTION_KEY
    if not key:
        return None
    try:
        return Fernet(key.encode())
    except (ValueError, TypeError) as exc:
        raise RuntimeError(
            "ENCRYPTION_KEY is not a valid Fernet key. Generate one with: "
            'python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"'
        ) from exc


def encryption_enabled() -> bool:
    return _get_fernet() is not None


def encrypt_secret(value: str) -> str:
    """Encrypts a secret for storage. With no key configured (development only)
    the value is stored as-is and a warning is logged — production startup
    refuses to boot without a key, see src/main.py."""
    fernet = _get_fernet()
    if fernet is None:
        logger.warning("secret_stored_unencrypted", extra={"extra_fields": {"reason": "ENCRYPTION_KEY unset"}})
        return value
    return _PREFIX + fernet.encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    """Decrypts a stored secret. Legacy plaintext rows (written before
    encryption was enabled) are returned unchanged so existing connections keep
    working until they're next saved."""
    if not value.startswith(_PREFIX):
        return value
    fernet = _get_fernet()
    if fernet is None:
        raise EncryptionNotConfiguredError()
    try:
        return fernet.decrypt(value[len(_PREFIX) :].encode()).decode()
    except InvalidToken as exc:
        logger.error("secret_decrypt_failed")
        raise EncryptionNotConfiguredError() from exc
