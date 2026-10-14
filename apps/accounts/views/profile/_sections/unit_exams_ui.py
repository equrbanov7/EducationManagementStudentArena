"""«Bölmə imtahanları» — ems_ui komponent müqavilələrinə (KPI, filtr paneli, cədvəl, çekmecə) uyğun forma.

Məntiq ``unit_exams_query``-dədir; burada yalnız etiketlər, sütunlar, sətirlər və çekmecə JSON-u.
Fərdi tələbə balı YOXDUR — yalnız aqreqatlar; orta nəticə ``MIN_GROUP_FOR_AVG``-dən az bitirəndə gizlədilir.
"""

from __future__ import annotations

from urllib.parse import urlencode

from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import pgettext

from .unit_exams_query import MIN_GROUP_FOR_AVG

CTX = "accounts.unit_exams"
GROUPS_SHOWN = 2
STATUS_TONES = {"active": "success", "scheduled": "info", "finished": "neutral", "draft": "muted"}


def status_labels() -> dict:
    return {
        "active": pgettext(CTX, "Aktiv"),
        "scheduled": pgettext(CTX, "Planlaşdırılıb"),
        "finished": pgettext(CTX, "Bitib"),
        "draft": pgettext(CTX, "Qaralama"),
    }


def _choice_labels(choices) -> dict:
    return {key: str(label) for key, label in choices}


def _fmt_dt(value) -> str:
    if not value:
        return ""
    return date_format(timezone.localtime(value), "d.m.Y H:i")


def _pct(value) -> str:
    return "" if value is None else f"{round(float(value), 1):g}%"


def _author_name(user) -> str:
    return (user.get_full_name() or user.username) if user else "—"


# --------------------------------------------------------------------------- #
# KPI
# --------------------------------------------------------------------------- #


def kpi_tiles(kpi: dict, filters: dict) -> list[dict]:
    avg = kpi.get("avg")
    return [
        {"label": pgettext(CTX, "İMTAHAN"), "value": kpi["total"], "note": pgettext(CTX, "Bölmədə cəmi")},
        {
            "label": pgettext(CTX, "AKTİV"),
            "value": kpi["active"],
            "tone": "accent-success" if kpi["active"] else None,
            "filter": "status:active",
            "pressed": filters["status"] == "active",
            "note": pgettext(CTX, "Planlaşdırılıb: %(n)d") % {"n": kpi["scheduled"]},
        },
        {
            "label": pgettext(CTX, "BİTMİŞ"),
            "value": kpi["finished"],
            "filter": "status:finished",
            "pressed": filters["status"] == "finished",
            "note": pgettext(CTX, "Qaralama: %(n)d") % {"n": kpi["draft"]},
        },
        {
            "label": pgettext(CTX, "FİNAL / MİDTERM"),
            "value": f"{kpi['final']} / {kpi['midterm']}",
            "note": pgettext(CTX, "İmtahan növünə görə"),
        },
        {
            "label": pgettext(CTX, "İŞTİRAKÇI"),
            "value": kpi.get("participants") or 0,
            "note": (
                pgettext(CTX, "Orta nəticə: %(avg)s") % {"avg": _pct(avg)}
                if avg is not None
                else pgettext(CTX, "Orta nəticə hələ yoxdur")
            ),
        },
    ]


# --------------------------------------------------------------------------- #
# Filtr paneli
# --------------------------------------------------------------------------- #


def filter_fields(filters: dict, *, chair_options, period_options, kind_labels, form_labels) -> list[dict]:
    every = {"value": "", "label": pgettext(CTX, "Hamısı")}
    fields = [
        {
            "name": "ue_q",
            "label": pgettext(CTX, "Axtarış"),
            "kind": "search",
            "value": filters["search"],
            "placeholder": pgettext(CTX, "İmtahan, fənn və ya müəllif"),
            "wide": True,
        }
    ]
    if len(chair_options) > 1:
        fields.append(
            {
                "name": "ue_chair",
                "label": pgettext(CTX, "Kafedra"),
                "kind": "select",
                "searchable": True,
                "value": filters["chair"],
                "options": [every] + chair_options,
            }
        )
    fields += [
        {
            "name": "ue_kind",
            "label": pgettext(CTX, "İmtahan növü"),
            "kind": "select",
            "value": filters["kind"],
            "options": [every] + [{"value": key, "label": label} for key, label in kind_labels.items()],
        },
        {
            "name": "ue_form",
            "label": pgettext(CTX, "Forma"),
            "kind": "select",
            "value": filters["form"],
            "options": [every] + [{"value": key, "label": label} for key, label in form_labels.items()],
        },
        {
            "name": "ue_status",
            "label": pgettext(CTX, "Status"),
            "kind": "select",
            "value": filters["status"],
            "options": [every] + [{"value": key, "label": label} for key, label in status_labels().items()],
        },
    ]
    if period_options:
        fields.append(
            {
                "name": "ue_period",
                "label": pgettext(CTX, "Dövr"),
                "kind": "select",
                "value": filters["period"],
                "options": [every] + period_options,
            }
        )
    fields += [
        {
            "name": "ue_from",
            "label": pgettext(CTX, "Tarixdən"),
            "kind": "date",
            "value": filters["date_from"].isoformat() if filters["date_from"] else "",
        },
        {
            "name": "ue_to",
            "label": pgettext(CTX, "Tarixədək"),
            "kind": "date",
            "value": filters["date_to"].isoformat() if filters["date_to"] else "",
        },
    ]
    return fields


def base_params(filters: dict) -> dict:
    return {
        "section": "unit-exams",
        "ue_q": filters["search"],
        "ue_chair": filters["chair"],
        "ue_kind": filters["kind"],
        "ue_form": filters["form"],
        "ue_status": filters["status"],
        "ue_period": filters["period"],
        "ue_from": filters["date_from"].isoformat() if filters["date_from"] else "",
        "ue_to": filters["date_to"].isoformat() if filters["date_to"] else "",
    }


