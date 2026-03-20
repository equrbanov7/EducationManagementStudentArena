from urllib.parse import urlencode

from django.urls import reverse

from core.helpers import ASSIGNED_TASK_FILTER_CHOICES, _safe_same_origin_redirect_path


def student_return_to(request):
    return _safe_same_origin_redirect_path(
        request,
        request.GET.get("return_to") or request.GET.get("next"),
    )


def append_return_to(url, return_to):
    if not return_to:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{urlencode({'return_to': return_to})}"


def build_student_task_back_url(request, *, course_id):
    dashboard_url = reverse("courses:course_dashboard", kwargs={"course_id": course_id})
    explicit_return_url = student_return_to(request)
    if explicit_return_url:
        return append_return_to(dashboard_url, explicit_return_url)

    source_section = (request.GET.get("from_section") or "").strip()
    if source_section == "assigned-exams":
        params = {"section": "assigned-exams"}
        assigned_type = (request.GET.get("assigned_type") or "").strip().lower()
        if assigned_type in ASSIGNED_TASK_FILTER_CHOICES:
            params["assigned_type"] = assigned_type
        return f"{reverse('accounts:profile')}?{urlencode(params)}"

    return dashboard_url


def build_teacher_review_back_url(request, *, course_id):
    explicit_return_url = _safe_same_origin_redirect_path(
        request,
        request.GET.get("return_to") or request.GET.get("next"),
    )
    if explicit_return_url:
        return explicit_return_url

    source_section = (request.GET.get("from_section") or "").strip()
    if source_section in {"pending-review", "review-results"}:
        return f"{reverse('accounts:profile')}?section={source_section}"

    return reverse("courses:course_dashboard", kwargs={"course_id": course_id})
