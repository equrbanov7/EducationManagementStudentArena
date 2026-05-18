"""
Profile views: user profile management and avatar serving.
"""

import mimetypes
import os
import re
from urllib.parse import urlencode
from urllib.parse import urlparse as _parse_url

from django.contrib import messages
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.files.images import get_image_dimensions
from django.core.files.storage import default_storage
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.db.models.deletion import ProtectedError
from django.http import FileResponse, Http404, HttpResponseBadRequest, QueryDict
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import http_date
from django.utils.translation import gettext as _
from django.utils.translation import pgettext_lazy
from django.views.decorators.http import require_safe

from apps.assignments.models import Submission
from apps.audit.utils import log_action
from apps.courses.models import Course
from apps.exams.forms import StudentGroupForm
from apps.exams.models import Exam, ExamAttempt, StudentGroup
from apps.labs.models import LabSubmission
from apps.notifications.models import NotificationType, StudentOrganizationRequestStatus
from apps.notifications.services import (
    build_profile_notification_state,
    create_notification_for_users,
    get_unread_count,
    get_user_notifications,
)
from apps.projects.models import ProjectSubmission
from core.tenancy import restore_request_organization_from_profile
from core.upload_security import IMAGE_ALLOWED_EXTENSIONS, randomize_uploaded_filename, validate_uploaded_file

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
    PROFILE_ROLE_LABELS,
    REVIEW_EDIT_WINDOW,
    STUDENT_MEMBER_GROUPS_DISPLAY_LIMIT,
    STUDENT_ORG_MANAGEMENT_MIN_LEVEL,
    STUDENT_ORG_REQUEST_MESSAGE_MAX_LENGTH,
    _append_query_params,
    _assignable_profile_roles_for_user,
    _assigned_courses_queryset,
    _assigned_exams_queryset,
    _bind_active_role_context,
    _build_student_org_management_section,
    _build_student_org_request_section,
    _build_user_organization_access_rows,
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
from .account_management import build_superadmin_user_management_context
from .superadmin import build_superadmin_ai_settings_context

User = get_user_model()
PUBLIC_PROFILE_SEARCH_MAX_LENGTH = 100
PUBLIC_PROFILE_CATEGORY_MAX_LENGTH = 120
PROFILE_AVATAR_VERSION_MAX_LENGTH = 64
PUBLIC_PROFILE_PAGE_NUMBER_PATTERN = re.compile(r"^[0-9]+$")
PUBLIC_PROFILE_ALLOWED_QUERY_PUNCTUATION = frozenset({" ", "-", "_", ".", ",", "@", "#", "+"})
PUBLIC_PROFILE_FORMAT_SPECIFIER_PATTERN = re.compile(r"%(?:\d+\$)?[-+#0*. ]*[a-zA-Z]")
PUBLIC_PROFILE_CATEGORY_PATTERN = re.compile(r"^[a-z0-9_-]{1,%s}$" % PUBLIC_PROFILE_CATEGORY_MAX_LENGTH)
PROFILE_AVATAR_VERSION_PATTERN = re.compile(r"^[0-9]{1,%s}$" % PROFILE_AVATAR_VERSION_MAX_LENGTH)
PROFILE_SECTIONS_REQUIRING_ORG_CONTEXT = {
    "profile-info",
    "courses",
    "assigned-exams",
    "assigned-courses",
    "my-results",
    "pending-answers",
    "groups",
    "my-courses",
    "my-exams",
    "pending-post-approvals",
    "pending-review",
    "review-results",
    "role-assignment",
    "student-organization-management",
    "permission-editor",
    "manage-roles",
    "publish-notification",
    "statistics",
}
PROFILE_SECTIONS_ALLOWING_MULTI_ORG_PROFILE_FALLBACK = {
    "groups",
    "my-courses",
    "my-exams",
    "courses",
    "pending-post-approvals",
    "pending-review",
    "review-results",
    "role-assignment",
    "student-organization-management",
    "permission-editor",
    "manage-roles",
    "publish-notification",
    "statistics",
}
PROFILE_EXAM_NAV_SECTIONS = {
    "groups",
    "my-exams",
    "assigned-exams",
    "my-results",
    "pending-answers",
    "pending-review",
    "review-results",
}


def _build_effective_user_roles(user, profile):
    role_names = []

    if getattr(user, "is_superuser", False):
        role_names.append(ProfileRole.SUPERADMIN)

    if hasattr(user, "get_all_roles"):
        for role_name in user.get_all_roles():
            normalized_role_name = ProfileRole.normalize_membership_role_name(role_name)
            if normalized_role_name in PROFILE_ROLE_LABELS and normalized_role_name not in role_names:
                role_names.append(normalized_role_name)

    fallback_role_name = ProfileRole.normalize_membership_role_name(getattr(profile, "role", ""))
    if fallback_role_name in PROFILE_ROLE_LABELS and fallback_role_name not in role_names:
        role_names.append(fallback_role_name)

    role_names.sort(key=lambda role_name: (ProfileRole.LEVELS.get(role_name, 0), role_name), reverse=True)
    return [
        {
            "name": role_name,
            "label": PROFILE_ROLE_LABELS.get(role_name, role_name.replace("_", " ").title()),
        }
        for role_name in role_names
    ]


def _normalize_public_profile_query_value(raw_value, *, max_length):
    normalized = " ".join(str(raw_value or "").split())
    return normalized[:max_length]


def _sanitize_public_profile_search_query(raw_value):
    normalized = _normalize_public_profile_query_value(raw_value, max_length=PUBLIC_PROFILE_SEARCH_MAX_LENGTH)
    if not normalized:
        return "", False

    if PUBLIC_PROFILE_FORMAT_SPECIFIER_PATTERN.search(normalized):
        return "", True

    sanitized = "".join(
        character
        for character in normalized
        if character.isalnum() or character in PUBLIC_PROFILE_ALLOWED_QUERY_PUNCTUATION
    ).strip()
    return sanitized[:PUBLIC_PROFILE_SEARCH_MAX_LENGTH], sanitized != normalized


def _validate_public_profile_category(raw_value, *, allowed_slugs):
    normalized = _normalize_public_profile_query_value(raw_value, max_length=PUBLIC_PROFILE_CATEGORY_MAX_LENGTH).lower()
    if not normalized:
        return "", False

    if not PUBLIC_PROFILE_CATEGORY_PATTERN.fullmatch(normalized):
        return "", True

    if normalized not in allowed_slugs:
        return "", True

    return normalized, False


def _restore_profile_org_context(request, profile, active_section):
    """
    Re-hydrate the active organization for org-bound profile sections when the
    session lost its tenant selection but the profile still points at a valid org.
    """
    if active_section not in PROFILE_SECTIONS_REQUIRING_ORG_CONTEXT:
        return
    restore_request_organization_from_profile(
        request,
        profile=profile,
        allow_multi_org_restore=active_section in PROFILE_SECTIONS_ALLOWING_MULTI_ORG_PROFILE_FALLBACK,
    )


def _parse_public_profile_page_number(raw_value):
    normalized = str(raw_value or "").strip()
    if not normalized:
        return None

    if not PUBLIC_PROFILE_PAGE_NUMBER_PATTERN.fullmatch(normalized):
        return None

    return int(normalized)


def _validate_profile_avatar_version(raw_value):
    normalized = _normalize_public_profile_query_value(raw_value, max_length=PROFILE_AVATAR_VERSION_MAX_LENGTH)
    if not normalized:
        return ""

    if not PROFILE_AVATAR_VERSION_PATTERN.fullmatch(normalized):
        raise ValidationError("Invalid avatar version parameter.")

    return normalized


@login_required
def profile_avatar(request, user_id):
    """Serve a logged-in user's requested profile avatar through Django."""
    try:
        _validate_profile_avatar_version(request.GET.get("v"))
    except ValidationError:
        return HttpResponseBadRequest("Invalid avatar version parameter.")

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


