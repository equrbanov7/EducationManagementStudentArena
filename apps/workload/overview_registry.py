"""Ekran 17 «Rektor — Ümumi baxış» — YALNIZ OXU.

Dörd görünüş (dizayn `state.view`): `overview` · `fac` (fakültələr) ·
`dep` (kafedralar) · `rep` (hesabatlar — boş vəziyyət).

⚠️ Sətir səviyyəsində REDAKTƏ YOXDUR. Bütün rəqəmlər
``services.overview.build_overview`` ilə AŞAĞIDAN YUXARI hesablanır və heç
bir yerdə saxlanılmır (§8/13).
"""

from __future__ import annotations

from .center_registry import current_academic_year, known_years, safe_uuid
from .constants import DEFAULT_HOURLY_PAID_CAP, PERM_REPORT
from .services import build_overview, resolve_actor

VIEWS = ("overview", "fac", "dep", "rep")


def build_overview_section(request, organization) -> dict:
    actor = resolve_actor(request.user, organization, request=request)
    if not actor.has(PERM_REPORT):
        return {"has_access": False}

    params = request.GET
    view = params.get("wo_view") or "overview"
    if view not in VIEWS:
        view = "overview"
    years = known_years(organization)
    year = params.get("wo_year") or current_academic_year(organization)
    faculty_id = safe_uuid(params.get("wo_faculty"))

    data = build_overview(actor=actor, academic_year=year)
    chairs = data["chairs"]
    if faculty_id:
        chairs = [row for row in chairs if row["faculty_id"] == faculty_id]

    return {
        "has_access": True,
        "view": view,
        "year": year,
        "years": years,
        "faculty_id": faculty_id,
        "faculty_options": [{"value": row["id"], "label": row["name"]} for row in data["faculties"] if row["id"]],
        "chairs": chairs,
        "faculties": data["faculties"],
        "totals": data["totals"],
        "risky": data["risky"],
        "status_map": data["status_map"],
        "hourly_cap": DEFAULT_HOURLY_PAID_CAP,
    }


__all__ = ["VIEWS", "build_overview_section"]
