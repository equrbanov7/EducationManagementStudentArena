"""Qrupa ÜNVANLANMIŞ elanlar — kabinetin «Starosta» bölməsi üçün (2026-10-13 (gecə)).

Starosta qrupa aid elanları bir yerdə görməlidir: tələbə ailəsinə ünvanlanmış VƏ struktur daraltması
(``audience_units``) qrupun özünü və ya əcdadını (ixtisas / kafedra / fakültə) əhatə edən elanlar.
Təşkilat-geniş elanlar (``audience_units=[]``) buraya DÜŞMÜR — onlar hər kəsin «Elanlar» bölməsindədir;
bu siyahının dəyəri «qrupumu birbaşa maraqlandıran» elanlardır.

Auditoriya qaydası ``audience.visible_q`` ilə EYNİDİR (``Viewer`` qrupun path-ından qurulur), yəni baxan
tələbənin özü də bu elanları görür — yeni görünürlük AÇILMIR. TƏK sorğu. Heç nə yazmır.
"""

from __future__ import annotations

from django.utils import timezone

from ..constants import Audience
from .audience import Viewer
from .queries import _active_q, published_for

DEFAULT_LIMIT = 5


def _group_ancestors(group) -> frozenset:
    segments = [segment for segment in (getattr(group, "path", "") or "").strip("/").split("/") if segment]
    return frozenset(segments or [str(group.pk)])


def group_announcements(organization, group, *, limit=DEFAULT_LIMIT, now=None) -> list:
    """``[{"id", "title", "summary", "publish_at", "deadline_at", "is_pinned"}]`` — yeni → köhnə."""
    if organization is None or group is None:
        return []
    now = now or timezone.now()
    viewer = Viewer(families=frozenset({Audience.STUDENTS.value}), ancestors=_group_ancestors(group))
    rows = (
        published_for(organization, viewer, now=now)
        .filter(_active_q(now))
        .exclude(audience_units=[])
        .order_by("-is_pinned", "-publish_at", "-created_at")
        .values("id", "title", "summary", "publish_at", "deadline_at", "is_pinned")[: max(1, int(limit))]
    )
    return list(rows)


__all__ = ["DEFAULT_LIMIT", "group_announcements"]
