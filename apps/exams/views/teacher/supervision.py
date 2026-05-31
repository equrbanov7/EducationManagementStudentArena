"""
Supervision views for both teacher monitoring and student event logging.
"""

import json
from collections import defaultdict
from datetime import datetime
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils.translation import pgettext
from django.views.decorators.http import require_GET, require_POST

from apps.exams.models import Exam, ExamAttempt, ExamSupervisionConfig, SupervisionIncident
from apps.exams.services.access_policy import _ensure_teacher
from apps.exams.services.supervision import (
    get_attempt_live_snapshot,
    get_attempt_supervision_status,
    get_exam_live_monitor_data,
    get_exam_session_dates,
    get_supervision_monitor_data,
    log_supervision_incident,
    teacher_lock_attempt,
    teacher_resume_attempt,
    teacher_stop_attempt,
)
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

    is_manual_lock = bool(attempt.supervision_manual_lock and attempt.supervision_status == "locked")
    if not is_manual_lock:
        attempt.expire_if_time_limit_reached()
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
            "manual_lock": bool(attempt.supervision_manual_lock and attempt.supervision_status == "locked"),
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

    is_manual_lock = bool(attempt.supervision_manual_lock and attempt.supervision_status == "locked")
    if not is_manual_lock:
        attempt.expire_if_time_limit_reached()
    attempt.expire_if_resume_window_expired()
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
    date_from_str = request.GET.get("date_from", "").strip()
    date_to_str = request.GET.get("date_to", "").strip()

    accessible_exams = _supervision_exam_queryset(request, org)
    data = get_supervision_monitor_data(org, exam_id=exam_id, exam_queryset=accessible_exams)

    attempts = data["monitor_attempts"]
    monitor_exams = data["monitor_exams"]

    # Apply search filter
    if search_query:
        attempts = attempts.filter(
            Q(user__username__icontains=search_query)
            | Q(user__first_name__icontains=search_query)
            | Q(user__last_name__icontains=search_query)
            | Q(exam__title__icontains=search_query)
        ).distinct()
        matching_exam_ids = attempts.values_list("exam_id", flat=True).distinct()
        monitor_exams = monitor_exams.filter(Q(title__icontains=search_query) | Q(id__in=matching_exam_ids)).distinct()

    # Apply status filter
    if status_filter:
        attempts = attempts.filter(supervision_status=status_filter)
        monitor_exams = monitor_exams.filter(id__in=attempts.values_list("exam_id", flat=True).distinct())

    # Apply date range filters
    date_from_value = date_from_str
    date_to_value = date_to_str
    if date_from_str:
        try:
            dt_from = datetime.strptime(date_from_str, "%Y-%m-%d")
            attempts = attempts.filter(started_at__date__gte=dt_from.date())
            monitor_exams = monitor_exams.filter(id__in=attempts.values_list("exam_id", flat=True).distinct())
        except ValueError:
            date_from_value = ""
    if date_to_str:
        try:
            dt_to = datetime.strptime(date_to_str, "%Y-%m-%d")
            attempts = attempts.filter(started_at__date__lte=dt_to.date())
            monitor_exams = monitor_exams.filter(id__in=attempts.values_list("exam_id", flat=True).distinct())
        except ValueError:
            date_to_value = ""

    # Sorting
    sort_by = (request.GET.get("sort_by") or "").strip()
    sort_dir = (request.GET.get("sort_dir") or "").strip()
    ALLOWED_SORT_FIELDS = {
        "student": "user__first_name",
        "exam": "exam__title",
        "violations": "supervision_violation_count",
        "status": "supervision_status",
        "start": "started_at",
    }
    if sort_by in ALLOWED_SORT_FIELDS and sort_dir in ("asc", "desc"):
        order_field = ALLOWED_SORT_FIELDS[sort_by]
        if sort_dir == "desc":
            order_field = f"-{order_field}"
        attempts = attempts.order_by(order_field, "-started_at")
    else:
        sort_by = ""
        sort_dir = ""
        attempts = attempts.order_by("-supervision_violation_count", "-started_at")

    # Build sort_base_query for pagination/sort links
    sort_base_params = {}
    if search_query:
        sort_base_params["q"] = search_query
    if status_filter:
        sort_base_params["status"] = status_filter
    if exam_id:
        sort_base_params["exam"] = exam_id
    if date_from_value:
        sort_base_params["date_from"] = date_from_value
    if date_to_value:
        sort_base_params["date_to"] = date_to_value
    sort_base_query = urlencode(sort_base_params)

    # Build pagination query (includes sort params)
    pagination_params = dict(sort_base_params)
    if sort_by:
        pagination_params["sort_by"] = sort_by
    if sort_dir:
        pagination_params["sort_dir"] = sort_dir
    pagination_query = urlencode(pagination_params)

    monitored_attempts_count = attempts.count()

    # Pagination is exam-based so newly created exams appear even before any
    # student joins or any violation is logged.
    page_number = request.GET.get("page", 1)
    paginator = Paginator(monitor_exams, 10)
    page_obj = paginator.get_page(page_number)
    page_exam_ids = [exam.id for exam in page_obj.object_list]

    attempts_by_exam = defaultdict(list)
    if page_exam_ids:
        for attempt in attempts.filter(exam_id__in=page_exam_ids):
            attempts_by_exam[attempt.exam_id].append(attempt)

    exam_cards = []
    for exam in page_obj.object_list:
        exam_attempts = attempts_by_exam.get(exam.id, [])
        exam_cards.append(
            {
                "exam": exam,
                "attempts": exam_attempts,
                "attempt_count": len(exam_attempts),
                "violation_total": sum(item.supervision_violation_count for item in exam_attempts),
                "active_count": sum(1 for item in exam_attempts if not item.is_finished),
            }
        )

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
        "exam_cards": exam_cards,
        "supervised_exams": data["supervised_exams"],
        "total_incidents": data["total_incidents"],
        "monitored_attempts_count": monitored_attempts_count,
        "severity_counts": severity_counts,
        "violation_type_counts": violation_type_counts,
        "search_query": search_query,
        "status_filter": status_filter,
        "severity_filter": severity_filter,
        "selected_exam_id": exam_id,
        "date_from_value": date_from_value,
        "date_to_value": date_to_value,
        "sort_by": sort_by,
        "sort_dir": sort_dir,
        "sort_base_query": sort_base_query,
        "pagination_query": pagination_query,
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
        exam__in=_supervision_exam_queryset(request, org),
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
        exam__in=_supervision_exam_queryset(request, org),
    )

    # A manual teacher pause must stay resumable regardless of the exam clock —
    # do NOT auto-expire it here.  Only auto-lock (violation) attempts are
    # subject to the time-limit / terminated checks before resuming.
    is_manual_lock = bool(getattr(attempt, "supervision_manual_lock", False))

    if not is_manual_lock:
        attempt.expire_if_time_limit_reached()

        # Explicitly block resume for terminated/finished attempts
        if attempt.is_finished:
            return JsonResponse(
                {"error": pgettext("supervision.view.api", "attempt_already_terminated")},
                status=403,
            )

    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        body = {}

    grant_extra_chance = body.get("grant_extra_chance", False)

    try:
        teacher_resume_attempt(attempt, request.user, grant_extra_chance=grant_extra_chance)
    except ValueError as exc:
        return JsonResponse(
            {"error": str(exc) or pgettext("supervision.view.api", "operation_not_allowed")},
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
        exam__in=_supervision_exam_queryset(request, org),
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


@login_required
@require_POST
def teacher_lock_api(request, attempt_id):
    """
    Teacher action to temporarily lock a supervised student attempt.
    Locks the student's screen without submitting the exam.
    The teacher can later resume or permanently remove the student.
    """
    org = _ensure_organization_context(request)
    _ensure_teacher(request.user)

    attempt = get_object_or_404(
        ExamAttempt.objects.select_related("exam"),
        id=attempt_id,
        exam__organization=org,
        exam__in=_supervision_exam_queryset(request, org),
    )

    try:
        teacher_lock_attempt(attempt, request.user)
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
        },
        reason="teacher_temporary_lock_supervision",
        request=request,
    )

    return JsonResponse(
        {
            "success": True,
            "supervision_status": attempt.supervision_status,
        }
    )


