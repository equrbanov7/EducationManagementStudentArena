"""RİM — müəllim / əməkdaş «Arxivə göndər» / «Arxivdən çıxar» (sahib 2026-11-04).

Qayda və səbəb ``retired.py``-dədir (yeni sxem yoxdur): giriş «İşdən ayrılıb» səbəb kodu ilə bağlanır,
təşkilatdakı aktiv üzvlüklər ``profile.blocked_at`` damğası ilə deaktiv olur. Bərpa EYNİ izi geri açır. Heç bir
sətir silinmir — jurnal, qiymət, dərs yükü tarixçəsi qalır. Tələbə bu yoldan keçmir (məzun / xaric əmri, registrar).

Qapılar: ``user.block`` + ``assert_can_manage`` + ``assert_no_foreign_authority`` (hesab qlobaldır) + tələbə deyil.
"""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone
from django.utils.translation import pgettext

from apps.audit.public import log_action
from core.constants import AuditAction

from ..account_deletion import AccountDeletionError, block_account, unblock_account
from .lifecycle import normalize_reason
from .policy import PERM_BLOCK, RimAccessError, assert_can_manage, assert_no_foreign_authority, require_permission
from .retired import EMPLOYMENT_CONTACT, EMPLOYMENT_ENDED, is_staff_archived
from .search import STATUS_DELETED, account_status

_CTX = "accounts.rim.archive"


def _membership_model():
    from apps.organizations.models import Membership

    return Membership


def archive_trace(user, organization=None):
    """Arxivləmə anında deaktiv edilmiş üzvlüklər (``updated_at == profile.blocked_at``)."""
    Membership = _membership_model()
    profile = getattr(user, "profile", None)
    stamp = getattr(profile, "blocked_at", None)
    if stamp is None or not is_staff_archived(user):
        return Membership.objects.none()
    queryset = Membership.objects.filter(user=user, is_active=False, updated_at=stamp)
    if organization is not None:
        queryset = queryset.filter(organization=organization)
    return queryset


def is_student_account(user, organization) -> bool:
    """Tələbə hesabı: təşkilatda tələbə ailəsi rolu (aktiv və ya arxiv izi) VƏ YA akademik qeyd."""
    from django.apps import apps as django_apps

    from .search import STUDENT_ROLE_NAMES

    if organization is None:
        return False
    Membership = _membership_model()
    if Membership.objects.filter(user=user, organization=organization, role__name__in=STUDENT_ROLE_NAMES).exists():
        return True
    record_model = django_apps.get_model("registrar", "StudentAcademicRecord")
    return record_model.objects.filter(organization=organization, student=user).exists()


def _organization(actor, user):
    from .archive import restore_organization

    organization = restore_organization(actor, user)
    if organization is None:
        raise RimAccessError("no_organization_context", pgettext(_CTX, "Aktiv təşkilat konteksti yoxdur."), status=409)
    return organization


def _role_labels(memberships) -> list:
    from core.staff_position import visible_role_label

    rows = []
    for membership in memberships.select_related("role", "scope_unit").order_by("-role__level", "role__name"):
        label = visible_role_label(membership.role.name, membership.role.display_name) or membership.role.name
        unit = membership.scope_unit.name if membership.scope_unit_id else ""
        rows.append(f"{label} — {unit}" if unit else label)
    return rows


def card(actor, user, *, manageable: bool) -> dict | None:
    """Detal kartının «Arxivə göndər / Arxivdən çıxar» bloku; tələbə üçün ``None`` (məzun kartı var)."""
    organization = actor.organization or getattr(getattr(user, "profile", None), "organization", None)
    if organization is None or is_student_account(user, organization):
        return None
    status = account_status(user)
    if status == STATUS_DELETED:
        return None
    archived = is_staff_archived(user)
    Membership = _membership_model()
    if archived:
        roles = _role_labels(archive_trace(user, organization))
    else:
        roles = _role_labels(Membership.objects.filter(user=user, organization=organization, is_active=True))
    allowed = manageable and actor.has(PERM_BLOCK)
    note = ""
    if not actor.has(PERM_BLOCK):
        note = pgettext(_CTX, "Bunun üçün «Hesabı bloklamaq» (user.block) icazəsi lazımdır.")
    elif not manageable:
        note = pgettext(_CTX, "Bu hesab sizin idarə sahənizdə deyil.")
    blocked_at = getattr(getattr(user, "profile", None), "blocked_at", None)
    return {
        "archived": archived,
        "can_archive": bool(allowed and not archived),
        "can_unarchive": bool(allowed and archived),
        "disabled_reason": note,
        "roles": roles,
        "since": blocked_at.isoformat() if archived and blocked_at else "",
    }


