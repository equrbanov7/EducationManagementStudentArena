"""
Supervision views for both teacher monitoring and student event logging.
"""

import json

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils.translation import pgettext
from django.views.decorators.http import require_GET, require_POST

from apps.exams.models import ExamAttempt, ExamSupervisionConfig, SupervisionIncident
from apps.exams.services.access_policy import _ensure_teacher
from apps.exams.services.supervision import (
    get_attempt_supervision_status,
    get_supervision_monitor_data,
    log_supervision_incident,
    teacher_resume_attempt,
    teacher_stop_attempt,
)
from apps.exams.views.shared.tenant import get_active_organization
from core.tenancy import request_has_active_organization_context


def _ensure_organization_context(request):
    """Ensure request has active organization context. Returns organization."""
    org = get_active_organization(request)
    if org is None or not request_has_active_organization_context(request):
        raise PermissionDenied(pgettext("supervision.view.permission", "active_org_required"))
    return org


# ─────────────────────────────────────────────
# Student-facing API endpoints
# ─────────────────────────────────────────────


@login_required
@require_POST
def log_incident_api(request, attempt_id):
    """
    Student-side endpoint to log a supervision incident.
    Called by the client-side supervision JavaScript.
    """
    attempt = get_object_or_404(
        ExamAttempt,
        id=attempt_id,
        user=request.user,
    )

    if attempt.is_finished:
        return JsonResponse({"error": "Attempt is already finished."}, status=400)

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON body."}, status=400)

    event_type = body.get("event_type", "")
    metadata = body.get("metadata", {})

    # Validate event type
    valid_types = {c[0] for c in SupervisionIncident.EVENT_TYPE_CHOICES}
    if event_type not in valid_types:
        return JsonResponse({"error": "Invalid event type."}, status=400)

    # Ensure metadata is dict and limit size
    if not isinstance(metadata, dict):
        metadata = {}

    result = log_supervision_incident(attempt, event_type, metadata)

    if result is None:
        return JsonResponse({"supervised": False})

    return JsonResponse(
        {
            "supervised": True,
            "violation_count": result["violation_count"],
            "max_violations": result["max_violations"],
            "limit_exceeded": result["limit_exceeded"],
            "action_taken": result["action_taken"],
            "supervision_status": result["supervision_status"],
        }
    )


@login_required
@require_GET
def supervision_status_api(request, attempt_id):
    """
    Get current supervision status for an attempt.
    Used by student to check if they can continue.
    """
    attempt = get_object_or_404(
        ExamAttempt,
        id=attempt_id,
        user=request.user,
    )

    status = get_attempt_supervision_status(attempt)
    status["is_finished"] = attempt.is_finished
    status["attempt_status"] = attempt.status
    return JsonResponse(status)


# ─────────────────────────────────────────────
# Teacher-facing views
# ─────────────────────────────────────────────


@login_required
def supervision_monitor(request):
    """
    Teacher supervision monitor dashboard.
    Shows all flagged students and incident logs.
    """
    org = _ensure_organization_context(request)
    _ensure_teacher(request.user)

    exam_id = request.GET.get("exam")
    search_query = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "").strip()
    severity_filter = request.GET.get("severity", "").strip()

    data = get_supervision_monitor_data(org, exam_id=exam_id)

    flagged = data["flagged_attempts"]

    # Apply search filter
    if search_query:
        flagged = (
            flagged.filter(user__username__icontains=search_query)
            | flagged.filter(user__first_name__icontains=search_query)
            | flagged.filter(user__last_name__icontains=search_query)
            | flagged.filter(exam__title__icontains=search_query)
        )
        flagged = flagged.distinct()

    # Apply status filter
    if status_filter:
        flagged = flagged.filter(supervision_status=status_filter)

    # Pagination
    page_number = request.GET.get("page", 1)
    paginator = Paginator(flagged, 20)
    page_obj = paginator.get_page(page_number)

    # Severity distribution for charts (single aggregation query)
    severity_agg = dict(
        data["incidents_qs"].values("severity").annotate(count=Count("id")).values_list("severity", "count")
    )
    severity_counts = {sev: severity_agg.get(sev, 0) for sev in ["info", "low", "medium", "high", "critical"]}

    # Violation type distribution (single aggregation query)
    violation_type_counts = dict(
        data["incidents_qs"].values("event_type").annotate(count=Count("id")).values_list("event_type", "count")
    )

    context = {
        "page_obj": page_obj,
        "supervised_exams": data["supervised_exams"],
        "total_incidents": data["total_incidents"],
        "severity_counts": severity_counts,
        "violation_type_counts": violation_type_counts,
        "search_query": search_query,
        "status_filter": status_filter,
        "severity_filter": severity_filter,
        "selected_exam_id": exam_id,
    }

    return render(request, "exams/teacher/supervision_monitor.html", context)


