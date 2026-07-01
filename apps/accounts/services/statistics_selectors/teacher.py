"""statistics_selectors paketi — teacher."""

from __future__ import annotations

from collections import defaultdict

from django.db.models import Count, Q

from ._shared import (
    _apply_date_filter,
    _content_type_enabled,
    _parse_date,
    _safe_avg,
    _safe_pct,
)


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
