"""
Pending-review collector for the teacher review section.
"""

from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext_lazy

from apps.assignments.models import Assignment, Submission
from apps.courses.models import Course, CourseMembership
from apps.exams.domain.access_policy import StudentGroup
from apps.exams.models import Exam, ExamAttempt
from apps.exams.services.result_calculation import calculate_test_attempt_result
from apps.exams.services.review_visibility import (
    resolve_exam_attempt_name_visibility,
    resolve_exam_attempt_review_window_seconds,
)
from apps.labs.models import Lab, LabSubmission
from apps.projects.models import Project, ProjectSubmission
from apps.task_submission_core.review import resolve_identity_window as resolve_submission_identity_window
from apps.task_submission_core.review import resolve_recheck_window as resolve_submission_recheck_window

from .._helpers import (
    PENDING_REVIEW_STATUS_CHOICES,
    PENDING_REVIEW_TYPE_CHOICES,
    REVIEW_EDIT_WINDOW,
    _append_query_params,
    _assigned_courses_queryset,
    _assigned_exams_queryset,
    _csv_to_lower_token_set,
    _is_result_visible_to_student,
    _normalize_assigned_tasks_filter,
    _normalize_pending_answers_filter,
    _normalize_results_filter,
    _pending_review_type_label,
    _result_status_badge,
    _review_window_seconds_left,
    _task_state_badge_data,
    _tenant_scoped_courses,
    _tenant_scoped_exams,
)
from .formatters import (
    _build_student_group_map_and_available,
    _format_score_display,
    _normalize_pending_review_status,
    _normalize_pending_review_type,
    _normalize_submission_date_order,
    _resolve_teacher_review_action,
    _standard_item_type_meta,
    _user_display_name,
)

User = get_user_model()


