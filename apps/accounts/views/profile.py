"""
Profile views: user profile management and avatar serving.
"""

import mimetypes

from django.contrib import messages
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.files.images import get_image_dimensions
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Count, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import http_date
from django.utils.translation import pgettext_lazy
from django.views.decorators.http import require_safe

from apps.assignments.models import Submission
from apps.blog.models import Post
from apps.courses.models import Course
from apps.exams.forms import StudentGroupForm
from apps.exams.models import Exam, ExamAttempt, StudentGroup
from apps.labs.models import LabSubmission
from apps.notifications.models import StudentOrganizationRequestStatus
from apps.notifications.services import build_profile_notification_state
from apps.projects.models import ProjectSubmission
from core.upload_security import randomize_uploaded_filename, validate_uploaded_file

from ..forms import CustomPasswordChangeForm
from ..models import ProfileRole, UserProfile
from ._dashboard_helpers import (
    _collect_assigned_tasks,
    _collect_evaluated_review_items,
    _collect_my_results,
    _collect_pending_answer_items,
    _collect_pending_review_items,
)
from ._helpers import (
    MAX_PROFILE_AVATAR_SIZE_BYTES,
    PROFILE_AVATAR_ALLOWED_EXTENSIONS,
    REVIEW_EDIT_WINDOW,
    STUDENT_MEMBER_GROUPS_DISPLAY_LIMIT,
    STUDENT_ORG_REQUEST_MESSAGE_MAX_LENGTH,
    _append_query_params,
    _assignable_profile_roles_for_user,
    _assigned_courses_queryset,
    _assigned_exams_queryset,
    _bind_active_role_context,
    _build_user_organization_access_rows,
    _build_student_org_management_section,
    _build_student_org_request_section,
    _collect_actor_permissions,
    _decorate_manage_role_profiles,
    _ensure_profile_admin_membership,
    _get_active_organization,
    _pending_student_request_queryset,
    _query_string,
    _role_capabilities,
    _tenant_scoped_courses,
    _tenant_scoped_exams,
    _user_has_any_role,
)

User = get_user_model()
PUBLIC_PROFILE_SEARCH_MAX_LENGTH = 100
PUBLIC_PROFILE_CATEGORY_MAX_LENGTH = 120


def _normalize_public_profile_query_value(raw_value, *, max_length):
    normalized = " ".join(str(raw_value or "").split())
    return normalized[:max_length]

def profile_avatar(request, user_id):
    """Serve profile avatar through Django to avoid direct MEDIA URL dependency."""
    target_user = get_object_or_404(User, id=user_id, is_active=True)
    target_profile = UserProfile.objects.filter(user=target_user).only("avatar", "updated_at").first()
    if not target_profile or not target_profile.avatar:
        raise Http404("Avatar tapılmadı.")

    avatar_field = target_profile.avatar
    try:
        avatar_stream = avatar_field.storage.open(avatar_field.name, "rb")
    except Exception as exc:
        raise Http404("Avatar faylı açılmadı.") from exc

    content_type = mimetypes.guess_type(avatar_field.name or "")[0] or "application/octet-stream"
    response = FileResponse(avatar_stream, content_type=content_type)
    response["Cache-Control"] = "private, max-age=300"
    response["Last-Modified"] = http_date(target_profile.updated_at.timestamp())
    response["X-Content-Type-Options"] = "nosniff"
    return response