def _get_publish_notification_targets(user, capabilities):
    """Return list of target options for notification publishing based on role."""
    from apps.exams.models import StudentGroup
    from apps.organizations.models import Membership

    targets = []
    is_superadmin = capabilities["is_superadmin"]
    is_org_admin = capabilities["is_org_admin"]
    is_teacher = capabilities["is_teacher"]

    if is_superadmin:
        # "All users" is exclusive — if selected, ignore specific org selections
        targets.append(
            {
                "value": "all",
                "label": _("target_all_users"),
                "is_exclusive": True,
            }
        )
        from apps.organizations.models import Organization

        for org in Organization.objects.filter(is_active=True, status="active").order_by("name"):
            targets.append(
                {
                    "value": f"org_{org.pk}",
                    "label": f'{_("target_org_prefix")}: {org.name}',
                    "is_exclusive": False,
                }
            )
    elif is_org_admin:
        # Get user's active org memberships
        org_memberships = (
            Membership.objects.filter(user=user, is_active=True, organization__is_active=True)
            .select_related("organization")
            .order_by("organization__name", "organization_id", "-role__level", "id")
        )
        seen_org_ids = set()
        for membership in org_memberships:
            if membership.organization_id in seen_org_ids:
                continue
            seen_org_ids.add(membership.organization_id)
            targets.append(
                {
                    "value": f"org_{membership.organization_id}",
                    "label": f'{_("target_org_prefix")}: {membership.organization.name} ({_("target_org_all_members")})',
                    "is_exclusive": False,
                }
            )
    elif is_teacher:
        teacher_groups = StudentGroup.objects.filter(teacher=user).order_by("name")
        for group in teacher_groups:
            targets.append(
                {
                    "value": f"group_{group.pk}",
                    "label": f'{_("target_group_prefix")}: {group.name}',
                    "is_exclusive": False,
                }
            )
    return targets


def _get_notification_recipients(user, capabilities, target: str):
    """Resolve notification target to a queryset of recipient users.

    Returns a queryset/list of users, or None if target is invalid/unauthorized.
    """
    from apps.exams.models import StudentGroup
    from apps.organizations.models import Membership, Organization

    is_superadmin = capabilities["is_superadmin"]
    User = get_user_model()

    if target == "all":
        if not is_superadmin:
            return None
        return User.objects.filter(is_active=True)

    if target.startswith("org_"):
        org_id = (target[4:] or "").strip()
        if not org_id:
            return None
        try:
            org = Organization.objects.get(pk=org_id, is_active=True, status="active")
        except (ValidationError, Organization.DoesNotExist):
            return None
        # Superadmin can target any org; org admin only their own
        if not is_superadmin:
            if not Membership.objects.filter(user=user, organization=org, is_active=True).exists():
                return None
        member_user_ids = Membership.objects.filter(organization=org, is_active=True).values_list("user_id", flat=True)
        return User.objects.filter(pk__in=member_user_ids, is_active=True)

    if target.startswith("group_"):
        try:
            grp_id = int(target[6:])
        except (ValueError, IndexError):
            return None
        try:
            group = StudentGroup.objects.get(pk=grp_id)
        except StudentGroup.DoesNotExist:
            return None
        # Only the teacher who owns the group (or superadmin) may target it
        if not is_superadmin and group.teacher_id != user.pk:
            return None
        return group.students.filter(is_active=True)

    return None


