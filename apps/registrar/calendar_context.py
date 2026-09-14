"""Akademik təqvimin kontekst qurucusu.

`page_contexts.py` modul-ölçü büdcəsinə dayandığı üçün ayrıldı (2026-09-09).
Burada YALNIZ təqvim var: semestrlər, qeydiyyat/imtahan pəncərələrinin
vəziyyəti, tədris ili üzrə qruplaşdırma və KPI xülasəsi.

Sorğu profili: TƏK `AcademicPeriod` sorğusu — qruplaşdırma və saylar Python-da
aparılır (dövr sayı onlarla ölçülür, minlərlə deyil).
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.utils import timezone
from django.utils.translation import pgettext

__all__ = ["calendar_context"]


def calendar_context(organization, *, year="") -> dict:
    """Semestrlər + qeydiyyat/imtahan pəncərələrinin vəziyyəti.

    2026-09-09 (sahib: «yenidən dizayn et, oxunaqlı olsun»): siyahı indi TƏDRİS
    İLİ üzrə qruplaşdırılır və yuxarıda KPI zolağı verilir — 13+ semestr düz
    siyahıda oxunmurdu. Sorğu sayı DƏYİŞMİR: hamısı bir `AcademicPeriod`
    sorğusudur, qalan hesablama Python-dadır.
    """
    AcademicPeriod = django_apps.get_model("organizations", "AcademicPeriod")
    today = timezone.localdate()
    rows = []
    for period in AcademicPeriod.objects.filter(organization=organization).order_by("-start_date"):
        rows.append(
            {
                "period": period,
                "is_running": period.start_date <= today <= period.end_date,
                "registration_state": period.registration_state,
                "exam_session_state": period.exam_session_state,
                "year_key": str(period.year_display or ""),
            }
        )

    years = sorted({row["year_key"] for row in rows if row["year_key"]}, reverse=True)
    year = (year or "").strip()
    shown = [row for row in rows if not year or row["year_key"] == year]

    # Qruplaşdırma: tədris ili → semestrlər (sıra `-start_date`-dən qalır).
    groups, index = [], {}
    for row in shown:
        key = row["year_key"] or "—"
        if key not in index:
            index[key] = {"year": key, "items": []}
            groups.append(index[key])
        index[key]["items"].append(row)

    # `*_state` ya "open"/"upcoming"/"closed", ya da None (pəncərə qurulmayıb).
    missing = sum(1 for row in rows if row["registration_state"] is None or row["exam_session_state"] is None)
    current = next((row["period"].name for row in rows if row["period"].is_current), "")
    running = sum(1 for row in rows if row["is_running"])
    ctx = "registrar.calendar"
    return {
        "has_context": True,
        "periods": shown,
        "groups": groups,
        "years": years,
        "year": year,
        "today": today,
        # KPI zolağı ORTAQ komponentlə render olunur (`ems_ui/_kpi_row.html`) —
        # bölməyə məxsus yeni sinif icad edilmir.
        "kpi_tiles": [
            {
                "label": pgettext(ctx, "Semestr"),
                "value": len(rows),
                "note": pgettext(ctx, "təqvimdə, süzgəcdən asılı deyil"),
                "tone": "accent-primary",
            },
            {"label": pgettext(ctx, "Cari semestr"), "value": current or "—"},
            {
                "label": pgettext(ctx, "Davam edir"),
                "value": running,
                "note": pgettext(ctx, "bugünkü tarix dövrün içindədir"),
            },
            {
                "label": pgettext(ctx, "Pəncərəsi yoxdur"),
                "value": missing,
                "note": pgettext(ctx, "qeydiyyat və ya imtahan tarixi qurulmayıb"),
                "tone": "accent-warning" if missing else None,
            },
        ],
        "summary": {
            "total": len(rows),
            "running": running,
            "current": current,
            "missing_windows": missing,
        },
    }
