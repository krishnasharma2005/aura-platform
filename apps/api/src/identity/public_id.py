"""Generation of an organization's opaque public web-chat id.

This is the only organization identifier that is ever handed to an
unauthenticated visitor, so it must not be derivable from anything public
about the business. `token_urlsafe(24)` gives ~192 bits of entropy — a
32-character string that is not worth enumerating.
"""

import secrets

PUBLIC_ID_BYTES = 24


def generate_public_id() -> str:
    return secrets.token_urlsafe(PUBLIC_ID_BYTES)
