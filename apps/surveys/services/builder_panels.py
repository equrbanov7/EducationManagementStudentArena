"""Sorğu qurucusu (2026-09-30) — kabinet bölmələrinin kontekstləri (``survey_cabinet`` tag-ları).

* ``surveys-builder`` (``survey.manage``): siyahı (filtr, kartlar, yeni sorğu forması) və
  ``?survey=<id>`` ilə redaktor — «Ayarlar», «Suallar», «Nəticələr» tab-ları (``&tab=``).
* ``surveys-inbox`` (hər üzv): gözləyən / tamamlanmış / bağlı sorğular.

İcazə FAIL-CLOSED yenidən yoxlanılır; GET-də yalnız özünü bərpa edən yazılar (sarğısız dəstlərin
qəbulu, vaxtı çatmış bildirişlər) olur və view-as altında onlar da yoxdur.
"""

from __future__ import annotations

import uuid

from django.db.models import Count
from django.urls import reverse
from django.utils import timezone

from .. import registrar_bridge as bridge
from ..constants import (
    MAX_DEFER_DAYS,
    MIN_GROUP_SIZE_CEIL,
    MIN_GROUP_SIZE_FLOOR,
    Audience,
    GatePolicy,
    QuestionKind,
    Section,
    SurveyKind,
    SurveyStatus,
)
from ..models import Survey, SurveyCampaign
from .access import can_manage_campaigns
from .analytics_guard import count_bucket
from .audience import normalize_filter, unit_choices
from .questions import allowed_kinds, is_locked
from .survey_builder import GENERIC_SURVEY_KINDS, default_close_date
from .survey_results import likert_labels, participation, question_results, respondents, results_state

STATUS_FILTERS = ("active", "draft", "published", "closed", "archived", "all")
TABS = ("settings", "questions", "results")


def _request_org(context):
    request = context.get("request")
    return request, getattr(request, "organization", None)


def _kind_label(kind) -> str:
    return str(dict(SurveyKind.choices).get(kind, kind))


def _choices(enum_cls, values=None):
    labels = dict(enum_cls.choices)
    return [{"value": value, "label": str(labels[value])} for value in (values or labels)]


# ── Siyahı ──────────────────────────────────────────────────────────────────


def _list_context(request, organization, status_filter) -> dict:
    from .survey_notify import notify_due
    from .templates import adopt_templates

    if not getattr(request, "is_view_as", False):
        adopt_templates(organization)
        notify_due(organization)
    today = timezone.localdate()
    queryset = Survey.objects.filter(organization=organization).select_related("template")
    if status_filter == "active":
        queryset = queryset.exclude(status=SurveyStatus.ARCHIVED)
    elif status_filter != "all":
        queryset = queryset.filter(status=status_filter)
    surveys = list(queryset.annotate(done=Count("participations")).order_by("-created_at")[:200])
    template_ids = [survey.template_id for survey in surveys if survey.is_teacher_evaluation]
    used = dict(
        SurveyCampaign.objects.filter(template_id__in=template_ids)
        .values("template_id")
        .annotate(c=Count("id"))
        .values_list("template_id", "c")
    )
    rows = []
    for survey in surveys:
        rows.append(
            {
                "survey": survey,
                "kind_label": _kind_label(survey.kind),
                "status": survey.effective_status(today),
                "audience_label": str(dict(Audience.choices).get(survey.audience, "")),
                "narrowed": bool(any(normalize_filter(survey.audience_filter).values())),
                "done_label": count_bucket(survey.done) if survey.anonymous else survey.done,
                "is_default": survey.is_teacher_evaluation and survey.template.is_default,
                "campaigns": used.get(survey.template_id, 0),
                "edit_url": _editor_url(survey),
                "results_url": _editor_url(survey, "results"),
            }
        )
    return {
        "mode": "list",
        "rows": rows,
        "status_filter": status_filter,
        "status_filters": [
            {"value": value, "url": f"{_list_url()}&status={value}", "active": value == status_filter}
            for value in STATUS_FILTERS
        ],
        "kinds": _choices(SurveyKind),
        "audiences": _choices(Audience),
        "create_url": reverse("surveys:builder_create"),
    }


def _list_url() -> str:
    return reverse("accounts:profile") + "?section=surveys-builder"


def _editor_url(survey, tab="") -> str:
    url = f"{_list_url()}&survey={survey.pk}"
    return f"{url}&tab={tab}" if tab else url


# ── Redaktor ────────────────────────────────────────────────────────────────


def _options_text(question) -> str:
    options = question.options if isinstance(question.options, dict) else {}
    return "\n".join(item.get("label", "") for item in options.get("choices") or [])


def _question_row(question, locked) -> dict:
    options = question.options if isinstance(question.options, dict) else {}
    labels = options.get("labels") or []
    anchors = options.get("anchors") or []
    return {
        "q": question,
        "kind_label": str(dict(QuestionKind.choices).get(question.kind, question.kind)),
        "choices_text": _options_text(question),
        "choices": [item.get("label", "") for item in options.get("choices") or []],
        "labels": [labels[index] if index < len(labels) else "" for index in range(5)],
        "label_defaults": likert_labels(question) if question.kind == QuestionKind.LIKERT5 else [],
        "anchors": [anchors[index] if index < len(anchors) else "" for index in range(2)],
        "min": options.get("min"),
        "max": options.get("max"),
        "revisions": len(question.history or []),
        "metric": question.code in ("overall", "recommend", "satisfaction", "facilities"),
        "locked": locked,
    }


