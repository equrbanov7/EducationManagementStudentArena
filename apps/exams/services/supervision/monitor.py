"""supervision paketi — monitor."""

from django.utils import timezone

from apps.exams.features import disabled_supervision_status, exam_supervision_enabled
from apps.exams.models import Exam, ExamAttempt, SupervisionIncident

from ._shared import (
    get_supervision_config,
)
from .actions import (
    sweep_expired_resume_windows,
)
from .constants import (
    VIOLATION_EVENT_TYPES,
)
from .interventions import get_attempt_intervention


def get_attempt_supervision_status(attempt):
    """Get current supervision status and details for an attempt."""
    if not exam_supervision_enabled():
        return disabled_supervision_status(attempt)

    config = get_supervision_config(attempt.exam)
    # Resume window countdown: how long the student still has to actually
    # return after a resume before the backend auto-finishes the attempt.
    resume_deadline = attempt.supervision_resume_deadline
    resume_seconds_remaining = None
    if resume_deadline is not None:
        resume_seconds_remaining = max(0, int((resume_deadline - timezone.now()).total_seconds()))

    config_payload = {}
    max_violations = 3
    resume_window_seconds = 0
    if config is not None:
        max_violations = config.get_max_total_violations()
        resume_window_seconds = config.resume_window_seconds
        config_payload = {
            "force_fullscreen": config.force_fullscreen,
            "grace_period_seconds": config.grace_period_seconds,
            "detect_tab_switch": config.detect_tab_switch,
            "block_copy_paste": config.block_copy_paste,
            "disable_right_click": config.disable_right_click,
            "disable_text_selection": config.disable_text_selection,
            "restrict_keyboard_shortcuts": config.restrict_keyboard_shortcuts,
            "violation_action": config.violation_action,
            "recovery_policy": config.recovery_policy,
        }

    intervention = get_attempt_intervention(attempt)
    return {
        "supervised": config is not None,
        "supervision_status": attempt.supervision_status,
        "manual_lock": bool(attempt.supervision_manual_lock and attempt.supervision_status == "locked"),
        "violation_count": attempt.supervision_violation_count,
        "max_violations": max_violations,
        "extra_chances_used": attempt.supervision_extra_chances,
        "resume_window_seconds": resume_window_seconds,
        "resume_seconds_remaining": resume_seconds_remaining,
        "resume_deadline": resume_deadline.isoformat() if resume_deadline else None,
        "intervention_action": intervention["action"],
        "intervention_reason": intervention["reason"],
        "config": config_payload,
    }


def get_flagged_students_for_exam(exam, organization):
    """Get summary of flagged students for a specific exam."""
    if not exam_supervision_enabled():
        return []

    attempts = (
        ExamAttempt.objects.filter(
            exam=exam,
            exam__organization=organization,
            supervision_violation_count__gt=0,
        )
        .select_related("user", "exam")
        .order_by("-supervision_violation_count")
    )

    return [
        {
            "attempt_id": a.id,
            "student_id": a.user_id,
            "student_name": a.user.get_full_name() or a.user.username,
            "student_username": a.user.username,
            "violation_count": a.supervision_violation_count,
            "supervision_status": a.supervision_status,
            "started_at": a.started_at,
            "status": a.status,
        }
        for a in attempts
    ]


