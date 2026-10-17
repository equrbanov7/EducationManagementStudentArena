"""«Sual təsdiqi» bölməsinin TƏQDİMAT qatı — ems_ui komponent modeli (Paket C 2026-10-17).

Sorğu/filtr məntiqi ``question_chair_review.py``-dədir; burada nəticə KPI kartlarına (klik edilə
bilən status filtrləri), avto filtr panelinin sahələrinə və cədvəl sətirlərinə çevrilir — eyni
naxış «Sual göndərişləri» bölməsindədir (``question_submissions_ui.py``).  GET parametr adları
(``qchair_q`` · ``qchair_status`` · ``qchair_kind`` · ``qchair_teacher`` · ``qchair_page``)
dəyişməyib.
"""

from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import pgettext

CELL_DIR = "exams/teacher/partials/question_submissions/"

#: Status → (etiket, badge tonu). Etiketlər bölmənin mövcud msgid-ləridir.
_STATUS_TONES = {
    "submitted_to_chair": "warning",
    "chair_revision": "danger",
    "chair_approved": "info",
    "center_review": "info",
    "accepted": "success",
    "rejected": "danger",
}


def _status_label(status):
    labels = {
        "submitted_to_chair": pgettext("accounts.profile.question_chair_review", "Təsdiq gözləyir"),
        "chair_revision": pgettext("accounts.profile.question_chair_review", "Düzəliş istənilib"),
        "chair_approved": pgettext("accounts.profile.question_chair_review", "Təsdiqlənib — mərkəzdə"),
        "center_review": pgettext("accounts.profile.question_chair_review", "Mərkəz baxır"),
        "accepted": pgettext("accounts.profile.question_chair_review", "Mərkəz qəbul etdi"),
        "rejected": pgettext("accounts.profile.question_chair_review", "Rədd edilib"),
    }
    return labels.get(status, pgettext("accounts.profile.question_chair_review", "Müəllimdə"))


def status_badge(status):
    tone = _STATUS_TONES.get(status, "neutral")
    return {"css_class": f"ems-badge ems-badge--{tone} ems-badge--wrap", "label": _status_label(status)}


def kpi_tiles(counts, *, active_status):
    tiles = [
        (
            "submitted_to_chair",
            pgettext("accounts.profile.question_chair_review", "Təsdiq gözləyir"),
            "pending",
            "warning",
        ),
        ("chair_approved", pgettext("accounts.profile.question_chair_review", "Təsdiqlədiyim"), "approved", "success"),
        (
            "chair_revision",
            pgettext("accounts.profile.question_chair_review", "Düzəliş istənilən"),
            "revision",
            "danger",
        ),
        ("", pgettext("accounts.profile.question_chair_review", "Ümumi"), "total", "primary"),
    ]
    return [
        {
            "label": label,
            "value": counts.get(key) or 0,
            "tone": tone,
            "filter": status or "all",
            "pressed": (active_status or "all") == (status or "all"),
        }
        for status, label, key, tone in tiles
    ]


def filter_fields(*, filters, teachers, exam_kinds, status_values):
    status_options = [{"value": "", "label": pgettext("accounts.profile.question_submissions", "Bütün statuslar")}]
    # «chair_approved» filtri KPI kimi «kafedra təsdiqləyib» deməkdir (sonrakı statuslar daxil) — etiket də eyni.
    approved_label = pgettext("accounts.profile.question_chair_review", "Təsdiqlədiyim")
    status_options += [
        {"value": value, "label": approved_label if value == "chair_approved" else _status_label(value)}
        for value in status_values
    ]
    kind_options = [{"value": "", "label": pgettext("accounts.profile.question_chair_review", "Bütün imtahan növləri")}]
    kind_options += [{"value": code, "label": label} for code, label in exam_kinds]
    teacher_options = [{"value": "", "label": pgettext("accounts.profile.question_chair_review", "Bütün müəllimlər")}]
    teacher_options += [{"value": str(t.id), "label": t.get_full_name() or t.username} for t in teachers]
    return [
        {
            "name": "qchair_q",
            "label": pgettext("accounts.profile.question_submissions", "Axtarış"),
            "kind": "search",
            "value": filters.get("q", ""),
            "wide": True,
            "placeholder": pgettext(
                "accounts.profile.question_chair_review", "Başlıq, fənn, qrup və ya müəllim üzrə axtar…"
            ),
        },
        {
            "name": "qchair_status",
            "label": pgettext("accounts.profile.question_submissions", "Vəziyyət"),
            "kind": "select",
            "options": status_options,
            "value": filters.get("status", ""),
        },
        {
            "name": "qchair_kind",
            "label": pgettext("accounts.profile.question_chair_review", "İmtahan növü"),
            "kind": "select",
            "options": kind_options,
            "value": filters.get("kind", ""),
        },
        {
            "name": "qchair_teacher",
            "label": pgettext("accounts.profile.question_chair_review", "Müəllim"),
            "kind": "select",
            "searchable": True,
            "options": teacher_options,
            "value": filters.get("teacher", ""),
        },
    ]


