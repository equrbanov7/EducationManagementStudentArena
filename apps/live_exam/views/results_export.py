"""Bitmiş canlı sessiyanın CSV ixracı — müəllim üçün (Audit 2026-09-28 LX-SEC).

Hər sətir bir cavabdır: oyunçu, sual, seçilmiş variant(lar) və ya YAZILI cavab,
düzlük, bal, cavab müddəti. Ləqəb və yazılı cavab oyunçu girişidir:

* nəzarət / bidi / görünməz simvollar ``clean_typed_answer`` ilə atılır;
* ``= + - @`` və ``\\t \\r \\n`` ilə başlayan xanalar ``core.export_safety``
  yazıcısı ilə ``'`` prefiksi alır (CSV/formula injection — OWASP);
* giriş hüququ HTML nəticə səhifəsi ilə EYNİDİR (``_ensure_teacher_access``, LXS-01).
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.translation import pgettext
from django.views.decorators.http import require_GET

from apps.exams.models import Exam
from apps.live_exam.auth import clean_typed_answer
from apps.live_exam.models import LiveAnswer, LiveSession
from core.export_safety import safe_csv_writer

from .results import _ensure_teacher_access, _session_questions

# i18n skaneri kontekst sabitini modul daxilində axtarır — import yox, yerli təyin.
_CTX = "live_exam.results.export"


def _header() -> list[str]:
    return [
        pgettext(_CTX, "export_nickname"),
        pgettext(_CTX, "export_total_score"),
        pgettext(_CTX, "export_question_number"),
        pgettext(_CTX, "export_question"),
        pgettext(_CTX, "export_answer"),
        pgettext(_CTX, "export_correct"),
        pgettext(_CTX, "export_points"),
        pgettext(_CTX, "export_answer_ms"),
    ]


def _answer_text(answer, option_texts: dict[int, str]) -> str:
    typed = clean_typed_answer(getattr(answer, "text_answer", ""))
    if typed:
        return typed
    chosen = list(answer.choice_ids or []) or ([answer.choice_id] if answer.choice_id is not None else [])
    labels = []
    for raw_id in chosen:
        try:
            labels.append(option_texts.get(int(raw_id), ""))
        except (TypeError, ValueError):
            continue
    return " | ".join(label for label in labels if label)


@login_required
@require_GET
def teacher_live_session_export(request, slug, pin):
    exam = get_object_or_404(Exam.objects.select_related("organization"), slug=slug)
    _ensure_teacher_access(request, exam)
    session = get_object_or_404(LiveSession, exam=exam, pin=pin, state=LiveSession.STATE_FINISHED)

    questions = _session_questions(exam, session)
    positions = {question.id: index + 1 for index, question in enumerate(questions)}
    texts = {question.id: (question.text or "").strip() for question in questions}
    option_texts = {
        option.id: (option.text or "").strip() for question in questions for option in question.options.all()
    }

    answers = (
        LiveAnswer.objects.filter(session=session, question_id__in=list(positions))
        .select_related("player")
        .order_by("-player__score", "player__created_at", "player_id", "created_at", "id")
    )

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="live-{session.pin}.csv"'
    response.write("﻿")  # Excel UTF-8 BOM
    writer = safe_csv_writer(response)
    writer.writerow(_header())
    yes, no = pgettext(_CTX, "export_yes"), pgettext(_CTX, "export_no")
    for answer in answers:
        writer.writerow(
            [
                answer.player.nickname,
                int(answer.player.score or 0),
                positions.get(answer.question_id, ""),
                texts.get(answer.question_id, ""),
                _answer_text(answer, option_texts),
                yes if answer.is_correct else no,
                int(answer.awarded_points or 0),
                int(answer.answer_ms or 0),
            ]
        )
    return response
