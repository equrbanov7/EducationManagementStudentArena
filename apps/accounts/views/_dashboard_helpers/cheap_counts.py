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
from django.db.models import Count, F, IntegerField, OuterRef, Q, Subquery
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.assignments.models import Assignment, Submission
from apps.courses.models import CourseMembership
from apps.exams.models import ExamAttempt, StudentExamAttemptGrant
from apps.labs.models import Lab, LabSubmission
from apps.projects.models import Project, ProjectSubmission

from .._helpers import (
    REVIEW_EDIT_WINDOW,
    _assigned_exams_queryset,
    _csv_to_lower_token_set,
    _tenant_scoped_courses,
    _tenant_scoped_exams,
)
from .academic_results import count_academic_items

User = get_user_model()

FINISHED_ATTEMPT_STATUSES = ("submitted", "expired")


def _count_assigned_exams(request, user) -> int:
    """
    Cheap exam count matching `_collect_assigned_tasks`.

    Completed exams whose result is already visible move to "My results", so they
    must not keep the "Assigned tasks" sidebar badge alive.
    """
    now = timezone.now()
    review_cutoff = now - REVIEW_EDIT_WINDOW

    finished_sq = Subquery(
        ExamAttempt.objects.filter(
            exam=OuterRef("pk"),
            user=user,
            status__in=FINISHED_ATTEMPT_STATUSES,
        )
        .values("exam")
        .annotate(cnt=Count("id"))
        .values("cnt"),
        output_field=IntegerField(),
    )
    grant_sq = Subquery(
        StudentExamAttemptGrant.objects.filter(exam=OuterRef("pk"), student=user).values("extra_attempts")[:1],
        output_field=IntegerField(),
    )
    visible_result_sq = Subquery(
        ExamAttempt.objects.filter(
            exam=OuterRef("pk"),
            user=user,
            status__in=FINISHED_ATTEMPT_STATUSES,
            exam__results_hidden_from_students=False,
        )
        .filter(Q(exam__exam_type="test") | Q(checked_by_teacher=True, teacher_checked_at__lte=review_cutoff))
        .values("exam")
        .annotate(cnt=Count("id"))
        .values("cnt"),
        output_field=IntegerField(),
    )

    return (
        _assigned_exams_queryset(request, user, active_only=True)
        .annotate(
            _finished_attempts=Coalesce(finished_sq, 0),
            _extra_grant=Coalesce(grant_sq, 0),
            _visible_result_attempts=Coalesce(visible_result_sq, 0),
        )
        # Siyahı ilə eyni: nəticə görünsə də tələbənin cəhd haqqı (qrant) varsa say.
        .filter(
            Q(_visible_result_attempts=0)
            | Q(max_attempts_per_user__gt=0, _finished_attempts__lt=F("max_attempts_per_user") + F("_extra_grant"))
        )
        .filter(
            Q(max_attempts_per_user__isnull=True)
            | Q(max_attempts_per_user=0)
            | Q(_finished_attempts__lt=F("max_attempts_per_user") + F("_extra_grant"))
        )
        .values("id")
        .distinct()
        .count()
    )


def count_assigned_tasks(request, user) -> int:
    """
    Cheap aggregate matching `_collect_assigned_tasks` membership filters
    (exams + assignments + labs + projects) but without ordering, formatting
    or per-item context. Lab counting still requires a small Python pass
    because `Lab.allowed_groups` is stored as CSV.
    """
    # Exams (tenant-scoped, active_only=True, includes group/course-based).
    exam_count = _count_assigned_exams(request, user)

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
    graded/in-review-window assignment/lab/project submissions **plus** the
    registrar's academic (journal) subject results.

    Mirrors the logic in `_collect_my_results` for `filter_type != "all"`
    which already used pure count() queries — we apply it for the badge
    even when no specific filter is active. The academic term is a single
    `COUNT(*)` over the same enrollment set the heavy builder walks
    (`transcript.student_record_enrollments`), so the badge can never drift
    from the tab.
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

    academic = count_academic_items(request)

    return exams + courses + labs + independent + academic


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


def count_applications_pending(request, user) -> int:
    """«Müraciətlərim» badge-i — emalçıya gələn açıqlar / göndərənə məlumat sorğusu.

    Məntiq ``apps.applications.public.pending_badge_count``-dadır (iki COUNT
    sorğusu); burada yalnız aktiv təşkilat konteksti həll olunur. Modul
    sərhədi: yalnız public fasad çağırılır.
    """
    from apps.accounts.views._helpers.tenant import _get_active_organization
    from apps.applications.public import pending_badge_count

    organization = _get_active_organization(request)
    if organization is None:
        return 0
    return pending_badge_count(user, organization)


