"""Kabinet panellərinin konteksti — HR siyahısı («Əmək müqavilələri») və işçinin «Müqavilələrim» bölməsi.

Yalnız OXU; sətirlər şablon üçün hazır lüğətlərdir (vəziyyət tonu, qalan gün, əməl bayraqları, redaktə üçün
JSON). Əməl bayraqları server qaydasının əksidir — endpoint-lər onları yenidən, fail-closed yoxlayır.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from django.apps import apps as django_apps
from django.core.paginator import Paginator
from django.urls import reverse
from django.utils.translation import pgettext

from core.constants import OrgUnitType

from ..constants import (
    CLOSABLE_STATUSES,
    CTX,
    EMPLOYEE_SECTION,
    FILE_ACCEPT,
    HR_SECTION,
    OPEN_STATUSES,
    PAGE_SIZE,
    PARAM_PREFIX,
    TERMINATION_REASON_MIN,
    ContractState,
    ContractStatus,
    ContractType,
)
from . import queries
from .notify import person_name

P = PARAM_PREFIX

#: Heyətin bölməsi ola bilməyən (akademik / sinif) vahid tipləri.
NON_STAFF_UNIT_TYPES = (
    OrgUnitType.GROUP,
    OrgUnitType.SPECIALTY,
    OrgUnitType.CLASS,
    OrgUnitType.PARALLEL,
    OrgUnitType.GRADE_LEVEL,
)


@dataclass(frozen=True)
class ListParams:
    q: str = ""
    unit: str = ""
    unit_path: str = ""
    type: str = ""
    status: str = ""
    window: str = ""
    employee: str = ""
    page: int = 1

    def as_query(self, **override) -> str:
        values = {
            f"{P}q": self.q,
            f"{P}unit": self.unit,
            f"{P}type": self.type,
            f"{P}status": self.status,
            f"{P}window": self.window,
            f"{P}employee": self.employee,
        }
        values.update({f"{P}{key}": value for key, value in override.items()})
        from urllib.parse import urlencode

        return urlencode({key: value for key, value in values.items() if value not in ("", None)})


STATUS_FILTERS = (
    ContractState.ACTIVE,
    ContractState.EXPIRING,
    ContractState.EXPIRED,
    ContractState.DRAFT,
    ContractState.TERMINATED,
    ContractState.RENEWED,
    ContractState.DISCARDED,
)


def _units(actor):
    """Filtr / forma üçün aktorun əhatəsindəki aktiv struktur bölmələri (qruplar xaric)."""
    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    rows = OrgUnit.objects.filter(organization=actor.organization, is_active=True).exclude(
        unit_type__in=NON_STAFF_UNIT_TYPES
    )
    if not actor.view_scope.is_org_wide:
        rows = rows.filter(actor.view_scope.unit_subtree_q())
    return list(rows.order_by("path", "name").values("pk", "name", "path", "unit_type"))


def parse_params(request, units) -> ListParams:
    get = request.GET
    unit = str(get.get(f"{P}unit") or "").strip()
    known = {str(row["pk"]): row["path"] for row in units}
    if unit not in known:
        unit = ""
    contract_type = str(get.get(f"{P}type") or "")
    status = str(get.get(f"{P}status") or "")
    window = str(get.get(f"{P}window") or "")
    employee = str(get.get(f"{P}employee") or "").strip()
    try:
        page = max(1, int(get.get(f"{P}page") or 1))
    except ValueError:
        page = 1
    return ListParams(
        q=" ".join(str(get.get(f"{P}q") or "").split())[:80],
        unit=unit,
        unit_path=known.get(unit, ""),
        type=contract_type if contract_type in ContractType.values else "",
        status=status if status in {*STATUS_FILTERS, "awaiting_ack"} else "",
        window=window if window in queries.WINDOW_CHOICES else "",
        employee=employee if employee.isdigit() else "",
        page=page,
    )


def _money(value) -> str:
    if value is None:
        return ""
    return format(value.normalize(), "f")


def contract_row(contract, actor=None, *, on=None, window=None) -> dict:
    on = on or queries.today()
    state = queries.state_of(contract, on=on, window=window)
    left = queries.days_left(contract, on=on)
    is_open = contract.status in OPEN_STATUSES
    manages = bool(actor and actor.manages(contract))
    row = {
        "obj": contract,
        "id": str(contract.pk),
        "employee_name": person_name(contract.employee),
        "employee_username": contract.employee.username,
        "state": state,
        "state_label": ContractState(state).label,
        "state_tone": queries.STATE_TONES.get(state, "muted"),
        "type_label": ContractType(contract.contract_type).label,
        "days_left": left,
        "days_abs": abs(left) if left is not None else None,
        "days_tone": queries.days_tone(left) if contract.status == ContractStatus.ACTIVE else "muted",
        "unit_name": contract.unit.name if contract.unit_id else "",
        "file_url": contract.file.url if contract.file else "",
        "awaiting_ack": bool(contract.sent_at and not contract.acknowledged_at and is_open),
        "can_edit": manages and is_open,
        "can_send": manages and is_open and contract.acknowledged_at is None,
        "can_renew": manages and contract.status in CLOSABLE_STATUSES and not contract.renewed_by_id,
        "can_terminate": manages and contract.status in CLOSABLE_STATUSES,
        "can_discard": manages and contract.status == ContractStatus.DRAFT,
        "locked": contract.acknowledged_at is not None,
        "weekly_hours": _money(contract.weekly_hours),
        "staff_rate": _money(contract.staff_rate),
    }
    if manages:
        row["payload"] = json.dumps(
            {
                "id": row["id"],
                "employee": contract.employee_id,
                "employee_name": row["employee_name"],
                "number": contract.number,
                "contract_type": contract.contract_type,
                "position": contract.position,
                "unit": str(contract.unit_id or ""),
                "start_date": contract.start_date.isoformat(),
                "end_date": contract.end_date.isoformat() if contract.end_date else "",
                "probation_end": contract.probation_end.isoformat() if contract.probation_end else "",
                "weekly_hours": row["weekly_hours"],
                "staff_rate": row["staff_rate"],
                "notes": contract.notes,
                "status": contract.status,
                "file_name": contract.file_name,
            },
            ensure_ascii=False,
        )
    return row


def hr_panel(request, actor) -> dict:
    if not actor.can_view:
        return {"has_access": False}
    units = _units(actor)
    params = parse_params(request, units)
    rows, on, window = queries.filtered(actor, params)
    paginator = Paginator(rows.order_by("end_date", "employee__last_name", "employee__first_name", "pk"), PAGE_SIZE)
    page = paginator.get_page(params.page)
    items = [contract_row(contract, actor, on=on, window=window) for contract in page.object_list]
    profile_url = reverse("accounts:profile")
    section_url = f"{profile_url}?section={HR_SECTION}"
    stats = queries.kpis(actor)
    return {
        "has_access": True,
        "can_manage": actor.can_manage,
        "view_as": actor.view_as,
        "params": params,
        "rows": items,
        "page": page,
        "total": paginator.count,
        "kpis": _kpi_tiles(stats, section_url),
        "window": window,
        "section_url": section_url,
        "prev_url": f"{section_url}&{params.as_query(page=page.previous_page_number())}" if page.has_previous() else "",
        "next_url": f"{section_url}&{params.as_query(page=page.next_page_number())}" if page.has_next() else "",
        "filter_fields": _filter_fields(params, units),
        "units": units,
        "type_choices": ContractType.choices,
        "export_url": f"{reverse('hr_contracts:export')}?{params.as_query()}",
        "save_url": reverse("hr_contracts:save"),
        "staff_url": reverse("hr_contracts:staff"),
        "file_accept": FILE_ACCEPT,
        "reason_min": TERMINATION_REASON_MIN,
        "today": on.isoformat(),
    }


def _kpi_tiles(stats, section_url) -> list:
    window = stats["window"]
    return [
        {"key": ContractState.ACTIVE, "label": pgettext(CTX, "Qüvvədə"), "value": stats["active"], "tone": "accent-success",
         "url": f"{section_url}&{P}status={ContractState.ACTIVE}"},
        {"key": ContractState.EXPIRING, "label": pgettext(CTX, "{n} gün ərzində bitir").format(n=window),
         "value": stats["expiring"], "tone": "accent-warning", "url": f"{section_url}&{P}status={ContractState.EXPIRING}"},
        {"key": ContractState.EXPIRED, "label": pgettext(CTX, "Müddəti bitib"), "value": stats["expired"],
         "tone": "accent-danger", "url": f"{section_url}&{P}status={ContractState.EXPIRED}"},
        {"key": "awaiting_ack", "label": pgettext(CTX, "Təsdiq gözləyir"), "value": stats["awaiting_ack"],
         "tone": "accent-primary", "url": f"{section_url}&{P}status=awaiting_ack"},
    ]  # fmt: skip


def _options(pairs, *, empty_label):
    return [{"value": "", "label": empty_label}] + [{"value": value, "label": label} for value, label in pairs]


def _filter_fields(params, units) -> list:
    status_pairs = [(state.value, state.label) for state in STATUS_FILTERS] + [
        ("awaiting_ack", pgettext(CTX, "Təsdiq gözləyir"))
    ]
    window_pairs = [
        ("30", pgettext(CTX, "30 gün ərzində bitir")),
        ("60", pgettext(CTX, "60 gün ərzində bitir")),
        ("90", pgettext(CTX, "90 gün ərzində bitir")),
        ("expired", pgettext(CTX, "Müddəti bitib")),
    ]
    return [
        {"name": f"{P}q", "label": pgettext(CTX, "Axtarış"), "kind": "search", "value": params.q, "wide": True,
         "placeholder": pgettext(CTX, "Ad, soyad, vəzifə və ya müqavilə №")},
        {"name": f"{P}unit", "label": pgettext(CTX, "Bölmə"), "kind": "select", "value": params.unit, "searchable": True,
         "options": _options([(str(row["pk"]), row["name"]) for row in units], empty_label=pgettext(CTX, "Bütün bölmələr"))},
        {"name": f"{P}type", "label": pgettext(CTX, "Növ"), "kind": "select", "value": params.type,
         "options": _options(ContractType.choices, empty_label=pgettext(CTX, "Bütün növlər"))},
        {"name": f"{P}status", "label": pgettext(CTX, "Vəziyyət"), "kind": "select", "value": params.status,
         "options": _options(status_pairs, empty_label=pgettext(CTX, "Bütün vəziyyətlər"))},
        {"name": f"{P}window", "label": pgettext(CTX, "Bitmə müddəti"), "kind": "select", "value": params.window,
         "options": _options(window_pairs, empty_label=pgettext(CTX, "İstənilən"))},
    ]  # fmt: skip


def employee_panel(request) -> dict:
    user = getattr(request, "user", None)
    organization = getattr(request, "organization", None)
    contracts = list(queries.employee_contracts(user, organization))
    on = queries.today()
    window = queries.expiring_window()
    rows = [contract_row(contract, on=on, window=window) for contract in contracts]
    current = queries.current_for(contracts, on=on)
    pending = [row for row in rows if row["awaiting_ack"]]
    return {
        "available": organization is not None,
        "view_as": bool(getattr(request, "is_view_as", False)),
        "rows": rows,
        "current": next((row for row in rows if current is not None and row["id"] == str(current.pk)), None),
        "pending": pending,
        "others": [row for row in rows if current is None or row["id"] != str(current.pk)],
        "ack_url_name": "hr_contracts:acknowledge",
        "section_url": f"{reverse('accounts:profile')}?section={EMPLOYEE_SECTION}",
    }


def person_card(actor, user_id) -> dict | None:
    """Şəxs səhifəsinin kiçik kartı — cari müqavilə + qalan gün (aktorun əhatəsində olanlardan)."""
    if not actor.can_view:
        return None
    contracts = list(
        queries.scoped_contracts(actor)
        .filter(employee_id=user_id)
        .exclude(status__in=(ContractStatus.DRAFT, ContractStatus.DISCARDED))
        .select_related("employee", "unit")
        .order_by("-start_date", "-created_at")[:10]
    )
    if not contracts:
        return {"empty": True, "url": _person_url(user_id, "")}
    current = queries.current_for(contracts) or contracts[0]
    return {"empty": False, "row": contract_row(current, actor), "count": len(contracts),
            "url": _person_url(user_id, current.employee.username)}  # fmt: skip


def _person_url(user_id, _username) -> str:
    return f"{reverse('accounts:profile')}?section={HR_SECTION}&{P}employee={user_id}"


__all__ = ["ListParams", "contract_row", "employee_panel", "hr_panel", "parse_params", "person_card"]
