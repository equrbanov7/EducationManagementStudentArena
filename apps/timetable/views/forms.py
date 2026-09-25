"""Səhifə kontekst köməkçiləri — işləmə sətri, yeni işləmə forması, çəki etiketləri."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils.translation import pgettext

from apps.registrar.public import schedule, schedule_manage

from ..constants import ScopeKind

_CTX = "timetable.run"


def weight_labels() -> dict:
    return {
        "teacher_idle": pgettext(_CTX, "Müəllimin boş cütü (pəncərə)"),
        "discouraged": pgettext(_CTX, "«Dəyişdirilə bilən» saatın istifadəsi"),
        "group_single_day": pgettext(_CTX, "Qrupun bir dərs üçün gəldiyi gün"),
        "same_subject_day": pgettext(_CTX, "Eyni fənn eyni gün (mühazirə + məşğələ)"),
        "group_overload": pgettext(_CTX, "Qrupun gündəlik limiti aşması"),
        "teacher_overload": pgettext(_CTX, "Müəllimin gündəlik limiti aşması"),
        "move": pgettext(_CTX, "Dərc olunmuş cədvəldən fərq (sabitlik)"),
    }


def _name(user) -> str:
    if user is None:
        return ""
    return (user.get_full_name() or "").strip() or user.username


def run_row(run, tones) -> dict:
    kpis = run.kpis or {}
    soft = kpis.get("soft") or {}
    scope = run.scope or {}
    return {
        "id": str(run.pk),
        "title": run.title or str(run.pk)[:8],
        "scope_label": str(dict(ScopeKind.choices).get(scope.get("kind"), "")),
        "status": run.status,
        "status_label": run.get_status_display(),
        "tone": tones.get(run.status, "neutral"),
        "placed": kpis.get("placed"),
        "events": kpis.get("events"),
        "hard": kpis.get("hard_total"),
        "idle": soft.get("teacher_idle_per_week"),
        "elapsed": kpis.get("elapsed"),
        "created_by": _name(run.created_by),
        "created_at": run.created_at,
        "published_at": run.published_at,
        "seed": run.seed,
        "time_limit": (run.params or {}).get("time_limit"),
        "error": run.error,
        "url": reverse("timetable:run_detail", args=[run.pk]),
    }


def _group_choices(actor, organization, period) -> list:
    rows = (
        schedule_manage.scoped_offerings(actor, organization, period=period)
        .exclude(group__isnull=True)
        .values_list("group_id", "group__name")
        .distinct()
    )
    return sorted(({"value": str(gid), "label": name} for gid, name in rows), key=lambda row: row["label"])


def new_run_form(request, organization, period, *, options, source, defaults, stream_policies, weights) -> dict:
    """«Yeni işləmə» forması — mənbə işləmə verilibsə onun əhatə/parametrləri ilə doldurulur."""
    params = dict(defaults)
    scope = {"kind": ScopeKind.FACULTY, "unit_ids": [], "group_ids": []}
    priorities = []
    seed = 1
    if source is not None:
        params.update(source.params or {})
        scope.update(source.scope or {})
        seed = source.seed
        order = (source.priorities or {}).get("teachers") or []
        names = {user.pk: _name(user) for user in get_user_model().objects.filter(pk__in=order)}
        priorities = [{"id": pk, "name": names.get(pk, str(pk))} for pk in order if pk in names]
    if not scope.get("unit_ids"):
        first = (options["faculties"] or options["programs"] or [{}])[0].get("id")
        scope["unit_ids"] = [first] if first else []
        if not options["faculties"] and options["programs"]:
            scope["kind"] = ScopeKind.PROGRAM
    custom = params.get("weights") or {}
    for item in weights:
        item["value"] = custom.get(item["key"], item["value"])
    weekday_set = set(params.get("weekdays") or [])
    return {
        "scope_kinds": [{"value": value, "label": str(label)} for value, label in ScopeKind.choices],
        "scope": scope,
        "faculties": options["faculties"],
        "programs": options["programs"],
        "faculty_options": [{"value": row["id"], "label": row["name"]} for row in options["faculties"]],
        "program_options": [{"value": row["id"], "label": row["name"]} for row in options["programs"]],
        "scope_unit": (scope.get("unit_ids") or [""])[0],
        "group_choices": _group_choices(request.user, organization, period),
        "params": params,
        "seed": seed,
        "weekday_choices": [
            {"value": num, "label": str(label), "checked": num in weekday_set} for num, label in schedule.WEEKDAYS
        ],
        "stream_choices": [{"value": value, "label": str(label)} for value, label in stream_policies],
        "weights": weights,
        "priorities": priorities,
        "source_run": source,
        "precheck_url": reverse("timetable:api_precheck"),
        "start_url": reverse("timetable:api_run_start"),
    }


__all__ = ["new_run_form", "run_row", "weight_labels"]