# ─────────────────────────────────────────────
# Live exam monitoring (per-exam dashboard)
# ─────────────────────────────────────────────


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


@login_required
def exam_live_monitor(request, exam_id):
    """
    Live monitoring dashboard for a single exam: every student's progress and
    supervision state, a student map, and a suspicious-events feed. Read-only
    observation — a teacher can watch without interfering; stop/lock remain
    explicit actions via the existing APIs.
    """
    org = _ensure_organization_context(request)
    _ensure_teacher(request.user)

    exam = _get_scoped_exam_or_404(request, org, exam_id)
    date_value = _parse_date_param(request)

    data = get_exam_live_monitor_data(exam, date_value=date_value)
    session_dates = get_exam_session_dates(exam)

    from django.utils import timezone

    context = {
        "exam": exam,
        "monitor_data": data,
        "session_dates": session_dates,
        "selected_date": date_value.isoformat() if date_value else "",
        "today_value": timezone.localdate().isoformat(),
        "poll_url": f"/exams/supervision/live/{exam.id}/poll/",
    }
    return render(request, "exams/teacher/exam_live_monitor.html", context)


@login_required
@require_GET
def exam_live_monitor_poll_api(request, exam_id):
    """JSON polling endpoint that backs the live dashboard's auto-refresh."""
    org = _ensure_organization_context(request)
    _ensure_teacher(request.user)

    exam = _get_scoped_exam_or_404(request, org, exam_id)
    date_value = _parse_date_param(request)

    data = get_exam_live_monitor_data(exam, date_value=date_value)
    return JsonResponse(data)


@login_required
@require_GET
def attempt_live_snapshot_api(request, attempt_id):
    """
    JSON snapshot of one student's current answers + supervision events, for the
    "look over the shoulder" modal. Read-only; scope enforced via the exam.
    """
    org = _ensure_organization_context(request)
    _ensure_teacher(request.user)

    attempt = get_object_or_404(
        ExamAttempt.objects.select_related("user", "exam"),
        id=attempt_id,
        exam__organization=org,
        exam__in=_supervision_exam_queryset(request, org),
    )

    return JsonResponse(get_attempt_live_snapshot(attempt))
