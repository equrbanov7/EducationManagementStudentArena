"""Birdəfəlik popup + oxundu qəbzləri + sidebar sayğacı.

Popup qaydası: aktiv, dərc olunmuş, ``show_as_popup`` elan istifadəçiyə ünvanlanıbsa və
onun qəbzində ``popup_seen_at`` YOXDURSA növbəti tam səhifə açılışında göstərilir.
«Bağla» / «Ətraflı bax» ``popup_seen_at`` yazır — bir daha göstərilmir.

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

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.utils import timezone

from ..constants import POPUP_EXEMPT_PREFIXES, POPUP_EXEMPT_SECTIONS, POPUP_MAX_ITEMS, POPUP_SESSION_KEY, Status
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


def _signature(organization, ids) -> str:
    raw = f"{organization.pk}:{snapshot.version(organization)}:{','.join(sorted(ids))}"
    return hashlib.sha1(raw.encode(), usedforsecurity=False).hexdigest()[:16]


def _candidates(request, now) -> list:
    """Ailəyə uyğun aktiv popup sətirləri (SIFIR sorğu)."""
    families = families_only(getattr(request, "org_memberships", None))
    if not families:
        return []
    return [
        item
        for item in snapshot.active_items(request.organization, now)
        if item.get("pop") and set(item.get("f") or ()) & families
    ]


def pending_popups(request) -> list:
    """Modalda göstəriləcək elanlar (prioritet → yeni birinci); yoxdursa ``[]``."""
    if not _eligible(request):
        return []
    now = timezone.now()
    candidates = _candidates(request, now)
    if not candidates:
        return []
    organization, user = request.organization, request.user
    signature = _signature(organization, [item["id"] for item in candidates])
    session = getattr(request, "session", None)
    if session is not None and session.get(POPUP_SESSION_KEY) == signature:
        return []
    seen = set(
        str(pk)
        for pk in AnnouncementReceipt.objects.filter(
            organization=organization,
            user=user,
            announcement_id__in=[item["id"] for item in candidates],
            popup_seen_at__isnull=False,
        ).values_list("announcement_id", flat=True)
    )
    remaining = [item for item in candidates if item["id"] not in seen]
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
        ).order_by("-priority", "-is_pinned", "-publish_at")[:POPUP_MAX_ITEMS]
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


def mark_read(request, announcement) -> bool:
    """``True`` — elan indi ilk dəfə oxundu (sayğac bir azalır)."""
    newly = bool(_touch(request.organization, request.user, [announcement.pk], "read_at"))
    cache.delete(_badge_key(request.organization, request.user))
    try:
        del request.user._announcements_badge
    except AttributeError:
        pass
    return newly


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


__all__ = ["badge_count", "mark_popup_seen", "mark_read", "pending_popups"]