def get_supervision_monitor_data(organization, exam_id=None, exam_queryset=None):
    """
    Get supervision monitor data for the teacher dashboard.
    Returns all monitorable exams and their attempts, even when an exam has no
    explicit supervision config or has no violations yet.
    """
    if not exam_supervision_enabled():
        empty_qs = Exam.objects.none()
        return {
            "monitor_attempts": ExamAttempt.objects.none(),
            "monitor_exams": empty_qs,
            "supervised_exams": [],
            "total_incidents": 0,
            "incidents_qs": SupervisionIncident.objects.none(),
        }

    exam_choices_qs = (
        exam_queryset if exam_queryset is not None else Exam.objects.filter(organization=organization, is_deleted=False)
    )
    exam_choices_qs = exam_choices_qs.filter(organization=organization)

    monitor_exams = exam_choices_qs
    if exam_id:
        monitor_exams = monitor_exams.filter(id=exam_id)

    # Lazily finish any stale "resumed" attempts (student never returned within
    # the resume window) before building the view, scoped to this org so the
    # monitor never shows phantom open rows for exams that ended long ago.
    sweep_qs = ExamAttempt.objects.filter(exam__organization=organization, exam__in=monitor_exams)
    sweep_expired_resume_windows(sweep_qs)

    incidents_qs = SupervisionIncident.objects.filter(
        organization=organization,
    ).select_related("exam", "student", "attempt")
    incidents_qs = incidents_qs.filter(exam__in=monitor_exams)
    if exam_id:
        incidents_qs = incidents_qs.filter(exam_id=exam_id)

    # Get all joined attempts.  ``exam__supervision_config`` is selected so
    # the per-row ``supervision_resume_deadline`` countdown does not trigger an
    # extra query for every resumed attempt.
    monitor_attempts = (
        ExamAttempt.objects.filter(
            exam__organization=organization,
            exam__in=monitor_exams,
        )
        .select_related("user", "exam", "exam__course", "exam__supervision_config")
        .order_by("-supervision_violation_count")
    )

    exam_choices = exam_choices_qs.order_by("title", "id").values_list("id", "title")

    # Summary stats
    total_incidents = incidents_qs.filter(
        event_type__in=VIOLATION_EVENT_TYPES,
    ).count()

    return {
        "monitor_attempts": monitor_attempts,
        "monitor_exams": monitor_exams.select_related("course", "author").order_by("-created_at", "-id"),
        "supervised_exams": list(exam_choices),
        "total_incidents": total_incidents,
        "incidents_qs": incidents_qs,
    }


def get_exam_question_total(exam):
    """
    Total number of questions a student is shown for this exam.

    Honours the project rule that a test may draw N random questions from a
    larger bank: when ``random_question_count`` is set we use it, otherwise we
    fall back to the number of questions actually attached to the exam.
    """
    random_count = getattr(exam, "random_question_count", 0) or 0
    if random_count > 0:
        return random_count
    return exam.questions.count()


def _attempt_live_state(attempt):
    """
    Map an attempt to a coarse live state used by the monitor map / stats.

    Returns one of: ``finished`` (submitted/expired), ``flagged`` (locked or
    removed by supervision), ``in_progress`` (actively taking the exam).
    Students who never started have no attempt row, so they are handled by the
    caller (``not_entered``) rather than here.
    """
    if attempt.is_finished:
        return "finished"
    if attempt.supervision_status in ("locked", "removed"):
        return "flagged"
    return "in_progress"


