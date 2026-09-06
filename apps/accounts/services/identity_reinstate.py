"""Bərpa əmri ilə girişin açılması — tələbə hərəkəti üçün sanksiyalanmış səth.

Kontekst. Xaric/məzun əmri profili ``archived`` edir və giriş məhz orada
bağlanır (bax :mod:`identity_archive`). Əks istiqamət 0016-nın trigger-i ilə
qorunur: ``archived → active`` yalnız EYNİ tranzaksiyada bərpa sübutu varsa
mümkündür, sübut cədvəlinə isə yalnız ``SECURITY DEFINER`` funksiyaları yaza
bilər (0013/0018 REVOKE ALL + RLS).

0018-in mövcud funksiyası (`restore_archived_account`) SƏHV ARXİV QƏRARININ
geri alınması üçündür: aktordan ``member.edit`` istəyir, üzvlüyün rolunu
sıfırlayır və e-poçt səlahiyyət sübutu tələb edir. Tələbənin BƏRPA ƏMRİ isə
başqa haldır — ona görə 0021 ayrıca funksiya verir
(``accounts_reinstate_student_identity``), bu modul da onun Python səthidir.

Səlahiyyət ayrılığı DƏYİŞMİR: aktor həm ``student.movement``, həm
``people.manage_academic`` daşımalıdır — servis qatındakı
``people/movements.py::_require`` ilə eyni cütlük, funksiyanın içində (``?&``)
təkrar yoxlanılır.

Sübut nədir? Rəsmi əmrin özü: nömrə + tarix + akademik qeyd + aktor
:func:`order_evidence_digest` ilə sha256-ya çevrilir. Yəni sübut sətri hansı
əmrə əsasən açıldığını göstərir və əmr sonradan dəyişdirilsə digest uyuşmaz.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import connection, transaction
from django.utils import timezone

from apps.audit.public import log_action
from core.constants import AuditAction

from ..identity_models import AccountRestoreEvidence
from ..models import UserProfile
from .identity_access import IdentityAccessError, _real_actor
from .identity_archive import _locked_profile

User = get_user_model()

#: Sübut kodu — 0021-dəki funksiya onu sabit yazır, burada yalnız audit üçün.
REINSTATEMENT_REASON_CODE = "student_reinstatement_order"


@dataclass(frozen=True)
class ReinstateResult:
    user: object
    reopened: bool
    notice: str = ""


def order_evidence_digest(*, order_number: str, order_date, record_id, actor_id) -> str:
    """Rəsmi bərpa əmrinin sha256 barmaq izi (funksiya `^[0-9a-f]{64}$` istəyir)."""

    raw = "|".join(
        [
            "student_reinstatement",
            str(order_number or "").strip(),
            str(order_date or ""),
            str(record_id or ""),
            str(actor_id or ""),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _reinstate_with_postgres(*, evidence_id, locked_user, organization, actor, digest):
    """0021-dəki yeganə sanksiyalanmış səth — bütün qapılar funksiyanın içindədir."""

    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting('app.current_user_id', true)")
        current_actor = cursor.fetchone()[0] or ""
        if current_actor and current_actor != str(actor.pk):
            raise PermissionDenied("identity_actor_database_context_mismatch")
        cursor.execute("SELECT set_config('app.current_user_id', %s, true)", [str(actor.pk)])
        cursor.execute(
            "SELECT public.accounts_reinstate_student_identity(%s, %s, %s, %s, %s)",
            [str(evidence_id), locked_user.pk, str(organization.pk), actor.pk, digest],
        )


def _reinstate_without_postgres(*, evidence_id, locked_user, organization, actor, profile, digest):
    """sqlite (yalnız test) yolu: trigger yoxdur, sübut sətrini Python yazır."""

    from apps.organizations.models import Membership

    membership = Membership.objects.filter(user=locked_user, organization=organization).first()
    if membership is not None and not membership.is_active:
        membership.is_active = True
        membership.save(update_fields=["is_active", "updated_at"])
    profile.access_state = UserProfile.AccessState.ACTIVE
    profile.save(update_fields=["access_state", "updated_at"])
    AccountRestoreEvidence.objects.create(
        id=evidence_id,
        organization=organization,
        user_ref=str(locked_user.pk),
        role_ref=str(getattr(membership, "role_id", "") or ""),
        actor_ref=str(actor.pk),
        evidence_digest=digest,
        reason_code=REINSTATEMENT_REASON_CODE,
        transaction_id=0,
        consumed_at=timezone.now(),
    )


@transaction.atomic
def reinstate_student_access(*, user, organization, actor, evidence_digest, request=None) -> ReinstateResult:
    """``archived`` tələbə hesabının girişini rəsmi bərpa əmri ilə açır.

    İdempotentdir: onsuz da ``active`` hesab üçün ``reopened=False`` qaytarır.
    Səlahiyyət qapısı funksiyanın İÇİNDƏDİR (superadmin / təşkilat sahibi /
    ``student.movement`` + ``people.manage_academic``) — Python tərəfdə təkrar
    yoxlama yoxdur ki, iki fərqli qayda yaranmasın.
    """

    actor = _real_actor(actor, request)
    digest = str(evidence_digest or "").strip().lower()
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise IdentityAccessError("identity_reinstatement_evidence_required")

    locked_user = User._default_manager.select_for_update().filter(pk=getattr(user, "pk", None)).first()
    if locked_user is None:
        raise IdentityAccessError("identity_target_missing")
    profile = _locked_profile(locked_user, organization)
    if profile.access_state == UserProfile.AccessState.ACTIVE:
        locked_user.profile = profile
        return ReinstateResult(user=locked_user, reopened=False)
    if profile.access_state != UserProfile.AccessState.ARCHIVED:
        raise IdentityAccessError("identity_archived_state_inconsistent")
    if not locked_user.is_active:
        raise IdentityAccessError("identity_archived_state_inconsistent")

    evidence_id = uuid.uuid4()
    if connection.vendor == "postgresql":
        _reinstate_with_postgres(
            evidence_id=evidence_id,
            locked_user=locked_user,
            organization=organization,
            actor=actor,
            digest=digest,
        )
        profile.refresh_from_db(fields=["access_state", "updated_at"])
    else:
        _reinstate_without_postgres(
            evidence_id=evidence_id,
            locked_user=locked_user,
            organization=organization,
            actor=actor,
            profile=profile,
            digest=digest,
        )
    locked_user.profile = profile

    log_action(
        action=AuditAction.UPDATE,
        user=actor,
        organization=organization,
        obj=locked_user,
        old_values={"access_state": "archived"},
        new_values={"access_state": "active"},
        reason=REINSTATEMENT_REASON_CODE,
        changes={"evidence_id": str(evidence_id)},
        request=request,
    )
    return ReinstateResult(user=locked_user, reopened=True)


__all__ = [
    "REINSTATEMENT_REASON_CODE",
    "ReinstateResult",
    "order_evidence_digest",
    "reinstate_student_access",
]
