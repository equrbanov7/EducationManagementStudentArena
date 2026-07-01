"""statistics_selectors paketi — student."""

from __future__ import annotations

from collections import defaultdict

from ._shared import (
    _apply_date_filter,
    _parse_date,
    _safe_avg,
    _safe_pct,
)


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
    # (identified by nickname + client_id). Showing organization-level live
    # answers in the student dashboard leaks data outside the current student,
    # so student statistics intentionally keep these metrics empty.
    live_total = 0
    live_correct = 0

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
