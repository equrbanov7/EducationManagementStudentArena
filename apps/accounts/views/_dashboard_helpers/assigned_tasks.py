"""
Assigned-tasks collector for the profile dashboard.
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

    assigned_exams_qs = _assigned_exams_queryset(request, user, active_only=True).order_by(
        "-start_datetime", "-created_at"
    )
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
        .prefetch_related("allowed_students")
        .order_by("-created_at")
    )
    assigned_labs = []
    for lab in labs_qs:
        # Use .all() to hit the prefetch_related cache (values_list bypasses it).
        allowed_student_ids = {s.id for s in lab.allowed_students.all()}
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
