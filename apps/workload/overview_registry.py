"""Ekran 17 «Rektor — Ümumi baxış» — YALNIZ OXU.

Dörd görünüş (dizayn `state.view`): `overview` · `fac` (fakültələr) ·
`dep` (kafedralar) · `rep` (hesabatlar — boş vəziyyət).

⚠️ Sətir səviyyəsində REDAKTƏ YOXDUR. Bütün rəqəmlər
``services.overview.build_overview`` ilə AŞAĞIDAN YUXARI hesablanır və heç
bir yerdə saxlanılmır (§8/13).

ƏHATƏ (sahib, 2026-10-14 — «yük ümumi baxışda ancaq kafedraya uyğun görünsün»):
rəqəmlər ``workload.report`` açarının əhatəsindəndir (``scope_kind``):

* ``org``     — rektorluq / RİM / tədris şöbəsi: bütün universitet, «Fakültə» filtri açıq;
* ``faculty`` — dekan: öz fakültəsi, filtr avtomatik seçilib və gizlidir;
* ``chair``   — kafedra müdiri: yalnız öz kafedra(lar)ı, «Fakültələr» görünüşü YOXDUR.

«Fakültə» filtri seçiləndə KPI, «Təsdiq axını» və «Diqqət tələb edən kafedralar» da
həmin fakültəyə görə yenidən (aşağıdan yuxarı) hesablanır — əvvəl yalnız cədvəl daralırdı.
"""

from __future__ import annotations

from apps.organizations.public import permission_scope_unit_types

from .center_registry import current_academic_year, known_years, safe_uuid
from .constants import DEFAULT_HOURLY_PAID_CAP, PERM_REPORT
from .services import build_overview, resolve_actor
from .services.overview import _rollup, _rollup_all, _status_map

VIEWS = ("overview", "fac", "dep", "rep")

#: Fakültə səviyyəli əhatə tipləri (``core.constants.OrgUnitType`` dəyərləri).
_FACULTY_SCOPE_TYPES = frozenset({"faculty", "deanery"})
_CHAIR_SCOPE_TYPES = frozenset({"chair", "department"})

#: «Diqqət tələb edən kafedralar» siyahısının tavanı (``build_overview`` ilə eyni).
RISKY_CAP = 10


def _scope_kind(actor) -> str:
    """``org`` · ``faculty`` · ``chair`` — ``workload.report`` əhatəsinin NÖVÜ (sorğusuz, memo)."""
    if actor.scope_for(PERM_REPORT).is_org_wide:
        return "org"
    types = permission_scope_unit_types(actor.user, actor.organization, PERM_REPORT)
    if types and types <= _CHAIR_SCOPE_TYPES:
        return "chair"
    return "faculty"


def _risky(chair_rows) -> list[dict]:
    """``services.overview.build_overview``-un risk qaydası — süzülmüş sətirlər üçün."""
    risky = [
        row
        for row in chair_rows
        if row["planned_hours"] and (row["percent"] < 90 or row["vacant_hours"] or row["over_norm"])
    ]
    risky.sort(key=lambda item: (-item["vacant_hours"], item["percent"]))
    return risky[:RISKY_CAP]


def build_overview_section(request, organization) -> dict:
    actor = resolve_actor(request.user, organization, request=request)
    if not actor.has(PERM_REPORT):
        return {"has_access": False}

    scope_kind = _scope_kind(actor)
    params = request.GET
    view = params.get("wo_view") or "overview"
    if view not in VIEWS or (view == "fac" and scope_kind == "chair"):
        view = "overview"
    years = known_years(organization)
    year = params.get("wo_year") or current_academic_year(organization)

    data = build_overview(actor=actor, academic_year=year)
    faculty_options = [{"value": row["id"], "label": row["name"]} for row in data["faculties"] if row["id"]]
    # Əhatəli aktorda (dekan, kafedra müdiri) tək fakültə → avtomatik seçilir, filtr gizlənir;
    # əhatədən kənar id-lər siyahıda olmadığı üçün nəticə boşdur (sızma yoxdur).
    faculty_locked = scope_kind != "org" and len(faculty_options) <= 1
    if faculty_locked:
        faculty_id = faculty_options[0]["value"] if faculty_options else ""
    else:
        faculty_id = safe_uuid(params.get("wo_faculty"))

    chairs = data["chairs"]
    faculties, totals, risky, status_map = data["faculties"], data["totals"], data["risky"], data["status_map"]
    if faculty_id:
        chairs = [row for row in chairs if row["faculty_id"] == faculty_id]
        faculties, totals = _rollup(chairs), _rollup_all(chairs)
        risky, status_map = _risky(chairs), _status_map(chairs)

    return {
        "has_access": True,
        "view": view,
        "year": year,
        "years": years,
        "scope_kind": scope_kind,
        "show_faculties": scope_kind != "chair",
        "faculty_id": faculty_id,
        "faculty_locked": faculty_locked,
        "faculty_options": faculty_options,
        "chairs": chairs,
        "faculties": faculties,
        "totals": totals,
        "risky": risky,
        "status_map": status_map,
        "hourly_cap": DEFAULT_HOURLY_PAID_CAP,
    }


__all__ = ["VIEWS", "build_overview_section"]
