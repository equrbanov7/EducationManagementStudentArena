"""Mərhələ 2 bölmələri — 05 «Tədris planı», 06 «Qruplar», 07 «Semestr açılışı».

GLUE qatı: bütün məntiq servis modullarındadır
(``apps.registrar.curriculum_registry`` / ``semester_open``,
``apps.organizations.groups_registry``). Burada YALNIZ context-in `ems_ui`
komponent müqavilələrinə (KPI sırası, filtr paneli, cədvəl, stepper) uyğun
formaya salınması var — Mərhələ 1-dəki ``catalog_sections`` ilə eyni naxış.

FİLTR SEMANTİKASI (handoff §8/14): `applied` state URL sorğu parametrləridir;
draft dəyər sorğu göndərmir (``static/js/ems_ui/filter_bar.js``). Sıralama və
səhifələmə də SERVER tərəfdədir — sütun başlığı adi linkdir, JS tələb etmir.
"""

from __future__ import annotations

from urllib.parse import urlencode

from django.urls import reverse
from django.utils.translation import pgettext

_CTX_PLAN = "accounts.curriculum"
_CTX_GROUPS = "accounts.groups"
_CTX_SEM = "accounts.semester"


def _sort_url(base_params: dict, *, param: str, key: str, current: str) -> str:
    params = dict(base_params)
    params[param] = f"-{key}" if current == key else key
    return f"{reverse('accounts:profile')}?{urlencode({k: v for k, v in params.items() if v not in ('', None)})}"


def _sort_dir(current: str, key: str):
    if current == key:
        return "ascending"
    if current == f"-{key}":
        return "descending"
    return None


def _columns(specs, base_params, *, param, current):
    return [
        {
            "key": key,
            "label": label,
            "sortable": bool(key),
            "sort_url": _sort_url(base_params, param=param, key=key, current=current) if key else "",
            "sort_dir": _sort_dir(current, key) if key else None,
        }
        for key, label in specs
    ]


# --------------------------------------------------------------------------- #
# 05 · Tədris planı redaktoru
# --------------------------------------------------------------------------- #


def _plan_row(row, *, can_edit):
    """`_data_table.html` müqaviləsi. Xəta olan sətir mətnlə də işarələnir (§7)."""
    note = " · ".join(row["error_labels"])
    return {
        "row_head": row["subject_code"],
        "cells": [
            {"text": row["subject_name"]},
            {"text": row["credits"], "num": True},
            {"text": row["total_hours"], "num": True},
            {"text": row["lecture_hours"], "num": True},
            {"text": row["seminar_hours"], "num": True},
            {"text": row["lab_hours"], "num": True},
            {"text": row["selfwork_hours"], "num": True},
            {"text": row["weekly_hours"], "num": True},
            {"text": row["semester_number"], "num": True},
            {"text": row["chair_name"] or "—"},
            {"text": note or "—"},
        ],
        "actions_include": "accounts/profile/sections/teaching_office/_plan_row_actions.html" if can_edit else "",
        "data": row,
    }


