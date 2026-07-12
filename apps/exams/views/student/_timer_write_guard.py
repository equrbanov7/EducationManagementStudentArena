"""Vaxtlı sual yazıları üçün HTTP-səviyyəli strict-protokol qapısı."""

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils.translation import pgettext

from apps.exams.services.question_timer import question_timer_start_required


def _request_has_answer_payload(request, question, *, exam_type, action):
    """Boş/unvisited finish sahəsini real cavab yazısından fərqləndir."""
    if action == "autosave":
        return True
    if exam_type == "test" and question.answer_mode in {"single", "multiple"}:
        return bool(request.POST.getlist(f"q_{question.id}"))
    return bool(
        (request.POST.get(f"q_{question.id}") or "").strip()
        or request.FILES.getlist(f"file_{question.id}[]")
        or (request.POST.get(f"paint_data_{question.id}") or "").strip()
    )


def reject_unstarted_timed_write(request, attempt, question, *, exam_type, action, is_ajax):
    """Strict attempt-də `question-seen` olmadan cavab yazısını rədd et."""
    if not _request_has_answer_payload(request, question, exam_type=exam_type, action=action):
        return None
    if not question_timer_start_required(attempt, question):
        return None

    message = pgettext(
        "exams.view.access.message",
        "Sual taymeri serverlə sinxronlaşmayıb. Cavabınız lokal saxlanılıb; səhifəni yeniləyin.",
    )
    if is_ajax:
        return JsonResponse(
            {
                "success": False,
                "conflict": False,
                "error": "question_timer_not_started",
                "question_id": question.id,
                "message": message,
            },
            status=409,
        )
    messages.error(request, message)
    return redirect(request.get_full_path())


__all__ = ["reject_unstarted_timed_write"]
