"""Popup (birdəfəlik + məcburi) + oxundu/təsdiq qəbzləri + sidebar sayğacı.

Popup qaydası: aktiv, dərc olunmuş, ``show_as_popup`` elan istifadəçiyə ünvanlanıbsa və
onun qəbzində ``popup_seen_at`` YOXDURSA növbəti tam səhifə açılışında göstərilir.
«Bağla» / «Ətraflı bax» ``popup_seen_at`` yazır — bir daha göstərilmir.

MƏCBURİ elan (``requires_ack``, 2026-10-07): ``acknowledged_at`` yazılanadək HƏR tam GET
səhifəsində (eyni istisnalarla) göstərilir — ``popup_seen_at`` onu gizlətmir. Modalda məcburi
elanlar birinci gəlir. Sessiya imzası məcburi id-ləri də daxil edir və yalnız «gözləyən YOXDUR»
olanda yazılır, təsdiq isə geri alınmır — ona görə imza təsdiqlənməmiş məcburi elanı gizlədə bilməz.
Elanın öz detal səhifəsində (``?section=announcements&elan=<id>``) həmin elan popup-a düşmür —
orada eyni təsdiq bloku banner kimi göstərilir.

Sorğu büdcəsi (adi səhifə açılışı):

1. Təşkilat xülasəsində (``Organization.settings`` — artıq yüklənib) istifadəçinin
   AİLƏSİNƏ uyğun aktiv popup elanı yoxdursa → SIFIR sorğu.
2. Varsa, sessiyada «bu namizəd dəsti üçün gözləyən yoxdur» işarəsi (dəst imzası) varsa
   → SIFIR sorğu (sessiya onsuz da yüklənir).
3. Əks halda: qəbzlər (1) + tələbənin akademik qeydi (daraltma varsa, 1) + modal üçün
   elan sətirləri (yalnız gözləyən varsa, 1). Gözləyən yoxdursa imza sessiyaya yazılır.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import F, Q, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from ..constants import (
    POPUP_EXEMPT_PREFIXES,
    POPUP_EXEMPT_SECTIONS,
    POPUP_MAX_ITEMS,
    POPUP_SESSION_KEY,
    PROFILE_SECTION,
    Status,
)
from ..models import Announcement, AnnouncementReceipt
from . import snapshot
from .audience import families_only, matches, viewer_for
from .queries import decorate


def _path_exempt(request) -> bool:
    path = request.path_info or ""
    if path.startswith(POPUP_EXEMPT_PREFIXES):
        return True
    return request.GET.get("section") in POPUP_EXEMPT_SECTIONS


def _eligible(request) -> bool:
    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if getattr(request, "organization", None) is None or getattr(request, "is_view_as", False):
        return False
    return request.method == "GET" and not _path_exempt(request)


def _signature(organization, candidates) -> str:
    """Namizəd dəstinin imzası — məcburi id-lər ayrıca daxildir (bayraq dəyişəndə imza da dəyişir)."""
    ids = sorted(item["id"] for item in candidates)
    mandatory = sorted(item["id"] for item in candidates if item.get("req"))
    raw = f"{organization.pk}:{snapshot.version(organization)}:{','.join(ids)}|req:{','.join(mandatory)}"
    return hashlib.sha1(raw.encode(), usedforsecurity=False).hexdigest()[:16]


def _viewing(request) -> str:
    """Kabinetdə açıq olan elan detalının id-si (``?section=announcements&elan=<id>``), yoxdursa ``""``."""
    if request.GET.get("section") != PROFILE_SECTION:
        return ""
    return str(request.GET.get("elan") or "").strip().lower()


def _candidates(request, now) -> list:
    """Ailəyə uyğun aktiv popup sətirləri (SIFIR sorğu). Açıq detalın öz məcburi elanı çıxarılır."""
    families = families_only(getattr(request, "org_memberships", None))
    if not families:
        return []
    viewing = _viewing(request)
    return [
        item
        for item in snapshot.active_items(request.organization, now)
        if item.get("pop")
        and set(item.get("f") or ()) & families
        and not (viewing and item.get("req") and item["id"] == viewing)
    ]


def _closed_ids(organization, user, candidates) -> set:
    """Artıq göstərilməyəcək namizədlər (BİR sorğu): adi popup — görülüb; məcburi — TƏSDİQ edilib."""
    mandatory = {item["id"] for item in candidates if item.get("req")}
    rows = (
        AnnouncementReceipt.objects.filter(
            organization=organization,
            user=user,
            announcement_id__in=[item["id"] for item in candidates],
        )
        .filter(Q(popup_seen_at__isnull=False) | Q(acknowledged_at__isnull=False))
        .values_list("announcement_id", "popup_seen_at", "acknowledged_at")
    )
    closed = set()
    for announcement_id, seen_at, acknowledged_at in rows:
        key = str(announcement_id)
        if acknowledged_at is not None or (seen_at is not None and key not in mandatory):
            closed.add(key)
    return closed


def pending_popups(request) -> list:
    """Modalda göstəriləcək elanlar (məcburi → prioritet → yeni birinci); yoxdursa ``[]``."""
    if not _eligible(request):
        return []
    now = timezone.now()
    candidates = _candidates(request, now)
    if not candidates:
        return []
    organization, user = request.organization, request.user
    signature = _signature(organization, candidates)
    session = getattr(request, "session", None)
    if session is not None and session.get(POPUP_SESSION_KEY) == signature:
        return []
    closed = _closed_ids(organization, user, candidates)
    remaining = [item for item in candidates if item["id"] not in closed]
    if remaining:
        viewer = viewer_for(user, organization, getattr(request, "org_memberships", None))
        remaining = [item for item in remaining if matches(item.get("f"), item.get("u"), viewer)]
    if not remaining:
        if session is not None:
            session[POPUP_SESSION_KEY] = signature
        return []
    order = {item["id"]: index for index, item in enumerate(remaining)}
    rows = list(
        Announcement.objects.filter(
            organization=organization, pk__in=list(order), status=Status.PUBLISHED, is_deleted=False
        ).order_by("-requires_ack", "-priority", "-is_pinned", "-publish_at")[:POPUP_MAX_ITEMS]
    )
    for row in rows:
        decorate(row, now)
    return rows


def _touch(organization, user, announcement_ids, field) -> int:
    """Qəbzi yaradır / sahəni (boşdursa) indiki vaxtla doldurur. Yalnız görünən elanlar üçün çağırılır."""
    now = timezone.now()
    updated = 0
    for announcement_id in announcement_ids:
        receipt, created = _get_or_create(organization, user, announcement_id, {field: now})
        if created:
            updated += 1
        elif getattr(receipt, field) is None:
            updated += AnnouncementReceipt.objects.filter(pk=receipt.pk, **{f"{field}__isnull": True}).update(
                **{field: now, "updated_at": now}
            )
    return updated


def _get_or_create(organization, user, announcement_id, defaults):
    try:
        with transaction.atomic():
            return AnnouncementReceipt.objects.get_or_create(
                organization=organization, user=user, announcement_id=announcement_id, defaults=defaults
            )
    except IntegrityError:  # paralel klik — sətir artıq var
        return AnnouncementReceipt.objects.get(user=user, announcement_id=announcement_id), False


def mark_popup_seen(request, announcement_ids) -> int:
    """Popup bağlandı / «Ətraflı bax» — yalnız istifadəçiyə HƏQİQƏTƏN ünvanlanmış elanlar üçün."""
    from .queries import published_for

    organization, user = request.organization, request.user
    viewer = viewer_for(user, organization, getattr(request, "org_memberships", None))
    visible = list(
        published_for(organization, viewer)
        .filter(pk__in=list(announcement_ids)[: POPUP_MAX_ITEMS * 2])
        .values_list("pk", flat=True)
    )
    count = _touch(organization, user, visible, "popup_seen_at")
    if getattr(request, "session", None) is not None:
        request.session.pop(POPUP_SESSION_KEY, None)
    return count


def _forget_badge(request) -> None:
    cache.delete(_badge_key(request.organization, request.user))
    try:
        del request.user._announcements_badge
    except AttributeError:
        pass


def mark_read(request, announcement) -> bool:
    """``True`` — elan indi ilk dəfə oxundu (sayğac bir azalır)."""
    newly = bool(_touch(request.organization, request.user, [announcement.pk], "read_at"))
    _forget_badge(request)
    return newly


@dataclass(frozen=True)
class AckResult:
    """``mandatory=False`` — elan görünür, amma təsdiq tələb etmir (heç nə yazılmır)."""

    mandatory: bool = True
    newly: bool = False
    newly_read: bool = False
    acknowledged_at: object = None


def acknowledge(request, announcement_id) -> AckResult | None:
    """«Elanı oxudum və tanış oldum» — ``None``: elan yoxdur / istifadəçiyə ünvanlanmayıb (404).

    Yalnız ``published_for`` süzgəcindən keçən (ünvanlanmış, dərc olunmuş, silinməmiş, başqa
    təşkilatın olmayan) məcburi elan üçün. ``acknowledged_at`` + boşdursa ``popup_seen_at`` /
    ``read_at`` yazılır. İdempotent: şərtli UPDATE (``acknowledged_at IS NULL``) və
    ``_get_or_create`` paralel klikdə ikinci yazını no-op edir; ilk təsdiq vaxtı dəyişmir.
    """
    from .queries import published_for

    organization, user = request.organization, request.user
    viewer = viewer_for(user, organization, getattr(request, "org_memberships", None))
    row = published_for(organization, viewer).filter(pk=announcement_id).values("pk", "requires_ack").first()
    if row is None:
        return None
    if not row["requires_ack"]:
        return AckResult(mandatory=False)
    now = timezone.now()
    receipt, created = _get_or_create(
        organization, user, row["pk"], {"acknowledged_at": now, "popup_seen_at": now, "read_at": now}
    )
    newly, newly_read, acknowledged_at = created, created, receipt.acknowledged_at
    if not created and receipt.acknowledged_at is None:
        newly = bool(
            AnnouncementReceipt.objects.filter(pk=receipt.pk, acknowledged_at__isnull=True).update(
                acknowledged_at=now,
                popup_seen_at=Coalesce(F("popup_seen_at"), Value(now)),
                read_at=Coalesce(F("read_at"), Value(now)),
                updated_at=now,
            )
        )
        newly_read = newly and receipt.read_at is None
        acknowledged_at = (
            now
            if newly
            else AnnouncementReceipt.objects.filter(pk=receipt.pk).values_list("acknowledged_at", flat=True).first()
        )
    _forget_badge(request)
    if getattr(request, "session", None) is not None:
        request.session.pop(POPUP_SESSION_KEY, None)
    return AckResult(mandatory=True, newly=newly, newly_read=newly_read, acknowledged_at=acknowledged_at)


#: Sayğac keşi (Redis): versiya xülasədən — dərc/redaktə hamının açarını köhnəldir; oxu öz açarını silir.
BADGE_TTL = 120


def _badge_key(organization, user) -> str:
    return f"ann:badge:{organization.pk}:{user.pk}:{snapshot.version(organization)}"


def badge_count(user, organization, memberships=None) -> int:
    """Oxunmamış aktiv elan sayı — ailəyə uyğun aktiv elan yoxdursa SIFIR sorğu; request-ömürlü memo."""
    if user is None or organization is None or not getattr(user, "is_authenticated", False):
        return 0
    memo = getattr(user, "_announcements_badge", None)
    if isinstance(memo, tuple) and memo[0] == organization.pk:
        return memo[1]
    count = 0
    families = families_only(memberships) if memberships is not None else None
    items = snapshot.active_items(organization)
    if items and (families is None or any(set(item.get("f") or ()) & families for item in items)):
        key = _badge_key(organization, user)
        cached = cache.get(key)
        if isinstance(cached, int):
            count = cached
        else:
            from .queries import unread_count

            count = unread_count(organization, user, viewer_for(user, organization, memberships))
            cache.set(key, count, BADGE_TTL)
    try:
        user._announcements_badge = (organization.pk, count)
    except Exception:  # noqa: BLE001 — dəyişməz istifadəçi obyekti (nadir)
        pass
    return count


__all__ = ["AckResult", "acknowledge", "badge_count", "mark_popup_seen", "mark_read", "pending_popups"]
