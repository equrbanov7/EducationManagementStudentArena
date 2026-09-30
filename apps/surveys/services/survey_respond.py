"""Sorğu qurucusu (2026-09-30) — respondent tərəfi: əlçatanlıq, göndəriş, qaralama, keçid/möhlət.

Göndəriş: iştirak qəbzi ayrıca savepoint-də (``surveys_participation_once`` — paralel ikinci POST
``IntegrityError`` alır, heç nə yazılmır), sonra cavab: ANONİM sorğuda şəxssiz BUFERƏ
(``survey_buffer.enqueue``), ŞƏXSLİ sorğuda birbaşa ``respondent`` + ``submitted_at`` ilə.
Anonim sorğuda heç bir audit/log yazılmır (qəbz kifayətdir). Qaralama göndərişdə silinir.
"""

from __future__ import annotations

import time

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import pgettext

from ..constants import (
    DEFER_SECONDS,
    SESSION_SURVEY_DEFER_KEY,
    SESSION_SURVEY_SKIP_KEY,
    GatePolicy,
    SurveyKind,
    SurveyStatus,
)
from ..models import (
    Survey,
    SurveyDraft,
    SurveyGateSkip,
    SurveyParticipation,
    SurveySubmission,
    SurveySubmissionAnswer,
)
from .answers import draft_values
from .audience import user_in_audience
from .survey_buffer import enqueue

_CTX = "surveys.respond"


class RespondError(ValidationError):
    """İstifadəçiyə göstərilə bilən xəta."""


class AlreadyAnswered(RespondError):
    pass


def survey_for(organization, survey_id):
    """Təşkilatın ümumi sorğusu (müəllim dəsti deyil) və ya ``None``."""
    return (
        Survey.objects.filter(organization=organization, pk=survey_id)
        .exclude(kind=SurveyKind.TEACHER_EVALUATION)
        .exclude(status=SurveyStatus.DRAFT)
        .select_related("template")
        .first()
    )


def has_participated(survey, user) -> bool:
    return SurveyParticipation.objects.filter(survey=survey, user=user).exists()


def submit(survey, user, cleaned) -> None:
    today = timezone.localdate()
    if not survey.is_active_on(today):
        raise RespondError(pgettext(_CTX, "Sorğu artıq qəbul edilmir."))
    with transaction.atomic():
        try:
            with transaction.atomic():
                SurveyParticipation.objects.create(
                    organization_id=survey.organization_id, survey=survey, user=user, completed_on=today
                )
        except IntegrityError as exc:
            raise AlreadyAnswered(pgettext(_CTX, "Bu sorğunu artıq doldurmusunuz.")) from exc
        if survey.anonymous:
            enqueue(survey, cleaned)
        else:
            submission = SurveySubmission.objects.create(
                organization_id=survey.organization_id, survey=survey, respondent=user, submitted_at=timezone.now()
            )
            SurveySubmissionAnswer.objects.bulk_create(
                SurveySubmissionAnswer(
                    organization_id=survey.organization_id,
                    submission=submission,
                    question=question,
                    number=number,
                    choices=list(choices),
                    text=text,
                )
                for question, number, choices, text in cleaned
            )
        SurveyDraft.objects.filter(survey=survey, user=user).delete()


# ── Qaralama (yalnız şəxsli sorğu) ──────────────────────────────────────────


def save_draft(survey, user, data) -> None:
    if survey.anonymous:
        raise RespondError(pgettext(_CTX, "Anonim sorğunun qaralaması yalnız brauzerdə saxlanır."))
    SurveyDraft.objects.update_or_create(
        survey=survey, user=user, defaults={"organization_id": survey.organization_id, "data": draft_values(data)}
    )


def load_draft(survey, user) -> dict:
    if survey.anonymous:
        return {}
    row = SurveyDraft.objects.filter(survey=survey, user=user).values_list("data", flat=True).first()
    return row if isinstance(row, dict) else {}


# ── Qapı: «bir dəfə keç» və «sonra doldur» ──────────────────────────────────


def skip_active(request, survey_id) -> bool:
    raw = request.session.get(SESSION_SURVEY_SKIP_KEY) if hasattr(request, "session") else None
    until = (raw or {}).get(str(survey_id)) if isinstance(raw, dict) else None
    return bool(until and int(until) > int(time.time()))


def defer_active(request, survey_id) -> bool:
    raw = request.session.get(SESSION_SURVEY_DEFER_KEY) if hasattr(request, "session") else None
    until = (raw or {}).get(str(survey_id)) if isinstance(raw, dict) else None
    return bool(until and int(until) > int(time.time()))


def _mark(request, key, survey_id) -> None:
    raw = request.session.get(key)
    raw = dict(raw) if isinstance(raw, dict) else {}
    now = int(time.time())
    raw = {pk: until for pk, until in raw.items() if int(until or 0) > now}
    raw[str(survey_id)] = now + DEFER_SECONDS
    request.session[key] = raw


def skip_once(request, survey) -> None:
    """Məcburi ``skip_once`` sorğusunu BU SESSİYADA (≤ 24 saat) keçmək — ömürdə bir dəfə."""
    if not (survey.mandatory and survey.gate_policy == GatePolicy.SKIP_ONCE):
        raise RespondError(pgettext(_CTX, "Bu sorğunu keçmək mümkün deyil."))
    try:
        with transaction.atomic():
            SurveyGateSkip.objects.create(organization_id=survey.organization_id, survey=survey, user=request.user)
    except IntegrityError as exc:
        raise RespondError(
            pgettext(_CTX, "Bu sorğunu artıq bir dəfə keçmisiniz — kabinetə daxil olmaq üçün onu doldurun.")
        ) from exc
    _mark(request, SESSION_SURVEY_SKIP_KEY, survey.pk)


def defer(request, survey) -> None:
    """``defer_days`` möhləti daxilində 24 saatlıq «Sonra doldur»."""
    grace = survey.grace_until
    if not (survey.mandatory and survey.gate_policy == GatePolicy.DEFER_DAYS and grace):
        raise RespondError(pgettext(_CTX, "Bu sorğu üçün möhlət yoxdur."))
    if timezone.localdate() > grace:
        raise RespondError(pgettext(_CTX, "Möhlət müddəti bitib — sorğunu doldurmaq məcburidir."))
    _mark(request, SESSION_SURVEY_DEFER_KEY, survey.pk)


def has_skipped(survey, user) -> bool:
    return SurveyGateSkip.objects.filter(survey=survey, user=user).exists()


def can_take(survey, user, memberships, today=None) -> tuple[bool, str]:
    """``(ok, səbəb)`` — səbəblər: ``closed``, ``scheduled``, ``not_audience``, ``done``."""
    today = today or timezone.localdate()
    if not user_in_audience(survey, user, memberships):
        return False, "not_audience"
    if has_participated(survey, user):
        return False, "done"
    status = survey.effective_status(today)
    if status == "scheduled":
        return False, "scheduled"
    if not survey.is_active_on(today):
        return False, "closed"
    return True, ""
