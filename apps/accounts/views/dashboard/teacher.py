"""
Teacher dashboard and grading queue views.
"""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.translation import pgettext_lazy

from apps.assignments.models import Assignment, Submission
from apps.courses.models import Course
from apps.exams.models import Exam

from .._helpers import (
    _role_capabilities,
    _tenant_scoped_courses,
    _tenant_scoped_exams,
)

User = get_user_model()


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

    # Get teacher's courses. Annotate the member count so the template badge
    # ({{ course.memberships_total }}) doesn't fire one COUNT query per card (N+1).
    my_courses = teacher_courses.filter(status="published").annotate(
        memberships_total=Count("memberships", distinct=True)
    )[:5]

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

    # Students at risk (low grades). One query across all the teacher's courses
    # instead of two queries per course (previously O(courses) round-trips).
    at_risk_user_ids = (
        Submission.objects.filter(
            assignment__course__in=teacher_courses,
            status="graded",
            grade__lt=50,
        )
        .values_list("user_id", flat=True)
        .distinct()
    )
    at_risk_students = list(User.objects.filter(id__in=at_risk_user_ids).values("id", "username")[:5])

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
