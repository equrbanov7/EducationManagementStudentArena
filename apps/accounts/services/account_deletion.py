"""
Account deletion service.

Handles soft-delete of user accounts with cascade cleanup
of related data (memberships, course enrollments, notifications, etc.).
"""

import logging
from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.utils import timezone

from apps.audit.public import log_action
from core.constants import AuditAction

logger = logging.getLogger(__name__)
User = get_user_model()


class AccountDeletionError(Exception):
    """Raised when account deletion cannot proceed."""


def _is_last_org_admin(user):
    """
    Check if user is the sole active admin/owner for any organization.
    Prevents deletion if removing the user would leave an org without admins.
    """
    from apps.organizations.models import Membership, Organization

    # Only currently active organizations must retain at least one active admin.
    owned_orgs = Organization.objects.filter(
        owner=user,
        is_active=True,
        status="active",
    )
    if owned_orgs.exists():
        return True

    # Check if user is the last active admin in any org
    admin_memberships = Membership.objects.filter(
        user=user,
        is_active=True,
        organization__is_active=True,
        organization__status="active",
        role__level__gte=80,
    ).select_related("organization")

    for membership in admin_memberships:
        other_admins = (
            Membership.objects.filter(
                organization=membership.organization,
                is_active=True,
                organization__is_active=True,
                organization__status="active",
                role__level__gte=80,
            )
            .exclude(user=user)
            .exists()
        )
        if not other_admins:
            return True

    return False


def _resolve_actor(actor, request):
    """Əməliyyatı APARAN şəxs: açıq ``actor`` > ``request.user`` > None.

    Vacibdir, çünki audit qeydində «kim etdi» sualının cavabı budur. Əvvəllər
    ``soft_delete_account`` audit-i HƏDƏFİN adına yazırdı (self-service axını
    üçün doğru, RİM əməliyyatı üçün YANLIŞ) — indi hər iki hal düzgün işlənir.
    """
    if actor is not None:
        return actor
    request_user = getattr(request, "user", None)
    if request_user is not None and getattr(request_user, "is_authenticated", False):
        return request_user
    return None


@dataclass(frozen=True)
class AccountRestoreResult:
    """Bərpanın AÇIQ nəticəsi — «sakit uğur» qadağandır.

    QA Y-1: UI «Hesab bərpa edildi» deyirdi, hesab isə rolsuz/təşkilatsız
    qalırdı. Operator artıq nəyin geri qayıtdığını və nəyin əl müdaxiləsi
    istədiyini görür (``notices`` birbaşa RİM cavabına əlavə olunur).
    """

    memberships_restored: int = 0
    organization_restored: bool = False
    notices: tuple[str, ...] = ()


# Bərpa üçün AYRICA snapshot sahəsi saxlanmır: ``soft_delete_account``
# üzvlükləri məhz ``profile.deleted_at`` ilə EYNİ ``now`` damğası ilə deaktiv
# edir, ona görə ``(is_active=False, updated_at == deleted_at)`` cütü silinmənin
# öz izidir. Silinmədən ƏVVƏL də deaktiv olan üzvlük başqa damğa daşıyır və
# bərpada TOXUNULMUR — yəni iz həm dəqiq, həm də miqrasiyasızdır (mövcud
# soft-delete edilmiş hesablar üçün geriyə-uyğun işləyir).
def _restore_deactivated_memberships(user, deleted_at, now):
    """Silinmə anında deaktiv edilmiş üzvlükləri geri qaytarır; sayı qaytarır."""
    from apps.organizations.models import Membership

    if deleted_at is None:
        return 0
    trace = Membership.objects.filter(user=user, is_active=False, updated_at=deleted_at)
    membership_ids = list(trace.values_list("pk", flat=True))
    if not membership_ids:
        return 0
    return Membership.objects.filter(pk__in=membership_ids).update(is_active=True, updated_at=now)


def _restore_profile_organization(profile, user):
    """``profile.organization``-u bərpa olunmuş AKTİV üzvlükdən geri qaytarır."""
    from apps.organizations.models import Membership

    if profile is None or profile.organization_id:
        return False
    membership = (
        Membership.objects.filter(
            user=user,
            is_active=True,
            organization__is_active=True,
            organization__status="active",
        )
        .select_related("organization")
        .order_by("-is_primary", "-role__level", "pk")
        .first()
    )
    if membership is None:
        return False
    profile.organization = membership.organization
    return True


