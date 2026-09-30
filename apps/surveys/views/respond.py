"""Sorğu qurucusu (2026-09-30) — ümumi sorğunun respondent səhifələri (``/sorgu/s/<id>/…``).

Kabinet qabığından KƏNAR, mobil-birinci forma: bölmələr, irəliləyiş zolağı, avtomatik saxlama
(şəxsli sorğu — server qaralaması; anonim sorğu — yalnız brauzerin ``sessionStorage``-ı),
server yoxlaması, «təşəkkür» səhifəsi. View-as altında BAĞLIDIR (aktor istifadəçinin adından
nə doldura, nə də keçə bilər). Keç / möhlət POST-ları qapı vəziyyətini təzələyir.
"""

from __future__ import annotations

import json
import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext
from django.views.decorators.http import require_http_methods, require_POST

from ..constants import SHORT_TEXT_MAX_LENGTH, TEXT_MAX_LENGTH, QuestionKind
from ..defaults import TEXT_PRIVACY_HINT
from ..services import survey_gate
from ..services.answers import choice_keys, field_name, validate_answers
from ..services.survey_respond import (
    AlreadyAnswered,
    RespondError,
    can_take,
    defer,
    load_draft,
    save_draft,
    skip_once,
    submit,
    survey_for,
)
from ..services.survey_results import likert_labels

_CTX = "surveys.respond"


def _unavailable(request, reason, status=403):
    return render(request, "surveys/unavailable.html", {"reason": reason}, status=status)


