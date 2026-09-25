"""Tələbənin qapı vəziyyəti — gözləyən hədəf sayı (sessiyada keşli) və «Sonra».

Sorğu büdcəsi:

* açıq kampaniya yoxdursa və ya hesab tələbə deyilsə — SIFIR sorğu (bayraq
  ``Organization.settings``-dədir, üzvlüklər middleware-dən gəlir);
* açıq kampaniya + tələbə: sessiya keşi təzədirsə yenə SIFIR; köhnəlibsə
  (TTL, xülasə versiyası dəyişib, cavab göndərilib) kampaniya başına ~4 sorğu.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from core.roles import ProfileRole

from ..constants import (
    DEFER_SECONDS,
    NON_STAFF_ROLE_NAMES,
    SESSION_DEFER_KEY,
    SESSION_STATE_KEY,
    STATE_TTL_SECONDS,
    STUDENT_ROLE_NAMES,
)
from .gate_snapshot import active_entries, snapshot_version


@dataclass
class GateState:
    """Bir sorğu üçün hesablanmış vəziyyət (``request.survey_gate``)."""

    campaigns: list = field(default_factory=list)  # [{"id", "pending", "total", "mandatory", "grace_until"}]

    @property
    def pending(self) -> int:
        return sum(item["pending"] for item in self.campaigns)

    @property
    def total(self) -> int:
        return sum(item["total"] for item in self.campaigns)

    def blocking_campaign(self):
        """Kabineti bağlayan kampaniya: məcburi + gözləyən hədəfi olan ilk kampaniya."""
        return next((item for item in self.campaigns if item["mandatory"] and item["pending"]), None)


def is_student_account(memberships) -> bool:
    """Tələbə ailəsindən rol VAR və heç bir heyət rolu YOXDUR (sıfır sorğu)."""
    names = set()
    for membership in memberships or ():
        role = getattr(membership, "role", None)
        if role is None or not getattr(membership, "is_active", True):
            continue
        names.add(ProfileRole.normalize_membership_role_name(getattr(role, "name", "")))
    return bool(names & STUDENT_ROLE_NAMES) and not (names - NON_STAFF_ROLE_NAMES)


def _load_campaigns(organization, ids):
    from ..models import SurveyCampaign

    campaigns = {str(c.pk): c for c in SurveyCampaign.objects.filter(organization=organization, pk__in=ids)}
    return [campaigns[pk] for pk in ids if pk in campaigns]


def compute_state(request, organization, entries, *, force=False) -> GateState:
    """Sessiya keşi təzədirsə onu, əks halda DB-dən hesablanmış vəziyyəti qaytarır."""
    from .targets import pending_counts

    version = snapshot_version(organization)
    now = int(time.time())
    ids = [entry["id"] for entry in entries]
    cached = request.session.get(SESSION_STATE_KEY) if hasattr(request, "session") else None
    counts = None
    if (
        not force
        and isinstance(cached, dict)
        and cached.get("v") == version
        and cached.get("u") == request.user.pk
        and now - int(cached.get("at") or 0) < STATE_TTL_SECONDS
        and sorted(cached.get("c", {})) == sorted(ids)
    ):
        counts = cached["c"]
    if counts is None:
        counts = {}
        for campaign in _load_campaigns(organization, ids):
            pending, total = pending_counts(campaign, request.user)
            counts[str(campaign.pk)] = [pending, total]
        if hasattr(request, "session"):
            request.session[SESSION_STATE_KEY] = {"v": version, "u": request.user.pk, "at": now, "c": counts}
    state = GateState()
    for entry in entries:
        pending, total = counts.get(entry["id"], [0, 0])
        state.campaigns.append(
            {
                "id": entry["id"],
                "pending": int(pending),
                "total": int(total),
                "mandatory": entry["mandatory"],
                "grace_until": entry["grace_until"],
            }
        )
    return state


def store_counts(request, organization, counts) -> None:
    """Hesablanmış ``{campaign_id: [pending, total]}``-u sessiya keşinə yazır (siyahı/forma
    səhifəsi təzə say bilir — qapı onu yenidən hesablamasın)."""
    if not hasattr(request, "session"):
        return
    cached = request.session.get(SESSION_STATE_KEY)
    version = snapshot_version(organization)
    merged = {}
    if isinstance(cached, dict) and cached.get("v") == version and cached.get("u") == request.user.pk:
        merged = dict(cached.get("c") or {})
    merged.update(counts)
    ids = {entry["id"] for entry in active_entries(organization, _today())}
    merged = {key: value for key, value in merged.items() if key in ids}
    request.session[SESSION_STATE_KEY] = {"v": version, "u": request.user.pk, "at": int(time.time()), "c": merged}


def _today():
    from django.utils import timezone

    return timezone.localdate()


def invalidate_state(request) -> None:
    if hasattr(request, "session"):
        request.session.pop(SESSION_STATE_KEY, None)


def deferral_active(request, campaign_id, today) -> bool:
    """«Sonra doldur» bayrağı bu kampaniya üçün hələ qüvvədədirmi."""
    raw = request.session.get(SESSION_DEFER_KEY) if hasattr(request, "session") else None
    if not isinstance(raw, dict) or raw.get("c") != str(campaign_id):
        return False
    return int(raw.get("until") or 0) > int(time.time())


def set_deferral(request, campaign_id) -> None:
    request.session[SESSION_DEFER_KEY] = {"c": str(campaign_id), "until": int(time.time()) + DEFER_SECONDS}


def student_entries(request, today):
    """Tələbə + açıq kampaniya varsa aktiv xülasə sətirləri, əks halda ``[]`` (sıfır sorğu)."""
    user = getattr(request, "user", None)
    organization = getattr(request, "organization", None)
    if user is None or not getattr(user, "is_authenticated", False) or organization is None:
        return []
    if getattr(user, "is_superuser", False) or getattr(request, "is_view_as", False):
        return []
    entries = active_entries(organization, today)
    if not entries:
        return []
    if not is_student_account(getattr(request, "org_memberships", None)):
        return []
    return entries
