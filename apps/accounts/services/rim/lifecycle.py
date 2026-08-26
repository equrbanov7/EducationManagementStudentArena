"""RİM hesab həyat dövrü — blok / blokdan çıxarma / soft-delete / bərpa.

Mexanizm TƏKRAR YARADILMIR: mövcud `apps.accounts.services.account_deletion`
servisi (kaskad təmizləmə, «son admin» qoruması, audit) olduğu kimi işlədilir.
Bu qat yalnız RİM-ə xas olanı əlavə edir: icazə qapısı, iyerarxiya yoxlaması,
məcburi səbəb mətni və status uyğunluğu.

**HARD DELETE YOXDUR.** Silinən hesabın qiymət/jurnal/imtahan yazıları
toxunulmaz qalır — yalnız hesab girişi bağlanır və hesab siyahılardan gizlənir.
`account_deletion.hard_delete_account` mövcuddur, amma RİM səthindən QƏSDƏN
çağırılmır (yalnız superadminin köhnə bölməsində).
"""

from __future__ import annotations

import logging

from ..account_deletion import (
    AccountDeletionError,
    block_account,
    restore_account,
    soft_delete_account,
    unblock_account,
)
from .policy import (
    PERM_BLOCK,
    PERM_SOFT_DELETE,
    RimAccessError,
    RimActor,
    assert_can_manage,
    require_permission,
)
from .search import STATUS_ACTIVE, STATUS_BLOCKED, STATUS_DELETED, account_status

logger = logging.getLogger(__name__)

MIN_REASON_LENGTH = 3
MAX_REASON_LENGTH = 300


def normalize_reason(raw_reason, *, required=True) -> str:
    """Səbəb mətnini təmizləyir. Dağıdıcı əməliyyatlarda səbəb MƏCBURİDİR."""
    reason = " ".join(str(raw_reason or "").strip().split())[:MAX_REASON_LENGTH]
    if required and len(reason) < MIN_REASON_LENGTH:
        raise RimAccessError(
            "reason_required",
            "Səbəb yazılmalıdır (ən azı 3 simvol).",
            status=400,
        )
    return reason


def _wrap_deletion_error(exc: AccountDeletionError) -> RimAccessError:
    code = str(exc)
    if code == "last_org_admin":
        return RimAccessError(
            "last_org_admin",
            "Bu hesab təşkilatın son aktiv administratorudur — əvvəlcə başqa admin təyin edin.",
            status=409,
        )
    return RimAccessError("account_operation_failed", "Əməliyyat tamamlana bilmədi.", status=409)


def block_user(actor: RimActor, target_user, *, reason, request=None):
    """Hesabı bloklayır (`is_active=False`) — data toxunulmaz qalır."""
    require_permission(actor, PERM_BLOCK)
    assert_can_manage(actor, target_user)
    reason = normalize_reason(reason)

    status = account_status(target_user)
    if status == STATUS_DELETED:
        raise RimAccessError("already_deleted", "Hesab artıq silinib.", status=409)
    if status == STATUS_BLOCKED:
        raise RimAccessError("already_blocked", "Hesab artıq bloklanıb.", status=409)

    try:
        block_account(target_user, request=request, actor=actor.user, reason=reason)
    except AccountDeletionError as exc:
        raise _wrap_deletion_error(exc) from exc
    return reason


def unblock_user(actor: RimActor, target_user, *, reason, request=None):
    """Blokdan çıxarır. Silinmiş hesab üçün əvvəlcə bərpa tələb olunur."""
    require_permission(actor, PERM_BLOCK)
    assert_can_manage(actor, target_user)
    reason = normalize_reason(reason, required=False)

    status = account_status(target_user)
    if status == STATUS_DELETED:
        raise RimAccessError(
            "restore_first",
            "Silinmiş hesabın blokunu açmaq üçün əvvəlcə hesabı bərpa edin.",
            status=409,
        )
    if status == STATUS_ACTIVE:
        raise RimAccessError("already_active", "Hesab onsuz da aktivdir.", status=409)

    unblock_account(target_user, request=request, actor=actor.user, reason=reason)
    return reason


def soft_delete_user(actor: RimActor, target_user, *, reason, request=None):
    """Hesabı YUMŞAQ silir — tarixi akademik yazılar qalır, giriş bağlanır."""
    require_permission(actor, PERM_SOFT_DELETE)
    assert_can_manage(actor, target_user)
    reason = normalize_reason(reason)

    if account_status(target_user) == STATUS_DELETED:
        raise RimAccessError("already_deleted", "Hesab artıq silinib.", status=409)

    try:
        soft_delete_account(target_user, request=request, actor=actor.user, reason=reason)
    except AccountDeletionError as exc:
        raise _wrap_deletion_error(exc) from exc
    return reason


def restore_user(actor: RimActor, target_user, *, reason, request=None):
    """Yumşaq silinmiş hesabı bərpa edir (giriş + rol/təşkilat bağlantıları).

    `AccountRestoreResult` qaytarır (digər lifecycle funksiyalarından fərqli
    olaraq `reason` YOX): bərpa natamam ola bilər və səth qatı operatora
    dəqiq nəyin əl müdaxiləsi istədiyini deməlidir (QA Y-1).
    """
    require_permission(actor, PERM_SOFT_DELETE)
    assert_can_manage(actor, target_user)
    reason = normalize_reason(reason, required=False)

    if account_status(target_user) != STATUS_DELETED:
        raise RimAccessError("not_deleted", "Hesab silinməyib.", status=409)

    return restore_account(target_user, request=request, actor=actor.user, reason=reason)


__all__ = [
    "MAX_REASON_LENGTH",
    "MIN_REASON_LENGTH",
    "block_user",
    "normalize_reason",
    "restore_user",
    "soft_delete_user",
    "unblock_user",
]
