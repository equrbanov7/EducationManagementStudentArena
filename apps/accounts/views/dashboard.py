"""
Dashboard views: teacher/student dashboards, grading queue, results, and review management.
"""

from decimal import Decimal, InvalidOperation
from pathlib import PurePosixPath

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext_lazy

from apps.assignments.models import Assignment, Submission
from apps.courses.models import Course
from apps.exams.models import Exam, ExamAttempt
from apps.labs.models import Lab, LabAnswer, LabSubmission
from apps.projects.models import Project, ProjectSubmission

from ._dashboard_helpers import (
    _collect_assigned_tasks,
    _collect_evaluated_review_items,
    _collect_my_results,
    _collect_pending_answer_items,
    _collect_pending_review_items,
    _resolve_teacher_identity_window,
)
from ._helpers import (
    REVIEW_EDIT_WINDOW,
    REVIEW_EDIT_WINDOW_MINUTES,
    _append_query_params,
    _assigned_courses_queryset,
    _assigned_exams_queryset,
    _extract_assignment_attachments,
    _get_active_organization,
    _is_result_visible_to_student,
    _is_review_window_closed,
    _is_superadmin_user,
    _normalize_assigned_tasks_filter,
    _normalize_pending_answers_filter,
    _normalize_pending_review_status,
    _normalize_pending_review_type,
    _normalize_results_filter,
    _normalize_review_result_item_type,
    _parse_decimal_score,
    _pending_review_type_label,
    _result_status_badge,
    _review_window_seconds_left,
    _role_capabilities,
    _safe_same_origin_redirect_path,
    _tenant_scoped_courses,
    _tenant_scoped_exams,
    _user_has_any_role,
)

from ..models import ProfileRole

User = get_user_model()


def _resolve_pending_review_identity(*, student, submitted_at, graded_at, is_recheck, now=None):
    is_hidden, seconds_left = _resolve_teacher_identity_window(
        submitted_at=submitted_at,
        reviewed_at=graded_at,
        is_reviewed=is_recheck,
        now=now,
    )
    student_display = "Anonim tələbə" if is_hidden else (student.get_full_name() or student.username)
    return student_display, is_hidden, seconds_left


def _format_decimal_input(value):
    if value is None or value == "":
        return ""
    formatted = format(Decimal(str(value)), "f")
    if "." in formatted:
        formatted = formatted.rstrip("0").rstrip(".")
    return formatted or "0"


@login_required
def dashboard(request):
    """Redirect users to the dashboard variant that matches their role."""
    profile = getattr(request.user, "profile", None)
    capabilities = _role_capabilities(request.user, profile)
    if capabilities["can_review_submissions"]:
        return redirect("accounts:teacher_dashboard")
    return redirect("accounts:student_dashboard")


@login_required
def teacher_dashboard(request):
    """
    Teacher dashboard with widgets showing courses, pending grading, and stats.
    """
    profile = getattr(request.user, "profile", None)
    capabilities = _role_capabilities(request.user, profile)
    if not capabilities["can_review_submissions"]:
        messages.error(request, pgettext_lazy("accounts.grading_queue.message", "teacher_only"))
        return redirect("home")

    teacher_courses = _tenant_scoped_courses(request, Course.objects.filter(owner=request.user))

    # Get teacher's courses
    my_courses = teacher_courses.filter(status="published")[:5]

    # Get pending submissions
    pending_submissions = Submission.objects.filter(
        assignment__course__in=teacher_courses, status="submitted"
    ).select_related("assignment", "user")[:10]

    # Get upcoming exams
    upcoming_exams = _tenant_scoped_exams(
        request,
        Exam.objects.filter(
            author=request.user,
            is_active=True,
            start_datetime__gte=timezone.now(),
        ),
    ).order_by("start_datetime")[:5]

    # Calculate stats
    total_courses = teacher_courses.count()
    total_students = teacher_courses.aggregate(count=Count("memberships__user", distinct=True)).get("count", 0)
    pending_count = Submission.objects.filter(assignment__course__in=teacher_courses, status="submitted").count()

    # Students at risk (failing grades or missing submissions)
    at_risk_students = []
    for course in teacher_courses:
        # Find students with low grades or missing submissions
        submissions = (
            Submission.objects.filter(assignment__course=course, status="graded", grade__lt=50)
            .values_list("user_id", flat=True)
            .distinct()
        )
        at_risk_students.extend(User.objects.filter(id__in=submissions).values("id", "username")[:3])

    context = {
        "my_courses": my_courses,
        "pending_submissions": pending_submissions,
        "upcoming_exams": upcoming_exams,
        "total_courses": total_courses,
        "total_students": total_students,
        "pending_count": pending_count,
        "at_risk_students": at_risk_students[:5],
    }

    return render(request, "accounts/teacher_dashboard.html", context)


