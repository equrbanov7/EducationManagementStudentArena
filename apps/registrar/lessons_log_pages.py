"""«Keçilmiş dərslər» — gün siyahısının səhifələnməsi (2026-11-11, sahib: «girəndə bir az yavaşlama olur»).

Əvvəl bölmə hər açılışda son 90 dərsi (sətir başına 8 xana + status nişanı) bir dəfəyə çəkirdi. İndi ilk cavab
:data:`PAGE_SIZE` dərslə gəlir, qalanı «Daha çox göstər» düyməsi ilə (AJAX) əlavə olunur.

Səhifə SƏTİR sayı ilə kəsilir (org-wide görünüşdə bir günə 300+ dərs düşür — «günü tam gətir» qaydası səhifəni
şişirdərdi). Gün iki səhifəyə düşə bilər: gün başlığındakı «N dərs · M saat» ona görə səhifədəki sətirlərdən YOX,
günün TAM cəmindən gəlir (:func:`day_totals` — bir aqreqat sorğu), müştəri isə davam edən günün sətirlərini
mövcud gün kartına əlavə edir (``lessons_log.js``). Sıra ``build_rows`` ilə eynidir (tarix ↓, saat ↓, yaranma ↓).
"""

from __future__ import annotations

from django.db.models import Count, Sum

#: Bir səhifədəki dərs sayı.
PAGE_SIZE = 30
#: Sürüşmə tavanı — əl ilə yazılmış nəhəng ``ll_offset`` bazanı boş yerə sıralatmasın.
MAX_OFFSET = 100_000


def parse_offset(raw) -> int:
    """``ll_offset`` → 0 … :data:`MAX_OFFSET`; boş / pozuq → 0 (ilk səhifə)."""
    try:
        return max(0, min(int(str(raw or "0").strip()), MAX_OFFSET))
    except ValueError:
        return 0


def day_totals(lessons_qs, dates) -> dict:
    """``{tarix: {"lessons", "hours"}}`` — verilmiş günlərin TAM cəmi (səhifədən asılı deyil), TƏK sorğu."""
    dates = sorted(set(dates))
    if not dates:
        return {}
    rows = lessons_qs.order_by().filter(date__in=dates).values("date").annotate(lessons=Count("id"), hours=Sum("hours"))
    return {row["date"]: {"lessons": int(row["lessons"] or 0), "hours": int(row["hours"] or 0)} for row in rows}


def page_rows(lessons_qs, *, offset: int = 0, size: int = PAGE_SIZE) -> dict:
    """``{"rows", "next_offset", "day_totals"}`` — 3 sorğu (sətirlər, xana aqreqatı, gün cəmləri).

    ``next_offset`` — növbəti səhifənin sürüşməsi və ya ``None`` (son səhifə; ``size + 1`` zondu ilə bilinir)."""
    from apps.registrar.lessons_log import build_rows

    rows = build_rows(lessons_qs, limit=size + 1, offset=offset)
    has_more = len(rows) > size
    rows = rows[:size]
    return {
        "rows": rows,
        "next_offset": offset + size if has_more else None,
        "day_totals": day_totals(lessons_qs, [row["date"] for row in rows]),
    }


__all__ = ["MAX_OFFSET", "PAGE_SIZE", "day_totals", "page_rows", "parse_offset"]