def _load(request, survey_id):
    """``(survey, None)`` və ya ``(None, cavab)``."""
    if getattr(request, "is_view_as", False):
        return None, _unavailable(request, "view_as")
    organization = getattr(request, "organization", None)
    if organization is None:
        return None, _unavailable(request, "no_org", status=404)
    try:
        survey_id = uuid.UUID(str(survey_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise Http404 from exc
    survey = survey_for(organization, survey_id)
    if survey is None:
        raise Http404
    return survey, None


def _row(question, value, error):
    options = question.options if isinstance(question.options, dict) else {}
    row = {
        "question": question,
        "name": field_name(question),
        "text": question.display_text,
        "help": question.display_help_text,
        "kind": question.kind,
        "value": value,
        "values": value if isinstance(value, list) else ([value] if value else []),
        "error": error,
    }
    if question.kind == QuestionKind.LIKERT5:
        row["choices"] = [
            (str(score), label) for score, label in zip(range(1, 6), likert_labels(question), strict=True)
        ]
    elif question.kind == QuestionKind.NPS:
        anchors = options.get("anchors") or []
        row["choices"] = [str(score) for score in range(0, 11)]
        row["anchor_low"] = anchors[0] if anchors and anchors[0] else pgettext(_CTX, "Heç ehtimal etmirəm")
        row["anchor_high"] = anchors[1] if len(anchors) > 1 and anchors[1] else pgettext(_CTX, "Mütləq")
    elif question.kind in (QuestionKind.SINGLE, QuestionKind.MULTI):
        row["choices"] = [(item["key"], item.get("label", "")) for item in options.get("choices") or []]
        row["min"], row["max"] = options.get("min"), options.get("max")
    elif question.kind == QuestionKind.YESNO:
        row["choices"] = [("1", pgettext(_CTX, "Bəli")), ("0", pgettext(_CTX, "Xeyr"))]
    row["maxlength"] = SHORT_TEXT_MAX_LENGTH if question.kind == QuestionKind.SHORT_TEXT else TEXT_MAX_LENGTH
    return row


def _sections(survey, questions, values=None, errors=None):
    values, errors = values or {}, errors or {}
    pages = {page.pk: page for page in survey.template.pages.all()}
    sections, index = [], {}
    for question in questions:
        key = question.page_id
        if key not in index:
            page = pages.get(key)
            index[key] = len(sections)
            sections.append(
                {
                    "title": page.title if page else "",
                    "description": page.description if page else "",
                    "rows": [],
                }
            )
        value = values.get(question.code, [] if question.kind == QuestionKind.MULTI else "")
        sections[index[key]]["rows"].append(_row(question, value, errors.get(question.code, "")))
    return sections


def _draft_to_values(questions, draft) -> dict:
    values = {}
    for question in questions:
        raw = draft.get(field_name(question))
        if question.kind == QuestionKind.MULTI:
            keys = choice_keys(question)
            values[question.code] = [item for item in (raw if isinstance(raw, list) else []) if item in keys]
        elif isinstance(raw, str):
            values[question.code] = raw
    return values


def _questions(survey):
    return list(survey.template.questions.select_related("page").order_by("page__order", "order", "code"))


def _form_context(request, survey, questions, values=None, errors=None):
    required = sum(1 for question in questions if question.required)
    return {
        "survey": survey,
        "sections": _sections(survey, questions, values, errors),
        "errors": errors or {},
        "total": len(questions),
        "required_total": required,
        "privacy_hint": pgettext("surveys.question", TEXT_PRIVACY_HINT),
        "draft_url": reverse("surveys:draft", args=[survey.pk]) if not survey.anonymous else "",
        "storage_key": f"ems-survey-{survey.pk}-{request.user.pk}",
        "inbox_url": reverse("accounts:profile") + "?section=surveys-inbox",
    }


@login_required
@require_http_methods(["GET", "POST"])
def take(request, survey_id):
    survey, denied = _load(request, survey_id)
    if denied:
        return denied
    ok, reason = can_take(survey, request.user, getattr(request, "org_memberships", None))
    if not ok:
        if reason == "done":
            return redirect("surveys:survey_thanks", survey_id=survey.pk)
        status = 403 if reason == "not_audience" else 200
        return render(request, "surveys/respond/closed.html", {"survey": survey, "reason": reason}, status=status)
    questions = _questions(survey)
    if request.method == "POST":
        cleaned, errors, values = validate_answers(questions, request.POST)
        if errors:
            return render(
                request,
                "surveys/respond/form.html",
                _form_context(request, survey, questions, values, errors),
                status=400,
            )
        try:
            submit(survey, request.user, cleaned)
        except AlreadyAnswered:
            return redirect("surveys:survey_thanks", survey_id=survey.pk)
        except RespondError as exc:
            messages.warning(request, exc.messages[0])
            return redirect("surveys:home")
        survey_gate.invalidate_state(request)
        return redirect("surveys:survey_thanks", survey_id=survey.pk)
    values = _draft_to_values(questions, load_draft(survey, request.user))
    return render(request, "surveys/respond/form.html", _form_context(request, survey, questions, values))


@login_required
@require_POST
def draft(request, survey_id):
    """Avtomatik saxlama (yalnız şəxsli sorğu) — JSON ``{"data": {name: value}}``."""
    survey, denied = _load(request, survey_id)
    if denied:
        return JsonResponse({"ok": False}, status=403)
    ok, _reason = can_take(survey, request.user, getattr(request, "org_memberships", None))
    if not ok or survey.anonymous:
        return JsonResponse({"ok": False}, status=409)
    if len(request.body) > 64 * 1024:
        return JsonResponse({"ok": False}, status=413)
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except ValueError:  # UnicodeDecodeError da ValueError-dur
        return JsonResponse({"ok": False}, status=400)
    save_draft(survey, request.user, payload.get("data") if isinstance(payload, dict) else {})
    return JsonResponse({"ok": True, "saved_at": timezone.localtime().strftime("%H:%M")})


@login_required
@require_POST
def skip(request, survey_id):
    survey, denied = _load(request, survey_id)
    if denied:
        return denied
    ok, _reason = can_take(survey, request.user, getattr(request, "org_memberships", None))
    if not ok:
        return redirect("surveys:home")
    try:
        skip_once(request, survey)
    except RespondError as exc:
        messages.warning(request, exc.messages[0])
        return redirect("surveys:home")
    survey_gate.invalidate_state(request)
    messages.info(
        request,
        pgettext(_CTX, "Bu dəfə keçdiniz. Növbəti girişdə sorğunu doldurmadan kabinetə daxil ola bilməyəcəksiniz."),
    )
    return redirect("accounts:profile")


@login_required
@require_POST
def defer_survey(request, survey_id):
    survey, denied = _load(request, survey_id)
    if denied:
        return denied
    try:
        defer(request, survey)
    except RespondError as exc:
        messages.warning(request, exc.messages[0])
        return redirect("surveys:home")
    messages.info(request, pgettext(_CTX, "Sorğunu 24 saat ərzində doldurmağı unutmayın."))
    return redirect("accounts:profile")


@login_required
def thanks(request, survey_id):
    survey, denied = _load(request, survey_id)
    if denied:
        return denied
    return render(
        request,
        "surveys/respond/thanks.html",
        {
            "survey": survey,
            "inbox_url": reverse("accounts:profile") + "?section=surveys-inbox",
            "home_url": reverse("surveys:home"),
        },
    )
