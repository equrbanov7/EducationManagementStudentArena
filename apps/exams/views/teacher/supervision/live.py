"""teacher supervision view paketi — live."""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_GET

from apps.exams.features import exam_supervision_enabled
from apps.exams.models import ExamAttempt
from apps.exams.services.access_policy import _ensure_teacher
from apps.exams.services.supervision import (
    get_attempt_live_snapshot,
    get_exam_live_monitor_data,
    get_exam_session_dates,
)

from ._shared import (
    _ensure_organization_context,
    _ensure_supervision_feature_enabled,
    _get_scoped_exam_or_404,
    _parse_date_param,
    _supervision_disabled_json,
    _supervision_exam_queryset,
)


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
    _ensure_supervision_feature_enabled()

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
    if not exam_supervision_enabled():
        return _supervision_disabled_json()

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
    if not exam_supervision_enabled():
        return _supervision_disabled_json()

    attempt = get_object_or_404(
        ExamAttempt.objects.select_related("user", "exam"),
        id=attempt_id,
        exam__organization=org,
        exam__in=_supervision_exam_queryset(request, org),
    )

    return JsonResponse(get_attempt_live_snapshot(attempt))