def _restore_notices(profile, *, memberships_restored, organization_restored):
    """Operatora göstəriləcək bildirişlər — bərpa nə qədər natamamdırsa, o qədər açıq."""
    notices = []
    if memberships_restored == 0:
        notices.append("Deaktiv edilmiş üzvlük izi tapılmadı — rol/təşkilat əl ilə təyin edilməlidir.")
    elif profile is not None and not profile.organization_id and not organization_restored:
        notices.append("Təşkilat bağlantısı bərpa oluna bilmədi — profildə təşkilat əl ilə seçilməlidir.")
    # Qrup üzvlüyü silinmədə m2m sətri kimi POZULUR; qrup sonradan silinmiş və ya
    # dəyişmiş ola bilər, ona görə avtomatik bərpa QƏSDƏN edilmir.
    notices.append("Tələbə qrupu üzvlükləri (varsa) avtomatik bərpa olunmur — əl ilə yoxlayın.")
    return tuple(notices)


def soft_delete_account(user, *, request=None, password=None, actor=None, reason=""):
    """
    Soft-delete a user account with cascade cleanup.

    Steps:
    1. Validate user can be deleted (not last org admin)
    2. Optionally verify password
    3. Deactivate all memberships
    4. Remove from student groups
    5. Soft-delete notifications
    6. Mark profile as deleted
    7. Deactivate the Django user account
    8. Log the action

    Args:
        user: The User instance to delete
        request: Optional HTTP request (for audit logging)
        password: Optional password for re-confirmation

    Raises:
        AccountDeletionError: If deletion cannot proceed
    """
    if password and not user.check_password(password):
        raise AccountDeletionError("password_incorrect")

    if _is_last_org_admin(user):
        raise AccountDeletionError("last_org_admin")

    resolved_actor = _resolve_actor(actor, request)

    with transaction.atomic():
        now = timezone.now()
        profile = getattr(user, "profile", None)
        # Təşkilat linki aşağıda NULL-lanır — audit üçün ƏVVƏLCƏDƏN oxunur.
        organization_at_deletion = getattr(profile, "organization", None)

        # 1. Deactivate all memberships
        from apps.organizations.models import Membership

        # ``updated_at=now`` TƏSADÜFİ deyil: eyni damğa aşağıda
        # ``profile.deleted_at``-a da yazılır və ``restore_account`` məhz bu cütlə
        # hansı üzvlüyün silinmə səbəbindən deaktiv olduğunu tapır.
        deactivated_memberships = Membership.objects.filter(user=user, is_active=True).update(
            is_active=False,
            updated_at=now,
        )

        # 2. Remove from student groups
        from apps.exams.models import StudentGroup

        removed_group_links = 0
        for group in StudentGroup.objects.filter(students=user):
            group.students.remove(user)
            removed_group_links += 1
        for group in StudentGroup.objects.filter(teachers=user):
            group.teachers.remove(user)
            removed_group_links += 1

        # 3. Soft-delete notifications
        from apps.notifications.models import InAppNotification

        InAppNotification.objects.filter(
            recipient=user,
            deleted_at__isnull=True,
        ).update(deleted_at=now)

        # 4. Cancel pending organization requests
        from apps.notifications.models import StudentOrganizationRequest

        StudentOrganizationRequest.objects.filter(
            user=user,
            status="pending",
        ).update(status="cancelled")

        # 5. Mark profile as deleted
        if profile:
            profile.is_deleted = True
            profile.deleted_at = now
            profile.organization = None
            profile.requested_organization = None
            profile.deleted_by = resolved_actor if resolved_actor is not None else None
            profile.deletion_reason = str(reason or "")[:300]
            profile.save(
                update_fields=[
                    "is_deleted",
                    "deleted_at",
                    "organization",
                    "requested_organization",
                    "deleted_by",
                    "deletion_reason",
                    "updated_at",
                ]
            )

        # 6. Deactivate the Django user account
        user.is_active = False
        user.save(update_fields=["is_active"])

        # 7. Log the action
        is_self_service = resolved_actor is None or getattr(resolved_actor, "pk", None) == user.pk
        log_action(
            action=AuditAction.DELETE,
            user=resolved_actor if resolved_actor is not None else user,
            organization=organization_at_deletion,
            obj=user,
            reason=(
                "User self-service account deletion"
                if is_self_service
                else f"Account soft-deleted by administrator. Reason: {str(reason or '-')[:300]}"
            ),
            changes={
                "target_username": user.username,
                "target_user_id": str(user.pk),
                "operation": "soft_delete",
                "reason_text": str(reason or "")[:300],
                # Bərpa auditi üçün: nə qədər bağlantı qopardıldı.
                "deactivated_membership_count": str(deactivated_memberships),
                "removed_group_link_count": str(removed_group_links),
            },
            request=request,
            resource_type="User",
            resource_id=str(user.pk),
            resource_repr=f"{user.username} ({user.email})",
        )

        logger.info(
            "Account soft-deleted for user %s (pk=%s)",
            user.username,
            user.pk,
        )