@login_required
def student_dashboard(request):
    """
    Student dashboard with enrolled courses, assignments, and upcoming exams.
    """
    # Get enrolled courses
    enrolled_courses = _assigned_courses_queryset(request, request.user)[:6]

    # Get pending assignments
    pending_assignments = Assignment.objects.filter(
        course__in=enrolled_courses,
        assigned_students=request.user,
        due_date__gte=timezone.now(),
        status__in=["published", "active"],
    ).distinct().order_by("due_date")[:5]

    # Get upcoming exams
    upcoming_exams = (
        _assigned_exams_queryset(request, request.user, active_only=True)
        .filter(start_datetime__gte=timezone.now())
        .order_by("start_datetime")[:5]
    )

    # Get recent grades
    recent_grades = Submission.objects.filter(user=request.user, status="graded").order_by("-graded_at")[:5]

    context = {
        "enrolled_courses": enrolled_courses,
        "pending_assignments": pending_assignments,
        "upcoming_exams": upcoming_exams,
        "recent_grades": recent_grades,
    }

    return render(request, "accounts/student_dashboard.html", context)


@login_required
def grading_queue(request):
    """
    Grading queue for teachers showing all pending submissions.
    """
    profile = getattr(request.user, "profile", None)
    capabilities = _role_capabilities(request.user, profile)
    if not capabilities["can_review_submissions"]:
        messages.error(request, pgettext_lazy("accounts.grading_queue.message", "teacher_only"))
        return redirect("home")

    # Get filter parameters
    course_id = request.GET.get("course")
    assignment_id = request.GET.get("assignment")

    teacher_courses = _tenant_scoped_courses(request, Course.objects.filter(owner=request.user))

    def _format_average_grading_time(seconds):
        if not seconds:
            return "0m"

        minutes = int(round(seconds / 60))
        hours, remaining_minutes = divmod(minutes, 60)
        if hours:
            return f"{hours}h {remaining_minutes}m"
        return f"{remaining_minutes}m"

    # Base query
    submissions = Submission.objects.filter(
        assignment__course__in=teacher_courses,
        status="submitted",
    ).select_related("assignment", "user", "assignment__course")

    assignments = Assignment.objects.filter(course__in=teacher_courses).select_related("course").order_by("title")
    if course_id:
        assignments = assignments.filter(course_id=course_id)

    # Apply filters
    if course_id:
        submissions = submissions.filter(assignment__course_id=course_id)
    if assignment_id:
        submissions = submissions.filter(assignment_id=assignment_id)

    # Order by oldest first
    submissions = submissions.order_by("submitted_at")

    graded_submissions = Submission.objects.filter(
        assignment__course__in=teacher_courses,
        status="graded",
        graded_at__isnull=False,
    )
    if course_id:
        graded_submissions = graded_submissions.filter(assignment__course_id=course_id)
    if assignment_id:
        graded_submissions = graded_submissions.filter(assignment_id=assignment_id)

    grading_durations = [
        max(0, (submission.graded_at - submission.submitted_at).total_seconds())
        for submission in graded_submissions.only("submitted_at", "graded_at")[:100]
        if submission.graded_at and submission.submitted_at
    ]

    context = {
        "submissions": submissions,
        "courses": teacher_courses,
        "assignments": assignments,
        "selected_course": course_id,
        "selected_assignment": assignment_id,
        "total_pending": submissions.count(),
        "graded_today": graded_submissions.filter(graded_at__date=timezone.localdate()).count(),
        "avg_grading_time": _format_average_grading_time(
            (sum(grading_durations) / len(grading_durations)) if grading_durations else 0
        ),
    }

    return render(request, "accounts/grading_queue.html", context)


@login_required
def assigned_exams(request):
    """Assigned exams list for the current user."""
    profile = getattr(request.user, "profile", None)
    capabilities = _role_capabilities(request.user, profile)
    if not capabilities["can_view_student_assignments"]:
        messages.error(request, pgettext_lazy("accounts.student_assignments.message", "student_or_member_only"))
        return redirect("accounts:profile")

    exams = _assigned_exams_queryset(request, request.user, active_only=True).order_by("-start_datetime", "-created_at")

    search = request.GET.get("search", "")
    if search:
        exams = exams.filter(Q(title__icontains=search) | Q(description__icontains=search))

    exam_items = []
    for exam in exams:
        can_start_without_code, _ = exam.can_user_start(request.user, code=None)
        exam_items.append(
            {
                "exam": exam,
                "requires_code": bool(exam.access_code and not can_start_without_code),
            }
        )

    context = {
        "exam_items": exam_items,
        "search_query": search,
    }
    return render(request, "accounts/assigned_exams.html", context)