def _clean(params: dict) -> dict:
    return {key: value for key, value in params.items() if value not in ("", None)}


def pagination_query(params: dict, sort: str) -> str:
    return urlencode(_clean({**params, "ue_sort": sort if sort and sort != "-date" else ""}))


# --------------------------------------------------------------------------- #
# Cədvəl
# --------------------------------------------------------------------------- #


def columns(params: dict, current: str) -> list[dict]:
    specs = [
        ("title", pgettext(CTX, "İmtahan")),
        ("subject", pgettext(CTX, "Fənn")),
        ("", pgettext(CTX, "Qrup(lar)")),
        ("author", pgettext(CTX, "Müəllif")),
        ("", pgettext(CTX, "Növ")),
        ("date", pgettext(CTX, "Tarix")),
        ("", pgettext(CTX, "Status")),
        ("participants", pgettext(CTX, "İştirakçı / bitirən")),
        ("avg", pgettext(CTX, "Orta nəticə")),
    ]
    base = reverse("accounts:profile")
    result = []
    for key, label in specs:
        sort_dir = None
        sort_url = ""
        if key:
            sort_dir = "ascending" if current == key else "descending" if current == f"-{key}" else None
            target = f"-{key}" if current == key else key
            sort_url = f"{base}?{urlencode(_clean({**params, 'ue_sort': target}))}"
        result.append({"key": key, "label": label, "sortable": bool(key), "sort_url": sort_url, "sort_dir": sort_dir})
    return result


def _group_names(exam) -> list[str]:
    names = [unit.name for unit in exam.allowed_units.all()]
    names += [group.name for group in exam.allowed_groups.all() if group.name not in names]
    return names


def _subject_label(exam) -> str:
    if exam.subject_id:
        return exam.subject.name
    if exam.course_id:
        return exam.course.title
    return "—"


def table_row(exam, *, kind_labels, form_labels, statuses) -> dict:
    groups = _group_names(exam)
    shown_avg = exam.ue_avg if exam.ue_finished >= MIN_GROUP_FOR_AVG else None
    kind = kind_labels.get(exam.exam_type_extended or "", "")
    form = form_labels.get(exam.exam_type, "")
    return {
        "head_include": "accounts/profile/sections/unit_exams/_cell_title.html",
        "exam_id": exam.pk,
        "title": exam.title,
        "cells": [
            {"text": _subject_label(exam), "muted": not (exam.subject_id or exam.course_id)},
            {
                "include": "accounts/profile/sections/unit_exams/_cell_groups.html",
                "groups": groups[:GROUPS_SHOWN],
                "more": max(len(groups) - GROUPS_SHOWN, 0),
                "all": ", ".join(groups),
            },
            {"text": _author_name(exam.author)},
            {"text": " · ".join(part for part in (kind, form) if part) or "—"},
            {"text": _fmt_dt(exam.ue_date) or "—", "nowrap": True},
            {
                "include": "accounts/profile/sections/unit_exams/_cell_status.html",
                "tone": STATUS_TONES.get(exam.ue_status, "neutral"),
                "label": statuses.get(exam.ue_status, exam.ue_status),
            },
            {"text": f"{exam.ue_participants} / {exam.ue_finished}", "num": True},
            {"text": _pct(shown_avg) or "—", "num": True, "muted": shown_avg is None},
        ],
    }


def drawer_row(exam, *, user, kind_labels, form_labels, statuses) -> dict:
    """Çekmecə üçün OXU məlumatı. Linklər yalnız istifadəçinin AÇA BİLDİYİ səhifələrə (öz imtahanı)."""
    enough = exam.ue_finished >= MIN_GROUP_FOR_AVG
    own = exam.author_id == getattr(user, "pk", None)
    subject = exam.subject if exam.subject_id else None
    chair = subject.chair_unit if subject is not None and subject.chair_unit_id else None
    return {
        "id": exam.pk,
        "title": exam.title,
        "subject": f"{subject.code} · {subject.name}" if subject else "",
        "chair": chair.name if chair else "",
        "course": exam.course.title if exam.course_id else "",
        "author": _author_name(exam.author),
        "kind": kind_labels.get(exam.exam_type_extended or "", ""),
        "form": form_labels.get(exam.exam_type, ""),
        "mode": exam.get_mode_display(),
        "status": statuses.get(exam.ue_status, exam.ue_status),
        "status_tone": STATUS_TONES.get(exam.ue_status, "neutral"),
        "start": _fmt_dt(exam.start_datetime),
        "end": _fmt_dt(exam.end_datetime),
        "created": _fmt_dt(exam.created_at),
        "duration": exam.total_duration_minutes or None,
        "questions": exam.ue_questions,
        "groups": _group_names(exam),
        "participants": exam.ue_participants,
        "finished": exam.ue_finished,
        "attempts": exam.ue_attempts,
        "avg": _pct(exam.ue_avg) if enough else "",
        "pass_rate": _pct(exam.ue_passed * 100 / exam.ue_attempts) if enough and exam.ue_attempts else "",
        "hidden_small": bool(exam.ue_finished) and not enough,
        "detail_url": reverse("exams:teacher_exam_detail", kwargs={"slug": exam.slug}) if own else "",
        "results_url": reverse("exams:teacher_exam_results", kwargs={"slug": exam.slug}) if own else "",
    }


__all__ = [
    "CTX",
    "base_params",
    "columns",
    "drawer_row",
    "filter_fields",
    "kpi_tiles",
    "pagination_query",
    "status_labels",
    "table_row",
]
