from urllib.parse import urlencode

from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from core.helpers import REVIEW_EDIT_LOCK_WINDOW


def safe_same_origin_redirect_path(request, candidate_url):
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


def current_return_to(request):
    return safe_same_origin_redirect_path(
        request,
        request.GET.get("return_to") or request.GET.get("next") or request.POST.get("return_to") or request.POST.get("next"),
    )


def append_query_params(url, **params):
    clean_params = {key: value for key, value in params.items() if value not in (None, "", [])}
    if not clean_params:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{urlencode(clean_params)}"


def append_return_to(url, return_to):
    return append_query_params(url, return_to=return_to)


def build_exam_history_url(exam, return_to=""):
    return append_query_params(reverse("exams:student_exam_history"), exam=exam.slug, return_to=return_to)


def build_exam_result_url(attempt, return_to=""):
    return append_query_params(
        reverse("exams:exam_result", kwargs={"slug": attempt.exam.slug, "attempt_id": attempt.id}),
        return_to=return_to,
    )


def annotate_attempt_result_visibility(attempts, *, current_time=None):
    now = current_time or timezone.now()
    prepared_attempts = []

    for attempt in attempts:
        can_view_result = attempt.exam.exam_type == "test"
        review_available_in_seconds = 0

        if attempt.exam.exam_type != "test":
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
        prepared_attempts.append(attempt)

    return prepared_attempts
