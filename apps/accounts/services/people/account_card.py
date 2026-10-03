"""Tələbə kartında HESAB bloku — vəziyyət + dayandırma səbəbi / «kimə yaxınlaşmalı» (sahib 2026-10-03)."""

from __future__ import annotations

from .. import account_block_reasons as block_reasons
from .filters import STATUS_BLOCKED, account_status_of


def account_card(user) -> dict:
    """``{"user_id", "status", "reason", "contact", "note", "blocked_at"}`` — səbəb yalnız dayandırılmış hesabda."""
    status = account_status_of(user)
    data = {"user_id": str(user.pk), "status": status, "reason": "", "contact": "", "note": "", "blocked_at": ""}
    profile = getattr(user, "profile", None)
    if status == STATUS_BLOCKED and profile is not None:
        code = profile.block_reason_code or ""
        data.update(
            {
                "reason": block_reasons.reason_label(code) if code else (profile.block_reason or ""),
                "contact": block_reasons.contact_label(profile.block_contact_code, code),
                "note": profile.block_contact_note or "",
                "blocked_at": profile.blocked_at.strftime("%d.%m.%Y") if profile.blocked_at else "",
            }
        )
    return data


__all__ = ["account_card"]
