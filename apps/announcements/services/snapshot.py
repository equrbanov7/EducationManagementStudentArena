"""SIFIR-SORĞULU xülasə — ``Organization.settings["announcements_snapshot"]``.

``apps/surveys/services/gate_snapshot.py`` ilə EYNİ fikir: ``request.organization``
``OrganizationMiddleware`` tərəfindən HƏR sorğuda üzvlüklə birlikdə onsuz da yüklənir;
dərc olunmuş, müddəti bitməmiş elanların qısa xülasəsi onun ``settings`` JSON-una yazılanda
popup və sidebar sayğacı «mənə aid aktiv elan varmı?» sualına HEÇ BİR əlavə sorğu və ya keş
oxuması etmədən cavab verir (test mühitinin ``DummyCache``-i, soyuq start da daxil).

Format::

    {"v": "<təsadüfi versiya>", "items": [
        {"id": "<uuid>", "f": ["students"], "u": ["<unit-id>"], "p": 1, "pop": true,
         "from": "2026-10-06T08:00:00+00:00", "to": "2026-10-20T20:00:00+00:00"}]}

``v`` hər sinxronda dəyişir — sessiyadakı «popup yoxdur» işarəsi onunla etibarsızlaşır.
Vaxt pəncərəsi oxunanda Python-da süzülür, ona görə planlaşdırılmış elan öz vaxtında
cron-suz görünür. Mənbə-həqiqət ``Announcement`` cədvəlidir; xülasə hər idarə
mutasiyasında və idarə səhifəsi açılanda (self-healing) yenidən qurulur.
"""

from __future__ import annotations

import datetime
import json
import secrets

from django.apps import apps as django_apps
from django.db import connection
from django.db.models import Q
from django.utils import timezone

from ..constants import SNAPSHOT_KEY, SNAPSHOT_LIMIT, Status


def _parse(value):
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def read_snapshot(organization) -> dict:
    raw = getattr(organization, "settings", None)
    raw = raw.get(SNAPSHOT_KEY) if isinstance(raw, dict) else None
    if not isinstance(raw, dict) or not isinstance(raw.get("items"), list):
        return {"v": "", "items": []}
    return raw


def active_items(organization, now=None) -> list:
    """Bu an AKTİV elanların xülasə sətirləri (pəncərə süzülüb; prioritet → yeni birinci)."""
    now = now or timezone.now()
    snapshot = read_snapshot(organization)
    items = []
    for item in snapshot["items"]:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        start, end = _parse(item.get("from")), _parse(item.get("to"))
        if (start and start > now) or (end and end <= now):
            continue
        items.append(item)
    return items


def version(organization) -> str:
    return str(read_snapshot(organization).get("v") or "")


def build_snapshot(organization) -> dict:
    from ..models import Announcement

    now = timezone.now()
    rows = (
        Announcement.objects.filter(organization=organization, status=Status.PUBLISHED)
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
        .order_by("-priority", "-publish_at")
        .values("pk", "audience_families", "audience_units", "priority", "show_as_popup", "publish_at", "expires_at")[
            :SNAPSHOT_LIMIT
        ]
    )
    return {
        "v": secrets.token_hex(6),
        "items": [
            {
                "id": str(row["pk"]),
                "f": list(row["audience_families"] or []),
                "u": [str(unit) for unit in row["audience_units"] or []],
                "p": int(row["priority"] or 0),
                "pop": bool(row["show_as_popup"]),
                "from": row["publish_at"].isoformat() if row["publish_at"] else None,
                "to": row["expires_at"].isoformat() if row["expires_at"] else None,
            }
            for row in rows
        ],
    }


def sync_snapshot(organization) -> dict:
    """Xülasəni DB-dən yenidən qurur və təşkilat sətrinə ATOMİK yazır (digər açarlara toxunmur)."""
    snapshot = build_snapshot(organization)
    Organization = django_apps.get_model("organizations", "Organization")
    if connection.vendor == "postgresql":
        table = connection.ops.quote_name(Organization._meta.db_table)
        with connection.cursor() as cursor:
            cursor.execute(
                f"UPDATE {table} SET settings = jsonb_set("  # noqa: S608 — cədvəl adı modeldən, dəyərlər parametrdir
                "CASE WHEN jsonb_typeof(settings) = 'object' THEN settings ELSE '{}'::jsonb END, "
                "%s::text[], %s::jsonb, true) WHERE id = %s",
                ["{" + SNAPSHOT_KEY + "}", json.dumps(snapshot), str(organization.pk)],
            )
    else:  # pragma: no cover — yalnız PostgreSQL olmayan lokal baza
        stored = Organization.objects.filter(pk=organization.pk).values_list("settings", flat=True).first()
        stored = dict(stored) if isinstance(stored, dict) else {}
        stored[SNAPSHOT_KEY] = snapshot
        Organization.objects.filter(pk=organization.pk).update(settings=stored)
    current = organization.settings if isinstance(organization.settings, dict) else {}
    organization.settings = {**current, SNAPSHOT_KEY: snapshot}
    return snapshot


def snapshot_is_stale(organization) -> bool:
    """Xülasə DB ilə üst-üstə düşmürmü (versiyadan başqa) — idarə səhifəsinin self-healing yoxlaması."""
    stored = read_snapshot(organization)["items"]
    fresh = build_snapshot(organization)["items"]
    return stored != fresh


__all__ = ["active_items", "build_snapshot", "read_snapshot", "snapshot_is_stale", "sync_snapshot", "version"]
