"""Oxu qatı — vəziyyət hesablanması, HR siyahısı (filtr + KPI), işçinin öz müqavilələri.

Göstərilən vəziyyət (``ContractState``) SAXLANAN statusdan + tarixdən çıxır:
qaralama / xitam / yenilənib olduğu kimi; ``active`` isə bitmə tarixinə görə «Qüvvədədir», «Bitmək üzrədir»
(≤ ``hr.contract_expiring_window`` gün) və ya «Müddəti bitib» (bitmə tarixi keçib).
"""

from __future__ import annotations

import datetime as dt

from django.db.models import Q
from django.utils import timezone

from core.search_text import tolerant_q

from ..constants import (
    DEFAULT_EXPIRING_WINDOW,
    DEFAULT_REMINDER_DAYS,
    EMPLOYEE_VISIBLE_STATUSES,
    SETTING_EMAIL_ENABLED,
    SETTING_EXPIRING_WINDOW,
    SETTING_REMINDER_DAYS,
    ContractState,
    ContractStatus,
)
from ..models import EmploymentContract
from .access import contracts_q

#: Siyahının «bitmə pəncərəsi» filtri (gün; ``expired`` — artıq bitmiş).
WINDOW_CHOICES = ("30", "60", "90", "expired")


def today() -> dt.date:
    return timezone.localdate()


def _setting(key: str, fallback):
    try:
        from core import runtime_settings

        return runtime_settings.get(key)
    except Exception:  # noqa: BLE001 — tənzimləmə oxunmursa defolt işləyir
        return fallback


def expiring_window() -> int:
    try:
        return max(1, int(_setting(SETTING_EXPIRING_WINDOW, DEFAULT_EXPIRING_WINDOW)))
    except (TypeError, ValueError):
        return DEFAULT_EXPIRING_WINDOW


def reminder_thresholds() -> list[int]:
    """«60,30,14,7,1» → ``[60, 30, 14, 7, 1]`` (azalan, unikal, müsbət)."""
    raw = str(_setting(SETTING_REMINDER_DAYS, DEFAULT_REMINDER_DAYS) or DEFAULT_REMINDER_DAYS)
    values = set()
    for part in raw.replace(";", ",").split(","):
        try:
            value = int(part.strip())
        except ValueError:
            continue
        if 0 < value <= 365:
            values.add(value)
    return sorted(values or {60, 30, 14, 7, 1}, reverse=True)


def email_enabled() -> bool:
    return bool(_setting(SETTING_EMAIL_ENABLED, True))


def days_left(contract, *, on: dt.date | None = None):
    if contract.end_date is None:
        return None
    return (contract.end_date - (on or today())).days


def state_of(contract, *, on: dt.date | None = None, window: int | None = None) -> str:
    if contract.status != ContractStatus.ACTIVE:
        return contract.status
    left = days_left(contract, on=on)
    if left is None:
        return ContractState.ACTIVE
    if left < 0:
        return ContractState.EXPIRED
    if left <= (window if window is not None else expiring_window()):
        return ContractState.EXPIRING
    return ContractState.ACTIVE


STATE_TONES = {
    ContractState.DRAFT: "muted",
    ContractState.ACTIVE: "success",
    ContractState.EXPIRING: "warning",
    ContractState.EXPIRED: "danger",
    ContractState.TERMINATED: "neutral",
    ContractState.RENEWED: "info",
    ContractState.DISCARDED: "muted",
}


def days_tone(left) -> str:
    if left is None:
        return "muted"
    if left < 0:
        return "danger"
    if left <= 14:
        return "danger"
    if left <= expiring_window():
        return "warning"
    return "success"


def state_q(state: str, *, on: dt.date, window: int) -> Q:
    """Hesablanmış vəziyyət üzrə queryset filtri."""
    active = Q(status=ContractStatus.ACTIVE)
    soon = on + dt.timedelta(days=window)
    if state == ContractState.EXPIRED:
        return active & Q(end_date__lt=on)
    if state == ContractState.EXPIRING:
        return active & Q(end_date__gte=on, end_date__lte=soon)
    if state == ContractState.ACTIVE:
        return active & (Q(end_date__isnull=True) | Q(end_date__gt=soon))
    if state in ContractStatus.values:
        return Q(status=state)
    return Q()


def window_q(window: str, *, on: dt.date) -> Q:
    if window == "expired":
        return Q(status=ContractStatus.ACTIVE, end_date__lt=on)
    if window in WINDOW_CHOICES:
        return Q(status=ContractStatus.ACTIVE, end_date__gte=on, end_date__lte=on + dt.timedelta(days=int(window)))
    return Q()


