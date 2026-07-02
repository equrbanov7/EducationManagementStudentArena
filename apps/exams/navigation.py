"""Ortaq URL / redirect köməkçiləri (Faza 5, audit 2026-07-02).

Bu modul view və servis qatlarının HƏR İKİSİ tərəfindən istifadə olunur —
əvvəllər eyni məntiq `views/student/_helpers.py` və `services/attempts.py`
içində iki nüsxə idi. Neytral yerləşmə servis→view import istiqamətinin
qarşısını alır. `_helpers` geriyə-uyğunluq üçün bu adları re-export edir.
"""

from urllib.parse import urlencode

from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme


def safe_same_origin_redirect_path(request, candidate_url):
    """Yalnız eyni-origin nisbi yönləndirmə yollarını qəbul et (open-redirect qoruması)."""
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
        request.GET.get("return_to")
        or request.GET.get("next")
        or request.POST.get("return_to")
        or request.POST.get("next"),
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
