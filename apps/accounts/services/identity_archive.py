"""Arxiv hesab körpüsü — məzun/xaric hesabın DATA-sı qalır, GİRİŞİ bağlanır.

Problem. ``registrar`` tərəfindəki ``registrar_guard_active_member`` trigger-i
(``registrar_member_has_permission``, migration 0042) bir tələbə sətrini yalnız
DÖRD şərtin hamısı ödənəndə qəbul edir: ``organization.is_active``,
``membership.is_active``, ``role.is_active`` VƏ ``auth_user.is_active``. Yəni
``is_active=False`` qalan məzun hesabına NƏ ``Enrollment``, NƏ
``StudentAcademicRecord`` yazmaq mümkün deyil — onların bütün tarixi jurnal
datası köçə bilmir.

Həll (spec A2(a)). Hesab ``is_active=True`` olur (trigger keçir), amma profil
``access_state='archived'`` vəziyyətinə düşür və GİRİŞ məhz orada bağlanır:
``identity.user_access_is_login_blocked`` backend, login forması, OTP səthləri,
middleware, parol sıfırlama və view-as qapılarının HAMISINI eyni anda bağlayır.
Portal təsnifatı (müəllim/tələbə) QAPI DEYİL — rolsuz/naməlum rol əməkdaş
portalına düşdüyü üçün blok mütləq ``access_state`` qatında olmalıdır.

Niyə yeni SECURITY DEFINER funksiya yazılmır (E-10). Arxivləşdirmə mövcud
``activate_staged_account``-u OLDUĞU KİMİ çağırır — beləliklə aktor icazəsi,
tenant aktivliyi, üzvlük dəsti, ``AccountActivationEvidence`` və audit sətri
tam olaraq həmişəki qapılardan keçir — və dərhal SONRA, EYNİ tranzaksiyada
profil ``active → archived`` endirilir. ``accounts_reject_active_staged_profile``
trigger-i ``staged → *`` keçidində evidence tələb edir; ``active → archived``
keçidi isə MƏHDUDLAŞDIRICI olduğu üçün sərbəstdir. Əks istiqamət (``archived``
vəziyyətindən çıxmaq) 0016 migration-ı ilə eyni evidence qapısına bağlanır.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import transaction

from apps.audit.public import log_action
from core.constants import AuditAction

from ..models import UserProfile
from .identity_access import IdentityAccessError, _assert_tenant_permission, _real_actor, activate_staged_account

User = get_user_model()

#: Arxiv üzvlüyünün rol adı — icazə dəsti BOŞ, level ən aşağı (bax
#: ``organizations.default_roles_university``). Rol trigger qapısını açır,
#: hüquq VERMİR.
ARCHIVE_ROLE_NAME = "alumni"


@dataclass(frozen=True)
class AccountArchiveResult:
    user: object
    archived: bool


def _locked_profile(locked_user, organization):
    profile = UserProfile.objects.select_for_update().filter(user=locked_user, organization=organization).first()
    if profile is None:
        raise PermissionDenied("identity_target_cross_tenant")
    return profile


def _assert_archive_membership(locked_user, organization, expected_role):
    """İdempotent yol: arxiv artıq qurulubsa üzvlük dəsti hələ də düzgün olmalıdır."""

    from apps.organizations.models import Membership

    memberships = list(
        Membership.objects.filter(user=locked_user, organization=organization).select_related("role").order_by("pk")
    )
    if len(memberships) != 1 or memberships[0].role_id != getattr(expected_role, "pk", None):
        raise IdentityAccessError("identity_membership_set_mismatch")
    if not memberships[0].is_active:
        raise IdentityAccessError("identity_archived_state_inconsistent")


@transaction.atomic
def archive_staged_account(
    *,
    user,
    organization,
    expected_role,
    actor,
    email_authoritative,
    email_authority_evidence_digest,
    email_authority_reason_code,
    request=None,
):
    """Bir ``staged`` hesabı ARXİVƏ keçirir: üzvlük aktiv, giriş bağlı.

    ``expected_role`` arxiv rolu olmalıdır (``alumni``) — çağıran tərəf üzvlüyün
    rolunu ƏVVƏLCƏDƏN ona keçirməlidir, çünki ``activate_staged_account`` dəqiq
    bir üzvlük və dəqiq bu rolu tələb edir (``identity_membership_set_mismatch``).

    İdempotentdir: artıq arxivlənmiş hesab üçün ``archived=False`` qaytarır və
    heç nəyə toxunmur.
    """

    actor = _real_actor(actor, request)
    _assert_tenant_permission(actor, organization, "member.edit")

    locked_user = User._default_manager.select_for_update().filter(pk=getattr(user, "pk", None)).first()
    if locked_user is None:
        raise IdentityAccessError("identity_target_missing")
    profile = _locked_profile(locked_user, organization)

    if profile.access_state == UserProfile.AccessState.ARCHIVED:
        # Təkrar run: arxiv onsuz da qurulub. Fail-closed — hesabın trigger
        # qapısını açan hər üç şərt hələ də yerindədirmi?
        if not locked_user.is_active:
            raise IdentityAccessError("identity_archived_state_inconsistent")
        _assert_archive_membership(locked_user, organization, expected_role)
        locked_user.profile = profile
        return AccountArchiveResult(user=locked_user, archived=False)

    activate_staged_account(
        user=locked_user,
        organization=organization,
        expected_role=expected_role,
        actor=actor,
        email_authoritative=email_authoritative,
        email_authority_evidence_digest=email_authority_evidence_digest,
        email_authority_reason_code=email_authority_reason_code,
        request=request,
    )

    profile = _locked_profile(locked_user, organization)
    if profile.access_state != UserProfile.AccessState.ACTIVE:
        raise IdentityAccessError("identity_archive_state_inconsistent")
    profile.access_state = UserProfile.AccessState.ARCHIVED
    profile.save(update_fields=["access_state", "updated_at"])
    locked_user.refresh_from_db(fields=["is_active"])
    locked_user.profile = profile

    log_action(
        action=AuditAction.UPDATE,
        user=actor,
        organization=organization,
        obj=locked_user,
        old_values={"access_state": "active", "is_active": True},
        new_values={"access_state": "archived", "is_active": True},
        reason="legacy_account_archived",
        changes={"role_id": str(getattr(expected_role, "pk", ""))},
        request=request,
    )
    return AccountArchiveResult(user=locked_user, archived=True)


__all__ = [
    "ARCHIVE_ROLE_NAME",
    "AccountArchiveResult",
    "archive_staged_account",
]
