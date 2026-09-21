"""Audit jurnalı — sətir, fərq (əvvəl → sonra) və detal serializasiyası.

``apps/audit/views.py``-dan ayrılıb (modul-ölçü qapısı, 2026-09-21); ``views.py``
``build_diff`` / ``serialize_entry`` və köməkçiləri yenidən ixrac edir.
"""

from __future__ import annotations

from urllib.parse import urlencode

from django.urls import reverse
from django.utils import timezone

from core.ui import status_catalog

from .views_filters import PREFIX, RANGE_ALL, REASONED_ACTIONS, STATUS_FAMILY

# ─── Sətir / detal serializasiyası ──────────────────────────────────────────


def _initials(name: str) -> str:
    parts = [part for part in (name or "").split() if part]
    if not parts:
        return "—"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _display_name(user) -> str:
    return (user.get_full_name() or "").strip() or user.username


def _humanize_type(value: str) -> str:
    return value.replace("_", " ").replace(".", " › ").strip().capitalize() if value else ""


def action_label(key: str) -> str:
    return str(status_catalog.label(STATUS_FAMILY, key))


def _action_tone(key: str) -> str:
    status = status_catalog.get(STATUS_FAMILY, key)
    return status.tone if status is not None else "neutral"


def _resource_bits(log) -> tuple[str, str, str]:
    """``(tip etiketi, identifikator, göstəriş)`` — GenericFK-ya TOXUNMADAN."""
    type_key = log.resource_type or (log.content_type.model if log.content_type_id else "")
    identifier = log.resource_id or log.object_id or ""
    repr_text = log.resource_repr or ""
    if not repr_text and type_key and identifier:
        repr_text = f"{_humanize_type(type_key)} #{identifier}"
    return _humanize_type(type_key), identifier, repr_text


def _row(log, *, profile_url_name="accounts:public_profile") -> dict:
    user = log.user if log.user_id else None
    name = _display_name(user) if user is not None else ""
    type_label, identifier, repr_text = _resource_bits(log)
    return {
        "id": str(log.id),
        "created_at": log.created_at,
        "actor_name": name,
        "actor_username": user.username if user is not None else "",
        "actor_initials": _initials(name) if name else "",
        "actor_url": reverse(profile_url_name, kwargs={"username": user.username}) if user is not None else "",
        "action": log.action,
        "action_label": action_label(log.action),
        "resource_type": type_label,
        "resource_type_key": log.resource_type or "",
        "resource_id": identifier,
        # `resource_label` YALNIZ həqiqi `resource_repr`-dir; sintez olunmuş
        # «Tip #id» forması `resource_display`-dədir (CSV/detal) — xana
        # tip+id-ni ayrıca göstərdiyi üçün təkrar olmasın.
        "resource_label": log.resource_repr or "",
        "resource_display": repr_text,
        "reason": log.reason or "",
        "reason_missing": log.action in REASONED_ACTIONS and not (log.reason or "").strip(),
        "ip": log.ip_address or "",
        "org_name": log.organization.name if log.organization_id else "",
        "has_changes": bool(log.changes or log.old_values or log.new_values),
        "detail_url": reverse("audit:detail", kwargs={"pk": log.id}),
    }


def _diff_state(before, after, *, in_old: bool, in_new: bool) -> str:
    if not in_old and in_new:
        return "added"
    if in_old and not in_new:
        return "removed"
    if before is None and after is not None:
        return "added"
    if before is not None and after is None:
        return "removed"
    return "same" if before == after else "changed"


def build_diff(old_values, new_values, changes) -> list[dict]:
    """Oxunaqlı əvvəl → sonra siyahısı.

    Prioritet `changes`-dədir (`{sahə: {"old": …, "new": …}}` konvensiyası;
    `[old, new]` cütü və düz dəyər də qəbul olunur). O yoxdursa, `old_values` və
    `new_values` açar-açar tutuşdurulur; dəyişməyən sahələr `same` kimi qalır
    (UI onları yığılmış göstərir).
    """
    old = old_values if isinstance(old_values, dict) else {}
    new = new_values if isinstance(new_values, dict) else {}
    rows: list[dict] = []
    if isinstance(changes, dict) and changes:
        for key, value in changes.items():
            key = str(key)
            if isinstance(value, dict) and value and set(value) <= {"old", "new"}:
                before, after = value.get("old"), value.get("new")
                in_old, in_new = "old" in value, "new" in value
            elif isinstance(value, (list, tuple)) and len(value) == 2:
                before, after = value[0], value[1]
                in_old, in_new = True, True
            else:
                before, after = old.get(key), value
                in_old, in_new = key in old, True
            rows.append(
                {
                    "key": key,
                    "old": before,
                    "new": after,
                    "state": _diff_state(before, after, in_old=in_old, in_new=in_new),
                }
            )
        return rows
    for key in sorted(set(old) | set(new), key=str):
        before, after = old.get(key), new.get(key)
        rows.append(
            {
                "key": str(key),
                "old": before,
                "new": after,
                "state": _diff_state(before, after, in_old=key in old, in_new=key in new),
            }
        )
    return rows


def serialize_entry(log, *, list_url: str) -> dict:
    """Çekmecə üçün tam qeyd (JSON)."""
    row = _row(log)
    created_local = timezone.localtime(log.created_at)
    type_label, identifier, repr_text = _resource_bits(log)
    diff = build_diff(log.old_values, log.new_values, log.changes)
    filter_links = {}
    if log.user_id:
        filter_links["actor"] = (
            f"{list_url}?{urlencode({'section': 'audit-log', PREFIX + 'actor': log.user_id, PREFIX + 'range': RANGE_ALL})}"
        )
    if log.request_id:
        filter_links["request"] = (
            f"{list_url}?{urlencode({'section': 'audit-log', PREFIX + 'q': str(log.request_id), PREFIX + 'range': RANGE_ALL})}"
        )
    return {
        "id": row["id"],
        "created_at": created_local.isoformat(),
        "created_display": created_local.strftime("%d.%m.%Y %H:%M:%S"),
        "actor": (
            {
                "name": row["actor_name"],
                "username": row["actor_username"],
                "initials": row["actor_initials"],
                "url": row["actor_url"],
            }
            if log.user_id
            else None
        ),
        "organization": row["org_name"],
        "action": log.action,
        "action_label": row["action_label"],
        "action_tone": _action_tone(log.action),
        "resource": {
            "type": type_label,
            "type_key": log.resource_type or "",
            "id": identifier,
            "repr": repr_text,
            "content_type": (f"{log.content_type.app_label}.{log.content_type.model}" if log.content_type_id else ""),
            "object_id": log.object_id or "",
        },
        "reason": log.reason or "",
        "reason_required": log.action in REASONED_ACTIONS,
        "ip_address": log.ip_address or "",
        "user_agent": log.user_agent or "",
        "request_id": str(log.request_id) if log.request_id else "",
        "diff": diff,
        "changed_count": sum(1 for item in diff if item["state"] != "same"),
        "raw": {"old_values": log.old_values, "new_values": log.new_values, "changes": log.changes},
        "filter_links": filter_links,
    }
