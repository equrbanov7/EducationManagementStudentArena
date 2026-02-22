"""
Account views for user dashboards, profile management, authentication, and role assignment.
"""

from datetime import timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import get_user_model, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.core.paginator import Paginator
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.assignments.models import Assignment, Submission
from apps.blog.models import EmailOTP
from apps.blog.utils import generate_otp, send_verify_email
from apps.courses.models import Course
from apps.exams.models import Exam, ExamAttempt
from apps.labs.models import LabSubmission
from apps.projects.models import ProjectSubmission
from core.constants import OrganizationType
from core.tenancy import get_request_organization, scoped_by_organization_id

from .forms import CustomLoginForm, RegisterForm
from .models import ProfileRole, UserProfile

User = get_user_model()
signer = TimestampSigner()
RESULT_FILTER_CHOICES = {"all", "exams", "courses", "labs", "independent"}


def _is_superadmin_user(user):
    return user.is_superuser or getattr(user, "is_superadmin", False)


def _get_active_organization(request):
    """
    Use middleware-selected organization first; fallback to profile organization.
    """
    return get_request_organization(request)


def _tenant_scoped_courses(request, queryset=None):
    base_queryset = queryset if queryset is not None else Course.objects.all()
    return scoped_by_organization_id(
        base_queryset,
        request,
        org_id_field="organization_id",
        fallback_org_field="owner__profile__organization",
    )


def _tenant_scoped_exams(request, queryset=None):
    base_queryset = queryset if queryset is not None else Exam.objects.all()
    return scoped_by_organization_id(
        base_queryset,
        request,
        org_id_field="organization_id",
        fallback_org_field="author__profile__organization",
    )


def _assigned_courses_queryset(request, user):
    return _tenant_scoped_courses(
        request,
        Course.objects.filter(
            memberships__user=user,
            memberships__role="student",
            status="published",
        ).distinct(),
    )


def _assigned_exams_queryset(request, user, *, active_only=True):
    assignment_filter = (
        Q(allowed_users=user)
        | Q(allowed_groups__students=user)
        | Q(
            course__memberships__user=user,
            course__memberships__role="student",
            course__status="published",
        )
    )

    exams = Exam.objects.filter(assignment_filter, is_public=False)
    if active_only:
        exams = exams.filter(is_active=True)

    return _tenant_scoped_exams(request, exams).distinct()


def _normalized_org_name(value):
    return " ".join((value or "").strip().lower().split())


def _role_capabilities(user, profile):
    role = profile.role if profile and profile.role else ProfileRole.MEMBER
    is_superadmin = _is_superadmin_user(user)
    is_student = role in {ProfileRole.STUDENT, ProfileRole.LEAD_STUDENT}
    is_teacher = role in {ProfileRole.TEACHER, ProfileRole.ASSISTANT_TEACHER}
    is_org_admin = role in {ProfileRole.ORG_ADMIN, ProfileRole.ORG_OWNER, ProfileRole.HR}

    can_manage_org = is_superadmin or is_org_admin
    can_view_owned_learning = is_superadmin or is_teacher or is_org_admin
    can_review_submissions = is_superadmin or is_teacher
    can_view_student_assignments = is_student or role == ProfileRole.MEMBER
    can_manage_blog = getattr(user, "is_authenticated", False)

    if is_superadmin:
        allowed_sections = {
            "profile-info",
            "posts",
            "my-results",
            "my-exams",
            "my-courses",
            "courses",
            "assigned-exams",
            "assigned-courses",
            "groups",
            "pending-review",
            "role-assignment",
            "permission-editor",
            "manage-roles",
            "superadmin-organizations",
            "blog",
            "edit-profile",
        }
    elif is_org_admin:
        allowed_sections = {
            "profile-info",
            "posts",
            "my-results",
            "my-exams",
            "my-courses",
            "groups",
            "role-assignment",
            "permission-editor",
            "manage-roles",
            "blog",
            "edit-profile",
        }
    elif is_teacher:
        allowed_sections = {
            "profile-info",
            "posts",
            "my-results",
            "my-exams",
            "my-courses",
            "groups",
            "pending-review",
            "blog",
            "edit-profile",
        }
    elif is_student:
        allowed_sections = {
            "profile-info",
            "posts",
            "my-results",
            "assigned-exams",
            "assigned-courses",
            "blog",
            "edit-profile",
        }
    else:
        allowed_sections = {
            "profile-info",
            "posts",
            "my-results",
            "courses",
            "assigned-exams",
            "assigned-courses",
            "groups",
            "blog",
            "edit-profile",
        }

    if can_manage_blog:
        allowed_sections.add("create-post")

    return {
        "role": role,
        "is_superadmin": is_superadmin,
        "is_student": is_student,
        "is_teacher": is_teacher,
        "is_org_admin": is_org_admin,
        "can_manage_org": can_manage_org,
        "can_view_owned_learning": can_view_owned_learning,
        "can_review_submissions": can_review_submissions,
        "can_view_student_assignments": can_view_student_assignments,
        "can_view_blog": True,
        "can_manage_blog": can_manage_blog,
        "allowed_sections": allowed_sections,
    }


def _collect_actor_permissions(user, organization):
    """
    Return two sets:
    1. effective permissions user currently has in org
    2. explicitly grantable permissions declared as `grant:<permission>` in role permissions
    """
    from apps.organizations.models import Membership

    effective_permissions = set()
    grantable_permissions = set()

    memberships = Membership.objects.filter(user=user, organization=organization, is_active=True).select_related("role")
    for membership in memberships:
        for permission in membership.role.permissions or []:
            if permission.startswith("grant:"):
                grantable_permissions.add(permission.split("grant:", 1)[1].strip())
            else:
                effective_permissions.add(permission)

    return effective_permissions, grantable_permissions


def _ensure_profile_admin_membership(user, organization):
    """
    Backfill membership for org owner/admin profiles that are missing organization membership.
    This prevents false-negative `role.assign` errors for valid tenant admins.
    """
    from apps.organizations.models import Membership, Role

    if _is_superadmin_user(user):
        return

    profile = getattr(user, "profile", None)
    profile_role = getattr(profile, "role", None)
    profile_org = getattr(profile, "organization", None)

    if profile_role not in {ProfileRole.ORG_OWNER, ProfileRole.ORG_ADMIN}:
        return
    if not organization or profile_org != organization:
        return
    if Membership.objects.filter(user=user, organization=organization, is_active=True).exists():
        return

    fallback_role = Role.objects.filter(organization=organization, is_active=True).order_by("-level").first()
    if fallback_role is None:
        return

    Membership.objects.create(
        user=user,
        organization=organization,
        role=fallback_role,
        is_primary=True,
        is_active=True,
        assigned_by=user,
    )


def _permission_is_grantable(permission, effective_permissions, grantable_permissions):
    """
    A permission can be granted when:
    - actor already has that permission, or
    - permission is explicitly grantable via `grant:*`, `grant:category.*` or `grant:exact.permission`.
    """
    from apps.organizations.permissions import has_permission

    effective_list = list(effective_permissions)
    grantable_list = list(grantable_permissions)
    return has_permission(effective_list, permission) or has_permission(grantable_list, permission)


