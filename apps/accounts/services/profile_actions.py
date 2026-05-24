"""
Profile page POST-action services (FAZA 8 refactor).

The ``accounts.views.profile.user_profile`` view historically grew to ~1900
lines because every profile-section POST handler lived inline. This module
extracts that logic into small, testable, reusable service functions so the
view stays thin.

Each function returns a plain result object / value and never touches the
HTTP request directly beyond what is passed in — keeping it unit-testable.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.images import get_image_dimensions
from django.core.files.storage import default_storage

from apps.notifications.models import NotificationType
from apps.notifications.services import create_notification_for_users
from core.upload_security import (
    IMAGE_ALLOWED_EXTENSIONS,
    randomize_uploaded_filename,
    validate_uploaded_file,
)

# Profile-avatar upload limits. Defined here (a service module) rather than
# imported from views._helpers so the service layer never depends on the view
# layer — that would risk a circular import and inverts the dependency
# direction. views._helpers re-exports these names for backward compatibility.
MAX_PROFILE_AVATAR_SIZE_BYTES = 10 * 1024 * 1024
PROFILE_AVATAR_ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


def validate_profile_avatar_upload(uploaded_avatar) -> str:
    """Validate a profile-avatar upload.

    Returns an empty string when the file is valid, otherwise a human-readable
    Azerbaijani error message. Extracted verbatim from the former
    ``_validate_avatar_upload`` closure inside ``user_profile``.
    """
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


# ── publish-notification action ────────────────────────────────────────────


def resolve_notification_recipients(user, capabilities, target: str):
    """Resolve a notification *target* string to a queryset of recipient users.

    Returns a queryset/list of users, or ``None`` when the target is invalid
    or *user* is not authorised for it. Extracted verbatim from the former
    ``_get_notification_recipients`` helper in ``views.profile``.
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
        # Superadmin can target any org; org admin only their own.
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
        # Only the teacher who owns the group (or superadmin) may target it.
        if not is_superadmin and group.teacher_id != user.pk:
            return None
        return group.students.filter(is_active=True)

    return None


# Result message keys returned by publish_system_notification. The view maps
# these to translated, user-facing strings via gettext.
PUBLISH_NOTIFICATION_TITLE_REQUIRED = "notif_title_required"
PUBLISH_NOTIFICATION_LINK_INVALID = "notif_link_invalid"
PUBLISH_NOTIFICATION_IMAGE_TOO_LARGE = "notif_image_too_large"
PUBLISH_NOTIFICATION_IMAGE_INVALID = "notif_image_invalid"
PUBLISH_NOTIFICATION_SENT = "notif_sent_success"
PUBLISH_NOTIFICATION_NO_RECIPIENTS = "notif_no_recipients"

_NOTIFICATION_IMAGE_MAX_MB = 5


def publish_system_notification(*, request, capabilities) -> tuple[bool, str]:
    """Handle the profile page's "publish-notification" POST action.

    Reads the notification fields from ``request.POST`` / ``request.FILES``,
    validates them, fans out to the resolved recipients, and returns
    ``(ok, message_key)`` where *message_key* is one of the
    ``PUBLISH_NOTIFICATION_*`` constants above. The caller is responsible for
    turning the key into a translated flash message.
    """
    notif_title = (request.POST.get("notif_title") or "").strip()
    notif_message = (request.POST.get("notif_message") or "").strip()

    # Accept multiple targets submitted as a checkbox list.
    notif_targets = [t.strip() for t in request.POST.getlist("notif_targets") if t.strip()]
    # Fall back to the old single-value field for backward compatibility.
    if not notif_targets:
        single = (request.POST.get("notif_target") or "").strip()
        if single:
            notif_targets = [single]
    if not notif_targets:
        notif_targets = ["all"]

    notif_link = (request.POST.get("notif_link") or "").strip()
    notif_image_file = request.FILES.get("notif_image")

    if not notif_title:
        return False, PUBLISH_NOTIFICATION_TITLE_REQUIRED

    # Validate the optional link — require an explicit http/https scheme.
    if notif_link:
        try:
            parsed_link = urlparse(notif_link)
            if parsed_link.scheme not in ("http", "https"):
                raise ValueError("invalid scheme")
        except Exception:
            return False, PUBLISH_NOTIFICATION_LINK_INVALID

    # Validate + persist the optional image.
    notif_image_url = ""
    if notif_image_file:
        max_bytes = _NOTIFICATION_IMAGE_MAX_MB * 1024 * 1024
        if getattr(notif_image_file, "size", 0) > max_bytes:
            return False, PUBLISH_NOTIFICATION_IMAGE_TOO_LARGE
        try:
            validate_uploaded_file(
                notif_image_file,
                allowed_extensions=IMAGE_ALLOWED_EXTENSIONS,
                max_size_mb=_NOTIFICATION_IMAGE_MAX_MB,
                allowed_mime_types=set(),
                allowed_mime_prefixes=("image/",),
            )
        except ValidationError:
            return False, PUBLISH_NOTIFICATION_IMAGE_INVALID
        randomize_uploaded_filename(notif_image_file)
        saved_path = default_storage.save(
            os.path.join("notifications", "images", notif_image_file.name),
            notif_image_file,
        )
        notif_image_url = default_storage.url(saved_path)

    metadata = {"image_url": notif_image_url} if notif_image_url else {}

    # Resolve each selected target and collect unique recipients.
    User = get_user_model()
    sent_to_user_ids: set = set()
    for notif_target in notif_targets:
        recipients = resolve_notification_recipients(request.user, capabilities, notif_target)
        if recipients is None:
            continue
        qs_ids = list(recipients.values_list("pk", flat=True).exclude(pk__in=sent_to_user_ids))
        if not qs_ids:
            continue
        target_recipients = User.objects.filter(pk__in=qs_ids)
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
        return True, PUBLISH_NOTIFICATION_SENT
    return False, PUBLISH_NOTIFICATION_NO_RECIPIENTS
