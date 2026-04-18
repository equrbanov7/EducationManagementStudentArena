from urllib.parse import urlencode

from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import pgettext

from apps.exams.models import Exam, ExamAttempt
from apps.exams.services.randomizer import generate_random_questions_for_attempt
from apps.exams.services.utils import _attempt_has_any_answer, _effective_needed_count


def get_active_attempt_for_user(exam, user):
    for attempt in exam.attempts.filter(user=user, status__in=["draft", "in_progress"]).order_by("-started_at"):
        if attempt.expire_if_time_limit_reached():
            continue
        return attempt
    return None


def get_finished_attempts_for_user(exam, user):
    return exam.attempts.filter(user=user, status__in=["submitted", "expired"]).order_by("-started_at")


def can_user_start_new_attempt(exam, user):
    active_attempt = get_active_attempt_for_user(exam, user)
    if active_attempt:
        return False, "active_attempt_exists"

    max_attempts = exam.max_attempts_per_user
    if max_attempts and get_finished_attempts_for_user(exam, user).count() >= max_attempts:
        return False, "max_attempts_reached"

    return True, "ok"


@transaction.atomic
def create_exam_attempt(exam, user):
    last_attempt = exam.attempts.filter(user=user).order_by("-attempt_number").first()
    next_attempt_number = (last_attempt.attempt_number + 1) if last_attempt else 1
    return ExamAttempt.objects.create(
        user=user,
        exam=exam,
        attempt_number=next_attempt_number,
        status="in_progress",
    )


@transaction.atomic
def submit_exam_attempt(attempt):
    attempt.mark_finished(status="submitted")
    return attempt


def _safe_same_origin_redirect_path(request, candidate_url):
    raw_url = (candidate_url or "").strip()
    if not raw_url:
        return ""

    if not url_has_allowed_host_and_scheme(
        raw_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return ""
    return raw_url


def _append_return_to(url, return_to):
    if not return_to:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{urlencode({'return_to': return_to})}"


def _build_exam_result_url(exam, attempt, return_to):
    return _append_return_to(
        reverse("exams:exam_result", kwargs={"slug": exam.slug, "attempt_id": attempt.id}),
        return_to,
    )


def _start_or_resume_attempt(request, exam: Exam):
    """
    İstifadəçi üçün attempt yaradır və ya mövcud attempt-ə yönləndirir.
    """
    user = request.user
    return_to = _safe_same_origin_redirect_path(
        request,
        request.GET.get("return_to")
        or request.GET.get("next")
        or request.POST.get("return_to")
        or request.POST.get("next"),
    )

    current = get_active_attempt_for_user(exam, user)
    if current:
        desired = _effective_needed_count(exam)
        current_count = current.answers.count()

        if current_count != desired and not _attempt_has_any_answer(current):
            generate_random_questions_for_attempt(current, force_rebuild=True)

        return redirect(
            _append_return_to(
                reverse("exams:take_exam", kwargs={"slug": exam.slug, "attempt_id": current.id}), return_to
            )
        )

    finished_qs = get_finished_attempts_for_user(exam, user)
    finished_count = finished_qs.count()
    max_attempts = exam.max_attempts_per_user

    if max_attempts and finished_count >= max_attempts:
        last = finished_qs.first()
        if last:
            messages.info(
                request,
                pgettext("exams.service.attempt.message", "max_attempts_reached").format(max_attempts=max_attempts),
            )
            return redirect(_build_exam_result_url(exam, last, return_to))
        return redirect("exams:student_exam_list")

    last_attempt = exam.attempts.filter(user=user).order_by("-attempt_number").first()
    next_attempt_number = last_attempt.attempt_number + 1 if last_attempt else 1

    attempt = ExamAttempt.objects.create(
        user=user,
        exam=exam,
        attempt_number=next_attempt_number,
        status="in_progress",
    )

    generate_random_questions_for_attempt(attempt)

    messages.success(
        request,
        pgettext("exams.service.attempt.message", "exam_started").format(attempt_number=next_attempt_number),
    )
    return redirect(
        _append_return_to(reverse("exams:take_exam", kwargs={"slug": exam.slug, "attempt_id": attempt.id}), return_to)
    )
