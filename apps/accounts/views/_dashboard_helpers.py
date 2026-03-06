"""
Helper functions for dashboard data collection.
"""

from decimal import Decimal, InvalidOperation
from pathlib import PurePosixPath

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext_lazy

from apps.assignments.models import Assignment, Submission
from apps.courses.models import Course
from apps.exams.models import Exam, ExamAttempt
from apps.labs.models import Lab, LabAnswer, LabSubmission
from apps.projects.models import Project, ProjectSubmission

from ._helpers import (
    ASSIGNED_TASK_FILTER_CHOICES,
    PENDING_ANSWER_FILTER_CHOICES,
    PENDING_REVIEW_STATUS_CHOICES,
    PENDING_REVIEW_TYPE_CHOICES,
    RESULT_FILTER_CHOICES,
    REVIEW_EDIT_WINDOW,
    _append_query_params,
    _assigned_courses_queryset,
    _assigned_exams_queryset,
    _csv_to_int_set,
    _csv_to_lower_token_set,
    _extract_assignment_attachments,
    _is_result_visible_to_student,
    _is_review_window_closed,
    _is_review_window_open,
    _normalize_pending_answers_filter,
    _normalize_results_filter,
    _parse_decimal_score,
    _pending_review_type_label,
    _result_status_badge,
    _review_window_seconds_left,
    _task_state_badge_data,
    _tenant_scoped_courses,
    _tenant_scoped_exams,
)

User = get_user_model()

def _standard_item_type_meta(raw_type):
    normalized = (raw_type or "").lower()
    mapping = {
        "courses": ("Kurs", "fas fa-graduation-cap"),
        "assignments": ("Sərbəst iş", "fas fa-file-signature"),
        "independent": ("Kurs işi", "fas fa-diagram-project"),
        "projects": ("Kurs işi", "fas fa-diagram-project"),
        "labs": ("Lab işi", "fas fa-flask"),
        "lab": ("Lab işi", "fas fa-flask"),
        "exams": ("İmtahan", "fas fa-file-alt"),
        "exam": ("İmtahan", "fas fa-file-alt"),
    }
    return mapping.get(normalized, ("Tapşırıq", "fas fa-file"))