def scoped_contracts(actor):
    if not actor.can_view:
        return EmploymentContract.objects.none()
    return EmploymentContract.objects.filter(organization=actor.organization).filter(contracts_q(actor.view_scope))


def search_q(query: str) -> Q | None:
    return tolerant_q(
        query,
        fields=("employee__first_name", "employee__last_name", "employee__username", "position", "unit__name"),
        compact_fields=("number",),
    )


def filtered(actor, params) -> tuple:
    """``(queryset, on, window)`` — HR siyahısının filtr dəsti (``params`` — ``ListParams``)."""
    on = today()
    window = expiring_window()
    rows = scoped_contracts(actor).select_related("employee", "unit", "sent_by", "renewed_by", "renewal_of")
    if params.q:
        query = search_q(params.q)
        if query is not None:
            rows = rows.filter(query)
    if params.unit:
        rows = rows.filter(Q(unit_id=params.unit) | Q(unit__path__startswith=f"{params.unit_path}/"))
    if params.type:
        rows = rows.filter(contract_type=params.type)
    if params.status == "awaiting_ack":
        rows = rows.filter(awaiting_ack_q())
    elif params.status:
        rows = rows.filter(state_q(params.status, on=on, window=window))
    else:
        rows = rows.exclude(status=ContractStatus.DISCARDED)  # ləğv edilmiş qaralama yalnız öz filtrində
    if params.window:
        rows = rows.filter(window_q(params.window, on=on))
    if params.employee:
        rows = rows.filter(employee_id=params.employee)
    return rows, on, window


def kpis(actor) -> dict:
    """Əhatədəki bütün müqavilələr üzrə dörd sayğac (filtrdən asılı DEYİL) — BİR sorğu."""
    from django.db.models import Count

    on = today()
    window = expiring_window()
    result = scoped_contracts(actor).aggregate(
        active=Count("pk", filter=state_q(ContractState.ACTIVE, on=on, window=window)),
        expiring=Count("pk", filter=state_q(ContractState.EXPIRING, on=on, window=window)),
        expired=Count("pk", filter=state_q(ContractState.EXPIRED, on=on, window=window)),
        awaiting_ack=Count("pk", filter=awaiting_ack_q()),
    )
    result["window"] = window
    return result


def employee_contracts(user, organization):
    """İşçinin öz müqavilələri — yenidən köhnəyə. Qaralama / ləğv edilmiş qaralama HEÇ VAXT (rəy A2)."""
    if organization is None or user is None or not getattr(user, "is_authenticated", False):
        return EmploymentContract.objects.none()
    return (
        EmploymentContract.objects.filter(organization=organization, employee=user)
        .filter(status__in=EMPLOYEE_VISIBLE_STATUSES)
        .select_related("unit", "renewed_by")
        .order_by("-start_date", "-created_at")
    )


def employees_with_contracts(organization) -> frozenset:
    """İşçiyə GÖRÜNƏN müqaviləsi olan istifadəçi id-ləri (``employee_contracts`` ilə eyni qayda)."""
    return frozenset(
        EmploymentContract.objects.filter(organization=organization)
        .filter(status__in=EMPLOYEE_VISIBLE_STATUSES)
        .order_by()
        .values_list("employee_id", flat=True)
        .distinct()
    )


def awaiting_ack_q() -> Q:
    return Q(sent_at__isnull=False, acknowledged_at__isnull=True) & ~Q(
        status__in=(ContractStatus.TERMINATED, ContractStatus.RENEWED, ContractStatus.DISCARDED)
    )


def current_for(contracts: list, *, on: dt.date | None = None):
    """Hazırda qüvvədə olan (və ya ən son) aktiv müqavilə — siyahıdan, sorğusuz."""
    on = on or today()
    active = [c for c in contracts if c.status == ContractStatus.ACTIVE and c.start_date <= on]
    running = [c for c in active if c.end_date is None or c.end_date >= on]
    if running:
        return running[0]
    return active[0] if active else None


__all__ = [
    "STATE_TONES",
    "WINDOW_CHOICES",
    "awaiting_ack_q",
    "current_for",
    "days_left",
    "days_tone",
    "email_enabled",
    "employee_contracts",
    "employees_with_contracts",
    "expiring_window",
    "filtered",
    "kpis",
    "reminder_thresholds",
    "scoped_contracts",
    "search_q",
    "state_of",
    "state_q",
    "today",
    "window_q",
]
