"""
Account views for user dashboards, profile management, and role assignment.
"""

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.assignments.models import Assignment, Submission
from apps.courses.models import Course
from apps.exams.models import Exam, ExamAttempt
from core.constants import ROLE_LEVELS

User = get_user_model()


@login_required
def teacher_dashboard(request):
    """
    Teacher dashboard with widgets showing courses, pending grading, and stats.
    """
    # Only teachers and above can access
    if not getattr(request.user, "is_teacher_or_above", False):
        messages.error(request, "Bu səhifəyə yalnız müəllimlər daxil ola bilər.")
        return redirect("home")

    # Get teacher's courses
    my_courses = Course.objects.filter(owner=request.user, status="published")[:5]

    # Get pending submissions
    pending_submissions = Submission.objects.filter(
        assignment__course__owner=request.user, status="submitted"
    ).select_related("assignment", "user")[:10]

    # Get upcoming exams
    upcoming_exams = Exam.objects.filter(
        owner=request.user, is_active=True, start_date__gte=timezone.now()
    ).order_by("start_date")[:5]

    # Calculate stats
    total_courses = Course.objects.filter(owner=request.user).count()
    total_students = (
        Course.objects.filter(owner=request.user)
        .aggregate(count=Count("memberships__user", distinct=True))
        .get("count", 0)
    )
    pending_count = Submission.objects.filter(
        assignment__course__owner=request.user, status="submitted"
    ).count()

    # Students at risk (failing grades or missing submissions)
    at_risk_students = []
    for course in Course.objects.filter(owner=request.user):
        # Find students with low grades or missing submissions
        submissions = Submission.objects.filter(
            assignment__course=course, status="graded", grade__lt=50
        ).values_list("user_id", flat=True).distinct()
        at_risk_students.extend(
            User.objects.filter(id__in=submissions).values("id", "username")[:3]
        )

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
    enrolled_courses = Course.objects.filter(
        memberships__user=request.user, status="published"
    ).distinct()[:6]

    # Get pending assignments
    pending_assignments = Assignment.objects.filter(
        course__in=enrolled_courses,
        deadline__gte=timezone.now(),
        status="published",
    ).order_by("deadline")[:5]

    # Get upcoming exams
    upcoming_exams = Exam.objects.filter(
        Q(assigned_students=request.user) | Q(assigned_groups__students=request.user),
        is_active=True,
        start_date__gte=timezone.now(),
    ).distinct().order_by("start_date")[:5]

    # Get recent grades
    recent_grades = Submission.objects.filter(
        user=request.user, status="graded"
    ).order_by("-graded_at")[:5]

    context = {
        "enrolled_courses": enrolled_courses,
        "pending_assignments": pending_assignments,
        "upcoming_exams": upcoming_exams,
        "recent_grades": recent_grades,
    }

    return render(request, "accounts/student_dashboard.html", context)


@login_required
def user_profile(request):
    """
    User profile page with edit functionality.
    """
    profile = request.user.profile if hasattr(request.user, "profile") else None

    if request.method == "POST":
        # Update user info
        request.user.first_name = request.POST.get("first_name", "")
        request.user.last_name = request.POST.get("last_name", "")
        request.user.email = request.POST.get("email", "")
        request.user.save()

        # Update profile
        if profile:
            profile.phone = request.POST.get("phone", "")
            profile.bio = request.POST.get("bio", "")
            profile.location = request.POST.get("location", "")

            # Handle avatar upload
            if "avatar" in request.FILES:
                profile.avatar = request.FILES["avatar"]

            # Only admins can change supervisor_code
            if request.user.is_admin_level:
                profile.supervisor_code = request.POST.get("supervisor_code", "")

            profile.save()

        messages.success(request, "Profil uğurla yeniləndi!")
        return redirect("accounts:profile")

    # Get user's roles
    user_roles = request.user.get_all_roles() if hasattr(request.user, "get_all_roles") else []

    context = {
        "profile": profile,
        "user_roles": user_roles,
    }

    return render(request, "accounts/profile.html", context)


@login_required
def manage_roles(request):
    """
    Role assignment view for admin-level users.
    Only users with admin level (level >= 80) can access.
    """
    if not getattr(request.user, "is_admin_level", False):
        messages.error(request, "Bu səhifəyə yalnız administratorlar daxil ola bilər.")
        return redirect("home")

    if request.method == "POST":
        user_id = request.POST.get("user_id")
        role_name = request.POST.get("role_name")
        action = request.POST.get("action")  # "add" or "remove"

        user = get_object_or_404(User, id=user_id)

        # Check if current user can assign this role
        if not request.user.can_assign_role(role_name):
            messages.error(request, "Bu rolu təyin etmək icazəniz yoxdur.")
            return redirect("accounts:manage_roles")

        group = get_object_or_404(Group, name=role_name)

        if action == "add":
            user.groups.add(group)
            messages.success(request, f"{role_name} rolu {user.username} istifadəçisinə əlavə edildi.")
        elif action == "remove":
            user.groups.remove(group)
            messages.success(request, f"{role_name} rolu {user.username} istifadəçisindən silindi.")

        return redirect("accounts:manage_roles")

    # Get all users
    users = User.objects.all().prefetch_related("groups")

    # Get all roles that current user can assign
    assignable_roles = [
        role_name for role_name in ROLE_LEVELS.keys()
        if request.user.can_assign_role(role_name)
    ]

    context = {
        "users": users,
        "assignable_roles": assignable_roles,
        "role_levels": ROLE_LEVELS,
    }

    return render(request, "accounts/manage_roles.html", context)


@login_required
def grading_queue(request):
    """
    Grading queue for teachers showing all pending submissions.
    """
    if not getattr(request.user, "is_teacher_or_above", False):
        messages.error(request, "Bu səhifəyə yalnız müəllimlər daxil ola bilər.")
        return redirect("home")

    # Get filter parameters
    course_id = request.GET.get("course")
    assignment_id = request.GET.get("assignment")

    # Base query
    submissions = Submission.objects.filter(
        assignment__course__owner=request.user, status="submitted"
    ).select_related("assignment", "user", "assignment__course")

    # Apply filters
    if course_id:
        submissions = submissions.filter(assignment__course_id=course_id)
    if assignment_id:
        submissions = submissions.filter(assignment_id=assignment_id)

    # Order by oldest first
    submissions = submissions.order_by("submitted_at")

    # Get courses for filter dropdown
    courses = Course.objects.filter(owner=request.user)

    context = {
        "submissions": submissions,
        "courses": courses,
        "selected_course": course_id,
        "selected_assignment": assignment_id,
    }

    return render(request, "accounts/grading_queue.html", context)
