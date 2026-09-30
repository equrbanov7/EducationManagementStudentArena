"""Sorğu qurucusu (2026-09-30) — ``/sorgu/qurucu/…`` POST ucları (``survey.manage``, org-wide).

Bölmənin özü kabinetdə render olunur (``?section=surveys-builder`` → ``survey_cabinet`` tag-ı);
bu uclar əməli icra edib eyni host-dakı ``next``-ə qayıdır. Sual redaktoru XHR ilə çağırılır və
``{"ok", "message", "html"}`` qaytarır (siyahı serverdə yenidən render olunur — JS yalnız
dəyişdirir); JS-siz forma POST-u da işləyir (yönləndirmə + mesaj). İcazə hər ucda FAIL-CLOSED
yenidən yoxlanılır; view-as READONLY yazıları middleware bloklayır.
"""

from __future__ import annotations

import datetime
import uuid

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponseForbidden, JsonResponse
from django.shortcuts import redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import pgettext, pgettext_lazy
from django.views.decorators.http import require_POST

from ..constants import SurveyStatus
from ..models import Survey, SurveyPage, SurveyQuestion
from ..services import questions as editor
from ..services import survey_builder as builder
from ..services.access import can_manage_campaigns

_CTX = "surveys.builder"


def editor_url(survey, tab="") -> str:
    url = reverse("accounts:profile") + f"?section=surveys-builder&survey={survey.pk}"
    return f"{url}&tab={tab}" if tab else url


def list_url() -> str:
    return reverse("accounts:profile") + "?section=surveys-builder"