@login_required
def assigned_courses(request):
    """Assigned courses list for the current user."""
    profile = getattr(request.user, "profile", None)
    capabilities = _role_capabilities(request.user, profile)
    if not capabilities["can_view_student_assignments"]:
        messages.error(request, pgettext_lazy("accounts.student_assignments.message", "student_or_member_only"))
        return redirect("accounts:profile")

    courses = _assigned_courses_queryset(request, request.user).order_by("-created_at")

    search = request.GET.get("search", "")
    if search:
        courses = courses.filter(Q(title__icontains=search) | Q(description__icontains=search))

    context = {
        "courses": courses,
        "search_query": search,
    }
    return render(request, "accounts/assigned_courses.html", context)


@login_required
def my_results(request):
    """Unified submission/result list for students and member-level users."""
    profile = getattr(request.user, "profile", None)
    capabilities = _role_capabilities(request.user, profile)
    if not capabilities["can_view_student_assignments"]:
        messages.error(request, pgettext_lazy("accounts.student_assignments.message", "student_or_member_only"))
        return redirect("accounts:profile")

    items, counts, active_filter = _collect_my_results(request, filter_type=request.GET.get("type"))
    context = {
        "items": items,
        "counts": counts,
        "active_filter": active_filter,
    }
    return render(request, "accounts/my_results.html", context)


@login_required
def pending_answers(request):
    """Pending (not yet finalized) answer list for students."""
    profile = getattr(request.user, "profile", None)
    capabilities = _role_capabilities(request.user, profile)
    if not capabilities["can_view_student_assignments"]:
        messages.error(request, pgettext_lazy("accounts.student_assignments.message", "student_or_member_only"))
        return redirect("accounts:profile")

    pending_search = request.GET.get("pending_search")
    if pending_search is None:
        pending_search = request.GET.get("search")
    pending_type = request.GET.get("pending_type")
    if pending_type is None:
        pending_type = request.GET.get("type")

    items, counts, active_filter, search_query = _collect_pending_answer_items(
        request,
        search=pending_search,
        filter_type=pending_type,
    )
    context = {
        "pending_answer_items": items,
        "pending_answer_counts": counts,
        "pending_answers_active_filter": active_filter,
        "pending_answers_search_query": search_query,
        "pending_answers_total_count": counts.get("all", 0),
    }
    return render(request, "accounts/pending_answers.html", context)


