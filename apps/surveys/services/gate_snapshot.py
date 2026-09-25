"""Qapının SIFIR-SORĞULU bayrağı — ``Organization.settings["surveys_gate"]``.

Niyə keş deyil? ``request.organization`` ``OrganizationMiddleware`` tərəfindən
HƏR sorğuda üzvlüklə birlikdə (``select_related``) onsuz da yüklənir; açıq
kampaniyaların qısa xülasəsi onun ``settings`` JSON-una yazılanda qapı heç bir
əlavə sorğu və ya keş oxuması etmədən «açıq kampaniya varmı?» sualına cavab
verir — keş boş olanda da (test mühitinin ``DummyCache``-i, soyuq start).

Format::

    {"v": "<təsadüfi versiya>", "campaigns": [
        {"id": "<uuid>", "mandatory": true, "opens_on": "2026-09-25",
         "closes_on": "2026-10-25", "grace_until": "2026-09-28"}]}

``v`` hər sinxronda dəyişir — tələbə sessiyasındakı gözləyən-say keşi onunla
etibarsızlaşır (yeni jurnal bağlanması → yeni hədəflər). Yazı PostgreSQL-də
``jsonb_set`` ilə atomikdir (digər ``settings`` açarlarına toxunmur).

Mənbə-həqiqət ``SurveyCampaign`` cədvəlidir; xülasə hər kampaniya dəyişikliyində,
jurnal bağlananda, kampaniyalar bölməsi açılanda və əmrlə yenidən qurulur
(self-healing).
"""

from __future__ import annotations

import datetime
import json
import secrets

from django.apps import apps as django_apps
from django.db import connection

from ..constants import GATE_SNAPSHOT_KEY, CampaignStatus


def _iso(day):
    return day.isoformat() if day else None


def _parse(day_text):
    if not day_text:
        return None
    try:
        return datetime.date.fromisoformat(day_text)
    except (TypeError, ValueError):
        return None


def read_snapshot(organization) -> dict:
    """Sıfır sorğu: artıq yüklənmiş ``organization.settings``-dən oxunur."""
    raw = getattr(organization, "settings", None)
    raw = raw.get(GATE_SNAPSHOT_KEY) if isinstance(raw, dict) else None
    if not isinstance(raw, dict) or not isinstance(raw.get("campaigns"), list):
        return {"v": "", "campaigns": []}
    return raw


def active_entries(organization, day) -> list:
    """Bu gün AKTİV olan kampaniyaların xülasə sətirləri (tarixlər ``date``-ə çevrilir)."""
    entries = []
    for item in read_snapshot(organization)["campaigns"]:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        opens_on, closes_on = _parse(item.get("opens_on")), _parse(item.get("closes_on"))
        if (opens_on and day < opens_on) or (closes_on and day > closes_on):
            continue
        entries.append(
            {
                "id": str(item["id"]),
                "mandatory": bool(item.get("mandatory")),
                "opens_on": opens_on,
                "closes_on": closes_on,
                "grace_until": _parse(item.get("grace_until")),
            }
        )
    return entries


def snapshot_version(organization) -> str:
    return str(read_snapshot(organization).get("v") or "")


def build_snapshot(organization) -> dict:
    from ..models import SurveyCampaign

    rows = SurveyCampaign.objects.filter(organization=organization, status=CampaignStatus.OPEN).order_by(
        "opens_on", "created_at"
    )
    return {
        "v": secrets.token_hex(6),
        "campaigns": [
            {
                "id": str(row.pk),
                "mandatory": bool(row.mandatory),
                "opens_on": _iso(row.opens_on),
                "closes_on": _iso(row.closes_on),
                "grace_until": _iso(row.grace_until),
            }
            for row in rows
        ],
    }


def sync_gate_snapshot(organization) -> dict:
    """Xülasəni DB-dən yenidən qurur və təşkilat sətrinə yazır (versiya dəyişir)."""
    snapshot = build_snapshot(organization)
    Organization = django_apps.get_model("organizations", "Organization")
    if connection.vendor == "postgresql":
        table = connection.ops.quote_name(Organization._meta.db_table)
        with connection.cursor() as cursor:
            cursor.execute(
                f"UPDATE {table} SET settings = jsonb_set("  # noqa: S608 — cədvəl adı modeldən, dəyərlər parametrdir
                "CASE WHEN jsonb_typeof(settings) = 'object' THEN settings ELSE '{}'::jsonb END, "
                "%s::text[], %s::jsonb, true) WHERE id = %s",
                ["{" + GATE_SNAPSHOT_KEY + "}", json.dumps(snapshot), str(organization.pk)],
            )
    else:  # pragma: no cover — yalnız PostgreSQL olmayan lokal baza
        stored = Organization.objects.filter(pk=organization.pk).values_list("settings", flat=True).first()
        stored = dict(stored) if isinstance(stored, dict) else {}
        stored[GATE_SNAPSHOT_KEY] = snapshot
        Organization.objects.filter(pk=organization.pk).update(settings=stored)
    current = organization.settings if isinstance(organization.settings, dict) else {}
    organization.settings = {**current, GATE_SNAPSHOT_KEY: snapshot}
    return snapshot


def snapshot_is_stale(organization) -> bool:
    """Xülasə DB-dəki açıq kampaniyalarla (id + tarixlər + məcburilik) üst-üstə düşmürmü (1 sorğu).

    Başqa kod ``Organization.settings``-i köhnə nüsxədən BÜTÖV yazsa (məs. modul
    görünürlüyü paneli), xülasə geri qayıda bilər — bu yoxlama onu tutur.
    """
    stored = read_snapshot(organization)["campaigns"]
    return build_snapshot(organization)["campaigns"] != stored
