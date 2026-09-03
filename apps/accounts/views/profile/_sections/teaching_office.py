"""Tədris şöbəsi bölmələri — ekran 01 «Universitet strukturu» + 02 «Kafedra profili».

Bu modul GLUE qatıdır: domen məntiqi ÜÇ ayrı modulda qalır və buraya yalnız
onların fasadları çağırılır (memory: cross-domain glue accounts-dadır):

* struktur / ağac / kafedra detalı → ``apps.organizations.structure_views``
* müəllim ştatı və yük saatları     → ``apps.workload.public.chair_staff_load``
* sillabus əhatəsi                  → ``apps.syllabus.models`` (sayğac sorğusu)

SCOPE (handoff §8/8 — «əhatə yoxdur ≠ bütün universitet»): kafedra siyahısı
``visible_chairs`` ilə gəlir, o da ``scope_org_units``-a söykənir — kafedra
müdiri YALNIZ öz kafedrasını görür, əhatəsiz aktor BOŞ siyahı alır.
"""

from __future__ import annotations

from django.utils.translation import pgettext

from apps.organizations.structure_views import (
    build_structure_tree_context,
    chair_detail_context,
    visible_chairs,
)
from apps.workload.public import chair_staff_load

_CTX = "accounts.chair_profile"


def build_structure_tree_section(request, section, *, active_organization, allowed_sections, active_section):
    """«Universitet strukturu» — OrgUnit ağacı (yerində mutasiya)."""
    if "org-structure-tree" not in allowed_sections or active_section != "org-structure-tree":
        return
    if active_organization is None:
        section["has_access"] = False
        return
    section.update(build_structure_tree_context(request, active_organization))


def _syllabus_coverage(organization, chair, teacher_ids) -> dict:
    """Müəllim → (təsdiqlənmiş, cəmi) sillabus sayı + kafedra faizi.

    Sillabus modulunun DAXİLİNƏ girmirik — yalnız iki aqreqat sorğu. Sayğac
    SAXLANILMIR (handoff §8/13): hər dəfə hesablanır.
    """
    from apps.syllabus.models import Syllabus

    by_teacher: dict = {}
    queryset = Syllabus.objects.filter(organization=organization, is_active=True).filter(chair_unit=chair)
    for author_id, approved_id in queryset.values_list("author_id", "approved_version_id"):
        bucket = by_teacher.setdefault(author_id, {"total": 0, "approved": 0})
        bucket["total"] += 1
        if approved_id:
            bucket["approved"] += 1
    total = sum(bucket["total"] for bucket in by_teacher.values())
    approved = sum(bucket["approved"] for bucket in by_teacher.values())
    for teacher_id in teacher_ids:
        by_teacher.setdefault(teacher_id, {"total": 0, "approved": 0})
    return {
        "by_teacher": by_teacher,
        "total": total,
        "approved": approved,
        "percent": int(round(approved * 100 / total)) if total else 0,
    }


