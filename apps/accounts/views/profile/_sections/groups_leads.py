"""«Qruplar» reyestri — STAROSTA sütunu + «Starosta təyin et / dəyiş / götür» dialoqlarının konteksti.

2026-10-13 (gecə), sahib: «qrupa starosta əlavə etmək yerinə yenidən bax». Əvvəl reyestrdə kimin starosta
olduğu görünmürdü, təyinat isə ümumi rol axınlarından gedirdi (``scope_unit`` boş → bölmə açılmırdı).
İndi hər sətirdə starostanın adı (və ya «—»), çekmecədə isə qrupun öz qeydiyyatlı tələbələrindən seçimli
dialoq var; yazı ``accounts:group_lead_action``-a gedir (qapı + qaydalar serverdədir).

Sorğu büdcəsi: səhifə üzrə 2 sorğu (``group_lead_map``) — qrup sayından asılı deyil.
"""

from __future__ import annotations

from types import SimpleNamespace

from django.urls import reverse

from ....services.group_lead import group_lead_map
from ...group_lead import LEAD_MANAGE_PERMISSIONS, can_manage_group_leads

LEAD_CELL_INCLUDE = "accounts/profile/sections/teaching_office/_group_lead_cell.html"


def attach_group_leads(organization, rows) -> None:
    """Reyestr sətirlərinə ``lead_*`` sahələrini yazır (yerində)."""
    leads = group_lead_map(organization, [row["id"] for row in rows])
    by_id = {str(group_id): items for group_id, items in leads.items()}
    for row in rows:
        items = by_id.get(str(row["id"]), [])
        primary = items[0] if items else None
        row["lead_name"] = primary.name if primary else ""
        row["lead_username"] = primary.username if primary else ""
        if len(items) > 1:
            row["lead_warning"] = "multiple"
        elif primary is not None and primary.not_in_group:
            row["lead_warning"] = "not_in_group"
        else:
            row["lead_warning"] = ""


def attach_lead_rights(request, organization, rows) -> None:
    """Hər sətrə ``can_lead`` — qrup starosta açarlarından BİRİNİN (öz) əhatəsindədirmi (yerində).

    2026-10-14: reyestrin OXU əhatəsi fakültəyə genişləndi; starosta düymələri isə yalnız ``manageable_group``
    qapısından keçən qrupda görünür (server kənar qrupa 404). Əhatələr bir dəfə həll olunur — sətir başına
    sorğu YOXDUR; aktiv olmayan (arxiv) qrupda starosta təyin edilmir.
    """
    from apps.organizations.public import get_permission_scope, unit_in_scope

    scopes = [
        get_permission_scope(request.user, organization, permission, request=request)
        for permission in LEAD_MANAGE_PERMISSIONS
    ]
    scopes = [scope for scope in scopes if scope.has_structure_access]
    for row in rows:
        unit = SimpleNamespace(pk=None, path=row.get("path", ""))
        row["can_lead"] = bool(row.get("is_active")) and any(unit_in_scope(scope, unit) for scope in scopes)


def lead_cell(row) -> dict:
    return {"include": LEAD_CELL_INCLUDE, "lead": row}


def lead_dialog_context(request, organization) -> dict:
    action_url = reverse("accounts:group_lead_action")
    return {
        "can_assign_lead": can_manage_group_leads(request, organization),
        "lead_action_url": action_url,
        "lead_form_data": {"data-tof-form": "1", "data-tof-url": action_url},
        # `keep` — dialoq açılışında `action` sıfırlanmasın (teaching_office.js prefill qaydası).
        "lead_assign_hidden": [{"name": "action", "value": "assign", "keep": True}, {"name": "group_id"}],
        "lead_remove_hidden": [{"name": "action", "value": "remove", "keep": True}, {"name": "group_id"}],
    }


__all__ = ["attach_group_leads", "attach_lead_rights", "lead_cell", "lead_dialog_context"]