def _map_signup_role_to_profile_role(initial_role):
    role_map = {
        ProfileRole.STUDENT: ProfileRole.STUDENT,
        ProfileRole.MEMBER: ProfileRole.MEMBER,
        ProfileRole.TEACHER: ProfileRole.TEACHER,
        ProfileRole.HR: ProfileRole.HR,
        ProfileRole.ORG_ADMIN: ProfileRole.ORG_ADMIN,
    }
    return role_map.get(initial_role, ProfileRole.MEMBER)


def _map_org_role_to_profile_role(role):
    role_name = (role.name or "").lower()
    if role_name == "member":
        return ProfileRole.MEMBER
    if role_name == "student" or role.level <= 20:
        return ProfileRole.STUDENT
    if "hr" in role_name:
        return ProfileRole.HR
    if role.level >= 80:
        return ProfileRole.ORG_ADMIN
    if any(token in role_name for token in ["teacher", "instructor", "professor", "assistant"]):
        return ProfileRole.TEACHER
    return ProfileRole.MEMBER


def _resolve_membership_role(organization, initial_role):
    from apps.organizations.models import Role

    roles = Role.objects.filter(organization=organization, is_active=True)
    if not roles.exists():
        return None

    if initial_role == ProfileRole.ORG_ADMIN:
        return roles.order_by("-level").first()

    if initial_role == ProfileRole.MEMBER:
        member_role = roles.filter(name="member").first()
        if member_role:
            return member_role
        student_role = roles.filter(name="student").first()
        if student_role:
            return student_role
        return roles.order_by("level").first()

    if initial_role == ProfileRole.STUDENT:
        return roles.filter(name="student").first() or roles.order_by("level").first()

    if initial_role == ProfileRole.TEACHER:
        for role_name in [
            "teacher",
            "instructor",
            "assistant_teacher",
            "professor",
            "associate_professor",
            "assistant",
        ]:
            match = roles.filter(name=role_name).first()
            if match:
                return match
        return roles.filter(level__gte=50).order_by("level").first() or roles.order_by("-level").first()

    if initial_role == ProfileRole.HR:
        hr_role = roles.filter(name="hr").first()
        if hr_role:
            return hr_role
        return Role.objects.create(
            organization=organization,
            name="hr",
            display_name="HR",
            level=65,
            scope_type="organization",
            permissions=["member.view", "member.invite", "member.edit"],
            is_system=False,
            is_active=True,
        )

    return roles.order_by("level").first()


def _get_signup_lookup_payload():
    """
    Return lookup payload for signup institution filtering.
    """
    from apps.organizations.models import Country, Institution

    countries = list(Country.objects.filter(is_active=True).values("code", "name").order_by("name"))
    institutions = list(
        Institution.objects.filter(is_active=True)
        .select_related("country")
        .values("id", "name", "code", "institution_type", "country__code")
        .order_by("name")
    )
    return {
        "countries": countries,
        "institutions": institutions,
    }


def _result_status_badge(status, is_graded=False):
    """Normalize source-specific statuses into submitted/graded/pending."""
    if is_graded:
        return "graded"

    normalized_status = (status or "").lower()
    if normalized_status in {"graded"}:
        return "graded"
    if normalized_status in {"grading", "returned", "rejected", "expired", "draft", "in_progress"}:
        return "pending"
    return "submitted"


def _normalize_results_filter(value):
    normalized = (value or "all").lower()
    if normalized in RESULT_FILTER_CHOICES:
        return normalized
    return "all"


def _append_query_params(url, **params):
    clean_params = {key: value for key, value in params.items() if value not in (None, "")}
    if not clean_params:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{urlencode(clean_params)}"


