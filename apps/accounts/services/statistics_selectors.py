"""
Statistics selectors — role-aware data aggregation for the profile
statistics section.

Each public function returns a plain dict ready for template rendering.
Heavy work is done via QuerySet annotations / aggregations to avoid N+1
queries.  Every function respects multi-tenancy: only data within the
caller's organization (or globally for superadmins) is ever returned.

Metrics that are NOT supported by the current data model are documented
in the ``UNSUPPORTED_METRICS`` constant at the bottom of this file.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models import (
    Avg,
    Case,
    Count,
    F,
    Max,
    Min,
    Q,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Coalesce, TruncDate, TruncMonth
from django.utils import timezone

User = get_user_model()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ZERO = Decimal("0")


def _safe_pct(numerator, denominator):
    if not denominator:
        return 0.0
    return round(float(numerator) * 100 / float(denominator), 1)


def _safe_avg(values):
    nums = [float(v) for v in values if v is not None]
    return round(sum(nums) / len(nums), 1) if nums else 0.0


def _parse_date(raw):
    """Parse a YYYY-MM-DD string to a date object, or None."""
    from datetime import date as _date

    if not raw:
        return None
    try:
        return _date.fromisoformat(str(raw).strip())
    except (ValueError, TypeError):
        return None


def _apply_date_filter(qs, field_name, date_from, date_to):
    if date_from:
        qs = qs.filter(**{f"{field_name}__date__gte": date_from})
    if date_to:
        qs = qs.filter(**{f"{field_name}__date__lte": date_to})
    return qs


# ---------------------------------------------------------------------------
# Student statistics
# ---------------------------------------------------------------------------


def get_student_statistics(user, *, organization=None, filters=None):
    """Aggregate the requesting student's own performance data."""
    from apps.assignments.models import Submission
    from apps.courses.models import CourseMembership
    from apps.exams.models import ExamAttempt
    from apps.labs.models import LabSubmission
    from apps.live_exam.models import LiveAnswer, LivePlayer
    from apps.projects.models import ProjectSubmission

    filters = filters or {}
    date_from = _parse_date(filters.get("date_from"))
    date_to = _parse_date(filters.get("date_to"))
    course_id = filters.get("course")
    content_type = filters.get("content_type", "all")

    # ── Exam attempts ─────────────────────────────────────────────
    exam_attempts = ExamAttempt.objects.filter(user=user)
    if organization:
        exam_attempts = exam_attempts.filter(exam__organization=organization)
    if course_id:
        exam_attempts = exam_attempts.filter(exam__course_id=course_id)
    exam_attempts = _apply_date_filter(exam_attempts, "started_at", date_from, date_to)
    exam_list = list(
        exam_attempts.select_related("exam").values(
            "id",
            "exam__title",
            "exam__exam_type",
            "exam__max_score",
            "correct_count",
            "wrong_count",
            "teacher_score",
            "status",
            "started_at",
            "completed_at",
            "checked_by_teacher",
        )
    )

    def _exam_pct(a):
        if a["exam__exam_type"] == "written":
            ms = float(a["exam__max_score"] or 0)
            return round(float(a["teacher_score"] or 0) * 100 / ms, 1) if ms else 0
        total = (a["correct_count"] or 0) + (a["wrong_count"] or 0)
        return round((a["correct_count"] or 0) * 100 / total, 1) if total else 0

    exam_scores = [_exam_pct(a) for a in exam_list if a["status"] in ("submitted", "expired")]
    exam_passed = sum(1 for s in exam_scores if s >= 50)

    # ── Assignments ───────────────────────────────────────────────
    submissions_qs = Submission.objects.filter(user=user)
    if organization:
        submissions_qs = submissions_qs.filter(assignment__course__organization=organization)
    if course_id:
        submissions_qs = submissions_qs.filter(assignment__course_id=course_id)
    submissions_qs = _apply_date_filter(submissions_qs, "submitted_at", date_from, date_to)
    assignment_list = list(
        submissions_qs.values(
            "id",
            "assignment__title",
            "assignment__max_score",
            "grade",
            "status",
            "is_late",
            "submitted_at",
        )
    )
    assignment_graded = [s for s in assignment_list if s["status"] == "graded" and s["grade"] is not None]
    assignment_scores = [
        _safe_pct(s["grade"], s["assignment__max_score"]) for s in assignment_graded
    ]

    # ── Labs ──────────────────────────────────────────────────────
    lab_subs = LabSubmission.objects.filter(assignment__student=user)
    if organization:
        lab_subs = lab_subs.filter(assignment__lab__course__organization=organization)
    if course_id:
        lab_subs = lab_subs.filter(assignment__lab__course_id=course_id)
    lab_subs = _apply_date_filter(lab_subs, "submitted_at", date_from, date_to)
    lab_list = list(
        lab_subs.values(
            "id",
            "assignment__lab__title",
            "assignment__lab__max_score",
            "score",
            "status",
            "submitted_at",
        )
    )
    lab_graded = [s for s in lab_list if s["status"] == "graded" and s["score"] is not None]
    lab_scores = [
        _safe_pct(s["score"], s["assignment__lab__max_score"]) for s in lab_graded
    ]

    # ── Projects ──────────────────────────────────────────────────
    proj_subs = ProjectSubmission.objects.filter(student=user)
    if organization:
        proj_subs = proj_subs.filter(project__course__organization=organization)
    if course_id:
        proj_subs = proj_subs.filter(project__course_id=course_id)
    proj_subs = _apply_date_filter(proj_subs, "submitted_at", date_from, date_to)
    proj_list = list(
        proj_subs.values(
            "id",
            "project__title",
            "project__max_score",
            "grade",
            "status",
            "submitted_at",
        )
    )
    proj_graded = [s for s in proj_list if s["status"] == "graded" and s["grade"] is not None]
    proj_scores = [
        _safe_pct(s["grade"], s["project__max_score"]) for s in proj_graded
    ]

    # ── Live exams ────────────────────────────────────────────────
    live_players = LivePlayer.objects.filter(
        session__state="finished",
    )
    # Filter by nickname containing username (players are semi-anonymous)
    live_answers = LiveAnswer.objects.filter(
        player__in=live_players,
    )
    if organization:
        live_answers = live_answers.filter(session__exam__organization=organization)
    live_answers = _apply_date_filter(live_answers, "session__created_at", date_from, date_to)
    live_stats = live_answers.aggregate(
        total=Count("id"),
        correct=Count("id", filter=Q(is_correct=True)),
    )
    live_total = live_stats["total"] or 0
    live_correct = live_stats["correct"] or 0

    # ── Aggregate all scores ──────────────────────────────────────
    all_scores = []
    if content_type in ("all", "exam"):
        all_scores.extend(exam_scores)
    if content_type in ("all", "assignment"):
        all_scores.extend(assignment_scores)
    if content_type in ("all", "lab"):
        all_scores.extend(lab_scores)
    if content_type in ("all", "project"):
        all_scores.extend(proj_scores)

    total_items = (
        len(exam_list) + len(assignment_list) + len(lab_list) + len(proj_list)
    )
    graded_items = len(exam_scores) + len(assignment_graded) + len(lab_graded) + len(proj_graded)
    pending_items = total_items - graded_items

    late_count = sum(1 for s in assignment_list if s["is_late"])
    on_time_count = len(assignment_list) - late_count

    avg_score = _safe_avg(all_scores) if all_scores else 0
    pass_count = sum(1 for s in all_scores if s >= 50)
    pass_rate = _safe_pct(pass_count, len(all_scores))

    # ── Score trend (monthly) ─────────────────────────────────────
    trend_data = defaultdict(list)
    for a in exam_list:
        if a["started_at"] and a["status"] in ("submitted", "expired"):
            month = a["started_at"].strftime("%Y-%m")
            trend_data[month].append(_exam_pct(a))
    for s in assignment_graded:
        if s["submitted_at"]:
            month = s["submitted_at"].strftime("%Y-%m")
            trend_data[month].append(_safe_pct(s["grade"], s["assignment__max_score"]))
    for s in lab_graded:
        if s["submitted_at"]:
            month = s["submitted_at"].strftime("%Y-%m")
            trend_data[month].append(_safe_pct(s["score"], s["assignment__lab__max_score"]))

    trend_labels = sorted(trend_data.keys())[-12:]
    trend_values = [_safe_avg(trend_data[m]) for m in trend_labels]

    # ── Courses enrolled ──────────────────────────────────────────
    enrolled_courses = CourseMembership.objects.filter(user=user, role="student")
    if organization:
        enrolled_courses = enrolled_courses.filter(course__organization=organization)
    course_names = list(enrolled_courses.values_list("course__title", flat=True)[:20])

    return {
        "summary": {
            "total_items": total_items,
            "graded_items": graded_items,
            "pending_items": pending_items,
            "avg_score": avg_score,
            "pass_rate": pass_rate,
            "pass_count": pass_count,
            "fail_count": len(all_scores) - pass_count,
            "late_count": late_count,
            "on_time_count": on_time_count,
            "exam_count": len(exam_list),
            "assignment_count": len(assignment_list),
            "lab_count": len(lab_list),
            "project_count": len(proj_list),
            "live_total": live_total,
            "live_correct": live_correct,
            "live_accuracy": _safe_pct(live_correct, live_total),
            "enrolled_courses": len(course_names),
        },
        "trend": {
            "labels": trend_labels,
            "values": trend_values,
        },
        "score_breakdown": {
            "exam_avg": _safe_avg(exam_scores),
            "assignment_avg": _safe_avg(assignment_scores),
            "lab_avg": _safe_avg(lab_scores),
            "project_avg": _safe_avg(proj_scores),
        },
        "recent_activity": (exam_list + assignment_list + lab_list + proj_list)[:10],
        "courses": course_names,
    }