def get_exam_live_monitor_data(exam, date_value=None):
    """
    Live monitoring snapshot for a single exam session.

    Scope note: ``exam`` MUST already be tenant/permission scoped by the caller
    (the view resolves it through ``_supervision_exam_queryset``). This function
    never widens scope — it only reads attempts/incidents for the given exam.

    ``date_value`` optionally filters to attempts started on that calendar day
    (the "today" button / date picker), since one exam can be run on several
    dates. When ``None`` all sessions are included.

    Returns a JSON-serialisable dict consumed by both the initial page render
    and the polling endpoint, so the two never drift apart.
    """
    if not exam_supervision_enabled():
        return {
            "exam_id": exam.id,
            "exam_title": exam.title,
            "total_questions": get_exam_question_total(exam),
            "counts": {"entered": 0, "in_progress": 0, "finished": 0, "flagged": 0, "not_entered": 0},
            "status_dist": {"active": 0, "warned": 0, "locked": 0, "removed": 0, "resumed": 0},
            "violation_type_dist": {},
            "avg_progress": 0,
            "total_violations": 0,
            "students": [],
            "recent_incidents": [],
        }

    from django.db.models import Count

    # ``answered_count`` is annotated so each student's progress is read in the
    # single attempts query instead of one COUNT per row (avoids N+1).
    attempts_qs = (
        ExamAttempt.objects.filter(exam=exam)
        .select_related("user", "exam", "exam__supervision_config")
        .annotate(answered_count=Count("answers", distinct=True))
        .order_by("started_at")
    )
    if date_value is not None:
        attempts_qs = attempts_qs.filter(started_at__date=date_value)

    total_questions = get_exam_question_total(exam)

    students = []
    counts = {"entered": 0, "in_progress": 0, "finished": 0, "flagged": 0, "not_entered": 0}
    status_dist = {"active": 0, "warned": 0, "locked": 0, "removed": 0, "resumed": 0}
    progress_sum = 0
    progress_n = 0

    for a in attempts_qs:
        counts["entered"] += 1
        state = _attempt_live_state(a)
        counts[state] = counts.get(state, 0) + 1
        if a.supervision_status in status_dist:
            status_dist[a.supervision_status] += 1

        answered = a.answered_count
        progress_pct = int(round((answered / total_questions) * 100)) if total_questions else 0
        if not a.is_finished:
            progress_sum += progress_pct
            progress_n += 1

        # Coarse violation severity tier drives the map cell colour. Kept here
        # (not the client) so the rule stays in one place and matches the feed.
        vio = a.supervision_violation_count
        if a.supervision_status == "removed":
            vio_level = "removed"
        elif vio >= 6:
            vio_level = "critical"
        elif vio >= 3:
            vio_level = "high"
        elif vio >= 1:
            vio_level = "low"
        else:
            vio_level = "none"

        # Lightweight raw score (correct vs answered) — only meaningful once the
        # attempt is finished. We avoid the heavier per-test result calculation
        # here to keep the monitor query cheap; the modal shows the precise score.
        graded = a.correct_count + a.wrong_count
        raw_score = int(round(a.correct_count * 100 / graded)) if graded else None

        students.append(
            {
                "attempt_id": a.id,
                "student_id": a.user_id,
                "name": a.user.get_full_name() or a.user.username,
                "username": a.user.username,
                "state": state,
                "supervision_status": a.supervision_status,
                "violation_count": vio,
                "violation_level": vio_level,
                "answered": answered,
                "total_questions": total_questions,
                "progress_pct": progress_pct,
                "correct_count": a.correct_count,
                "wrong_count": a.wrong_count,
                "score_percent": raw_score if a.is_finished else None,
                "checked_by_teacher": a.checked_by_teacher,
                "teacher_score": a.teacher_score,
                "started_at": a.started_at.isoformat() if a.started_at else None,
                "finished_at": a.finished_at.isoformat() if a.finished_at else None,
                "is_finished": a.is_finished,
            }
        )

    # Recent suspicious events for the live feed (most recent first).
    incidents_qs = (
        SupervisionIncident.objects.filter(exam=exam, event_type__in=VIOLATION_EVENT_TYPES)
        .select_related("student")
        .order_by("-timestamp")
    )
    if date_value is not None:
        incidents_qs = incidents_qs.filter(timestamp__date=date_value)

    recent_incidents = [
        {
            "student_name": inc.student.get_full_name() or inc.student.username,
            "event_type": inc.event_type,
            "severity": inc.severity,
            "timestamp": inc.timestamp.isoformat(),
        }
        for inc in incidents_qs[:25]
    ]

    # Violation-type distribution for the chart (single aggregation query).
    from django.db.models import Count as _Count

    vtype_dist = dict(incidents_qs.values("event_type").annotate(c=_Count("id")).values_list("event_type", "c"))

    avg_progress = int(round(progress_sum / progress_n)) if progress_n else 0

    return {
        "exam_id": exam.id,
        "exam_title": exam.title,
        "total_questions": total_questions,
        "counts": counts,
        "status_dist": status_dist,
        "violation_type_dist": vtype_dist,
        "avg_progress": avg_progress,
        "total_violations": incidents_qs.count(),
        "students": students,
        "recent_incidents": recent_incidents,
    }


def get_exam_session_dates(exam):
    """
    Distinct calendar dates on which this exam has been attempted, newest first.

    Used to populate the date filter so a teacher can isolate one sitting of an
    exam that is run on multiple days.
    """
    if not exam_supervision_enabled():
        return []

    from django.db.models.functions import TruncDate

    return list(
        ExamAttempt.objects.filter(exam=exam)
        .annotate(day=TruncDate("started_at"))
        .values_list("day", flat=True)
        .distinct()
        .order_by("-day")
    )
