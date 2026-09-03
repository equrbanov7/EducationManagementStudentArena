"""Dərs yükü modulunun PUBLIC fasadı — CONTEXT MÜQAVİLƏSİ.

Profil bölmələri (``workload-distribution``, ``my-workload``) modulun DAXİLİNƏ
girmir: onlar YALNIZ buradakı iki context qurucusunu çağırır. Bölmə qeydiyyatı
DÖRD yerdə eyni olmalıdır: ``sections_api.SECTION_PARTIALS``,
``AJAX_SAFE_SECTIONS``, ``profile.html`` ``data-ajax-sections`` və
``rbac.allowed_sections``.

──────────────────────────────────────────────────────────────────────────────
1. BÖLGÜ CONTEXT-i — ``build_distribution_context`` (kafedra müdiri / RİM)
──────────────────────────────────────────────────────────────────────────────
``{
    "has_access": bool,          # `workload.distribute` VƏ ya `workload.manage`
    "can_manage": bool, "can_distribute": bool,
    "access_denied_message": str,
    "chairs": [{"id", "name"}],  # aktorun əhatəsindəki kafedralar
    "chair_id": str, "chair_name": str,
    "academic_year": str, "years": [str],
    "task": {"id", "status", "status_label", "revision"} | None,
    "rows_url", "save_row_url", "delete_row_url", "assign_url",
    "unassign_url", "confirm_url", "amend_url", "teachers_url",
    "options_url", "curriculum_url", "task_url",
    "activities": [{"key", "label"}], "seasons": [{"key", "label"}],
    "education_forms": […], "degree_levels": […], "amendment_reasons": […],
}``

2. MÜƏLLİM CONTEXT-i — ``build_my_workload_context``
``{
    "has_access": bool, "years": [str], "academic_year": str,
    "summary": {...}, "rows": [...], "seasons": [...],
    "rows_url": str, "export_url": str, "journal_base_url": str,
}``

XƏTA KODLARI (``WorkloadDenied.code``) — UI mətni bu kodlara görə yazılır:
``workload.manage_denied``, ``workload.distribute_denied``, ``workload.view_denied``,
``workload.chair_not_found``, ``workload.teacher_not_in_chair``,
``workload.hours_exceeded``, ``workload.hours_positive``,
``workload.task_not_editable``, ``workload.task_not_assignable``,
``workload.distribution_incomplete``, ``workload.amendment_not_needed``,
``workload.note_required``.
"""

from __future__ import annotations

import json

from django.urls import reverse

from .constants import (
    PERM_DISTRIBUTE,
    PERM_MANAGE,
    PERM_VIEW,
    Activity,
    AmendmentReason,
    DegreeLevel,
    EducationForm,
    RowKind,
    Season,
    TaskStatus,
    TeacherPosition,
)
from .services import (
    can_manage_chair,
    find_task,
    list_years,
    manageable_chairs,
    resolve_actor,
    teacher_workload_rows,
    teacher_workload_summary,
    teacher_years,
)

STATUS_LABELS = {str(value): str(label) for value, label in TaskStatus.choices}


def _choice_payload(choices) -> list[dict]:
    return [{"key": str(value), "label": str(label)} for value, label in choices]


def build_distribution_context(request, *, organization, chair_id=None, academic_year: str = "") -> dict:
    """«Yük bölgüsü» bölməsinin çərçivə context-i (SPA: data JSON-la gəlir)."""
    actor = resolve_actor(getattr(request, "user", None), organization, request=request)
    can_manage = actor.has(PERM_MANAGE)
    can_distribute = actor.has(PERM_DISTRIBUTE)
    base = {
        "has_access": bool(organization is not None and (can_manage or can_distribute)),
        "can_manage": can_manage,
        "can_distribute": can_distribute,
        "access_denied_message": ("Dərs yükü bölgüsü üçün icazəniz yoxdur — bu bölmə kafedra müdiri və RİM üçündür."),
        "chairs": [],
        "chair_id": "",
        "chair_name": "",
        "academic_year": "",
        "years": [],
        "task": None,
        "rows_url": reverse("workload:rows"),
        "task_url": reverse("workload:task"),
        "save_row_url": reverse("workload:row_save"),
        "delete_row_url": reverse("workload:row_delete"),
        "assign_url": reverse("workload:assign"),
        "unassign_url": reverse("workload:unassign"),
        "confirm_url": reverse("workload:confirm"),
        "amend_url": reverse("workload:amend"),
        "teachers_url": reverse("workload:teachers"),
        "options_url": reverse("workload:options"),
        "curriculum_url": reverse("workload:curriculum"),
        "activities": _choice_payload(Activity.choices),
        "seasons": _choice_payload(Season.choices),
        "education_forms": _choice_payload(EducationForm.choices),
        "degree_levels": _choice_payload(DegreeLevel.choices),
        "row_kinds": _choice_payload(RowKind.choices),
        "amendment_reasons": _choice_payload(AmendmentReason.choices),
    }
    # Xarici JS Django template engine-dən KEÇMİR (bax CLAUDE.md) — kataloqlar
    # JSON blokla ötürülür, JS onu `JSON.parse` ilə oxuyur.
    base["catalog_json"] = json.dumps(
        {
            key: base[key]
            for key in (
                "activities",
                "seasons",
                "education_forms",
                "degree_levels",
                "row_kinds",
                "amendment_reasons",
            )
        },
        ensure_ascii=False,
    )
    if not base["has_access"]:
        return base

    chairs = list(manageable_chairs(actor, permission=PERM_MANAGE if can_manage else PERM_DISTRIBUTE))
    base["chairs"] = [{"id": str(unit.pk), "name": unit.name} for unit in chairs]
    chair = None
    if chair_id:
        chair = next((unit for unit in chairs if str(unit.pk) == str(chair_id)), None)
    if chair is None and chairs:
        chair = chairs[0]
    if chair is not None:
        base["chair_id"] = str(chair.pk)
        base["chair_name"] = chair.name

    years = list_years(organization=organization, chair_ids=[unit.pk for unit in chairs])
    base["years"] = years
    year = academic_year or (years[0] if years else "")
    base["academic_year"] = year

    if chair is not None and year:
        task = find_task(organization=organization, chair_id=chair.pk, academic_year=year)
        if task is not None and can_manage_chair(actor, task.chair_id):
            base["task"] = {
                "id": str(task.pk),
                "status": task.status,
                "status_label": STATUS_LABELS.get(task.status, task.status),
                "revision": task.revision,
                "is_locked": task.is_locked,
            }
    return base


