"""
Account views for user dashboards, profile management, authentication, and role assignment.
"""

from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login as auth_login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.core.mail import send_mail
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone

from apps.assignments.models import Assignment, Submission
from apps.blog.models import EmailOTP, Post
from apps.blog.utils import generate_otp, send_verify_email
from apps.courses.models import Course
from apps.exams.models import Exam, ExamAttempt
from core.constants import ROLE_LEVELS

from .forms import RegisterForm
from .models import UserProfile

User = get_user_model()
signer = TimestampSigner()


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
    Ensures profile exists before rendering.
    """
    from apps.accounts.models import UserProfile

    # Ensure profile exists (get_or_create for safety)
    profile, created = UserProfile.objects.get_or_create(user=request.user)

    if request.method == "POST":
        # Update user info
        request.user.first_name = request.POST.get("first_name", "")
        request.user.last_name = request.POST.get("last_name", "")
        request.user.email = request.POST.get("email", "")
        request.user.save()

        # Update profile
        profile.phone = request.POST.get("phone", "")
        profile.bio = request.POST.get("bio", "")
        profile.location = request.POST.get("location", "")

        # Handle avatar upload
        if "avatar" in request.FILES:
            profile.avatar = request.FILES["avatar"]

        # Only admins can change supervisor_code
        if getattr(request.user, "is_admin_level", False):
            profile.supervisor_code = request.POST.get("supervisor_code", "")

        profile.save()

        messages.success(request, "Profil uğurla yeniləndi!")
        return redirect("accounts:profile")

    # Get user's roles
    user_roles = (
        request.user.get_all_roles()
        if hasattr(request.user, "get_all_roles")
        else []
    )

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


# ------------------- AUTHENTICATION VIEWS ------------------- #


def register_view(request):
    """User registration with email verification."""
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)

            # Set password
            password = form.cleaned_data["password"]
            user.set_password(password)

            # Disable account until email is verified
            user.is_active = False
            user.save()

            # Create user profile with organization type
            organization_type = form.cleaned_data.get("organization_type", "individual")
            UserProfile.objects.create(
                user=user,
                organization_type=organization_type
            )

            # Generate and send verification code
            code = generate_otp()
            EmailOTP.objects.create(
                user=user,
                code=code,
                expires_at=timezone.now() + timedelta(minutes=10),
            )
            send_verify_email(user, code)

            request.session["pending_verify_email"] = user.email
            messages.success(request, "Email-ə təsdiq kodu göndərildi.")
            return redirect("accounts:verify_code")
    else:
        form = RegisterForm()

    return render(request, "accounts/register.html", {"form": form})


def verify_code_view(request):
    """Verify email using OTP code."""
    email = request.session.get("pending_verify_email")
    if not email:
        messages.error(
            request, "Təsdiqləmə üçün email tapılmadı. Yenidən qeydiyyatdan keç."
        )
        return redirect("accounts:register")

    if request.method == "POST":
        code = request.POST.get("code", "").strip()

        user = User.objects.filter(email=email).first()
        if not user:
            messages.error(request, "User tapılmadı.")
            return redirect("accounts:register")

        otp = (
            EmailOTP.objects.filter(user=user, code=code, is_used=False)
            .order_by("-created_at")
            .first()
        )
        if not otp or otp.is_expired():
            messages.error(request, "Kod yanlışdır və ya vaxtı bitib.")
            return render(request, "accounts/verify_code.html", {"email": email})

        otp.is_used = True
        otp.save()

        user.is_active = True
        user.save()

        messages.success(request, "Email təsdiqləndi. İndi daxil ola bilərsən.")
        return redirect("login")

    return render(request, "accounts/verify_code.html", {"email": email})


def verify_email_link_view(request):
    """Verify email using signed token link."""
    token = request.GET.get("token", "")
    try:
        user_id = signer.unsign(token, max_age=60 * 10)  # 10 minutes
        user = User.objects.get(pk=user_id)
        user.is_active = True
        user.save()
        messages.success(request, "Email təsdiqləndi. İndi login ola bilərsən.")
        return redirect("login")
    except (BadSignature, SignatureExpired, User.DoesNotExist):
        messages.error(request, "Link yanlışdır və ya vaxtı bitib.")
        return redirect("accounts:register")


def resend_code_view(request):
    """Resend email verification code."""
    email = request.session.get("pending_verify_email")
    if not email:
        messages.error(request, "Email tapılmadı.")
        return redirect("accounts:register")

    user = User.objects.filter(email=email).first()
    if not user:
        messages.error(request, "User tapılmadı.")
        return redirect("accounts:register")

    code = generate_otp()
    EmailOTP.objects.create(
        user=user, code=code, expires_at=timezone.now() + timedelta(minutes=10)
    )
    send_verify_email(user, code)

    messages.success(request, "Yeni kod göndərildi.")
    return redirect("accounts:verify_code")


def logout_view(request):
    """Logout user and redirect to home."""
    logout(request)
    messages.success(request, "Uğurla çıxış etdiniz.")
    return redirect("home")


# ------------------- BLOG-STYLE USER PROFILE ------------------- #


def public_user_profile(request, username):
    """
    Public user profile showing user's posts and activity.
    Different from the accounts:profile which is for editing own profile.
    """
    from apps.blog.models import Post
    from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator

    profile_user = get_object_or_404(User, username=username)

    # Get user's profile
    profile, created = UserProfile.objects.get_or_create(user=profile_user)

    # 1. Posts filtering
    if request.user == profile_user:
        user_posts_list = (
            Post.objects.filter(author=profile_user)
            .select_related("category")
            .order_by("-created_at")
        )
    else:
        user_posts_list = (
            Post.objects.filter(author=profile_user, is_published=True)
            .select_related("category")
            .order_by("-created_at")
        )

    # 2. Pagination
    paginator = Paginator(user_posts_list, 6)
    page_number = request.GET.get("page")
    try:
        posts = paginator.page(page_number)
    except PageNotAnInteger:
        posts = paginator.page(1)
    except EmptyPage:
        posts = paginator.page(paginator.num_pages)

    # 3. Pending exams count (for teachers)
    pending_count = 0
    if (
        request.user.is_authenticated
        and request.user == profile_user
        and getattr(request.user, "is_teacher", False)
    ):
        pending_count = (
            ExamAttempt.objects.filter(
                exam__author=request.user,
                status__in=["submitted", "expired"],
                checked_by_teacher=False,
            )
            .exclude(exam__exam_type="test")
            .count()
        )

    # 4. Assigned exams count
    assigned_count = 0
    if request.user.is_authenticated and request.user == profile_user:
        assigned_count = (
            Exam.objects.filter(is_active=True)
            .filter(
                Q(allowed_users=request.user) | Q(allowed_groups__students=request.user)
            )
            .distinct()
            .count()
        )

    # 5. Student courses
    student_courses = []
    student_courses_count = 0

    if request.user.is_authenticated and request.user == profile_user:
        if getattr(request.user, "is_student", False):
            student_courses = (
                Course.objects.filter(
                    memberships__user=request.user,
                    memberships__role="student",
                    status="published",
                )
                .distinct()
                .order_by("-created_at")
            )
            student_courses_count = student_courses.count()

    # 6. Categories
    from apps.blog.models import Category

    categories = Category.objects.all().order_by("name")

    context = {
        "profile_user": profile_user,
        "profile": profile,
        "posts": posts,
        "categories": categories,
        "pending_count": pending_count,
        "assigned_count": assigned_count,
        "student_courses": student_courses,
        "student_courses_count": student_courses_count,
    }
    return render(request, "accounts/public_profile.html", context)
