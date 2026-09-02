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

import uuid
from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import connection, transaction
from django.utils import timezone

from apps.audit.public import log_action
from core.constants import AuditAction

from ..identity_models import AccountActivationEvidence
from ..models import UserProfile
from .identity_access import (
    _EVIDENCE_DIGEST_RE,
    IdentityAccessError,
    _assert_tenant_permission,
    _real_actor,
    activate_staged_account,
)

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


@dataclass(frozen=True)
class ArchiveRestoreResult:
    user: object
    restored: bool


def _restore_with_postgres_function(*, evidence_id, locked_user, organization, expected_role, actor, digest, reason):
    """0018-dəki YEGANƏ sanksiyalanmış səth — bütün qapılar funksiyanın içindədir.

    Aktivasiya sübutu (0013) append-only və BİRDƏFƏLİKDİR, ona görə arxivi geri
    almaq üçün ondan istifadə etmək mümkün deyil; 0018 ayrıca, eyni sərtlikdə
    bərpa sübutu və ``accounts_restore_archived_identity`` funksiyası əlavə edir.
    """

    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting('app.current_user_id', true)")
        current_actor = cursor.fetchone()[0] or ""
        if current_actor and current_actor != str(actor.pk):
            raise PermissionDenied("identity_actor_database_context_mismatch")
        cursor.execute("SELECT set_config('app.current_user_id', %s, true)", [str(actor.pk)])
        cursor.execute(
            "SELECT public.accounts_restore_archived_identity(%s, %s, %s, %s, %s, %s, %s)",
            [
                str(evidence_id),
                locked_user.pk,
                str(organization.pk),
                str(expected_role.pk),
                actor.pk,
                digest,
                reason,
            ],
        )


def _restore_without_postgres(*, locked_user, organization, expected_role, actor, profile):
    """sqlite (yalnız test) yolu: trigger yoxdur, qapılar Python tərəfindədir."""

    from apps.organizations.models import Membership

    Membership.objects.filter(user=locked_user, organization=organization).update(
        role=expected_role, is_active=True, is_primary=True, assigned_by=actor, updated_at=timezone.now()
    )
    profile.access_state = UserProfile.AccessState.ACTIVE
    profile.save(update_fields=["access_state", "updated_at"])


@transaction.atomic
def restore_archived_account(
    *,
    user,
    organization,
    expected_role,
    actor,
    email_authority_evidence_digest,
    email_authority_reason_code,
    request=None,
):
    """``archived`` hesabı yenidən AKTİV et — səhv arxiv qərarının geri alınması.

    Niyə lazımdır (2026-09-02 auditi, P0-1).  Köçürmə qəbul ili həll olunmayan
    2 291 CARİ tələbəni «məzun» sayıb arxivləmişdi; onların girişi
    ``identity.user_access_is_login_blocked`` ilə bağlıdır.  Faza qaydası
    düzəldildi (``rehearsal_sar_phase`` A2-fix), amma ARTIQ KÖÇÜRÜLMÜŞ hədəfdə
    qərarı geri almaq üçün ayrıca, auditli səth lazımdır.

    Qapılar zəifləmir: aktor icazəsi Python tərəfdə (``member.edit``) VƏ 0018-dəki
    ``accounts_restore_archived_identity`` funksiyasının içində yenidən yoxlanılır;
    keçidin özü append-only bərpa sübutu olmadan mümkün deyil.

    İdempotentdir: onsuz da ``active`` olan hesab üçün ``restored=False`` qaytarır.
    Heç bir sətir SİLİNMİR — arxiv sübutu da, bərpa sübutu da qalır.
    """

    actor = _real_actor(actor, request)
    _assert_tenant_permission(actor, organization, "member.edit")
    evidence_digest = str(email_authority_evidence_digest or "").strip().lower()
    reason_code = str(email_authority_reason_code or "").strip()
    if not _EVIDENCE_DIGEST_RE.fullmatch(evidence_digest):
        raise IdentityAccessError("identity_email_authority_evidence_required")
    if reason_code not in AccountActivationEvidence.Reason.values:
        raise IdentityAccessError("identity_email_authority_reason_invalid")
    if (
        expected_role is None
        or str(getattr(expected_role, "organization_id", "")) != str(organization.pk)
        or not getattr(expected_role, "is_active", False)
    ):
        raise IdentityAccessError("identity_expected_role_invalid")

    locked_user = User._default_manager.select_for_update().filter(pk=getattr(user, "pk", None)).first()
    if locked_user is None:
        raise IdentityAccessError("identity_target_missing")
    profile = _locked_profile(locked_user, organization)
    if profile.access_state == UserProfile.AccessState.ACTIVE:
        locked_user.profile = profile
        return ArchiveRestoreResult(user=locked_user, restored=False)
    if profile.access_state != UserProfile.AccessState.ARCHIVED:
        raise IdentityAccessError("identity_archived_state_inconsistent")
    if not locked_user.is_active:
        raise IdentityAccessError("identity_archived_state_inconsistent")

    if connection.vendor == "postgresql":
        _restore_with_postgres_function(
            evidence_id=uuid.uuid4(),
            locked_user=locked_user,
            organization=organization,
            expected_role=expected_role,
            actor=actor,
            digest=evidence_digest,
            reason=reason_code,
        )
        profile.refresh_from_db(fields=["access_state", "updated_at"])
    else:
        _restore_without_postgres(
            locked_user=locked_user,
            organization=organization,
            expected_role=expected_role,
            actor=actor,
            profile=profile,
        )
    locked_user.profile = profile

    log_action(
        action=AuditAction.UPDATE,
        user=actor,
        organization=organization,
        obj=locked_user,
        old_values={"access_state": "archived"},
        new_values={"access_state": "active"},
        reason="legacy_repair:archive_status",
        changes={"role_id": str(expected_role.pk)},
        request=request,
    )
    return ArchiveRestoreResult(user=locked_user, restored=True)


__all__ = [
    "ARCHIVE_ROLE_NAME",
    "AccountArchiveResult",
    "ArchiveRestoreResult",
    "archive_staged_account",
    "restore_archived_account",
]