@login_required
def my_result_detail(request, item_type, item_id):
    """Detail page for a single item from My Results."""
    profile = getattr(request.user, "profile", None)
    capabilities = _role_capabilities(request.user, profile)
    if not capabilities["can_view_student_assignments"]:
        messages.error(request, pgettext_lazy("accounts.student_assignments.message", "student_or_member_only"))
        return redirect("accounts:profile")

    requested_section = (request.GET.get("section") or "").strip().lower()
    if requested_section == "pending-answers":
        pending_filter = _normalize_pending_answers_filter(request.GET.get("pending_type") or request.GET.get("type"))
        back_url = _append_query_params(
            reverse("accounts:profile"),
            section="pending-answers",
            pending_type=pending_filter,
            pending_search=(request.GET.get("pending_search") or "").strip(),
        )
    else:
        results_filter = _normalize_results_filter(request.GET.get("results_type") or request.GET.get("type"))
        back_url = _append_query_params(
            reverse("accounts:profile"),
            section="my-results",
            results_type=results_filter,
        )

    normalized_type = (item_type or "").lower()
    tenant_course_ids = _tenant_scoped_courses(request).values_list("id", flat=True)

    if normalized_type == "exams":
        attempt = get_object_or_404(
            ExamAttempt.objects.select_related("exam"),
            id=item_id,
            user=request.user,
            exam__in=_tenant_scoped_exams(request),
        )
        if (
            attempt.exam.exam_type != "test"
            and attempt.checked_by_teacher
            and attempt.teacher_checked_at
            and not _is_result_visible_to_student(attempt.teacher_checked_at)
        ):
            messages.info(
                request,
                f"Nəticə hələ yekunlaşmayıb. {REVIEW_EDIT_WINDOW_MINUTES} dəqiqə tamam olduqdan sonra görünəcək.",
            )
            return redirect(back_url)
        return redirect("exams:exam_result", slug=attempt.exam.slug, attempt_id=attempt.id)

    if normalized_type == "courses":
        submission = get_object_or_404(
            Submission.objects.select_related("assignment", "assignment__course"),
            id=item_id,
            user=request.user,
            assignment__course_id__in=tenant_course_ids,
        )
        if (
            submission.status == "graded"
            and submission.graded_at
            and not _is_result_visible_to_student(submission.graded_at)
        ):
            messages.info(
                request,
                f"Nəticə hələ yekunlaşmayıb. {REVIEW_EDIT_WINDOW_MINUTES} dəqiqə tamam olduqdan sonra görünəcək.",
            )
            return redirect(back_url)

        is_graded_visible = submission.status == "graded" and (
            not submission.graded_at or _is_result_visible_to_student(submission.graded_at)
        )
        context = {
            "item_type": "courses",
            "item_type_label": pgettext_lazy("accounts.my_result_detail.type", "course"),
            "item_title": submission.assignment.title,
            "item_subtitle": submission.assignment.course.title,
            "submitted_at": submission.submitted_at,
            "status": _result_status_badge(submission.status, is_graded=is_graded_visible),
            "status_raw": submission.get_status_display(),
            "score": submission.grade if is_graded_visible else None,
            "feedback": submission.feedback if is_graded_visible else "",
            "content_text": submission.content,
            "files": submission.files or [],
            "back_url": back_url,
        }
        return render(request, "accounts/my_result_detail.html", context)

    if normalized_type == "labs":
        submission = get_object_or_404(
            LabSubmission.objects.select_related("assignment", "assignment__lab", "assignment__lab__course"),
            id=item_id,
            assignment__student=request.user,
            assignment__lab__course_id__in=tenant_course_ids,
        )
        if (
            submission.status == "graded"
            and submission.graded_at
            and not _is_result_visible_to_student(submission.graded_at)
        ):
            messages.info(
                request,
                f"Nəticə hələ yekunlaşmayıb. {REVIEW_EDIT_WINDOW_MINUTES} dəqiqə tamam olduqdan sonra görünəcək.",
            )
            return redirect(back_url)

        is_graded_visible = submission.status == "graded" and (
            not submission.graded_at or _is_result_visible_to_student(submission.graded_at)
        )
        lab_answers = (
            LabAnswer.objects.filter(
                lab=submission.assignment.lab,
                student=request.user,
                attempt_number=submission.attempt_number,
                is_draft=False,
            )
            .select_related("question", "question__block")
            .order_by("question__block__order", "question__question_number")
        )
        if not lab_answers.exists():
            lab_answers = (
                submission.answers.filter(is_draft=False)
                .select_related("question", "question__block")
                .order_by("question__block__order", "question__question_number")
            )

        context = {
            "item_type": "labs",
            "item_type_label": pgettext_lazy("accounts.my_result_detail.type", "lab"),
            "item_title": submission.assignment.lab.title,
            "item_subtitle": submission.assignment.lab.course.title,
            "submitted_at": submission.submitted_at,
            "status": _result_status_badge(submission.status, is_graded=is_graded_visible),
            "status_raw": submission.get_status_display(),
            "score": submission.score if is_graded_visible else None,
            "feedback": submission.feedback if is_graded_visible else "",
            "content_text": submission.submission_text,
            "submission_link": submission.submission_link,
            "submission_file": submission.submission_file,
            "lab_answers": lab_answers,
            "lab_answer_count": lab_answers.count(),
            "back_url": back_url,
        }
        return render(request, "accounts/my_result_detail.html", context)

    if normalized_type == "independent":
        submission = get_object_or_404(
            ProjectSubmission.objects.select_related("project", "project__course"),
            id=item_id,
            student=request.user,
            project__course_id__in=tenant_course_ids,
        )
        if (
            submission.status == "graded"
            and submission.graded_at
            and not _is_result_visible_to_student(submission.graded_at)
        ):
            messages.info(
                request,
                f"Nəticə hələ yekunlaşmayıb. {REVIEW_EDIT_WINDOW_MINUTES} dəqiqə tamam olduqdan sonra görünəcək.",
            )
            return redirect(back_url)

        is_graded_visible = submission.status == "graded" and (
            not submission.graded_at or _is_result_visible_to_student(submission.graded_at)
        )
        context = {
            "item_type": "independent",
            "item_type_label": pgettext_lazy("accounts.my_result_detail.type", "independent_work"),
            "item_title": submission.project.title,
            "item_subtitle": submission.project.course.title,
            "submitted_at": submission.submitted_at,
            "status": _result_status_badge(submission.status, is_graded=is_graded_visible),
            "status_raw": submission.get_status_display(),
            "score": submission.grade if is_graded_visible else None,
            "feedback": submission.feedback if is_graded_visible else "",
            "content_text": submission.content,
            "submission_file": submission.file,
            "back_url": back_url,
        }
        return render(request, "accounts/my_result_detail.html", context)

    messages.error(request, pgettext_lazy("accounts.my_results.message", "unknown_result_type"))
    return redirect(back_url)


