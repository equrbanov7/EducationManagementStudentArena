"""Sorğu qurucusu (2026-09-30) — ümumi sorğunun CSV ixracı (``/sorgu/qurucu/<id>/ixrac.csv``).

* ANONİM sorğu, və ya şəxsli sorğunu idarəçi OLMAYAN nəticə baxıcısı: yalnız AQREQATLAR (sual →
  variant → faiz / orta; açıq cavablar identifikatorsuz, təsadüfi sırada, yalnız k keçəndə) —
  ekranda göstərilən nə varsa, o.
* ŞƏXSLİ sorğu + ``survey.manage``: respondent başına sətir (ad, istifadəçi adı, vaxt, cavablar).
* Hər xana formula-neytrallaşdırılır (``core.export_safety``), ixrac audit jurnalına yazılır.
* Anonim sorğunun nəticəsi hələ dərc olunmayıbsa (davam edir) — 409.
"""

from __future__ import annotations

import io
import uuid

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, JsonResponse
from django.utils import timezone
from django.utils.translation import pgettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from core.export_safety import safe_csv_writer

from ..constants import CHOICE_KINDS, TEXT_KINDS, QuestionKind, SurveyKind
from ..models import Survey, SurveySubmission, SurveySubmissionAnswer
from ..services.access import can_manage_campaigns, results_scope
from ..services.survey_results import likert_labels, question_results, results_state

CTX = "surveys.export"


def _survey(request, survey_id):
    organization = getattr(request, "organization", None)
    try:
        pk = uuid.UUID(str(survey_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise Http404 from exc
    survey = (
        Survey.objects.filter(organization=organization, pk=pk)
        .exclude(kind=SurveyKind.TEACHER_EVALUATION)
        .select_related("template", "organization")
        .first()
    )
    if survey is None:
        raise Http404
    return survey


def _aggregate_rows(survey) -> list:
    data = question_results(survey)
    rows = []
    if data["suppressed"]:
        return [[pgettext(CTX, "Cavab sayı k-həddindən azdır — nəticələr gizlidir."), "", "", "", ""]]
    for card in data["questions"]:
        question = card["question"]
        text = question.display_text
        if card["hidden"]:
            rows.append([text, pgettext(CTX, "gizli (k-dan az cavab)"), "", "", card["answered_label"]])
            continue
        if question.kind in TEXT_KINDS:
            rows.extend([text, pgettext(CTX, "açıq cavab"), item["text"], "", ""] for item in card.get("texts", []))
            continue
        for bucket in card.get("buckets", []):
            rows.append([text, bucket["label"], f"{bucket['pct']}%", card.get("avg", ""), card["answered_label"]])
        if card.get("nps"):
            rows.append([text, "NPS", card["nps"]["score"], "", card["answered_label"]])
    return rows


def _answer_label(question, number, choices, text) -> str:
    if question.kind in TEXT_KINDS:
        return text
    if question.kind in CHOICE_KINDS:
        labels = {item.get("key"): item.get("label", "") for item in (question.options or {}).get("choices") or []}
        return "; ".join(labels.get(key, key) for key in choices or [])
    if question.kind == QuestionKind.YESNO:
        return pgettext("surveys.respond", "Bəli") if number == 1 else pgettext("surveys.respond", "Xeyr")
    if question.kind == QuestionKind.LIKERT5 and number:
        return f"{number} — {likert_labels(question)[number - 1]}"
    return "" if number is None else str(number)


def _respondent_rows(survey, questions) -> list:
    user_model = get_user_model()
    answers: dict = {}
    for submission_id, question_id, number, choices, text in SurveySubmissionAnswer.objects.filter(
        submission__survey=survey
    ).values_list("submission_id", "question_id", "number", "choices", "text"):
        answers.setdefault(submission_id, {})[question_id] = (number, choices, text)
    rows = []
    for pk, first, last, username, at in (
        SurveySubmission.objects.filter(survey=survey)
        .order_by("submitted_at")
        .values_list(
            "pk",
            "respondent__first_name",
            "respondent__last_name",
            "respondent__" + user_model.USERNAME_FIELD,
            "submitted_at",
        )
    ):
        given = answers.get(pk, {})
        cells = [_answer_label(question, *given[question.pk]) if question.pk in given else "" for question in questions]
        stamp = timezone.localtime(at).strftime("%Y-%m-%d %H:%M") if at else ""
        rows.append([f"{first or ''} {last or ''}".strip(), username or "", stamp, *cells])
    return rows


def _audit(request, survey, mode, rows):
    from core.audit import log_action
    from core.constants import AuditAction

    log_action(
        AuditAction.EXPORT,
        user=request.user,
        organization=survey.organization,
        request=request,
        resource_type="surveys.survey_results",
        resource_id=str(survey.pk),
        resource_repr=f"CSV · {mode}",
        reason=pgettext(CTX, "Sorğu nəticələrinin ixracı"),
        new_values={"mode": mode, "rows": rows, "anonymous": survey.anonymous},
    )


@never_cache
@login_required
@require_GET
def export_csv(request, survey_id):
    organization = getattr(request, "organization", None)
    manage = can_manage_campaigns(request.user, organization, request=request)
    if not (manage or results_scope(request.user, organization, request=request).is_org_wide):
        return JsonResponse({"ok": False, "error": "forbidden"}, status=403)
    survey = _survey(request, survey_id)
    if results_state(survey) != "ready":
        return JsonResponse({"ok": False, "error": "survey_open"}, status=409)
    buffer = io.StringIO()
    buffer.write("﻿")
    writer = safe_csv_writer(buffer)
    if manage and not survey.anonymous:
        questions = list(survey.template.questions.order_by("order", "code"))
        writer.writerow(
            [pgettext(CTX, "Ad"), pgettext(CTX, "İstifadəçi adı"), pgettext(CTX, "Vaxt")]
            + [question.display_text for question in questions]
        )
        rows, mode = _respondent_rows(survey, questions), "respondents"
    else:
        writer.writerow(
            [
                pgettext(CTX, "Sual"),
                pgettext(CTX, "Variant"),
                pgettext(CTX, "Faiz / cavab"),
                pgettext(CTX, "Orta"),
                pgettext(CTX, "Cavab sayı"),
            ]
        )
        rows, mode = _aggregate_rows(survey), "aggregates"
    for row in rows:
        writer.writerow(["" if value is None else value for value in row])
    _audit(request, survey, mode, len(rows))
    stamp = timezone.localdate().isoformat()
    response = HttpResponse(buffer.getvalue().encode("utf-8"), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="sorgu-{str(survey.pk)[:8]}-{stamp}.csv"'
    response["X-Content-Type-Options"] = "nosniff"
    return response
