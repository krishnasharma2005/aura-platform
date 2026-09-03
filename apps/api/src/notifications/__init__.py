"""Pluggable outbound notifications — right now just "a new approval is
waiting on you," but written so a second event type is a new call site, not a
new subsystem.

See `notifier.py` for the interface and the shipped implementations.
"""

from src.notifications.notifier import Notifier, get_notifier

__all__ = ["Notifier", "get_notifier"]