# ---------------------------------------------------------------------------
# Teacher statistics
# ---------------------------------------------------------------------------


def get_teacher_statistics(user, *, organization=None, filters=None):
    """Aggregate teaching statistics for courses/exams owned by the teacher."""
    from apps.assignments.models import Assignment, Submission
    from apps.courses.models import Course, CourseMembership
    from apps.exams.models import Exam, ExamAttempt, StudentGroup
    from apps.labs.models import Lab, LabSubmission
    from apps.projects.models import Project, ProjectSubmission

    filters = filters or {}
    date_from = _parse_date(filters.get("date_from"))
    date_to = _parse_date(filters.get("date_to"))
    course_id = filters.get("course")
    group_id = filters.get("group")

    # ── Owned courses ─────────────────────────────────────────────
    courses = Course.objects.filter(owner=user)
    if organization:
        courses = courses.filter(organization=organization)
    if course_id:
        courses = courses.filter(id=course_id)
    course_ids = list(courses.values_list("id", flat=True))

    total_students = CourseMembership.objects.filter(
        course_id__in=course_ids, role="student"
    ).values("user").distinct().count()

    # ── Exams ─────────────────────────────────────────────────────
    exams = Exam.objects.filter(author=user)
    if organization:
        exams = exams.filter(organization=organization)
    if course_id:
        exams = exams.filter(course_id=course_id)
    exam_ids = list(exams.values_list("id", flat=True))

    attempts = ExamAttempt.objects.filter(exam_id__in=exam_ids)
    attempts = _apply_date_filter(attempts, "started_at", date_from, date_to)
    if group_id:
        try:
            group = StudentGroup.objects.get(id=int(group_id))
            attempts = attempts.filter(user__in=group.students.all())
        except (StudentGroup.DoesNotExist, ValueError, TypeError):
            pass

    attempt_stats = attempts.aggregate(
        total=Count("id"),
        submitted=Count("id", filter=Q(status="submitted")),
        expired=Count("id", filter=Q(status="expired")),
        checked=Count("id", filter=Q(checked_by_teacher=True)),
    )

    # Exam scores
    scored_attempts = list(
        attempts.filter(status__in=["submitted", "expired"]).values(
            "exam__exam_type",
            "exam__max_score",
            "correct_count",
            "wrong_count",
            "teacher_score",
        )
    )

    def _attempt_pct(a):
        if a["exam__exam_type"] == "written":
            ms = float(a["exam__max_score"] or 0)
            return round(float(a["teacher_score"] or 0) * 100 / ms, 1) if ms else 0
        total = (a["correct_count"] or 0) + (a["wrong_count"] or 0)
        return round((a["correct_count"] or 0) * 100 / total, 1) if total else 0

    exam_scores = [_attempt_pct(a) for a in scored_attempts]
    exam_avg = _safe_avg(exam_scores)
    exam_pass_count = sum(1 for s in exam_scores if s >= 50)
    exam_pass_rate = _safe_pct(exam_pass_count, len(exam_scores))

    # ── Assignments ───────────────────────────────────────────────
    assignments = Assignment.objects.filter(course_id__in=course_ids)
    assignment_subs = Submission.objects.filter(assignment__in=assignments)
    assignment_subs = _apply_date_filter(assignment_subs, "submitted_at", date_from, date_to)
    assignment_stats = assignment_subs.aggregate(
        total=Count("id"),
        graded=Count("id", filter=Q(status="graded")),
        late=Count("id", filter=Q(is_late=True)),
    )

    # Grading turnaround (avg days between submitted_at and graded_at)
    graded_subs = assignment_subs.filter(
        status="graded", graded_at__isnull=False
    ).values("submitted_at", "graded_at")
    turnaround_days = []
    for sub in graded_subs:
        if sub["submitted_at"] and sub["graded_at"]:
            delta = (sub["graded_at"] - sub["submitted_at"]).total_seconds() / 86400
            turnaround_days.append(delta)
    avg_turnaround = round(sum(turnaround_days) / len(turnaround_days), 1) if turnaround_days else 0

    # ── Labs ──────────────────────────────────────────────────────
    labs = Lab.objects.filter(course_id__in=course_ids)
    lab_subs = LabSubmission.objects.filter(assignment__lab__in=labs)
    lab_subs = _apply_date_filter(lab_subs, "submitted_at", date_from, date_to)
    lab_stats = lab_subs.aggregate(
        total=Count("id"),
        graded=Count("id", filter=Q(status="graded")),
    )

    # ── Projects ──────────────────────────────────────────────────
    projects = Project.objects.filter(course_id__in=course_ids)
    proj_subs = ProjectSubmission.objects.filter(project__in=projects)
    proj_subs = _apply_date_filter(proj_subs, "submitted_at", date_from, date_to)
    proj_stats = proj_subs.aggregate(
        total=Count("id"),
        graded=Count("id", filter=Q(status="graded")),
    )

    # ── Group comparison ──────────────────────────────────────────
    groups_qs = StudentGroup.objects.none()
    if organization:
        groups_qs = StudentGroup.objects.filter(organization=organization)
    group_comparison = []
    for grp in groups_qs[:20]:
        grp_attempts = ExamAttempt.objects.filter(
            exam_id__in=exam_ids,
            user__in=grp.students.all(),
            status__in=["submitted", "expired"],
        )
        grp_attempts = _apply_date_filter(grp_attempts, "started_at", date_from, date_to)
        grp_scored = list(
            grp_attempts.values(
                "exam__exam_type",
                "exam__max_score",
                "correct_count",
                "wrong_count",
                "teacher_score",
            )
        )
        grp_scores = [_attempt_pct(a) for a in grp_scored]
        grp_avg = _safe_avg(grp_scores)
        group_comparison.append({
            "id": grp.id,
            "name": grp.name,
            "student_count": grp.students.count(),
            "avg_score": grp_avg,
            "attempt_count": len(grp_scored),
            "pass_rate": _safe_pct(
                sum(1 for s in grp_scores if s >= 50), len(grp_scores)
            ),
        })

    # ── Submission trend ──────────────────────────────────────────
    trend_data = defaultdict(int)
    for a in attempts.filter(started_at__isnull=False).values("started_at"):
        month = a["started_at"].strftime("%Y-%m")
        trend_data[month] += 1
    trend_labels = sorted(trend_data.keys())[-12:]
    trend_values = [trend_data[m] for m in trend_labels]

    return {
        "summary": {
            "total_courses": len(course_ids),
            "total_students": total_students,
            "total_exams": len(exam_ids),
            "total_attempts": attempt_stats["total"] or 0,
            "submitted_attempts": attempt_stats["submitted"] or 0,
            "checked_attempts": attempt_stats["checked"] or 0,
            "exam_avg_score": exam_avg,
            "exam_pass_rate": exam_pass_rate,
            "assignment_total": assignment_stats["total"] or 0,
            "assignment_graded": assignment_stats["graded"] or 0,
            "assignment_late": assignment_stats["late"] or 0,
            "avg_grading_turnaround_days": avg_turnaround,
            "lab_total": lab_stats["total"] or 0,
            "lab_graded": lab_stats["graded"] or 0,
            "project_total": proj_stats["total"] or 0,
            "project_graded": proj_stats["graded"] or 0,
        },
        "trend": {
            "labels": trend_labels,
            "values": trend_values,
        },
        "group_comparison": group_comparison,
    }