def _collect_assigned_tasks(request, filter_type=None, search=None):
    """
    Build a unified assigned task list across exams, assignments, labs, and projects.
    """
    user = request.user
    selected_filter = filter_type if filter_type is not None else request.GET.get("assigned_type")
    filter_type = _normalize_assigned_tasks_filter(selected_filter)
    search_query = (search if search is not None else request.GET.get("assigned_search", "")).strip()
    search_token = search_query.lower()
    now = timezone.now()

    assigned_courses_qs = _assigned_courses_queryset(request, user).select_related("owner").order_by("-created_at")
    course_ids = list(assigned_courses_qs.values_list("id", flat=True))

    memberships = CourseMembership.objects.filter(
        course_id__in=course_ids,
        user=user,
        role="student",
    ).values_list("course_id", "group_name")
    course_groups = {}
    for course_id, group_name in memberships:
        normalized_group = (group_name or "").strip().lower()
        if not normalized_group:
            continue
        course_groups.setdefault(course_id, set()).add(normalized_group)

    items = []
    counts = {"exams": 0, "courses": 0, "assignments": 0, "labs": 0, "independent": 0}

    def matches_search(*values):
        if not search_token:
            return True
        for value in values:
            if search_token in (value or "").lower():
                return True
        return False

    def append_item(
        *,
        category,
        title,
        kind,
        icon,
        detail_url,
        assigned_at=None,
        deadline=None,
        state="open",
        description="",
        extra=None,
    ):
        state_label, state_badge = _task_state_badge_data(state)
        payload = {
            "category": category,
            "title": title,
            "kind": kind,
            "icon": icon,
            "type_label": _standard_item_type_meta(category)[0],
            "detail_url": detail_url,
            "assigned_at": assigned_at,
            "deadline": deadline,
            "state_label": state_label,
            "state_badge": state_badge,
            "description": description,
            "sort_at": assigned_at or deadline or now,
        }
        if extra:
            payload.update(extra)
        items.append(payload)

    counts["courses"] = assigned_courses_qs.count()

    assigned_exams_qs = _assigned_exams_queryset(request, user, active_only=True).order_by("-start_datetime", "-created_at")
    counts["exams"] = assigned_exams_qs.count()
    if filter_type in {"all", "exams"}:
        for exam in assigned_exams_qs:
            if not matches_search(
                exam.title,
                exam.description,
                exam.course.title if exam.course else "",
            ):
                continue

            if exam.start_datetime and now < exam.start_datetime:
                state = "upcoming"
            elif exam.end_datetime and now > exam.end_datetime:
                state = "closed"
            else:
                state = "open"

            append_item(
                category="exams",
                title=exam.title,
                kind=f"İmtahan - {exam.get_exam_type_display()}",
                icon=_standard_item_type_meta("exams")[1],
                detail_url=_append_query_params(
                    reverse("exams:start_exam", kwargs={"slug": exam.slug}),
                    from_section="assigned-exams",
                    assigned_type=filter_type,
                ),
                assigned_at=exam.start_datetime or exam.created_at,
                deadline=exam.end_datetime,
                state=state,
                description=exam.description,
                extra={
                    "exam_slug": exam.slug,
                    "exam_type_display": exam.get_exam_type_display(),
                    "exam_total_duration_minutes": exam.total_duration_minutes,
                    "exam_start_at": exam.start_datetime,
                    "exam_end_at": exam.end_datetime,
                    "exam_requires_code": bool(exam.access_code),
                },
            )

    assignments_qs = (
        Assignment.objects.filter(
            course_id__in=course_ids,
            assigned_students=user,
        )
        .exclude(status__in=["inactive", "archived"])
        .select_related("course")
        .distinct()
        .order_by("-created_at")
    )
    counts["assignments"] = assignments_qs.count()
    if filter_type in {"all", "assignments"}:
        for assignment in assignments_qs:
            if not matches_search(assignment.title, assignment.description, assignment.course.title):
                continue

            if assignment.start_date and assignment.start_date > now:
                state = "upcoming"
            elif assignment.due_date and now > assignment.due_date and not assignment.allow_late:
                state = "closed"
            elif assignment.status not in {"published", "active"}:
                state = "closed"
            else:
                state = "open"

            append_item(
                category="assignments",
                title=assignment.title,
                kind=f"Sərbəst İş • {assignment.course.title}",
                icon=_standard_item_type_meta("assignments")[1],
                detail_url=_append_query_params(
                    reverse("assignments:assignment_detail", kwargs={"pk": assignment.id}),
                    from_section="assigned-exams",
                    assigned_type=filter_type,
                ),
                assigned_at=assignment.start_date or assignment.created_at,
                deadline=assignment.due_date,
                state=state,
                description=assignment.description,
            )

    labs_qs = (
        Lab.objects.filter(course_id__in=course_ids, status="published")
        .select_related("course")
        .order_by("-created_at")
    )
    assigned_labs = []
    for lab in labs_qs:
        allowed_student_ids = _csv_to_int_set(lab.allowed_students)
        allowed_group_names = _csv_to_lower_token_set(lab.allowed_groups)
        if not allowed_student_ids and not allowed_group_names:
            continue

        is_assigned = user.id in allowed_student_ids
        if not is_assigned and allowed_group_names:
            student_groups = course_groups.get(lab.course_id, set())
            is_assigned = bool(student_groups.intersection(allowed_group_names))

        if is_assigned:
            assigned_labs.append(lab)

    counts["labs"] = len(assigned_labs)
    if filter_type in {"all", "labs"}:
        for lab in assigned_labs:
            if not matches_search(lab.title, lab.description, lab.course.title):
                continue

            if lab.start_datetime and now < lab.start_datetime:
                state = "upcoming"
            elif lab.end_datetime and now > lab.end_datetime and not lab.allow_late_submission:
                state = "closed"
            else:
                state = "open"

            append_item(
                category="labs",
                title=lab.title,
                kind=f"Lab işi • {lab.course.title}",
                icon=_standard_item_type_meta("labs")[1],
                detail_url=_append_query_params(
                    reverse("labs:lab_detail", kwargs={"pk": lab.id}),
                    from_section="assigned-exams",
                    assigned_type=filter_type,
                ),
                assigned_at=lab.start_datetime or lab.created_at,
                deadline=lab.end_datetime,
                state=state,
                description=lab.description,
            )

    projects_qs = (
        Project.objects.filter(
            course_id__in=course_ids,
            assigned_students=user,
        )
        .exclude(status="archived")
        .select_related("course")
        .distinct()
        .order_by("-created_at")
    )
    counts["independent"] = projects_qs.count()
    if filter_type in {"all", "independent"}:
        for project in projects_qs:
            if not matches_search(project.title, project.description, project.course.title):
                continue

            if project.start_date and project.start_date > now:
                state = "upcoming"
            elif project.deadline and now > project.deadline:
                state = "closed"
            elif project.status != "active":
                state = "closed"
            else:
                state = "open"

            append_item(
                category="independent",
                title=project.title,
                kind=f"Kurs işi • {project.course.title}",
                icon=_standard_item_type_meta("independent")[1],
                detail_url=_append_query_params(
                    reverse("projects:project_detail", kwargs={"pk": project.id}),
                    from_section="assigned-exams",
                    assigned_type=filter_type,
                ),
                assigned_at=project.start_date or project.created_at,
                deadline=project.deadline,
                state=state,
                description=project.description,
            )

    items.sort(key=lambda item: item["sort_at"] or now, reverse=True)
    for item in items:
        item.pop("sort_at", None)

    counts["all"] = counts["exams"] + counts["assignments"] + counts["labs"] + counts["independent"]
    return items, counts, filter_type


