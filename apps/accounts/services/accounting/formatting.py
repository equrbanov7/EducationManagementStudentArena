"""«Mühasibatlıq» — saat və ştat dəyərlərinin göstərilişi (AZ yazılışı: onluq vergül)."""

from __future__ import annotations

from django.utils.translation import pgettext

from ..hr_analytics.constants import STAFF_HOURLY, STAFF_NONE
from . import constants as C


def fmt_hours(value, *, signed: bool = False) -> str:
    """Saat: «38», «37,5»; ``signed`` — «+3,5» / «−2» (sıfır «0»)."""
    number = round(float(value or 0), 1)
    text = f"{abs(number) if signed else number:.1f}".rstrip("0").rstrip(".").replace(".", ",")
    if signed and number:
        return ("+" if number > 0 else "−") + text
    return text or "0"


def staff_short(person) -> str:
    """Ştat sütunu: «1», «0,5», saathesabı «s/h», yük profili yoxdursa «—»."""
    if person["staff_type"] == STAFF_NONE:
        return "—"
    if person["staff_type"] == STAFF_HOURLY:
        return pgettext(C.CTX, "s/h")
    return fmt_hours(person["staff_fraction"] or 0)


def kind_cells(kinds: dict) -> list[dict]:
    """Növ xanaları — [{label, value}] (mühazirə / seminar / lab sırası ilə; telefonda kart etiketi)."""
    return [{"label": str(label), "value": fmt_hours((kinds or {}).get(key, 0))} for key, label in C.KINDS]


__all__ = ["fmt_hours", "kind_cells", "staff_short"]
