"""Take-exam klientinin 409-dan sonrakı sinxronlaşması — serverdəki cari cavablar.

2026-10-21: OCC konflikti (``autosave_revision`` geridə) əvvəl tabı «səhifəni yeniləyin»
ilə donundururdu və sonrakı cavablar saxlanmırdı. İndi klient (``take_exam/resync.js``)
bu endpoint-dən serverin cari revision-unu və sualların cari cavablarını alır, öz son
təsdiqlənmiş dəyəri (base) ilə üç tərəfli müqayisə edir: başqa tabın toxunmadığı sualları
yenidən göndərir, başqa tabın dəyişdirdiyini götürür, hər iki tərəfin fərqli dəyişdirdiyi
sualda isə tab bloklanır (çox-tab qoruması qalır — kor-koranə üzərinə yazı yoxdur).

Dəyər formatı klientlə eynidir: test → seçilmiş variant tokenləri (``option_token``),
sıralanmış və vergüllə birləşmiş; yazılı → ``text_answer`` (server onsuz da ``strip`` edir).
Yalnız oxumadır; GET kilid götürmür.
"""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET

from apps.exams.models import ExamAttempt
from apps.exams.services.option_tokens import option_token
from apps.exams.views.shared.tenant import tenant_scoped_exams

from ._autosave_writer import current_writer_state
from ._final_device import final_device_guarded
from ._helpers import build_exam_result_url, ensure_student_exam_tenant_context
from .access_guard import ensure_active_attempt_access

#: Bir sorğuda ən çox sual (imtahanlar ~50–100 sualdır; sərhəd payload-u məhdudlaşdırır).
MAX_SYNC_QUESTIONS = 500


def _requested_question_ids(request):
    ids = []
    for raw in (request.GET.get("q") or "").split(","):
        raw = raw.strip()
        if raw.isdigit():
            ids.append(int(raw))
        if len(ids) >= MAX_SYNC_QUESTIONS:
            break
    return ids


def answer_state_value(attempt, answer, *, is_test):
    """Klientin ``resync.js → currentValue`` formatında kanonik dəyər."""
    question = answer.question
    if is_test and question.answer_mode in ("single", "multiple"):
        tokens = sorted(option_token(attempt.id, option.id) for option in answer.selected_options.all())
        return ",".join(tokens)
    return (answer.text_answer or "").strip()


@login_required
@require_GET
@final_device_guarded
def take_exam_answers_state(request, slug, attempt_id):
    ensure_student_exam_tenant_context(request)
    attempt = get_object_or_404(
        ExamAttempt.objects.select_related("exam", "exam__organization"),
        id=attempt_id,
        exam__in=tenant_scoped_exams(request),
        exam__slug=slug,
        user=request.user,
    )
    ensure_active_attempt_access(attempt, request.user, request=request)
    if attempt.is_finished:
        return JsonResponse({"success": True, "finished": True, "redirect_url": build_exam_result_url(attempt)})

    is_test = attempt.exam.exam_type == "test"
    answers = attempt.answers.select_related("question").order_by("id")
    if is_test:
        answers = answers.prefetch_related("selected_options")
    question_ids = _requested_question_ids(request)
    if question_ids:
        answers = answers.filter(question_id__in=question_ids)
    answers = answers[:MAX_SYNC_QUESTIONS]

    state = current_writer_state(attempt) or {}
    return JsonResponse(
        {
            "success": True,
            "finished": False,
            "server_revision": attempt.autosave_revision,
            "writer": state.get("writer") or "",
            "writer_since": state.get("since"),
            "answers": {
                str(answer.question_id): answer_state_value(attempt, answer, is_test=is_test) for answer in answers
            },
        }
    )


__all__ = ["MAX_SYNC_QUESTIONS", "answer_state_value", "take_exam_answers_state"]