def _collect_pending_review_items(
    request, search=None, filter_type=None, filter_status=None, submitted_order=None, filter_group=None
):
    search_query = (search if search is not None else request.GET.get("search", "")).strip()
    normalized_type = _normalize_pending_review_type(
        filter_type if filter_type is not None else request.GET.get("type", "all")
    )
    normalized_status = _normalize_pending_review_status(
        filter_status if filter_status is not None else request.GET.get("status", "all")
    )
    selected_group = (filter_group if filter_group is not None else request.GET.get("pr_group", "")).strip()
    normalized_submitted_order = _normalize_submission_date_order(
        submitted_order if submitted_order is not None else request.GET.get("submitted_order", "oldest"),
        default="oldest",
    )

    student_group_map, available_groups = _build_student_group_map_and_available(request.user)
    if selected_group and selected_group not in available_groups:
        selected_group = ""

    profile_return_url = _append_query_params(
        reverse("accounts:profile"),
        section="pending-review",
        search=search_query,
        type=normalized_type,
        status=normalized_status,
        pr_group=selected_group,
        submitted_order=normalized_submitted_order,
        pr_page=(request.GET.get("pr_page") or request.GET.get("page") or "").strip(),
    )

    teacher_courses = _tenant_scoped_courses(request, Course.objects.filter(owner=request.user))
    teacher_exams = _tenant_scoped_exams(request, Exam.objects.filter(author=request.user))
    current_time = timezone.now()
    review_cutoff = current_time - REVIEW_EDIT_WINDOW

    items = []

    if normalized_type in {"all", "exams"}:
        attempts = (
            ExamAttempt.objects.filter(
                exam__in=teacher_exams,
                status__in=["submitted", "expired"],
            )
            .filter(Q(checked_by_teacher=False) | Q(checked_by_teacher=True, teacher_checked_at__gte=review_cutoff))
            .exclude(exam__exam_type="test")
            .select_related("exam", "user", "exam__author", "exam__course")
        )
        if search_query:
            attempts = attempts.filter(
                Q(exam__title__icontains=search_query) | Q(exam__course__title__icontains=search_query)
            )
        for attempt in attempts:
            course = attempt.exam.course
            can_view_student_identity, identity_window_seconds_left = resolve_exam_attempt_name_visibility(
                attempt,
                current_time=current_time,
            )
            review_window_seconds_left = resolve_exam_attempt_review_window_seconds(
                attempt,
                current_time=current_time,
            )
            is_recheck = bool(attempt.checked_by_teacher and review_window_seconds_left > 0)
            student_display = (
                attempt.user.get_full_name() or attempt.user.username if can_view_student_identity else "Anonim tələbə"
            )
            submitted_at = attempt.finished_at or attempt.started_at
            items.append(
                {
                    "type": "exam",
                    "icon": _standard_item_type_meta("exam")[1],
                    "student": attempt.user,
                    "student_display": student_display,
                    "creator_display": _user_display_name(attempt.exam.author),
                    "title": attempt.exam.title,
                    "course_title": course.title if course else "-",
                    "group_name": student_group_map.get(attempt.user_id, ""),
                    "status": attempt.status,
                    "submitted_at": submitted_at,
                    "reviewed_at": attempt.teacher_checked_at,
                    "type_label": _pending_review_type_label("exam", exam_type=attempt.exam.exam_type),
                    "is_recheck": is_recheck,
                    "review_window_seconds_left": review_window_seconds_left,
                    "can_view_student_identity": can_view_student_identity,
                    "countdown_mode": (
                        "recheck"
                        if is_recheck
                        else ("identity" if (not can_view_student_identity and identity_window_seconds_left) else "")
                    ),
                    "action_url": _append_query_params(
                        reverse(
                            "exams:teacher_check_attempt",
                            kwargs={"slug": attempt.exam.slug, "attempt_id": attempt.id},
                        ),
                        from_section="pending-review",
                        return_to=profile_return_url,
                    ),
                    "action_label": _resolve_teacher_review_action(
                        is_graded=bool(attempt.checked_by_teacher),
                        in_recheck_window=is_recheck,
                    ),
                }
            )

    if normalized_type in {"all", "assignments"}:
        submissions = (
            Submission.objects.filter(
                assignment__course__in=teacher_courses,
            )
            .filter(Q(status="submitted") | Q(status="graded", graded_at__gte=review_cutoff))
            .select_related("assignment", "user", "assignment__course", "assignment__course__organization")
        )
        if search_query:
            submissions = submissions.filter(
                Q(assignment__title__icontains=search_query) | Q(assignment__course__title__icontains=search_query)
            )
        for submission in submissions:
            course = submission.assignment.course
            is_recheck, review_window_seconds_left = resolve_submission_recheck_window(
                submission,
                current_time=current_time,
            )
            is_identity_hidden, identity_window_seconds_left = resolve_submission_identity_window(
                submission,
                current_time=current_time,
            )
            items.append(
                {
                    "type": "assignment",
                    "icon": _standard_item_type_meta("assignments")[1],
                    "student": submission.user,
                    "student_display": (
                        "Anonim tələbə"
                        if is_identity_hidden
                        else (submission.user.get_full_name() or submission.user.username)
                    ),
                    "title": submission.assignment.title,
                    "course_title": course.title,
                    "group_name": student_group_map.get(submission.user_id, ""),
                    "status": submission.status,
                    "submitted_at": submission.submitted_at,
                    "reviewed_at": submission.graded_at,
                    "type_label": _pending_review_type_label("assignment"),
                    "is_recheck": is_recheck,
                    "review_window_seconds_left": review_window_seconds_left,
                    "can_view_student_identity": not is_identity_hidden,
                    "countdown_mode": (
                        "recheck" if is_recheck else ("identity" if identity_window_seconds_left > 0 else "")
                    ),
                    "action_url": _append_query_params(
                        reverse(
                            "accounts:pending_review_detail",
                            kwargs={"item_type": "assignment", "item_id": submission.id},
                        ),
                        return_to=profile_return_url,
                    ),
                    "action_label": _resolve_teacher_review_action(
                        is_graded=submission.status == "graded",
                        in_recheck_window=is_recheck,
                    ),
                }
            )

    if normalized_type in {"all", "projects"}:
        project_submissions = (
            ProjectSubmission.objects.filter(
                project__course__in=teacher_courses,
            )
            .filter(Q(status="pending") | Q(status="graded", graded_at__gte=review_cutoff))
            .select_related("project", "project__course", "project__course__organization", "student")
        )
        if search_query:
            project_submissions = project_submissions.filter(
                Q(project__title__icontains=search_query) | Q(project__course__title__icontains=search_query)
            )
        for submission in project_submissions:
            course = submission.project.course
            is_recheck, review_window_seconds_left = resolve_submission_recheck_window(
                submission,
                current_time=current_time,
            )
            is_identity_hidden, identity_window_seconds_left = resolve_submission_identity_window(
                submission,
                current_time=current_time,
            )
            items.append(
                {
                    "type": "project",
                    "icon": _standard_item_type_meta("projects")[1],
                    "student": submission.student,
                    "student_display": (
                        "Anonim tələbə"
                        if is_identity_hidden
                        else (submission.student.get_full_name() or submission.student.username)
                    ),
                    "title": submission.project.title,
                    "course_title": course.title,
                    "group_name": student_group_map.get(submission.student_id, ""),
                    "status": submission.status,
                    "submitted_at": submission.submitted_at,
                    "reviewed_at": submission.graded_at,
                    "type_label": _pending_review_type_label("project"),
                    "is_recheck": is_recheck,
                    "review_window_seconds_left": review_window_seconds_left,
                    "can_view_student_identity": not is_identity_hidden,
                    "countdown_mode": (
                        "recheck" if is_recheck else ("identity" if identity_window_seconds_left > 0 else "")
                    ),
                    "action_url": _append_query_params(
                        reverse(
                            "accounts:pending_review_detail",
                            kwargs={"item_type": "project", "item_id": submission.id},
                        ),
                        return_to=profile_return_url,
                    ),
                    "action_label": _resolve_teacher_review_action(
                        is_graded=submission.status == "graded",
                        in_recheck_window=is_recheck,
                    ),
                }
            )

    if normalized_type in {"all", "labs"}:
        lab_submissions = (
            LabSubmission.objects.filter(
                assignment__lab__course__in=teacher_courses,
            )
            .filter(Q(status__in=["submitted", "late"]) | Q(status="graded", graded_at__gte=review_cutoff))
            .select_related(
                "assignment",
                "assignment__lab",
                "assignment__lab__course",
                "assignment__lab__course__organization",
                "assignment__student",
            )
        )
        if search_query:
            lab_submissions = lab_submissions.filter(
                Q(assignment__lab__title__icontains=search_query)
                | Q(assignment__lab__course__title__icontains=search_query)
            )
        for submission in lab_submissions:
            student = submission.assignment.student
            course = submission.assignment.lab.course
            is_recheck, review_window_seconds_left = resolve_submission_recheck_window(
                submission,
                current_time=current_time,
            )
            is_identity_hidden, identity_window_seconds_left = resolve_submission_identity_window(
                submission,
                current_time=current_time,
            )
            items.append(
                {
                    "type": "lab",
                    "icon": _standard_item_type_meta("lab")[1],
                    "student": student,
                    "student_display": (
                        "Anonim tələbə" if is_identity_hidden else (student.get_full_name() or student.username)
                    ),
                    "title": submission.assignment.lab.title,
                    "course_title": course.title,
                    "group_name": student_group_map.get(student.id, ""),
                    "status": submission.status,
                    "submitted_at": submission.submitted_at,
                    "reviewed_at": submission.graded_at,
                    "type_label": _pending_review_type_label("lab"),
                    "is_recheck": is_recheck,
                    "review_window_seconds_left": review_window_seconds_left,
                    "can_view_student_identity": not is_identity_hidden,
                    "countdown_mode": (
                        "recheck" if is_recheck else ("identity" if identity_window_seconds_left > 0 else "")
                    ),
                    "action_url": _append_query_params(
                        reverse(
                            "accounts:pending_review_detail",
                            kwargs={"item_type": "lab", "item_id": submission.id},
                        ),
                        return_to=profile_return_url,
                    ),
                    "action_label": _resolve_teacher_review_action(
                        is_graded=submission.status == "graded",
                        in_recheck_window=is_recheck,
                    ),
                }
            )

    if normalized_status != "all":
        items = [item for item in items if item["status"] == normalized_status]

    if selected_group:
        items = [item for item in items if item.get("group_name") == selected_group]

    items.sort(
        key=lambda item: (
            item["submitted_at"] is None,
            item["submitted_at"] or timezone.now(),
        ),
        reverse=normalized_submitted_order == "newest",
    )
    return (
        items,
        search_query,
        normalized_type,
        normalized_status,
        normalized_submitted_order,
        selected_group,
        available_groups,
    )