def _delete_owned_organizations(user):
    """Remove organizations still owned by the user before a hard delete."""
    from apps.organizations.models import Organization

    owned_organizations = Organization.objects.filter(owner=user)
    if not owned_organizations.exists():
        return

    active_owned_organizations = owned_organizations.filter(
        is_active=True,
        status="active",
    )
    if active_owned_organizations.exists():
        raise AccountDeletionError("last_org_admin")

    owned_organizations.delete()


def restore_account(user, *, request=None, actor=None, reason=""):
    """Yumşaq silinmiş hesabı bərpa edir və NƏYİN bərpa olunduğunu qaytarır.

    Silinmə TƏK bayraq dəyişikliyi deyil (üzvlüklər deaktiv olur,
    ``profile.organization`` NULL-lanır, qrup üzvlükləri silinir), ona görə
    bərpa da simmetrik olmalıdır — əks halda hesab «aktiv, amma rolsuz» qalır
    (QA Y-1: sakit sınma). Qrup üzvlüyü İSTİSNADIR: qrup artıq silinmiş və ya
    dəyişmiş ola bilər, ona görə avtomatik bərpa olunmur — bunun əvəzinə
    ``notices`` operatoru açıq xəbərdar edir.

    Args:
        user: The User instance to restore
        request: Optional HTTP request (for audit logging)
        actor: The administrator performing the restore (audit attribution)
        reason: Free-text justification recorded in the audit log

    Returns:
        ``AccountRestoreResult`` — bərpa olunan üzvlük sayı, təşkilat bağlantısı
        və operatora göstəriləcək bildirişlər.
    """
    from ..identity import user_access_is_staged

    # Staged hesab bərpa yolu ilə aktivləşdirilə bilməz (mövcud qapı qorunur).
    if user_access_is_staged(user):
        raise AccountDeletionError("staged_account_activation_forbidden")

    resolved_actor = _resolve_actor(actor, request)

    with transaction.atomic():
        now = timezone.now()
        profile = getattr(user, "profile", None)
        # İz bayraqlar təmizlənməmişdən ƏVVƏL oxunmalıdır.
        deleted_at = getattr(profile, "deleted_at", None)

        # Reactivate user
        user.is_active = True
        user.save(update_fields=["is_active"])

        # 1. Silinmə anında deaktiv edilmiş üzvlükləri geri qaytar
        memberships_restored = _restore_deactivated_memberships(user, deleted_at, now)

        # Clear soft-delete flags on profile (+ təşkilat bağlantısı)
        organization_restored = False
        if profile:
            profile.is_deleted = False
            profile.deleted_at = None
            profile.deleted_by = None
            profile.deletion_reason = ""
            # Bərpa həm də blok izlərini təmizləyir: hesab yenidən aktivdir.
            profile.blocked_at = None
            profile.blocked_by = None
            profile.block_reason = ""
            organization_restored = _restore_profile_organization(profile, user)
            profile.save(
                update_fields=[
                    "is_deleted",
                    "deleted_at",
                    "deleted_by",
                    "deletion_reason",
                    "blocked_at",
                    "blocked_by",
                    "block_reason",
                    "organization",
                    "updated_at",
                ]
            )

        notices = _restore_notices(
            profile,
            memberships_restored=memberships_restored,
            organization_restored=organization_restored,
        )

        # Log the action
        log_action(
            action=AuditAction.UPDATE,
            user=resolved_actor,
            obj=user,
            reason=f"Account restored by administrator. Reason: {str(reason or '-')[:300]}",
            changes={
                "target_username": user.username,
                "target_user_id": str(user.pk),
                "operation": "restore",
                "reason_text": str(reason or "")[:300],
                "restored_membership_count": str(memberships_restored),
                "organization_restored": str(bool(organization_restored)),
            },
            request=request,
            resource_type="User",
            resource_id=str(user.pk),
            resource_repr=f"{user.username} ({user.email})",
        )

        logger.info(
            "Account restored for user %s (pk=%s, memberships=%s, organization=%s)",
            user.username,
            user.pk,
            memberships_restored,
            organization_restored,
        )

    return AccountRestoreResult(
        memberships_restored=memberships_restored,
        organization_restored=organization_restored,
        notices=notices,
    )