def editor_questions_context(request, survey) -> dict:
    locked = is_locked(survey)
    questions = list(survey.template.questions.select_related("page").order_by("order", "code"))
    groups = []
    if survey.is_teacher_evaluation:
        for value, label in Section.choices:
            rows = [_question_row(q, locked) for q in questions if q.section == value]
            groups.append({"key": value, "title": str(label), "rows": rows, "page": None})
    else:
        pages = list(survey.template.pages.order_by("order", "id"))
        for index, page in enumerate(pages):
            rows = [_question_row(q, locked) for q in questions if q.page_id == page.pk]
            groups.append(
                {
                    "key": str(page.pk),
                    "title": page.title,
                    "rows": rows,
                    "page": page,
                    "first": index == 0,
                    "last": index == len(pages) - 1,
                }
            )
        orphans = [_question_row(q, locked) for q in questions if q.page_id is None]
        if orphans:
            groups.append({"key": "", "title": "", "rows": orphans, "page": None})
    kind_labels = dict(QuestionKind.choices)
    return {
        "survey": survey,
        "locked": locked,
        "groups": groups,
        "count": len(questions),
        "kinds": [{"value": kind, "label": str(kind_labels[kind])} for kind in allowed_kinds(survey)],
        "sections": _choices(Section),
        "post_url": reverse("surveys:builder_questions", args=[survey.pk]),
        "next_url": _editor_url(survey, "questions"),
        "teacher": survey.is_teacher_evaluation,
    }


def _settings_context(request, survey) -> dict:
    organization = survey.organization
    flt = normalize_filter(survey.audience_filter)
    draft = survey.status == SurveyStatus.DRAFT
    today = timezone.localdate()
    units = unit_choices(organization) if not survey.is_teacher_evaluation else []
    programs = bridge.program_choices(organization) if not survey.is_teacher_evaluation else []
    return {
        "post_url": reverse("surveys:builder_update", args=[survey.pk]),
        "frozen": not draft,
        "opens_frozen": not draft and bool(survey.opens_on and survey.opens_on <= today),
        "k_frozen": bool(survey.results_published_at),
        "kinds": _choices(SurveyKind, GENERIC_SURVEY_KINDS),
        "audiences": _choices(Audience),
        "policies": _choices(GatePolicy),
        "units": [{**unit, "checked": unit["id"] in flt["units"]} for unit in units],
        "programs": [{**program, "checked": program["id"] in flt["programs"]} for program in programs],
        "years": [{"value": year, "checked": year in flt["course_years"]} for year in range(1, 7)],
        "selected_units": len(flt["units"]),
        "selected_programs": len(flt["programs"]),
        "k_floor": MIN_GROUP_SIZE_FLOOR,
        "k_ceil": MIN_GROUP_SIZE_CEIL,
        "defer_max": MAX_DEFER_DAYS,
        "suggested_close": default_close_date(today),
        "today": today,
    }


def _results_context(request, survey, manage) -> dict:
    if survey.is_teacher_evaluation:
        return {"teacher": True, "results_url": reverse("accounts:profile") + "?section=evaluation-results"}
    state = results_state(survey)
    data = {"teacher": False, "state": state, "participation": participation(survey) if state != "draft" else None}
    if state == "ready":
        data["results"] = question_results(survey, with_identity=manage and not survey.anonymous)
        data["respondents"] = respondents(survey) if manage and not survey.anonymous else []
        data["export_url"] = reverse("surveys:builder_export", args=[survey.pk])
    return data


def _editor_context(request, organization, survey, tab, manage) -> dict:
    today = timezone.localdate()
    context = {
        "mode": "editor",
        "survey": survey,
        "tab": tab,
        "manage": manage,
        "status": survey.effective_status(today),
        "kind_label": _kind_label(survey.kind),
        "tabs": [{"value": value, "url": _editor_url(survey, value), "active": value == tab} for value in TABS],
        "list_url": _list_url(),
        "action_url": reverse("surveys:builder_action", args=[survey.pk]),
        "next_url": _editor_url(survey, tab),
        "locked": is_locked(survey),
        "question_count": survey.template.questions.count(),
        "take_url": reverse("surveys:take", args=[survey.pk]) if not survey.is_teacher_evaluation else "",
        "grace_until": survey.grace_until,
        "is_default": survey.is_teacher_evaluation and survey.template.is_default,
    }
    if tab == "settings":
        context["settings"] = _settings_context(request, survey)
    elif tab == "questions":
        context["ed"] = editor_questions_context(request, survey)
    else:
        context["res"] = _results_context(request, survey, manage)
    return context


def builder_panel(context) -> dict:
    request, organization = _request_org(context)
    user = getattr(request, "user", None)
    manage = organization is not None and can_manage_campaigns(user, organization, request=request)
    if not manage:
        return {"has_access": False}
    raw = request.GET.get("survey") or ""
    if raw:
        try:
            survey = (
                Survey.objects.filter(organization=organization, pk=uuid.UUID(raw))
                .select_related("template", "organization")
                .first()
            )
        except (TypeError, ValueError):
            survey = None
        if survey is not None:
            tab = request.GET.get("tab") if request.GET.get("tab") in TABS else "settings"
            return {"has_access": True, **_editor_context(request, organization, survey, tab, manage)}
    status_filter = request.GET.get("status") if request.GET.get("status") in STATUS_FILTERS else "active"
    return {"has_access": True, **_list_context(request, organization, status_filter)}


def inbox_panel(context) -> dict:
    from .inbox import build_inbox

    request, organization = _request_org(context)
    if organization is None:
        return {"available": False}
    inbox = build_inbox(request)
    return {
        "available": True,
        **inbox,
        "count": len(inbox["pending"]) + (1 if inbox["campaign"] and inbox["campaign"]["pending"] else 0),
    }