@login_required
def pending_review(request):
    """Teacher review queue across exams, assignments, labs, and projects."""
    profile = getattr(request.user, "profile", None)
    capabilities = _role_capabilities(request.user, profile)
    if not capabilities["can_review_submissions"]:
        messages.error(request, pgettext_lazy("accounts.pending_review.message", "teacher_only"))
        return redirect("accounts:profile")

    items, search, filter_type, filter_status = _collect_pending_review_items(request)
    context = {
        "review_items": items,
        "search_query": search,
        "filter_type": filter_type,
        "filter_status": filter_status,
        "total_count": len(items),
    }
    return render(request, "accounts/pending_review.html", context)


@login_required
def pending_review_detail(request, item_type, item_id):
    """Teacher-facing grading page for pending assignment/project/lab submissions."""
    profile = getattr(request.user, "profile", None)
    capabilities = _role_capabilities(request.user, profile)
    if not capabilities["can_review_submissions"]:
        messages.error(request, pgettext_lazy("accounts.pending_review.message", "teacher_only"))
        return redirect("accounts:profile")

    normalized_type = _normalize_review_result_item_type(item_type)
    if not normalized_type:
        return redirect(f"{reverse('accounts:profile')}?section=pending-review")

    default_back_url = f"{reverse('accounts:profile')}?section=pending-review"
    back_url = _safe_same_origin_redirect_path(
        request,
        request.GET.get("return_to") or request.GET.get("next"),
    )
    if not back_url:
        back_url = default_back_url

    teacher_courses = _tenant_scoped_courses(request, Course.objects.filter(owner=request.user))
    redirect_url = request.get_full_path()

    base_context = {
        "item_type": normalized_type,
        "item_type_label": _pending_review_type_label(normalized_type),
        "back_url": back_url,
        "review_window_minutes": REVIEW_EDIT_WINDOW_MINUTES,
    }

    if normalized_type == "assignment":
        submission = get_object_or_404(
            Submission.objects.select_related("assignment", "assignment__course", "user", "graded_by"),
            id=item_id,
            assignment__course__in=teacher_courses,
        )
        max_score = Decimal(str(submission.assignment.max_score or 100))
        is_locked = _is_review_window_closed(submission.graded_at)
        is_recheck_window = bool(
            submission.status == "graded"
            and submission.graded_at
            and not is_locked
        )
        student_display, is_identity_hidden, identity_window_seconds_left = _resolve_pending_review_identity(
            student=submission.user,
            submitted_at=submission.submitted_at,
            graded_at=submission.graded_at,
            is_recheck=is_recheck_window,
        )

        if request.method == "POST":
            if is_locked:
                messages.error(request, "Bu cavab üçün yoxlama müddəti bitib. Artıq bal dəyişdirilə bilməz.")
                return redirect(redirect_url)

            feedback = (request.POST.get("feedback") or "").strip()
            try:
                score = _parse_decimal_score(request.POST.get("score"))
            except InvalidOperation:
                messages.error(request, "Bal düzgün rəqəm formatında olmalıdır.")
                return redirect(redirect_url)

            if score < 0 or score > max_score:
                messages.error(request, f"Bal 0 və {max_score} aralığında olmalıdır.")
                return redirect(redirect_url)

            submission.grade = score
            submission.feedback = feedback
            submission.status = "graded"
            submission.graded_by = request.user
            if not submission.graded_at:
                submission.graded_at = timezone.now()
            submission.save(update_fields=["grade", "feedback", "status", "graded_by", "graded_at"])
            messages.success(
                request,
                f"Qiymət saxlanıldı. {REVIEW_EDIT_WINDOW_MINUTES} dəqiqə ərzində yenidən yoxlaya bilərsiniz.",
            )
            return redirect(redirect_url)

        context = {
            **base_context,
            "item_title": submission.assignment.title,
            "course_title": submission.assignment.course.title,
            "student_display": student_display,
            "status_display": submission.get_status_display(),
            "submitted_at": submission.submitted_at,
            "graded_at": submission.graded_at,
            "feedback": submission.feedback,
            "content_text": submission.content,
            "attachments": _extract_assignment_attachments(submission),
            "current_score": submission.grade,
            "current_score_input_value": _format_decimal_input(submission.grade),
            "max_score": max_score,
            "is_locked": is_locked,
            "is_recheck_window": is_recheck_window,
            "is_identity_hidden": is_identity_hidden,
            "is_pregrade_anonymous_window": is_identity_hidden and not is_recheck_window,
            "review_window_seconds_left": _review_window_seconds_left(submission.graded_at),
            "identity_window_seconds_left": identity_window_seconds_left,
            "review_deadline": submission.graded_at + REVIEW_EDIT_WINDOW if submission.graded_at else None,
        }
        return render(request, "accounts/pending_review_detail.html", context)

    if normalized_type == "project":
        submission = get_object_or_404(
            ProjectSubmission.objects.select_related("project", "project__course", "student", "graded_by"),
            id=item_id,
            project__course__in=teacher_courses,
        )
        max_score = Decimal(str(submission.project.max_score or 100))
        is_locked = _is_review_window_closed(submission.graded_at)
        is_recheck_window = bool(
            submission.status == "graded"
            and submission.graded_at
            and not is_locked
        )
        student_display, is_identity_hidden, identity_window_seconds_left = _resolve_pending_review_identity(
            student=submission.student,
            submitted_at=submission.submitted_at,
            graded_at=submission.graded_at,
            is_recheck=is_recheck_window,
        )

        if request.method == "POST":
            if is_locked:
                messages.error(request, "Bu cavab üçün yoxlama müddəti bitib. Artıq bal dəyişdirilə bilməz.")
                return redirect(redirect_url)

            feedback = (request.POST.get("feedback") or "").strip()
            try:
                score = _parse_decimal_score(request.POST.get("score"))
            except InvalidOperation:
                messages.error(request, "Bal düzgün rəqəm formatında olmalıdır.")
                return redirect(redirect_url)

            if score < 0 or score > max_score:
                messages.error(request, f"Bal 0 və {max_score} aralığında olmalıdır.")
                return redirect(redirect_url)

            submission.grade = score
            submission.feedback = feedback
            submission.status = "graded"
            submission.graded_by = request.user
            if not submission.graded_at:
                submission.graded_at = timezone.now()
            submission.save(update_fields=["grade", "feedback", "status", "graded_by", "graded_at"])
            messages.success(
                request,
                f"Qiymət saxlanıldı. {REVIEW_EDIT_WINDOW_MINUTES} dəqiqə ərzində yenidən yoxlaya bilərsiniz.",
            )
            return redirect(redirect_url)

        attachments = []
        if submission.file:
            attachments.append({"name": PurePosixPath(submission.file.name).name, "url": submission.file.url})

        context = {
            **base_context,
            "item_title": submission.project.title,
            "course_title": submission.project.course.title,
            "student_display": student_display,
            "status_display": submission.get_status_display(),
            "submitted_at": submission.submitted_at,
            "graded_at": submission.graded_at,
            "feedback": submission.feedback,
            "content_text": submission.content,
            "attachments": attachments,
            "current_score": submission.grade,
            "current_score_input_value": _format_decimal_input(submission.grade),
            "max_score": max_score,
            "is_locked": is_locked,
            "is_recheck_window": is_recheck_window,
            "is_identity_hidden": is_identity_hidden,
            "is_pregrade_anonymous_window": is_identity_hidden and not is_recheck_window,
            "review_window_seconds_left": _review_window_seconds_left(submission.graded_at),
            "identity_window_seconds_left": identity_window_seconds_left,
            "review_deadline": submission.graded_at + REVIEW_EDIT_WINDOW if submission.graded_at else None,
        }
        return render(request, "accounts/pending_review_detail.html", context)

    submission = get_object_or_404(
        LabSubmission.objects.select_related("assignment", "assignment__lab", "assignment__lab__course", "assignment__student"),
        id=item_id,
        assignment__lab__course__in=teacher_courses,
    )
    max_score = Decimal(str(submission.assignment.lab.max_score or 100))
    is_locked = _is_review_window_closed(submission.graded_at)
    is_recheck_window = bool(
        submission.status == "graded"
        and submission.graded_at
        and not is_locked
    )
    student_display, is_identity_hidden, identity_window_seconds_left = _resolve_pending_review_identity(
        student=submission.assignment.student,
        submitted_at=submission.submitted_at,
        graded_at=submission.graded_at,
        is_recheck=is_recheck_window,
    )

    lab_answers = list(
        submission.answers.select_related("question", "question__block").order_by(
            "question__block__order",
            "question__question_number",
        )
    )
    if not lab_answers:
        lab_answers = list(
            LabAnswer.objects.filter(
                lab=submission.assignment.lab,
                student=submission.assignment.student,
                attempt_number=submission.attempt_number,
                is_draft=False,
            )
            .select_related("question", "question__block")
            .order_by("question__block__order", "question__question_number")
        )

    if request.method == "POST":
        if is_locked:
            messages.error(request, "Bu cavab üçün yoxlama müddəti bitib. Artıq bal dəyişdirilə bilməz.")
            return redirect(redirect_url)

        feedback = (request.POST.get("feedback") or "").strip()
        try:
            auto_total = Decimal("0")
            has_posted_answer_scores = False
            for answer in lab_answers:
                raw_answer_score = (request.POST.get(f"answer_score_{answer.id}") or "").strip()
                if not raw_answer_score:
                    answer.score = None
                else:
                    has_posted_answer_scores = True
                    answer_score = _parse_decimal_score(raw_answer_score)
                    if answer_score < 0:
                        answer_score = Decimal("0")
                    question_max = Decimal(str(answer.question.points or 0))
                    if question_max > 0 and answer_score > question_max:
                        answer_score = question_max
                    answer.score = answer_score
                    auto_total += answer_score
                answer.save(update_fields=["score", "submitted_at"])

            entered_total = _parse_decimal_score(request.POST.get("score"))
        except InvalidOperation:
            messages.error(request, "Bal düzgün rəqəm formatında olmalıdır.")
            return redirect(redirect_url)

        score = entered_total if (not has_posted_answer_scores or entered_total != auto_total) else auto_total

        if score < 0 or score > max_score:
            messages.error(request, f"Bal 0 və {max_score} aralığında olmalıdır.")
            return redirect(redirect_url)

        submission.score = score
        submission.feedback = feedback
        submission.status = "graded"
        submission.graded_by = request.user
        if not submission.graded_at:
            submission.graded_at = timezone.now()
        submission.save(update_fields=["score", "feedback", "status", "graded_by", "graded_at"])
        messages.success(
            request,
            f"Qiymət saxlanıldı. {REVIEW_EDIT_WINDOW_MINUTES} dəqiqə ərzində yenidən yoxlaya bilərsiniz.",
        )
        return redirect(redirect_url)

    attachments = []
    if submission.submission_file:
        attachments.append(
            {
                "name": PurePosixPath(submission.submission_file.name).name,
                "url": submission.submission_file.url,
            }
        )
    if submission.submission_link:
        attachments.append({"name": submission.submission_link, "url": submission.submission_link})

    has_answer_scores = any(answer.score is not None for answer in lab_answers)
    auto_total_decimal = sum(
        (answer.score if answer.score is not None else Decimal("0") for answer in lab_answers),
        Decimal("0"),
    )
    use_manual_total_initial = False
    if submission.score is not None:
        submission_score_decimal = Decimal(str(submission.score))
        use_manual_total_initial = (not has_answer_scores) or submission_score_decimal != auto_total_decimal

    for answer in lab_answers:
        answer.score_input_value = _format_decimal_input(answer.score)

    context = {
        **base_context,
        "item_title": submission.assignment.lab.title,
        "course_title": submission.assignment.lab.course.title,
        "student_display": student_display,
        "status_display": submission.get_status_display(),
        "submitted_at": submission.submitted_at,
        "graded_at": submission.graded_at,
        "feedback": submission.feedback,
        "content_text": submission.submission_text,
        "attachments": attachments,
        "lab_answers": lab_answers,
        "current_score": submission.score,
        "current_score_input_value": _format_decimal_input(submission.score),
        "auto_total_score": auto_total_decimal,
        "auto_total_score_input_value": _format_decimal_input(auto_total_decimal),
        "max_score": max_score,
        "is_locked": is_locked,
        "is_recheck_window": is_recheck_window,
        "is_identity_hidden": is_identity_hidden,
        "is_pregrade_anonymous_window": is_identity_hidden and not is_recheck_window,
        "review_window_seconds_left": _review_window_seconds_left(submission.graded_at),
        "identity_window_seconds_left": identity_window_seconds_left,
        "review_deadline": submission.graded_at + REVIEW_EDIT_WINDOW if submission.graded_at else None,
        "use_manual_total_initial": use_manual_total_initial,
    }
    return render(request, "accounts/pending_review_detail.html", context)