def compute_review_badge_counts(*, my_exams_qs, teacher_courses) -> tuple[int, int]:
    """Reviewer sidebar badges: (pending_review, evaluated_review).

    P2.B logic — collapses 8 separate COUNT(*) calls into 4 aggregate queries
    (one per content type, each returning pending + evaluated in a single pass).
    Extracted verbatim from ``user_profile`` so the result can be cached.
    """
    review_cutoff = timezone.now() - REVIEW_EDIT_WINDOW

    exam_attempt_counts = ExamAttempt.objects.filter(
        exam__in=my_exams_qs,
        status__in=["submitted", "expired"],
    ).aggregate(
        pending=Count(
            "id",
            filter=(
                ~Q(exam__exam_type="test")
                & (Q(checked_by_teacher=False) | Q(checked_by_teacher=True, teacher_checked_at__gte=review_cutoff))
            ),
        ),
        evaluated=Count(
            "id",
            filter=(
                Q(exam__exam_type="test")
                | Q(checked_by_teacher=True, teacher_checked_at__isnull=True)
                | Q(checked_by_teacher=True, teacher_checked_at__lte=review_cutoff)
            ),
        ),
    )

    submission_counts = Submission.objects.filter(assignment__course__in=teacher_courses).aggregate(
        pending=Count(
            "id",
            filter=(Q(status="submitted") | Q(status="graded", graded_at__gte=review_cutoff)),
        ),
        evaluated=Count(
            "id",
            filter=Q(status="graded") & (Q(graded_at__isnull=True) | Q(graded_at__lte=review_cutoff)),
        ),
    )

    project_counts = ProjectSubmission.objects.filter(project__course__in=teacher_courses).aggregate(
        pending=Count(
            "id",
            filter=(Q(status="pending") | Q(status="graded", graded_at__gte=review_cutoff)),
        ),
        evaluated=Count(
            "id",
            filter=Q(status="graded") & (Q(graded_at__isnull=True) | Q(graded_at__lte=review_cutoff)),
        ),
    )

    lab_counts = LabSubmission.objects.filter(assignment__lab__course__in=teacher_courses).aggregate(
        pending=Count(
            "id",
            filter=(Q(status__in=["submitted", "late"]) | Q(status="graded", graded_at__gte=review_cutoff)),
        ),
        evaluated=Count(
            "id",
            filter=Q(status="graded") & (Q(graded_at__isnull=True) | Q(graded_at__lte=review_cutoff)),
        ),
    )

    pending = (
        (exam_attempt_counts.get("pending") or 0)
        + (submission_counts.get("pending") or 0)
        + (project_counts.get("pending") or 0)
        + (lab_counts.get("pending") or 0)
    )
    evaluated = (
        (exam_attempt_counts.get("evaluated") or 0)
        + (submission_counts.get("evaluated") or 0)
        + (project_counts.get("evaluated") or 0)
        + (lab_counts.get("evaluated") or 0)
    )
    return pending, evaluated


def compute_profile_badge_counts(request, user, *, capabilities, my_exams_qs, teacher_courses) -> dict[str, int]:
    """Compute the full set of profile sidebar badge counts for *user*.

    Returns a flat ``{badge_name: int}`` dict. Only the badges the user's
    capabilities permit are populated; missing keys default to 0 at the call
    site. Designed to be wrapped by
    ``core.cache.get_or_set_cached_profile_badge_counts`` so the whole bundle is
    computed once per (user, org) and reused across loads / section swaps.
    """
    badges: dict[str, int] = {}
    if "applications" in capabilities.get("allowed_sections", set()):
        badges["applications_pending"] = count_applications_pending(request, user)
    if capabilities.get("can_view_student_assignments"):
        badges["assigned_tasks"] = count_assigned_tasks(request, user)
        badges["my_results"] = count_my_results(request, user)
        badges["pending_answers"] = count_pending_answers(request, user)
    if capabilities.get("can_review_submissions"):
        pending_review, evaluated_review = compute_review_badge_counts(
            my_exams_qs=my_exams_qs,
            teacher_courses=teacher_courses,
        )
        badges["pending_review"] = pending_review
        badges["evaluated_review"] = evaluated_review
    return badges


__all__ = [
    "compute_profile_badge_counts",
    "count_applications_pending",
    "compute_review_badge_counts",
    "count_assigned_tasks",
    "count_my_results",
    "count_pending_answers",
]
