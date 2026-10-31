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
    "catalog": {activities, seasons, education_forms, degree_levels,
                row_kinds, amendment_reasons},   # `json_script` üçün (P2-4)
}``

2. MÜƏLLİM CONTEXT-i — ``build_my_workload_context``
``{
    "has_access": bool, "years": [str], "academic_year": str,
    "summary": {...}, "rows": [...], "seasons": [...],
    "rows_url": str, "export_url": str, "journal_base_url": str,
    "lines": [...],   # 2026-10-15: fənn + qrup üzrə birləşmiş xətlər (``services.my_workload_lines``)
    # Mərhələ 4 (ekran 16 §4) — təsdiq/etiraz bloku:
    "can_object": bool, "is_load_confirmed": bool, "action_url": str,
    "objection_reasons": [{"key", "label"}],   # 4 hərfi səbəb
    "objection_targets": [{"id", "label"}],    # müəllimin ÖZ bölgü sətirləri
    "objections": [{"id", "subject", "reason_label", "text", "status", …}],
}``

3. AÇILIŞIN MÜƏLLİMLƏRİ — ``teachers_for_offering(offering)`` /
   ``teachers_for_offerings(offerings)`` (cədvəl generatoru, 2026-09-25)
``{"lecture": User|None, "seminar": [User], "lab": [User], "workload_lecture": User|None,
   "hours": {"lecture", "seminar", "lab"}, "vacant": [str], "row_ids": [str]}`` — mənbə
açılışı əhatə edən tapşırıq sətirləri və onların bölgüsü (``TeacherAssignment``);
``lecture`` = jurnal sahibi, yoxdursa yükün mühazirəçisi; saat QRUP başınadır.
Toplu forma açılış sayından asılı olmayan sorğu sayı ilə işləyir. Detal:
``services/offering_teachers.py``.

