"""
Labs Views - Helper Functions
Ortaq helper funksiyalar
"""

from urllib.parse import urlencode

from django.shortcuts import get_object_or_404
from django.urls import reverse

from apps.courses.models import Course
from core.helpers import ASSIGNED_TASK_FILTER_CHOICES, _safe_same_origin_redirect_path
from core.tenancy import scoped_by_organization_id
from core.upload_security import randomize_uploaded_filename, validate_uploaded_file

from ..models import Lab, LabBlock, LabQuestion, LabSubmission

DEFAULT_LAB_ALLOWED_EXTENSIONS = {
    ".zip",
    ".pdf",
    ".doc",
    ".docx",
    ".txt",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".py",
    ".java",
    ".cpp",
    ".c",
    ".rar",
    ".7z",
}


def _normalize_extensions(raw_extensions):
    extensions = {f".{ext.strip().lstrip('.').lower()}" for ext in (raw_extensions or "").split(",") if ext.strip()}
    return extensions or set(DEFAULT_LAB_ALLOWED_EXTENSIONS)


def _parse_max_size_mb(raw_value, *, fallback=25):
    try:
        parsed = int(raw_value)
    except (TypeError, ValueError):
        parsed = fallback
    return max(1, parsed)


def _validate_and_prepare_lab_upload(uploaded_file, *, allowed_extensions, max_size_mb):
    validate_uploaded_file(
        uploaded_file,
        allowed_extensions=allowed_extensions,
        max_size_mb=max_size_mb,
    )
    randomize_uploaded_filename(uploaded_file)
    return uploaded_file


def _tenant_scoped_courses(request, queryset=None):
    base_queryset = queryset if queryset is not None else Course.objects.all()
    return scoped_by_organization_id(
        base_queryset,
        request,
        org_id_field="organization_id",
        fallback_org_field="owner__profile__organization",
    )


def _tenant_scoped_labs(request, queryset=None):
    base_queryset = queryset if queryset is not None else Lab.objects.all()
    return base_queryset.filter(course__in=_tenant_scoped_courses(request))


def _tenant_scoped_blocks(request, queryset=None):
    base_queryset = queryset if queryset is not None else LabBlock.objects.all()
    return base_queryset.filter(lab__in=_tenant_scoped_labs(request))


def _tenant_scoped_questions(request, queryset=None):
    base_queryset = queryset if queryset is not None else LabQuestion.objects.all()
    return base_queryset.filter(block__in=_tenant_scoped_blocks(request))


def _tenant_scoped_submissions(request, queryset=None):
    base_queryset = queryset if queryset is not None else LabSubmission.objects.all()
    return base_queryset.filter(assignment__lab__in=_tenant_scoped_labs(request))


def _get_tenant_course_or_404(request, course_id):
    return get_object_or_404(_tenant_scoped_courses(request), id=course_id)


def _get_tenant_lab_or_404(request, lab_id):
    return get_object_or_404(_tenant_scoped_labs(request), id=lab_id)


def _get_tenant_block_or_404(request, block_id):
    return get_object_or_404(_tenant_scoped_blocks(request), id=block_id)


def _get_tenant_question_or_404(request, question_id):
    return get_object_or_404(_tenant_scoped_questions(request), id=question_id)


def _get_tenant_submission_or_404(request, submission_id):
    return get_object_or_404(_tenant_scoped_submissions(request), id=submission_id)


def _lab_back_url(request, lab):
    dashboard_url = reverse("courses:course_dashboard", kwargs={"course_id": lab.course.id})
    explicit_return_url = _safe_same_origin_redirect_path(
        request,
        request.GET.get("return_to") or request.GET.get("next"),
    )
    if explicit_return_url:
        return f"{dashboard_url}?{urlencode({'return_to': explicit_return_url})}"

    source_section = (request.GET.get("from_section") or "").strip()
    if source_section == "assigned-exams":
        params = {"section": "assigned-exams"}
        assigned_type = (request.GET.get("assigned_type") or "").strip().lower()
        if assigned_type in ASSIGNED_TASK_FILTER_CHOICES:
            params["assigned_type"] = assigned_type
        return f"{reverse('accounts:profile')}?{urlencode(params)}"

    return dashboard_url


def _lab_return_to(request):
    return _safe_same_origin_redirect_path(
        request,
        request.GET.get("return_to") or request.GET.get("next"),
    )


def _append_return_to(url, return_to):
    if not return_to:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{urlencode({'return_to': return_to})}"