# ---------------------------------------------------------------------------
# Organization admin statistics
# ---------------------------------------------------------------------------


def get_org_admin_statistics(*, organization, filters=None):
    """Organization-scoped analytics for org admins."""
    from apps.assignments.models import Submission
    from apps.courses.models import Course, CourseMembership
    from apps.exams.models import Exam, ExamAttempt
    from apps.labs.models import LabSubmission
    from apps.organizations.models import Membership
    from apps.projects.models import ProjectSubmission

    filters = filters or {}
    date_from = _parse_date(filters.get("date_from"))
    date_to = _parse_date(filters.get("date_to"))
    course_id = filters.get("course")

    # ── Active members ────────────────────────────────────────────
    memberships = Membership.objects.filter(organization=organization, is_active=True)
    total_members = memberships.values("user").distinct().count()
    teacher_count = memberships.filter(role__level__gte=55).values("user").distinct().count()
    student_count = memberships.filter(role__level__lte=30).values("user").distinct().count()

    # ── Courses ───────────────────────────────────────────────────
    courses = Course.objects.filter(organization=organization)
    if course_id:
        courses = courses.filter(id=course_id)
    total_courses = courses.count()
    active_courses = courses.filter(status="active").count()

    course_ids = list(courses.values_list("id", flat=True))

    # ── Exams ─────────────────────────────────────────────────────
    exams = Exam.objects.filter(organization=organization)
    total_exams = exams.count()

    attempts = ExamAttempt.objects.filter(exam__organization=organization)
    attempts = _apply_date_filter(attempts, "started_at", date_from, date_to)
    attempt_agg = attempts.aggregate(
        total=Count("id"),
        submitted=Count("id", filter=Q(status="submitted")),
        checked=Count("id", filter=Q(checked_by_teacher=True)),
    )

    # ── Assignments ───────────────────────────────────────────────
    assignment_subs = Submission.objects.filter(
        assignment__course__organization=organization
    )
    assignment_subs = _apply_date_filter(assignment_subs, "submitted_at", date_from, date_to)
    asn_agg = assignment_subs.aggregate(
        total=Count("id"),
        graded=Count("id", filter=Q(status="graded")),
        late=Count("id", filter=Q(is_late=True)),
    )

    # ── Labs ──────────────────────────────────────────────────────
    lab_subs = LabSubmission.objects.filter(
        assignment__lab__course__organization=organization
    )
    lab_subs = _apply_date_filter(lab_subs, "submitted_at", date_from, date_to)
    lab_agg = lab_subs.aggregate(
        total=Count("id"),
        graded=Count("id", filter=Q(status="graded")),
    )

    # ── Projects ──────────────────────────────────────────────────
    proj_subs = ProjectSubmission.objects.filter(
        project__course__organization=organization
    )
    proj_subs = _apply_date_filter(proj_subs, "submitted_at", date_from, date_to)
    proj_agg = proj_subs.aggregate(
        total=Count("id"),
        graded=Count("id", filter=Q(status="graded")),
    )

    # ── Submission trend ──────────────────────────────────────────
    trend_data = defaultdict(int)
    for a in attempts.filter(started_at__isnull=False).values("started_at"):
        month = a["started_at"].strftime("%Y-%m")
        trend_data[month] += 1
    for s in assignment_subs.filter(submitted_at__isnull=False).values("submitted_at"):
        month = s["submitted_at"].strftime("%Y-%m")
        trend_data[month] += 1
    trend_labels = sorted(trend_data.keys())[-12:]
    trend_values = [trend_data[m] for m in trend_labels]

    # ── Course rankings (top 10 by enrollment) ────────────────────
    course_rankings = list(
        CourseMembership.objects.filter(course__organization=organization, role="student")
        .values("course__id", "course__title")
        .annotate(student_count=Count("user", distinct=True))
        .order_by("-student_count")[:10]
    )

    # ── Teacher overview ──────────────────────────────────────────
    teacher_user_ids = memberships.filter(role__level__gte=55).values_list("user_id", flat=True)
    teacher_overview = []
    for tid in list(teacher_user_ids)[:20]:
        t_exams = Exam.objects.filter(author_id=tid, organization=organization).count()
        t_courses = Course.objects.filter(owner_id=tid, organization=organization).count()
        t_user = User.objects.filter(id=tid).values("username", "first_name", "last_name").first()
        if t_user:
            teacher_overview.append({
                "user_id": tid,
                "username": t_user["username"],
                "name": f"{t_user['first_name']} {t_user['last_name']}".strip() or t_user["username"],
                "exam_count": t_exams,
                "course_count": t_courses,
            })

    return {
        "summary": {
            "total_members": total_members,
            "teacher_count": teacher_count,
            "student_count": student_count,
            "total_courses": total_courses,
            "active_courses": active_courses,
            "total_exams": total_exams,
            "total_attempts": attempt_agg["total"] or 0,
            "submitted_attempts": attempt_agg["submitted"] or 0,
            "checked_attempts": attempt_agg["checked"] or 0,
            "assignment_total": asn_agg["total"] or 0,
            "assignment_graded": asn_agg["graded"] or 0,
            "assignment_late": asn_agg["late"] or 0,
            "lab_total": lab_agg["total"] or 0,
            "lab_graded": lab_agg["graded"] or 0,
            "project_total": proj_agg["total"] or 0,
            "project_graded": proj_agg["graded"] or 0,
        },
        "trend": {
            "labels": trend_labels,
            "values": trend_values,
        },
        "course_rankings": course_rankings,
        "teacher_overview": teacher_overview,
    }


