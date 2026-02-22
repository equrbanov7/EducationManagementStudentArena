"""
Account views for user dashboards, profile management, authentication, and role assignment.
"""

from datetime import timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import get_user_model, logout
from django.contrib.auth.models import Group
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.core.paginator import Paginator
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone
from django.utils.translation import pgettext_lazy

from apps.assignments.models import Assignment, Submission
from apps.blog.models import EmailOTP
from apps.blog.utils import generate_otp, send_verify_email
from apps.courses.models import Course, CourseMembership
from apps.exams.forms import StudentGroupForm
from apps.exams.models import Exam, ExamAttempt, StudentGroup
from apps.labs.models import Lab, LabSubmission
from apps.projects.models import Project, ProjectSubmission
from core.constants import OrganizationType
from core.tenancy import get_request_organization, scoped_by_organization_id

from .forms import CustomLoginForm, RegisterForm
from .models import ProfileRole, UserProfile

User = get_user_model()
signer = TimestampSigner()
RESULT_FILTER_CHOICES = {"all", "exams", "courses", "labs", "independent"}
ASSIGNED_TASK_FILTER_CHOICES = {"all", "courses", "assignments", "labs", "independent"}
PENDING_REVIEW_TYPE_CHOICES = {"all", "exams", "assignments", "projects", "labs"}
PENDING_REVIEW_STATUS_CHOICES = {"all", "submitted", "expired", "pending", "late"}
PROFILE_ROLE_LABELS = dict(ProfileRole.CHOICES)
PROFILE_ROLE_NAMES = set(PROFILE_ROLE_LABELS.keys())


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


def _user_has_any_role(user, role_names):
    if not user:
        return False

    normalized = set(role_names or [])
    if not normalized:
        return False

    if hasattr(user, "has_role"):
        return any(user.has_role(role_name) for role_name in normalized)

    profile = getattr(user, "profile", None)
    current_role = getattr(profile, "role", None)
    return current_role in normalized


def _extract_profile_roles_for_user(user):
    if not user:
        return [ProfileRole.MEMBER]

    roles = []
    if hasattr(user, "get_all_roles"):
        candidates = user.get_all_roles()
    else:
        profile = getattr(user, "profile", None)
        candidates = [getattr(profile, "role", None)]

    for role_name in candidates:
        if role_name in PROFILE_ROLE_NAMES and role_name not in roles:
            roles.append(role_name)

    if not roles:
        roles = [ProfileRole.MEMBER]
    return roles


def _assignable_profile_roles_for_user(user):
    if _is_superadmin_user(user):
        return [(name, display) for name, display in ProfileRole.CHOICES if name != ProfileRole.SUPERADMIN]

    user_level = user._highest_role_level() if hasattr(user, "_highest_role_level") else 0
    return [
        (name, display)
        for name, display in ProfileRole.CHOICES
        if ProfileRole.LEVELS.get(name, 0) < user_level
    ]


def _decorate_manage_role_profiles(profiles, *, actor_level, is_superadmin):
    for profile in profiles:
        current_roles = _extract_profile_roles_for_user(profile.user)
        profile.current_roles = current_roles
        profile.current_role_items = [
            {
                "name": role_name,
                "label": PROFILE_ROLE_LABELS.get(role_name, role_name),
            }
            for role_name in current_roles
        ]

        target_level = profile.user._highest_role_level() if hasattr(profile.user, "_highest_role_level") else 0
        profile.can_edit_roles = is_superadmin or actor_level > target_level


def _sync_user_role_groups(user, desired_role_names, *, editable_role_names=None):
    desired = set(desired_role_names or []) & PROFILE_ROLE_NAMES
    editable = set(editable_role_names or PROFILE_ROLE_NAMES) & PROFILE_ROLE_NAMES

    current_role_group_names = set(user.groups.filter(name__in=PROFILE_ROLE_NAMES).values_list("name", flat=True))
    removable_role_group_names = current_role_group_names & editable

    role_names_to_remove = removable_role_group_names - desired
    role_names_to_add = desired - current_role_group_names

    if role_names_to_remove:
        groups_to_remove = list(Group.objects.filter(name__in=role_names_to_remove))
        if groups_to_remove:
            user.groups.remove(*groups_to_remove)

    if role_names_to_add:
        existing_role_groups = set(Group.objects.filter(name__in=role_names_to_add).values_list("name", flat=True))
        missing_role_names = [role_name for role_name in role_names_to_add if role_name not in existing_role_groups]
        if missing_role_names:
            Group.objects.bulk_create([Group(name=role_name) for role_name in missing_role_names], ignore_conflicts=True)

        groups_to_add = list(Group.objects.filter(name__in=role_names_to_add))
        if groups_to_add:
            user.groups.add(*groups_to_add)


def _resolve_next_url(request, fallback_url):
    next_url = (request.POST.get("next") or request.GET.get("next") or "").strip()
    if not next_url:
        return fallback_url

    if url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return fallback_url


