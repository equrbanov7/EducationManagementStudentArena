"""«Kənardan jurnal girişi» servisi — icazə ver / geri al / yoxla (sahib 2026-11-20).

* **Yoxlama** (:func:`has_active_grant`) şəbəkə qapısının isti yoludur: kənar zonadan HƏR jurnal sorğusunda
  (Django middleware) və nginx ``auth_request``-də çağırılır. Nəticə paylaşılan keşdə ``CACHE_TTL`` saniyə saxlanılır
  (hesab başına bir açar); icazə verilən / geri alınan anda açar silinir, yəni dəyişiklik bütün serverlərdə dərhal
  qüvvəyə minir. Keş əlçatmazdırsa indeksli ``EXISTS`` sorğusu gedir (qismən unikal indeks ``user_id``-dədir).
* **Yazı** (:func:`grant`, :func:`revoke`) yalnız RİM rəhbəri / superadmin üçündür — qapı çağıranda
  (``runtime_settings_admin.can_manage``, «Sistem tənzimləmələri» ilə EYNİ); hər əməl audit jurnalına düşür.
* **Namizədlər** — təşkilatda aktiv inzibati / müəllim üzvlüyü olan aktiv hesablar (tələbə rolları siyahıya düşmür).

Mühit siyahısı (``JOURNAL_REMOTE_USER_IDS``) bu servisdən asılı deyil və olduğu kimi işləyir.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef
from django.utils import timezone

from core.audit import log_action
from core.constants import AuditAction

logger = logging.getLogger(__name__)

CACHE_TTL = 30
CACHE_PREFIX = "accounts:remote_journal_access:v1:"
AUDIT_RESOURCE = "accounts.remote_journal_access"
NOTE_MAX = 255


class RemoteAccessError(Exception):
    """Gözlənilən rədd: ``code`` — ``not_found`` | ``not_eligible`` | ``already`` | ``not_active``."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _cache_key(user_id) -> str:
    return f"{CACHE_PREFIX}{user_id}"


def invalidate(user_id) -> None:
    try:
        cache.delete(_cache_key(user_id))
    except Exception:  # noqa: BLE001 — keş xətası yazını sındırmasın (TTL özü təmizləyir)
        logger.warning("remote_journal_access: keş açarı silinmədi (user=%s)", user_id)


def has_active_grant(user_id) -> bool:
    """Hesabın qüvvədə olan icazəsi varmı (keşli, fail-closed)."""
    if not user_id:
        return False
    key = _cache_key(user_id)
    try:
        cached = cache.get(key)
    except Exception:  # noqa: BLE001
        cached = None
    if cached is not None:
        return cached == 1
    from apps.accounts.models import RemoteJournalAccess

    try:
        active = RemoteJournalAccess.objects.filter(user_id=user_id, revoked_at__isnull=True).exists()
    except Exception:  # noqa: BLE001 — baza xətası istisnanı AÇMASIN
        logger.exception("remote_journal_access: yoxlama alınmadı (user=%s)", user_id)
        return False
    try:
        cache.set(key, 1 if active else 0, CACHE_TTL)
    except Exception:  # noqa: BLE001
        pass
    return active


def env_user_ids() -> list[str]:
    """Server tənzimləməsindəki (mühit) hesablar — kabinetdən dəyişmir, yalnız göstərilir."""
    return [str(value) for value in getattr(settings, "JOURNAL_REMOTE_USER_IDS", ()) if str(value).isdigit()]


# ── Namizədlər və göstərim ──────────────────────────────────────────────────


def _staff_memberships(organization):
    from apps.accounts.network_zone import STUDENT_ROLE_NAMES
    from apps.organizations.models import Membership

    queryset = Membership.objects.filter(is_active=True, user__is_active=True).exclude(
        role__name__in=STUDENT_ROLE_NAMES
    )
    if organization is not None:
        queryset = queryset.filter(organization=organization)
    return queryset


def display_name(user) -> str:
    profile = getattr(user, "profile", None)
    name = getattr(profile, "full_name_with_patronymic", "") if profile is not None else ""
    return name or user.get_full_name() or user.username


def role_labels(organization, user_ids) -> dict:
    """``user_id`` → «Rol · Bölmə» (əsas üzvlük əvvəl, sonra ən yüksək rol). Bir sorğu."""
    labels: dict = {}
    if not user_ids:
        return labels
    rows = (
        _staff_memberships(organization)
        .filter(user_id__in=list(user_ids))
        .order_by("user_id", "-is_primary", "-role__level")
        .values_list("user_id", "role__display_name", "scope_unit__name")
    )
    for user_id, role_name, unit_name in rows:
        if user_id not in labels:
            labels[user_id] = " · ".join(part for part in (role_name, unit_name) if part)
    return labels