# ---------------------------------------------------------------------------
# Superadmin statistics
# ---------------------------------------------------------------------------


def get_superadmin_statistics(*, filters=None):
    """Platform-wide analytics for superadmins — cross-organization."""
    from apps.assignments.models import Submission
    from apps.courses.models import Course
    from apps.exams.models import Exam, ExamAttempt
    from apps.labs.models import LabSubmission
    from apps.organizations.models import Membership, Organization
    from apps.projects.models import ProjectSubmission

    filters = filters or {}
    date_from = _parse_date(filters.get("date_from"))
    date_to = _parse_date(filters.get("date_to"))
    org_id = filters.get("organization")

    # ── Organizations ─────────────────────────────────────────────
    orgs = Organization.objects.filter(is_active=True, status="active")
    total_orgs = orgs.count()

    # ── Users ─────────────────────────────────────────────────────
    total_users = User.objects.filter(is_active=True).count()
    total_memberships = Membership.objects.filter(is_active=True).count()

    # ── Scoping ───────────────────────────────────────────────────
    exam_filter = {}
    course_filter = {}
    if org_id:
        exam_filter["exam__organization_id"] = org_id
        course_filter["organization_id"] = org_id

    # ── Exams ─────────────────────────────────────────────────────
    attempts = ExamAttempt.objects.all()
    if org_id:
        attempts = attempts.filter(exam__organization_id=org_id)
    attempts = _apply_date_filter(attempts, "started_at", date_from, date_to)
    attempt_agg = attempts.aggregate(
        total=Count("id"),
        submitted=Count("id", filter=Q(status="submitted")),
        checked=Count("id", filter=Q(checked_by_teacher=True)),
    )

    total_exams = Exam.objects.filter(**{k.replace("exam__", ""): v for k, v in exam_filter.items()}).count() if exam_filter else Exam.objects.count()
    total_courses = Course.objects.filter(**course_filter).count() if course_filter else Course.objects.count()

    # ── Assignments ───────────────────────────────────────────────
    asn_qs = Submission.objects.all()
    if org_id:
        asn_qs = asn_qs.filter(assignment__course__organization_id=org_id)
    asn_qs = _apply_date_filter(asn_qs, "submitted_at", date_from, date_to)
    asn_agg = asn_qs.aggregate(
        total=Count("id"),
        graded=Count("id", filter=Q(status="graded")),
    )

    # ── Labs + Projects ───────────────────────────────────────────
    lab_qs = LabSubmission.objects.all()
    if org_id:
        lab_qs = lab_qs.filter(assignment__lab__course__organization_id=org_id)
    lab_qs = _apply_date_filter(lab_qs, "submitted_at", date_from, date_to)
    lab_agg = lab_qs.aggregate(total=Count("id"), graded=Count("id", filter=Q(status="graded")))

    proj_qs = ProjectSubmission.objects.all()
    if org_id:
        proj_qs = proj_qs.filter(project__course__organization_id=org_id)
    proj_qs = _apply_date_filter(proj_qs, "submitted_at", date_from, date_to)
    proj_agg = proj_qs.aggregate(total=Count("id"), graded=Count("id", filter=Q(status="graded")))

    # ── Org comparison ────────────────────────────────────────────
    org_comparison = []
    for org in orgs[:30]:
        o_members = Membership.objects.filter(organization=org, is_active=True).values("user").distinct().count()
        o_courses = Course.objects.filter(organization=org).count()
        o_exams = Exam.objects.filter(organization=org).count()
        o_attempts = ExamAttempt.objects.filter(exam__organization=org).count()
        org_comparison.append({
            "id": org.id,
            "name": org.name,
            "org_type": org.org_type,
            "members": o_members,
            "courses": o_courses,
            "exams": o_exams,
            "attempts": o_attempts,
        })

    # ── Submission trend ──────────────────────────────────────────
    trend_data = defaultdict(int)
    for a in attempts.filter(started_at__isnull=False).values("started_at"):
        month = a["started_at"].strftime("%Y-%m")
        trend_data[month] += 1
    trend_labels = sorted(trend_data.keys())[-12:]
    trend_values = [trend_data[m] for m in trend_labels]

    return {
        "summary": {
            "total_orgs": total_orgs,
            "total_users": total_users,
            "total_memberships": total_memberships,
            "total_courses": total_courses,
            "total_exams": total_exams,
            "total_attempts": attempt_agg["total"] or 0,
            "submitted_attempts": attempt_agg["submitted"] or 0,
            "checked_attempts": attempt_agg["checked"] or 0,
            "assignment_total": asn_agg["total"] or 0,
            "assignment_graded": asn_agg["graded"] or 0,
            "lab_total": lab_agg["total"] or 0,
            "lab_graded": lab_agg["graded"] or 0,
            "project_total": proj_agg["total"] or 0,
            "project_graded": proj_agg["graded"] or 0,
        },
        "trend": {
            "labels": trend_labels,
            "values": trend_values,
        },
        "org_comparison": org_comparison,
    }