def columns():
    return [
        {"key": "title", "label": pgettext("accounts.profile.question_submissions", "Göndəriş")},
        {"key": "teacher", "label": pgettext("accounts.profile.question_submissions", "Müəllim")},
        {"key": "status", "label": pgettext("accounts.profile.question_submissions", "Vəziyyət")},
        {"key": "questions", "label": pgettext("accounts.profile.question_submissions", "Sual"), "align": "num"},
        {"key": "signals", "label": pgettext("accounts.profile.question_submissions", "Xəbərdarlıq")},
        {"key": "created", "label": pgettext("accounts.profile.question_submissions", "Tarix")},
        {"key": "actions", "label": pgettext("accounts.profile.question_submissions", "Əməllər"), "sr_only": True},
    ]


def _when(value):
    if not value:
        return ""
    if timezone.is_aware(value):
        value = timezone.localtime(value)
    return date_format(value, "d.m.Y H:i")


def table_rows(items):
    rows = []
    for item in items:
        group = item.group_label
        if item.resubmission_count:
            group = f"{group} · ×{item.resubmission_count}"
        data = {
            "id": item.id,
            "title": item.title,
            "subject": item.subject,
            "group": group,
            "open_url": reverse("exams:question_submission_chair_review", args=[item.id]),
            "error_count": item.error_count,
            "warning_count": item.warning_count,
            "status_badge": status_badge(item.status),
            "routed_to_dean": item.routed_to_dean,
        }
        rows.append(
            {
                "row_head": item.title,
                "head_include": f"{CELL_DIR}_chair_cell_title.html",
                "cells": [
                    {"text": item.teacher.get_full_name() or item.teacher.username},
                    {"include": f"{CELL_DIR}_cell_status.html"},
                    {"text": item.question_count, "num": True},
                    {"include": f"{CELL_DIR}_cell_signals.html"},
                    {"text": _when(item.created_at), "nowrap": True},
                ],
                "actions_include": f"{CELL_DIR}_chair_row_actions.html",
                "data": data,
            }
        )
    return rows


def section_ui(*, counts, filters, items, teachers, exam_kinds, status_values, has_filters, total):
    state = "ready" if items else "empty"
    if has_filters or total:
        state_title = pgettext("accounts.profile.question_chair_review", "Bu şərtlərə uyğun sual dəsti tapılmadı.")
    else:
        state_title = pgettext("accounts.profile.question_chair_review", "Təsdiq gözləyən sual dəsti yoxdur.")
    return {
        "subtitle": pgettext(
            "accounts.profile.question_chair_review",
            "Müəllimlərinizin imtahan sual dəstlərini təsdiqləyin — yalnız təsdiqdən sonra İmtahan Mərkəzinə gedir.",
        ),
        "kpi_tiles": kpi_tiles(counts, active_status=filters.get("status", "")),
        "filter_fields": filter_fields(
            filters=filters, teachers=teachers, exam_kinds=exam_kinds, status_values=status_values
        ),
        "columns": columns(),
        "table_rows": table_rows(items),
        "table_state": state,
        "state_title": state_title,
    }


__all__ = ["section_ui", "status_badge"]
