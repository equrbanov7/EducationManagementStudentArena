"""
Evaluated-review collector for the teacher review-results section.
"""

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext_lazy

from apps.assignments.models import Submission
from apps.courses.models import Course
from apps.exams.models import Exam, ExamAttempt
from apps.labs.models import LabSubmission
from apps.projects.models import ProjectSubmission

from .._helpers import (
    REVIEW_EDIT_WINDOW,
    _append_query_params,
    _tenant_scoped_courses,
    _tenant_scoped_exams,
)
from .formatters import (
    _build_student_group_map_and_available,
    _format_score_display,
    _normalize_pending_review_type,
    _normalize_submission_date_order,
    _user_display_name,
)

User = get_user_model()


def _collect_evaluated_review_items(request, search=None, filter_type=None, filter_group=None, submitted_order=None):
    search_query = (search if search is not None else request.GET.get("evaluated_search", "")).strip()
    normalized_type = _normalize_pending_review_type(
        filter_type if filter_type is not None else request.GET.get("evaluated_type", "all")
    )
    selected_group = (filter_group if filter_group is not None else request.GET.get("evaluated_group", "")).strip()
    normalized_submitted_order = _normalize_submission_date_order(
        submitted_order if submitted_order is not None else request.GET.get("evaluated_submitted_order", "newest"),
        default="newest",
    )

    teacher_courses = _tenant_scoped_courses(request, Course.objects.filter(owner=request.user))
    teacher_exams = _tenant_scoped_exams(request, Exam.objects.filter(author=request.user))
    review_cutoff = timezone.now() - REVIEW_EDIT_WINDOW

    student_group_map, available_groups = _build_student_group_map_and_available(request.user)
    if selected_group and selected_group not in available_groups:
        selected_group = ""

    profile_return_url = _append_query_params(
        reverse("accounts:profile"),
        section="review-results",
        evaluated_search=search_query,
        evaluated_type=normalized_type,
        evaluated_group=selected_group,
        evaluated_submitted_order=normalized_submitted_order,
    )

    items = []

    if normalized_type in {"all", "exams"}:
        attempts = (
            ExamAttempt.objects.filter(
                exam__in=teacher_exams,
                status__in=["submitted", "expired"],
            )
            .filter(
                Q(exam__exam_type="test")
                | Q(checked_by_teacher=True, teacher_checked_at__isnull=True)
                | Q(checked_by_teacher=True, teacher_checked_at__lte=review_cutoff)
            )
            .select_related("exam", "user", "exam__author", "exam__course")
        )
        if search_query:
            attempts = attempts.filter(
                Q(user__username__icontains=search_query)
                | Q(user__first_name__icontains=search_query)
                | Q(user__last_name__icontains=search_query)
                | Q(exam__title__icontains=search_query)
                | Q(exam__course__title__icontains=search_query)
            )
        from apps.appeals.services import effective_test_score

        for attempt in attempts:
            course = attempt.exam.course
            submitted_at = attempt.finished_at or attempt.started_at
            # Test: apellyasiyadan SONRAKI effektiv balı bal olaraq göstər
            # (X / maks) + faiz; yazılı/praktiki: müəllim balı.
            if attempt.exam.exam_type == "test":
                eff = effective_test_score(attempt)
                score_display = "{} / {}".format(
                    _format_score_display(eff["effective_score"]),
                    _format_score_display(eff["max_score"]),
                )
                score_percent_display = "{}%".format(_format_score_display(eff["effective_percentage"]))
            else:
                score_value = attempt.teacher_score if attempt.teacher_score is not None else attempt.score_percent
                score_display = _format_score_display(score_value)
                score_percent_display = ""
            items.append(
                {
                    "type": "exam",
                    "student": attempt.user,
                    "title": attempt.exam.title,
                    "course_title": course.title if course else "-",
                    "group_name": student_group_map.get(attempt.user_id, ""),
                    "score_display": score_display,
                    "score_percent_display": score_percent_display,
                    "evaluator_display": _user_display_name(attempt.exam.author),
                    "submitted_at": submitted_at,
                    "reviewed_at": attempt.teacher_checked_at,
                    "action_url": _append_query_params(
                        reverse(
                            "exams:teacher_view_attempt",
                            kwargs={"slug": attempt.exam.slug, "attempt_id": attempt.id},
                        ),
                        from_section="review-results",
                        return_to=profile_return_url,
                    ),
                    "action_label": pgettext_lazy("profile.pending_review.action", "review"),
                }
            )

    if normalized_type in {"all", "assignments"}:
        submissions = (
            Submission.objects.filter(
                assignment__course__in=teacher_courses,
                status="graded",
            )
            .filter(Q(graded_at__isnull=True) | Q(graded_at__lte=review_cutoff))
            .select_related("assignment", "assignment__course", "user", "graded_by")
        )
        if search_query:
            submissions = submissions.filter(
                Q(user__username__icontains=search_query)
                | Q(user__first_name__icontains=search_query)
                | Q(user__last_name__icontains=search_query)
                | Q(assignment__title__icontains=search_query)
                | Q(assignment__course__title__icontains=search_query)
            )
        for submission in submissions:
            course = submission.assignment.course
            items.append(
                {
                    "type": "assignment",
                    "student": submission.user,
                    "title": submission.assignment.title,
                    "course_title": course.title if course else "-",
                    "group_name": student_group_map.get(submission.user_id, ""),
                    "score_display": _format_score_display(submission.grade),
                    "evaluator_display": _user_display_name(submission.graded_by) if submission.graded_by_id else "-",
                    "submitted_at": submission.submitted_at,
                    "reviewed_at": submission.graded_at,
                    "action_url": _append_query_params(
                        reverse(
                            "accounts:review_result_detail",
                            kwargs={"item_type": "assignment", "item_id": submission.id},
                        ),
                        return_to=profile_return_url,
                    ),
                    "action_label": pgettext_lazy("profile.pending_review.action", "open_assignment"),
                }
            )

    if normalized_type in {"all", "projects"}:
        project_submissions = (
            ProjectSubmission.objects.filter(
                project__course__in=teacher_courses,
                status="graded",
            )
            .filter(Q(graded_at__isnull=True) | Q(graded_at__lte=review_cutoff))
            .select_related("project", "project__course", "student", "graded_by")
        )
        if search_query:
            project_submissions = project_submissions.filter(
                Q(student__username__icontains=search_query)
                | Q(student__first_name__icontains=search_query)
                | Q(student__last_name__icontains=search_query)
                | Q(project__title__icontains=search_query)
                | Q(project__course__title__icontains=search_query)
            )
        for submission in project_submissions:
            course = submission.project.course
            items.append(
                {
                    "type": "project",
                    "student": submission.student,
                    "title": submission.project.title,
                    "course_title": course.title if course else "-",
                    "group_name": student_group_map.get(submission.student_id, ""),
                    "score_display": _format_score_display(submission.grade),
                    "evaluator_display": _user_display_name(submission.graded_by) if submission.graded_by_id else "-",
                    "submitted_at": submission.submitted_at,
                    "reviewed_at": submission.graded_at,
                    "action_url": _append_query_params(
                        reverse(
                            "accounts:review_result_detail",
                            kwargs={"item_type": "project", "item_id": submission.id},
                        ),
                        return_to=profile_return_url,
                    ),
                    "action_label": pgettext_lazy("profile.pending_review.action", "open_project"),
                }
            )

    if normalized_type in {"all", "labs"}:
        lab_submissions = (
            LabSubmission.objects.filter(
                assignment__lab__course__in=teacher_courses,
                status="graded",
            )
            .filter(Q(graded_at__isnull=True) | Q(graded_at__lte=review_cutoff))
            .select_related(
                "assignment",
                "assignment__lab",
                "assignment__lab__course",
                "assignment__student",
                "graded_by",
            )
        )
        if search_query:
            lab_submissions = lab_submissions.filter(
                Q(assignment__student__username__icontains=search_query)
                | Q(assignment__student__first_name__icontains=search_query)
                | Q(assignment__student__last_name__icontains=search_query)
                | Q(assignment__lab__title__icontains=search_query)
                | Q(assignment__lab__course__title__icontains=search_query)
            )
        for submission in lab_submissions:
            student = submission.assignment.student
            course = submission.assignment.lab.course
            items.append(
                {
                    "type": "lab",
                    "student": student,
                    "title": submission.assignment.lab.title,
                    "course_title": course.title if course else "-",
                    "group_name": student_group_map.get(student.id, ""),
                    "score_display": _format_score_display(submission.score),
                    "evaluator_display": _user_display_name(submission.graded_by) if submission.graded_by_id else "-",
                    "submitted_at": submission.submitted_at,
                    "reviewed_at": submission.graded_at,
                    "action_url": _append_query_params(
                        reverse(
                            "accounts:review_result_detail",
                            kwargs={"item_type": "lab", "item_id": submission.id},
                        ),
                        return_to=profile_return_url,
                    ),
                    "action_label": pgettext_lazy("profile.pending_review.action", "grade"),
                }
            )

    if selected_group:
        items = [item for item in items if item.get("group_name") == selected_group]

    items.sort(
        key=lambda item: (
            item["submitted_at"] is None,
            item["submitted_at"] or timezone.now(),
        ),
        reverse=normalized_submitted_order == "newest",
    )
    return items, search_query, normalized_type, selected_group, available_groups, normalized_submitted_order