def build_curriculum_section(request, section, *, active_organization, allowed_sections, active_section):
    """«Tədris planı redaktoru» (yerində mutasiya)."""
    if "curriculum-editor" not in allowed_sections or active_section != "curriculum-editor":
        return
    if active_organization is None:
        section["has_access"] = False
        return

    from apps.registrar.curriculum_registry import build_curriculum_editor

    payload = build_curriculum_editor(request, active_organization)
    section.update(payload)
    if not payload.get("has_access"):
        return

    plan = payload["plan"]
    balance = payload["balance"]
    can_edit = bool(payload["can_edit"] and plan and plan["is_editable"])
    section["can_edit_rows"] = can_edit
    section["action_url"] = reverse("registrar:curriculum_action")
    section["form_data"] = {"data-tof-form": "1", "data-tof-url": section["action_url"]}

    base_params = {
        "section": "curriculum-editor",
        "cu_program": payload["filters"]["program"],
        "cu_plan": plan["id"] if plan else "",
        "cu_sem": payload["filters"]["semester"],
    }
    section["base_params"] = base_params
    specs = [
        ("", pgettext(_CTX_PLAN, "Şifr")),
        ("", pgettext(_CTX_PLAN, "Fənnin adı")),
        ("", pgettext(_CTX_PLAN, "Kredit")),
        ("", pgettext(_CTX_PLAN, "Ümumi saat")),
        ("", pgettext(_CTX_PLAN, "Mühazirə")),
        ("", pgettext(_CTX_PLAN, "Seminar")),
        ("", pgettext(_CTX_PLAN, "Laboratoriya")),
        ("", pgettext(_CTX_PLAN, "Sərbəst iş")),
        ("", pgettext(_CTX_PLAN, "Həftəlik")),
        ("", pgettext(_CTX_PLAN, "Semestr")),
        ("", pgettext(_CTX_PLAN, "Tədris edən kafedra")),
        ("", pgettext(_CTX_PLAN, "Yoxlama")),
    ]
    if can_edit:
        specs.append(("", pgettext(_CTX_PLAN, "Əməllər")))
    section["columns"] = _columns(specs, base_params, param="cu_sort", current="")
    section["table_rows"] = [_plan_row(row, can_edit=can_edit) for row in payload["rows"]]
    section["state_title"] = pgettext(_CTX_PLAN, "Plan sətri yoxdur")
    section["state_body"] = pgettext(_CTX_PLAN, "Seçilmiş semestr üçün sətir qeydə alınmayıb — «Sətir əlavə et».")

    section["kpi_tiles"] = [
        {"label": pgettext(_CTX_PLAN, "PLAN SƏTRİ"), "value": payload.get("all_row_count", 0)},
        {"label": pgettext(_CTX_PLAN, "CƏMİ KREDİT"), "value": balance["total_credits"]},
        {"label": pgettext(_CTX_PLAN, "ÜMUMİ SAAT"), "value": balance["total_hours"], "unit": "saat"},
        {"label": pgettext(_CTX_PLAN, "AUDİTORİYA SAATI"), "value": balance["total_contact"], "unit": "saat"},
        {
            "label": pgettext(_CTX_PLAN, "AÇIQ XƏBƏRDARLIQ"),
            "value": len(balance["warnings"]),
            "tone": "warning" if balance["warnings"] else None,
            "note": pgettext(_CTX_PLAN, "Təsdiqə göndərməni bloklayır"),
        },
    ]
    section["semester_tabs"] = [
        {
            "key": str(bucket["semester_number"]),
            "label": pgettext(_CTX_PLAN, "%(n)d-ci semestr") % {"n": bucket["semester_number"]},
            "count": bucket["row_count"],
            "current": payload["filters"]["semester"] == str(bucket["semester_number"]),
            "url": f"{reverse('accounts:profile')}?" + urlencode({**base_params, "cu_sem": bucket["semester_number"]}),
            "warning": bucket["credit_warning"],
            "credits": bucket["credits"],
        }
        for bucket in balance["semesters"]
    ]
    section["all_tab_url"] = f"{reverse('accounts:profile')}?" + urlencode({**base_params, "cu_sem": ""})
    section["filter_fields"] = [
        {
            "name": "cu_program",
            "label": pgettext(_CTX_PLAN, "İxtisas"),
            "kind": "select",
            "value": payload["filters"]["program"],
            "options": [{"value": "", "label": pgettext(_CTX_PLAN, "Hamısı")}] + payload["program_options"],
            "wide": True,
        },
        {
            "name": "cu_plan",
            "label": pgettext(_CTX_PLAN, "Plan"),
            "kind": "select",
            "value": plan["id"] if plan else "",
            "options": payload["plan_options"],
            "wide": True,
        },
    ]
    section["filter_count_label"] = pgettext(_CTX_PLAN, "Plan sətri: %(count)d") % {
        "count": payload.get("all_row_count", 0)
    }
    section["dialog_hidden"] = [{"name": "action"}, {"name": "plan"}, {"name": "id"}]
    section["reason_hidden"] = [{"name": "action"}, {"name": "plan"}]