@transaction.atomic
def archive(actor, user, *, reason="", request=None) -> dict:
    """Müəllimi / əməkdaşı arxivə göndərir: giriş bağlanır, təşkilatdakı rollar deaktiv olur (iz qalır)."""
    require_permission(actor, PERM_BLOCK)
    assert_can_manage(actor, user)
    assert_no_foreign_authority(actor, user)
    organization = _organization(actor, user)
    status = account_status(user)
    if status == STATUS_DELETED:
        raise RimAccessError("already_deleted", pgettext(_CTX, "Hesab silinib — əvvəlcə bərpa edin."), status=409)
    if is_staff_archived(user):
        raise RimAccessError("already_archived", pgettext(_CTX, "Hesab artıq arxivdədir."), status=409)
    if is_student_account(user, organization):
        raise RimAccessError(
            "target_is_student",
            pgettext(_CTX, "Tələbə arxivə «Məzun et» (və ya reyestrdəki xaric) əmri ilə keçir."),
            status=409,
        )
    text = normalize_reason(reason, required=False) or pgettext(_CTX, "İşdən ayrılıb / müqavilə bitib")

    profile = user.profile
    if user.is_active:
        try:
            block_account(
                user,
                request=request,
                actor=actor.user,
                reason=text,
                reason_code=EMPLOYMENT_ENDED,
                contact_code=EMPLOYMENT_CONTACT,
            )
        except AccountDeletionError as exc:
            if str(exc) == "last_org_admin":
                raise RimAccessError(
                    "last_org_admin",
                    pgettext(_CTX, "Bu hesab təşkilatın son aktiv administratorudur — əvvəlcə başqa admin təyin edin."),
                    status=409,
                ) from exc
            raise RimAccessError("archive_failed", pgettext(_CTX, "Arxivləmə alınmadı."), status=409) from exc
    else:
        # Artıq bloklanmış hesab: blok səbəbi «işdən ayrılıb»a çevrilir, damğa yenilənir (iz bu damğadır).
        profile.blocked_at = timezone.now()
        profile.blocked_by = actor.user if getattr(actor.user, "pk", None) else None
        profile.block_reason = text[:300]
        profile.block_reason_code = EMPLOYMENT_ENDED
        profile.block_contact_code = EMPLOYMENT_CONTACT
        profile.save(
            update_fields=[
                "blocked_at",
                "blocked_by",
                "block_reason",
                "block_reason_code",
                "block_contact_code",
                "updated_at",
            ]
        )

    Membership = _membership_model()
    active = Membership.objects.filter(user=user, organization=organization, is_active=True)
    membership_ids = [str(pk) for pk in active.values_list("pk", flat=True)]
    roles = _role_labels(active)
    # İz = blok damğası (soft-delete-in `deleted_at` izi ilə eyni naxış) — bərpa məhz bu sətirləri açır.
    Membership.objects.filter(pk__in=membership_ids).update(is_active=False, updated_at=profile.blocked_at)
    _invalidate(user)

    log_action(
        AuditAction.UPDATE,
        user=actor.user,
        organization=organization,
        obj=user,
        request=request,
        reason=f"RİM: arxivə göndərildi. Səbəb: {text}",
        old_values={"status": status, "active_memberships": membership_ids},
        new_values={"status": "archived", "active_memberships": []},
        changes={
            "action": "rim.staff_archived",
            "target_user_id": str(user.pk),
            "target_username": user.username,
            "membership_ids": membership_ids,
            "roles": roles,
            "reason_text": text,
        },
        resource_type="User",
        resource_id=str(user.pk),
        resource_repr=user.username,
    )
    return {"memberships_archived": len(membership_ids), "roles": roles}


@transaction.atomic
def unarchive(actor, user, *, reason="", request=None) -> dict:
    """Arxivdən çıxarır: giriş açılır və arxivləmədə deaktiv edilmiş rollar geri qayıdır."""
    require_permission(actor, PERM_BLOCK)
    assert_can_manage(actor, user)
    assert_no_foreign_authority(actor, user)
    organization = _organization(actor, user)
    if not is_staff_archived(user):
        raise RimAccessError("not_archived", pgettext(_CTX, "Hesab arxivdə deyil."), status=409)
    text = normalize_reason(reason, required=False)

    trace = archive_trace(user, organization)
    membership_ids = [str(pk) for pk in trace.values_list("pk", flat=True)]
    roles = _role_labels(trace)
    try:
        unblock_account(user, request=request, actor=actor.user, reason=text)
    except AccountDeletionError as exc:
        raise RimAccessError("unarchive_failed", pgettext(_CTX, "Arxivdən çıxarmaq alınmadı."), status=409) from exc
    restored = (
        _membership_model().objects.filter(pk__in=membership_ids).update(is_active=True, updated_at=timezone.now())
    )
    _invalidate(user)

    notices = []
    if not restored:
        notices.append(pgettext(_CTX, "Arxivdə saxlanmış rol izi tapılmadı — rolları «Rol təyinatı»nda təyin edin."))
    log_action(
        AuditAction.UPDATE,
        user=actor.user,
        organization=organization,
        obj=user,
        request=request,
        reason=f"RİM: arxivdən çıxarıldı. Səbəb: {text or '-'}",
        old_values={"status": "archived", "active_memberships": []},
        new_values={"status": "active", "active_memberships": membership_ids},
        changes={
            "action": "rim.staff_unarchived",
            "target_user_id": str(user.pk),
            "target_username": user.username,
            "membership_ids": membership_ids,
            "roles": roles,
            "reason_text": text,
        },
        resource_type="User",
        resource_id=str(user.pk),
        resource_repr=user.username,
    )
    return {"memberships_restored": restored, "roles": roles, "notices": notices}


def _invalidate(user) -> None:
    from apps.organizations.public import invalidate_permission_scope_cache

    invalidate_permission_scope_cache(user)


__all__ = ["archive", "archive_trace", "card", "is_student_account", "unarchive"]