def build_my_workload_context(request, *, organization, academic_year: str = "") -> dict:
    """«Dərs yüküm» bölməsi — müəllimin öz yükü (yalnız-oxu)."""
    user = getattr(request, "user", None)
    actor = resolve_actor(user, organization, request=request)
    payload = {
        "has_access": bool(organization is not None and actor.has(PERM_VIEW)),
        "access_denied_message": "Dərs yükü məlumatına baxış icazəniz yoxdur.",
        "years": [],
        "academic_year": "",
        "summary": {},
        "rows": [],
        "seasons": _choice_payload(Season.choices),
        "rows_url": reverse("workload:my_rows"),
        "export_url": reverse("workload:my_export"),
        # Jurnal keçidi: sətir `offering_id` daşıyırsa UI bu prefiksə əlavə edir
        # (`registrar:journal_detail` = `<base>/<offering_id>/`).
        "journal_base_url": reverse("registrar:journal_list"),
    }
    if not payload["has_access"]:
        return payload

    years = teacher_years(organization=organization, teacher=user)
    payload["years"] = years
    year = academic_year or (years[0] if years else "")
    payload["academic_year"] = year
    payload["summary"] = teacher_workload_summary(organization=organization, teacher=user, academic_year=year)
    payload["rows"] = teacher_workload_rows(organization=organization, teacher=user, academic_year=year)
    return payload


# ── Kafedra profili (ekran 02) — ştat və yük xülasəsi ────────────────────────


def chair_staff_load(*, organization, teacher_ids, academic_year: str = "") -> dict:
    """Kafedra profilinin ştat/yük qatı — müəllim id → xülasə + kafedra cəmi.

    NİYƏ BURADA? «Kafedra profili» ekranı ``apps.accounts``-dadır və dərs yükü
    modulunun DAXİLİNƏ girməməlidir. Fasad yalnız hazır aqreqat qaytarır:
    saat, norma, doluluq faizi, ştat növü. Norma dəyəri POLICY cədvəlindən
    (``TeacherWorkloadProfile.annual_norm_hours``) gəlir — kodda hardcode YOX;
    profil yoxdursa NK №215 default-u (``DEFAULT_ANNUAL_NORM_HOURS``) tətbiq
    olunur (spec §8).

    ``dept_load`` status ailəsi (``core/ui/status_catalog.py``) üçün hər müəllimə
    bant açarı da verilir: `free` (<70%), `normal` (70–100%), `loaded` (100–120%),
    `risk` (>120%).
    """
    from django.contrib.auth import get_user_model

    ids = [tid for tid in teacher_ids if tid]
    summaries: dict = {}
    totals = {"teachers": len(ids), "hours": 0, "norm_hours": 0, "hourly_paid_hours": 0}
    if not ids:
        return {"by_teacher": summaries, "totals": totals, "staff_fraction_total": 0.0}

    users = {user.pk: user for user in get_user_model().objects.filter(pk__in=ids)}
    staff_fraction_total = 0.0
    for teacher_id in ids:
        user = users.get(teacher_id)
        if user is None:
            continue
        summary = teacher_workload_summary(organization=organization, teacher=user, academic_year=academic_year)
        percent = int(summary.get("fill_percent") or 0)
        if percent < 70:
            band = "free"
        elif percent <= 100:
            band = "normal"
        elif percent <= 120:
            band = "loaded"
        else:
            band = "risk"
        summary["load_band"] = band
        summary["position_label"] = str(dict(TeacherPosition.choices).get(summary.get("position"), ""))
        summaries[teacher_id] = summary
        totals["hours"] += int(summary.get("total_hours") or 0)
        totals["norm_hours"] += int(summary.get("norm_hours") or 0)
        totals["hourly_paid_hours"] += int(summary.get("hourly_paid_hours") or 0)
        try:
            staff_fraction_total += float(summary.get("staff_fraction") or 0)
        except (TypeError, ValueError):
            pass

    totals["fill_percent"] = int(round(totals["hours"] * 100 / totals["norm_hours"])) if totals["norm_hours"] else 0
    return {"by_teacher": summaries, "totals": totals, "staff_fraction_total": round(staff_fraction_total, 2)}


__all__ = [
    "STATUS_LABELS",
    "build_distribution_context",
    "build_my_workload_context",
    "chair_staff_load",
]