def _role_capabilities(user, profile):
    role = profile.role if profile and profile.role else ProfileRole.MEMBER
    is_superadmin = _is_superadmin_user(user)
    is_student = _user_has_any_role(user, {ProfileRole.STUDENT, ProfileRole.LEAD_STUDENT})
    is_teacher = _user_has_any_role(user, {ProfileRole.TEACHER, ProfileRole.ASSISTANT_TEACHER})
    is_org_admin = _user_has_any_role(user, {ProfileRole.ORG_ADMIN, ProfileRole.ORG_OWNER, ProfileRole.HR})

    can_manage_org = is_superadmin or is_org_admin
    can_view_owned_learning = is_superadmin or is_teacher or is_org_admin
    can_review_submissions = is_superadmin or is_teacher
    can_view_student_assignments = is_student or _user_has_any_role(user, {ProfileRole.MEMBER})
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
    else:
        allowed_sections = {
            "profile-info",
            "posts",
            "blog",
            "edit-profile",
        }
        allowed_sections.add("my-results")

        if is_org_admin:
            allowed_sections.update(
                {
                    "my-exams",
                    "my-courses",
                    "groups",
                    "role-assignment",
                    "permission-editor",
                    "manage-roles",
                }
            )

        if is_teacher:
            allowed_sections.update({"my-exams", "my-courses", "groups", "pending-review"})

        if is_student:
            allowed_sections.update({"assigned-exams", "assigned-courses"})

        if not (is_student or is_teacher or is_org_admin):
            allowed_sections.update({"courses", "assigned-exams", "assigned-courses", "groups"})

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


def _query_string(**params):
    clean_params = {key: value for key, value in params.items() if value not in (None, "")}
    return urlencode(clean_params)


def _normalize_assigned_tasks_filter(value):
    normalized = (value or "all").lower()
    if normalized in ASSIGNED_TASK_FILTER_CHOICES:
        return normalized
    return "all"


def _csv_to_int_set(raw_value):
    values = set()
    for chunk in (raw_value or "").split(","):
        token = chunk.strip()
        if token.isdigit():
            values.add(int(token))
    return values


def _csv_to_lower_token_set(raw_value):
    return {chunk.strip().lower() for chunk in (raw_value or "").split(",") if chunk.strip()}


def _task_state_badge_data(state):
    normalized_state = (state or "open").lower()
    if normalized_state == "upcoming":
        return "Gözləyir", "upcoming"
    if normalized_state == "closed":
        return "Bağlı", "closed"
    return "Aktiv", "open"


