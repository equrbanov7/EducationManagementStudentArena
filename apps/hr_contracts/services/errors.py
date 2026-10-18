"""Servis xətası — endpoint onu ``{"ok": false, "error": …, "code": …, "field": …}`` cavabına çevirir."""

from __future__ import annotations


class ContractError(Exception):
    """İstifadəçiyə göstərilən domen xətası (``status`` — HTTP kodu)."""

    def __init__(self, code: str, message: str = "", field: str = "", status: int = 400):
        super().__init__(code, message, field, status)
        self.code = code
        self.message = message or code
        self.field = field
        self.status = status


__all__ = ["ContractError"]