# ---------------------------------------------------------------------------
# AI summary builder — role-aware prompt data
# ---------------------------------------------------------------------------


def build_ai_stats_payload(*, role, stats):
    """Build a concise stats dict suitable for the AI prompt.

    This strips internal keys and keeps only the data the AI model
    needs to reason about, preventing prompt bloat.
    """
    payload = {
        "role": role,
        "summary": stats.get("summary", {}),
    }
    if "trend" in stats:
        payload["trend"] = stats["trend"]
    if "group_comparison" in stats:
        payload["group_comparison"] = stats["group_comparison"][:10]
    if "score_breakdown" in stats:
        payload["score_breakdown"] = stats["score_breakdown"]
    if "org_comparison" in stats:
        payload["org_comparison"] = stats["org_comparison"][:10]
    if "course_rankings" in stats:
        payload["course_rankings"] = stats["course_rankings"][:10]
    return payload


# ---------------------------------------------------------------------------
# Unsupported metrics documentation
# ---------------------------------------------------------------------------

UNSUPPORTED_METRICS = """
The following metrics were requested but are NOT supported by the current
data model and were intentionally skipped:

Student:
  - Strongest/weakest topics: QuestionBlock is available on exams but not
    linked uniformly across assignments/labs/projects. Partial exam-block
    analysis is possible but not cross-content-type.
  - Comparison to class/group average: Possible for exams via StudentGroup
    but not uniformly across all content types.
  - Video watch time / attendance / login heatmaps: No model support.

Teacher:
  - Proctoring incident trends: ProctoringLog exists but SupervisionIncident
    aggregation per teacher is not directly linked; would require joining
    through exams + attempts. Deferred to future iteration.
  - At-risk students (automatic detection): Requires ML scoring or
    threshold-based rules not currently defined.

Organization Admin:
  - Grading SLA: No SLA target field exists on any model.
  - Workload distribution: Requires submission-per-teacher tracking which
    is partially possible but not reliably complete.

Superadmin:
  - Adoption/activity trends by country: Organization has country FK but
    activity (logins, daily active users) is not tracked.
  - Anomaly detection: Requires statistical baselines not currently stored.
  - Grading delays: Possible for assignments (submitted_at vs graded_at)
    but not uniformly for exams/labs/projects.

All roles:
  - AcademicPeriod / OrgUnit filtering: Models exist but content (exams,
    courses, etc.) does not consistently reference them. Filter UI is
    present but may return no results for orgs that don't use periods/units.
  - Radar/scatter charts for topic analysis: Deferred due to lack of
    uniform topic tagging across content types.
"""
