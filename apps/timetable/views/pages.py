"""Müstəqil səhifələr (server-render) — hamısı ``schedule.manage`` + struktur əhatəsi.

Səhifələr: işləmələr (ana), müəllim əlçatanlığı, növbə siyasəti, yeni işləmə
(parametrlər + «Məlumatı yoxla»), işləmənin baxışı (şəbəkə, yerləşməyənlər, dərc).
İnteraktiv əməllər ``views/api.py``-dakı JSON endpoint-lərə gedir.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.cache import never_cache

from core.search_text import tolerant_match

from ..constants import (
    DEFAULT_PARAMS,
    KIND_LAB,
    KIND_LECTURE,
    KIND_SEMINAR,
    TUNABLE_WEIGHTS,
    Band,
    RunStatus,
    StreamPolicy,
)
from ..engine import Weights
from ..services import access, availability, policy, review, teachers
from ..sources import scope_options
from .common import base_context
from .forms import new_run_form, run_row, weight_labels

_STATUS_TONE = {
    RunStatus.DONE: "success",
    RunStatus.PUBLISHED: "primary",
    RunStatus.FAILED: "danger",
    RunStatus.RUNNING: "warning",
    RunStatus.QUEUED: "warning",
}


def _period(organization, request):
    period = access.period_or_default(organization, request.GET.get("period"))
    if period is None:
        raise Http404
    return period


@login_required
@never_cache
def home(request):
    organization = access.organization_for(request)
    period = _period(organization, request)
    runs = access.visible_runs(request.user, organization, period).select_related("created_by").order_by("-created_at")
    context = base_context(request, organization, period, "home")
    context["runs"] = [run_row(run, _STATUS_TONE) for run in runs[:40]]
    return render(request, "timetable/home.html", context)


@login_required
@never_cache
def availability_page(request):
    organization = access.organization_for(request)
    period = _period(organization, request)
    query = str(request.GET.get("q") or "").strip()[:80]
    context = base_context(request, organization, period, "availability")
    context.update(
        {
            "query": query,
            "teachers": teachers.teacher_rows(request.user, organization, period, query=query),
            "selected": None,
        }
    )
    raw = request.GET.get("teacher")
    if raw:
        teacher = access.teacher_or_404(request.user, organization, period, raw)
        row = availability.get_row(organization, period, teacher)
        subjects = teachers.teacher_subjects(request.user, organization, period, teacher)
        prios = (row.subject_priorities if row is not None else None) or {}
        for subject in subjects:
            subject["priority"] = int(prios.get(subject["subject_id"]) or 1)
            subject["kinds_text"] = _kinds_text(subject["kinds"])
        context.update(
            {
                "selected": {
                    "id": teacher.pk,
                    "name": (teacher.get_full_name() or "").strip() or teacher.username,
                    "max_pairs_per_day": getattr(row, "max_pairs_per_day", None) or "",
                    "max_days_per_week": getattr(row, "max_days_per_week", None) or "",
                    "priority": getattr(row, "priority", 1) or 1,
                    "note": getattr(row, "note", "") or "",
                    "updated_at": getattr(row, "updated_at", None),
                },
                "matrix": availability.matrix(organization, row),
                "subjects": subjects,
                "priority_choices": [{"value": n, "label": str(n)} for n in range(1, 6)],
                "save_url": reverse("timetable:api_availability"),
            }
        )
    return render(request, "timetable/availability.html", context)


def _kinds_text(kinds) -> str:
    from django.utils.translation import pgettext

    labels = {
        KIND_LECTURE: pgettext("timetable.availability", "mühazirə"),
        KIND_SEMINAR: pgettext("timetable.availability", "seminar"),
        KIND_LAB: pgettext("timetable.availability", "laboratoriya"),
    }
    parts = [
        f"{labels.get(kind, kind)} {hours} s" if hours else str(labels.get(kind, kind)) for kind, hours in kinds.items()
    ]
    return ", ".join(parts)


@login_required
@never_cache
def policies_page(request):
    organization = access.organization_for(request)
    period = _period(organization, request)
    query = str(request.GET.get("q") or "").strip()[:80]
    rows = policy.group_rows(request.user, organization, period, access.scoped_groups(request.user, organization))
    if query:
        # Qrup adı kod rejimində: «234king» → «234 K ing» (sahib 2026-09-26).
        rows = [row for row in rows if tolerant_match(query, row["name"], compact=True)]
    context = base_context(request, organization, period, "policies")
    context.update(
        {
            "levels": policy.level_rows(organization),
            "band_choices": [{"code": code, "label": str(label)} for code, label in Band.choices],
            "groups": rows[:400],
            "groups_total": len(rows),
            "query": request.GET.get("q", ""),
            "save_url": reverse("timetable:api_policy"),
        }
    )
    return render(request, "timetable/policies.html", context)


@login_required
@never_cache
def new_run_page(request):
    organization = access.organization_for(request)
    period = _period(organization, request)
    source = None
    if request.GET.get("from"):
        source = access.run_or_404(request, organization, request.GET.get("from"))
    context = base_context(request, organization, period, "new")
    options = scope_options(request.user, organization)
    context.update(
        new_run_form(
            request,
            organization,
            period,
            options=options,
            source=source,
            defaults=DEFAULT_PARAMS,
            stream_policies=StreamPolicy.choices,
            weights=[
                {"key": key, "label": weight_labels().get(key, key), "value": getattr(Weights(), key)}
                for key in TUNABLE_WEIGHTS
            ],
        )
    )
    return render(request, "timetable/run_new.html", context)


@login_required
@never_cache
def run_detail(request, run_id):
    organization = access.organization_for(request)
    run = access.run_or_404(request, organization, run_id)
    view = request.GET.get("view") if request.GET.get("view") in ("group", "teacher", "room") else "group"
    events = review.events_of(review.draft_rows(run))
    options = review.options(events)
    choices = options["groups" if view == "group" else "teachers" if view == "teacher" else "rooms"]
    key = str(request.GET.get("key") or "")
    if not any(choice["value"] == key for choice in choices):
        key = choices[0]["value"] if choices else ""
    weekdays = (run.params or {}).get("weekdays") or list(DEFAULT_PARAMS["weekdays"])
    selected = review.select(events, run, view, key)
    grid = review.grid(run, selected, weekdays)
    unplaced = review.unplaced(events)
    context = base_context(request, organization, run.period, "home")
    context.update(
        {
            "run": run,
            "run_info": run_row(run, _STATUS_TONE),
            "kpi_tiles": review.kpi_tiles(run) if run.kpis else [],
            "view": view,
            "view_key": key,
            "view_choices": choices,
            "grid": grid,
            "unplaced": unplaced,
            "split_teachers": [e for e in events if e["split_teacher"] and e["weekday"] is not None][:40],
            "can_edit": review.can_edit(run),
            "is_active": run.status in (RunStatus.QUEUED, RunStatus.RUNNING),
            "events_json": {e["key"]: e for e in selected + unplaced},
            "action_url": reverse("timetable:api_run_action", args=[run.pk]),
            "status_url": reverse("timetable:api_run_status", args=[run.pk]),
            "rerun_url": reverse("timetable:new_run") + f"?period={run.period_id}&from={run.pk}",
            "weekday_choices": [{"value": day["weekday"], "label": day["label"]} for day in grid["days"]],
            "pair_choices": [
                {"value": row["no"], "label": f"{row['no']} · {row['start_text']}"} for row in grid["rows"]
            ],
        }
    )
    return render(request, "timetable/run_detail.html", context)


__all__ = ["availability_page", "home", "new_run_page", "policies_page", "run_detail"]
