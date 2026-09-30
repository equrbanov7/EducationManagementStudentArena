"""Anonim ümumi sorğunun cavab buferi və nəticə dərci — ``services/pending.py`` ilə EYNİ qayda.

* Göndəriş qəbzlə (``SurveyParticipation``) eyni tranzaksiyada yalnız şəxssiz BUFER sətri yazır.
* :func:`flush` AYRI tranzaksiyada işləyir: ≥ k cavab yığılanda hamısı birlikdə, təsadüfi sıra
  ilə ``SurveySubmission``-a köçürülür (fiziki sıra / ``xmin`` cavabı qəbzə deyil, ≥ k nəfərlik
  partiyaya bağlayır; Audit 2026-09-28 SV-3).
* İlk dərcdə (bağlanma / ``closes_on`` keçəndən sonra ilk baxış) bufer TAM köçürülür; k-dan az
  qalıq təsadüfi köhnə cavablarla bir partiyada yenidən yazılır. Dərcdən SONRA gələnlər
  (yenidən açılış) yalnız ≥ k yığılanda görünür (SV-2).

Anonim sorğunun cavabında snapshot YOXDUR (struktur bölgüsü yalnız iştirak üzrədir) — bütün
cavablar bir açardadır.
"""

from __future__ import annotations

import logging
import random

from django.db import transaction
from django.utils import timezone

from core.rls import bypass_rls

from ..constants import DEFAULT_MIN_GROUP_SIZE
from ..models import Survey, SurveyPendingSubmission, SurveyQuestion, SurveySubmission, SurveySubmissionAnswer

logger = logging.getLogger(__name__)
_RANDOM = random.SystemRandom()


def _k(survey) -> int:
    return max(int(survey.min_group_size or DEFAULT_MIN_GROUP_SIZE), DEFAULT_MIN_GROUP_SIZE)


def enqueue(survey, answers) -> None:
    """``answers`` — ``[(question, number, choices, text)]``; çağıranın tranzaksiyasında."""
    SurveyPendingSubmission.objects.create(
        organization_id=survey.organization_id,
        survey=survey,
        payload={"answers": [[str(q.pk), number, list(choices), text] for q, number, choices, text in answers]},
    )
    survey_id = survey.pk
    transaction.on_commit(lambda: flush_quietly(survey_id))


def flush_quietly(survey_id) -> None:
    try:
        flush(survey_id)
    except Exception:  # pragma: no cover — növbəti tetik (bağlanma / baxış) yenidən cəhd edir
        logger.exception("survey submission flush failed (survey=%s)", survey_id)


def _write(survey, items) -> int:
    items = list(items)
    _RANDOM.shuffle(items)
    # Təhlükəsizlik baxışı 2026-09-30 (L8): cavab buferə düşəndən sonra sual silinibsə
    # (redaktə ilə anonim göndərişin yarışı) FK xətası hər sonrakı flush-u və sorğunun
    # bağlanmasını əbədi sındırardı — mövcud olmayan sualın cavabı atılır.
    known = {
        str(pk) for pk in SurveyQuestion.objects.filter(template_id=survey.template_id).values_list("pk", flat=True)
    }
    submissions, answers = [], []
    for rows in items:
        submission = SurveySubmission(organization_id=survey.organization_id, survey_id=survey.pk)
        submissions.append(submission)
        answers.extend(
            SurveySubmissionAnswer(
                organization_id=survey.organization_id,
                submission=submission,
                question_id=question_id,
                number=number,
                choices=choices or [],
                text=text or "",
            )
            for question_id, number, choices, text in rows
            if str(question_id) in known
        )
    SurveySubmission.objects.bulk_create(submissions)
    SurveySubmissionAnswer.objects.bulk_create(answers)
    return len(submissions)


def _existing(survey, limit) -> tuple[list, list]:
    ids = list(
        SurveySubmission.objects.filter(survey_id=survey.pk, respondent__isnull=True)
        .order_by("?")
        .values_list("pk", flat=True)[:limit]
    )
    rows: dict = {pk: [] for pk in ids}
    for submission_id, question_id, number, choices, text in SurveySubmissionAnswer.objects.filter(
        submission_id__in=ids
    ).values_list("submission_id", "question_id", "number", "choices", "text"):
        rows[submission_id].append([question_id, number, choices, text])
    return list(rows.values()), ids


def flush(survey_id, *, final=False) -> int:
    with transaction.atomic(), bypass_rls():
        survey = Survey.objects.select_for_update(skip_locked=not final).filter(pk=survey_id).first()
        if survey is None or not survey.anonymous:
            return 0
        first = final and survey.results_published_at is None
        k = _k(survey)
        pending = list(SurveyPendingSubmission.objects.filter(survey_id=survey_id).order_by("pk"))
        count = 0
        if pending and (len(pending) >= k or first):
            items = [row.payload.get("answers") or [] for row in pending]
            moved = []
            if len(pending) < k:
                extra, moved = _existing(survey, k - len(pending))
                items.extend(extra)
            SurveySubmission.objects.filter(pk__in=moved).delete()
            count = _write(survey, items)
            SurveyPendingSubmission.objects.filter(pk__in=[row.pk for row in pending]).delete()
        if first:
            survey.results_published_at = timezone.now()
            survey.save(update_fields=["results_published_at"])
    return count


def publish_results(survey_id) -> int:
    return flush(survey_id, final=True)


def publish_if_due(survey, today=None) -> None:
    """Nəticə görünüşündən: anonim, effektiv bağlı, hələ dərc olunmamış sorğunu dərc edir."""
    today = today or timezone.localdate()
    if survey.anonymous and survey.results_published_at is None and survey.effective_status(today) == "closed":
        publish_results(survey.pk)
        survey.refresh_from_db(fields=["results_published_at"])
