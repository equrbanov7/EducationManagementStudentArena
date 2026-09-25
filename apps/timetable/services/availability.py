"""Müəllim əlçatanlığı — şəbəkənin oxunması, validasiyası və yazılması (audit ilə).

Şəbəkə: günlər (B.e.–Şənbə) × təşkilatın dərs saatları. Hər xana bir səviyyədir:
neytral / üstünlük / dəyişdirilə bilən (arzuolunmaz) / gələ bilmir. Yazılan hər
dəyişiklik ``core.audit`` jurnalına düşür (kim, nə vaxt, köhnə → yeni).
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.db import transaction
from django.utils.translation import pgettext

from apps.registrar.public import schedule_grid

from ..constants import LEVEL_CODES, Level

_CTX = "timetable.availability"

#: Redaktorun göstərdiyi günlər — mövcud cədvəl redaktoru ilə eyni (B.e.–Şənbə).
EDIT_WEEKDAYS = (1, 2, 3, 4, 5, 6)


class AvailabilityError(Exception):
    def __init__(self, message, errors=None):
        errors = dict(errors or {})
        super().__init__(message, errors)
        self.message = message
        self.errors = errors


def _model():
    return django_apps.get_model("timetable", "TeacherAvailability")


def get_row(organization, period, teacher):
    return _model().objects.filter(organization=organization, period=period, teacher=teacher).first()


def matrix(organization, row) -> dict:
    """UI üçün şəbəkə: ``{"periods": [...], "days": [{"weekday", "label", "cells": [...]}]}``."""
    from apps.registrar.public import schedule

    periods = schedule_grid.lesson_periods(organization)
    grid = (row.grid if row is not None else None) or {}
    labels = dict(schedule.WEEKDAYS)
    level_labels = {code: str(label) for code, label in Level.choices}
    days = []
    for weekday in EDIT_WEEKDAYS:
        text = str(grid.get(str(weekday)) or "")
        cells = []
        for index, period in enumerate(periods):
            level = text[index] if index < len(text) and text[index] in LEVEL_CODES else Level.NEUTRAL
            cells.append(
                {"pair": period["no"], "level": level, "level_label": level_labels[level], "shift": period["shift"]}
            )
        days.append({"weekday": weekday, "label": str(labels.get(weekday, weekday)), "cells": cells})
    rows = []
    for index, period in enumerate(periods):
        rows.append(
            {
                "no": period["no"],
                "roman": period["roman"],
                "start": period["start_text"],
                "end": period["end_text"],
                "shift": period["shift"],
                "cells": [{"weekday": day["weekday"], "label": day["label"], **day["cells"][index]} for day in days],
            }
        )
    return {
        "days": [{"weekday": day["weekday"], "label": day["label"]} for day in days],
        "rows": rows,
        "levels": [{"code": code, "label": str(label)} for code, label in Level.choices],
    }


def _small_int(value, *, low, high, field, errors):
    if value in (None, ""):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        errors[field] = pgettext(_CTX, "Tam ədəd daxil edin.")
        return None
    if not low <= number <= high:
        errors[field] = pgettext(_CTX, "Dəyər %(low)s–%(high)s aralığında olmalıdır.") % {"low": low, "high": high}
        return None
    return number


def clean(organization, data) -> dict:
    """Xam JSON → təmiz dəyərlər; səhv varsa ``AvailabilityError``."""
    periods = len(schedule_grid.lesson_periods(organization))
    errors: dict = {}
    raw_grid = data.get("grid") if isinstance(data.get("grid"), dict) else {}
    grid = {}
    for weekday in EDIT_WEEKDAYS:
        text = str(raw_grid.get(str(weekday)) or "")
        if any(ch not in LEVEL_CODES for ch in text):
            errors["grid"] = pgettext(_CTX, "Şəbəkədə naməlum səviyyə var.")
            break
        text = (text + Level.NEUTRAL * periods)[:periods]
        if text != Level.NEUTRAL * periods:
            grid[str(weekday)] = text
    cleaned = {
        "grid": grid,
        "max_pairs_per_day": _small_int(
            data.get("max_pairs_per_day"), low=1, high=periods, field="max_pairs_per_day", errors=errors
        ),
        "max_days_per_week": _small_int(
            data.get("max_days_per_week"), low=1, high=7, field="max_days_per_week", errors=errors
        ),
        "priority": _small_int(data.get("priority"), low=1, high=5, field="priority", errors=errors) or 1,
        "note": str(data.get("note") or "").strip()[:2000],
    }
    subject_priorities = {}
    raw_subjects = data.get("subject_priorities") if isinstance(data.get("subject_priorities"), dict) else {}
    for key, value in raw_subjects.items():
        number = _small_int(value, low=1, high=5, field="subject_priorities", errors=errors)
        if number and number > 1:
            subject_priorities[str(key)[:64]] = number
    cleaned["subject_priorities"] = subject_priorities
    if errors:
        raise AvailabilityError(pgettext(_CTX, "Əlçatanlıq yadda saxlanılmadı — xanaları yoxlayın."), errors)
    return cleaned


def _snapshot(row) -> dict:
    if row is None:
        return {}
    return {
        "grid": row.grid,
        "max_pairs_per_day": row.max_pairs_per_day,
        "max_days_per_week": row.max_days_per_week,
        "priority": row.priority,
        "subject_priorities": row.subject_priorities,
        "note": row.note,
    }


def save(*, actor, organization, period, teacher, data, request=None):
    """Upsert + audit. Qaytarır ``TeacherAvailability`` sətrini."""
    from core.audit import log_action
    from core.constants import AuditAction

    cleaned = clean(organization, data)
    Model = _model()
    with transaction.atomic():
        row = (
            Model.objects.select_for_update().filter(organization=organization, period=period, teacher=teacher).first()
        )
        old = _snapshot(row)
        if row is None:
            row = Model(organization=organization, period=period, teacher=teacher)
        for field, value in cleaned.items():
            setattr(row, field, value)
        row.updated_by = actor if getattr(actor, "pk", None) else None
        row.save()
        log_action(
            AuditAction.UPDATE if old else AuditAction.CREATE,
            user=actor,
            organization=organization,
            obj=row,
            old_values=old or None,
            new_values=_snapshot(row),
            request=request,
            resource_type="timetable.TeacherAvailability",
            resource_id=str(row.pk),
            resource_repr=f"{teacher.get_full_name() or teacher.username} · {period.name}",
        )
    return row


def summary(row, periods: int) -> dict:
    """Siyahı sütunu: neçə xana «gələ bilmir» / «dəyişdirilə bilən»."""
    grid = (row.grid if row is not None else None) or {}
    text = "".join(str(v) for v in grid.values())
    return {
        "saved": row is not None,
        "unavailable": text.count(Level.UNAVAILABLE),
        "discouraged": text.count(Level.DISCOURAGED),
        "preferred": text.count(Level.PREFERRED),
        "priority": getattr(row, "priority", 1) or 1,
        "cells": periods * len(EDIT_WEEKDAYS),
    }


__all__ = ["EDIT_WEEKDAYS", "AvailabilityError", "clean", "get_row", "matrix", "save", "summary"]