@login_required
def supervision_detail(request, attempt_id):
    """
    Detailed incident timeline for a specific student attempt.
    """
    org = _ensure_organization_context(request)
    _ensure_teacher(request.user)

    attempt = get_object_or_404(
        ExamAttempt.objects.select_related("user", "exam"),
        id=attempt_id,
        exam__organization=org,
    )

    incidents_qs = SupervisionIncident.objects.filter(attempt=attempt).order_by("-timestamp")

    # Pagination for incidents
    page_number = request.GET.get("page", 1)
    paginator = Paginator(incidents_qs, 20)
    incidents_page = paginator.get_page(page_number)

    config = None
    try:
        config = attempt.exam.supervision_config
    except ExamSupervisionConfig.DoesNotExist:
        pass

    context = {
        "attempt": attempt,
        "incidents": incidents_page,
        "incidents_page": incidents_page,
        "config": config,
        "student": attempt.user,
        "exam": attempt.exam,
    }

    return render(request, "exams/teacher/supervision_detail.html", context)


@login_required
@require_POST
def teacher_resume_api(request, attempt_id):
    """
    Teacher action to resume a locked/removed student attempt.
    """
    org = _ensure_organization_context(request)
    _ensure_teacher(request.user)

    attempt = get_object_or_404(
        ExamAttempt.objects.select_related("exam"),
        id=attempt_id,
        exam__organization=org,
    )

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        body = {}

    grant_extra_chance = body.get("grant_extra_chance", False)

    try:
        teacher_resume_attempt(attempt, request.user, grant_extra_chance=grant_extra_chance)
    except ValueError:
        return JsonResponse(
            {"error": pgettext("supervision.view.api", "operation_not_allowed")},
            status=400,
        )

    # Audit log
    from apps.audit.utils import log_action
    from core.constants import AuditAction

    log_action(
        action=AuditAction.UPDATE,
        user=request.user,
        organization=org,
        obj=attempt,
        new_values={
            "supervision_status": attempt.supervision_status,
            "grant_extra_chance": str(grant_extra_chance),
        },
        reason="teacher_resumed_supervision",
        request=request,
    )

    return JsonResponse(
        {
            "success": True,
            "supervision_status": attempt.supervision_status,
            "violation_count": attempt.supervision_violation_count,
        }
    )


@login_required
@require_POST
def teacher_stop_api(request, attempt_id):
    """
    Teacher action to force-stop a supervised student attempt.
    Submits the exam immediately and marks the student as removed.
    """
    org = _ensure_organization_context(request)
    _ensure_teacher(request.user)

    attempt = get_object_or_404(
        ExamAttempt.objects.select_related("exam"),
        id=attempt_id,
        exam__organization=org,
    )

    try:
        teacher_stop_attempt(attempt, request.user)
    except ValueError:
        return JsonResponse(
            {"error": pgettext("supervision.view.api", "operation_not_allowed")},
            status=400,
        )

    # Audit log
    from apps.audit.utils import log_action
    from core.constants import AuditAction

    log_action(
        action=AuditAction.UPDATE,
        user=request.user,
        organization=org,
        obj=attempt,
        new_values={
            "supervision_status": attempt.supervision_status,
            "status": attempt.status,
        },
        reason="teacher_force_stopped_supervision",
        request=request,
    )

    return JsonResponse(
        {
            "success": True,
            "supervision_status": attempt.supervision_status,
        }
    )