# --------------------------------------------------------------------------- #
# 06 · Qruplar
# --------------------------------------------------------------------------- #


def _group_row(row, *, can_manage):
    return {
        "row_head": row["name"],
        "cells": [
            {"text": row["code"] or "—"},
            {"text": row["specialty_name"] or "—"},
            {"text": " / ".join(part for part in (row["chair_name"], row["faculty_name"]) if part) or "—"},
            {"text": row["course_year"] or "—", "num": True},
            {"text": row["language_sector"] or "—"},
            {"text": row["students"], "num": True},
            {"text": row["tutor"] or "—"},
            {"badge_family": "catalog_entry", "badge_key": row["status_key"]},
        ],
        "actions_include": "accounts/profile/sections/teaching_office/_group_row_actions.html" if can_manage else "",
        "data": row,
    }


def build_groups_section(request, section, *, active_organization, allowed_sections, active_section):
    """«Qruplar» reyestri (yerində mutasiya)."""
    if "groups-registry" not in allowed_sections or active_section != "groups-registry":
        return
    if active_organization is None:
        section["has_access"] = False
        return

    from apps.organizations.groups_registry import build_groups_registry

    payload = build_groups_registry(request, active_organization)
    section.update(payload)
    if not payload.get("has_access"):
        return

    filters = payload["filters"]
    base_params = {
        "section": "groups-registry",
        "gr_q": filters["search"],
        "gr_faculty": filters["faculty"],
        "gr_specialty": filters["specialty"],
        "gr_lang": filters["language"],
        "gr_course": filters["course"],
        "gr_arch": "1" if filters["show_archived"] else "",
    }
    specs = [
        ("name", pgettext(_CTX_GROUPS, "Qrup")),
        ("code", pgettext(_CTX_GROUPS, "Kod")),
        ("", pgettext(_CTX_GROUPS, "İxtisas")),
        ("", pgettext(_CTX_GROUPS, "Kafedra / fakültə")),
        ("", pgettext(_CTX_GROUPS, "Kurs")),
        ("", pgettext(_CTX_GROUPS, "Dil sektoru")),
        ("", pgettext(_CTX_GROUPS, "Tələbə")),
        ("", pgettext(_CTX_GROUPS, "Kurator")),
        ("", pgettext(_CTX_GROUPS, "Vəziyyət")),
    ]
    if payload["can_manage"]:
        specs.append(("", pgettext(_CTX_GROUPS, "Əməllər")))
    section["columns"] = _columns(specs, base_params, param="gr_sort", current=filters["sort"])
    section["base_params"] = base_params
    section["action_url"] = reverse("organizations:group_action", kwargs={"slug": active_organization.slug})
    section["form_data"] = {"data-tof-form": "1", "data-tof-url": section["action_url"]}
    section["schedule_url"] = f"{reverse('accounts:profile')}?section=schedule-manage"
    section["exam_groups_url"] = f"{reverse('accounts:profile')}?section=groups"
    section["table_rows"] = [_group_row(row, can_manage=payload["can_manage"]) for row in payload["rows"]]
    section["state_title"] = pgettext(_CTX_GROUPS, "Qrup tapılmadı")
    section["state_body"] = pgettext(_CTX_GROUPS, "Süzgəcləri dəyişin və ya yeni qrup əlavə edin.")
    section["kpi_tiles"] = [
        {"label": pgettext(_CTX_GROUPS, "QRUP"), "value": payload["filtered_count"]},
        {"label": pgettext(_CTX_GROUPS, "TƏLƏBƏ (SƏHİFƏDƏ)"), "value": payload["student_total"]},
        {
            "label": pgettext(_CTX_GROUPS, "KURATORSUZ"),
            "value": payload["no_tutor_total"],
            "tone": "warning" if payload["no_tutor_total"] else None,
        },
        {
            "label": pgettext(_CTX_GROUPS, "PLAN YOXDUR"),
            "value": payload["no_plan_total"],
            "tone": "warning" if payload["no_plan_total"] else None,
            "note": pgettext(_CTX_GROUPS, "İxtisasın təsdiqlənmiş planı yoxdur"),
        },
        {"label": pgettext(_CTX_GROUPS, "REYESTRDƏ CƏMİ"), "value": payload["total_count"]},
    ]
    section["filter_fields"] = [
        {
            "name": "gr_q",
            "label": pgettext(_CTX_GROUPS, "Axtarış"),
            "kind": "search",
            "value": filters["search"],
            "placeholder": pgettext(_CTX_GROUPS, "Qrup adı və ya kodu"),
            "wide": True,
        },
        {
            "name": "gr_faculty",
            "label": pgettext(_CTX_GROUPS, "Fakültə"),
            "kind": "select",
            "value": filters["faculty"],
            "options": [{"value": "", "label": pgettext(_CTX_GROUPS, "Hamısı")}] + payload["faculty_options"],
        },
        {
            "name": "gr_specialty",
            "label": pgettext(_CTX_GROUPS, "İxtisas"),
            "kind": "select",
            "value": filters["specialty"],
            "options": [{"value": "", "label": pgettext(_CTX_GROUPS, "Hamısı")}] + payload["specialty_options"],
        },
        {
            "name": "gr_lang",
            "label": pgettext(_CTX_GROUPS, "Dil sektoru"),
            "kind": "select",
            "value": filters["language"],
            "options": [{"value": "", "label": pgettext(_CTX_GROUPS, "Hamısı")}] + payload["language_options"],
        },
        {
            "name": "gr_course",
            "label": pgettext(_CTX_GROUPS, "Kurs"),
            "kind": "select",
            "value": filters["course"],
            "options": [{"value": "", "label": pgettext(_CTX_GROUPS, "Hamısı")}]
            + [{"value": str(number), "label": str(number)} for number in range(1, 7)],
        },
        {
            "name": "gr_arch",
            "label": pgettext(_CTX_GROUPS, "Arxiv"),
            "kind": "select",
            "value": "1" if filters["show_archived"] else "",
            "options": [
                {"value": "", "label": pgettext(_CTX_GROUPS, "Aktivlər")},
                {"value": "1", "label": pgettext(_CTX_GROUPS, "Arxivdəkilər")},
            ],
        },
    ]
    section["filter_count_label"] = pgettext(_CTX_GROUPS, "Nəticə: %(count)d qrup") % {
        "count": payload["filtered_count"]
    }
    section["dialog_hidden"] = [{"name": "action"}, {"name": "id"}]
    section["reason_hidden"] = [{"name": "action"}, {"name": "id"}]
    # Toplu əməlin formu AYRICA işarələnir: seçilmiş sətir id-ləri ora GÖNDƏRMƏ
    # anında əlavə olunur (dialoq doldurulması gizli sahələri sıfırlayır, ona
    # görə açılışda yazmaq işləmir) — bax `teaching_office_bulk.js`.
    section["bulk_form_data"] = dict(section["form_data"], **{"data-tof-bulk-target": "1"})
    section["pagination_query"] = urlencode({k: v for k, v in base_params.items() if v not in ("", None)})


