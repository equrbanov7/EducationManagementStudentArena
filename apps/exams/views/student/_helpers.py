from django.utils import timezone

# Faza 5 (audit 2026-07-02): URL/redirect köməkçiləri apps/exams/navigation-a
# köçürüldü (servis qatı ilə ortaq istifadə). Aşağıdakı re-exportlar mövcud
# `from ._helpers import ...` çağırışlarının import səthini qoruyur.
from apps.exams.navigation import (  # noqa: F401
    append_query_params,
    append_return_to,
    build_exam_history_url,
    build_exam_result_url,
    current_return_to,
    safe_same_origin_redirect_path,
)
from core.helpers import REVIEW_EDIT_LOCK_WINDOW
from core.tenancy import request_has_active_organization_context, restore_request_organization_from_profile


def ensure_student_exam_tenant_context(request):
    if request_has_active_organization_context(request):
        return True
    return restore_request_organization_from_profile(request, profile=getattr(request.user, "profile", None))


def are_exam_results_hidden_from_student(exam):
    return bool(getattr(exam, "results_hidden_from_students", False))


def annotate_attempt_result_visibility(attempts, *, current_time=None):
    now = current_time or timezone.now()
    prepared_attempts = []

    for attempt in attempts:
        result_hidden_by_teacher = are_exam_results_hidden_from_student(attempt.exam)
        can_view_result = not result_hidden_by_teacher and attempt.exam.exam_type in {"test", "coding"}
        review_available_in_seconds = 0

        if result_hidden_by_teacher:
            can_view_result = False
        elif attempt.exam.exam_type not in {"test", "coding"}:
            if attempt.checked_by_teacher:
                if attempt.teacher_checked_at:
                    reveal_at = attempt.teacher_checked_at + REVIEW_EDIT_LOCK_WINDOW
                    can_view_result = now >= reveal_at
                    if not can_view_result:
                        review_available_in_seconds = max(0, int((reveal_at - now).total_seconds()))
                else:
                    can_view_result = True
            else:
                can_view_result = True

        attempt.can_view_result = can_view_result
        attempt.review_available_in_seconds = review_available_in_seconds
        attempt.result_hidden_by_teacher = result_hidden_by_teacher
        prepared_attempts.append(attempt)

    return prepared_attempts


def posted_autosave_question_ids(request, *, action):
    """Autosave POST-undakı dəyişmiş sual id-ləri (yoxdursa None = full save)."""
    if action != "autosave":
        return None
    raw_ids = request.POST.getlist("changed_questions[]") or request.POST.getlist("changed_questions")
    parsed_ids = set()
    for raw_id in raw_ids:
        try:
            parsed_ids.add(int(raw_id))
        except (TypeError, ValueError):
            continue
    return parsed_ids


def finish_skips_absent_question(request, question_id, *, form_has_presence_markers):
    """EXAM-P1-05: finish zamanı timer-expired (q_present markeri absent) sualı
    ötür ki, boş POST saxlanmış cavabı silməsin. Markersiz (köhnə/keşlənmiş)
    formada köhnə davranış qalır (geriyə-uyğun)."""
    return form_has_presence_markers and request.POST.get(f"q_present_{question_id}") != "1"


def autosave_occ_conflict_response(request, attempt, action):
    """EXAM-P1-06: autosave optimistic concurrency yoxlaması.

    Client öz bildiyi ``autosave_revision``-u göndərir. Server daha yenidirsə
    (başqa tab yazıb) stale yazını rədd edən 409 JsonResponse qaytarır; əks
    halda (uyğun və ya base yoxdur) None. base_revision yoxdursa geriyə-uyğun.
    """
    from django.http import JsonResponse
    from django.utils.translation import pgettext

    from apps.exams.metrics import record_autosave

    base_raw = (request.POST.get("autosave_revision") or "").strip()
    if not base_raw:
        return None
    try:
        base_revision = int(base_raw)
    except (TypeError, ValueError):
        return None
    if base_revision == attempt.autosave_revision:
        return None
    if action == "autosave":
        record_autosave("conflict")
    return JsonResponse(
        {
            "success": False,
            "conflict": True,
            "server_revision": attempt.autosave_revision,
            "message": pgettext(
                "exams.view.access.message",
                "Bu imtahan başqa bir tab/pəncərədə yenilənib. Ən son cavabları görmək üçün səhifəni yeniləyin.",
            ),
        },
        status=409,
    )


def bump_autosave_revision(attempt):
    """Uğurlu yazıdan sonra attempt-in autosave revision-unu atomik artır."""
    from django.db.models import F

    type(attempt).objects.filter(pk=attempt.pk).update(autosave_revision=F("autosave_revision") + 1)
    attempt.refresh_from_db(fields=["autosave_revision"])


def selected_option_ids_from_request(request, question):
    """POST-dan bir sual üçün seçilmiş option id-lərini (single/multi) parse et."""
    if question.answer_mode == "single":
        raw_option_id = request.POST.get(f"q_{question.id}")
        if not raw_option_id:
            return set()
        try:
            return {int(raw_option_id)}
        except (TypeError, ValueError):
            return set()

    selected_option_ids = set()
    for raw_option_id in request.POST.getlist(f"q_{question.id}"):
        try:
            selected_option_ids.add(int(raw_option_id))
        except (TypeError, ValueError):
            continue
    return selected_option_ids
