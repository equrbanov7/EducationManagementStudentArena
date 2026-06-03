"""
Cheap sidebar/badge counters (P2.A).

P1 introduced section-gating which deferred the heavy `_collect_*` calls until
the corresponding profile section was active. As a side-effect the sidebar
badges for `assigned_tasks_count`, `my_results_count` and `pending_answers_count`
became inaccurate or zero on the profile-info page.

This module computes those badges via a small number of cheap `COUNT(*)`
queries that mirror the *include rules* (but not the ordering, search,
formatting or detail context) of the heavy collectors.

Tenancy: every queryset is scoped via `_tenant_scoped_*`, identical to the
heavy collectors. RLS behaviour is unchanged.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

from apps.assignments.models import Assignment, Submission
from apps.courses.models import CourseMembership
from apps.exams.models import ExamAttempt
from apps.labs.models import Lab, LabSubmission
from apps.projects.models import Project, ProjectSubmission

from .._helpers import (
    REVIEW_EDIT_WINDOW,
    _assigned_exams_queryset,
    _csv_to_lower_token_set,
    _tenant_scoped_courses,
    _tenant_scoped_exams,
)

User = get_user_model()


def count_assigned_tasks(request, user) -> int:
    """
    Cheap aggregate matching `_collect_assigned_tasks` membership filters
    (exams + assignments + labs + projects) but without ordering, formatting
    or per-item context. Lab counting still requires a small Python pass
    because `Lab.allowed_groups` is stored as CSV.
    """
    # Exams (tenant-scoped, active_only=True, includes group/course-based).
    exam_count = _assigned_exams_queryset(request, user, active_only=True).values("id").distinct().count()

    # Courses the user is enrolled in — required for assignments/labs/projects.
    assigned_courses_qs = _tenant_scoped_courses(request)
    course_ids = list(
        assigned_courses_qs.filter(
            memberships__user=user,
            memberships__role="student",
            status="published",
        )
        .values_list("id", flat=True)
        .distinct()
    )

    if not course_ids:
        # Even without courses, exams may still be allowed_users/allowed_groups based.
        return exam_count

    assignment_count = (
        Assignment.objects.filter(
            course_id__in=course_ids,
            assigned_students=user,
        )
        .exclude(status__in=["inactive", "archived"])
        .values("id")
        .distinct()
        .count()
    )

    project_count = (
        Project.objects.filter(
            course_id__in=course_ids,
            assigned_students=user,
        )
        .exclude(status="archived")
        .values("id")
        .distinct()
        .count()
    )

    # Labs need a small Python pass because allowed_groups is CSV.
    lab_count = 0
    labs_qs = (
        Lab.objects.filter(course_id__in=course_ids, status="published")
        .only("id", "course_id", "allowed_groups")
        .prefetch_related("allowed_students")
    )
    # Pre-compute the user's per-course group memberships once.
    memberships = CourseMembership.objects.filter(course_id__in=course_ids, user=user, role="student").values_list(
        "course_id", "group_name"
    )
    course_groups: dict[int, set[str]] = {}
    for course_id, group_name in memberships:
        normalized = (group_name or "").strip().lower()
        if not normalized:
            continue
        course_groups.setdefault(course_id, set()).add(normalized)

    for lab in labs_qs:
        allowed_student_ids = {s.id for s in lab.allowed_students.all()}
        allowed_group_names = _csv_to_lower_token_set(lab.allowed_groups)
        if not allowed_student_ids and not allowed_group_names:
            continue
        if user.id in allowed_student_ids:
            lab_count += 1
            continue
        if allowed_group_names and course_groups.get(lab.course_id, set()).intersection(allowed_group_names):
            lab_count += 1

    return exam_count + assignment_count + lab_count + project_count


def count_my_results(request, user) -> int:
    """
    Cheap aggregate matching `_collect_my_results` *all* filter:
    counts submitted/expired exam attempts (with results not hidden) plus
    graded/in-review-window assignment/lab/project submissions.

    Mirrors the logic in `_collect_my_results` for `filter_type != "all"`
    which already used pure count() queries — we apply it for the badge
    even when no specific filter is active.
    """
    now = timezone.now()
    review_cutoff = now - REVIEW_EDIT_WINDOW

    scoped_exam_ids = _tenant_scoped_exams(request).values_list("id", flat=True)
    scoped_course_ids = _tenant_scoped_courses(request).values_list("id", flat=True)

    exams = (
        ExamAttempt.objects.filter(
            user=user,
            exam_id__in=scoped_exam_ids,
            exam__results_hidden_from_students=False,
            status__in=["submitted", "expired"],
        )
        .filter(
            Q(exam__exam_type="test")
            | Q(checked_by_teacher=False)
            | Q(checked_by_teacher=True, teacher_checked_at__isnull=True)
            | Q(checked_by_teacher=True, teacher_checked_at__lte=review_cutoff)
        )
        .count()
    )

    courses = (
        Submission.objects.filter(user=user, assignment__course_id__in=scoped_course_ids)
        .exclude(status="graded", graded_at__gt=review_cutoff)
        .count()
    )

    labs = (
        LabSubmission.objects.filter(assignment__student=user, assignment__lab__course_id__in=scoped_course_ids)
        .exclude(status="graded", graded_at__gt=review_cutoff)
        .count()
    )

    independent = (
        ProjectSubmission.objects.filter(student=user, project__course_id__in=scoped_course_ids)
        .exclude(status="graded", graded_at__gt=review_cutoff)
        .count()
    )

    return exams + courses + labs + independent


def count_pending_answers(request, user) -> int:
    """
    Cheap aggregate matching `_collect_pending_answer_items`:
    pending = not yet graded OR graded but still inside review window.
    Excludes exam_type="test" (auto-graded) just like the heavy collector.
    """
    now = timezone.now()
    review_cutoff = now - REVIEW_EDIT_WINDOW

    scoped_exam_ids = _tenant_scoped_exams(request).values_list("id", flat=True)
    scoped_course_ids = _tenant_scoped_courses(request).values_list("id", flat=True)

    exams = (
        ExamAttempt.objects.filter(
            user=user,
            exam_id__in=scoped_exam_ids,
            status__in=["submitted", "expired"],
        )
        .exclude(exam__exam_type="test")
        .filter(Q(checked_by_teacher=False) | Q(checked_by_teacher=True, teacher_checked_at__gt=review_cutoff))
        .count()
    )

    courses = (
        Submission.objects.filter(user=user, assignment__course_id__in=scoped_course_ids)
        .filter(~Q(status="graded") | Q(status="graded", graded_at__gt=review_cutoff))
        .count()
    )

    labs = (
        LabSubmission.objects.filter(assignment__student=user, assignment__lab__course_id__in=scoped_course_ids)
        .filter(~Q(status="graded") | Q(status="graded", graded_at__gt=review_cutoff))
        .count()
    )

    independent = (
        ProjectSubmission.objects.filter(student=user, project__course_id__in=scoped_course_ids)
        .filter(~Q(status="graded") | Q(status="graded", graded_at__gt=review_cutoff))
        .count()
    )

    return exams + courses + labs + independent


__all__ = [
    "count_assigned_tasks",
    "count_my_results",
    "count_pending_answers",
]