def _collect_assigned_tasks(request, filter_type=None):
    """
    Build a unified assigned task list across courses, assignments, labs, and projects.
    """
    user = request.user
    selected_filter = filter_type if filter_type is not None else request.GET.get("assigned_type")
    filter_type = _normalize_assigned_tasks_filter(selected_filter)
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
    counts = {"courses": 0, "assignments": 0, "labs": 0, "independent": 0}

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
    ):
        state_label, state_badge = _task_state_badge_data(state)
        items.append(
            {
                "category": category,
                "title": title,
                "kind": kind,
                "icon": icon,
                "detail_url": detail_url,
                "assigned_at": assigned_at,
                "deadline": deadline,
                "state_label": state_label,
                "state_badge": state_badge,
                "description": description,
                "sort_at": assigned_at or deadline or now,
            }
        )

    counts["courses"] = assigned_courses_qs.count()
    if filter_type in {"all", "courses"}:
        for course in assigned_courses_qs:
            append_item(
                category="courses",
                title=course.title,
                kind="Kurs",
                icon="fas fa-graduation-cap",
                detail_url=_append_query_params(
                    reverse("courses:course_dashboard", kwargs={"course_id": course.id}),
                    from_section="assigned-exams",
                    assigned_type=filter_type,
                ),
                assigned_at=course.created_at,
                state="open" if course.status == "published" else "closed",
                description=course.description,
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
                icon="fas fa-file-signature",
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

    labs_qs = Lab.objects.filter(course_id__in=course_ids, status="published").select_related("course").order_by("-created_at")
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
                icon="fas fa-flask",
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
                icon="fas fa-project-diagram",
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

    counts["all"] = counts["courses"] + counts["assignments"] + counts["labs"] + counts["independent"]
    return items, counts, filter_type


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
                    "kind": attempt.exam.get_exam_type_display()
                    or pgettext_lazy("accounts.my_results.kind", "exam"),
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

    teacher_courses = _tenant_scoped_courses(request, Course.objects.filter(owner=request.user))
    teacher_exams = _tenant_scoped_exams(request, Exam.objects.filter(author=request.user))

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

    items = []

    if normalized_type in {"all", "exams"}:
        attempts = (
            ExamAttempt.objects.filter(
                exam__in=teacher_exams,
                status__in=["submitted", "expired"],
                checked_by_teacher=False,
            )
            .exclude(exam__exam_type="test")
            .select_related("exam", "user", "exam__course")
        )
        if search_query:
            attempts = attempts.filter(
                Q(user__username__icontains=search_query)
                | Q(user__first_name__icontains=search_query)
                | Q(user__last_name__icontains=search_query)
                | Q(exam__title__icontains=search_query)
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
                    "action_label": pgettext_lazy("profile.pending_review.action", "review"),
                }
            )

    if normalized_type in {"all", "assignments"}:
        submissions = Submission.objects.filter(
            assignment__course__in=teacher_courses,
            status="submitted",
        ).select_related("assignment", "user", "assignment__course")
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
                    "course_title": course.title,
                    "group_name": group_map.get((course.id, submission.user_id), ""),
                    "status": submission.status,
                    "date": submission.submitted_at,
                    "action_url": reverse(
                        "assignments:review_assignment_submissions",
                        kwargs={"pk": submission.assignment_id},
                    ),
                    "action_label": pgettext_lazy("profile.pending_review.action", "open_assignment"),
                }
            )

    if normalized_type in {"all", "projects"}:
        project_submissions = ProjectSubmission.objects.filter(
            project__course__in=teacher_courses,
            status="pending",
        ).select_related("project", "project__course", "student")
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
                    "course_title": course.title,
                    "group_name": group_map.get((course.id, submission.student_id), ""),
                    "status": submission.status,
                    "date": submission.submitted_at,
                    "action_url": reverse(
                        "projects:review_project_submissions",
                        kwargs={"pk": submission.project_id},
                    ),
                    "action_label": pgettext_lazy("profile.pending_review.action", "open_project"),
                }
            )

    if normalized_type in {"all", "labs"}:
        lab_submissions = LabSubmission.objects.filter(
            assignment__lab__course__in=teacher_courses,
            status__in=["submitted", "late"],
        ).select_related("assignment", "assignment__lab", "assignment__lab__course", "assignment__student")
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
                    "course_title": course.title,
                    "group_name": group_map.get((course.id, student.id), ""),
                    "status": submission.status,
                    "date": submission.submitted_at,
                    "action_url": reverse(
                        "labs:grade_submission_page",
                        kwargs={"pk": submission.id},
                    ),
                    "action_label": pgettext_lazy("profile.pending_review.action", "grade"),
                }
            )

    if normalized_status != "all":
        items = [item for item in items if item["status"] == normalized_status]

    items.sort(key=lambda item: (item["date"] is not None, item["date"] or timezone.now()), reverse=True)
    return items, search_query, normalized_type, normalized_status


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
            messages.error(request, pgettext_lazy("accounts.profile_edit.message", "required_fields_missing"))
            return redirect("accounts:profile" + "?section=edit-profile")

        if new_email and User.objects.exclude(pk=request.user.pk).filter(email__iexact=new_email).exists():
            messages.error(request, pgettext_lazy("accounts.profile_edit.message", "email_already_in_use"))
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

        if _user_has_any_role(request.user, {ProfileRole.STUDENT, ProfileRole.LEAD_STUDENT}) and not (
            profile.student_university_name or profile.student_school_identifier
        ):
            messages.error(
                request,
                pgettext_lazy("accounts.profile_edit.message", "student_university_or_school_required"),
            )
            return redirect("accounts:profile" + "?section=edit-profile")

        profile.save()

        messages.success(request, pgettext_lazy("accounts.profile_edit.message", "profile_updated_successfully"))
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
    assigned_tasks_count = 0
    my_results_count = 0
    assigned_task_items = []
    assigned_task_counts = {
        "all": 0,
        "courses": 0,
        "assignments": 0,
        "labs": 0,
        "independent": 0,
    }
    assigned_tasks_active_filter = "all"
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
        assigned_task_items, assigned_task_counts, assigned_tasks_active_filter = _collect_assigned_tasks(
            request,
            filter_type=request.GET.get("assigned_type"),
        )
        assigned_tasks_count = assigned_task_counts.get("all", 0)
        assigned_courses_count = assigned_task_counts.get("courses", 0)
        assigned_courses = list(enrolled_courses_qs[:20])

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

    teacher_groups = []
    teacher_groups_count = 0
    teacher_groups_payload = {}
    group_form = None
    can_multi_assign_group_teachers = False
    groups_section_return_url = f"{reverse('accounts:profile')}?section=groups"
    if "groups" in allowed_sections:
        active_organization = _get_active_organization(request)
        if active_organization is not None:
            current_role_level = (
                request.user._highest_role_level()
                if hasattr(request.user, "_highest_role_level")
                else ProfileRole.LEVELS.get(getattr(profile, "role", ProfileRole.MEMBER), 0)
            )
            can_multi_assign_group_teachers = capabilities["is_superadmin"] or (
                current_role_level >= ProfileRole.LEVELS.get(ProfileRole.TEACHER, 60)
            )
            group_form = StudentGroupForm(
                actor=request.user,
                organization=active_organization,
                can_multi_assign_teachers=can_multi_assign_group_teachers,
                is_superadmin=capabilities["is_superadmin"],
                auto_id="group_%s",
            )

            teacher_groups_qs = (
                StudentGroup.objects.filter(organization=active_organization)
                .select_related("teacher")
                .prefetch_related("students", "teachers")
                .order_by("name")
            )
            can_view_all_groups = capabilities["is_superadmin"] or capabilities["can_manage_org"]
            if not can_view_all_groups:
                teacher_groups_qs = teacher_groups_qs.filter(Q(teacher=request.user) | Q(teachers=request.user)).distinct()

            teacher_groups_count = teacher_groups_qs.count()
            teacher_groups = list(teacher_groups_qs[:20])

            for group in teacher_groups:
                student_ids = [student.id for student in group.students.all()]
                teacher_ids = [teacher.id for teacher in group.teachers.all()]
                if group.teacher_id and group.teacher_id not in teacher_ids:
                    teacher_ids.append(group.teacher_id)

                teacher_groups_payload[str(group.id)] = {
                    "name": group.name,
                    "primary_teacher": group.teacher_id,
                    "students": student_ids,
                    "teachers": teacher_ids,
                }

    pending_review_items = []
    pending_review_search_query = ""
    pending_review_filter_type = "all"
    pending_review_filter_status = "all"
    if "pending-review" in allowed_sections:
        (
            pending_review_items,
            pending_review_search_query,
            pending_review_filter_type,
            pending_review_filter_status,
        ) = _collect_pending_review_items(request)

    role_assignment_section = {
        "organization": None,
        "members": [],
        "assignable_roles": [],
        "search_query": "",
        "unassigned_search_query": "",
        "unassigned_users": [],
        "can_assign_roles": False,
        "access_denied_message": "",
        "members_page_param": "role_members_page",
        "members_pagination_query": "",
        "unassigned_page_param": "role_pending_page",
        "unassigned_pagination_query": "",
    }
    permission_editor_section = {
        "organization": None,
        "roles": [],
        "selected_role": None,
        "permission_categories": {},
        "actor_permissions": [],
        "grantable_permissions": [],
        "can_manage_permissions": False,
        "access_denied_message": "",
    }
    manage_roles_section = {
        "profiles": [],
        "assignable_roles": [],
        "search_query": "",
        "organization": None,
        "access_denied_message": "",
        "profiles_page_param": "manage_roles_page",
        "profiles_pagination_query": "",
    }
    superadmin_organizations_section = {
        "organizations": [],
        "all_modules": [],
        "organizations_page_param": "superadmin_org_page",
        "organizations_pagination_query": "",
    }

    management_org = None
    management_user_level = 0
    management_actor_permissions = set()
    management_grantable_permissions = set()
    management_can_assign_roles = False
    management_min_level_ok = False
    if "role-assignment" in allowed_sections or "permission-editor" in allowed_sections:
        from apps.organizations.permissions import has_permission
        from apps.organizations.services import get_user_org_role_level

        management_org = _get_active_organization(request)
        if management_org:
            _ensure_profile_admin_membership(request.user, management_org)
            management_user_level = (
                999 if capabilities["is_superadmin"] else get_user_org_role_level(request.user, management_org)
            )
            management_actor_permissions, management_grantable_permissions = _collect_actor_permissions(
                request.user,
                management_org,
            )
            management_can_assign_roles = capabilities["is_superadmin"] or has_permission(
                list(management_actor_permissions),
                "role.assign",
            )
            management_min_level_ok = capabilities["is_superadmin"] or management_user_level >= 50

    if "role-assignment" in allowed_sections:
        from apps.organizations.models import Membership, Role

        role_assignment_search = request.GET.get("search", "")
        role_assignment_unassigned_search = request.GET.get("unassigned_search", "")
        role_assignment_section.update(
            {
                "organization": management_org,
                "search_query": role_assignment_search,
                "unassigned_search_query": role_assignment_unassigned_search,
                "can_assign_roles": management_can_assign_roles or management_user_level >= 50,
            }
        )

        if management_org is None:
            role_assignment_section["access_denied_message"] = "Aktiv təşkilat tapılmadı."
        elif not management_min_level_ok:
            role_assignment_section["access_denied_message"] = (
                "Bu bölmə üçün minimum müəllim və ya daha yüksək səviyyə tələb olunur."
            )
        else:
            members = (
                Membership.objects.filter(organization=management_org, is_active=True)
                .select_related("user", "role")
                .order_by("-role__level", "user__username")
            )
            if not capabilities["is_superadmin"]:
                members = members.filter(role__level__lt=management_user_level)

            assignable_roles = Role.objects.filter(organization=management_org, is_active=True).order_by("-level")
            if not capabilities["is_superadmin"]:
                assignable_roles = assignable_roles.filter(level__lt=management_user_level)

            if role_assignment_search:
                members = members.filter(
                    Q(user__username__icontains=role_assignment_search)
                    | Q(user__email__icontains=role_assignment_search)
                    | Q(user__first_name__icontains=role_assignment_search)
                    | Q(user__last_name__icontains=role_assignment_search)
                )

            unassigned_users = UserProfile.objects.filter(user__is_active=True, organization__isnull=True).select_related(
                "user",
                "requested_organization",
            )
            if not capabilities["is_superadmin"]:
                unassigned_users = unassigned_users.filter(
                    Q(requested_organization=management_org)
                    | Q(
                        requested_organization__isnull=True,
                        requested_organization_name__iexact=management_org.name,
                    )
                )
            if role_assignment_unassigned_search:
                unassigned_users = unassigned_users.filter(
                    Q(user__username__icontains=role_assignment_unassigned_search)
                    | Q(user__email__icontains=role_assignment_unassigned_search)
                    | Q(user__first_name__icontains=role_assignment_unassigned_search)
                    | Q(user__last_name__icontains=role_assignment_unassigned_search)
                )

            role_assignment_members_page = request.GET.get("role_members_page")
            role_assignment_members_page_obj = Paginator(members, 12).get_page(role_assignment_members_page)

            role_assignment_pending_page = request.GET.get("role_pending_page")
            role_assignment_pending_page_obj = Paginator(unassigned_users.order_by("user__username"), 12).get_page(
                role_assignment_pending_page
            )

            role_assignment_section["members"] = role_assignment_members_page_obj
            role_assignment_section["assignable_roles"] = assignable_roles
            role_assignment_section["unassigned_users"] = role_assignment_pending_page_obj
            role_assignment_section["members_pagination_query"] = _query_string(
                section="role-assignment",
                search=role_assignment_search,
                unassigned_search=role_assignment_unassigned_search,
            )
            role_assignment_section["unassigned_pagination_query"] = _query_string(
                section="role-assignment",
                search=role_assignment_search,
                unassigned_search=role_assignment_unassigned_search,
            )

    if "permission-editor" in allowed_sections:
        from apps.organizations.models import Role
        from apps.organizations.permissions import PERMISSION_CATEGORIES

        selected_permission_role_id = request.GET.get("role")
        permission_editor_section.update(
            {
                "organization": management_org,
                "permission_categories": PERMISSION_CATEGORIES,
                "actor_permissions": sorted(management_actor_permissions),
                "grantable_permissions": sorted(management_grantable_permissions),
                "can_manage_permissions": management_can_assign_roles,
            }
        )

        if management_org is None:
            permission_editor_section["access_denied_message"] = "Aktiv təşkilat tapılmadı."
        elif not capabilities["is_superadmin"] and not management_can_assign_roles:
            permission_editor_section["access_denied_message"] = (
                "Permission idarəetməsi üçün `role.assign` səlahiyyəti tələb olunur."
            )
        else:
            roles = Role.objects.filter(organization=management_org, is_active=True).order_by("-level")
            if not capabilities["is_superadmin"]:
                roles = roles.filter(level__lt=management_user_level)

            selected_permission_role = None
            if selected_permission_role_id:
                selected_permission_role = roles.filter(id=selected_permission_role_id).first()
            if selected_permission_role is None:
                selected_permission_role = roles.first()

            permission_editor_section["roles"] = roles
            permission_editor_section["selected_role"] = selected_permission_role

    if "manage-roles" in allowed_sections:
        manage_roles_search = request.GET.get("manage_roles_search", "")
        manage_roles_org = _get_active_organization(request)
        manage_roles_user_level = request.user._highest_role_level() if hasattr(request.user, "_highest_role_level") else 0
        assignable_roles = _assignable_profile_roles_for_user(request.user)
        manage_roles_section.update(
            {
                "search_query": manage_roles_search,
                "organization": manage_roles_org,
                "assignable_roles": assignable_roles,
                "post_next_url": _append_query_params(
                    reverse("accounts:profile"),
                    section="manage-roles",
                    manage_roles_search=manage_roles_search,
                ),
            }
        )

        if capabilities["is_superadmin"]:
            manage_role_profiles = UserProfile.objects.all().select_related("user").prefetch_related("user__groups")
        elif manage_roles_org is None:
            manage_roles_section["access_denied_message"] = "Rol idarəetməsi üçün aktiv təşkilat tapılmadı."
            manage_role_profiles = UserProfile.objects.none()
        else:
            manage_role_profiles = (
                UserProfile.objects.filter(organization=manage_roles_org)
                .select_related("user")
                .prefetch_related("user__groups")
            )

        if manage_roles_search:
            manage_role_profiles = manage_role_profiles.filter(
                Q(user__username__icontains=manage_roles_search)
                | Q(user__email__icontains=manage_roles_search)
                | Q(user__first_name__icontains=manage_roles_search)
                | Q(user__last_name__icontains=manage_roles_search)
            )

        manage_roles_page = request.GET.get("manage_roles_page")
        manage_roles_page_obj = Paginator(manage_role_profiles.order_by("user__username"), 12).get_page(manage_roles_page)
        _decorate_manage_role_profiles(
            manage_roles_page_obj.object_list,
            actor_level=manage_roles_user_level,
            is_superadmin=capabilities["is_superadmin"],
        )

        manage_roles_section["profiles"] = manage_roles_page_obj
        manage_roles_section["profiles_pagination_query"] = _query_string(
            section="manage-roles",
            manage_roles_search=manage_roles_search,
        )

    if "superadmin-organizations" in allowed_sections:
        from apps.organizations.models import Organization

        superadmin_organizations_queryset = (
            Organization.objects.select_related("owner")
            .annotate(active_member_count=Count("memberships", filter=Q(memberships__is_active=True)))
            .order_by("name")
        )
        superadmin_org_page = request.GET.get("superadmin_org_page")
        superadmin_organizations_section["organizations"] = Paginator(superadmin_organizations_queryset, 12).get_page(
            superadmin_org_page
        )
        superadmin_organizations_section["all_modules"] = [
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
        superadmin_organizations_section["organizations_pagination_query"] = _query_string(
            section="superadmin-organizations"
        )

    section_titles = {
        "profile-info": pgettext_lazy("profile.section", "profile_info"),
        "posts": pgettext_lazy("profile.section", "posts"),
        "create-post": pgettext_lazy("profile.section", "create_post"),
        "courses": pgettext_lazy("profile.section", "my_courses"),
        "my-exams": pgettext_lazy("profile.section", "my_exams"),
        "my-courses": pgettext_lazy("profile.section", "my_created_courses"),
        "assigned-exams": pgettext_lazy("profile.section", "assigned_tasks"),
        "assigned-courses": pgettext_lazy("profile.section", "assigned_courses"),
        "my-results": pgettext_lazy("profile.section", "my_results"),
        "groups": pgettext_lazy("profile.section", "groups"),
        "pending-review": pgettext_lazy("profile.section", "pending_review"),
        "role-assignment": pgettext_lazy("profile.section", "role_assignment"),
        "permission-editor": pgettext_lazy("profile.section", "permissions"),
        "manage-roles": pgettext_lazy("profile.section", "manage_roles"),
        "superadmin-organizations": pgettext_lazy("profile.section", "superadmin_control"),
        "blog": pgettext_lazy("profile.section", "blog"),
        "edit-profile": pgettext_lazy("profile.section", "edit_profile"),
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
                "description": pgettext_lazy("profile.shortcut", "create_post_description"),
                "action_label": pgettext_lazy("profile.shortcut", "create_post_action"),
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
                "description": pgettext_lazy("profile.shortcut", "open_blog_description"),
                "action_label": pgettext_lazy("profile.shortcut", "open_blog_action"),
            }
        )

    active_section_title = section_titles.get(active_section, pgettext_lazy("profile.sidebar", "title"))

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
        "assigned_tasks_count": assigned_tasks_count,
        "assigned_task_items": assigned_task_items,
        "assigned_task_counts": assigned_task_counts,
        "assigned_tasks_active_filter": assigned_tasks_active_filter,
        "assigned_courses": assigned_courses,
        "my_results_count": my_results_count,
        "my_result_items": my_result_items,
        "my_result_counts": my_result_counts,
        "my_results_active_filter": my_results_active_filter,
        "pending_review_count": pending_review_count,
        "teacher_groups": teacher_groups,
        "teacher_groups_count": teacher_groups_count,
        "teacher_groups_payload": teacher_groups_payload,
        "group_form": group_form,
        "can_multi_assign_group_teachers": can_multi_assign_group_teachers,
        "groups_section_return_url": groups_section_return_url,
        "pending_review_items": pending_review_items,
        "pending_review_search_query": pending_review_search_query,
        "pending_review_filter_type": pending_review_filter_type,
        "pending_review_filter_status": pending_review_filter_status,
        "pending_review_total_count": len(pending_review_items),
        "role_assignment_section": role_assignment_section,
        "permission_editor_section": permission_editor_section,
        "manage_roles_section": manage_roles_section,
        "superadmin_organizations_section": superadmin_organizations_section,
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
    Multi-role assignment view for admin-level users.
    Primary role is stored in UserProfile.role; additional roles are synced via Django groups.
    Organization-scoped: only shows users from the same org.
    """
    is_superadmin = _is_superadmin_user(request.user)
    if not is_superadmin and not getattr(request.user, "is_admin_level", False):
        messages.error(request, pgettext_lazy("accounts.manage_roles.message", "admin_only"))
        return redirect("home")

    # Get user's active organization for scoping
    user_org = _get_active_organization(request)
    if not is_superadmin and not user_org:
        messages.error(request, pgettext_lazy("accounts.manage_roles.message", "active_organization_not_found"))
        return redirect("accounts:profile")

    actor_level = request.user._highest_role_level() if hasattr(request.user, "_highest_role_level") else 0
    assignable_roles = _assignable_profile_roles_for_user(request.user)
    assignable_role_names = {name for name, _ in assignable_roles}

    if request.method == "POST":
        user_id = request.POST.get("user_id")
        action = request.POST.get("action")  # "assign" or "remove"
        next_url = _resolve_next_url(request, reverse("accounts:manage_roles"))

        if not user_id:
            messages.error(request, pgettext_lazy("accounts.manage_roles.message", "user_not_selected"))
            return redirect(next_url)

        target_user = get_object_or_404(User, id=user_id)

        # Ensure target is in same organization
        target_org = getattr(getattr(target_user, "profile", None), "organization", None)
        if not is_superadmin and target_org != user_org:
            messages.error(request, pgettext_lazy("accounts.manage_roles.message", "manage_only_own_org_users"))
            return redirect(next_url)

        target_level = target_user._highest_role_level() if hasattr(target_user, "_highest_role_level") else 0
        if not is_superadmin and target_user != request.user and target_level >= actor_level:
            messages.error(request, pgettext_lazy("accounts.manage_roles.message", "insufficient_level_for_target_user"))
            return redirect(next_url)

        selected_role_names = set(request.POST.getlist("role_names"))
        single_role_name = (request.POST.get("role_name") or "").strip()
        if single_role_name:
            selected_role_names.add(single_role_name)

        if action == "remove":
            selected_role_names = {ProfileRole.MEMBER}
        if not selected_role_names:
            selected_role_names = {ProfileRole.MEMBER}

        invalid_roles = selected_role_names - PROFILE_ROLE_NAMES
        if invalid_roles:
            messages.error(request, pgettext_lazy("accounts.manage_roles.message", "invalid_roles_selected"))
            return redirect(next_url)

        disallowed_roles = selected_role_names - assignable_role_names
        if disallowed_roles:
            messages.error(request, pgettext_lazy("accounts.manage_roles.message", "not_allowed_to_assign_some_roles"))
            return redirect(next_url)

        current_roles = set(_extract_profile_roles_for_user(target_user))
        protected_roles = current_roles - assignable_role_names
        effective_roles = protected_roles | selected_role_names

        if not effective_roles:
            effective_roles = {ProfileRole.MEMBER}

        primary_role = max(effective_roles, key=lambda role_name: ProfileRole.LEVELS.get(role_name, 0))
        additional_roles = effective_roles - {primary_role}

        target_profile, _ = UserProfile.objects.get_or_create(user=target_user)

        with transaction.atomic():
            target_profile.role = primary_role
            target_profile.save(update_fields=["role", "updated_at"])
            _sync_user_role_groups(
                target_user,
                additional_roles,
                editable_role_names=assignable_role_names,
            )

        assigned_labels = [PROFILE_ROLE_LABELS.get(role_name, role_name) for role_name in sorted(effective_roles)]
        messages.success(
            request,
            pgettext_lazy("accounts.manage_roles.message", "roles_updated_for_user")
            % {"username": target_user.username, "roles": ", ".join(assigned_labels)},
        )
        return redirect(next_url)

    # Get org-scoped users
    if is_superadmin:
        profiles = UserProfile.objects.all().select_related("user").prefetch_related("user__groups")
    else:
        profiles = UserProfile.objects.filter(organization=user_org).select_related("user").prefetch_related("user__groups")

    # Search
    search = request.GET.get("search", "")
    if search:
        profiles = profiles.filter(
            Q(user__username__icontains=search)
            | Q(user__email__icontains=search)
            | Q(user__first_name__icontains=search)
            | Q(user__last_name__icontains=search)
        )

    profiles_page = request.GET.get("manage_roles_page")
    profiles_page_obj = Paginator(profiles.order_by("user__username"), 12).get_page(profiles_page)
    _decorate_manage_role_profiles(
        profiles_page_obj.object_list,
        actor_level=actor_level,
        is_superadmin=is_superadmin,
    )

    context = {
        "profiles": profiles_page_obj,
        "assignable_roles": assignable_roles,
        "search_query": search,
        "organization": user_org,
        "profiles_page_param": "manage_roles_page",
        "profiles_pagination_query": _query_string(search=search),
        "post_next_url": _append_query_params(reverse("accounts:manage_roles"), search=search),
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
        messages.error(request, pgettext_lazy("accounts.grading_queue.message", "teacher_only"))
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
def my_result_detail(request, item_type, item_id):
    """Detail page for a single item from My Results."""
    profile = getattr(request.user, "profile", None)
    capabilities = _role_capabilities(request.user, profile)
    if not capabilities["can_view_student_assignments"]:
        messages.error(request, pgettext_lazy("accounts.student_assignments.message", "student_or_member_only"))
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
            "item_type_label": pgettext_lazy("accounts.my_result_detail.type", "course"),
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
            "item_type_label": pgettext_lazy("accounts.my_result_detail.type", "lab"),
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
            "item_type_label": pgettext_lazy("accounts.my_result_detail.type", "independent_work"),
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
def role_assignment(request):
    """Organization-scoped role assignment UI with strict server-side permission checks."""
    from apps.organizations.models import Membership, Role
    from apps.organizations.permissions import has_permission
    from apps.organizations.services import create_audit_log, get_user_org_role_level

    org = _get_active_organization(request)
    if not org:
        messages.error(request, pgettext_lazy("accounts.role_assignment.message", "active_organization_not_found"))
        return redirect("accounts:profile")

    _ensure_profile_admin_membership(request.user, org)

    is_superadmin = _is_superadmin_user(request.user)
    user_level = 999 if is_superadmin else get_user_org_role_level(request.user, org)
    actor_permissions, _ = _collect_actor_permissions(request.user, org)
    can_assign_roles = is_superadmin or has_permission(list(actor_permissions), "role.assign")

    # Teacher+ can at least assign Student/Member roles.
    # Default teacher membership level is 50 in org role templates.
    if not is_superadmin and user_level < 50:
        messages.error(request, pgettext_lazy("accounts.role_assignment.message", "teacher_or_higher_only"))
        return redirect("accounts:profile")

    if request.method == "POST":
        action = request.POST.get("action", "update_member")
        role_id = request.POST.get("role_id")
        target_role = get_object_or_404(Role, id=role_id, organization=org, is_active=True)

        if not is_superadmin and target_role.level >= user_level:
            messages.error(request, pgettext_lazy("accounts.role_assignment.message", "assign_lower_roles_only"))
            return redirect("accounts:role_assignment")

        # Teacher+ can assign student/member even without explicit role.assign permission.
        teacher_can_assign_basic = not is_superadmin and user_level >= 50 and target_role.name in {"student", "member"}

        if not (can_assign_roles or teacher_can_assign_basic):
            messages.error(request, pgettext_lazy("accounts.role_assignment.message", "missing_role_assign_permission"))
            return redirect("accounts:role_assignment")

        if action == "attach_user":
            user_id = request.POST.get("user_id")
            target_user = get_object_or_404(User, id=user_id, is_active=True)
            target_profile, _ = UserProfile.objects.get_or_create(user=target_user)

            if target_profile.organization and target_profile.organization != org:
                messages.error(request, pgettext_lazy("accounts.role_assignment.message", "user_bound_to_other_org"))
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
                        pgettext_lazy("accounts.role_assignment.message", "user_did_not_select_this_org_on_signup"),
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
                    messages.error(
                        request,
                        pgettext_lazy("accounts.role_assignment.message", "not_allowed_to_change_user_role"),
                    )
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
                request,
                pgettext_lazy("accounts.role_assignment.message", "user_added_to_org_with_role")
                % {"username": target_user.username, "role_display": target_role.display_name},
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
            messages.error(request, pgettext_lazy("accounts.role_assignment.message", "change_lower_level_users_only"))
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
            request,
            pgettext_lazy("accounts.role_assignment.message", "role_updated_for_user")
            % {"username": target_membership.user.username, "role_display": target_role.display_name},
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

    members_page = request.GET.get("role_members_page")
    members_page_obj = Paginator(members, 12).get_page(members_page)

    pending_page = request.GET.get("role_pending_page")
    unassigned_users_page_obj = Paginator(unassigned_users.order_by("user__username"), 12).get_page(pending_page)

    context = {
        "organization": org,
        "members": members_page_obj,
        "assignable_roles": assignable_roles,
        "user_level": user_level,
        "search_query": search,
        "unassigned_search_query": unassigned_search,
        "unassigned_users": unassigned_users_page_obj,
        "is_superadmin": is_superadmin,
        "can_assign_roles": can_assign_roles or user_level >= 50,
        "members_page_param": "role_members_page",
        "members_pagination_query": _query_string(
            search=search,
            unassigned_search=unassigned_search,
        ),
        "unassigned_page_param": "role_pending_page",
        "unassigned_pagination_query": _query_string(
            search=search,
            unassigned_search=unassigned_search,
        ),
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
        messages.error(request, pgettext_lazy("accounts.permission_editor.message", "active_organization_not_found"))
        return redirect("accounts:profile")

    _ensure_profile_admin_membership(request.user, org)

    is_superadmin = _is_superadmin_user(request.user)
    user_level = 999 if is_superadmin else get_user_org_role_level(request.user, org)
    actor_permissions, grantable_permissions = _collect_actor_permissions(request.user, org)

    can_manage_permissions = is_superadmin or has_permission(list(actor_permissions), "role.assign")
    if not is_superadmin and not can_manage_permissions:
        messages.error(request, pgettext_lazy("accounts.permission_editor.message", "role_assign_permission_required"))
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
            messages.error(request, pgettext_lazy("accounts.permission_editor.message", "manage_lower_role_permissions_only"))
            return redirect(f"{request.path}?role={selected_role.id}")

        all_permissions = set(get_all_permissions())
        if selected_permission not in all_permissions:
            messages.error(request, pgettext_lazy("accounts.permission_editor.message", "invalid_permission_selection"))
            return redirect(f"{request.path}?role={selected_role.id}")

        role_permissions = list(selected_role.permissions or [])
        role_permissions_set = set(role_permissions)
        old_permissions = sorted(role_permissions_set)

        if action == "add":
            if (
                not _permission_is_grantable(selected_permission, actor_permissions, grantable_permissions)
                and not is_superadmin
            ):
                messages.error(
                    request,
                    pgettext_lazy("accounts.permission_editor.message", "grant_only_owned_or_grantable_permissions"),
                )
                return redirect(f"{request.path}?role={selected_role.id}")
            role_permissions_set.add(selected_permission)
            result_message = (
                pgettext_lazy("accounts.permission_editor.message", "permission_added")
                % {"permission": selected_permission}
            )
        elif action == "remove":
            role_permissions_set.discard(selected_permission)
            result_message = (
                pgettext_lazy("accounts.permission_editor.message", "permission_removed")
                % {"permission": selected_permission}
            )
        else:
            messages.error(request, pgettext_lazy("accounts.permission_editor.message", "unknown_action"))
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
    if selected_role is None:
        selected_role = roles.first()

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
        messages.error(request, pgettext_lazy("accounts.superadmin_orgs.message", "superadmin_only"))
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
            messages.success(
                request,
                pgettext_lazy("accounts.superadmin_orgs.message", "organization_suspended")
                % {"organization_name": organization.name},
            )
        elif action == "unsuspend":
            organization.status = "active"
            organization.is_active = True
            organization.suspended_at = None
            organization.suspension_reason = ""
            organization.save(update_fields=["status", "is_active", "suspended_at", "suspension_reason", "updated_at"])
            messages.success(
                request,
                pgettext_lazy("accounts.superadmin_orgs.message", "organization_unsuspended")
                % {"organization_name": organization.name},
            )
        else:
            messages.error(request, pgettext_lazy("accounts.superadmin_orgs.message", "unknown_action"))

        return redirect("accounts:superadmin_organizations")

    organizations = (
        Organization.objects.select_related("owner")
        .annotate(active_member_count=Count("memberships", filter=Q(memberships__is_active=True)))
        .order_by("name")
    )
    organizations_page = request.GET.get("superadmin_org_page")
    organizations_page_obj = Paginator(organizations, 12).get_page(organizations_page)

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
        "organizations": organizations_page_obj,
        "all_modules": all_modules,
        "organizations_page_param": "superadmin_org_page",
        "organizations_pagination_query": "",
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
                    pgettext_lazy("accounts.auth.message", "registration_completed_request_recorded"),
                )
            else:
                messages.success(
                    request,
                    pgettext_lazy("accounts.auth.message", "registration_completed_you_can_login_now"),
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
        messages.error(request, pgettext_lazy("accounts.auth.message", "verification_email_not_found_register_again"))
        return redirect("accounts:register")

    if request.method == "POST":
        code = request.POST.get("code", "").strip()

        user = User.objects.filter(email=email).first()
        if not user:
            messages.error(request, pgettext_lazy("accounts.auth.message", "user_not_found"))
            return redirect("accounts:register")

        otp = EmailOTP.objects.filter(user=user, code=code, is_used=False).order_by("-created_at").first()
        if not otp or otp.is_expired():
            messages.error(request, pgettext_lazy("accounts.auth.message", "code_invalid_or_expired"))
            return render(request, "accounts/verify_code.html", {"email": email})

        otp.is_used = True
        otp.save()

        user.is_active = True
        user.save()

        messages.success(request, pgettext_lazy("accounts.auth.message", "email_verified_you_can_login_now"))
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
        messages.success(request, pgettext_lazy("accounts.auth.message", "email_verified_you_can_login_now"))
        return redirect("accounts:login")
    except (BadSignature, SignatureExpired, User.DoesNotExist):
        messages.error(request, pgettext_lazy("accounts.auth.message", "link_invalid_or_expired"))
        return redirect("accounts:register")


def resend_code_view(request):
    """Resend email verification code."""
    email = request.session.get("pending_verify_email")
    if not email:
        messages.error(request, pgettext_lazy("accounts.auth.message", "email_not_found"))
        return redirect("accounts:register")

    user = User.objects.filter(email=email).first()
    if not user:
        messages.error(request, pgettext_lazy("accounts.auth.message", "user_not_found"))
        return redirect("accounts:register")

    code = generate_otp()
    EmailOTP.objects.create(user=user, code=code, expires_at=timezone.now() + timedelta(minutes=10))
    send_verify_email(user, code)

    messages.success(request, pgettext_lazy("accounts.auth.message", "new_code_sent"))
    return redirect("accounts:verify_code")


def logout_view(request):
    """Logout user and redirect to home."""
    logout(request)
    messages.success(request, pgettext_lazy("accounts.auth.message", "logout_success"))
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