def build_chair_profile_section(request, section, *, active_organization, allowed_sections, active_section):
    """«Kafedra profili» — ştat, müəllim heyəti, yük riski (yerində mutasiya)."""
    if "chair-profile" not in allowed_sections or active_section != "chair-profile":
        return
    if active_organization is None:
        section["has_access"] = False
        section["state_title"] = pgettext(_CTX, "Aktiv təşkilat konteksti yoxdur")
        section["state_body"] = pgettext(_CTX, "Təşkilat seçin və ya administratora müraciət edin.")
        return

    chairs = visible_chairs(request, active_organization)
    section["has_access"] = True
    section["chairs"] = [{"id": str(unit.id), "name": unit.name} for unit in chairs]
    section["chairs_options"] = [{"value": str(unit.id), "label": unit.name} for unit in chairs]
    section["chair_search"] = (request.GET.get("cp_q") or "").strip()[:120]
    section["academic_year"] = (request.GET.get("cp_year") or "").strip()[:20]

    if not chairs:
        # Əhatəsiz aktor: BOŞ vəziyyət + administrator kanalı (handoff §8/8).
        section["state_kind"] = "empty"
        section["state_title"] = pgettext(_CTX, "Əhatənizdə kafedra yoxdur")
        section["state_body"] = pgettext(
            _CTX,
            "Struktur əhatəniz təyin edilməyib. Kafedra təyinatı üçün Tədris şöbəsinə "
            "və ya administratora müraciət edin.",
        )
        return

    requested = (request.GET.get("cp_chair") or "").strip()
    chair = next((unit for unit in chairs if str(unit.id) == requested), chairs[0])
    section["selected_chair_id"] = str(chair.id)
    section["chair"] = chair

    detail = chair_detail_context(request, active_organization, chair)
    section["detail"] = detail

    memberships = detail.get("teacher_memberships") or []
    teacher_ids = [membership.user_id for membership in memberships]
    load = chair_staff_load(
        organization=active_organization,
        teacher_ids=teacher_ids,
        academic_year=section["academic_year"],
    )
    coverage = _syllabus_coverage(active_organization, chair, teacher_ids)

    staff_rows = []
    employment_counts = {"stat": 0, "evezcilik": 0, "saathesabi": 0}
    for membership in memberships:
        summary = load["by_teacher"].get(membership.user_id, {})
        syllabus_bucket = coverage["by_teacher"].get(membership.user_id, {"total": 0, "approved": 0})
        # Ştat növü: `staff_fraction` < 1 → əvəzçilik, saathesabı saatı varsa
        # saathesabı; əks halda tam ştat. Dəyərlər POLICY cədvəlindən
        # (`TeacherWorkloadProfile`) gəlir — kodda hardcode norma YOXDUR.
        try:
            fraction = float(summary.get("staff_fraction") or 0)
        except (TypeError, ValueError):
            fraction = 0.0
        if summary.get("hourly_paid_hours"):
            employment = "saathesabi"
        elif fraction and fraction < 1:
            employment = "evezcilik"
        else:
            employment = "stat"
        employment_counts[employment] += 1
        staff_rows.append(
            {
                "user_id": str(membership.user_id),
                "name": membership.user.get_full_name() or membership.user.username,
                "position_label": summary.get("position_label") or "",
                "employment": employment,
                "staff_fraction": summary.get("staff_fraction") or "",
                "hours": summary.get("total_hours") or 0,
                "norm_hours": summary.get("norm_hours") or 0,
                "fill_percent": summary.get("fill_percent") or 0,
                "load_band": summary.get("load_band") or "free",
                "syllabus_total": syllabus_bucket["total"],
                "syllabus_approved": syllabus_bucket["approved"],
                "is_active_teacher": getattr(membership, "is_active_teacher", False),
            }
        )

    only_overloaded = (request.GET.get("cp_risk") or "") == "1"
    if only_overloaded:
        staff_rows = [row for row in staff_rows if row["load_band"] in {"loaded", "risk"}]

    section["staff_rows"] = staff_rows
    section["staff_state"] = "ready" if staff_rows else "empty"
    section["employment_counts"] = employment_counts
    section["staff_fraction_total"] = load["staff_fraction_total"]
    section["load_totals"] = load["totals"]
    section["syllabus_coverage"] = {
        "total": coverage["total"],
        "approved": coverage["approved"],
        "percent": coverage["percent"],
    }
    section["only_overloaded"] = only_overloaded
    section["filter_fields"] = [
        {
            "name": "cp_chair",
            "label": pgettext(_CTX, "Kafedra"),
            "kind": "select",
            "value": str(chair.id),
            "options": section["chairs_options"],
            "wide": True,
        },
        {
            "name": "cp_year",
            "label": pgettext(_CTX, "Tədris ili"),
            "kind": "text",
            "value": section["academic_year"],
            "placeholder": "2025/2026",
        },
        {
            "name": "cp_risk",
            "label": pgettext(_CTX, "Yalnız yüklü / risk"),
            "kind": "select",
            "value": "1" if only_overloaded else "",
            "options": [
                {"value": "", "label": pgettext(_CTX, "Hamısı")},
                {"value": "1", "label": pgettext(_CTX, "Bəli")},
            ],
        },
    ]
    section["filter_count_label"] = pgettext(_CTX, "Nəticə: %(count)d müəllim") % {"count": len(staff_rows)}
    section["kpi_tiles"] = [
        {"label": pgettext(_CTX, "MÜƏLLİM"), "value": detail.get("total_teacher_count", 0)},
        {
            "label": pgettext(_CTX, "ŞTAT VAHİDİ CƏMİ"),
            "value": load["staff_fraction_total"],
            "note": pgettext(_CTX, "Ştat payının cəmi"),
        },
        {
            "label": pgettext(_CTX, "İLLİK SAAT"),
            "value": load["totals"]["hours"],
            "unit": pgettext(_CTX, "saat"),
            "has_bar": True,
            "pct": load["totals"].get("fill_percent", 0),
            "note": pgettext(_CTX, "Normaya nisbətdə"),
        },
        {
            "label": pgettext(_CTX, "SİLLABUS ƏHATƏSİ"),
            "value": coverage["percent"],
            "unit": "%",
            "tone": "success" if coverage["percent"] >= 80 else "warning",
        },
    ]
    # Norma dəyərləri POLICY cədvəlindədir (`TeacherWorkloadProfile.annual_norm_hours`);
    # handoff-un iki `normSet` variantı (Nazirlik ↔ Universitet) SAHİB QƏRARI
    # gözləyir — dəyərlər verilməyib, ona görə ekran tək (mövcud) dəsti göstərir.
    section["norm_source_note"] = pgettext(
        _CTX,
        "Norma dəyərləri müəllim yük profilindən oxunur (NK №215 default: 500 saat). "
        "Nazirlik/Universitet norma dəstlərinin ayrılması sahib qərarını gözləyir.",
    )


__all__ = ["build_chair_profile_section", "build_structure_tree_section"]