# --------------------------------------------------------------------------- #
# 07 · Semestr açılışı
# --------------------------------------------------------------------------- #


def _offering_row(row, *, can_open):
    return {
        "row_head": row["subject_code"],
        "cells": [
            {"text": row["subject_name"]},
            {"text": row["group_name"]},
            {"text": row["students"], "num": True},
            {"text": row["hours"], "num": True},
            {"text": row["chair_name"]},
            {"text": row["instructor"] or "—"},
            {"badge_family": "offering", "badge_key": row["status_key"]},
        ],
        "actions_include": "accounts/profile/sections/teaching_office/_offering_row_actions.html" if can_open else "",
        "data": row,
    }


def build_semester_section(request, section, *, active_organization, allowed_sections, active_section):
    """«Semestr açılışı» (yerində mutasiya)."""
    if "semester-opening" not in allowed_sections or active_section != "semester-opening":
        return
    if active_organization is None:
        section["has_access"] = False
        return

    from apps.registrar.semester_open import build_semester_opening, offering_counts_by_chair

    payload = build_semester_opening(request, active_organization)
    section.update(payload)
    if not payload.get("has_access"):
        return

    period = payload["period"]
    section["action_url"] = reverse("registrar:semester_action")
    section["form_data"] = {"data-tof-form": "1", "data-tof-url": section["action_url"]}
    base_params = {
        "section": "semester-opening",
        "sm_period": payload["filters"]["period"],
        "sm_chair": payload["filters"]["chair"],
    }
    section["base_params"] = base_params
    specs = [
        ("", pgettext(_CTX_SEM, "Fənn kodu")),
        ("", pgettext(_CTX_SEM, "Fənn")),
        ("", pgettext(_CTX_SEM, "Qrup")),
        ("", pgettext(_CTX_SEM, "Tələbə sayı")),
        ("", pgettext(_CTX_SEM, "Semestr saatı")),
        ("", pgettext(_CTX_SEM, "Dərsi aparan kafedra")),
        ("", pgettext(_CTX_SEM, "Təyin olunmuş müəllim")),
        ("", pgettext(_CTX_SEM, "Açılışın vəziyyəti")),
    ]
    if payload["can_open"]:
        specs.append(("", pgettext(_CTX_SEM, "Əməllər")))
    section["columns"] = _columns(specs, base_params, param="sm_sort", current="")
    section["table_rows"] = [_offering_row(row, can_open=payload["can_open"]) for row in payload["rows"]]
    section["state_title"] = pgettext(_CTX_SEM, "Açılış yoxdur")
    section["state_body"] = pgettext(_CTX_SEM, "Təsdiqlənmiş plandan açılış yaradın və ya süzgəci dəyişin.")

    if period is None:
        section["kpi_tiles"] = []
        return

    stats = payload["stats"]
    section["kpi_tiles"] = [
        {"label": pgettext(_CTX_SEM, "AÇILIŞ"), "value": stats["total"]},
        {
            "label": pgettext(_CTX_SEM, "MÜƏLLİMSİZ"),
            "value": stats["without_instructor"],
            "tone": "warning" if stats["without_instructor"] else None,
        },
        {
            "label": pgettext(_CTX_SEM, "JURNALSIZ"),
            "value": stats["without_journal"],
            "tone": "warning" if stats["without_journal"] else None,
        },
        {
            "label": pgettext(_CTX_SEM, "SİLLABUSSUZ"),
            "value": "—" if stats["without_syllabus"] is None else stats["without_syllabus"],
            "note": pgettext(_CTX_SEM, "Gecikmə hesabatına düşür"),
        },
        {"label": pgettext(_CTX_SEM, "SEMESTR SAATI"), "value": stats["hours"], "unit": "saat"},
    ]
    section["chair_rows"] = offering_counts_by_chair(active_organization, _period_instance(active_organization, period))
    section["filter_fields"] = [
        {
            "name": "sm_period",
            "label": pgettext(_CTX_SEM, "Tədris dövrü"),
            "kind": "select",
            "value": payload["filters"]["period"],
            "options": payload["period_options"],
            "wide": True,
        },
        {
            "name": "sm_chair",
            "label": pgettext(_CTX_SEM, "Kafedra"),
            "kind": "select",
            "value": payload["filters"]["chair"],
            "options": [{"value": "", "label": pgettext(_CTX_SEM, "Hamısı")}] + payload.get("chair_options", []),
        },
    ]
    section["filter_count_label"] = pgettext(_CTX_SEM, "Nəticə: %(count)d açılış") % {"count": len(payload["rows"])}
    section["dialog_hidden"] = [{"name": "action"}, {"name": "period"}, {"name": "id"}]
    section["reason_hidden"] = [{"name": "action"}, {"name": "period"}, {"name": "id"}]


def _period_instance(organization, period_payload):
    from django.apps import apps as django_apps

    AcademicPeriod = django_apps.get_model("organizations", "AcademicPeriod")
    return AcademicPeriod.objects.filter(organization=organization, pk=period_payload["id"]).first()


__all__ = ["build_curriculum_section", "build_groups_section", "build_semester_section"]
