"""
Pending-answers collector for the profile dashboard.
"""

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.assignments.models import Submission
from apps.exams.models import ExamAttempt
from apps.labs.models import LabSubmission
from apps.projects.models import ProjectSubmission

from .._helpers import (
    _append_query_params,
    _is_result_visible_to_student,
    _normalize_pending_answers_filter,
    _review_window_seconds_left,
    _tenant_scoped_courses,
    _tenant_scoped_exams,
)
from .formatters import _standard_item_type_meta

User = get_user_model()


def _collect_pending_answer_items(request, search=None, filter_type=None):
    """Build pending-answer list for students (not yet visible final results)."""
    user = request.user
    search_query = (search if search is not None else request.GET.get("pending_search", "")).strip()
    selected_filter = filter_type if filter_type is not None else request.GET.get("pending_type")
    filter_type = _normalize_pending_answers_filter(selected_filter)

    now = timezone.now()
    scoped_exams = _tenant_scoped_exams(request)
    scoped_courses = _tenant_scoped_courses(request)
    scoped_exam_ids = scoped_exams.values_list("id", flat=True)
    scoped_course_ids = scoped_courses.values_list("id", flat=True)

    items = []
    counts = {
        "exams": 0,
        "written_exams": 0,
        "practical_exams": 0,
        "courses": 0,
        "labs": 0,
        "independent": 0,
    }
    search_token = search_query.lower()

    def matches_search(*values):
        if not search_token:
            return True
        for value in values:
            if search_token in (value or "").lower():
                return True
        return False

    def add_item(
        *,
        category,
        title,
        kind,
        submitted_at,
        status_label,
        status_class,
        detail_url,
        countdown_seconds=0,
        filter_aliases=(),
    ):
        counts[category] += 1
        for alias in filter_aliases:
            counts[alias] += 1
        if filter_type not in {"all", category, *filter_aliases}:
            return
        items.append(
            {
                "category": category,
                "title": title,
                "kind": kind,
                "icon": _standard_item_type_meta(category)[1],
                "type_label": _standard_item_type_meta(category)[0],
                "submitted_at": submitted_at,
                "status_label": status_label,
                "status_class": status_class,
                "detail_url": detail_url,
                "review_window_seconds_left": max(0, int(countdown_seconds or 0)),
            }
        )

    attempts = (
        ExamAttempt.objects.filter(
            user=user,
            exam_id__in=scoped_exam_ids,
            status__in=["submitted", "expired"],
        )
        .exclude(exam__exam_type="test")
        .select_related("exam", "exam__course")
        .order_by("-finished_at", "-started_at")
    )
    for attempt in attempts:
        in_recheck_window = (
            attempt.checked_by_teacher
            and attempt.teacher_checked_at
            and not _is_result_visible_to_student(attempt.teacher_checked_at)
        )
        is_pending = not attempt.checked_by_teacher or in_recheck_window
        if not is_pending:
            continue
        course_title = attempt.exam.course.title if attempt.exam.course else ""
        if not matches_search(attempt.exam.title, course_title):
            continue
        if in_recheck_window:
            status_label = "Yoxlanır"
            status_class = "reviewing"
            countdown_seconds = _review_window_seconds_left(attempt.teacher_checked_at)
        else:
            status_label = "Gözləmədə"
            status_class = "pending"
            countdown_seconds = 0
        filter_alias = "practical_exams" if attempt.exam.exam_type == "coding" else "written_exams"
        add_item(
            category="exams",
            title=attempt.exam.title,
            kind=(attempt.exam.get_exam_type_display() or "Yazılı imtahan"),
            submitted_at=attempt.finished_at or attempt.started_at,
            status_label=status_label,
            status_class=status_class,
            detail_url=_append_query_params(
                reverse("accounts:my_result_detail", kwargs={"item_type": "exams", "item_id": attempt.id}),
                section="pending-answers",
                pending_type=filter_type,
                pending_search=search_query,
            ),
            countdown_seconds=countdown_seconds,
            filter_aliases=(filter_alias,),
        )

    assignment_submissions = (
        Submission.objects.filter(
            user=user,
            assignment__course_id__in=scoped_course_ids,
        )
        .select_related("assignment", "assignment__course")
        .order_by("-submitted_at")
    )
    for submission in assignment_submissions:
        in_recheck_window = (
            submission.status == "graded"
            and submission.graded_at
            and not _is_result_visible_to_student(submission.graded_at)
        )
        is_pending = submission.status != "graded" or in_recheck_window
        if not is_pending:
            continue
        if not matches_search(submission.assignment.title, submission.assignment.course.title):
            continue
        status_label = "Yoxlanır" if in_recheck_window else "Gözləmədə"
        status_class = "reviewing" if in_recheck_window else "pending"
        add_item(
            category="courses",
            title=submission.assignment.title,
            kind=submission.assignment.course.title,
            submitted_at=submission.submitted_at,
            status_label=status_label,
            status_class=status_class,
            detail_url=_append_query_params(
                reverse("accounts:my_result_detail", kwargs={"item_type": "courses", "item_id": submission.id}),
                section="pending-answers",
                pending_type=filter_type,
                pending_search=search_query,
            ),
            countdown_seconds=_review_window_seconds_left(submission.graded_at) if in_recheck_window else 0,
        )

    lab_submissions = (
        LabSubmission.objects.filter(
            assignment__student=user,
            assignment__lab__course_id__in=scoped_course_ids,
        )
        .select_related("assignment", "assignment__lab", "assignment__lab__course")
        .order_by("-submitted_at")
    )
    for submission in lab_submissions:
        in_recheck_window = (
            submission.status == "graded"
            and submission.graded_at
            and not _is_result_visible_to_student(submission.graded_at)
        )
        is_pending = submission.status != "graded" or in_recheck_window
        if not is_pending:
            continue
        if not matches_search(submission.assignment.lab.title, submission.assignment.lab.course.title):
            continue
        status_label = "Yoxlanır" if in_recheck_window else "Gözləmədə"
        status_class = "reviewing" if in_recheck_window else "pending"
        add_item(
            category="labs",
            title=submission.assignment.lab.title,
            kind=submission.assignment.lab.course.title,
            submitted_at=submission.submitted_at,
            status_label=status_label,
            status_class=status_class,
            detail_url=_append_query_params(
                reverse("accounts:my_result_detail", kwargs={"item_type": "labs", "item_id": submission.id}),
                section="pending-answers",
                pending_type=filter_type,
                pending_search=search_query,
            ),
            countdown_seconds=_review_window_seconds_left(submission.graded_at) if in_recheck_window else 0,
        )

    project_submissions = (
        ProjectSubmission.objects.filter(
            student=user,
            project__course_id__in=scoped_course_ids,
        )
        .select_related("project", "project__course")
        .order_by("-submitted_at")
    )
    for submission in project_submissions:
        in_recheck_window = (
            submission.status == "graded"
            and submission.graded_at
            and not _is_result_visible_to_student(submission.graded_at)
        )
        is_pending = submission.status != "graded" or in_recheck_window
        if not is_pending:
            continue
        if not matches_search(submission.project.title, submission.project.course.title):
            continue
        status_label = "Yoxlanır" if in_recheck_window else "Gözləmədə"
        status_class = "reviewing" if in_recheck_window else "pending"
        add_item(
            category="independent",
            title=submission.project.title,
            kind=submission.project.course.title,
            submitted_at=submission.submitted_at,
            status_label=status_label,
            status_class=status_class,
            detail_url=_append_query_params(
                reverse("accounts:my_result_detail", kwargs={"item_type": "independent", "item_id": submission.id}),
                section="pending-answers",
                pending_type=filter_type,
                pending_search=search_query,
            ),
            countdown_seconds=_review_window_seconds_left(submission.graded_at) if in_recheck_window else 0,
        )

    items.sort(key=lambda item: item["submitted_at"] or now, reverse=True)
    counts["all"] = counts["exams"] + counts["courses"] + counts["labs"] + counts["independent"]
    return items, counts, filter_type, search_query