def block_account(user, *, request=None, actor=None, reason=""):
    """
    Temporarily block a user account without marking it as deleted.

    This keeps account data intact so an administrator can later unblock the user.
    """
    if _is_last_org_admin(user):
        raise AccountDeletionError("last_org_admin")

    if not user.is_active:
        return

    resolved_actor = _resolve_actor(actor, request)

    with transaction.atomic():
        user.is_active = False
        user.save(update_fields=["is_active"])

        profile = getattr(user, "profile", None)
        if profile:
            profile.blocked_at = timezone.now()
            profile.blocked_by = resolved_actor if resolved_actor is not None else None
            profile.block_reason = str(reason or "")[:300]
            profile.save(update_fields=["blocked_at", "blocked_by", "block_reason", "updated_at"])

        log_action(
            action=AuditAction.UPDATE,
            user=resolved_actor,
            obj=user,
            reason=f"Account temporarily blocked. Reason: {str(reason or '-')[:300]}",
            changes={
                "target_username": user.username,
                "target_user_id": str(user.pk),
                "operation": "block",
                "reason_text": str(reason or "")[:300],
            },
            request=request,
            resource_type="User",
            resource_id=str(user.pk),
            resource_repr=f"{user.username} ({user.email})",
        )

    logger.info(
        "Account temporarily blocked for user %s (pk=%s)",
        user.username,
        user.pk,
    )


def unblock_account(user, *, request=None, actor=None, reason=""):
    """
    Restore a temporarily blocked account back to active state.
    """
    from ..identity import user_access_is_staged

    if user_access_is_staged(user):
        raise AccountDeletionError("staged_account_activation_forbidden")
    if user.is_active:
        return

    resolved_actor = _resolve_actor(actor, request)

    with transaction.atomic():
        user.is_active = True
        user.save(update_fields=["is_active"])

        profile = getattr(user, "profile", None)
        if profile:
            profile.blocked_at = None
            profile.blocked_by = None
            profile.block_reason = ""
            profile.save(update_fields=["blocked_at", "blocked_by", "block_reason", "updated_at"])

        log_action(
            action=AuditAction.UPDATE,
            user=resolved_actor,
            obj=user,
            reason=f"Account unblocked. Reason: {str(reason or '-')[:300]}",
            changes={
                "target_username": user.username,
                "target_user_id": str(user.pk),
                "operation": "unblock",
                "reason_text": str(reason or "")[:300],
            },
            request=request,
            resource_type="User",
            resource_id=str(user.pk),
            resource_repr=f"{user.username} ({user.email})",
        )

    logger.info(
        "Account unblocked for user %s (pk=%s)",
        user.username,
        user.pk,
    )


def hard_delete_account(user, *, request=None):
    """
    Permanently delete a user account from the database.
    Should only be used by superadmins.

    Args:
        user: The User instance to permanently delete
        request: Optional HTTP request (for audit logging)
    """
    username = user.username
    email = user.email
    user_pk = user.pk

    # Log before deletion (since user will be gone)
    log_action(
        action=AuditAction.DELETE,
        user=getattr(request, "user", None) if request else None,
        obj=None,
        reason=f"Permanent account deletion of user {username} ({email})",
        request=request,
        resource_type="User",
        resource_id=str(user_pk),
        resource_repr=f"{username} ({email})",
    )

    try:
        with transaction.atomic():
            _delete_owned_organizations(user)
            user.delete()
    except ProtectedError as exc:
        logger.exception(
            "Hard delete blocked for user %s (pk=%s) due to protected relations",
            username,
            user_pk,
        )
        raise AccountDeletionError("hard_delete_blocked") from exc

    logger.info(
        "Account permanently deleted for user %s (pk=%s)",
        username,
        user_pk,
    )