def _collect_my_results(request, filter_type=None):
    """
    Build a unified result list for current user across exams, assignments, labs, and projects.
    """
    user = request.user
    selected_filter = filter_type if filter_type is not None else request.GET.get("type")
    filter_type = _normalize_results_filter(selected_filter)

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
            score_value = attempt.teacher_score
            if score_value is None and is_auto_test and (attempt.correct_count + attempt.wrong_count) > 0:
                score_value = attempt.score_percent

            items.append(
                {
                    "category": "exams",
                    "title": attempt.exam.title,
                    "kind": attempt.exam.get_exam_type_display() or "Exam",
                    "submitted_at": attempt.finished_at or attempt.started_at,
                    "status": _result_status_badge(
                        attempt.status,
                        is_graded=attempt.checked_by_teacher or score_value is not None,
                    ),
                    "status_raw": attempt.get_status_display(),
                    "score": score_value,
                    "feedback": attempt.teacher_feedback,
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
            items.append(
                {
                    "category": "courses",
                    "title": submission.assignment.title,
                    "kind": submission.assignment.course.title,
                    "submitted_at": submission.submitted_at,
                    "status": _result_status_badge(submission.status),
                    "status_raw": submission.get_status_display(),
                    "score": submission.grade,
                    "feedback": submission.feedback,
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
            items.append(
                {
                    "category": "labs",
                    "title": submission.assignment.lab.title,
                    "kind": submission.assignment.lab.course.title,
                    "submitted_at": submission.submitted_at,
                    "status": _result_status_badge(submission.status),
                    "status_raw": submission.get_status_display(),
                    "score": submission.score,
                    "feedback": submission.feedback,
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
            items.append(
                {
                    "category": "independent",
                    "title": submission.project.title,
                    "kind": submission.project.course.title,
                    "submitted_at": submission.submitted_at,
                    "status": _result_status_badge(submission.status),
                    "status_raw": submission.get_status_display(),
                    "score": submission.grade,
                    "feedback": submission.feedback,
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

    items.sort(key=lambda item: item["submitted_at"] or timezone.now(), reverse=True)
    if filter_type != "all":
        counts = {
            "exams": ExamAttempt.objects.filter(
                user=user,
                exam_id__in=scoped_exam_ids,
                status__in=["submitted", "expired"],
            ).count(),
            "courses": Submission.objects.filter(
                user=user,
                assignment__course_id__in=scoped_course_ids,
            ).count(),
            "labs": LabSubmission.objects.filter(
                assignment__student=user,
                assignment__lab__course_id__in=scoped_course_ids,
            ).count(),
            "independent": ProjectSubmission.objects.filter(
                student=user,
                project__course_id__in=scoped_course_ids,
            ).count(),
        }
    counts["all"] = counts["exams"] + counts["courses"] + counts["labs"] + counts["independent"]

    return items, counts, filter_type


@login_required
def teacher_dashboard(request):
    """
    Teacher dashboard with widgets showing courses, pending grading, and stats.
    """
    profile = getattr(request.user, "profile", None)
    capabilities = _role_capabilities(request.user, profile)
    if not capabilities["can_review_submissions"]:
        messages.error(request, "Bu səhifəyə yalnız müəllimlər daxil ola bilər.")
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
        due_date__gte=timezone.now(),
        status__in=["published", "active"],
    ).order_by("due_date")[:5]

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
def user_profile(request):
    """
    User profile page with edit functionality.
    Ensures profile exists before rendering.
    Now accessible to ALL users (not just teachers).
    """
    from apps.blog.models import Category, Post

    # Ensure profile exists (get_or_create for safety)
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    capabilities = _role_capabilities(request.user, profile)

    # Get active section from URL parameter (default: profile-info)
    requested_section = request.GET.get("section", "profile-info")
    allowed_sections = capabilities["allowed_sections"]
    active_section = requested_section if requested_section in allowed_sections else "profile-info"

    if request.method == "POST":
        if request.POST.get("profile_form") != "edit-profile":
            target_section = request.GET.get("section") or request.POST.get("section") or active_section
            if target_section not in allowed_sections:
                target_section = "profile-info"
            return redirect(f"{reverse('accounts:profile')}?section={target_section}")

        first_name = (request.POST.get("first_name", request.user.first_name) or "").strip()
        last_name = (request.POST.get("last_name", request.user.last_name) or "").strip()
        new_email = (request.POST.get("email", request.user.email) or "").strip().lower()
        student_university_name = (
            request.POST.get("student_university_name", profile.student_university_name) or ""
        ).strip()
        student_school_identifier = (
            request.POST.get("student_school_identifier", profile.student_school_identifier) or ""
        ).strip()

        if not first_name or not last_name or not new_email:
            messages.error(request, "Ad, soyad və email sahələri boş buraxıla bilməz.")
            return redirect("accounts:profile" + "?section=edit-profile")

        if new_email and User.objects.exclude(pk=request.user.pk).filter(email__iexact=new_email).exists():
            messages.error(request, "Bu email artıq istifadə olunur.")
            return redirect("accounts:profile" + "?section=edit-profile")

        # Update user info
        request.user.first_name = first_name
        request.user.last_name = last_name
        request.user.email = new_email
        request.user.save()

        # Update profile
        profile.phone = (request.POST.get("phone", profile.phone) or "").strip()
        profile.bio = (request.POST.get("bio", profile.bio) or "").strip()
        profile.location = (request.POST.get("location", profile.location) or "").strip()
        profile.student_university_name = student_university_name
        profile.student_school_identifier = student_school_identifier

        # Handle avatar upload
        if "avatar" in request.FILES:
            profile.avatar = request.FILES["avatar"]

        # Only admins can change supervisor_code
        if getattr(request.user, "is_admin_level", False):
            profile.supervisor_code = request.POST.get("supervisor_code", "")

        if profile.role == ProfileRole.STUDENT and not (
            profile.student_university_name or profile.student_school_identifier
        ):
            messages.error(
                request,
                "Student rolu üçün universitet adı və ya məktəb identifikatoru mütləqdir.",
            )
            return redirect("accounts:profile" + "?section=edit-profile")

        profile.save()

        messages.success(request, "Profil uğurla yeniləndi!")
        return redirect("accounts:profile")

    # Get user's roles
    user_roles = request.user.get_all_roles() if hasattr(request.user, "get_all_roles") else []

    teacher_courses = _tenant_scoped_courses(request, Course.objects.filter(owner=request.user))
    created_courses_qs = teacher_courses.order_by("-created_at")
    enrolled_courses_qs = _assigned_courses_queryset(request, request.user).order_by("-created_at")
    my_exams_qs = _tenant_scoped_exams(request, Exam.objects.filter(author=request.user)).order_by("-created_at")

    if capabilities["is_student"]:
        visible_courses_qs = enrolled_courses_qs
    else:
        visible_courses_qs = created_courses_qs

    my_courses = list(visible_courses_qs[:10])
    courses_count = visible_courses_qs.count()

    my_created_courses = []
    my_created_courses_count = 0
    my_exams = []
    my_exams_count = 0
    if capabilities["can_view_owned_learning"]:
        my_created_courses = list(created_courses_qs[:10])
        my_created_courses_count = created_courses_qs.count()
        my_exams = list(my_exams_qs[:10])
        my_exams_count = my_exams_qs.count()

    user_posts = None
    posts_count = 0
    categories = []
    if capabilities["can_manage_blog"]:
        user_posts_qs = Post.objects.filter(author=request.user).select_related("category").order_by("-created_at")
        posts_count = user_posts_qs.count()
        user_posts = Paginator(user_posts_qs, 6).get_page(request.GET.get("page"))
        categories = Category.objects.all().order_by("name")

    assigned_exams_count = 0
    assigned_courses_count = 0
    my_results_count = 0
    assigned_exam_items = []
    assigned_courses = []
    my_result_items = []
    my_result_counts = {
        "all": 0,
        "exams": 0,
        "courses": 0,
        "labs": 0,
        "independent": 0,
    }
    my_results_active_filter = "all"
    if capabilities["can_view_student_assignments"]:
        assigned_exams_qs = _assigned_exams_queryset(request, request.user, active_only=True).order_by(
            "-start_datetime",
            "-created_at",
        )
        assigned_exams_count = assigned_exams_qs.count()
        assigned_courses_count = enrolled_courses_qs.count()
        assigned_courses = list(enrolled_courses_qs[:20])
        for exam in assigned_exams_qs[:20]:
            can_start_without_code, _ = exam.can_user_start(request.user, code=None)
            assigned_exam_items.append(
                {
                    "exam": exam,
                    "requires_code": bool(exam.access_code and not can_start_without_code),
                }
            )

        my_result_items, my_result_counts, my_results_active_filter = _collect_my_results(
            request,
            filter_type=request.GET.get("results_type"),
        )
        my_results_count = my_result_counts.get("all", 0)

    pending_review_count = 0
    if capabilities["can_review_submissions"]:
        pending_review_count = (
            ExamAttempt.objects.filter(
                exam__in=my_exams_qs,
                status__in=["submitted", "expired"],
                checked_by_teacher=False,
            )
            .exclude(exam__exam_type="test")
            .count()
        )
        pending_review_count += Submission.objects.filter(
            assignment__course__in=teacher_courses,
            status="submitted",
        ).count()
        pending_review_count += ProjectSubmission.objects.filter(
            project__course__in=teacher_courses,
            status="pending",
        ).count()
        pending_review_count += LabSubmission.objects.filter(
            assignment__lab__course__in=teacher_courses,
            status__in=["submitted", "late"],
        ).count()

    section_titles = {
        "profile-info": "Profil Məlumatları",
        "posts": "Postlarım",
        "create-post": "Yeni Post Yarat",
        "courses": "Kurslarım",
        "my-exams": "İmtahanlarım",
        "my-courses": "Yaratdığım Kurslar",
        "assigned-exams": "Təyin olunmuş imtahanlar",
        "assigned-courses": "Təyin olunmuş kurslar",
        "my-results": "My Results",
        "groups": "Qruplar",
        "pending-review": "To Review",
        "role-assignment": "Role təyin et",
        "permission-editor": "Permission-lar",
        "manage-roles": "Rolları idarə et",
        "superadmin-organizations": "Superadmin Nəzarəti",
        "blog": "Blog",
        "edit-profile": "Profili Redaktə Et",
    }

    shortcut_sections = []
    if "create-post" in allowed_sections:
        shortcut_sections.append(
            {
                "section": "create-post",
                "title": section_titles["create-post"],
                "url": reverse("create_post"),
                "icon": "fas fa-plus-circle",
                "source_url": reverse("create_post"),
                "description": "Yeni postu standart redaktorda yaratmaq üçün aşağıdakı düymədən istifadə edin.",
                "action_label": "Post yarat",
            }
        )
    if "groups" in allowed_sections:
        shortcut_sections.append(
            {
                "section": "groups",
                "title": section_titles["groups"],
                "url": reverse("exams:teacher_group_list"),
                "icon": "fas fa-users",
                "source_url": reverse("exams:teacher_group_list"),
                "description": "Qrup idarəetməsini açmaq üçün aşağıdakı düyməyə keçin.",
                "action_label": "Qrupları aç",
            }
        )
    if "pending-review" in allowed_sections:
        shortcut_sections.append(
            {
                "section": "pending-review",
                "title": section_titles["pending-review"],
                "url": reverse("accounts:pending_review"),
                "icon": "fas fa-tasks",
                "source_url": reverse("accounts:pending_review"),
                "description": "Yoxlanılacaq işlərin tam siyahısını açmaq üçün düymədən istifadə edin.",
                "action_label": "Yoxlama səhifəsini aç",
            }
        )
    if "role-assignment" in allowed_sections:
        shortcut_sections.append(
            {
                "section": "role-assignment",
                "title": section_titles["role-assignment"],
                "url": reverse("accounts:role_assignment"),
                "icon": "fas fa-user-shield",
                "source_url": reverse("accounts:role_assignment"),
                "description": "Rol təyinatı üçün idarəetmə səhifəsi ayrıca açılır.",
                "action_label": "Role təyin et",
            }
        )
    if "permission-editor" in allowed_sections:
        shortcut_sections.append(
            {
                "section": "permission-editor",
                "title": section_titles["permission-editor"],
                "url": reverse("accounts:permission_editor"),
                "icon": "fas fa-key",
                "source_url": reverse("accounts:permission_editor"),
                "description": "Permission redaktəsi üçün idarəetmə səhifəsi ayrıca açılır.",
                "action_label": "Permission-ları aç",
            }
        )
    if "manage-roles" in allowed_sections:
        shortcut_sections.append(
            {
                "section": "manage-roles",
                "title": section_titles["manage-roles"],
                "url": reverse("accounts:manage_roles"),
                "icon": "fas fa-user-cog",
                "source_url": reverse("accounts:manage_roles"),
                "description": "Klassik rol idarəetmə səhifəsini açmaq üçün düymədən istifadə edin.",
                "action_label": "Rolları idarə et",
            }
        )
    if "superadmin-organizations" in allowed_sections:
        shortcut_sections.append(
            {
                "section": "superadmin-organizations",
                "title": section_titles["superadmin-organizations"],
                "url": reverse("accounts:superadmin_organizations"),
                "icon": "fas fa-building",
                "source_url": reverse("accounts:superadmin_organizations"),
                "description": "Superadmin təşkilat nəzarəti ayrıca səhifədədir.",
                "action_label": "Nəzarət səhifəsini aç",
            }
        )
    if capabilities["can_view_blog"]:
        shortcut_sections.append(
            {
                "section": "blog",
                "title": section_titles["blog"],
                "url": reverse("home"),
                "icon": "fas fa-blog",
                "source_url": reverse("home"),
                "description": "Blog lentinə keçmək üçün aşağıdakı düyməyə klik edin.",
                "action_label": "Blogu aç",
            }
        )

    active_section_title = section_titles.get(active_section, "Profil")

    context = {
        "profile": profile,
        "user_roles": user_roles,
        "active_section": active_section,
        "active_section_title": active_section_title,
        "allowed_sections": allowed_sections,
        "profile_base_url": reverse("accounts:profile"),
        "shortcut_sections": shortcut_sections,
        "role_capabilities": capabilities,
        "user_posts": user_posts,
        "posts_count": posts_count,
        "categories": categories,
        "my_courses": my_courses,
        "courses_count": courses_count,
        "my_exams": my_exams,
        "my_exams_count": my_exams_count,
        "my_created_courses": my_created_courses,
        "my_created_courses_count": my_created_courses_count,
        "assigned_exams_count": assigned_exams_count,
        "assigned_courses_count": assigned_courses_count,
        "assigned_exam_items": assigned_exam_items,
        "assigned_courses": assigned_courses,
        "my_results_count": my_results_count,
        "my_result_items": my_result_items,
        "my_result_counts": my_result_counts,
        "my_results_active_filter": my_results_active_filter,
        "pending_review_count": pending_review_count,
        "is_teacher": capabilities["is_teacher"],
        "is_admin": capabilities["can_manage_org"],
        "is_superadmin": capabilities["is_superadmin"],
        "can_manage_org": capabilities["can_manage_org"],
        "can_view_owned_learning": capabilities["can_view_owned_learning"],
        "can_review_submissions": capabilities["can_review_submissions"],
        "can_view_blog": capabilities["can_view_blog"],
        "can_manage_blog": capabilities["can_manage_blog"],
        "can_view_student_assignments": capabilities["can_view_student_assignments"],
    }

    return render(request, "accounts/profile.html", context)


@login_required
def manage_roles(request):
    """
    Role assignment view for admin-level users.
    Uses UserProfile.role (RBAC) instead of Django Groups.
    Organization-scoped: only shows users from the same org.
    """
    is_superadmin = _is_superadmin_user(request.user)
    if not is_superadmin and not getattr(request.user, "is_admin_level", False):
        messages.error(request, "Bu səhifəyə yalnız administratorlar daxil ola bilər.")
        return redirect("home")

    from apps.accounts.models import ProfileRole

    # Get user's active organization for scoping
    user_org = _get_active_organization(request)
    if not is_superadmin and not user_org:
        messages.error(request, "Rol idarəetməsi üçün aktiv təşkilat tapılmadı.")
        return redirect("accounts:profile")

    if request.method == "POST":
        user_id = request.POST.get("user_id")
        role_name = request.POST.get("role_name")
        action = request.POST.get("action")  # "assign" or "remove"

        target_user = get_object_or_404(User, id=user_id)

        # Ensure target is in same organization
        target_org = getattr(getattr(target_user, "profile", None), "organization", None)
        if not is_superadmin and target_org != user_org:
            messages.error(request, "Yalnız öz təşkilatınızdakı istifadəçiləri idarə edə bilərsiniz.")
            return redirect("accounts:manage_roles")

        # Check hierarchy: can't assign role >= own level
        if not request.user.can_assign_role(role_name):
            messages.error(request, "Bu rolu təyin etmək icazəniz yoxdur.")
            return redirect("accounts:manage_roles")

        target_profile, _ = UserProfile.objects.get_or_create(user=target_user)

        valid_roles = {choice[0] for choice in ProfileRole.CHOICES}
        if action == "assign" and role_name:
            if role_name not in valid_roles:
                messages.error(request, "Seçilən rol etibarlı deyil.")
                return redirect("accounts:manage_roles")
            target_profile.role = role_name
            target_profile.save()
            messages.success(
                request,
                f"{target_profile.get_role_display()} rolu {target_user.username} istifadəçisinə təyin edildi.",
            )
        elif action == "remove":
            target_profile.role = ProfileRole.MEMBER
            target_profile.save()
            messages.success(request, f"{target_user.username} istifadəçisinin rolu sıfırlandı.")

        return redirect("accounts:manage_roles")

    # Get org-scoped users
    if is_superadmin:
        profiles = UserProfile.objects.all().select_related("user")
    else:
        profiles = UserProfile.objects.filter(organization=user_org).select_related("user")

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
    profile = getattr(request.user, "profile", None)
    capabilities = _role_capabilities(request.user, profile)
    if not capabilities["can_review_submissions"]:
        messages.error(request, "Bu səhifəyə yalnız müəllimlər daxil ola bilər.")
        return redirect("home")

    # Get filter parameters
    course_id = request.GET.get("course")
    assignment_id = request.GET.get("assignment")

    teacher_courses = _tenant_scoped_courses(request, Course.objects.filter(owner=request.user))

    # Base query
    submissions = Submission.objects.filter(
        assignment__course__in=teacher_courses,
        status="submitted",
    ).select_related("assignment", "user", "assignment__course")

    # Apply filters
    if course_id:
        submissions = submissions.filter(assignment__course_id=course_id)
    if assignment_id:
        submissions = submissions.filter(assignment_id=assignment_id)

    # Order by oldest first
    submissions = submissions.order_by("submitted_at")

    # Get courses for filter dropdown
    courses = teacher_courses

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
    profile = getattr(request.user, "profile", None)
    capabilities = _role_capabilities(request.user, profile)
    if not capabilities["can_view_student_assignments"]:
        messages.error(request, "Bu səhifə yalnız tələbə/member rolları üçün nəzərdə tutulub.")
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
        messages.error(request, "Bu səhifə yalnız tələbə/member rolları üçün nəzərdə tutulub.")
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
        messages.error(request, "Bu səhifə yalnız tələbə/member rolları üçün nəzərdə tutulub.")
        return redirect("accounts:profile")

    items, counts, active_filter = _collect_my_results(request, filter_type=request.GET.get("type"))
    context = {
        "items": items,
        "counts": counts,
        "active_filter": active_filter,
    }
    return render(request, "accounts/my_results.html", context)


@login_required
def my_result_detail(request, item_type, item_id):
    """Detail page for a single item from My Results."""
    profile = getattr(request.user, "profile", None)
    capabilities = _role_capabilities(request.user, profile)
    if not capabilities["can_view_student_assignments"]:
        messages.error(request, "Bu səhifə yalnız tələbə/member rolları üçün nəzərdə tutulub.")
        return redirect("accounts:profile")

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
        return redirect("exams:exam_result", slug=attempt.exam.slug, attempt_id=attempt.id)

    if normalized_type == "courses":
        submission = get_object_or_404(
            Submission.objects.select_related("assignment", "assignment__course"),
            id=item_id,
            user=request.user,
            assignment__course_id__in=tenant_course_ids,
        )
        context = {
            "item_type": "courses",
            "item_title": submission.assignment.title,
            "item_subtitle": submission.assignment.course.title,
            "submitted_at": submission.submitted_at,
            "status": _result_status_badge(submission.status),
            "status_raw": submission.get_status_display(),
            "score": submission.grade,
            "feedback": submission.feedback,
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
        context = {
            "item_type": "labs",
            "item_title": submission.assignment.lab.title,
            "item_subtitle": submission.assignment.lab.course.title,
            "submitted_at": submission.submitted_at,
            "status": _result_status_badge(submission.status),
            "status_raw": submission.get_status_display(),
            "score": submission.score,
            "feedback": submission.feedback,
            "content_text": submission.submission_text,
            "submission_link": submission.submission_link,
            "submission_file": submission.submission_file,
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
        context = {
            "item_type": "independent",
            "item_title": submission.project.title,
            "item_subtitle": submission.project.course.title,
            "submitted_at": submission.submitted_at,
            "status": _result_status_badge(submission.status),
            "status_raw": submission.get_status_display(),
            "score": submission.grade,
            "feedback": submission.feedback,
            "content_text": submission.content,
            "submission_file": submission.file,
            "back_url": back_url,
        }
        return render(request, "accounts/my_result_detail.html", context)

    messages.error(request, "Nəticə tipi tanınmadı.")
    return redirect(back_url)


@login_required
def pending_review(request):
    """Teacher review queue across exams, assignments, labs, and projects."""
    profile = getattr(request.user, "profile", None)
    capabilities = _role_capabilities(request.user, profile)
    if not capabilities["can_review_submissions"]:
        messages.error(request, "Bu səhifəyə yalnız müəllimlər daxil ola bilər.")
        return redirect("accounts:profile")

    search = request.GET.get("search", "")
    filter_type = request.GET.get("type", "all")
    filter_status = request.GET.get("status", "all")

    teacher_courses = _tenant_scoped_courses(request, Course.objects.filter(owner=request.user))
    teacher_exams = _tenant_scoped_exams(request, Exam.objects.filter(author=request.user))

    student_memberships = []
    if teacher_courses.exists():
        from apps.courses.models import CourseMembership

        student_memberships = CourseMembership.objects.filter(
            course__in=teacher_courses,
            role="student",
        ).values("course_id", "user_id", "group_name")

    group_map = {
        (membership["course_id"], membership["user_id"]): membership["group_name"] or ""
        for membership in student_memberships
    }

    items = []

    if filter_type in {"all", "exams"}:
        attempts = (
            ExamAttempt.objects.filter(
                exam__in=teacher_exams,
                status__in=["submitted", "expired"],
                checked_by_teacher=False,
            )
            .exclude(exam__exam_type="test")
            .select_related("exam", "user", "exam__course")
        )
        if search:
            attempts = attempts.filter(
                Q(user__username__icontains=search)
                | Q(user__first_name__icontains=search)
                | Q(user__last_name__icontains=search)
                | Q(exam__title__icontains=search)
            )
        for attempt in attempts:
            course = attempt.exam.course
            items.append(
                {
                    "type": "exam",
                    "student": attempt.user,
                    "title": attempt.exam.title,
                    "course_title": course.title if course else "-",
                    "group_name": group_map.get((course.id, attempt.user_id), "") if course else "",
                    "status": attempt.status,
                    "date": attempt.started_at,
                    "action_url": reverse(
                        "exams:teacher_check_attempt",
                        kwargs={"slug": attempt.exam.slug, "attempt_id": attempt.id},
                    ),
                    "action_label": "Yoxla",
                }
            )

    if filter_type in {"all", "assignments"}:
        submissions = Submission.objects.filter(
            assignment__course__in=teacher_courses,
            status="submitted",
        ).select_related("assignment", "user", "assignment__course")
        if search:
            submissions = submissions.filter(
                Q(user__username__icontains=search)
                | Q(user__first_name__icontains=search)
                | Q(user__last_name__icontains=search)
                | Q(assignment__title__icontains=search)
                | Q(assignment__course__title__icontains=search)
            )
        for submission in submissions:
            course = submission.assignment.course
            items.append(
                {
                    "type": "assignment",
                    "student": submission.user,
                    "title": submission.assignment.title,
                    "course_title": course.title,
                    "group_name": group_map.get((course.id, submission.user_id), ""),
                    "status": submission.status,
                    "date": submission.submitted_at,
                    "action_url": reverse(
                        "assignments:review_assignment_submissions",
                        kwargs={"pk": submission.assignment_id},
                    ),
                    "action_label": "Tapşırığa keç",
                }
            )

    if filter_type in {"all", "projects"}:
        project_submissions = ProjectSubmission.objects.filter(
            project__course__in=teacher_courses,
            status="pending",
        ).select_related("project", "project__course", "student")
        if search:
            project_submissions = project_submissions.filter(
                Q(student__username__icontains=search)
                | Q(student__first_name__icontains=search)
                | Q(student__last_name__icontains=search)
                | Q(project__title__icontains=search)
                | Q(project__course__title__icontains=search)
            )
        for submission in project_submissions:
            course = submission.project.course
            items.append(
                {
                    "type": "project",
                    "student": submission.student,
                    "title": submission.project.title,
                    "course_title": course.title,
                    "group_name": group_map.get((course.id, submission.student_id), ""),
                    "status": submission.status,
                    "date": submission.submitted_at,
                    "action_url": reverse(
                        "projects:review_project_submissions",
                        kwargs={"pk": submission.project_id},
                    ),
                    "action_label": "Layihəyə keç",
                }
            )

    if filter_type in {"all", "labs"}:
        lab_submissions = LabSubmission.objects.filter(
            assignment__lab__course__in=teacher_courses,
            status__in=["submitted", "late"],
        ).select_related("assignment", "assignment__lab", "assignment__lab__course", "assignment__student")
        if search:
            lab_submissions = lab_submissions.filter(
                Q(assignment__student__username__icontains=search)
                | Q(assignment__student__first_name__icontains=search)
                | Q(assignment__student__last_name__icontains=search)
                | Q(assignment__lab__title__icontains=search)
                | Q(assignment__lab__course__title__icontains=search)
            )
        for submission in lab_submissions:
            student = submission.assignment.student
            course = submission.assignment.lab.course
            items.append(
                {
                    "type": "lab",
                    "student": student,
                    "title": submission.assignment.lab.title,
                    "course_title": course.title,
                    "group_name": group_map.get((course.id, student.id), ""),
                    "status": submission.status,
                    "date": submission.submitted_at,
                    "action_url": reverse(
                        "labs:grade_submission_page",
                        kwargs={"pk": submission.id},
                    ),
                    "action_label": "Qiymətləndir",
                }
            )

    if filter_status != "all":
        items = [item for item in items if item["status"] == filter_status]

    items.sort(key=lambda item: (item["date"] is not None, item["date"] or timezone.now()), reverse=True)

    context = {
        "review_items": items,
        "search_query": search,
        "filter_type": filter_type,
        "filter_status": filter_status,
        "total_count": len(items),
    }
    return render(request, "accounts/pending_review.html", context)


@login_required
def role_assignment(request):
    """Organization-scoped role assignment UI with strict server-side permission checks."""
    from apps.organizations.models import Membership, Role
    from apps.organizations.permissions import has_permission
    from apps.organizations.services import create_audit_log, get_user_org_role_level

    org = _get_active_organization(request)
    if not org:
        messages.error(request, "Aktiv təşkilat tapılmadı.")
        return redirect("accounts:profile")

    _ensure_profile_admin_membership(request.user, org)

    is_superadmin = _is_superadmin_user(request.user)
    user_level = 999 if is_superadmin else get_user_org_role_level(request.user, org)
    actor_permissions, _ = _collect_actor_permissions(request.user, org)
    can_assign_roles = is_superadmin or has_permission(list(actor_permissions), "role.assign")

    # Teacher+ can at least assign Student/Member roles.
    # Default teacher membership level is 50 in org role templates.
    if not is_superadmin and user_level < 50:
        messages.error(request, "Bu səhifəyə yalnız müəllim və yuxarı səviyyə daxil ola bilər.")
        return redirect("accounts:profile")

    if request.method == "POST":
        action = request.POST.get("action", "update_member")
        role_id = request.POST.get("role_id")
        target_role = get_object_or_404(Role, id=role_id, organization=org, is_active=True)

        if not is_superadmin and target_role.level >= user_level:
            messages.error(request, "Yalnız sizdən aşağı səviyyəli rolları təyin edə bilərsiniz.")
            return redirect("accounts:role_assignment")

        # Teacher+ can assign student/member even without explicit role.assign permission.
        teacher_can_assign_basic = not is_superadmin and user_level >= 50 and target_role.name in {"student", "member"}

        if not (can_assign_roles or teacher_can_assign_basic):
            messages.error(request, "Rol təyin etmək üçün lazımi icazəniz yoxdur.")
            return redirect("accounts:role_assignment")

        if action == "attach_user":
            user_id = request.POST.get("user_id")
            target_user = get_object_or_404(User, id=user_id, is_active=True)
            target_profile, _ = UserProfile.objects.get_or_create(user=target_user)

            if target_profile.organization and target_profile.organization != org:
                messages.error(request, "İstifadəçi artıq başqa təşkilata bağlıdır.")
                return redirect("accounts:role_assignment")

            if not is_superadmin:
                requested_org = target_profile.requested_organization
                requested_name = _normalized_org_name(target_profile.requested_organization_name)
                is_requested_for_org = (requested_org is not None and requested_org == org) or (
                    requested_org is None and requested_name and requested_name == _normalized_org_name(org.name)
                )
                if not is_requested_for_org:
                    messages.error(
                        request,
                        "Bu istifadəçi sizin təşkilatınızı signup zamanı seçməyib. Yalnız həmin pending istifadəçiləri əlavə edə bilərsiniz.",
                    )
                    return redirect("accounts:role_assignment")

            membership, created = Membership.objects.get_or_create(
                user=target_user,
                organization=org,
                defaults={
                    "role": target_role,
                    "assigned_by": request.user,
                    "is_primary": True,
                    "is_active": True,
                },
            )
            if not created:
                if not is_superadmin and membership.role.level >= user_level:
                    messages.error(request, "Bu istifadəçinin rolunu dəyişmək icazəniz yoxdur.")
                    return redirect("accounts:role_assignment")
                membership.role = target_role
                membership.assigned_by = request.user
                membership.is_active = True
                membership.save(update_fields=["role", "assigned_by", "is_active", "updated_at"])

            target_profile.organization = org
            target_profile.organization_type = org.org_type
            target_profile.role = _map_org_role_to_profile_role(target_role)
            target_profile.requested_organization = org
            target_profile.requested_organization_name = org.name
            target_profile.save(
                update_fields=[
                    "organization",
                    "organization_type",
                    "role",
                    "requested_organization",
                    "requested_organization_name",
                    "updated_at",
                ]
            )

            create_audit_log(
                user=request.user,
                organization=org,
                action="update",
                resource_type="membership",
                resource_id=membership.id,
                resource_repr=str(membership),
                old_values=None,
                new_values={"role": target_role.name, "attached_user": target_user.username},
                request=request,
            )

            messages.success(
                request, f"{target_user.username} təşkilata əlavə edildi və `{target_role.display_name}` rolu verildi."
            )
            return redirect("accounts:role_assignment")

        # Default action: update existing org membership
        membership_id = request.POST.get("membership_id")
        target_membership = get_object_or_404(
            Membership.objects.select_related("role", "user"),
            id=membership_id,
            organization=org,
            is_active=True,
        )

        if not is_superadmin and target_membership.role.level >= user_level:
            messages.error(request, "Yalnız sizdən aşağı səviyyəli istifadəçilərin rolunu dəyişə bilərsiniz.")
            return redirect("accounts:role_assignment")

        old_role_name = target_membership.role.name
        target_membership.role = target_role
        target_membership.assigned_by = request.user
        target_membership.save(update_fields=["role", "assigned_by", "updated_at"])

        target_profile, _ = UserProfile.objects.get_or_create(user=target_membership.user)
        target_profile.role = _map_org_role_to_profile_role(target_role)
        target_profile.organization = org
        target_profile.organization_type = org.org_type
        target_profile.requested_organization = org
        target_profile.requested_organization_name = org.name
        target_profile.save(
            update_fields=[
                "role",
                "organization",
                "organization_type",
                "requested_organization",
                "requested_organization_name",
                "updated_at",
            ]
        )

        create_audit_log(
            user=request.user,
            organization=org,
            action="update",
            resource_type="membership",
            resource_id=target_membership.id,
            resource_repr=str(target_membership),
            old_values={"role": old_role_name},
            new_values={"role": target_role.name},
            request=request,
        )

        messages.success(
            request, f"{target_membership.user.username} üçün rol `{target_role.display_name}` olaraq yeniləndi."
        )
        return redirect("accounts:role_assignment")

    members = (
        Membership.objects.filter(organization=org, is_active=True)
        .select_related("user", "role")
        .order_by("-role__level", "user__username")
    )
    if not is_superadmin:
        members = members.filter(role__level__lt=user_level)

    assignable_roles = Role.objects.filter(organization=org, is_active=True).order_by("-level")
    if not is_superadmin:
        assignable_roles = assignable_roles.filter(level__lt=user_level)

    search = request.GET.get("search", "")
    if search:
        members = members.filter(
            Q(user__username__icontains=search)
            | Q(user__email__icontains=search)
            | Q(user__first_name__icontains=search)
            | Q(user__last_name__icontains=search)
        )

    unassigned_search = request.GET.get("unassigned_search", "")
    unassigned_users = UserProfile.objects.filter(user__is_active=True, organization__isnull=True).select_related(
        "user",
        "requested_organization",
    )
    if not is_superadmin:
        unassigned_users = unassigned_users.filter(
            Q(requested_organization=org)
            | Q(
                requested_organization__isnull=True,
                requested_organization_name__iexact=org.name,
            )
        )
    if unassigned_search:
        unassigned_users = unassigned_users.filter(
            Q(user__username__icontains=unassigned_search)
            | Q(user__email__icontains=unassigned_search)
            | Q(user__first_name__icontains=unassigned_search)
            | Q(user__last_name__icontains=unassigned_search)
        )

    context = {
        "organization": org,
        "members": members,
        "assignable_roles": assignable_roles,
        "user_level": user_level,
        "search_query": search,
        "unassigned_search_query": unassigned_search,
        "unassigned_users": unassigned_users.order_by("user__username")[:100],
        "is_superadmin": is_superadmin,
        "can_assign_roles": can_assign_roles or user_level >= 50,
    }
    return render(request, "accounts/role_assignment.html", context)


@login_required
def permission_editor(request):
    """Organization-scoped permission editor with add/remove enforcement."""
    from apps.organizations.models import Role
    from apps.organizations.permissions import PERMISSION_CATEGORIES, get_all_permissions, has_permission
    from apps.organizations.services import create_audit_log, get_user_org_role_level

    org = _get_active_organization(request)
    if not org:
        messages.error(request, "Aktiv təşkilat tapılmadı.")
        return redirect("accounts:profile")

    _ensure_profile_admin_membership(request.user, org)

    is_superadmin = _is_superadmin_user(request.user)
    user_level = 999 if is_superadmin else get_user_org_role_level(request.user, org)
    actor_permissions, grantable_permissions = _collect_actor_permissions(request.user, org)

    can_manage_permissions = is_superadmin or has_permission(list(actor_permissions), "role.assign")
    if not is_superadmin and not can_manage_permissions:
        messages.error(request, "Permission idarəetməsi üçün `role.assign` səlahiyyəti tələb olunur.")
        return redirect("accounts:profile")

    roles = Role.objects.filter(organization=org, is_active=True).order_by("-level")
    if not is_superadmin:
        roles = roles.filter(level__lt=user_level)

    selected_role = None
    selected_role_id = request.GET.get("role")
    if request.method == "POST":
        selected_role_id = request.POST.get("role_id")
        selected_permission = request.POST.get("permission")
        action = request.POST.get("action")
        selected_role = get_object_or_404(Role, id=selected_role_id, organization=org, is_active=True)

        if not is_superadmin and selected_role.level >= user_level:
            messages.error(request, "Yalnız sizdən aşağı səviyyəli rolların permission-larını idarə edə bilərsiniz.")
            return redirect(f"{request.path}?role={selected_role.id}")

        all_permissions = set(get_all_permissions())
        if selected_permission not in all_permissions:
            messages.error(request, "Yanlış permission seçimi.")
            return redirect(f"{request.path}?role={selected_role.id}")

        role_permissions = list(selected_role.permissions or [])
        role_permissions_set = set(role_permissions)
        old_permissions = sorted(role_permissions_set)

        if action == "add":
            if (
                not _permission_is_grantable(selected_permission, actor_permissions, grantable_permissions)
                and not is_superadmin
            ):
                messages.error(request, "Yalnız özünüzdə olan və ya grant edilə bilən permission-ları verə bilərsiniz.")
                return redirect(f"{request.path}?role={selected_role.id}")
            role_permissions_set.add(selected_permission)
            result_message = f"`{selected_permission}` permission-u əlavə edildi."
        elif action == "remove":
            role_permissions_set.discard(selected_permission)
            result_message = f"`{selected_permission}` permission-u silindi."
        else:
            messages.error(request, "Naməlum əməliyyat.")
            return redirect(f"{request.path}?role={selected_role.id}")

        selected_role.permissions = sorted(role_permissions_set)
        selected_role.save(update_fields=["permissions", "updated_at"])

        create_audit_log(
            user=request.user,
            organization=org,
            action="update",
            resource_type="role",
            resource_id=selected_role.id,
            resource_repr=selected_role.display_name,
            old_values={"permissions": old_permissions},
            new_values={"permissions": selected_role.permissions},
            request=request,
        )

        messages.success(request, result_message)
        return redirect(f"{request.path}?role={selected_role.id}")

    if selected_role_id:
        selected_role = roles.filter(id=selected_role_id).first()

    context = {
        "organization": org,
        "roles": roles,
        "selected_role": selected_role,
        "permission_categories": PERMISSION_CATEGORIES,
        "user_level": user_level,
        "actor_permissions": sorted(actor_permissions),
        "grantable_permissions": sorted(grantable_permissions),
        "can_manage_permissions": can_manage_permissions,
    }
    return render(request, "accounts/permission_editor.html", context)


@login_required
def superadmin_organizations(request):
    """
    Superadmin oversight screen for all organizations with suspend/unsuspend controls.
    """
    if not _is_superadmin_user(request.user):
        messages.error(request, "Bu səhifəyə yalnız superadmin daxil ola bilər.")
        return redirect("accounts:profile")

    from apps.organizations.models import Organization

    if request.method == "POST":
        organization = get_object_or_404(Organization, id=request.POST.get("organization_id"))
        action = request.POST.get("action")
        reason = (request.POST.get("reason") or "").strip()

        if action == "suspend":
            organization.status = "suspended"
            organization.is_active = False
            organization.suspended_at = timezone.now()
            organization.suspension_reason = reason
            organization.save(update_fields=["status", "is_active", "suspended_at", "suspension_reason", "updated_at"])
            messages.success(request, f"`{organization.name}` təşkilatı dayandırıldı.")
        elif action == "unsuspend":
            organization.status = "active"
            organization.is_active = True
            organization.suspended_at = None
            organization.suspension_reason = ""
            organization.save(update_fields=["status", "is_active", "suspended_at", "suspension_reason", "updated_at"])
            messages.success(request, f"`{organization.name}` təşkilatı yenidən aktiv edildi.")
        else:
            messages.error(request, "Naməlum əməliyyat.")

        return redirect("accounts:superadmin_organizations")

    organizations = (
        Organization.objects.select_related("owner")
        .annotate(active_member_count=Count("memberships", filter=Q(memberships__is_active=True)))
        .order_by("name")
    )

    all_modules = [
        "accounts",
        "organizations",
        "courses",
        "exams",
        "assignments",
        "projects",
        "labs",
        "live_exam",
        "blog",
        "audit",
    ]

    context = {
        "organizations": organizations,
        "all_modules": all_modules,
    }
    return render(request, "accounts/superadmin_organizations.html", context)


# ------------------- AUTHENTICATION VIEWS ------------------- #


class CustomLoginView(LoginView):
    """Login view with custom form and suspended-organization checks."""

    template_name = "accounts/login.html"
    authentication_form = CustomLoginForm
    redirect_authenticated_user = True


def register_view(request):
    """User registration with organization bootstrap and immediate login eligibility."""
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            from apps.organizations.models import Country, Membership, Organization, Role

            with transaction.atomic():
                user = form.save(commit=False)
                user.email = form.cleaned_data["email"]
                user.set_password(form.cleaned_data["password"])
                user.is_active = True
                user.save()

                organization_type = form.cleaned_data["organization_type"]
                country_code = form.cleaned_data.get("country", "")
                country_obj = Country.objects.filter(code=country_code).first()
                country_name = country_obj.name if country_obj else country_code
                institution = form.cleaned_data.get("institution")
                join_organization = form.cleaned_data.get("join_organization")
                institution_not_listed_name = form.cleaned_data.get("institution_not_listed_name", "")
                organization_identifier = form.cleaned_data.get("organization_identifier", "")
                organization_license_identifier = form.cleaned_data.get("organization_license_identifier", "")
                initial_role = form.cleaned_data.get("initial_role", ProfileRole.MEMBER)

                organization = None
                requested_organization = None
                requested_organization_name = ""
                resolved_identifier = organization_identifier
                if organization_type == OrganizationType.INDIVIDUAL:
                    if join_organization is not None:
                        organization = join_organization
                        requested_organization = join_organization
                        requested_organization_name = join_organization.name
                else:
                    organization_name = institution.name if institution else institution_not_listed_name
                    requested_organization_name = organization_name
                    resolved_identifier = organization_identifier or (institution.code if institution else "")

                    if initial_role == ProfileRole.ORG_ADMIN:
                        organization = Organization.objects.create(
                            name=organization_name,
                            org_type=organization_type,
                            country=country_name,
                            owner=user,
                            status="active",
                            is_active=True,
                            organization_identifier=resolved_identifier,
                            license_identifier=organization_license_identifier,
                        )
                        requested_organization = organization
                        requested_organization_name = organization.name
                    else:
                        requested_organization = (
                            Organization.objects.filter(
                                name__iexact=organization_name,
                                org_type=organization_type,
                                country=country_name,
                                is_active=True,
                            )
                            .order_by("name")
                            .first()
                        )
                        if requested_organization is not None:
                            requested_organization_name = requested_organization.name

                profile, _ = UserProfile.objects.get_or_create(user=user)
                profile.organization_type = organization.org_type if organization is not None else organization_type
                profile.organization = organization
                profile.requested_organization = requested_organization
                profile.requested_organization_name = requested_organization_name
                profile.country = country_name
                profile.role = _map_signup_role_to_profile_role(initial_role)
                profile.student_university_name = (
                    requested_organization_name
                    if organization_type
                    in {
                        OrganizationType.UNIVERSITY,
                        OrganizationType.SCHOOL,
                        OrganizationType.COURSE_CENTER,
                    }
                    else ""
                )
                profile.student_school_identifier = (
                    resolved_identifier if organization_type == OrganizationType.SCHOOL else ""
                )
                profile.save()

                if organization is not None:
                    membership_role = _resolve_membership_role(organization, initial_role)
                    if membership_role is None:
                        membership_role = Role.objects.create(
                            organization=organization,
                            name="member",
                            display_name="Member",
                            level=20,
                            scope_type="organization",
                            permissions=["course.view", "exam.view", "analytics.view_own"],
                            is_system=False,
                            is_active=True,
                        )

                    Membership.objects.create(
                        user=user,
                        organization=organization,
                        role=membership_role,
                        is_primary=True,
                        is_active=True,
                        assigned_by=user,
                    )

                    request.session["active_organization"] = organization.slug

            if organization is None and requested_organization_name:
                messages.success(
                    request,
                    "Qeydiyyat tamamlandı. Hesabınız yaradıldı və təşkilat müraciətiniz qeydə alındı.",
                )
            else:
                messages.success(
                    request,
                    "Qeydiyyat tamamlandı. İndi eyni istifadəçi adı/email və şifrə ilə daxil ola bilərsiniz.",
                )
            return redirect("accounts:login")
    else:
        form = RegisterForm()

    return render(
        request,
        "accounts/register.html",
        {
            "form": form,
            "lookup_payload": _get_signup_lookup_payload(),
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
        return redirect("accounts:login")

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
        return redirect("accounts:login")
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
        assigned_count = _assigned_exams_queryset(request, request.user, active_only=True).count()

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