def _collect_my_results(request, filter_type=None):
    """
    Build a unified result list for current user across exams, assignments, labs, and projects.
    """
    user = request.user
    selected_filter = filter_type if filter_type is not None else request.GET.get("type")
    filter_type = _normalize_results_filter(selected_filter)
    now = timezone.now()
    review_cutoff = now - REVIEW_EDIT_WINDOW

    scoped_exams = _tenant_scoped_exams(request)
    scoped_courses = _tenant_scoped_courses(request)
    scoped_exam_ids = scoped_exams.values_list("id", flat=True)
    scoped_course_ids = scoped_courses.values_list("id", flat=True)

    items = []
    counts = {"exams": 0, "courses": 0, "labs": 0, "independent": 0}

    if filter_type in {"all", "exams"}:
        attempts = (
            ExamAttempt.objects.filter(
                user=user,
                exam_id__in=scoped_exam_ids,
                status__in=["submitted", "expired"],
            )
            .select_related("exam")
            .order_by("-started_at")
        )
        for attempt in attempts:
            is_auto_test = attempt.exam.exam_type == "test"
            if (
                not is_auto_test
                and attempt.checked_by_teacher
                and attempt.teacher_checked_at
                and not _is_result_visible_to_student(attempt.teacher_checked_at)
            ):
                continue

            score_value = attempt.teacher_score
            if score_value is None and is_auto_test and (attempt.correct_count + attempt.wrong_count) > 0:
                score_value = attempt.score_percent

            is_graded_visible = attempt.checked_by_teacher or score_value is not None
            items.append(
                {
                    "category": "exams",
                    "title": attempt.exam.title,
                    "kind": attempt.exam.get_exam_type_display() or pgettext_lazy("accounts.my_results.kind", "exam"),
                    "icon": _standard_item_type_meta("exams")[1],
                    "type_label": _standard_item_type_meta("exams")[0],
                    "submitted_at": attempt.finished_at or attempt.started_at,
                    "status": _result_status_badge(
                        attempt.status,
                        is_graded=is_graded_visible,
                    ),
                    "status_raw": attempt.get_status_display(),
                    "score": score_value if is_graded_visible else None,
                    "feedback": attempt.teacher_feedback if is_graded_visible else "",
                    "detail_url": reverse(
                        "exams:exam_result",
                        kwargs={"slug": attempt.exam.slug, "attempt_id": attempt.id},
                    ),
                }
            )
            counts["exams"] += 1

    if filter_type in {"all", "courses"}:
        assignment_submissions = (
            Submission.objects.filter(
                user=user,
                assignment__course_id__in=scoped_course_ids,
            )
            .select_related("assignment", "assignment__course")
            .order_by("-submitted_at")
        )
        for submission in assignment_submissions:
            if (
                submission.status == "graded"
                and submission.graded_at
                and not _is_result_visible_to_student(submission.graded_at)
            ):
                continue

            is_graded_visible = submission.status == "graded" and (
                not submission.graded_at or _is_result_visible_to_student(submission.graded_at)
            )
            items.append(
                {
                    "category": "courses",
                    "title": submission.assignment.title,
                    "kind": submission.assignment.course.title,
                    "icon": _standard_item_type_meta("assignments")[1],
                    "type_label": _standard_item_type_meta("assignments")[0],
                    "submitted_at": submission.submitted_at,
                    "status": _result_status_badge(submission.status, is_graded=is_graded_visible),
                    "status_raw": submission.get_status_display(),
                    "score": submission.grade if is_graded_visible else None,
                    "feedback": submission.feedback if is_graded_visible else "",
                    "detail_url": _append_query_params(
                        reverse(
                            "accounts:my_result_detail",
                            kwargs={"item_type": "courses", "item_id": submission.id},
                        ),
                        results_type=filter_type,
                    ),
                }
            )
            counts["courses"] += 1

    if filter_type in {"all", "labs"}:
        lab_submissions = (
            LabSubmission.objects.filter(
                assignment__student=user,
                assignment__lab__course_id__in=scoped_course_ids,
            )
            .select_related("assignment", "assignment__lab", "assignment__lab__course")
            .order_by("-submitted_at")
        )
        for submission in lab_submissions:
            if (
                submission.status == "graded"
                and submission.graded_at
                and not _is_result_visible_to_student(submission.graded_at)
            ):
                continue

            is_graded_visible = submission.status == "graded" and (
                not submission.graded_at or _is_result_visible_to_student(submission.graded_at)
            )
            items.append(
                {
                    "category": "labs",
                    "title": submission.assignment.lab.title,
                    "kind": submission.assignment.lab.course.title,
                    "icon": _standard_item_type_meta("labs")[1],
                    "type_label": _standard_item_type_meta("labs")[0],
                    "submitted_at": submission.submitted_at,
                    "status": _result_status_badge(submission.status, is_graded=is_graded_visible),
                    "status_raw": submission.get_status_display(),
                    "score": submission.score if is_graded_visible else None,
                    "feedback": submission.feedback if is_graded_visible else "",
                    "detail_url": _append_query_params(
                        reverse(
                            "accounts:my_result_detail",
                            kwargs={"item_type": "labs", "item_id": submission.id},
                        ),
                        results_type=filter_type,
                    ),
                }
            )
            counts["labs"] += 1

    if filter_type in {"all", "independent"}:
        project_submissions = (
            ProjectSubmission.objects.filter(
                student=user,
                project__course_id__in=scoped_course_ids,
            )
            .select_related("project", "project__course")
            .order_by("-submitted_at")
        )
        for submission in project_submissions:
            if (
                submission.status == "graded"
                and submission.graded_at
                and not _is_result_visible_to_student(submission.graded_at)
            ):
                continue

            is_graded_visible = submission.status == "graded" and (
                not submission.graded_at or _is_result_visible_to_student(submission.graded_at)
            )
            items.append(
                {
                    "category": "independent",
                    "title": submission.project.title,
                    "kind": submission.project.course.title,
                    "icon": _standard_item_type_meta("independent")[1],
                    "type_label": _standard_item_type_meta("independent")[0],
                    "submitted_at": submission.submitted_at,
                    "status": _result_status_badge(submission.status, is_graded=is_graded_visible),
                    "status_raw": submission.get_status_display(),
                    "score": submission.grade if is_graded_visible else None,
                    "feedback": submission.feedback if is_graded_visible else "",
                    "detail_url": _append_query_params(
                        reverse(
                            "accounts:my_result_detail",
                            kwargs={"item_type": "independent", "item_id": submission.id},
                        ),
                        results_type=filter_type,
                    ),
                }
            )
            counts["independent"] += 1

    items.sort(key=lambda item: item["submitted_at"] or now, reverse=True)
    if filter_type != "all":
        counts = {
            "exams": ExamAttempt.objects.filter(
                user=user,
                exam_id__in=scoped_exam_ids,
                status__in=["submitted", "expired"],
            )
            .filter(
                Q(exam__exam_type="test")
                | Q(checked_by_teacher=False)
                | Q(checked_by_teacher=True, teacher_checked_at__isnull=True)
                | Q(checked_by_teacher=True, teacher_checked_at__lte=review_cutoff)
            )
            .count(),
            "courses": Submission.objects.filter(
                user=user,
                assignment__course_id__in=scoped_course_ids,
            )
            .exclude(status="graded", graded_at__gt=review_cutoff)
            .count(),
            "labs": LabSubmission.objects.filter(
                assignment__student=user,
                assignment__lab__course_id__in=scoped_course_ids,
            )
            .exclude(status="graded", graded_at__gt=review_cutoff)
            .count(),
            "independent": ProjectSubmission.objects.filter(
                student=user,
                project__course_id__in=scoped_course_ids,
            )
            .exclude(status="graded", graded_at__gt=review_cutoff)
            .count(),
        }
    counts["all"] = counts["exams"] + counts["courses"] + counts["labs"] + counts["independent"]

    return items, counts, filter_type


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
    counts = {"exams": 0, "courses": 0, "labs": 0, "independent": 0}
    search_token = search_query.lower()

    def matches_search(*values):
        if not search_token:
            return True
        for value in values:
            if search_token in (value or "").lower():
                return True
        return False

    def add_item(*, category, title, kind, submitted_at, status_label, status_class, detail_url, countdown_seconds=0):
        counts[category] += 1
        if filter_type not in {"all", category}:
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


