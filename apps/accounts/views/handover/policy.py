"""Fənn təhvili bölməsinin AKTOR qapısı + serializasiya köməkçiləri.

``people`` kataloqundakı ``PeopleActor`` naxışı ilə eyni məntiq: sorğudan
təşkilat + icazə həll olunur, qapı **fail-closed**-dur. Fərq — burada icazə
YALNIZ bir açardır (``journal.reassign``) və əhatə hesablaması registrar
tərəfdədir (``apps.registrar.handover.actor_scope``), çünki əhatə açılışın
QRUPUNA görə hesablanır (fakültə → kafedra → qrup zənciri).
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.registrar import handover as handover_read


@dataclass(frozen=True)
class HandoverActor:
    """Sorğu üçün həll olunmuş təhvil konteksti."""

    user: object
    organization: object | None
    can_reassign: bool
    is_superadmin: bool

    @property
    def has_access(self) -> bool:
        return bool(self.organization is not None and self.can_reassign)


def _is_superadmin(user) -> bool:
    return bool(getattr(user, "is_superuser", False) or getattr(user, "is_superadmin", False))


def resolve_actor(request) -> HandoverActor:
    """Sorğudan aktoru qurur; heç vaxt exception atmır (fail-closed)."""
    from apps.accounts.views._helpers.tenant import _get_active_organization

    user = getattr(request, "user", None)
    if user is None or not getattr(user, "is_authenticated", False):
        return HandoverActor(user=None, organization=None, can_reassign=False, is_superadmin=False)

    organization = _get_active_organization(request)
    return HandoverActor(
        user=user,
        organization=organization,
        can_reassign=bool(organization is not None and handover_read.can_reassign(user, organization)),
        is_superadmin=_is_superadmin(user),
    )


# ── Serializasiya ────────────────────────────────────────────────────────────


def person_name(user) -> str:
    if user is None:
        return ""
    full = (getattr(user, "get_full_name", lambda: "")() or "").strip()
    return full or str(getattr(user, "username", "") or "")


def person_row(user) -> dict:
    if user is None:
        return {"id": "", "name": "", "username": ""}
    return {
        "id": str(user.pk),
        "name": person_name(user),
        "username": str(getattr(user, "username", "") or ""),
    }


def period_label(period) -> str:
    """Semestrin oxunaqlı adı — il TƏKRARLANMIR.

    Real datada dövr adı çox vaxt ili onsuz da daşıyır («2024/2025 Payız»).
    Kor-koranə birləşdirsək «2024/2025 Payız · 2024/2025» alınırdı.
    """
    if period is None:
        return ""
    year = str(getattr(period, "year_display", "") or "")
    name = str(getattr(period, "name", "") or "")
    if not year or year in name:
        return name or year
    return f"{name} · {year}".strip(" ·")


def offering_row(offering, *, blocker_codes, blocker_labels, counts) -> dict:
    """Cədvəl sətri — UI-ın söykəndiyi JSON müqaviləsi (açar adları dəyişməz)."""
    subject = offering.subject
    stats = counts.get(offering.pk, {})
    return {
        "id": str(offering.pk),
        "subject_code": getattr(subject, "code", "") or "",
        "subject_name": getattr(subject, "name", "") or "",
        "group": getattr(offering.group, "name", "") or "",
        "period": period_label(offering.period),
        "period_id": str(offering.period_id or ""),
        "is_current_period": bool(getattr(offering.period, "is_current", False)),
        "instructor": person_row(offering.instructor),
        "students": stats.get("students", 0),
        "lessons": stats.get("lessons", 0),
        "marks": stats.get("marks", 0),
        "finals": stats.get("finals", 0),
        "can_transfer": not blocker_codes,
        "blockers": [{"code": code, "label": blocker_labels.get(code, code)} for code in blocker_codes],
    }


__all__ = [
    "HandoverActor",
    "offering_row",
    "period_label",
    "person_name",
    "person_row",
    "resolve_actor",
]
