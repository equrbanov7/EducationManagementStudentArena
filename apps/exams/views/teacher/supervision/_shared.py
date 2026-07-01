"""teacher supervision view paketi — _shared."""

from datetime import datetime

from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.translation import pgettext

from apps.exams.features import exam_supervision_enabled, supervision_disabled_message
from apps.exams.models import Exam
from apps.exams.views.shared.tenant import get_active_organization, tenant_scoped_exams
from core.permissions import is_superadmin_user, request_has_permission
from core.tenancy import request_has_active_organization_context


def _ensure_organization_context(request):
    """Ensure request has active organization context. Returns organization."""
    org = get_active_organization(request)
    if org is None or not request_has_active_organization_context(request):
        raise PermissionDenied(pgettext("supervision.view.permission", "active_org_required"))
    return org


def _supervision_exam_queryset(request, organization):
    exams = tenant_scoped_exams(request, Exam.objects.filter(organization=organization))
    if is_superadmin_user(request.user) or request_has_permission(request, "exam.manage"):
        return exams
    return exams.filter(author=request.user)


def _ensure_supervision_feature_enabled():
    if not exam_supervision_enabled():
        raise PermissionDenied(supervision_disabled_message())


def _supervision_disabled_json(*, status=403):
    return JsonResponse(
        {
            "success": False,
            "supervised": False,
            "error": supervision_disabled_message(),
        },
        status=status,
    )


def _get_scoped_exam_or_404(request, org, exam_id):
    """
    Resolve an exam by id, strictly scoped to the org and the teacher's
    permission (author-only unless they hold ``exam.manage`` / are superadmin).
    Centralises the scope check so live-monitor views can never leak another
    organisation's or another teacher's exam.
    """
    return get_object_or_404(
        _supervision_exam_queryset(request, org).select_related("supervision_config"),
        id=exam_id,
    )


def _parse_date_param(request):
    """Parse ?date=YYYY-MM-DD (or ?today=1) into a date, or None for all sessions."""
    if request.GET.get("today") == "1":
        from django.utils import timezone

        return timezone.localdate()
    raw = (request.GET.get("date") or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None
