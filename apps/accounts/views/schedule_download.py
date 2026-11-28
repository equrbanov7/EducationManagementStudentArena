"""Şəxsi dərs cədvəli və cədvəl idarəetməsi üçün tenant-əhatəli XLSX cavabları."""

from uuid import UUID

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404
from django.utils.http import content_disposition_header
from django.utils.text import get_valid_filename
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from apps.organizations.models import AcademicPeriod
from apps.registrar.public import schedule, schedule_exports
from core.audit import log_action
from core.constants import AuditAction

from ._helpers import _load_user_profile, _role_capabilities
from ._helpers.tenant import _get_active_organization

FILTERS = ("faculty", "chair", "group", "teacher")


@never_cache
@login_required
@require_GET
def download(request, *, personal):
    org = _get_active_organization(request)
    if not org or getattr(request, "is_view_as", False):
        raise PermissionDenied
    profile, _ = _load_user_profile(request.user)
    caps = _role_capabilities(request.user, profile)
    section = "my-schedule" if personal else "schedule-manage"
    if section not in caps["allowed_sections"]:
        raise PermissionDenied
    filters = {key: request.GET[key] for key in FILTERS if request.GET.get(key)}
    if personal and (filters or caps["is_student"] or schedule_exports.has_student_schedule(org, request.user)):
        raise PermissionDenied
    try:
        period_id = UUID(request.GET.get("period", ""))
    except (ValueError, TypeError):
        raise Http404 from None
    period = get_object_or_404(AcademicPeriod, pk=period_id, organization=org)
    try:
        offset = int(request.GET.get("w") or 0)
    except ValueError:
        return HttpResponseBadRequest("Həftə düzgün seçilməyib.")
    if offset < -8 or offset > 16:
        return HttpResponseBadRequest("Həftə seçim həddindən kənardadır.")
    week = schedule.build_week_context(period, offset=offset, weekdays=schedule.WEEKDAYS)
    if personal:
        teacher_name = request.user.get_full_name() or request.user.username
        slots = schedule.get_teacher_schedule(organization=org, teacher=request.user, period=period)
        if not schedule_exports.has_personal_teaching(request.user, slots):
            raise PermissionDenied
        labels = [teacher_name]
    else:
        slots, labels, teacher_name = schedule_exports.management_slots(request.user, org, period, filters)
    payload = schedule_exports.workbook_bytes(org, period, week, slots, labels, teacher_name)
    log_action(
        AuditAction.EXPORT,
        user=request.user,
        organization=org,
        request=request,
        resource_type="registrar.schedule",
        resource_repr=f"XLSX · {period.name}",
        new_values={
            "section": section,
            "period": str(period.pk),
            "week": week["monday"].isoformat(),
            "filters": filters,
            "rows": len(slots),
        },
    )
    response = HttpResponse(payload, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    label = get_valid_filename("Dərs cədvəli " + (" ".join(labels) or "Bütün dərslər"))[:106]
    response["Content-Disposition"] = content_disposition_header(True, f"{label}_{week['monday']}.xlsx")
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response