@login_required
def user_profile(request):
    """
    User profile page with edit functionality.
    Ensures profile exists before rendering.
    Now accessible to ALL users (not just teachers).
    """
    from apps.blog.forms import CategoryManagementForm
    from apps.blog.models import Category, Post
    from apps.blog.selectors import build_post_category_picker_options, get_post_category_tree
    from apps.blog.services import (
        author_requires_post_approval,
        can_user_manage_categories,
        can_user_publish_post,
        collect_reviewable_posts,
        count_pending_reviewable_posts,
    )

    # Ensure profile exists (get_or_create for safety)
    profile, _created = UserProfile.objects.get_or_create(user=request.user)
    requested_section = request.GET.get("section", "profile-info")
    _restore_profile_org_context(request, profile, requested_section)

    capabilities = _role_capabilities(request.user, profile)
    notification_state = build_profile_notification_state(user=request.user, profile=profile)
    pending_student_invites = notification_state["pending_student_invites"]
    pending_student_join_requests = notification_state["pending_student_join_requests"]
    pending_student_join_org_name = notification_state["pending_student_join_org_name"]
    pending_student_join_message = notification_state["pending_student_join_message"]
    student_can_leave_org = notification_state["student_can_leave_org"]
    org_notification_count = notification_state["unread_count"]
    in_app_unread_count = get_unread_count(user=request.user)
    notifications_unread_count = org_notification_count + in_app_unread_count

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
    allowed_sections = capabilities["allowed_sections"]
    active_section = requested_section if requested_section in allowed_sections else "profile-info"
    if active_section == "delete-account":
        active_section = "profile-info"
    password_change_form = CustomPasswordChangeForm(request.user)
    category_management_create_form = None
    category_management_edit_form = None
    category_management_edit_item = None

    def _category_section_url(*, section="category-management", edit_category=None):
        query_params = QueryDict(mutable=True)
        query_params["section"] = section
        if edit_category:
            query_params["edit_category"] = str(edit_category)
        return f"{reverse('accounts:profile')}?{query_params.urlencode()}"

    def _load_managed_category(raw_category_id):
        try:
            category_id = int(str(raw_category_id or "").strip())
        except (TypeError, ValueError):
            return None
        return Category.objects.select_related("parent").filter(pk=category_id).first()

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
        elif submitted_form == "publish-notification":
            if "publish-notification" not in allowed_sections:
                messages.error(request, "Bu əməliyyatı yerinə yetirmək üçün icazəniz yoxdur.")
                return redirect(f"{reverse('accounts:profile')}?section=profile-info")
            notif_title = (request.POST.get("notif_title") or "").strip()
            notif_message = (request.POST.get("notif_message") or "").strip()
            # Accept multiple targets submitted as a checkbox list
            notif_targets_raw = request.POST.getlist("notif_targets")
            notif_targets = [t.strip() for t in notif_targets_raw if t.strip()]
            # Fall back to the old single-value field for backward-compat
            if not notif_targets:
                single = (request.POST.get("notif_target") or "").strip()
                if single:
                    notif_targets = [single]
            if not notif_targets:
                notif_targets = ["all"]
            notif_link = (request.POST.get("notif_link") or "").strip()
            notif_image_file = request.FILES.get("notif_image")

            if not notif_title:
                messages.error(request, _("notif_title_required"))
                return redirect(f"{reverse('accounts:profile')}?section=publish-notification")

            # Validate optional link — require explicit http/https scheme
            if notif_link:
                try:
                    parsed_link = _parse_url(notif_link)
                    if parsed_link.scheme not in ("http", "https"):
                        raise ValueError("invalid scheme")
                except Exception:
                    messages.error(request, _("notif_link_invalid"))
                    return redirect(f"{reverse('accounts:profile')}?section=publish-notification")

            # Validate + save optional image
            notif_image_url = ""
            if notif_image_file:
                _img_max_mb = 5
                _img_max_bytes = _img_max_mb * 1024 * 1024
                if getattr(notif_image_file, "size", 0) > _img_max_bytes:
                    messages.error(request, _("notif_image_too_large"))
                    return redirect(f"{reverse('accounts:profile')}?section=publish-notification")
                try:
                    validate_uploaded_file(
                        notif_image_file,
                        allowed_extensions=IMAGE_ALLOWED_EXTENSIONS,
                        max_size_mb=_img_max_mb,
                        allowed_mime_types=set(),
                        allowed_mime_prefixes=("image/",),
                    )
                except ValidationError as exc:
                    messages.error(request, exc.messages[0] if exc.messages else _("notif_image_invalid"))
                    return redirect(f"{reverse('accounts:profile')}?section=publish-notification")
                # Save image to media/notifications/images/
                randomize_uploaded_filename(notif_image_file)
                saved_path = default_storage.save(
                    os.path.join("notifications", "images", notif_image_file.name),
                    notif_image_file,
                )
                notif_image_url = default_storage.url(saved_path)

            metadata = {}
            if notif_image_url:
                metadata["image_url"] = notif_image_url

            # Resolve each selected target and collect unique recipients
            UserModel = get_user_model()
            sent_to_user_ids: set = set()
            for notif_target in notif_targets:
                recipients = _get_notification_recipients(request.user, capabilities, notif_target)
                if recipients is None:
                    continue
                # Avoid duplicate notifications to the same user
                qs_ids = list(recipients.values_list("pk", flat=True).exclude(pk__in=sent_to_user_ids))
                if not qs_ids:
                    continue
                target_recipients = UserModel.objects.filter(pk__in=qs_ids)
                create_notification_for_users(
                    recipients=target_recipients,
                    title=notif_title,
                    message=notif_message,
                    link=notif_link,
                    notification_type=NotificationType.SYSTEM,
                    metadata=metadata or None,
                )
                sent_to_user_ids.update(qs_ids)

            if sent_to_user_ids:
                messages.success(request, _("notif_sent_success"))
            else:
                messages.error(request, _("notif_no_recipients"))
            return redirect(f"{reverse('accounts:profile')}?section=publish-notification")
        elif submitted_form in {"category-create", "category-management-save", "category-management-delete"}:
            if not {"create-category", "category-management"} & set(allowed_sections) or not can_user_manage_categories(
                request.user
            ):
                messages.error(request, "Bu bölməni yalnız SuperAdmin idarə edə bilər.")
                return redirect(f"{reverse('accounts:profile')}?section=profile-info")

            if submitted_form == "category-management-delete":
                active_section = "category-management"
                category_to_delete = _load_managed_category(request.POST.get("category_id"))
                if category_to_delete is None:
                    messages.error(request, "Silinəcək kateqoriya tapılmadı.")
                    return redirect(_category_section_url(section="category-management"))

                deleted_category_name = category_to_delete.localized_full_name
                try:
                    category_to_delete.delete()
                except ProtectedError:
                    messages.error(
                        request,
                        "Bu kateqoriyanı silmək olmur. Ona bağlı alt kateqoriya və ya post mövcuddur.",
                    )
                else:
                    messages.success(request, f'"{deleted_category_name}" uğurla silindi.')
                return redirect(_category_section_url(section="category-management"))

            if submitted_form == "category-create":
                active_section = "create-category"
                category_management_bound_form = CategoryManagementForm(request.POST)

                if category_management_bound_form.is_valid():
                    saved_category = category_management_bound_form.save()
                    saved_label = "Alt kateqoriya" if saved_category.parent_id else "Kateqoriya"
                    messages.success(request, f'{saved_label} "{saved_category.localized_full_name}" uğurla yaradıldı.')
                    return redirect(_category_section_url(section="create-category"))

                category_management_create_form = category_management_bound_form
                messages.error(request, "Kateqoriya yaradılmadı. Zəhmət olmasa xətaları düzəldin.")
            else:
                active_section = "category-management"

                submitted_category_id = request.POST.get("category_id")
                category_management_edit_item = _load_managed_category(submitted_category_id)
                if submitted_category_id and category_management_edit_item is None:
                    messages.error(request, "Redaktə ediləcək kateqoriya tapılmadı.")
                    return redirect(_category_section_url(section="category-management"))

                category_management_bound_form = CategoryManagementForm(
                    request.POST,
                    instance=category_management_edit_item,
                )

                if category_management_bound_form.is_valid():
                    saved_category = category_management_bound_form.save()
                    saved_label = "Alt kateqoriya" if saved_category.parent_id else "Kateqoriya"
                    messages.success(request, f'{saved_label} "{saved_category.localized_full_name}" uğurla yeniləndi.')
                    return redirect(_category_section_url(section="category-management"))

                category_management_edit_form = category_management_bound_form
                messages.error(request, "Kateqoriya yadda saxlanmadı. Zəhmət olmasa xətaları düzəldin.")
        elif submitted_form != "edit-profile":
            target_section = request.GET.get("section") or request.POST.get("section") or active_section
            if target_section not in allowed_sections:
                target_section = "profile-info"
            return redirect(f"{reverse('accounts:profile')}?section={target_section}")

        if submitted_form == "edit-profile":
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

            # Update enhanced profile fields
            profile.student_specialization = (
                request.POST.get("student_specialization", profile.student_specialization) or ""
            ).strip()
            profile.student_group_number = (
                request.POST.get("student_group_number", profile.student_group_number) or ""
            ).strip()
            profile.department = (request.POST.get("department", profile.department) or "").strip()

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

            # Audit log for profile update
            from core.constants import AuditAction

            log_action(
                action=AuditAction.UPDATE,
                user=request.user,
                obj=profile,
                reason="Profile updated by user",
                request=request,
                resource_type="UserProfile",
                resource_id=str(profile.pk),
                resource_repr=f"{request.user.username}",
            )

            messages.success(request, pgettext_lazy("accounts.profile_edit.message", "profile_updated_successfully"))
            return redirect("accounts:profile")

    # Get user's roles
    user_roles = _build_effective_user_roles(request.user, profile)
    primary_user_role_label = user_roles[0]["label"] if user_roles else ""
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
    my_exams_count = 0
    my_exams_search_query = ""
    my_exams_filter_type = ""
    my_exams_page_obj = None
    if capabilities["can_view_owned_learning"]:
        my_created_courses = list(created_courses_qs[:10])
        my_created_courses_count = created_courses_qs.count()

        # --- Search ---
        my_exams_search_query = (request.GET.get("exam_q", "") or "").strip()
        if my_exams_search_query:
            my_exams_qs = my_exams_qs.filter(title__icontains=my_exams_search_query)

        # --- Filter by exam type ---
        my_exams_filter_type = (request.GET.get("exam_type", "") or "").strip()
        if my_exams_filter_type not in {"", "test", "written", "coding"}:
            my_exams_filter_type = ""
        if my_exams_filter_type:
            my_exams_qs = my_exams_qs.filter(exam_type=my_exams_filter_type)

        my_exams_count = my_exams_qs.count()
        my_exams_page_obj = Paginator(my_exams_qs, 6).get_page(request.GET.get("exam_page"))

    user_posts = None
    posts_count = 0
    post_category_tree = []
    post_category_root_options = []
    post_category_subcategory_options = []
    post_creation_requires_approval = False
    posting_blocked = False
    posting_blocked_reason = ""
    if capabilities["can_manage_blog"]:
        user_posts_qs = (
            Post.objects.filter(author=request.user)
            .select_related("category")
            .prefetch_related("approval_logs")
            .order_by("-created_at")
        )
        posts_count = user_posts_qs.count()
        user_posts = Paginator(user_posts_qs, 6).get_page(request.GET.get("page"))
        post_category_tree = get_post_category_tree()
        post_category_root_options, post_category_subcategory_options = build_post_category_picker_options(
            post_category_tree
        )
        post_creation_requires_approval = author_requires_post_approval(request.user)
        can_publish, blocked_reason = can_user_publish_post(request.user)
        posting_blocked = not can_publish
        posting_blocked_reason = blocked_reason

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
    my_results_page_obj = None
    my_results_search_query = ""
    my_results_pagination_query = ""
    my_results_page_param = "results_page"
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
        "written_exams": 0,
        "practical_exams": 0,
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
            search=request.GET.get("results_search"),
        )
        my_results_search_query = (request.GET.get("results_search", "") or "").strip()
        my_results_page_obj = Paginator(my_result_items, 6).get_page(request.GET.get(my_results_page_param))
        my_result_items = my_results_page_obj
        my_results_pagination_query = _query_string(
            section="my-results",
            results_type=my_results_active_filter,
            results_search=my_results_search_query,
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
            .filter(Q(checked_by_teacher=False) | Q(checked_by_teacher=True, teacher_checked_at__gte=review_cutoff))
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
    teacher_groups_filtered_count = 0
    teacher_groups_payload = {}
    teacher_groups_page = None
    teacher_groups_search_query = (request.GET.get("group_q") or "").strip()
    teacher_groups_pagination_query = ""
    selected_teacher_group = None
    selected_group_students_page = None
    selected_group_students_count = 0
    selected_group_students_filtered_count = 0
    group_students_search_query = (request.GET.get("student_q") or "").strip()
    group_students_pagination_query = ""
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

            visible_teacher_groups_qs = teacher_groups_qs
            teacher_groups_count = visible_teacher_groups_qs.count()

            if teacher_groups_search_query:
                visible_teacher_groups_qs = visible_teacher_groups_qs.filter(
                    Q(name__icontains=teacher_groups_search_query)
                    | Q(teacher__username__icontains=teacher_groups_search_query)
                    | Q(teacher__first_name__icontains=teacher_groups_search_query)
                    | Q(teacher__last_name__icontains=teacher_groups_search_query)
                    | Q(students__username__icontains=teacher_groups_search_query)
                    | Q(students__first_name__icontains=teacher_groups_search_query)
                    | Q(students__last_name__icontains=teacher_groups_search_query)
                    | Q(students__profile__student_group_number__icontains=teacher_groups_search_query)
                ).distinct()

            teacher_groups_filtered_count = visible_teacher_groups_qs.count()
            teacher_groups_page = Paginator(visible_teacher_groups_qs, 8).get_page(request.GET.get("groups_page"))
            teacher_groups = list(teacher_groups_page.object_list)

            selected_group_id = (request.GET.get("group") or "").strip()
            if selected_group_id.isdigit():
                selected_teacher_group = teacher_groups_qs.filter(id=int(selected_group_id)).first()

            teacher_groups_pagination_query = urlencode(
                {
                    key: value
                    for key, value in {
                        "section": "groups",
                        "group_q": teacher_groups_search_query,
                        "group": selected_teacher_group.id if selected_teacher_group else "",
                        "student_q": group_students_search_query if selected_teacher_group else "",
                    }.items()
                    if value not in ("", None)
                }
            )

            if selected_teacher_group:
                students_qs = selected_teacher_group.students.select_related("profile").order_by(
                    "first_name", "last_name", "username", "id"
                )
                selected_group_students_count = students_qs.count()
                if group_students_search_query:
                    students_qs = students_qs.filter(
                        Q(username__icontains=group_students_search_query)
                        | Q(first_name__icontains=group_students_search_query)
                        | Q(last_name__icontains=group_students_search_query)
                        | Q(email__icontains=group_students_search_query)
                        | Q(profile__student_group_number__icontains=group_students_search_query)
                    )
                selected_group_students_filtered_count = students_qs.count()
                selected_group_students_page = Paginator(students_qs, 12).get_page(request.GET.get("students_page"))
                group_students_pagination_query = urlencode(
                    {
                        key: value
                        for key, value in {
                            "section": "groups",
                            "group": selected_teacher_group.id,
                            "group_q": teacher_groups_search_query,
                            "groups_page": teacher_groups_page.number if teacher_groups_page else "",
                            "student_q": group_students_search_query,
                        }.items()
                        if value not in ("", None)
                    }
                )

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
            if selected_teacher_group and str(selected_teacher_group.id) not in teacher_groups_payload:
                student_ids = [student.id for student in selected_teacher_group.students.all()]
                teacher_ids = [teacher.id for teacher in selected_teacher_group.teachers.all()]
                if selected_teacher_group.teacher_id and selected_teacher_group.teacher_id not in teacher_ids:
                    teacher_ids.append(selected_teacher_group.teacher_id)
                teacher_groups_payload[str(selected_teacher_group.id)] = {
                    "name": selected_teacher_group.name,
                    "primary_teacher": selected_teacher_group.teacher_id,
                    "students": student_ids,
                    "teachers": teacher_ids,
                }

    pending_post_approval_items = []
    pending_post_approval_count = 0
    pending_post_approval_search_query = ""
    pending_post_approval_filter_status = "pending"
    pending_post_approval_filter_group = ""
    pending_post_approval_filter_organization = ""
    pending_post_approval_available_groups = []
    pending_post_approval_available_organizations = []
    pending_post_approval_page_obj = None
    pending_post_approval_pagination_query = ""
    pending_post_approval_total_count = 0
    if "pending-post-approvals" in allowed_sections:
        (
            pending_post_approval_items,
            pending_post_approval_search_query,
            pending_post_approval_filter_status,
            pending_post_approval_filter_group,
            pending_post_approval_available_groups,
            pending_post_approval_filter_organization,
            pending_post_approval_available_organizations,
        ) = collect_reviewable_posts(
            request.user,
            search=request.GET.get("approval_search"),
            status=request.GET.get("approval_status"),
            group_id=request.GET.get("approval_group"),
            organization_id=request.GET.get("approval_organization"),
        )
        pending_post_approval_total_count = len(pending_post_approval_items)
        pending_post_approval_count = count_pending_reviewable_posts(request.user)
        pending_post_approval_page_obj = Paginator(pending_post_approval_items, 10).get_page(
            request.GET.get("approval_page", 1)
        )
        extra = []
        extra.append("section=pending-post-approvals")
        if pending_post_approval_search_query:
            extra.append(f"approval_search={pending_post_approval_search_query}")
        if pending_post_approval_filter_status and pending_post_approval_filter_status != "pending":
            extra.append(f"approval_status={pending_post_approval_filter_status}")
        if pending_post_approval_filter_group:
            extra.append(f"approval_group={pending_post_approval_filter_group}")
        if pending_post_approval_filter_organization:
            extra.append(f"approval_organization={pending_post_approval_filter_organization}")
        pending_post_approval_pagination_query = "&".join(extra)

    pending_review_items = []
    pending_review_search_query = ""
    pending_review_filter_type = "all"
    pending_review_filter_status = "all"
    pending_review_submitted_order = "oldest"
    pending_review_filter_group = ""
    pending_review_available_groups = []
    pending_review_page_obj = None
    pending_review_pagination_query = ""
    evaluated_review_items = []
    evaluated_review_search_query = ""
    evaluated_review_filter_type = "all"
    evaluated_review_filter_group = ""
    evaluated_review_available_groups = []
    evaluated_review_submitted_order = "newest"
    evaluated_review_page_obj = None
    evaluated_review_pagination_query = ""
    if "pending-review" in allowed_sections or "review-results" in allowed_sections:
        (
            pending_review_items,
            pending_review_search_query,
            pending_review_filter_type,
            pending_review_filter_status,
            pending_review_submitted_order,
            pending_review_filter_group,
            pending_review_available_groups,
        ) = _collect_pending_review_items(request)
        pending_review_page_obj = Paginator(pending_review_items, 15).get_page(request.GET.get("pr_page", 1))
        pr_extra = ["section=pending-review"]
        if pending_review_search_query:
            pr_extra.append(f"search={pending_review_search_query}")
        if pending_review_filter_type != "all":
            pr_extra.append(f"type={pending_review_filter_type}")
        if pending_review_filter_status != "all":
            pr_extra.append(f"status={pending_review_filter_status}")
        if pending_review_submitted_order != "oldest":
            pr_extra.append(f"submitted_order={pending_review_submitted_order}")
        if pending_review_filter_group:
            pr_extra.append(f"pr_group={pending_review_filter_group}")
        pending_review_pagination_query = "&".join(pr_extra)

        (
            evaluated_review_items,
            evaluated_review_search_query,
            evaluated_review_filter_type,
            evaluated_review_filter_group,
            evaluated_review_available_groups,
            evaluated_review_submitted_order,
        ) = _collect_evaluated_review_items(request)
        evaluated_review_page_obj = Paginator(evaluated_review_items, 15).get_page(request.GET.get("er_page", 1))
        er_extra = ["section=review-results"]
        if evaluated_review_search_query:
            er_extra.append(f"evaluated_search={evaluated_review_search_query}")
        if evaluated_review_filter_type != "all":
            er_extra.append(f"evaluated_type={evaluated_review_filter_type}")
        if evaluated_review_filter_group:
            er_extra.append(f"evaluated_group={evaluated_review_filter_group}")
        if evaluated_review_submitted_order != "newest":
            er_extra.append(f"evaluated_submitted_order={evaluated_review_submitted_order}")
        evaluated_review_pagination_query = "&".join(er_extra)

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
    superadmin_users_section = {
        "users": [],
        "user_rows": [],
        "status_tabs": [],
        "role_options": [],
        "organization_options": [],
        "sort_options": [],
        "search_query": "",
        "status_filter": "all",
        "role_filter": "",
        "organization_filter": "",
        "group_filter": "",
        "department_filter": "",
        "sort_filter": "newest",
        "pagination_query": "",
        "page_param": "user_page",
        "post_next_url": "",
        "reset_url": "",
        "filtered_count": 0,
        "total_count": 0,
        "active_count": 0,
        "blocked_count": 0,
        "deleted_count": 0,
        "embedded_in_profile": True,
    }
    superadmin_ai_settings_section = {
        "config": None,
        "model_choices": [],
        "rate_info": {},
        "cost_estimates": {},
        "post_next_url": "",
    }
    superadmin_org_features_section = {
        "organizations": [],
        "organizations_page_param": "superadmin_feature_org_page",
        "organizations_pagination_query": "",
        "post_next_url": "",
    }
    superadmin_organizations_section = {
        "organizations": [],
        "organization_access_rows": [],
        "all_modules": [],
        "organizations_page_param": "superadmin_org_page",
        "organizations_pagination_query": "",
        "post_next_url": "",
        "pending_count": 0,
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
            management_can_assign_roles = (
                capabilities["is_superadmin"]
                or has_permission(
                    list(management_actor_permissions),
                    "role.assign",
                )
                or has_permission(
                    list(management_actor_permissions),
                    "org.manage_members",
                )
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
            teacher_student_only=capabilities.get("teacher_has_student_org_access", False),
            can_manage_students=(
                capabilities["is_superadmin"]
                or capabilities["is_org_admin"]
                or management_user_level >= STUDENT_ORG_MANAGEMENT_MIN_LEVEL
                or capabilities.get("teacher_can_manage_students", False)
            ),
            can_invite_members=(
                capabilities["is_superadmin"]
                or capabilities["is_org_admin"]
                or management_user_level >= STUDENT_ORG_MANAGEMENT_MIN_LEVEL
                or capabilities.get("teacher_can_invite_members", False)
            ),
        )
        student_org_management_section["post_next_url"] = _append_query_params(
            reverse("accounts:profile"),
            section="student-organization-management",
            management_view=student_org_management_section["active_management_view"],
            student_tab=student_org_management_section["active_student_tab"],
            teacher_tab=student_org_management_section["active_teacher_tab"],
            staff_tab=student_org_management_section["active_staff_tab"],
            student_org_search=student_org_management_section["student_search_query"],
            student_org_pending_search=student_org_management_section["pending_search_query"],
            student_org_unassigned_search=student_org_management_section["unassigned_search_query"],
            student_org_sent_invite_search=student_org_management_section["sent_invite_search_query"],
            student_org_ts_search=student_org_management_section["teacher_staff_search_query"],
            organization_search=student_org_management_section["organization_search_query"],
            organization_status=student_org_management_section["organization_status_filter"],
            organization_type=student_org_management_section["organization_type_filter"],
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

            # Include the requesting superadmin's own profile even without a formal membership
            if capabilities["is_superadmin"] and not manage_role_profiles.filter(user=request.user).exists():
                own_profile_qs = (
                    UserProfile.objects.filter(user=request.user)
                    .select_related("user")
                    .prefetch_related("user__memberships__role")
                    .distinct()
                )
                manage_role_profiles = (manage_role_profiles | own_profile_qs).distinct()

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

    if "superadmin-org-features" in allowed_sections or "superadmin-organizations" in allowed_sections:
        from apps.organizations.models import REVIEW_VISIBILITY_FEATURES, Organization

        superadmin_organizations_queryset = (
            Organization.objects.select_related("owner")
            .annotate(active_member_count=Count("memberships", filter=Q(memberships__is_active=True)))
            .order_by("name")
        )
        organization_status_filter = (request.GET.get("status") or "").strip().lower()
        if organization_status_filter in {"active", "pending", "suspended"}:
            superadmin_organizations_queryset = superadmin_organizations_queryset.filter(
                status=organization_status_filter
            )
        elif organization_status_filter == "inactive":
            superadmin_organizations_queryset = superadmin_organizations_queryset.filter(is_active=False).exclude(
                status="suspended"
            )

        if "superadmin-org-features" in allowed_sections:
            superadmin_feature_org_page = request.GET.get("superadmin_feature_org_page")
            superadmin_org_features_page = Paginator(superadmin_organizations_queryset, 12).get_page(
                superadmin_feature_org_page
            )
            for organization in superadmin_org_features_page.object_list:
                organization.review_feature_items = [
                    {
                        "key": feature_name,
                        "label": feature_config["label"],
                        "short_label": feature_config["short_label"],
                        "enabled": organization.is_review_identity_reveal_enabled(feature_name),
                    }
                    for feature_name, feature_config in REVIEW_VISIBILITY_FEATURES.items()
                ]
            superadmin_org_features_section["organizations"] = superadmin_org_features_page
            superadmin_org_features_section["organizations_pagination_query"] = _query_string(
                section="superadmin-org-features"
            )
            superadmin_org_features_section["post_next_url"] = _append_query_params(
                reverse("accounts:profile"),
                section="superadmin-org-features",
                superadmin_feature_org_page=superadmin_feature_org_page,
            )

        if "superadmin-organizations" in allowed_sections:
            superadmin_org_page = request.GET.get("superadmin_org_page")
            superadmin_organizations_section["organizations"] = Paginator(
                superadmin_organizations_queryset, 12
            ).get_page(superadmin_org_page)
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
            superadmin_organizations_section["post_next_url"] = _append_query_params(
                reverse("accounts:profile"),
                section="superadmin-organizations",
                superadmin_org_page=superadmin_org_page,
            )
            superadmin_organizations_section["pending_count"] = Organization.objects.filter(status="pending").count()

    if "superadmin-users" in allowed_sections:
        superadmin_users_section.update(
            build_superadmin_user_management_context(
                request,
                base_url=reverse("accounts:profile"),
                include_section=True,
            )
        )

    if "superadmin-ai" in allowed_sections:
        superadmin_ai_settings_section.update(build_superadmin_ai_settings_context())
        superadmin_ai_settings_section["post_next_url"] = _append_query_params(
            reverse("accounts:profile"),
            section="superadmin-ai",
        )

    # InAppNotification data for profile notifications section
    notif_filter = request.GET.get("notif_filter", "all")
    if notif_filter not in ("all", "unread", "read"):
        notif_filter = "all"
    notif_search_query = _normalize_public_profile_query_value(
        request.GET.get("notif_search"),
        max_length=100,
    )
    in_app_notifications_qs = get_user_notifications(
        user=request.user,
        filter_by=notif_filter,
        search_query=notif_search_query,
    )
    in_app_notifications_paginator = Paginator(in_app_notifications_qs, 10)
    in_app_notifications_page = in_app_notifications_paginator.get_page(request.GET.get("notif_page", 1))
    notif_pagination_query = _query_string(
        section="notifications",
        notif_filter=notif_filter,
        notif_search=notif_search_query,
    )

    # Publish-notification data (teacher groups, org info)
    publish_notification_targets = []
    if "publish-notification" in allowed_sections:
        publish_notification_targets = _get_publish_notification_targets(request.user, capabilities)

    category_management_page = None
    category_management_create_parent_options = []
    category_management_create_selected_parent_id = ""
    category_management_edit_parent_options = []
    category_management_edit_selected_parent_id = ""
    category_management_search_query = ""
    category_management_page_param = "category_page"
    category_management_pagination_query = ""
    category_management_total_count = 0
    category_management_filtered_count = 0
    if {"create-category", "category-management"} & set(allowed_sections):
        if category_management_create_form is None:
            category_management_create_form = CategoryManagementForm()

        category_management_create_parent_options = [
            {
                "value": str(category.id),
                "label": category.localized_name,
                "attrs": "",
            }
            for category in category_management_create_form.fields["parent"].queryset
        ]
        category_management_create_selected_parent_id = category_management_create_form["parent"].value() or ""

    if "category-management" in allowed_sections:
        category_management_search_query = _normalize_public_profile_query_value(
            request.GET.get("category_search"),
            max_length=100,
        )
        normalized_category_search = category_management_search_query.casefold()
        managed_categories_queryset = Category.objects.annotate(direct_post_count=Count("posts")).order_by(
            "sort_order",
            "name_en",
            "name_az",
            "id",
        )
        category_management_tree = get_post_category_tree(category_queryset=managed_categories_queryset)
        filtered_category_tree = []

        def _category_matches_search(category):
            if not normalized_category_search:
                return True
            searchable_values = (
                category.name_az,
                category.name_en,
                category.name_ru,
                category.name_tr,
                category.slug,
            )
            return any(normalized_category_search in (value or "").casefold() for value in searchable_values)

        for root_category in category_management_tree:
            root_children = list(getattr(root_category, "child_categories", []))
            matching_children = [
                child_category for child_category in root_children if _category_matches_search(child_category)
            ]
            if normalized_category_search:
                root_matches = _category_matches_search(root_category)
                if not root_matches and not matching_children:
                    continue
                visible_children = root_children if root_matches else matching_children
            else:
                visible_children = root_children

            root_category.total_child_count = len(root_children)
            root_category.can_delete = root_category.direct_post_count == 0 and not root_children
            root_category.child_categories = visible_children

            for child_category in visible_children:
                child_category.can_delete = child_category.direct_post_count == 0

            filtered_category_tree.append(root_category)

        category_management_total_count = len(category_management_tree)
        category_management_filtered_count = len(filtered_category_tree)
        category_management_page = Paginator(filtered_category_tree, 6).get_page(
            request.GET.get(category_management_page_param)
        )
        category_management_pagination_query = _query_string(
            section="category-management",
            category_search=category_management_search_query,
        )

        if category_management_edit_form is None:
            category_management_edit_item = _load_managed_category(request.GET.get("edit_category"))
            if category_management_edit_item is not None:
                category_management_edit_form = CategoryManagementForm(instance=category_management_edit_item)

        if category_management_edit_form is not None:
            category_management_edit_parent_options = [
                {
                    "value": str(category.id),
                    "label": category.localized_name,
                    "attrs": "",
                }
                for category in category_management_edit_form.fields["parent"].queryset
            ]
            category_management_edit_selected_parent_id = category_management_edit_form["parent"].value() or ""
        else:
            category_management_edit_form = CategoryManagementForm()
            category_management_edit_parent_options = [
                {
                    "value": str(category.id),
                    "label": category.localized_name,
                    "attrs": "",
                }
                for category in category_management_edit_form.fields["parent"].queryset
            ]

    # ── Statistics section context ────────────────────────────────────
    statistics_data = {}
    statistics_filters = {}
    statistics_courses = []
    statistics_groups = []
    statistics_organizations = []
    statistics_has_active_filters = False
    statistics_reset_url = _append_query_params(reverse("accounts:profile"), section="statistics")
    statistics_org_page = None
    statistics_teacher_page = None
    statistics_course_page = None
    statistics_group_page = None
    statistics_teacher_course_page = None
    statistics_org_rows = []
    statistics_teacher_rows = []
    statistics_course_rows = []
    statistics_group_rows = []
    statistics_teacher_course_rows = []
    statistics_org_page_param = "stats_org_page"
    statistics_teacher_page_param = "stats_teacher_page"
    statistics_course_page_param = "stats_course_page"
    statistics_group_page_param = "stats_group_page"
    statistics_teacher_course_page_param = "stats_teacher_course_page"
    statistics_org_pagination_query = ""
    statistics_teacher_pagination_query = ""
    statistics_course_pagination_query = ""
    statistics_group_pagination_query = ""
    statistics_teacher_course_pagination_query = ""
    if active_section == "statistics" and "statistics" in allowed_sections:
        from apps.accounts.services.statistics_selectors import (
            get_org_admin_statistics,
            get_student_statistics,
            get_superadmin_statistics,
            get_teacher_statistics,
        )
        from apps.organizations.models import Organization as _StatisticsOrganization

        stat_org = _get_active_organization(request)
        statistics_content_type = (request.GET.get("stat_content_type") or "all").strip().lower()
        if statistics_content_type not in {"all", "exam", "assignment", "lab", "project"}:
            statistics_content_type = "all"
        statistics_filters = {
            "date_from": (request.GET.get("stat_date_from") or "").strip(),
            "date_to": (request.GET.get("stat_date_to") or "").strip(),
            "course": (request.GET.get("stat_course") or "").strip() or None,
            "group": (request.GET.get("stat_group") or "").strip() or None,
            "content_type": statistics_content_type,
            "organization": (request.GET.get("stat_organization") or "").strip() or None,
        }
        statistics_has_active_filters = any(
            [
                statistics_filters["date_from"],
                statistics_filters["date_to"],
                statistics_filters["course"],
                statistics_filters["group"],
                statistics_filters["organization"],
                statistics_filters["content_type"] != "all",
            ]
        )

        selected_statistics_org = None
        if capabilities["is_superadmin"] and statistics_filters["organization"]:
            selected_statistics_org = (
                _StatisticsOrganization.objects.filter(
                    id=statistics_filters["organization"],
                    is_active=True,
                    status="active",
                )
                .only("id", "name")
                .first()
            )

        statistics_scope_org = selected_statistics_org or stat_org

        # Populate filter options
        if statistics_scope_org and not capabilities["is_superadmin"]:
            statistics_courses = list(
                Course.objects.filter(organization=statistics_scope_org).order_by("title").values("id", "title")[:100]
            )
        elif capabilities["is_superadmin"]:
            statistics_organizations = list(
                _StatisticsOrganization.objects.filter(is_active=True, status="active")
                .order_by("name")
                .values("id", "name")[:150]
            )
            superadmin_course_qs = Course.objects.all()
            if selected_statistics_org:
                superadmin_course_qs = superadmin_course_qs.filter(organization=selected_statistics_org)
            statistics_courses = list(superadmin_course_qs.order_by("title").values("id", "title")[:150])

        if statistics_scope_org:
            from apps.exams.models import StudentGroup as _SG

            statistics_groups = list(
                _SG.objects.filter(organization=statistics_scope_org).order_by("name").values("id", "name")[:100]
            )

        if capabilities["is_superadmin"]:
            statistics_data = get_superadmin_statistics(filters=statistics_filters)
        elif capabilities["is_org_admin"]:
            if stat_org:
                statistics_data = get_org_admin_statistics(organization=stat_org, filters=statistics_filters)
        elif capabilities["is_teacher"]:
            statistics_data = get_teacher_statistics(request.user, organization=stat_org, filters=statistics_filters)
        else:
            # Student / lead student / member
            statistics_data = get_student_statistics(request.user, organization=stat_org, filters=statistics_filters)

        statistics_base_query = _query_string(
            section="statistics",
            stat_date_from=statistics_filters["date_from"],
            stat_date_to=statistics_filters["date_to"],
            stat_course=statistics_filters["course"],
            stat_group=statistics_filters["group"],
            stat_content_type=(
                None if statistics_filters["content_type"] == "all" else statistics_filters["content_type"]
            ),
            stat_organization=statistics_filters["organization"],
        )

        if statistics_data.get("org_comparison"):
            statistics_org_page = Paginator(statistics_data["org_comparison"], 8).get_page(
                request.GET.get(statistics_org_page_param)
            )
            statistics_org_rows = list(statistics_org_page.object_list)
            statistics_org_pagination_query = statistics_base_query

        if statistics_data.get("teacher_overview"):
            statistics_teacher_page = Paginator(statistics_data["teacher_overview"], 8).get_page(
                request.GET.get(statistics_teacher_page_param)
            )
            statistics_teacher_rows = list(statistics_teacher_page.object_list)
            statistics_teacher_pagination_query = statistics_base_query

        if statistics_data.get("course_rankings"):
            statistics_course_page = Paginator(statistics_data["course_rankings"], 8).get_page(
                request.GET.get(statistics_course_page_param)
            )
            statistics_course_rows = list(statistics_course_page.object_list)
            statistics_course_pagination_query = statistics_base_query

        if statistics_data.get("group_comparison"):
            statistics_group_page = Paginator(statistics_data["group_comparison"], 8).get_page(
                request.GET.get(statistics_group_page_param)
            )
            statistics_group_rows = list(statistics_group_page.object_list)
            statistics_group_pagination_query = statistics_base_query

        if statistics_data.get("course_overview"):
            statistics_teacher_course_page = Paginator(statistics_data["course_overview"], 8).get_page(
                request.GET.get(statistics_teacher_course_page_param)
            )
            statistics_teacher_course_rows = list(statistics_teacher_course_page.object_list)
            statistics_teacher_course_pagination_query = statistics_base_query

        # ── AI summary (AJAX) ─────────────────────────────────────
        if request.GET.get("stat_ai_summary") == "1" and statistics_data:
            from apps.accounts.services.statistics_selectors import build_ai_stats_payload
            from apps.exams.services.ai_summary import generate_exam_statistics_summary

            role_label = (
                "superadmin"
                if capabilities["is_superadmin"]
                else (
                    "org_admin"
                    if capabilities["is_org_admin"]
                    else ("teacher" if capabilities["is_teacher"] else "student")
                )
            )
            ai_payload = build_ai_stats_payload(role=role_label, stats=statistics_data)
            result = generate_exam_statistics_summary(
                exam_title=f"Profil Statistikası ({role_label})",
                exam_type="profile_statistics",
                stats=ai_payload,
                user_id=request.user.pk,
            )
            from django.http import JsonResponse as _JR

            return _JR(result)

    section_titles = {
        "profile-info": pgettext_lazy("profile.section", "profile_info"),
        "notifications": pgettext_lazy("profile.section", "notifications"),
        "publish-notification": pgettext_lazy("profile.publish_notification", "title"),
        "posts": pgettext_lazy("profile.section", "posts"),
        "create-post": pgettext_lazy("profile.section", "create_post"),
        "create-category": "Create category",
        "category-management": "Categories",
        "courses": pgettext_lazy("profile.section", "my_courses"),
        "my-exams": pgettext_lazy("profile.section", "my_exams"),
        "my-courses": pgettext_lazy("profile.section", "my_created_courses"),
        "assigned-exams": pgettext_lazy("profile.section", "assigned_tasks"),
        "assigned-courses": pgettext_lazy("profile.section", "assigned_courses"),
        "my-results": pgettext_lazy("profile.section", "my_results"),
        "pending-answers": pgettext_lazy("accounts.pending_answers", "section_title"),
        "groups": pgettext_lazy("profile.section", "groups"),
        "pending-post-approvals": "Postların idarəetməsi",
        "pending-review": pgettext_lazy("profile.section", "pending_review"),
        "review-results": "Dəyərləndirilmiş nəticələr",
        "role-assignment": pgettext_lazy("profile.section", "role_assignment"),
        "student-organization-request": pgettext_lazy("profile.section", "join_organization"),
        "student-organization-management": pgettext_lazy("profile.section", "staff_management"),
        "permission-editor": pgettext_lazy("profile.section", "permissions"),
        "manage-roles": pgettext_lazy("profile.section", "manage_roles"),
        "superadmin-org-features": "Təşkilat özəllikləri",
        "superadmin-organizations": pgettext_lazy("profile.section", "superadmin_control"),
        "superadmin-users": pgettext_lazy("superadmin.users", "user_management_title"),
        "superadmin-ai": pgettext_lazy("superadmin.ai_settings", "title"),
        "blog": pgettext_lazy("nav", "home"),
        "edit-profile": pgettext_lazy("profile.section", "edit_profile"),
        "change-password": pgettext_lazy("profile.section", "change_password"),
        "statistics": pgettext_lazy("profile.section", "statistics"),
    }

    shortcut_sections = []
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
    direct_profile_section = getattr(request, "direct_profile_section", "")
    direct_profile_section_templates = {
        "pending-answers": "accounts/profile/sections/_pending_answers.html",
        "pending-review": "accounts/profile/sections/_pending_review.html",
        "review-results": "accounts/profile/sections/_review_results.html",
        "student-organization-management": "accounts/profile/sections/_student_org_management.html",
        "student-organization-request": "accounts/profile/sections/_student_org_request.html",
        "manage-roles": "accounts/profile/sections/_manage_roles.html",
        "permission-editor": "accounts/profile/sections/_permission_editor.html",
        "superadmin-organizations": "accounts/profile/sections/_superadmin_organizations.html",
        "superadmin-ai": "accounts/profile/sections/_superadmin_ai_settings.html",
    }

    context = {
        "profile": profile,
        "user_roles": user_roles,
        "primary_user_role_label": primary_user_role_label,
        "active_section": active_section,
        "active_section_title": active_section_title,
        "direct_profile_section": direct_profile_section,
        "direct_profile_section_template": direct_profile_section_templates.get(direct_profile_section, ""),
        "active_main_nav": "exams" if active_section in PROFILE_EXAM_NAV_SECTIONS else "",
        "allowed_sections": allowed_sections,
        "profile_base_url": reverse("accounts:profile"),
        "shortcut_sections": shortcut_sections,
        "role_capabilities": capabilities,
        "password_change_form": password_change_form,
        "user_posts": user_posts,
        "posts_count": posts_count,
        "post_category_tree": post_category_tree,
        "post_category_root_options": post_category_root_options,
        "post_category_subcategory_options": post_category_subcategory_options,
        "post_creation_requires_approval": post_creation_requires_approval,
        "posting_blocked": posting_blocked,
        "posting_blocked_reason": posting_blocked_reason,
        "my_courses": my_courses,
        "courses_count": courses_count,
        "my_exams": my_exams_page_obj,
        "my_exams_count": my_exams_count,
        "my_exams_search_query": my_exams_search_query,
        "my_exams_filter_type": my_exams_filter_type,
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
        "my_results_page_obj": my_results_page_obj,
        "my_result_counts": my_result_counts,
        "my_results_active_filter": my_results_active_filter,
        "my_results_search_query": my_results_search_query,
        "my_results_pagination_query": my_results_pagination_query,
        "my_results_page_param": my_results_page_param,
        "pending_answers_count": pending_answers_count,
        "pending_answer_items": pending_answer_items,
        "pending_answer_counts": pending_answer_counts,
        "pending_answers_active_filter": pending_answers_active_filter,
        "pending_answers_search_query": pending_answers_search_query,
        "pending_review_count": pending_review_count,
        "evaluated_review_count": evaluated_review_count,
        "teacher_groups": teacher_groups,
        "teacher_groups_count": teacher_groups_count,
        "teacher_groups_filtered_count": teacher_groups_filtered_count,
        "teacher_groups_payload": teacher_groups_payload,
        "teacher_groups_page": teacher_groups_page,
        "teacher_groups_search_query": teacher_groups_search_query,
        "teacher_groups_pagination_query": teacher_groups_pagination_query,
        "selected_teacher_group": selected_teacher_group,
        "selected_group_students_page": selected_group_students_page,
        "selected_group_students_count": selected_group_students_count,
        "selected_group_students_filtered_count": selected_group_students_filtered_count,
        "group_students_search_query": group_students_search_query,
        "group_students_pagination_query": group_students_pagination_query,
        "organization_access_rows": organization_access_rows,
        "student_member_groups": student_member_groups,
        "student_member_groups_count": student_member_groups_count,
        "student_member_groups_more_count": student_member_groups_more_count,
        "group_form": group_form,
        "can_multi_assign_group_teachers": can_multi_assign_group_teachers,
        "groups_section_return_url": groups_section_return_url,
        "pending_post_approval_items": pending_post_approval_page_obj or pending_post_approval_items,
        "pending_post_approval_count": pending_post_approval_count,
        "pending_post_approval_search_query": pending_post_approval_search_query,
        "pending_post_approval_filter_status": pending_post_approval_filter_status,
        "pending_post_approval_filter_group": pending_post_approval_filter_group,
        "pending_post_approval_filter_organization": pending_post_approval_filter_organization,
        "pending_post_approval_available_groups": pending_post_approval_available_groups,
        "pending_post_approval_available_organizations": pending_post_approval_available_organizations,
        "pending_post_approval_page_obj": pending_post_approval_page_obj,
        "pending_post_approval_pagination_query": pending_post_approval_pagination_query,
        "pending_post_approval_total_count": pending_post_approval_total_count,
        "pending_review_items": pending_review_page_obj or pending_review_items,
        "pending_review_search_query": pending_review_search_query,
        "pending_review_filter_type": pending_review_filter_type,
        "pending_review_filter_status": pending_review_filter_status,
        "pending_review_submitted_order": pending_review_submitted_order,
        "pending_review_filter_group": pending_review_filter_group,
        "pending_review_available_groups": pending_review_available_groups,
        "pending_review_total_count": len(pending_review_items),
        "pending_review_page_obj": pending_review_page_obj,
        "pending_review_pagination_query": pending_review_pagination_query,
        "evaluated_review_items": evaluated_review_page_obj or evaluated_review_items,
        "evaluated_review_search_query": evaluated_review_search_query,
        "evaluated_review_filter_type": evaluated_review_filter_type,
        "evaluated_review_filter_group": evaluated_review_filter_group,
        "evaluated_review_available_groups": evaluated_review_available_groups,
        "evaluated_review_submitted_order": evaluated_review_submitted_order,
        "evaluated_review_total_count": len(evaluated_review_items),
        "evaluated_review_page_obj": evaluated_review_page_obj,
        "evaluated_review_pagination_query": evaluated_review_pagination_query,
        "pending_student_invites": pending_student_invites,
        "pending_student_join_requests": pending_student_join_requests,
        "notifications_unread_count": notifications_unread_count,
        "in_app_unread_count": in_app_unread_count,
        "in_app_notifications_page": in_app_notifications_page,
        "notif_filter": notif_filter,
        "notif_search_query": notif_search_query,
        "notif_pagination_query": notif_pagination_query,
        "pending_student_join_org_name": pending_student_join_org_name,
        "pending_student_join_message": pending_student_join_message,
        "student_can_leave_org": student_can_leave_org,
        "publish_notification_targets": publish_notification_targets,
        "role_assignment_section": role_assignment_section,
        "student_org_request_section": student_org_request_section,
        "student_org_management_section": student_org_management_section,
        "permission_editor_section": permission_editor_section,
        "manage_roles_section": manage_roles_section,
        "superadmin_users_section": superadmin_users_section,
        "superadmin_ai_settings_section": superadmin_ai_settings_section,
        "superadmin_org_features_section": superadmin_org_features_section,
        "category_management_create_form": category_management_create_form,
        "category_management_edit_form": category_management_edit_form,
        "category_management_edit_item": category_management_edit_item,
        "category_management_page": category_management_page,
        "category_management_create_parent_options": category_management_create_parent_options,
        "category_management_create_selected_parent_id": category_management_create_selected_parent_id,
        "category_management_edit_parent_options": category_management_edit_parent_options,
        "category_management_edit_selected_parent_id": category_management_edit_selected_parent_id,
        "category_management_search_query": category_management_search_query,
        "category_management_page_param": category_management_page_param,
        "category_management_pagination_query": category_management_pagination_query,
        "category_management_total_count": category_management_total_count,
        "category_management_filtered_count": category_management_filtered_count,
        "superadmin_organizations_section": superadmin_organizations_section,
        "superadmin_pending_org_count": superadmin_organizations_section.get("pending_count", 0),
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
        "statistics_data": statistics_data,
        "statistics_filters": statistics_filters,
        "statistics_courses": statistics_courses,
        "statistics_groups": statistics_groups,
        "statistics_organizations": statistics_organizations,
        "statistics_has_active_filters": statistics_has_active_filters,
        "statistics_reset_url": statistics_reset_url,
        "statistics_org_page": statistics_org_page,
        "statistics_teacher_page": statistics_teacher_page,
        "statistics_course_page": statistics_course_page,
        "statistics_group_page": statistics_group_page,
        "statistics_teacher_course_page": statistics_teacher_course_page,
        "statistics_org_rows": statistics_org_rows,
        "statistics_teacher_rows": statistics_teacher_rows,
        "statistics_course_rows": statistics_course_rows,
        "statistics_group_rows": statistics_group_rows,
        "statistics_teacher_course_rows": statistics_teacher_course_rows,
        "statistics_org_page_param": statistics_org_page_param,
        "statistics_teacher_page_param": statistics_teacher_page_param,
        "statistics_course_page_param": statistics_course_page_param,
        "statistics_group_page_param": statistics_group_page_param,
        "statistics_teacher_course_page_param": statistics_teacher_course_page_param,
        "statistics_org_pagination_query": statistics_org_pagination_query,
        "statistics_teacher_pagination_query": statistics_teacher_pagination_query,
        "statistics_course_pagination_query": statistics_course_pagination_query,
        "statistics_group_pagination_query": statistics_group_pagination_query,
        "statistics_teacher_course_pagination_query": statistics_teacher_course_pagination_query,
    }

    context.update(
        {
            "review_items": context["pending_review_items"],
            "search_query": pending_review_search_query,
            "filter_type": pending_review_filter_type,
            "filter_status": pending_review_filter_status,
            "total_count": context["pending_review_total_count"],
            "pagination_query": pending_review_pagination_query,
            "organizations": superadmin_organizations_section.get("organizations", []),
            "all_modules": superadmin_organizations_section.get("all_modules", []),
            "profiles": manage_roles_section.get("profiles", []),
            "assignable_roles": manage_roles_section.get("assignable_roles", []),
            "roles": permission_editor_section.get("roles", []),
            "selected_role": permission_editor_section.get("selected_role"),
        }
    )
    context.update(student_org_management_section)

    return render(request, "accounts/profile.html", context)


@login_required
def statistics_export_csv(request):
    """Export current statistics data as CSV."""
    import csv
    import io

    from apps.accounts.services.statistics_selectors import (
        get_org_admin_statistics,
        get_student_statistics,
        get_superadmin_statistics,
        get_teacher_statistics,
    )

    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    capabilities = _role_capabilities(request.user, profile)
    if "statistics" not in capabilities["allowed_sections"]:
        raise Http404

    org = _get_active_organization(request)
    filters = {
        "date_from": (request.GET.get("stat_date_from") or "").strip(),
        "date_to": (request.GET.get("stat_date_to") or "").strip(),
        "course": (request.GET.get("stat_course") or "").strip() or None,
        "group": (request.GET.get("stat_group") or "").strip() or None,
        "content_type": (
            (request.GET.get("stat_content_type") or "all").strip().lower()
            if (request.GET.get("stat_content_type") or "all").strip().lower()
            in {"all", "exam", "assignment", "lab", "project"}
            else "all"
        ),
        "organization": (request.GET.get("stat_organization") or "").strip() or None,
    }

    if capabilities["is_superadmin"]:
        stats = get_superadmin_statistics(filters=filters)
    elif capabilities["is_org_admin"] and org:
        stats = get_org_admin_statistics(organization=org, filters=filters)
    elif capabilities["is_teacher"]:
        stats = get_teacher_statistics(request.user, organization=org, filters=filters)
    else:
        stats = get_student_statistics(request.user, organization=org, filters=filters)

    output = io.StringIO()
    writer = csv.writer(output)
    summary = stats.get("summary", {})
    writer.writerow(
        [
            str(pgettext_lazy("profile.statistics", "csv_header_metric")),
            str(pgettext_lazy("profile.statistics", "csv_header_value")),
        ]
    )
    for key, value in summary.items():
        writer.writerow([key.replace("_", " ").title(), value])

    from django.http import HttpResponse as _HR

    response = _HR(output.getvalue(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="statistics.csv"'
    return response


@require_safe
def public_user_profile(request, username):
    """
    Public user profile showing only published posts and non-confidential profile information.
    """
    from django.db.models import Q

    from apps.blog.models import Category, Post
    from apps.blog.selectors import filter_posts_by_category_scope, get_flat_category_tree

    profile_user = get_object_or_404(User, username=username)

    if request.user.is_authenticated and request.user == profile_user:
        return redirect("accounts:profile")

    profile, _created = UserProfile.objects.get_or_create(user=profile_user)

    published_posts = (
        Post.objects.filter(author=profile_user, is_published=True).select_related("category").order_by("-created_at")
    )

    allowed_category_slugs = set(Category.objects.values_list("slug", flat=True))
    search_query, invalid_search_query = _sanitize_public_profile_search_query(request.GET.get("q"))
    selected_category, invalid_category = _validate_public_profile_category(
        request.GET.get("category"),
        allowed_slugs=allowed_category_slugs,
    )

    user_posts_list = published_posts
    if invalid_search_query and not search_query:
        user_posts_list = user_posts_list.none()
    elif search_query:
        user_posts_list = user_posts_list.filter(
            Q(title__icontains=search_query) | Q(excerpt__icontains=search_query) | Q(content__icontains=search_query)
        )

    if invalid_category:
        user_posts_list = user_posts_list.none()
    elif selected_category:
        selected_category_obj = Category.objects.select_related("parent").filter(slug=selected_category).first()
        if selected_category_obj:
            user_posts_list = filter_posts_by_category_scope(user_posts_list, selected_category_obj)
        else:
            user_posts_list = user_posts_list.none()

    category_items = get_flat_category_tree(posts_queryset=published_posts, include_empty=False)

    raw_page_number = request.GET.get("page")
    page_number = _parse_public_profile_page_number(raw_page_number)
    if raw_page_number not in (None, "") and page_number is None:
        return HttpResponseBadRequest("Invalid page parameter.")

    paginator = Paginator(user_posts_list, 6)
    posts = paginator.get_page(page_number)

    display_name = (f"{profile_user.first_name} {profile_user.last_name}").strip() or profile_user.username
    profile_bio = (profile.bio or "").strip()
    profile_location = (profile.location or "").strip()

    query_params = QueryDict(mutable=True)
    if search_query:
        query_params["q"] = search_query
    if selected_category:
        query_params["category"] = selected_category
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