XƏTA KODLARI (``WorkloadDenied.code``) — UI mətni bu kodlara görə yazılır:
``workload.manage_denied``, ``workload.distribute_denied``, ``workload.view_denied``,
``workload.chair_not_found``, ``workload.teacher_not_in_chair``,
``workload.hours_exceeded``, ``workload.hours_positive``,
``workload.task_not_editable``, ``workload.task_not_assignable``,
``workload.distribution_incomplete``, ``workload.amendment_not_needed``,
``workload.note_required``.
"""

from __future__ import annotations

from django.urls import reverse

from .center_registry import known_years
from .constants import (
    PERM_DISTRIBUTE,
    PERM_LOAD_IMPORT,
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
    distributable_chair_ids,
    find_task,
    list_years,
    manageable_chairs,
    resolve_actor,
    teacher_workload_rows,
    teacher_workload_summaries,
    teacher_workload_summary,
    teacher_years,
)
from .services.my_workload_lines import group_workload_lines
from .services.norms import norm_rule_note
from .services.offering_teachers import teachers_for_offering, teachers_for_offerings

STATUS_LABELS = {str(value): str(label) for value, label in TaskStatus.choices}


def _choice_payload(choices) -> list[dict]:
    return [{"key": str(value), "label": str(label)} for value, label in choices]


def build_distribution_context(
    request, *, organization, chair_id=None, academic_year: str = "", focus_row: str = ""
) -> dict:
    """«Yük bölgüsü» bölməsinin çərçivə context-i (SPA: data JSON-la gəlir).

    ``focus_row`` — «Mənim dərs yüküm» / ümumi baxışdakı «Redaktə et» keçidinin sətri (UUID; JS ona sürüşür).
    """
    from core.http_ids import parse_uuid

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
        # Sahib 2026-10-25: «İntensiv kurs» (kafedranın bölgü açarı və ya Tədris şöbəsinin «Dərs yükü faylı» açarı).
        "intensive_lookup_url": reverse("workload:intensive_lookup"),
        "can_intensive": bool(can_distribute or actor.has(PERM_LOAD_IMPORT)),
        "activities": _choice_payload(Activity.choices),
        "seasons": _choice_payload(Season.choices),
        "education_forms": _choice_payload(EducationForm.choices),
        "degree_levels": _choice_payload(DegreeLevel.choices),
        "row_kinds": _choice_payload([c for c in RowKind.choices if c[0] != RowKind.INTENSIVE]),
        "amendment_reasons": _choice_payload(AmendmentReason.choices),
        "norm_note": norm_rule_note(),
        "focus_row": str(parse_uuid(focus_row) or "") if focus_row else "",
    }
    # Xarici JS Django template engine-dən KEÇMİR (bax CLAUDE.md) — kataloqlar
    # JSON blokla ötürülür, JS onu `JSON.parse` ilə oxuyur.
    # 2026-09-12 (audit P2-4): əvvəl burada `json.dumps` ilə hazır sətir
    # (`catalog_json`) qurulub şablonda `|safe` ilə xam `<script>` gövdəsinə
    # yazılırdı. İndi Python obyekti (`catalog`) ötürülür — şablon onu
    # `{{ catalog|json_script:"wl-catalog" }}` ilə render edir (Django `</script>`
    # / `<`, `>`, `&` qaçırmasını özü edir; `_choice_payload` etiketləri `str()`
    # ilə hazırladığı üçün lazy tərcümə qalığı yoxdur).
    base["catalog"] = {
        key: base[key]
        for key in (
            "activities",
            "seasons",
            "education_forms",
            "degree_levels",
            "row_kinds",
            "amendment_reasons",
        )
    }
    if not base["has_access"]:
        return base

    # Sahib 2026-10-23: siyahıda YALNIZ kafedralar (inzibati şöbə — «Arxiv şöbəsi» — dərs yükü daşımır), fakültə
    # adı ilə və fakültə üzrə sıralı — axtarışla tapılsın.
    from core.constants import OrgUnitType

    chairs = sorted(
        manageable_chairs(actor, permission=PERM_MANAGE if can_manage else PERM_DISTRIBUTE)
        .filter(unit_type=OrgUnitType.CHAIR)
        .select_related("parent"),
        key=lambda unit: ((unit.parent.name if unit.parent_id else ""), unit.name),
    )
    base["chairs"] = [
        {"id": str(unit.pk), "name": f"{unit.name} — {unit.parent.name}" if unit.parent_id else unit.name}
        for unit in chairs
    ]
    chair = None
    if chair_id:
        chair = next((unit for unit in chairs if str(unit.pk) == str(chair_id)), None)
    if chair is None and chairs:
        chair = chairs[0]
    if chair is not None:
        base["chair_id"] = str(chair.pk)
        base["chair_name"] = chair.name

    # UX-08 (2026-09-05): «Tədris ili» əvvəllər sərbəst mətn idi, çünki
    # `list_years` yalnız ARTIQ TeachingTask yaradılmış illəri qaytarırdı —
    # kafedra hələ tapşırıq açmayıbsa siyahı boş görünürdü. `known_years`
    # (ekran 12 «Dərs yükü mərkəzi»ndə artıq işlənən helper) `AcademicPeriod`
    # illərini də daxil edir, ona görə picker açılış anında da doludur.
    years = sorted(
        set(list_years(organization=organization, chair_ids=[unit.pk for unit in chairs]))
        | set(known_years(organization)),
        reverse=True,
    )
    base["years"] = years
    year = academic_year or (years[0] if years else "")
    if year and year not in years:
        years = sorted(set(years) | {year}, reverse=True)
        base["years"] = years
    base["academic_year"] = year

    base["objections"] = []
    base["action_url"] = reverse("workload:action")
    base["objection_hidden"] = [{"name": "action"}, {"name": "objection"}, {"name": "state"}]
    base["form_data"] = {"data-tof-form": "1", "data-tof-url": base["action_url"]}
    if chair is not None and year:
        task = find_task(organization=organization, chair_id=chair.pk, academic_year=year)
        if task is not None and can_manage_chair(actor, task.chair_id):
            base["task"] = {
                "id": str(task.pk),
                "status": task.status,
                "status_label": STATUS_LABELS.get(task.status, task.status),
                "revision": task.revision,
                "is_locked": task.is_locked,
                # Zəncir qapısı (plan §2/14): bölgü YALNIZ təsdiqdən sonra.
                "is_chain_blocked": task.status in ("submitted", "returned", "pending_final_approval"),
            }
            base["objections"] = _chair_objection_payload(task)
    return base


def _chair_objection_payload(task) -> list[dict]:
    """Ekran 14 — müəllim etirazları (kafedra müdiri görür və yenidən bölür)."""
    from .services import chair_objections

    return [
        {
            "id": str(item.pk),
            "subject": item.row.subject_label,
            "teacher": ((item.teacher.get_full_name() or item.teacher.username) if item.teacher_id else ""),
            "reason_label": item.get_reason_key_display(),
            "text": item.text,
            "status": item.status,
            "status_label": item.get_status_display(),
            "created_at": item.created_at,
            "resolution_note": item.resolution_note,
            "is_open": item.status == "open",
        }
        for item in chair_objections(task=task)[:50]
    ]


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

    from .services.recorded_hours import teacher_recorded_hours

    history = teacher_recorded_hours(actor)
    years = sorted(set(teacher_years(organization=organization, teacher=user)) | set(history["years"]), reverse=True)
    payload["years"] = years
    year = academic_year or (years[0] if years else "")
    payload["academic_year"] = year
    payload["recorded_hours"] = teacher_recorded_hours(actor, academic_year=year)
    payload["summary"] = teacher_workload_summary(organization=organization, teacher=user, academic_year=year)
    payload["rows"] = teacher_workload_rows(organization=organization, teacher=user, academic_year=year)
    # 2026-10-15: cədvəl fənn + qrup üzrə birləşmiş xətləri göstərir; «Redaktə et» — yalnız aktorun
    # `workload.distribute` əhatəsindəki kafedralar (müəllimin özündə açar yoxdur → yalnız oxu).
    edit_chair_ids = distributable_chair_ids(actor)
    payload["lines"] = group_workload_lines(payload["rows"], edit_chair_ids=edit_chair_ids)
    payload["can_edit_any"] = bool(edit_chair_ids)
    payload.update(_confirmation_block(actor, organization, user, year, payload["rows"]))
    return payload


def _confirmation_block(actor, organization, user, year: str, rows) -> dict:
    """Ekran 16 §4 «Təsdiq / etiraz» — server-render idarəetmə bloku.

    Etiraz hədəfi (bölgü sətri) SEÇİCİDƏN gəlir: cədvəl JS ilə dolur, dialoq
    isə server-render-lidir — beləliklə iki data modeli bir-birinə bağlanmır.
    """
    from .constants import PERM_OBJECT, ObjectionReason
    from .services import is_load_confirmed, my_objections

    can_object = bool(actor.has(PERM_OBJECT) and year)
    objections = list(my_objections(organization=organization, teacher=user, academic_year=year)[:50]) if year else []
    return {
        "can_object": can_object,
        "action_url": reverse("workload:action"),
        # `_reason_dialog.html` gizli sahələri (JS `data-tof-prefill` ilə doldurur).
        "objection_hidden": [{"name": "action"}, {"name": "assignment"}],
        "form_data": {"data-tof-form": "1", "data-tof-url": reverse("workload:action")},
        "is_load_confirmed": bool(
            year and is_load_confirmed(organization=organization, teacher=user, academic_year=year)
        ),
        "objection_reasons": [{"key": str(value), "label": str(label)} for value, label in ObjectionReason.choices],
        "objection_targets": [
            {
                "id": row["id"],
                "label": f"{row['subject']} · {row['activity_label']} · {row['hours']} saat",
            }
            for row in rows
        ],
        "objections": [
            {
                "id": str(item.pk),
                "subject": item.row.subject_label,
                "reason_label": item.get_reason_key_display(),
                "text": item.text,
                "status": item.status,
                "status_label": item.get_status_display(),
                "created_at": item.created_at,
                "resolution_note": item.resolution_note,
            }
            for item in objections
        ],
    }


# ── Kafedra profili (ekran 02) — ştat və yük xülasəsi ────────────────────────


def chair_staff_load(*, organization, teacher_ids, academic_year: str = "", chair_id=None) -> dict:
    """Kafedra profilinin ştat/yük qatı — müəllim id → xülasə + kafedra cəmi.

    NİYƏ BURADA? «Kafedra profili» ekranı ``apps.accounts``-dadır və dərs yükü
    modulunun DAXİLİNƏ girməməlidir. Fasad yalnız hazır aqreqat qaytarır:
    saat, norma, doluluq faizi, ştat növü. Norma «Sistem tənzimləmələri»ndəki
    qayda ilə hesablanır (``services.norms``: 1 ştat / 0,5 ştat / inzibati
    vəzifəli ayrıca, digər paylar 1 ştata mütənasib; sahib 2026-10-14).

    ``dept_load`` status ailəsi (``core/ui/status_catalog.py``) üçün hər müəllimə
    bant açarı da verilir: `free` (<70%), `normal` (70–100%), `loaded` (100–120%),
    `risk` (>120%).

    KAFEDRALAR ARASI (sahib 2026-10-25): müəllim ştat olaraq bir kafedrada, saathesabı başqa kafedranın
    tapşırığında ola bilər. Hər xülasədə ``hours_by_chair`` (kafedra id → saat) və nəticədə ``chair_names``
    var — oxucu «başqa kafedrada: N saat»ı öz kafedrasına görə hesablayır. ``chair_id`` verilərsə (kafedra
    profili) əlavə olaraq: ``home_chair_id``/``home_chair_name`` (ştat kafedrası), ``is_outside`` (ştatı başqa
    kafedradadır — bu kafedraya yalnız saat verir), ``chair_hours`` (bu kafedradakı saat), ``other_chair_hours``
    və ``other_chairs`` (ştat kafedrasından kənar saatlar); kənar müəllim ştat/norma cəmlərinə DÜŞMÜR.
    """
    from django.apps import apps as django_apps
    from django.contrib.auth import get_user_model

    ids = [tid for tid in teacher_ids if tid]
    summaries: dict = {}
    totals = {"teachers": len(ids), "hours": 0, "norm_hours": 0, "hourly_paid_hours": 0}
    if not ids:
        return {"by_teacher": summaries, "totals": totals, "staff_fraction_total": 0.0, "chair_names": {}}

    users = {user.pk: user for user in get_user_model().objects.filter(pk__in=ids)}
    staff_fraction_total = 0.0
    # Toplu aqreqat: hər müəllimə 5 sorğu əvəzinə cəmi 2 sorğu (QA 2026-09-05 P2-3).
    bulk = teacher_workload_summaries(organization=organization, teacher_ids=ids, academic_year=academic_year)
    from .services.people import home_chairs

    homes = home_chairs(organization, ids) if chair_id else {}
    chair_ids = {key for item in bulk.values() for key in (item.get("hours_by_chair") or {})}
    chair_ids |= {home["id"] for home in homes.values()}
    chair_names = {
        str(pk): name
        for pk, name in django_apps.get_model("organizations", "OrgUnit")
        .objects.filter(organization=organization, pk__in=chair_ids)
        .values_list("pk", "name")
    }
    for teacher_id in ids:
        user = users.get(teacher_id)
        if user is None:
            continue
        summary = dict(bulk.get(teacher_id) or {})
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
        if chair_id and _attach_cross_chair(summary, homes.get(teacher_id), str(chair_id), chair_names):
            totals["teachers"] -= 1
            continue  # kənar müəllim: ştatı başqa kafedradadır — bu kafedranın ştat/norma cəmlərinə düşmür
        totals["hours"] += int(summary.get("total_hours") or 0)
        totals["norm_hours"] += int(summary.get("norm_hours") or 0)
        totals["hourly_paid_hours"] += int(summary.get("hourly_paid_hours") or 0)
        try:
            staff_fraction_total += float(summary.get("staff_fraction") or 0)
        except (TypeError, ValueError):
            pass

    totals["fill_percent"] = int(round(totals["hours"] * 100 / totals["norm_hours"])) if totals["norm_hours"] else 0
    return {
        "by_teacher": summaries,
        "totals": totals,
        "staff_fraction_total": round(staff_fraction_total, 2),
        "chair_names": chair_names,
    }


def other_chair_hours(summary: dict, home_chair_id, chair_names: dict) -> tuple[int, list[dict]]:
    """(ştat kafedrasından kənar saat, [{"name", "hours"}]) — ``chair_staff_load`` xülasəsindən."""
    home = str(home_chair_id or "")
    others = [
        {"name": chair_names.get(key, ""), "hours": hours}
        for key, hours in (summary.get("hours_by_chair") or {}).items()
        if key != home and hours
    ]
    others.sort(key=lambda item: (-item["hours"], item["name"]))
    return sum(item["hours"] for item in others), others


def _attach_cross_chair(summary: dict, home, chair_id: str, chair_names: dict) -> bool:
    """Kafedra profili sətri: ştat kafedrası, bu kafedradakı saat, kənar saatlar. Qaytarır: müəllim kənardırmı."""
    home_id = (home or {}).get("id", "")
    is_outside = bool(home_id and home_id != chair_id)
    summary["home_chair_id"] = home_id
    summary["home_chair_name"] = (home or {}).get("name", "")
    summary["is_outside"] = is_outside
    summary["chair_hours"] = int((summary.get("hours_by_chair") or {}).get(chair_id, 0))
    summary["other_chair_hours"], summary["other_chairs"] = other_chair_hours(summary, home_id or chair_id, chair_names)
    return is_outside


def position_labels() -> dict:
    """Yük profilinin vəzifə açarı → etiket (``TeacherPosition``) — modul xaricindəki oxucular üçün."""
    return {key: str(label) for key, label in TeacherPosition.choices}


__all__ = [
    "STATUS_LABELS",
    "build_distribution_context",
    "build_my_workload_context",
    "chair_staff_load",
    "other_chair_hours",
    "position_labels",
    "teachers_for_offering",
    "teachers_for_offerings",
]


# Explicit exports keep external callers out of implementation modules.
from .public_exports import *  # noqa: E402,F401,F403
from .public_exports import __all__ as _api_exports  # noqa: E402

__all__ += [name for name in _api_exports if name not in __all__]


from .services.mr118_journal_binding import MR118Error, repair_mr118_journal_binding  # noqa: E402,F401
from .services.mr123_subject_repair import MR123Error, repair_mr123_subject  # noqa: E402,F401