@login_required
def user_profile(request):
    """
    User profile page with edit functionality.
    Ensures profile exists before rendering.
    Now accessible to ALL users (not just teachers).
    """
    from apps.blog.models import Post
    from apps.blog.selectors import get_category_assignment_choices
    from apps.blog.services import (
        author_requires_post_approval,
        can_user_create_post_category,
        collect_reviewable_posts,
        count_pending_reviewable_posts,
    )

    # Ensure profile exists (get_or_create for safety)
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    capabilities = _role_capabilities(request.user, profile)
    notification_state = build_profile_notification_state(user=request.user, profile=profile)
    pending_student_invites = notification_state["pending_student_invites"]
    pending_student_join_requests = notification_state["pending_student_join_requests"]
    pending_student_join_org_name = notification_state["pending_student_join_org_name"]
    pending_student_join_message = notification_state["pending_student_join_message"]
    student_can_leave_org = notification_state["student_can_leave_org"]
    notifications_unread_count = notification_state["unread_count"]

    def _validate_avatar_upload(uploaded_avatar):
        if uploaded_avatar is None:
            return "Profil şəkli seçilməyib."

        if getattr(uploaded_avatar, "size", 0) > MAX_PROFILE_AVATAR_SIZE_BYTES:
            max_size_mb = MAX_PROFILE_AVATAR_SIZE_BYTES // (1024 * 1024)
            return f"Profil şəkli maksimum {max_size_mb} MB ola bilər."

        try:
            validate_uploaded_file(
                uploaded_avatar,
                allowed_extensions=PROFILE_AVATAR_ALLOWED_EXTENSIONS,
                max_size_mb=MAX_PROFILE_AVATAR_SIZE_BYTES // (1024 * 1024),
                allowed_mime_types=set(),
                allowed_mime_prefixes=("image/",),
            )
        except ValidationError as exc:
            return exc.messages[0]

        try:
            width, height = get_image_dimensions(uploaded_avatar)
            if not width or not height:
                return "Yüklənən fayl şəkil kimi oxunmadı."
        except Exception:
            return "Yüklənən fayl şəkil formatında deyil və ya zədəlidir."
        finally:
            try:
                uploaded_avatar.seek(0)
            except Exception:
                pass
        return ""

    # Get active section from URL parameter (default: profile-info)
    requested_section = request.GET.get("section", "profile-info")
    allowed_sections = capabilities["allowed_sections"]
    active_section = requested_section if requested_section in allowed_sections else "profile-info"
    password_change_form = CustomPasswordChangeForm(request.user)

    if request.method == "POST":
        submitted_form = (request.POST.get("profile_form") or "").strip()
        if submitted_form == "update-avatar":
            uploaded_avatar = request.FILES.get("avatar")
            avatar_error = _validate_avatar_upload(uploaded_avatar)
            if avatar_error:
                messages.error(request, avatar_error)
                return redirect(f"{reverse('accounts:profile')}?section=profile-info")

            randomize_uploaded_filename(uploaded_avatar)
            profile.avatar = uploaded_avatar
            profile.save(update_fields=["avatar", "updated_at"])
            messages.success(request, "Profil şəkli uğurla yeniləndi.")
            return redirect(f"{reverse('accounts:profile')}?section=profile-info")

        if submitted_form == "change-password":
            password_change_form = CustomPasswordChangeForm(request.user, request.POST)
            if password_change_form.is_valid():
                user = password_change_form.save()
                update_session_auth_hash(request, user)
                messages.success(request, "Şifrə uğurla yeniləndi.")
                return redirect(f"{reverse('accounts:profile')}?section=change-password")

            messages.error(request, "Şifrə yenilənmədi. Zəhmət olmasa formadakı xətaları düzəldin.")
            active_section = "change-password"
        elif submitted_form != "edit-profile":
            target_section = request.GET.get("section") or request.POST.get("section") or active_section
            if target_section not in allowed_sections:
                target_section = "profile-info"
            return redirect(f"{reverse('accounts:profile')}?section={target_section}")

        allowed_user_fields = ["first_name", "last_name", "email"]
        user_update_payload = {
            "first_name": (request.POST.get("first_name", request.user.first_name) or "").strip(),
            "last_name": (request.POST.get("last_name", request.user.last_name) or "").strip(),
            "email": (request.POST.get("email", request.user.email) or "").strip().lower(),
        }
        first_name = user_update_payload["first_name"]
        last_name = user_update_payload["last_name"]
        new_email = user_update_payload["email"]
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
        for field_name, field_value in user_update_payload.items():
            setattr(request.user, field_name, field_value)
        request.user.save(update_fields=allowed_user_fields)

        # Update profile
        profile.phone = (request.POST.get("phone", profile.phone) or "").strip()
        profile.bio = (request.POST.get("bio", profile.bio) or "").strip()
        profile.location = (request.POST.get("location", profile.location) or "").strip()
        profile.student_university_name = student_university_name
        profile.student_school_identifier = student_school_identifier

        # Handle avatar upload
        uploaded_avatar = request.FILES.get("avatar")
        if uploaded_avatar is not None:
            avatar_error = _validate_avatar_upload(uploaded_avatar)
            if avatar_error:
                messages.error(request, avatar_error)
                return redirect("accounts:profile" + "?section=edit-profile")
            randomize_uploaded_filename(uploaded_avatar)
            profile.avatar = uploaded_avatar

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
    active_organization = _get_active_organization(request)
    organization_access_rows = _build_user_organization_access_rows(
        request.user,
        active_organization=active_organization,
        include_active_superadmin_org=capabilities["is_superadmin"],
        profile_section="superadmin-organizations" if capabilities["is_superadmin"] else "profile-info",
    )

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
    post_creation_requires_approval = False
    can_create_post_categories = False
    if capabilities["can_manage_blog"]:
        user_posts_qs = (
            Post.objects.filter(author=request.user)
            .select_related("category")
            .prefetch_related("approval_logs")
            .order_by("-created_at")
        )
        posts_count = user_posts_qs.count()
        user_posts = Paginator(user_posts_qs, 6).get_page(request.GET.get("page"))
        categories = get_category_assignment_choices()
        post_creation_requires_approval = author_requires_post_approval(request.user)
        can_create_post_categories = can_user_create_post_category(request.user)

    assigned_exams_count = 0
    assigned_courses_count = 0
    assigned_tasks_count = 0
    my_results_count = 0
    assigned_task_items = []
    assigned_task_counts = {
        "all": 0,
        "exams": 0,
        "courses": 0,
        "assignments": 0,
        "labs": 0,
        "independent": 0,
    }
    assigned_tasks_active_filter = "all"
    assigned_tasks_search_query = ""
    assigned_courses = []
    assigned_courses_search_query = ""
    my_result_items = []
    my_result_counts = {
        "all": 0,
        "exams": 0,
        "courses": 0,
        "labs": 0,
        "independent": 0,
    }
    my_results_active_filter = "all"
    pending_answer_items = []
    pending_answer_counts = {
        "all": 0,
        "exams": 0,
        "courses": 0,
        "labs": 0,
        "independent": 0,
    }
    pending_answers_active_filter = "all"
    pending_answers_search_query = ""
    pending_answers_count = 0
    if capabilities["can_view_student_assignments"]:
        assigned_exams_qs = _assigned_exams_queryset(request, request.user, active_only=True).order_by(
            "-start_datetime",
            "-created_at",
        )
        assigned_exams_count = assigned_exams_qs.count()
        assigned_task_items, assigned_task_counts, assigned_tasks_active_filter = _collect_assigned_tasks(
            request,
            filter_type=request.GET.get("assigned_type"),
            search=request.GET.get("assigned_search"),
        )
        assigned_tasks_count = assigned_task_counts.get("all", 0)
        assigned_tasks_search_query = (request.GET.get("assigned_search", "") or "").strip()

        assigned_courses_count = enrolled_courses_qs.count()
        assigned_courses_search_query = (request.GET.get("assigned_course_search", "") or "").strip()
        assigned_courses_qs = enrolled_courses_qs
        if assigned_courses_search_query:
            assigned_courses_qs = assigned_courses_qs.filter(
                Q(title__icontains=assigned_courses_search_query)
                | Q(description__icontains=assigned_courses_search_query)
            )
        assigned_courses = list(assigned_courses_qs[:20])

        my_result_items, my_result_counts, my_results_active_filter = _collect_my_results(
            request,
            filter_type=request.GET.get("results_type"),
        )
        my_results_count = my_result_counts.get("all", 0)
        (
            pending_answer_items,
            pending_answer_counts,
            pending_answers_active_filter,
            pending_answers_search_query,
        ) = _collect_pending_answer_items(
            request,
            search=request.GET.get("pending_search"),
            filter_type=request.GET.get("pending_type"),
        )
        pending_answers_count = pending_answer_counts.get("all", 0)

    pending_review_count = 0
    evaluated_review_count = 0
    if capabilities["can_review_submissions"]:
        review_cutoff = timezone.now() - REVIEW_EDIT_WINDOW
        pending_review_count = (
            ExamAttempt.objects.filter(
                exam__in=my_exams_qs,
                status__in=["submitted", "expired"],
            )
            .filter(
                Q(checked_by_teacher=False)
                | Q(checked_by_teacher=True, teacher_checked_at__gte=review_cutoff)
            )
            .exclude(exam__exam_type="test")
            .count()
        )
        pending_review_count += (
            Submission.objects.filter(assignment__course__in=teacher_courses)
            .filter(Q(status="submitted") | Q(status="graded", graded_at__gte=review_cutoff))
            .count()
        )
        pending_review_count += (
            ProjectSubmission.objects.filter(project__course__in=teacher_courses)
            .filter(Q(status="pending") | Q(status="graded", graded_at__gte=review_cutoff))
            .count()
        )
        pending_review_count += (
            LabSubmission.objects.filter(assignment__lab__course__in=teacher_courses)
            .filter(Q(status__in=["submitted", "late"]) | Q(status="graded", graded_at__gte=review_cutoff))
            .count()
        )

        evaluated_review_count = (
            ExamAttempt.objects.filter(
                exam__in=my_exams_qs,
                status__in=["submitted", "expired"],
            )
            .filter(
                Q(exam__exam_type="test")
                | Q(checked_by_teacher=True, teacher_checked_at__isnull=True)
                | Q(checked_by_teacher=True, teacher_checked_at__lte=review_cutoff)
            )
            .count()
        )
        evaluated_review_count += (
            Submission.objects.filter(
                assignment__course__in=teacher_courses,
                status="graded",
            )
            .filter(Q(graded_at__isnull=True) | Q(graded_at__lte=review_cutoff))
            .count()
        )
        evaluated_review_count += (
            ProjectSubmission.objects.filter(
                project__course__in=teacher_courses,
                status="graded",
            )
            .filter(Q(graded_at__isnull=True) | Q(graded_at__lte=review_cutoff))
            .count()
        )
        evaluated_review_count += (
            LabSubmission.objects.filter(
                assignment__lab__course__in=teacher_courses,
                status="graded",
            )
            .filter(Q(graded_at__isnull=True) | Q(graded_at__lte=review_cutoff))
            .count()
        )

    teacher_groups = []
    teacher_groups_count = 0
    teacher_groups_payload = {}
    student_member_groups_qs = (
        StudentGroup.objects.filter(students=request.user)
        .select_related("organization", "teacher")
        .order_by("organization__name", "name")
        .distinct()
    )
    student_member_groups_count = student_member_groups_qs.count()
    student_member_groups = list(student_member_groups_qs[:STUDENT_MEMBER_GROUPS_DISPLAY_LIMIT])
    student_member_groups_more_count = max(0, student_member_groups_count - len(student_member_groups))
    group_form = None
    can_multi_assign_group_teachers = False
    groups_section_return_url = f"{reverse('accounts:profile')}?section=groups"
    if "groups" in allowed_sections:
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
                teacher_groups_qs = teacher_groups_qs.filter(
                    Q(teacher=request.user) | Q(teachers=request.user)
                ).distinct()

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

    pending_post_approval_items = []
    pending_post_approval_count = 0
    pending_post_approval_search_query = ""
    pending_post_approval_filter_status = "pending"
    pending_post_approval_filter_group = ""
    pending_post_approval_available_groups = []
    if "pending-post-approvals" in allowed_sections:
        (
            pending_post_approval_items,
            pending_post_approval_search_query,
            pending_post_approval_filter_status,
            pending_post_approval_filter_group,
            pending_post_approval_available_groups,
        ) = collect_reviewable_posts(
            request.user,
            search=request.GET.get("approval_search"),
            status=request.GET.get("approval_status"),
            group_id=request.GET.get("approval_group"),
        )
        pending_post_approval_count = count_pending_reviewable_posts(request.user)

    pending_review_items = []
    pending_review_search_query = ""
    pending_review_filter_type = "all"
    pending_review_filter_status = "all"
    evaluated_review_items = []
    evaluated_review_search_query = ""
    evaluated_review_filter_type = "all"
    evaluated_review_filter_group = ""
    evaluated_review_available_groups = []
    if "pending-review" in allowed_sections or "review-results" in allowed_sections:
        (
            pending_review_items,
            pending_review_search_query,
            pending_review_filter_type,
            pending_review_filter_status,
        ) = _collect_pending_review_items(request)
        (
            evaluated_review_items,
            evaluated_review_search_query,
            evaluated_review_filter_type,
            evaluated_review_filter_group,
            evaluated_review_available_groups,
        ) = _collect_evaluated_review_items(request)

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
        "post_next_url": "",
    }
    student_org_management_section = {
        "organization": None,
        "students": [],
        "pending_requested_students": [],
        "unassigned_students": [],
        "sent_student_invites": [],
        "student_search_query": "",
        "pending_search_query": "",
        "unassigned_search_query": "",
        "sent_invite_search_query": "",
        "access_denied_message": "",
        "can_manage_students": False,
        "students_page_param": "student_org_members_page",
        "students_pagination_query": "",
        "pending_page_param": "student_org_pending_page",
        "pending_pagination_query": "",
        "unassigned_page_param": "student_org_unassigned_page",
        "unassigned_pagination_query": "",
        "sent_invites_page_param": "student_org_sent_invites_page",
        "sent_invites_pagination_query": "",
    }
    student_org_request_section = {
        "organizations": [],
        "search_query": "",
        "org_type_filter": "",
        "pending_invites": [],
        "pending_invites_count": 0,
        "has_pending_invites": False,
        "pending_student_requests": [],
        "pending_student_requests_count": 0,
        "has_pending_student_requests": False,
        "pending_request_org_ids": set(),
        "current_organization": None,
        "pending_requested_organization": None,
        "pending_requested_org_name": "",
        "pending_request_message": "",
        "selected_org_id": "",
        "page_param": "student_org_request_page",
        "pagination_query": "",
        "post_next_url": "",
        "request_message_max_length": STUDENT_ORG_REQUEST_MESSAGE_MAX_LENGTH,
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
        "organization_access_rows": [],
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
    if (
        "role-assignment" in allowed_sections
        or "permission-editor" in allowed_sections
        or "student-organization-management" in allowed_sections
    ):
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
            ) or has_permission(
                list(management_actor_permissions),
                "org.manage_members",
            )
            management_min_level_ok = capabilities["is_superadmin"] or management_user_level >= 50

    if "role-assignment" in allowed_sections:
        from apps.organizations.models import Membership, Role

        role_assignment_search = request.GET.get("q", request.GET.get("search", ""))
        role_assignment_unassigned_search = request.GET.get("unassigned_search", "")
        role_assignment_section.update(
            {
                "organization": management_org,
                "search_query": role_assignment_search,
                "unassigned_search_query": role_assignment_unassigned_search,
                "can_assign_roles": management_can_assign_roles,
                "post_next_url": _append_query_params(
                    reverse("accounts:profile"),
                    section="role-assignment",
                    q=role_assignment_search,
                    unassigned_search=role_assignment_unassigned_search,
                    role_members_page=request.GET.get("role_members_page", ""),
                    role_pending_page=request.GET.get("role_pending_page", ""),
                ),
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

            unassigned_users = UserProfile.objects.filter(
                user__is_active=True, organization__isnull=True
            ).select_related(
                "user",
                "requested_organization",
            )
            if not capabilities["is_superadmin"]:
                pending_request_user_ids = _pending_student_request_queryset(
                    organization=management_org,
                    statuses=[StudentOrganizationRequestStatus.PENDING],
                ).values_list("user_id", flat=True)
                unassigned_users = unassigned_users.filter(
                    Q(user_id__in=pending_request_user_ids)
                    | Q(requested_organization=management_org)
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
                q=role_assignment_search,
                unassigned_search=role_assignment_unassigned_search,
            )
            role_assignment_section["unassigned_pagination_query"] = _query_string(
                section="role-assignment",
                q=role_assignment_search,
                unassigned_search=role_assignment_unassigned_search,
            )

    if "student-organization-management" in allowed_sections:
        student_org_management_section = _build_student_org_management_section(
            request=request,
            organization=management_org,
            is_superadmin=capabilities["is_superadmin"],
            user_level=management_user_level,
        )
        student_org_management_section["post_next_url"] = _append_query_params(
            reverse("accounts:profile"),
            section="student-organization-management",
            student_org_search=student_org_management_section["student_search_query"],
            student_org_pending_search=student_org_management_section["pending_search_query"],
            student_org_unassigned_search=student_org_management_section["unassigned_search_query"],
            student_org_sent_invite_search=student_org_management_section["sent_invite_search_query"],
        )

    if "student-organization-request" in allowed_sections:
        student_org_request_section = _build_student_org_request_section(request=request, profile=profile)
        student_org_request_section["post_next_url"] = _append_query_params(
            reverse("accounts:profile"),
            section="student-organization-request",
            student_org_request_search=student_org_request_section["search_query"],
            student_org_request_type=student_org_request_section["org_type_filter"],
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
        _bind_active_role_context(
            request.user,
            manage_roles_org,
            memberships=getattr(request, "org_memberships", []),
            permissions=getattr(request, "org_permissions", []),
        )
        manage_roles_user_level = (
            request.user._highest_role_level() if hasattr(request.user, "_highest_role_level") else 0
        )
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

        if manage_roles_org is None:
            manage_roles_section["access_denied_message"] = "Rol idarəetməsi üçün aktiv təşkilat tapılmadı."
            manage_role_profiles = UserProfile.objects.none()
        else:
            manage_role_profiles = (
                UserProfile.objects.filter(
                    user__memberships__organization=manage_roles_org,
                    user__memberships__is_active=True,
                )
                .select_related("user")
                .prefetch_related("user__memberships__role")
                .distinct()
            )

        if manage_roles_search:
            manage_role_profiles = manage_role_profiles.filter(
                Q(user__username__icontains=manage_roles_search)
                | Q(user__email__icontains=manage_roles_search)
                | Q(user__first_name__icontains=manage_roles_search)
                | Q(user__last_name__icontains=manage_roles_search)
            )

        manage_roles_page = request.GET.get("manage_roles_page")
        manage_roles_page_obj = Paginator(manage_role_profiles.order_by("user__username"), 12).get_page(
            manage_roles_page
        )
        _decorate_manage_role_profiles(
            manage_roles_page_obj.object_list,
            actor_level=manage_roles_user_level,
            is_superadmin=capabilities["is_superadmin"],
            organization=manage_roles_org,
            actor_user=request.user,
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
        superadmin_organizations_section["organization_access_rows"] = organization_access_rows
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
        "notifications": "Bildirişlər",
        "posts": pgettext_lazy("profile.section", "posts"),
        "create-post": pgettext_lazy("profile.section", "create_post"),
        "courses": pgettext_lazy("profile.section", "my_courses"),
        "my-exams": pgettext_lazy("profile.section", "my_exams"),
        "my-courses": pgettext_lazy("profile.section", "my_created_courses"),
        "assigned-exams": pgettext_lazy("profile.section", "assigned_tasks"),
        "assigned-courses": pgettext_lazy("profile.section", "assigned_courses"),
        "my-results": pgettext_lazy("profile.section", "my_results"),
        "pending-answers": "Pending cavablar",
        "groups": pgettext_lazy("profile.section", "groups"),
        "pending-post-approvals": "Təsdiq gözləyən postlar",
        "pending-review": pgettext_lazy("profile.section", "pending_review"),
        "review-results": "Dəyərləndirilmiş nəticələr",
        "role-assignment": pgettext_lazy("profile.section", "role_assignment"),
        "student-organization-request": "Təşkilata qoşul",
        "student-organization-management": "Tələbə idarəetməsi",
        "permission-editor": pgettext_lazy("profile.section", "permissions"),
        "manage-roles": pgettext_lazy("profile.section", "manage_roles"),
        "superadmin-organizations": pgettext_lazy("profile.section", "superadmin_control"),
        "blog": pgettext_lazy("nav", "home"),
        "edit-profile": pgettext_lazy("profile.section", "edit_profile"),
        "change-password": "Şifrəni dəyiş",
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
                "icon": "fas fa-house",
                "source_url": reverse("home"),
                "description": "Ana səhifə və məqalə bölməsini aç.",
                "action_label": pgettext_lazy("nav", "home"),
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
        "password_change_form": password_change_form,
        "user_posts": user_posts,
        "posts_count": posts_count,
        "categories": categories,
        "post_creation_requires_approval": post_creation_requires_approval,
        "can_create_post_categories": can_create_post_categories,
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
        "assigned_tasks_search_query": assigned_tasks_search_query,
        "assigned_courses": assigned_courses,
        "assigned_courses_search_query": assigned_courses_search_query,
        "my_results_count": my_results_count,
        "my_result_items": my_result_items,
        "my_result_counts": my_result_counts,
        "my_results_active_filter": my_results_active_filter,
        "pending_answers_count": pending_answers_count,
        "pending_answer_items": pending_answer_items,
        "pending_answer_counts": pending_answer_counts,
        "pending_answers_active_filter": pending_answers_active_filter,
        "pending_answers_search_query": pending_answers_search_query,
        "pending_review_count": pending_review_count,
        "evaluated_review_count": evaluated_review_count,
        "teacher_groups": teacher_groups,
        "teacher_groups_count": teacher_groups_count,
        "teacher_groups_payload": teacher_groups_payload,
        "organization_access_rows": organization_access_rows,
        "student_member_groups": student_member_groups,
        "student_member_groups_count": student_member_groups_count,
        "student_member_groups_more_count": student_member_groups_more_count,
        "group_form": group_form,
        "can_multi_assign_group_teachers": can_multi_assign_group_teachers,
        "groups_section_return_url": groups_section_return_url,
        "pending_post_approval_items": pending_post_approval_items,
        "pending_post_approval_count": pending_post_approval_count,
        "pending_post_approval_search_query": pending_post_approval_search_query,
        "pending_post_approval_filter_status": pending_post_approval_filter_status,
        "pending_post_approval_filter_group": pending_post_approval_filter_group,
        "pending_post_approval_available_groups": pending_post_approval_available_groups,
        "pending_review_items": pending_review_items,
        "pending_review_search_query": pending_review_search_query,
        "pending_review_filter_type": pending_review_filter_type,
        "pending_review_filter_status": pending_review_filter_status,
        "pending_review_total_count": len(pending_review_items),
        "evaluated_review_items": evaluated_review_items,
        "evaluated_review_search_query": evaluated_review_search_query,
        "evaluated_review_filter_type": evaluated_review_filter_type,
        "evaluated_review_filter_group": evaluated_review_filter_group,
        "evaluated_review_available_groups": evaluated_review_available_groups,
        "evaluated_review_total_count": len(evaluated_review_items),
        "pending_student_invites": pending_student_invites,
        "pending_student_join_requests": pending_student_join_requests,
        "notifications_unread_count": notifications_unread_count,
        "pending_student_join_org_name": pending_student_join_org_name,
        "pending_student_join_message": pending_student_join_message,
        "student_can_leave_org": student_can_leave_org,
        "role_assignment_section": role_assignment_section,
        "student_org_request_section": student_org_request_section,
        "student_org_management_section": student_org_management_section,
        "permission_editor_section": permission_editor_section,
        "manage_roles_section": manage_roles_section,
        "superadmin_organizations_section": superadmin_organizations_section,
        "is_teacher": capabilities["is_teacher"],
        "is_admin": capabilities["can_manage_org"],
        "is_superadmin": capabilities["is_superadmin"],
        "can_manage_org": capabilities["can_manage_org"],
        "can_view_owned_learning": capabilities["can_view_owned_learning"],
        "can_review_submissions": capabilities["can_review_submissions"],
        "can_approve_posts": capabilities["can_approve_posts"],
        "can_view_blog": capabilities["can_view_blog"],
        "can_manage_blog": capabilities["can_manage_blog"],
        "can_view_student_assignments": capabilities["can_view_student_assignments"],
    }

    return render(request, "accounts/profile.html", context)

@require_safe
def public_user_profile(request, username):
    """
    Public user profile showing only published posts and non-confidential profile information.
    """
    from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
    from django.db.models import Q

    from apps.blog.models import Category, Post
    from apps.blog.selectors import filter_posts_by_category_scope, get_flat_category_tree

    profile_user = get_object_or_404(User, username=username)

    if request.user.is_authenticated and request.user == profile_user:
        return redirect("accounts:profile")

    profile, _ = UserProfile.objects.get_or_create(user=profile_user)

    published_posts = (
        Post.objects.filter(author=profile_user, is_published=True)
        .select_related("category")
        .order_by("-created_at")
    )

    search_query = _normalize_public_profile_query_value(
        request.GET.get("q"),
        max_length=PUBLIC_PROFILE_SEARCH_MAX_LENGTH,
    )
    selected_category = _normalize_public_profile_query_value(
        request.GET.get("category"),
        max_length=PUBLIC_PROFILE_CATEGORY_MAX_LENGTH,
    )

    user_posts_list = published_posts
    if search_query:
        user_posts_list = user_posts_list.filter(
            Q(title__icontains=search_query)
            | Q(excerpt__icontains=search_query)
            | Q(content__icontains=search_query)
        )

    if selected_category:
        selected_category_obj = Category.objects.select_related("parent").filter(slug=selected_category).first()
        if selected_category_obj:
            user_posts_list = filter_posts_by_category_scope(user_posts_list, selected_category_obj)
        else:
            user_posts_list = user_posts_list.none()

    category_items = get_flat_category_tree(posts_queryset=published_posts, include_empty=False)

    paginator = Paginator(user_posts_list, 6)
    page_number = request.GET.get("page")
    try:
        posts = paginator.page(page_number)
    except PageNotAnInteger:
        posts = paginator.page(1)
    except EmptyPage:
        posts = paginator.page(paginator.num_pages)

    display_name = (f"{profile_user.first_name} {profile_user.last_name}").strip() or profile_user.username
    profile_bio = (profile.bio or "").strip()
    profile_location = (profile.location or "").strip()

    query_params = request.GET.copy()
    query_params.pop("page", None)
    extra_query = query_params.urlencode()

    context = {
        "profile_user": profile_user,
        "profile": profile,
        "display_name": display_name,
        "search_query": search_query,
        "selected_category": selected_category,
        "extra_query": extra_query,
        "category_items": category_items,
        "published_posts_count": published_posts.count(),
        "category_count": len(category_items),
        "profile_bio": profile_bio,
        "profile_location": profile_location,
        "posts": posts,
    }
    return render(request, "accounts/public_profile.html", context)
