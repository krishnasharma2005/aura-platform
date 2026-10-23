"""The password rules, in one place so signup and reset can't drift apart.

Deliberately modest — length, not "one capital and one symbol". Current guidance
is that length is what matters and composition rules mostly push people toward
predictable substitutions. The upper bound is not a nicety: bcrypt only reads
the first 72 bytes, so a longer password would silently be truncated, and the
person would "know" a password the system does not actually check in full.
"""

from src.core.exceptions import ValidationError

MIN_LENGTH = 8
MAX_BYTES = 72


def validate_new_password(password: str) -> None:
    """Raises ValidationError with a message safe to show the person."""
    if len(password) < MIN_LENGTH or not password.strip():
        raise ValidationError(f"Please choose a password with at least {MIN_LENGTH} characters.")
    if len(password.encode("utf-8")) > MAX_BYTES:
        raise ValidationError(f"That password is too long. Please use {MAX_BYTES} characters or fewer.")
