"""
Account views for user dashboards, profile management, authentication, and role assignment.
"""

from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model, logout
from django.contrib.auth.decorators import login_required
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.assignments.models import Assignment, Submission
from apps.blog.models import EmailOTP
from apps.blog.utils import generate_otp, send_verify_email
from apps.courses.models import Course
from apps.exams.models import Exam, ExamAttempt

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
        author=request.user, is_active=True, start_datetime__gte=timezone.now()
    ).order_by("start_datetime")[:5]

    # Calculate stats
    total_courses = Course.objects.filter(owner=request.user).count()
    total_students = (
        Course.objects.filter(owner=request.user)
        .aggregate(count=Count("memberships__user", distinct=True))
        .get("count", 0)
    )
    pending_count = Submission.objects.filter(assignment__course__owner=request.user, status="submitted").count()

    # Students at risk (failing grades or missing submissions)
    at_risk_students = []
    for course in Course.objects.filter(owner=request.user):
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
    enrolled_courses = Course.objects.filter(memberships__user=request.user, status="published").distinct()[:6]

    # Get pending assignments
    pending_assignments = Assignment.objects.filter(
        course__in=enrolled_courses,
        deadline__gte=timezone.now(),
        status="published",
    ).order_by("deadline")[:5]

    # Get upcoming exams
    upcoming_exams = (
        Exam.objects.filter(
            Q(assigned_students=request.user) | Q(assigned_groups__students=request.user),
            is_active=True,
            start_date__gte=timezone.now(),
        )
        .distinct()
        .order_by("start_date")[:5]
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
def user_profile(request):
    """
    User profile page with edit functionality.
    Ensures profile exists before rendering.
    Now accessible to ALL users (not just teachers).
    """
    from apps.accounts.models import UserProfile
    from apps.blog.models import Post

    # Ensure profile exists (get_or_create for safety)
    profile, created = UserProfile.objects.get_or_create(user=request.user)

    # Get active section from URL parameter (default: profile-info)
    active_section = request.GET.get("section", "profile-info")

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
    user_roles = request.user.get_all_roles() if hasattr(request.user, "get_all_roles") else []

    # Check role levels early (needed for context below)
    is_teacher = getattr(request.user, "is_teacher_or_above", False)
    is_admin = getattr(request.user, "is_admin_level", False)

    # Get user's posts for the posts section
    user_posts = Post.objects.filter(author=request.user).order_by("-created_at")[:10]
    posts_count = Post.objects.filter(author=request.user).count()

    # Get user's courses
    from apps.courses.models import Course

    my_courses = Course.objects.filter(Q(owner=request.user) | Q(memberships__user=request.user)).distinct()[:10]
    courses_count = my_courses.count()

    # Teacher/admin: exams created by this user
    my_exams_count = 0
    my_exams = []
    my_created_courses_count = 0
    my_created_courses = []
    if is_teacher:
        my_exams = Exam.objects.filter(author=request.user).order_by("-created_at")[:10]
        my_exams_count = Exam.objects.filter(author=request.user).count()
        my_created_courses = Course.objects.filter(owner=request.user).order_by("-created_at")[:10]
        my_created_courses_count = Course.objects.filter(owner=request.user).count()

    # Assigned exams count
    assigned_exams_count = (
        Exam.objects.filter(is_active=True)
        .filter(Q(allowed_users=request.user) | Q(allowed_groups__students=request.user))
        .distinct()
        .count()
    )

    # Assigned courses count
    assigned_courses_count = (
        Course.objects.filter(
            memberships__user=request.user,
            status="published",
        )
        .distinct()
        .count()
    )

    # Pending review count (for teachers)
    pending_review_count = 0
    if is_teacher:
        pending_review_count = (
            ExamAttempt.objects.filter(
                exam__author=request.user,
                status__in=["submitted", "expired"],
                checked_by_teacher=False,
            )
            .exclude(exam__exam_type="test")
            .count()
        )
        # Also count pending assignment submissions
        pending_review_count += Submission.objects.filter(
            assignment__course__owner=request.user, status="submitted"
        ).count()

    context = {
        "profile": profile,
        "user_roles": user_roles,
        "active_section": active_section,
        "user_posts": user_posts,
        "posts_count": posts_count,
        "my_courses": my_courses,
        "courses_count": courses_count,
        "my_exams": my_exams,
        "my_exams_count": my_exams_count,
        "my_created_courses": my_created_courses,
        "my_created_courses_count": my_created_courses_count,
        "assigned_exams_count": assigned_exams_count,
        "assigned_courses_count": assigned_courses_count,
        "pending_review_count": pending_review_count,
        "is_teacher": is_teacher,
        "is_admin": is_admin,
    }

    return render(request, "accounts/profile.html", context)


@login_required
def manage_roles(request):
    """
    Role assignment view for admin-level users.
    Uses UserProfile.role (RBAC) instead of Django Groups.
    Organization-scoped: only shows users from the same org.
    """
    if not getattr(request.user, "is_admin_level", False):
        messages.error(request, "Bu səhifəyə yalnız administratorlar daxil ola bilər.")
        return redirect("home")

    from apps.accounts.models import ProfileRole

    # Get user's organization for scoping
    user_org = getattr(getattr(request.user, "profile", None), "organization", None)

    if request.method == "POST":
        user_id = request.POST.get("user_id")
        role_name = request.POST.get("role_name")
        action = request.POST.get("action")  # "assign" or "remove"

        target_user = get_object_or_404(User, id=user_id)

        # Ensure target is in same organization
        target_org = getattr(getattr(target_user, "profile", None), "organization", None)
        if user_org and target_org and user_org.id != target_org.id:
            messages.error(request, "Başqa təşkilatdakı istifadəçini idarə edə bilməzsiniz.")
            return redirect("accounts:manage_roles")

        # Check hierarchy: can't assign role >= own level
        if not request.user.can_assign_role(role_name):
            messages.error(request, "Bu rolu təyin etmək icazəniz yoxdur.")
            return redirect("accounts:manage_roles")

        target_profile, _ = UserProfile.objects.get_or_create(user=target_user)

        if action == "assign" and role_name:
            target_profile.role = role_name
            target_profile.save()
            messages.success(
                request,
                f"{target_profile.get_role_display()} rolu {target_user.username} istifadəçisinə təyin edildi.",
            )
        elif action == "remove":
            target_profile.role = ProfileRole.STUDENT
            target_profile.save()
            messages.success(request, f"{target_user.username} istifadəçisinin rolu sıfırlandı.")

        return redirect("accounts:manage_roles")

    # Get org-scoped users
    if user_org:
        profiles = UserProfile.objects.filter(organization=user_org).select_related("user")
    else:
        profiles = UserProfile.objects.all().select_related("user")

    # Search
    search = request.GET.get("search", "")
    if search:
        profiles = profiles.filter(
            Q(user__username__icontains=search)
            | Q(user__email__icontains=search)
            | Q(user__first_name__icontains=search)
            | Q(user__last_name__icontains=search)
        )

    # Filter assignable roles: only roles with level lower than current user
    user_level = request.user._highest_role_level()
    assignable_roles = [
        (name, display) for name, display in ProfileRole.CHOICES if ProfileRole.LEVELS.get(name, 0) < user_level
    ]

    context = {
        "profiles": profiles.order_by("-role"),
        "assignable_roles": assignable_roles,
        "search_query": search,
        "organization": user_org,
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
    submissions = Submission.objects.filter(assignment__course__owner=request.user, status="submitted").select_related(
        "assignment", "user", "assignment__course"
    )

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


@login_required
def assigned_exams(request):
    """Assigned exams list for the current user."""
    exams = (
        Exam.objects.filter(
            Q(allowed_users=request.user) | Q(allowed_groups__students=request.user),
            is_active=True,
        )
        .distinct()
        .order_by("-start_datetime")
    )

    search = request.GET.get("search", "")
    if search:
        exams = exams.filter(Q(title__icontains=search) | Q(description__icontains=search))

    context = {
        "exams": exams,
        "search_query": search,
    }
    return render(request, "accounts/assigned_exams.html", context)


@login_required
def assigned_courses(request):
    """Assigned courses list for the current user."""
    courses = (
        Course.objects.filter(
            memberships__user=request.user,
            status="published",
        )
        .distinct()
        .order_by("-created_at")
    )

    search = request.GET.get("search", "")
    if search:
        courses = courses.filter(Q(title__icontains=search) | Q(description__icontains=search))

    context = {
        "courses": courses,
        "search_query": search,
    }
    return render(request, "accounts/assigned_courses.html", context)


@login_required
def pending_review(request):
    """Pending review queue for teachers, grouped by groups."""
    if not getattr(request.user, "is_teacher_or_above", False):
        messages.error(request, "Bu səhifəyə yalnız müəllimlər daxil ola bilər.")
        return redirect("accounts:profile")

    from apps.exams.models import StudentGroup

    search = request.GET.get("search", "")
    filter_type = request.GET.get("type", "all")
    filter_status = request.GET.get("status", "all")

    # Get teacher's groups
    groups = StudentGroup.objects.filter(teacher=request.user).prefetch_related("students")

    grouped_items = []
    for group in groups:
        items = []

        # Exam attempts
        if filter_type in ("all", "exams"):
            attempts = (
                ExamAttempt.objects.filter(
                    exam__author=request.user,
                    student__in=group.students.all(),
                    checked_by_teacher=False,
                    status__in=["submitted", "expired"],
                )
                .exclude(exam__exam_type="test")
                .select_related("exam", "student")
            )

            if search:
                attempts = attempts.filter(
                    Q(student__username__icontains=search)
                    | Q(student__first_name__icontains=search)
                    | Q(student__last_name__icontains=search)
                    | Q(exam__title__icontains=search)
                )

            for attempt in attempts:
                items.append(
                    {
                        "type": "exam",
                        "student": attempt.student,
                        "title": attempt.exam.title,
                        "status": attempt.status,
                        "date": attempt.started_at,
                        "id": attempt.id,
                    }
                )

        # Assignment submissions
        if filter_type in ("all", "assignments"):
            submissions = Submission.objects.filter(
                assignment__course__owner=request.user,
                user__in=group.students.all(),
                status="submitted",
            ).select_related("assignment", "user", "assignment__course")

            if search:
                submissions = submissions.filter(
                    Q(user__username__icontains=search)
                    | Q(user__first_name__icontains=search)
                    | Q(assignment__title__icontains=search)
                    | Q(assignment__course__title__icontains=search)
                )

            for sub in submissions:
                items.append(
                    {
                        "type": "assignment",
                        "student": sub.user,
                        "title": f"{sub.assignment.course.title} - {sub.assignment.title}",
                        "status": sub.status,
                        "date": sub.submitted_at,
                        "id": sub.id,
                    }
                )

        # Sort items by date, newest first; items without dates go to end
        epoch = timezone.datetime.min.replace(tzinfo=timezone.utc)
        items.sort(key=lambda x: x["date"] if x["date"] else epoch, reverse=True)

        if items:
            grouped_items.append(
                {
                    "group": group,
                    "items": items,
                    "count": len(items),
                }
            )

    context = {
        "grouped_items": grouped_items,
        "search_query": search,
        "filter_type": filter_type,
        "filter_status": filter_status,
        "total_count": sum(g["count"] for g in grouped_items),
    }
    return render(request, "accounts/pending_review.html", context)


@login_required
def role_assignment(request):
    """Organization-scoped role assignment UI."""
    if not getattr(request.user, "is_admin_level", False):
        messages.error(request, "Bu səhifəyə yalnız administratorlar daxil ola bilər.")
        return redirect("accounts:profile")

    from apps.organizations.models import Membership, Role
    from apps.organizations.services import get_user_org_role_level, get_user_organization

    org = get_user_organization(request.user)
    if not org:
        messages.error(request, "Təşkilat tapılmadı.")
        return redirect("accounts:profile")

    user_level = get_user_org_role_level(request.user, org)

    # Get org members
    members = (
        Membership.objects.filter(organization=org, is_active=True)
        .select_related("user", "role")
        .order_by("-role__level", "user__username")
    )

    # Get assignable roles (lower than current user's level)
    assignable_roles = Role.objects.filter(organization=org, is_active=True, level__lt=user_level).order_by("-level")

    search = request.GET.get("search", "")
    if search:
        members = members.filter(
            Q(user__username__icontains=search)
            | Q(user__email__icontains=search)
            | Q(user__first_name__icontains=search)
            | Q(user__last_name__icontains=search)
        )

    context = {
        "organization": org,
        "members": members,
        "assignable_roles": assignable_roles,
        "user_level": user_level,
        "search_query": search,
    }
    return render(request, "accounts/role_assignment.html", context)


@login_required
def permission_editor(request):
    """Organization-scoped permission editor UI."""
    if not getattr(request.user, "is_admin_level", False):
        messages.error(request, "Bu səhifəyə yalnız administratorlar daxil ola bilər.")
        return redirect("accounts:profile")

    from apps.organizations.models import Role
    from apps.organizations.permissions import PERMISSION_CATEGORIES
    from apps.organizations.services import get_user_org_role_level, get_user_organization

    org = get_user_organization(request.user)
    if not org:
        messages.error(request, "Təşkilat tapılmadı.")
        return redirect("accounts:profile")

    user_level = get_user_org_role_level(request.user, org)

    roles = Role.objects.filter(organization=org, is_active=True, level__lt=user_level).order_by("-level")

    selected_role_id = request.GET.get("role")
    selected_role = None
    if selected_role_id:
        selected_role = roles.filter(id=selected_role_id).first()

    context = {
        "organization": org,
        "roles": roles,
        "selected_role": selected_role,
        "permission_categories": PERMISSION_CATEGORIES,
        "user_level": user_level,
    }
    return render(request, "accounts/permission_editor.html", context)


# ------------------- AUTHENTICATION VIEWS ------------------- #


def register_view(request):
    """User registration with email verification and organization selection."""
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

            # Handle organization selection
            organization_type = form.cleaned_data.get("organization_type", "individual")
            country = form.cleaned_data.get("country", "")
            organization = None

            if organization_type != "individual":
                org_id = form.cleaned_data.get("organization_id", "")
                org_name_other = form.cleaned_data.get("organization_name_other", "")

                if org_id:
                    # User selected an existing organization
                    from apps.organizations.models import Organization

                    try:
                        organization = Organization.objects.get(id=org_id)
                    except Organization.DoesNotExist:
                        pass
                elif org_name_other:
                    # User entered "Other" - create pending organization
                    from apps.organizations.models import Organization

                    organization = Organization.objects.create(
                        name=org_name_other,
                        org_type=organization_type,
                        country=country,
                        owner=user,
                        status="pending",
                    )

            # Create user profile
            UserProfile.objects.create(
                user=user,
                organization_type=organization_type,
                organization=organization,
                country=country,
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

    # Get organizations for the dropdown (filtered by JS based on country+type)
    from apps.organizations.models import Organization

    organizations = Organization.objects.filter(is_active=True, status="active").values(
        "id", "name", "org_type", "country"
    )

    return render(
        request,
        "accounts/register.html",
        {
            "form": form,
            "organizations": list(organizations),
        },
    )


def verify_code_view(request):
    """Verify email using OTP code."""
    email = request.session.get("pending_verify_email")
    if not email:
        messages.error(request, "Təsdiqləmə üçün email tapılmadı. Yenidən qeydiyyatdan keç.")
        return redirect("accounts:register")

    if request.method == "POST":
        code = request.POST.get("code", "").strip()

        user = User.objects.filter(email=email).first()
        if not user:
            messages.error(request, "User tapılmadı.")
            return redirect("accounts:register")

        otp = EmailOTP.objects.filter(user=user, code=code, is_used=False).order_by("-created_at").first()
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
    EmailOTP.objects.create(user=user, code=code, expires_at=timezone.now() + timedelta(minutes=10))
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
    from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator

    from apps.blog.models import Post

    profile_user = get_object_or_404(User, username=username)

    # Get user's profile
    profile, created = UserProfile.objects.get_or_create(user=profile_user)

    # 1. Posts filtering
    if request.user == profile_user:
        user_posts_list = Post.objects.filter(author=profile_user).select_related("category").order_by("-created_at")
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
    if request.user.is_authenticated and request.user == profile_user and getattr(request.user, "is_teacher", False):
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
            .filter(Q(allowed_users=request.user) | Q(allowed_groups__students=request.user))
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