def _next(request, fallback) -> str:
    candidate = (request.POST.get("next") or "").strip()
    if candidate and url_has_allowed_host_and_scheme(
        candidate, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return candidate
    return fallback


def _is_xhr(request) -> bool:
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


def _guard(request):
    organization = getattr(request, "organization", None)
    if not can_manage_campaigns(request.user, organization, request=request):
        return None
    return organization


def _survey(organization, survey_id) -> Survey:
    try:
        pk = uuid.UUID(str(survey_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise Http404 from exc
    survey = Survey.objects.filter(organization=organization, pk=pk).select_related("template", "organization").first()
    if survey is None:
        raise Http404
    return survey


def _date(raw):
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return datetime.date.fromisoformat(raw)
    except ValueError as exc:
        raise ValidationError(pgettext(_CTX, "Tarix düzgün formatda deyil.")) from exc


def _forbidden():
    return HttpResponseForbidden(pgettext(_CTX, "Bu əməliyyat üçün icazəniz yoxdur."))


@login_required
@require_POST
def create(request):
    organization = _guard(request)
    if organization is None:
        return _forbidden()
    try:
        survey = builder.create_survey(
            organization,
            kind=(request.POST.get("kind") or "").strip(),
            title=request.POST.get("title") or "",
            audience=(request.POST.get("audience") or "students").strip(),
            by_user=request.user,
            request=request,
        )
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
        return redirect(list_url())
    messages.success(request, pgettext(_CTX, "Sorğu yaradıldı — indi sualları yazın."))
    return redirect(editor_url(survey, "questions"))


def settings_values(post, survey) -> dict:
    """Formadan DƏYİŞƏ BİLƏN sahələr (dondurulmuş sahələr formada söndürülüb, burada oxunmur)."""
    values = {"title": post.get("title", survey.title), "description": post.get("description", "")}
    if survey.is_teacher_evaluation:
        return values
    draft = survey.status == SurveyStatus.DRAFT
    if draft:
        values.update(
            kind=post.get("kind") or survey.kind,
            anonymous=post.get("anonymous") == "1",
            audience=post.get("audience") or survey.audience,
            audience_filter={
                "units": post.getlist("units"),
                "programs": post.getlist("programs"),
                "course_years": post.getlist("course_years"),
            },
        )
    if "opens_on" in post:
        values["opens_on"] = _date(post.get("opens_on"))
    values["closes_on"] = _date(post.get("closes_on"))
    values["mandatory"] = post.get("obligation") == "mandatory"
    values["gate_policy"] = post.get("gate_policy") or survey.gate_policy
    values["defer_days"] = post.get("defer_days") or survey.defer_days
    if "min_group_size" in post:
        values["min_group_size"] = post.get("min_group_size") or survey.min_group_size
    return values


@login_required
@require_POST
def update(request, survey_id):
    organization = _guard(request)
    if organization is None:
        return _forbidden()
    survey = _survey(organization, survey_id)
    try:
        builder.update_settings(survey, settings_values(request.POST, survey), by_user=request.user, request=request)
        messages.success(request, pgettext(_CTX, "Ayarlar yadda saxlanıldı."))
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect(_next(request, editor_url(survey)))


_ACTIONS = {
    "publish": (builder.publish, pgettext_lazy(_CTX, "Sorğu dərc olundu.")),
    "close": (builder.close, pgettext_lazy(_CTX, "Sorğu bağlandı.")),
    "archive": (builder.archive, pgettext_lazy(_CTX, "Sorğu arxivə köçürüldü.")),
    "restore": (builder.restore, pgettext_lazy(_CTX, "Sorğu arxivdən çıxarıldı.")),
    "set_default": (builder.set_default, pgettext_lazy(_CTX, "Sual dəsti yeni kampaniyalar üçün defolt edildi.")),
}


@login_required
@require_POST
def action(request, survey_id):
    organization = _guard(request)
    if organization is None:
        return _forbidden()
    survey = _survey(organization, survey_id)
    name = (request.POST.get("action") or "").strip()
    target = _next(request, editor_url(survey))
    try:
        if name == "duplicate":
            clone = builder.duplicate(survey, by_user=request.user, request=request)
            messages.success(request, pgettext(_CTX, "Nüsxə yaradıldı (qaralama)."))
            return redirect(editor_url(clone))
        if name == "delete":
            builder.delete_draft(survey, by_user=request.user, request=request)
            messages.success(request, pgettext(_CTX, "Qaralama silindi."))
            return redirect(list_url())
        if name == "reopen":
            builder.reopen(
                survey, closes_on=_date(request.POST.get("closes_on")), by_user=request.user, request=request
            )
            messages.success(request, pgettext(_CTX, "Sorğu yenidən açıldı."))
            return redirect(target)
        handler = _ACTIONS.get(name)
        if handler is None:
            raise ValidationError(pgettext(_CTX, "Naməlum əməliyyat."))
        handler[0](survey, by_user=request.user, request=request)
        messages.success(request, str(handler[1]))
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    return redirect(target)


def _question(survey, raw_id):
    try:
        pk = uuid.UUID(str(raw_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValidationError(pgettext(_CTX, "Sual tapılmadı.")) from exc
    question = SurveyQuestion.objects.filter(template_id=survey.template_id, pk=pk).first()
    if question is None:
        raise ValidationError(pgettext(_CTX, "Sual tapılmadı."))
    return question


def _page(survey, raw_id):
    try:
        pk = uuid.UUID(str(raw_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValidationError(pgettext(_CTX, "Bölmə tapılmadı.")) from exc
    page = SurveyPage.objects.filter(template_id=survey.template_id, pk=pk).first()
    if page is None:
        raise ValidationError(pgettext(_CTX, "Bölmə tapılmadı."))
    return page


def _run_op(request, survey, op) -> str:
    post, user = request.POST, request.user
    kwargs = {"by_user": user, "request": request}
    if op == "add_question":
        editor.add_question(survey, post, **kwargs)
        return pgettext(_CTX, "Sual əlavə olundu.")
    if op == "update_question":
        editor.update_question(survey, _question(survey, post.get("question")), post, **kwargs)
        return pgettext(_CTX, "Sual yadda saxlanıldı.")
    if op == "delete_question":
        editor.delete_question(survey, _question(survey, post.get("question")), **kwargs)
        return pgettext(_CTX, "Sual silindi.")
    if op == "move_question":
        editor.move(survey, _question(survey, post.get("question")), post.get("direction"), **kwargs)
        return pgettext(_CTX, "Sıra dəyişdi.")
    if op == "reorder":
        editor.reorder(survey, post.get("group") or None, post.getlist("order"), **kwargs)
        return pgettext(_CTX, "Sıra dəyişdi.")
    if op == "add_page":
        editor.add_page(survey, post, **kwargs)
        return pgettext(_CTX, "Bölmə əlavə olundu.")
    if op == "update_page":
        editor.update_page(survey, _page(survey, post.get("page_id")), post, **kwargs)
        return pgettext(_CTX, "Bölmə yadda saxlanıldı.")
    if op == "delete_page":
        editor.delete_page(survey, _page(survey, post.get("page_id")), **kwargs)
        return pgettext(_CTX, "Bölmə silindi, sualları qonşu bölməyə keçdi.")
    if op == "move_page":
        editor.move_page(survey, _page(survey, post.get("page_id")), post.get("direction"), **kwargs)
        return pgettext(_CTX, "Sıra dəyişdi.")
    raise ValidationError(pgettext(_CTX, "Naməlum əməliyyat."))


@login_required
@require_POST
def questions(request, survey_id):
    organization = _guard(request)
    if organization is None:
        if _is_xhr(request):
            return JsonResponse(
                {"ok": False, "message": pgettext(_CTX, "Bu əməliyyat üçün icazəniz yoxdur.")}, status=403
            )
        return _forbidden()
    survey = _survey(organization, survey_id)
    op = (request.POST.get("op") or "").strip()
    try:
        message, ok, status = _run_op(request, survey, op), True, 200
    except ValidationError as exc:
        message, ok, status = " ".join(exc.messages), False, 400
    if not _is_xhr(request):
        (messages.success if ok else messages.error)(request, message)
        return redirect(_next(request, editor_url(survey, "questions")))
    from ..services.builder_panels import editor_questions_context

    html = render_to_string(
        "surveys/builder/_questions.html", {"ed": editor_questions_context(request, survey)}, request=request
    )
    return JsonResponse({"ok": ok, "message": message, "html": html}, status=status)