def _normalize_pending_review_type(value):
    normalized = (value or "all").lower()
    if normalized in PENDING_REVIEW_TYPE_CHOICES:
        return normalized
    return "all"


def _normalize_pending_review_status(value):
    normalized = (value or "all").lower()
    if normalized in PENDING_REVIEW_STATUS_CHOICES:
        return normalized
    return "all"


def _collect_pending_review_items(request, search=None, filter_type=None, filter_status=None):
    search_query = (search if search is not None else request.GET.get("search", "")).strip()
    normalized_type = _normalize_pending_review_type(
        filter_type if filter_type is not None else request.GET.get("type", "all")
    )
    normalized_status = _normalize_pending_review_status(
        filter_status if filter_status is not None else request.GET.get("status", "all")
    )
    profile_return_url = _append_query_params(
        reverse("accounts:profile"),
        section="pending-review",
        search=search_query,
        type=normalized_type,
        status=normalized_status,
    )

    teacher_courses = _tenant_scoped_courses(request, Course.objects.filter(owner=request.user))
    teacher_exams = _tenant_scoped_exams(request, Exam.objects.filter(author=request.user))
    review_cutoff = timezone.now() - REVIEW_EDIT_WINDOW

    student_memberships = []
    if teacher_courses.exists():
        student_memberships = CourseMembership.objects.filter(
            course__in=teacher_courses,
            role="student",
        ).values("course_id", "user_id", "group_name")

    group_map = {
        (membership["course_id"], membership["user_id"]): membership["group_name"] or ""
        for membership in student_memberships
    }
    anonymous_student_label = "Anonim tələbə"

    items = []

    if normalized_type in {"all", "exams"}:
        attempts = (
            ExamAttempt.objects.filter(
                exam__in=teacher_exams,
                status__in=["submitted", "expired"],
            )
            .filter(
                Q(checked_by_teacher=False)
                | Q(checked_by_teacher=True, teacher_checked_at__gte=review_cutoff)
            )
            .exclude(exam__exam_type="test")
            .select_related("exam", "user", "exam__course")
        )
        if search_query:
            attempts = attempts.filter(
                Q(exam__title__icontains=search_query)
                | Q(exam__course__title__icontains=search_query)
            )
        for attempt in attempts:
            course = attempt.exam.course
            review_window_seconds_left = _review_window_seconds_left(attempt.teacher_checked_at)
            items.append(
                {
                    "type": "exam",
                    "icon": _standard_item_type_meta("exam")[1],
                    "student": attempt.user,
                    "student_display": anonymous_student_label,
                    "title": attempt.exam.title,
                    "course_title": course.title if course else "-",
                    "group_name": group_map.get((course.id, attempt.user_id), "") if course else "",
                    "status": attempt.status,
                    "date": attempt.teacher_checked_at or attempt.started_at,
                    "type_label": _pending_review_type_label("exam"),
                    "is_recheck": bool(attempt.checked_by_teacher),
                    "review_window_seconds_left": review_window_seconds_left if attempt.checked_by_teacher else 0,
                    "action_url": _append_query_params(
                        reverse(
                            "exams:teacher_check_attempt",
                            kwargs={"slug": attempt.exam.slug, "attempt_id": attempt.id},
                        ),
                        from_section="pending-review",
                        return_to=profile_return_url,
                    ),
                    "action_label": pgettext_lazy("profile.pending_review.action", "review"),
                }
            )

    if normalized_type in {"all", "assignments"}:
        submissions = Submission.objects.filter(
            assignment__course__in=teacher_courses,
        ).filter(
            Q(status="submitted")
            | Q(status="graded", graded_at__gte=review_cutoff)
        ).select_related("assignment", "user", "assignment__course")
        if search_query:
            submissions = submissions.filter(
                Q(assignment__title__icontains=search_query)
                | Q(assignment__course__title__icontains=search_query)
            )
        for submission in submissions:
            course = submission.assignment.course
            is_recheck = submission.status == "graded"
            review_window_seconds_left = _review_window_seconds_left(submission.graded_at) if is_recheck else 0
            items.append(
                {
                    "type": "assignment",
                    "icon": _standard_item_type_meta("assignments")[1],
                    "student": submission.user,
                    "student_display": anonymous_student_label,
                    "title": submission.assignment.title,
                    "course_title": course.title,
                    "group_name": group_map.get((course.id, submission.user_id), ""),
                    "status": submission.status,
                    "date": submission.graded_at or submission.submitted_at,
                    "type_label": _pending_review_type_label("assignment"),
                    "is_recheck": is_recheck,
                    "review_window_seconds_left": review_window_seconds_left,
                    "action_url": _append_query_params(
                        reverse(
                            "accounts:pending_review_detail",
                            kwargs={"item_type": "assignment", "item_id": submission.id},
                        ),
                        return_to=profile_return_url,
                    ),
                    "action_label": pgettext_lazy("profile.pending_review.action", "open_assignment"),
                }
            )

    if normalized_type in {"all", "projects"}:
        project_submissions = ProjectSubmission.objects.filter(
            project__course__in=teacher_courses,
        ).filter(
            Q(status="pending")
            | Q(status="graded", graded_at__gte=review_cutoff)
        ).select_related("project", "project__course", "student")
        if search_query:
            project_submissions = project_submissions.filter(
                Q(project__title__icontains=search_query)
                | Q(project__course__title__icontains=search_query)
            )
        for submission in project_submissions:
            course = submission.project.course
            is_recheck = submission.status == "graded"
            review_window_seconds_left = _review_window_seconds_left(submission.graded_at) if is_recheck else 0
            items.append(
                {
                    "type": "project",
                    "icon": _standard_item_type_meta("projects")[1],
                    "student": submission.student,
                    "student_display": anonymous_student_label,
                    "title": submission.project.title,
                    "course_title": course.title,
                    "group_name": group_map.get((course.id, submission.student_id), ""),
                    "status": submission.status,
                    "date": submission.graded_at or submission.submitted_at,
                    "type_label": _pending_review_type_label("project"),
                    "is_recheck": is_recheck,
                    "review_window_seconds_left": review_window_seconds_left,
                    "action_url": _append_query_params(
                        reverse(
                            "accounts:pending_review_detail",
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
            )
            .filter(
                Q(status__in=["submitted", "late"])
                | Q(status="graded", graded_at__gte=review_cutoff)
            )
            .select_related("assignment", "assignment__lab", "assignment__lab__course", "assignment__student")
        )
        if search_query:
            lab_submissions = lab_submissions.filter(
                Q(assignment__lab__title__icontains=search_query)
                | Q(assignment__lab__course__title__icontains=search_query)
            )
        for submission in lab_submissions:
            student = submission.assignment.student
            course = submission.assignment.lab.course
            is_recheck = submission.status == "graded"
            review_window_seconds_left = _review_window_seconds_left(submission.graded_at) if is_recheck else 0
            items.append(
                {
                    "type": "lab",
                    "icon": _standard_item_type_meta("lab")[1],
                    "student": student,
                    "student_display": anonymous_student_label,
                    "title": submission.assignment.lab.title,
                    "course_title": course.title,
                    "group_name": group_map.get((course.id, student.id), ""),
                    "status": submission.status,
                    "date": submission.graded_at or submission.submitted_at,
                    "type_label": _pending_review_type_label("lab"),
                    "is_recheck": is_recheck,
                    "review_window_seconds_left": review_window_seconds_left,
                    "action_url": _append_query_params(
                        reverse(
                            "accounts:pending_review_detail",
                            kwargs={"item_type": "lab", "item_id": submission.id},
                        ),
                        return_to=profile_return_url,
                    ),
                    "action_label": pgettext_lazy("profile.pending_review.action", "grade"),
                }
            )

    if normalized_status != "all":
        items = [item for item in items if item["status"] == normalized_status]

    items.sort(key=lambda item: (item["date"] is not None, item["date"] or timezone.now()), reverse=True)
    return items, search_query, normalized_type, normalized_status


def _collect_evaluated_review_items(request, search=None, filter_type=None, filter_group=None):
    search_query = (search if search is not None else request.GET.get("evaluated_search", "")).strip()
    normalized_type = _normalize_pending_review_type(
        filter_type if filter_type is not None else request.GET.get("evaluated_type", "all")
    )
    selected_group = (filter_group if filter_group is not None else request.GET.get("evaluated_group", "")).strip()

    teacher_courses = _tenant_scoped_courses(request, Course.objects.filter(owner=request.user))
    teacher_exams = _tenant_scoped_exams(request, Exam.objects.filter(author=request.user))
    review_cutoff = timezone.now() - REVIEW_EDIT_WINDOW

    student_memberships = []
    if teacher_courses.exists():
        student_memberships = CourseMembership.objects.filter(
            course__in=teacher_courses,
            role="student",
        ).values("course_id", "user_id", "group_name")

    group_map = {
        (membership["course_id"], membership["user_id"]): membership["group_name"] or ""
        for membership in student_memberships
    }
    available_groups = sorted(
        {
            membership["group_name"].strip()
            for membership in student_memberships
            if (membership.get("group_name") or "").strip()
        },
        key=str.lower,
    )
    if selected_group and selected_group not in available_groups:
        selected_group = ""

    profile_return_url = _append_query_params(
        reverse("accounts:profile"),
        section="review-results",
        evaluated_search=search_query,
        evaluated_type=normalized_type,
        evaluated_group=selected_group,
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
            .select_related("exam", "user", "exam__course")
        )
        if search_query:
            attempts = attempts.filter(
                Q(user__username__icontains=search_query)
                | Q(user__first_name__icontains=search_query)
                | Q(user__last_name__icontains=search_query)
                | Q(exam__title__icontains=search_query)
                | Q(exam__course__title__icontains=search_query)
            )
        for attempt in attempts:
            course = attempt.exam.course
            score_value = attempt.teacher_score if attempt.teacher_score is not None else attempt.score_percent
            items.append(
                {
                    "type": "exam",
                    "student": attempt.user,
                    "title": attempt.exam.title,
                    "course_title": course.title if course else "-",
                    "group_name": group_map.get((course.id, attempt.user_id), "") if course else "",
                    "score_display": f"{score_value}%" if score_value is not None else "-",
                    "date": attempt.teacher_checked_at or attempt.finished_at or attempt.started_at,
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
            .select_related("assignment", "assignment__course", "user")
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
                    "group_name": group_map.get((course.id, submission.user_id), "") if course else "",
                    "score_display": submission.grade if submission.grade is not None else "-",
                    "date": submission.graded_at or submission.submitted_at,
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
            .select_related("project", "project__course", "student")
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
                    "group_name": group_map.get((course.id, submission.student_id), "") if course else "",
                    "score_display": submission.grade if submission.grade is not None else "-",
                    "date": submission.graded_at or submission.submitted_at,
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
            .select_related("assignment", "assignment__lab", "assignment__lab__course", "assignment__student")
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
                    "group_name": group_map.get((course.id, student.id), "") if course else "",
                    "score_display": submission.score if submission.score is not None else "-",
                    "date": submission.graded_at or submission.submitted_at,
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

    items.sort(key=lambda item: (item["date"] is not None, item["date"] or timezone.now()), reverse=True)
    return items, search_query, normalized_type, selected_group, available_groups


