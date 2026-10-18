"""«Akademik təqvim» → «Bayram və qeyri-iş günləri» kartı — OXU konteksti + idarə səlahiyyəti (2026-10-19).

NİYƏ «Akademik təqvim»də (və «Semestr açılışı»nda yox)? Bayramlar bütün universitetin təqvimidir: müəllim,
tələbə, dekanlıq da görməlidir — «Akademik təqvim» universitet rejimində hər üzvə açıqdır, «Semestr açılışı»
isə yalnız Tədris şöbəsinin iş axınıdır (``semester.view``). Ona görə kart təqvimdə hamıya YALNIZ-OXU
göstərilir, idarə (əlavə / redaktə / sil / sabit bayramları əlavə et) isə semestr açılışı ilə EYNİ açara
bağlıdır: ``semester.open`` TƏŞKİLAT səviyyəsində (rol auditi B17 qaydası — kafedra/fakültə rolu bütün
universitetin təqvimini dəyişmir). View-as rejimində heç vaxt idarə yoxdur.

Model və keş ``apps.organizations`` qatındadır (``organizations.public``); burada yalnız görünüş forması.
Sorğu: dövr aralığı üzrə BİR ``AcademicHoliday`` sorğusu.
"""

from __future__ import annotations

import json

from django.utils import timezone
from django.utils.translation import pgettext

_CTX = "registrar.calendar"


def _weekday_labels() -> tuple:
    return (
        pgettext(_CTX, "Bazar ertəsi"),
        pgettext(_CTX, "Çərşənbə axşamı"),
        pgettext(_CTX, "Çərşənbə"),
        pgettext(_CTX, "Cümə axşamı"),
        pgettext(_CTX, "Cümə"),
        pgettext(_CTX, "Şənbə"),
        pgettext(_CTX, "Bazar"),
    )


def can_manage_holidays(request, organization) -> bool:
    """``semester.open`` org-wide + view-as deyil (yazı yoxdur)."""
    if organization is None or request is None or getattr(request, "is_view_as", False):
        return False
    from apps.organizations.public import get_permission_scope

    from .semester_open import PERM_OPEN, can_open_semester

    if not can_open_semester(request):
        return False
    return get_permission_scope(request.user, organization, PERM_OPEN, request=request).is_org_wide


def holidays_context(request, organization, *, year: str = "", years=()) -> dict:
    """Kartın konteksti: seçilmiş tədris ili (yoxdursa — bu günün tədris ili) üzrə qeydlər."""
    from apps.organizations.public import (
        holiday_academic_year_bounds,
        holiday_academic_year_label,
        holiday_academic_year_start,
        holiday_current_academic_year,
        holidays_between,
    )

    today = timezone.localdate()
    current = holiday_current_academic_year(today)
    start_year = holiday_academic_year_start(year) or current
    first, last = holiday_academic_year_bounds(start_year)
    weekdays = _weekday_labels()
    items = []
    for holiday in holidays_between(organization, first, last):
        items.append(
            {
                "id": str(holiday.pk),
                "date": holiday.date,
                "weekday": weekdays[holiday.date.weekday()],
                "is_weekend": holiday.date.weekday() >= 5,
                "name": holiday.name,
                "kind": holiday.kind,
                "kind_label": holiday.get_kind_display(),
                "note": holiday.note,
                "is_past": holiday.date < today,
                "prefill": json.dumps(
                    {
                        "action": "save",
                        "id": str(holiday.pk),
                        "date": holiday.date.isoformat(),
                        "name": holiday.name,
                        "kind": holiday.kind,
                        "note": holiday.note,
                    },
                    ensure_ascii=False,
                ),
            }
        )
    seed_years = sorted(
        {current - 1, current, current + 1} | {y for y in (holiday_academic_year_start(item) for item in years) if y},
        reverse=True,
    )
    non_working = sum(1 for item in items if item["kind"] != "workday")
    return {
        "academic_year": holiday_academic_year_label(start_year),
        "range_start": first,
        "range_end": last,
        "items": items,
        "non_working_count": non_working,
        "workday_count": len(items) - non_working,
        "can_manage": can_manage_holidays(request, organization),
        "seed_year_options": [
            {"value": holiday_academic_year_label(item), "label": holiday_academic_year_label(item)}
            for item in seed_years
        ],
        "seed_default": holiday_academic_year_label(start_year),
        "kind_options": [
            {"value": "holiday", "label": pgettext("organizations.holiday", "Bayram")},
            {"value": "day_off", "label": pgettext("organizations.holiday", "Qeyri-iş günü")},
            {"value": "workday", "label": pgettext("organizations.holiday", "İş günü köçürməsi")},
        ],
        # `_form_dialog.html` müqaviləsi: forma atributu + gizli sahələr (JS prefill-i ilə doldurulur).
        "form_data": {"data-acal-hol-form": "1"},
        "dialog_hidden": [{"name": "action", "value": "save", "keep": True}, {"name": "id", "value": ""}],
        "seed_hidden": [{"name": "action", "value": "seed_fixed", "keep": True}],
        "seed_prefill": json.dumps({"action": "seed_fixed", "academic_year": holiday_academic_year_label(start_year)}),
        "new_prefill": json.dumps({"action": "save", "id": "", "date": "", "name": "", "kind": "holiday", "note": ""}),
    }


__all__ = ["can_manage_holidays", "holidays_context"]
