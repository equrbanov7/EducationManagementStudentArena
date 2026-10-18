"""«Mühasibatlıq» — status leqendası və aralıq düzəlişi qeydləri (şablon üçün hazır mətnlər, sorğusuz)."""

from __future__ import annotations

from django.utils.translation import pgettext

from core.ui import status_catalog

from . import constants as C
from .ranges import NOTE_CLAMPED, NOTE_INVALID, NOTE_OUTSIDE, NOTE_SWAPPED, default_range, fmt_date


def legend_items() -> list[dict]:
    """Status → bir cümlə izah; band «Sistem tənzimləmələri»ndən (``accounting.deviation_percent``).

    «%» işarəsi msgid-də DEYİL, arqumentdədir: «%-i» kimi ardıcıllıq xgettext-də python-format direktivi sayılır və
    tərcüməsi fərqli olanda ``compilemessages`` yoxlaması yıxılır."""
    band = C.deviation_percent()
    texts = (
        (C.STATUS_ON_PLAN, pgettext(C.CTX, "fakt planın ±{band} hüdudunda").format(band=f"{band}%")),
        (C.STATUS_UNDER, pgettext(C.CTX, "fakt planın {share}-indən az").format(share=f"{100 - band}%")),
        (C.STATUS_OVER, pgettext(C.CTX, "fakt planın {share}-indən çox").format(share=f"{100 + band}%")),
        (C.STATUS_NO_PLAN, pgettext(C.CTX, "dərs keçilib, amma bu dövr üçün plan yoxdur")),
        (C.STATUS_IDLE, pgettext(C.CTX, "nə plan, nə keçirilmiş dərs")),
    )
    return [{"status": status_catalog.get(C.STATUS_FAMILY, key), "text": text} for key, text in texts]


def range_messages(notes, semester) -> list[str]:
    """Aralıq düzəlişləri (``ranges.normalize_range``) — istifadəçiyə aydın qeyd."""
    out = []
    if NOTE_INVALID in notes:
        out.append(pgettext(C.CTX, "Tarix tanınmadı — defolt aralıq göstərilir (semestrin başlanğıcından bu günədək)."))
    if NOTE_SWAPPED in notes:
        out.append(pgettext(C.CTX, "Başlanğıc tarixi son tarixdən sonra idi — tarixlərin yeri dəyişdirildi."))
    if NOTE_OUTSIDE in notes:
        start, end = default_range(semester)
        out.append(
            pgettext(C.CTX, "Seçilmiş aralıq bu semestrə düşmür — defolt aralıq göstərilir ({start} – {end}).").format(
                start=fmt_date(start), end=fmt_date(end)
            )
        )
    if NOTE_CLAMPED in notes:
        out.append(
            pgettext(C.CTX, "Aralıq seçilmiş semestrin hüdudlarına ({start} – {end}) uyğunlaşdırıldı.").format(
                start=fmt_date(semester.start), end=fmt_date(semester.end)
            )
        )
    return out


__all__ = ["legend_items", "range_messages"]
