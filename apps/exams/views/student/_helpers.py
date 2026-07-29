from django.urls import reverse
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


def resolve_exam_failure_redirect(request):
    """İmtahan başlamayanda tələbəni gəldiyi siyahıya qaytarır."""
    explicit_next = safe_same_origin_redirect_path(request, request.GET.get("next") or request.POST.get("next"))
    if explicit_next:
        return explicit_next

    source_section = (request.GET.get("from_section") or request.POST.get("from_section") or "").strip()
    if source_section == "assigned-exams":
        assigned_type = (request.GET.get("assigned_type") or request.POST.get("assigned_type") or "all").strip().lower()
        allowed_types = {"all", "exams", "courses", "assignments", "labs", "independent"}
        if assigned_type not in allowed_types:
            assigned_type = "all"
        return f"{reverse('accounts:profile')}?section=assigned-exams&assigned_type={assigned_type}"

    return reverse("exams:student_exam_list")


def resolve_author_failure_redirect(request, exam):
    """İmtahanın müəllifini öz idarəetmə səhifəsinə, tələbəni siyahıya qaytarır."""
    if exam.author_id == request.user.id:
        return reverse("exams:teacher_exam_detail", kwargs={"slug": exam.slug})
    return resolve_exam_failure_redirect(request)


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
    message = pgettext(
        "exams.view.access.message",
        "Bu imtahan başqa bir tab/pəncərədə yenilənib. Ən son cavabları görmək üçün səhifəni yeniləyin.",
    )
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        from django.contrib import messages
        from django.shortcuts import redirect

        messages.error(request, message)
        return redirect(request.get_full_path())
    return JsonResponse(
        {
            "success": False,
            "conflict": True,
            "server_revision": attempt.autosave_revision,
            "message": message,
        },
        status=409,
    )


def bump_autosave_revision(attempt):
    """Uğurlu yazıdan sonra attempt-in autosave revision-unu atomik artır."""
    from django.db.models import F

    type(attempt).objects.filter(pk=attempt.pk).update(autosave_revision=F("autosave_revision") + 1)
    attempt.refresh_from_db(fields=["autosave_revision"])


def build_take_exam_question_payload(exam, attempt, questions):
    """take_exam slide payload-u: hər sual üçün {q, opts, server_delivery}.

    EXAM-P1-04 strict delivery: yeni-protokol attempt-də vaxtlı test sualının
    məzmunu (mətn/variant/media/düzgün cavab) İLK GET-də səhifə mənbəyinə düşmür
    — ``server_delivery`` işarələnir, variantlar boş buraxılır və məzmun timer
    serverdə başlayandan sonra ``question-seen`` ilə gəlir.
    """
    from apps.exams.services.question_timer import question_timer_start_required
    from apps.exams.services.randomizer import build_shuffled_options

    payload = []
    for question in questions:
        opts = []
        strict_delivery = exam.exam_type == "test" and question_timer_start_required(attempt, question)
        if not strict_delivery and exam.exam_type == "test" and question.answer_mode in ("single", "multiple"):
            opts = build_shuffled_options(attempt.id, question)
        payload.append({"q": question, "opts": opts, "server_delivery": strict_delivery})
    return payload


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
