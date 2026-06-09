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
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db.models import (
    Count,
    Q,
)

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


def _content_type_enabled(selected_type, expected_type):
    return selected_type in ("all", expected_type)


# ---------------------------------------------------------------------------
# Student statistics
# ---------------------------------------------------------------------------


def get_student_statistics(user, *, organization=None, filters=None):
    """Aggregate the requesting student's own performance data."""
    from apps.assignments.models import Submission
    from apps.courses.models import CourseMembership
    from apps.exams.models import ExamAttempt
    from apps.labs.models import LabSubmission
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
            "exam__default_question_points",
            "correct_count",
            "wrong_count",
            "teacher_score",
            "status",
            "started_at",
            "finished_at",
            "checked_by_teacher",
        )
    )

    def _exam_pct(a):
        if a["exam__exam_type"] == "written":
            # Written exams use teacher_score directly; no max_score on model
            return float(a["teacher_score"] or 0)
        total = (a["correct_count"] or 0) + (a["wrong_count"] or 0)
        return round((a["correct_count"] or 0) * 100 / total, 1) if total else 0

    exam_scores = [_exam_pct(a) for a in exam_list if a["status"] in ("submitted", "expired")]
    # exam_passed = sum(1 for s in exam_scores if s >= 50)

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
    assignment_scores = [_safe_pct(s["grade"], s["assignment__max_score"]) for s in assignment_graded]

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
    lab_scores = [_safe_pct(s["score"], s["assignment__lab__max_score"]) for s in lab_graded]

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
    proj_scores = [_safe_pct(s["grade"], s["project__max_score"]) for s in proj_graded]

    # ── Live exams ────────────────────────────────────────────────
    # LivePlayer does not have a user FK — players are semi-anonymous
    # (identified by nickname + client_id). We cannot reliably tie live
    # exam answers to a specific user, so we report aggregate stats
    # for the organization only (not user-specific).
    live_total = 0
    live_correct = 0
    try:
        from apps.live_exam.models import LiveAnswer

        live_qs = LiveAnswer.objects.filter(session__state="finished")
        if organization:
            live_qs = live_qs.filter(session__exam__organization=organization)
        live_qs = _apply_date_filter(live_qs, "session__created_at", date_from, date_to)
        live_stats = live_qs.aggregate(
            total=Count("id"),
            correct=Count("id", filter=Q(is_correct=True)),
        )
        live_total = live_stats["total"] or 0
        live_correct = live_stats["correct"] or 0
    except Exception:
        pass

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

    total_items = len(exam_list) + len(assignment_list) + len(lab_list) + len(proj_list)
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
    content_type = filters.get("content_type", "all")

    # ── Owned courses ─────────────────────────────────────────────
    courses = Course.objects.filter(owner=user)
    if organization:
        courses = courses.filter(organization=organization)
    if course_id:
        courses = courses.filter(id=course_id)
    course_rows = list(courses.values("id", "title"))
    course_ids = [row["id"] for row in course_rows]

    group_students = None
    if group_id:
        try:
            group_students = StudentGroup.objects.get(id=int(group_id)).students.all()
        except (StudentGroup.DoesNotExist, ValueError, TypeError):
            group_students = None

    total_students = (
        CourseMembership.objects.filter(course_id__in=course_ids, role="student").values("user").distinct().count()
    )

    # ── Exams ─────────────────────────────────────────────────────
    exams = Exam.objects.none()
    exam_ids = []
    attempts = ExamAttempt.objects.none()
    attempt_stats = {
        "total": 0,
        "submitted": 0,
        "expired": 0,
        "checked": 0,
    }
    if _content_type_enabled(content_type, "exam"):
        exams = Exam.objects.filter(author=user)
        if organization:
            exams = exams.filter(organization=organization)
        if course_id:
            exams = exams.filter(course_id=course_id)
        exam_ids = list(exams.values_list("id", flat=True))

        attempts = ExamAttempt.objects.filter(exam_id__in=exam_ids)
        attempts = _apply_date_filter(attempts, "started_at", date_from, date_to)
        if group_students is not None:
            attempts = attempts.filter(user__in=group_students)

        attempt_stats = attempts.aggregate(
            total=Count("id"),
            submitted=Count("id", filter=Q(status="submitted")),
            expired=Count("id", filter=Q(status="expired")),
            checked=Count("id", filter=Q(checked_by_teacher=True)),
        )

    # Exam scores
    scored_attempts = list(
        attempts.filter(status__in=["submitted", "expired"]).values(
            "exam__course_id",
            "exam__exam_type",
            "exam__default_question_points",
            "correct_count",
            "wrong_count",
            "teacher_score",
        )
    )

    def _attempt_pct(a):
        if a["exam__exam_type"] == "written":
            return float(a["teacher_score"] or 0)
        total = (a["correct_count"] or 0) + (a["wrong_count"] or 0)
        return round((a["correct_count"] or 0) * 100 / total, 1) if total else 0

    exam_scores = [_attempt_pct(a) for a in scored_attempts]
    exam_avg = _safe_avg(exam_scores)
    exam_pass_count = sum(1 for s in exam_scores if s >= 50)
    exam_pass_rate = _safe_pct(exam_pass_count, len(exam_scores))

    # ── Assignments ───────────────────────────────────────────────
    assignment_subs = Submission.objects.none()
    assignment_stats = {
        "total": 0,
        "graded": 0,
        "late": 0,
    }
    if _content_type_enabled(content_type, "assignment"):
        assignments = Assignment.objects.filter(course_id__in=course_ids)
        assignment_subs = Submission.objects.filter(assignment__in=assignments)
        assignment_subs = _apply_date_filter(assignment_subs, "submitted_at", date_from, date_to)
        if group_students is not None:
            assignment_subs = assignment_subs.filter(user__in=group_students)
        assignment_stats = assignment_subs.aggregate(
            total=Count("id"),
            graded=Count("id", filter=Q(status="graded")),
            late=Count("id", filter=Q(is_late=True)),
        )

    # Grading turnaround (avg days between submitted_at and graded_at)
    graded_subs = assignment_subs.filter(status="graded", graded_at__isnull=False).values("submitted_at", "graded_at")
    turnaround_days = []
    for sub in graded_subs:
        if sub["submitted_at"] and sub["graded_at"]:
            delta = (sub["graded_at"] - sub["submitted_at"]).total_seconds() / 86400
            turnaround_days.append(delta)
    avg_turnaround = round(sum(turnaround_days) / len(turnaround_days), 1) if turnaround_days else 0

    # ── Labs ──────────────────────────────────────────────────────
    lab_subs = LabSubmission.objects.none()
    lab_stats = {
        "total": 0,
        "graded": 0,
    }
    if _content_type_enabled(content_type, "lab"):
        labs = Lab.objects.filter(course_id__in=course_ids)
        lab_subs = LabSubmission.objects.filter(assignment__lab__in=labs)
        lab_subs = _apply_date_filter(lab_subs, "submitted_at", date_from, date_to)
        if group_students is not None:
            lab_subs = lab_subs.filter(assignment__student__in=group_students)
        lab_stats = lab_subs.aggregate(
            total=Count("id"),
            graded=Count("id", filter=Q(status="graded")),
        )

    # ── Projects ──────────────────────────────────────────────────
    proj_subs = ProjectSubmission.objects.none()
    proj_stats = {
        "total": 0,
        "graded": 0,
    }
    if _content_type_enabled(content_type, "project"):
        projects = Project.objects.filter(course_id__in=course_ids)
        proj_subs = ProjectSubmission.objects.filter(project__in=projects)
        proj_subs = _apply_date_filter(proj_subs, "submitted_at", date_from, date_to)
        if group_students is not None:
            proj_subs = proj_subs.filter(student__in=group_students)
        proj_stats = proj_subs.aggregate(
            total=Count("id"),
            graded=Count("id", filter=Q(status="graded")),
        )

    # ── Group comparison ──────────────────────────────────────────
    groups_qs = StudentGroup.objects.none()
    if organization and _content_type_enabled(content_type, "exam"):
        # prefetch_related("students"): loop içində grp.students.all() hər qrup
        # üçün ayrı sorğu idi (N+1) — indi cache-dən.
        groups_qs = StudentGroup.objects.filter(organization=organization).prefetch_related("students")
    group_comparison = []
    for grp in groups_qs[:50]:
        grp_attempts = ExamAttempt.objects.filter(
            exam_id__in=exam_ids,
            user__in=grp.students.all(),
            status__in=["submitted", "expired"],
        )
        grp_attempts = _apply_date_filter(grp_attempts, "started_at", date_from, date_to)
        grp_scored = list(
            grp_attempts.values(
                "exam__exam_type",
                "exam__default_question_points",
                "correct_count",
                "wrong_count",
                "teacher_score",
            )
        )
        grp_scores = [_attempt_pct(a) for a in grp_scored]
        grp_avg = _safe_avg(grp_scores)
        group_comparison.append(
            {
                "id": grp.id,
                "name": grp.name,
                "student_count": grp.students.count(),
                "avg_score": grp_avg,
                "attempt_count": len(grp_scored),
                "pass_rate": _safe_pct(sum(1 for s in grp_scores if s >= 50), len(grp_scores)),
            }
        )

    # ── Course overview ───────────────────────────────────────────
    student_counts_by_course = dict(
        CourseMembership.objects.filter(course_id__in=course_ids, role="student")
        .values("course_id")
        .annotate(count=Count("user", distinct=True))
        .values_list("course_id", "count")
    )
    exam_counts_by_course = dict(
        exams.values("course_id").annotate(count=Count("id")).values_list("course_id", "count")
    )
    attempt_counts_by_course = dict(
        attempts.values("exam__course_id").annotate(count=Count("id")).values_list("exam__course_id", "count")
    )
    course_scores = defaultdict(list)
    for attempt in scored_attempts:
        course_scores[attempt["exam__course_id"]].append(_attempt_pct(attempt))

    course_overview = []
    for row in course_rows:
        scores = course_scores.get(row["id"], [])
        course_overview.append(
            {
                "course_id": row["id"],
                "title": row["title"],
                "student_count": student_counts_by_course.get(row["id"], 0),
                "exam_count": exam_counts_by_course.get(row["id"], 0),
                "attempt_count": attempt_counts_by_course.get(row["id"], 0),
                "avg_score": _safe_avg(scores),
                "pass_rate": _safe_pct(sum(1 for score in scores if score >= 50), len(scores)),
            }
        )
    course_overview.sort(key=lambda row: (-row["attempt_count"], row["title"].lower()))

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
        "course_overview": course_overview,
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
    content_type = filters.get("content_type", "all")

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
    active_courses = courses.filter(status="published").count()

    # course_ids = list(courses.values_list("id", flat=True))

    # ── Exams ─────────────────────────────────────────────────────
    exams = Exam.objects.none()
    attempts = ExamAttempt.objects.none()
    total_exams = 0
    attempt_agg = {"total": 0, "submitted": 0, "checked": 0}
    if _content_type_enabled(content_type, "exam"):
        exams = Exam.objects.filter(organization=organization)
        if course_id:
            exams = exams.filter(course_id=course_id)
        total_exams = exams.count()

        attempts = ExamAttempt.objects.filter(exam__in=exams)
        attempts = _apply_date_filter(attempts, "started_at", date_from, date_to)
        attempt_agg = attempts.aggregate(
            total=Count("id"),
            submitted=Count("id", filter=Q(status="submitted")),
            checked=Count("id", filter=Q(checked_by_teacher=True)),
        )

    # ── Assignments ───────────────────────────────────────────────
    assignment_subs = Submission.objects.none()
    asn_agg = {"total": 0, "graded": 0, "late": 0}
    if _content_type_enabled(content_type, "assignment"):
        assignment_subs = Submission.objects.filter(assignment__course__organization=organization)
        if course_id:
            assignment_subs = assignment_subs.filter(assignment__course_id=course_id)
        assignment_subs = _apply_date_filter(assignment_subs, "submitted_at", date_from, date_to)
        asn_agg = assignment_subs.aggregate(
            total=Count("id"),
            graded=Count("id", filter=Q(status="graded")),
            late=Count("id", filter=Q(is_late=True)),
        )

    # ── Labs ──────────────────────────────────────────────────────
    lab_subs = LabSubmission.objects.none()
    lab_agg = {"total": 0, "graded": 0}
    if _content_type_enabled(content_type, "lab"):
        lab_subs = LabSubmission.objects.filter(assignment__lab__course__organization=organization)
        if course_id:
            lab_subs = lab_subs.filter(assignment__lab__course_id=course_id)
        lab_subs = _apply_date_filter(lab_subs, "submitted_at", date_from, date_to)
        lab_agg = lab_subs.aggregate(
            total=Count("id"),
            graded=Count("id", filter=Q(status="graded")),
        )

    # ── Projects ──────────────────────────────────────────────────
    proj_subs = ProjectSubmission.objects.none()
    proj_agg = {"total": 0, "graded": 0}
    if _content_type_enabled(content_type, "project"):
        proj_subs = ProjectSubmission.objects.filter(project__course__organization=organization)
        if course_id:
            proj_subs = proj_subs.filter(project__course_id=course_id)
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

    # ── Course rankings / drill-down ──────────────────────────────
    course_memberships = CourseMembership.objects.filter(course__organization=organization, role="student")
    if course_id:
        course_memberships = course_memberships.filter(course_id=course_id)
    course_student_counts = dict(
        course_memberships.values("course_id")
        .annotate(student_count=Count("user", distinct=True))
        .values_list("course_id", "student_count")
    )
    course_exam_counts = dict(
        exams.values("course_id").annotate(exam_count=Count("id")).values_list("course_id", "exam_count")
    )
    course_attempt_counts = dict(
        attempts.values("exam__course_id")
        .annotate(attempt_count=Count("id"))
        .values_list("exam__course_id", "attempt_count")
    )
    course_assignment_counts = dict(
        assignment_subs.values("assignment__course_id")
        .annotate(assignment_total=Count("id"))
        .values_list("assignment__course_id", "assignment_total")
    )
    course_rankings = []
    for course in courses.select_related("owner").order_by("title"):
        owner_name = f"{course.owner.first_name} {course.owner.last_name}".strip() if course.owner_id else ""
        course_rankings.append(
            {
                "course__id": course.id,
                "course__title": course.title,
                "teacher_name": owner_name or getattr(course.owner, "username", ""),
                "student_count": course_student_counts.get(course.id, 0),
                "exam_count": course_exam_counts.get(course.id, 0),
                "attempt_count": course_attempt_counts.get(course.id, 0),
                "assignment_total": course_assignment_counts.get(course.id, 0),
            }
        )
    course_rankings.sort(key=lambda row: (-row["student_count"], row["course__title"].lower()))

    # ── Teacher overview ──────────────────────────────────────────
    teacher_user_ids = memberships.filter(role__level__gte=55).values_list("user_id", flat=True)
    teacher_course_counts = dict(
        Course.objects.filter(organization=organization, owner_id__in=teacher_user_ids)
        .values("owner_id")
        .annotate(course_count=Count("id"))
        .values_list("owner_id", "course_count")
    )
    teacher_student_counts = dict(
        CourseMembership.objects.filter(
            course__organization=organization, role="student", course__owner_id__in=teacher_user_ids
        )
        .values("course__owner_id")
        .annotate(student_count=Count("user", distinct=True))
        .values_list("course__owner_id", "student_count")
    )
    teacher_exam_counts = dict(
        exams.values("author_id").annotate(exam_count=Count("id")).values_list("author_id", "exam_count")
    )
    teacher_attempt_counts = dict(
        attempts.values("exam__author_id")
        .annotate(attempt_count=Count("id"))
        .values_list("exam__author_id", "attempt_count")
    )
    teacher_scores = defaultdict(list)
    for attempt in attempts.filter(status__in=["submitted", "expired"]).values(
        "exam__author_id",
        "exam__exam_type",
        "correct_count",
        "wrong_count",
        "teacher_score",
    ):
        total = (attempt["correct_count"] or 0) + (attempt["wrong_count"] or 0)
        score = (
            float(attempt["teacher_score"] or 0)
            if attempt["exam__exam_type"] == "written"
            else (round((attempt["correct_count"] or 0) * 100 / total, 1) if total else 0)
        )
        teacher_scores[attempt["exam__author_id"]].append(score)
    teacher_overview = []
    _teacher_ids = list(teacher_user_ids)[:20]
    # Əvvəl hər teacher üçün ayrıca User sorğusu idi (20-yə qədər N+1). İndi tək
    # id__in sorğusu + dict lookup.
    _users_by_id = {
        u["id"]: u for u in User.objects.filter(id__in=_teacher_ids).values("id", "username", "first_name", "last_name")
    }
    for tid in _teacher_ids:
        t_user = _users_by_id.get(tid)
        if t_user:
            teacher_overview.append(
                {
                    "user_id": tid,
                    "username": t_user["username"],
                    "name": f"{t_user['first_name']} {t_user['last_name']}".strip() or t_user["username"],
                    "exam_count": teacher_exam_counts.get(tid, 0),
                    "course_count": teacher_course_counts.get(tid, 0),
                    "student_count": teacher_student_counts.get(tid, 0),
                    "attempt_count": teacher_attempt_counts.get(tid, 0),
                    "avg_score": _safe_avg(teacher_scores.get(tid, [])),
                }
            )
    teacher_overview.sort(key=lambda row: (-row["attempt_count"], row["name"].lower()))

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
    course_id = filters.get("course")
    content_type = filters.get("content_type", "all")

    # ── Organizations ─────────────────────────────────────────────
    orgs = Organization.objects.filter(is_active=True, status="active")
    scoped_orgs = orgs.filter(id=org_id) if org_id else orgs
    total_orgs = scoped_orgs.count()

    # ── Users ─────────────────────────────────────────────────────
    total_memberships = Membership.objects.filter(is_active=True, organization__in=scoped_orgs).count()
    if org_id:
        total_users = (
            Membership.objects.filter(is_active=True, organization_id=org_id).values("user").distinct().count()
        )
    else:
        total_users = User.objects.filter(is_active=True).count()

    courses = Course.objects.all()
    if org_id:
        courses = courses.filter(organization_id=org_id)
    if course_id:
        courses = courses.filter(id=course_id)
    total_courses = courses.count()

    exam_qs = Exam.objects.all()
    if org_id:
        exam_qs = exam_qs.filter(organization_id=org_id)
    if course_id:
        exam_qs = exam_qs.filter(course_id=course_id)

    # ── Exams ─────────────────────────────────────────────────────
    attempts = ExamAttempt.objects.none()
    attempt_agg = {"total": 0, "submitted": 0, "checked": 0}
    total_exams = 0
    if _content_type_enabled(content_type, "exam"):
        attempts = ExamAttempt.objects.filter(exam__in=exam_qs)
        attempts = _apply_date_filter(attempts, "started_at", date_from, date_to)
        attempt_agg = attempts.aggregate(
            total=Count("id"),
            submitted=Count("id", filter=Q(status="submitted")),
            checked=Count("id", filter=Q(checked_by_teacher=True)),
        )
        total_exams = exam_qs.count()

    # ── Assignments ───────────────────────────────────────────────
    asn_qs = Submission.objects.none()
    asn_agg = {"total": 0, "graded": 0}
    if _content_type_enabled(content_type, "assignment"):
        asn_qs = Submission.objects.all()
        if org_id:
            asn_qs = asn_qs.filter(assignment__course__organization_id=org_id)
        if course_id:
            asn_qs = asn_qs.filter(assignment__course_id=course_id)
        asn_qs = _apply_date_filter(asn_qs, "submitted_at", date_from, date_to)
        asn_agg = asn_qs.aggregate(
            total=Count("id"),
            graded=Count("id", filter=Q(status="graded")),
        )

    # ── Labs + Projects ───────────────────────────────────────────
    lab_qs = LabSubmission.objects.none()
    lab_agg = {"total": 0, "graded": 0}
    if _content_type_enabled(content_type, "lab"):
        lab_qs = LabSubmission.objects.all()
        if org_id:
            lab_qs = lab_qs.filter(assignment__lab__course__organization_id=org_id)
        if course_id:
            lab_qs = lab_qs.filter(assignment__lab__course_id=course_id)
        lab_qs = _apply_date_filter(lab_qs, "submitted_at", date_from, date_to)
        lab_agg = lab_qs.aggregate(total=Count("id"), graded=Count("id", filter=Q(status="graded")))

    proj_qs = ProjectSubmission.objects.none()
    proj_agg = {"total": 0, "graded": 0}
    if _content_type_enabled(content_type, "project"):
        proj_qs = ProjectSubmission.objects.all()
        if org_id:
            proj_qs = proj_qs.filter(project__course__organization_id=org_id)
        if course_id:
            proj_qs = proj_qs.filter(project__course_id=course_id)
        proj_qs = _apply_date_filter(proj_qs, "submitted_at", date_from, date_to)
        proj_agg = proj_qs.aggregate(total=Count("id"), graded=Count("id", filter=Q(status="graded")))

    # ── Org comparison ────────────────────────────────────────────
    # Org comparison — əvvəl hər org üçün 6 ayrı sorğu idi (×60 org = ~360 sorğu, N+1).
    # İndi organization_id üzrə qruplaşmış 4 aqreqat (member/teacher/student tək
    # sorğuda filtered Count ilə; course/exam/attempt ayrıca qruplaşma).
    org_list = list(scoped_orgs[:60])
    org_ids = [o.id for o in org_list]

    _member_by_org = {
        row["organization_id"]: row
        for row in (
            Membership.objects.filter(organization_id__in=org_ids, is_active=True)
            .values("organization_id")
            .annotate(
                members=Count("user", distinct=True),
                teachers=Count("user", distinct=True, filter=Q(role__level__gte=55)),
                students=Count("user", distinct=True, filter=Q(role__level__lte=30)),
            )
        )
    }
    _courses_by_org = dict(
        Course.objects.filter(organization_id__in=org_ids)
        .values("organization_id")
        .annotate(c=Count("id"))
        .values_list("organization_id", "c")
    )
    _exams_by_org = dict(
        Exam.objects.filter(organization_id__in=org_ids)
        .values("organization_id")
        .annotate(c=Count("id"))
        .values_list("organization_id", "c")
    )
    _attempts_by_org = dict(
        ExamAttempt.objects.filter(exam__organization_id__in=org_ids)
        .values("exam__organization_id")
        .annotate(c=Count("id"))
        .values_list("exam__organization_id", "c")
    )

    org_comparison = []
    for org in org_list:
        m = _member_by_org.get(org.id) or {}
        org_comparison.append(
            {
                "id": org.id,
                "name": org.name,
                "org_type": org.org_type,
                "members": m.get("members", 0),
                "teachers": m.get("teachers", 0),
                "students": m.get("students", 0),
                "courses": _courses_by_org.get(org.id, 0),
                "exams": _exams_by_org.get(org.id, 0),
                "attempts": _attempts_by_org.get(org.id, 0),
            }
        )
    org_comparison.sort(key=lambda row: (-row["attempts"], row["name"].lower()))

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