@login_required
def review_results(request):
    """Teacher evaluated results across exams, assignments, labs, and projects."""
    profile = getattr(request.user, "profile", None)
    capabilities = _role_capabilities(request.user, profile)
    if not capabilities["can_review_submissions"]:
        messages.error(request, pgettext_lazy("accounts.pending_review.message", "teacher_only"))
        return redirect("accounts:profile")

    (
        evaluated_items,
        evaluated_search,
        evaluated_filter_type,
        evaluated_filter_group,
        evaluated_available_groups,
    ) = _collect_evaluated_review_items(request)

    context = {
        "evaluated_review_items": evaluated_items,
        "evaluated_review_search_query": evaluated_search,
        "evaluated_review_filter_type": evaluated_filter_type,
        "evaluated_review_filter_group": evaluated_filter_group,
        "evaluated_review_available_groups": evaluated_available_groups,
        "evaluated_review_total_count": len(evaluated_items),
    }
    return render(request, "accounts/review_results.html", context)


@login_required
def review_result_detail(request, item_type, item_id):
    """Teacher-facing detail page for graded assignment/project/lab results."""
    profile = getattr(request.user, "profile", None)
    capabilities = _role_capabilities(request.user, profile)
    if not capabilities["can_review_submissions"]:
        messages.error(request, pgettext_lazy("accounts.pending_review.message", "teacher_only"))
        return redirect("accounts:profile")

    normalized_type = _normalize_review_result_item_type(item_type)
    if not normalized_type:
        return redirect(f"{reverse('accounts:profile')}?section=review-results")

    default_back_url = f"{reverse('accounts:profile')}?section=review-results"
    back_url = _safe_same_origin_redirect_path(
        request,
        request.GET.get("return_to") or request.GET.get("next"),
    )
    if not back_url:
        back_url = default_back_url

    teacher_courses = _tenant_scoped_courses(request, Course.objects.filter(owner=request.user))

    if normalized_type == "assignment":
        submission = get_object_or_404(
            Submission.objects.select_related("assignment", "assignment__course", "user", "graded_by"),
            id=item_id,
            assignment__course__in=teacher_courses,
        )
        context = {
            "item_type": normalized_type,
            "item_type_label": "Sərbəst iş",
            "item_title": submission.assignment.title,
            "course_title": submission.assignment.course.title,
            "student": submission.user,
            "status_display": submission.get_status_display(),
            "score_display": submission.grade if submission.grade is not None else "-",
            "submitted_at": submission.submitted_at,
            "graded_at": submission.graded_at,
            "feedback": submission.feedback,
            "content_text": submission.content,
            "attachments": _extract_assignment_attachments(submission),
            "back_url": back_url,
        }
        return render(request, "accounts/review_result_detail.html", context)

    if normalized_type == "project":
        submission = get_object_or_404(
            ProjectSubmission.objects.select_related("project", "project__course", "student", "graded_by"),
            id=item_id,
            project__course__in=teacher_courses,
        )
        attachments = []
        if submission.file:
            attachments.append({"name": PurePosixPath(submission.file.name).name, "url": submission.file.url})

        context = {
            "item_type": normalized_type,
            "item_type_label": "Kurs işi",
            "item_title": submission.project.title,
            "course_title": submission.project.course.title,
            "student": submission.student,
            "status_display": submission.get_status_display(),
            "score_display": submission.grade if submission.grade is not None else "-",
            "submitted_at": submission.submitted_at,
            "graded_at": submission.graded_at,
            "feedback": submission.feedback,
            "content_text": submission.content,
            "attachments": attachments,
            "back_url": back_url,
        }
        return render(request, "accounts/review_result_detail.html", context)

    submission = get_object_or_404(
        LabSubmission.objects.select_related("assignment", "assignment__lab", "assignment__lab__course", "assignment__student"),
        id=item_id,
        assignment__lab__course__in=teacher_courses,
    )
    lab_answers = list(
        submission.answers.select_related("question", "question__block").order_by(
            "question__block__order",
            "question__question_number",
        )
    )
    if not lab_answers:
        lab_answers = list(
            LabAnswer.objects.filter(
                lab=submission.assignment.lab,
                student=submission.assignment.student,
                attempt_number=submission.attempt_number,
                is_draft=False,
            )
            .select_related("question", "question__block")
            .order_by("question__block__order", "question__question_number")
        )

    attachments = []
    if submission.submission_file:
        attachments.append(
            {
                "name": PurePosixPath(submission.submission_file.name).name,
                "url": submission.submission_file.url,
            }
        )
    if submission.submission_link:
        attachments.append({"name": submission.submission_link, "url": submission.submission_link})

    context = {
        "item_type": normalized_type,
        "item_type_label": "Lab işi",
        "item_title": submission.assignment.lab.title,
        "course_title": submission.assignment.lab.course.title,
        "student": submission.assignment.student,
        "status_display": submission.get_status_display(),
        "score_display": submission.score if submission.score is not None else "-",
        "submitted_at": submission.submitted_at,
        "graded_at": submission.graded_at,
        "feedback": submission.feedback,
        "content_text": submission.submission_text,
        "attachments": attachments,
        "lab_answers": lab_answers,
        "back_url": back_url,
    }
    return render(request, "accounts/review_result_detail.html", context)