def candidates(organization, query: str, *, offset: int, limit: int, granted_hint: str = "") -> tuple[list[dict], bool]:
    """Axtarışlı seçici üçün: aktiv inzibati / müəllim hesabları (dözümlü ad axtarışı)."""
    from apps.accounts.models import RemoteJournalAccess
    from apps.accounts.services.person_search import person_q

    User = get_user_model()
    users = User.objects.filter(is_active=True).filter(
        Exists(_staff_memberships(organization).filter(user_id=OuterRef("pk")))
    )
    condition = person_q(query or "", ("first_name", "last_name", "username", "profile__patronymic"))
    if condition is not None:
        users = users.filter(condition)
    page = list(users.select_related("profile").order_by("last_name", "first_name", "pk")[offset : offset + limit + 1])
    has_more = len(page) > limit
    page = page[:limit]
    ids = [user.pk for user in page]
    labels = role_labels(organization, ids)
    granted = set(
        RemoteJournalAccess.objects.filter(user_id__in=ids, revoked_at__isnull=True).values_list("user_id", flat=True)
    )
    granted |= {int(value) for value in env_user_ids() if int(value) in ids}
    rows = []
    for user in page:
        name = display_name(user)
        row = {"id": str(user.pk), "text": f"{name} ({user.username})", "label": name, "meta": labels.get(user.pk, "")}
        if user.pk in granted:
            row.update(disabled=True, hint=granted_hint)
        rows.append(row)
    return rows, has_more


def active_grants():
    from apps.accounts.models import RemoteJournalAccess

    return (
        RemoteJournalAccess.objects.filter(revoked_at__isnull=True)
        .select_related("user", "user__profile", "granted_by")
        .order_by("-granted_at")
    )


# ── Yazı ────────────────────────────────────────────────────────────────────


def _audit(action, *, actor, request, organization, grant, reason: str, values: dict) -> None:
    log_action(
        action,
        user=actor,
        organization=organization,
        request=request,
        resource_type=AUDIT_RESOURCE,
        resource_id=str(grant.pk),
        resource_repr=grant.user.username,
        reason=reason,
        new_values=values,
    )


def _after_commit(user_id) -> None:
    invalidate(user_id)
    transaction.on_commit(lambda: invalidate(user_id))


def grant(*, actor, user_id, note: str = "", request=None, organization=None):
    """Hesaba icazə verir; namizəd qaydası serverdə YENİDƏN yoxlanılır."""
    from apps.accounts.models import RemoteJournalAccess

    User = get_user_model()
    try:
        target = User.objects.get(pk=int(user_id), is_active=True)
    except (TypeError, ValueError, User.DoesNotExist):
        raise RemoteAccessError("not_found") from None
    if not _staff_memberships(organization).filter(user_id=target.pk).exists():
        raise RemoteAccessError("not_eligible")
    if str(target.pk) in env_user_ids():
        raise RemoteAccessError("already")
    note = str(note or "").strip()[:NOTE_MAX]
    try:
        with transaction.atomic():
            record = RemoteJournalAccess.objects.create(user=target, granted_by=actor, note=note)
            _audit(
                AuditAction.CREATE,
                actor=actor,
                request=request,
                organization=organization,
                grant=record,
                reason="remote journal access granted",
                values={"user_id": target.pk, "note": note},
            )
    except IntegrityError:
        raise RemoteAccessError("already") from None
    _after_commit(target.pk)
    return record


def revoke(*, actor, grant_id, request=None, organization=None):
    """Qüvvədəki icazəni geri alır (sətir tarixçə üçün qalır)."""
    from apps.accounts.models import RemoteJournalAccess

    with transaction.atomic():
        try:
            record = (
                RemoteJournalAccess.objects.select_for_update()
                .select_related("user")
                .get(pk=int(grant_id), revoked_at__isnull=True)
            )
        except (TypeError, ValueError, RemoteJournalAccess.DoesNotExist):
            raise RemoteAccessError("not_active") from None
        record.revoked_at = timezone.now()
        record.revoked_by = actor
        record.save(update_fields=["revoked_at", "revoked_by"])
        _audit(
            AuditAction.UPDATE,
            actor=actor,
            request=request,
            organization=organization,
            grant=record,
            reason="remote journal access revoked",
            values={"user_id": record.user_id, "revoked": True},
        )
    _after_commit(record.user_id)
    return record


__all__ = [
    "AUDIT_RESOURCE",
    "CACHE_TTL",
    "RemoteAccessError",
    "active_grants",
    "candidates",
    "display_name",
    "env_user_ids",
    "grant",
    "has_active_grant",
    "invalidate",
    "revoke",
    "role_labels",
]
