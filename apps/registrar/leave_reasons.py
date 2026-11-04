"""Akademik məzuniyyətin («Dondur») SƏBƏB KATEQORİYASI — sahib 2026-11-04.

«RİM tərəfindən tələbəni dondurarkən səbəb seçmək olsun — məzuniyyət, analıq və s.»
Kateqoriya hər yeni akademik məzuniyyət əmrində (``StudentMovement.kind=academic_leave``)
MƏCBURİDİR; «Digər» seçiləndə sərbəst qeyd (əmrin «səbəb» mətni) də məcburidir.

Qayda insan səthlərindədir (RİM reyestri, qrup çekmecəsi, «İnsanlar» status kartı) — hamısı
:func:`apps.registrar.movements.normalize_leave_reason`-dan keçir. Köhnə əmrlərdə və sistem
idxallarında sahə boşdur (``""`` — «göstərilməyib»); tarixçə sonradan doldurulmur.

Etiketlər bu modulun TƏK mənbəyidir: model ``choices``-i, dialoq seçicisi, ledger mətni
(``to_label``) və audit sətri eyni enum-dan oxuyur.
"""

from __future__ import annotations

from django.db import models
from django.utils.translation import pgettext_lazy


class LeaveReason(models.TextChoices):
    """Dondurma səbəbinin kateqoriyası (sıra = seçicidəki sıra)."""

    ACADEMIC = "academic", pgettext_lazy("registrar.leave_reason", "Akademik məzuniyyət")
    MATERNITY = "maternity", pgettext_lazy("registrar.leave_reason", "Analıq (doğuş) məzuniyyəti")
    CHILDCARE = "childcare", pgettext_lazy("registrar.leave_reason", "Uşağa qulluq məzuniyyəti")
    MEDICAL = "medical", pgettext_lazy("registrar.leave_reason", "Səhhətlə bağlı (tibbi)")
    MILITARY = "military", pgettext_lazy("registrar.leave_reason", "Hərbi xidmət")
    FAMILY = "family", pgettext_lazy("registrar.leave_reason", "Ailə vəziyyəti")
    FINANCIAL = "financial", pgettext_lazy("registrar.leave_reason", "Maliyyə səbəbi")
    OTHER = "other", pgettext_lazy("registrar.leave_reason", "Digər")


#: Sərbəst qeyd (əmrin səbəb mətni) MƏCBURİ olan kateqoriyalar.
NOTE_REQUIRED = frozenset({LeaveReason.OTHER})

#: Model sahəsinin uzunluğu (ən uzun açar + ehtiyat).
LEAVE_REASON_MAX_LENGTH = 24


def leave_reason_label(value) -> str:
    """Kateqoriyanın etiketi (``str`` — JSON/audit üçün lazy proxy qalmır); boş/naməlum → ``""``."""
    try:
        return str(LeaveReason(str(value or "")).label)
    except ValueError:
        return ""


def leave_reason_options() -> list:
    """Seçici variantları ``[{"value", "label"}]`` (şablon + JSON üçün eyni forma)."""
    return [{"value": choice.value, "label": str(choice.label)} for choice in LeaveReason]


__all__ = [
    "LEAVE_REASON_MAX_LENGTH",
    "NOTE_REQUIRED",
    "LeaveReason",
    "leave_reason_label",
    "leave_reason_options",
]
