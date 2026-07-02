"""contact modulunun PUBLIC API fasadı (M3-B, 2026-07-02)."""

from apps.contact.services import (  # noqa: F401
    send_reply_to_contact,
)

__all__ = [
    "send_reply_to_contact",
]
