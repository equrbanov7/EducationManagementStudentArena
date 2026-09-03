"""Akademik kataloq bölmələri — ekran 03 «İxtisaslar» + 04 «Fənn kataloqu».

GLUE qatı: bütün məntiq ``apps.registrar.catalog_registry``-dədir (oxu) və
``apps.registrar.catalog_actions``-dadır (yazı). Burada yalnız context-in
ems_ui komponent müqavilələrinə (KPI sırası, filtr paneli, cədvəl) uyğun
formaya salınması var.

FİLTR SEMANTİKASI (handoff §8/14): `applied` state URL sorğu parametrləridir;
draft dəyər sorğu göndərmir (``static/js/ems_ui/filter_bar.js``). Sıralama və
səhifələmə də SERVER tərəfdədir — sütun başlığı adi linkdir, JS tələb etmir.
"""

from __future__ import annotations

from urllib.parse import urlencode

from django.urls import reverse
from django.utils.translation import pgettext

from apps.registrar.catalog_registry import build_programs_registry, build_subject_catalog

_CTX = "accounts.catalog"


def _sort_url(base_params: dict, *, param: str, key: str, current: str) -> str:
    """Sütun başlığının sıralama linki — `key` ↔ `-key` arasında dəyişir."""
    params = dict(base_params)
    params[param] = f"-{key}" if current == key else key
    params["section"] = base_params.get("section", "")
    return f"{reverse('accounts:profile')}?{urlencode({k: v for k, v in params.items() if v not in ('', None)})}"


def _sort_dir(current: str, key: str) -> str | None:
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


def _status_key(row, *, kind):
    """Sətir statusu — `catalog_entry` ailəsi (saxlanılmır, hesablanır)."""
    if row["is_archived"]:
        return "archived"
    if kind == "program":
        return "active" if row["has_plan"] else "no_plan"
    if row["is_duplicate"]:
        return "duplicate"
    return "active" if row["plan_usage"] else "unused"


def _program_row(row, *, can_manage):
    """`_data_table.html` müqaviləsinə uyğun sətir (birinci sütun `th scope=row`)."""
    return {
        "row_head": row["official_code"] or "—",
        "cells": [
            {"text": row["name"]},
            {"text": row["degree_label"]},
            {"text": row["form_label"]},
            {"text": " / ".join(part for part in (row["chair_name"], row["faculty_name"]) if part) or "—"},
            {"text": row["group_count"], "num": True},
            {"text": row["ects_total"], "num": True},
            {"badge_family": "catalog_entry", "badge_key": _status_key(row, kind="program")},
        ],
        "actions_include": "accounts/profile/sections/teaching_office/_program_actions.html" if can_manage else "",
        "data": row,
    }


def _subject_row(row, *, can_manage):
    return {
        "row_head": row["code"],
        "cells": [
            {"text": row["name"]},
            {"text": row["ects"], "num": True},
            {"text": row["kind_label"]},
            {"text": row["chair_name"] or "—"},
            {"text": row["plan_usage"], "num": True},
            {"badge_family": "catalog_entry", "badge_key": _status_key(row, kind="subject")},
        ],
        "actions_include": "accounts/profile/sections/teaching_office/_subject_actions.html" if can_manage else "",
        "data": row,
    }


def build_programs_section(request, section, *, active_organization, allowed_sections, active_section):
    """«İxtisaslar» reyestri (yerində mutasiya)."""
    if "programs-registry" not in allowed_sections or active_section != "programs-registry":
        return
    if active_organization is None:
        section["has_access"] = False
        return

    payload = build_programs_registry(request, active_organization)
    section.update(payload)
    if not payload.get("has_access"):
        return

    filters = payload["filters"]
    base_params = {
        "section": "programs-registry",
        "pg_q": filters["search"],
        "pg_degree": filters["degree"],
        "pg_form": filters["form"],
        "pg_chair": filters["chair"],
        "pg_noplan": "1" if filters["only_no_plan"] else "",
        "pg_arch": "1" if filters["show_archived"] else "",
    }
    program_specs = [
        ("code", pgettext(_CTX, "İxtisas kodu")),
        ("name", pgettext(_CTX, "Tam ad")),
        ("degree", pgettext(_CTX, "Təhsil pilləsi")),
        ("", pgettext(_CTX, "Təhsil forması")),
        ("", pgettext(_CTX, "Kafedra / fakültə")),
        ("", pgettext(_CTX, "Qrup")),
        ("", pgettext(_CTX, "ECTS")),
        ("", pgettext(_CTX, "Vəziyyət")),
    ]
    if payload["can_manage"]:
        # «Əməllər» sütunu YALNIZ yazma icazəsi olanda görünür — `_data_table.html`
        # sətir əməlləri xanasını da yalnız `actions_include` verildikdə render edir.
        program_specs.append(("", pgettext(_CTX, "Əməllər")))
    section["columns"] = _columns(program_specs, base_params, param="pg_sort", current=filters["sort"])
    section["base_params"] = base_params
    section["action_url"] = reverse("registrar:catalog_action")
    section["kpi_tiles"] = [
        {"label": pgettext(_CTX, "İXTİSAS"), "value": payload["filtered_count"]},
        {
            "label": pgettext(_CTX, "PLAN YOXDUR"),
            "value": payload["no_plan_total"],
            "tone": "warning" if payload["no_plan_total"] else None,
            "note": pgettext(_CTX, "Tədris planı təsdiqlənməyib"),
        },
        {"label": pgettext(_CTX, "ARXİVDƏ"), "value": payload["archived_total"], "tone": "muted"},
        {"label": pgettext(_CTX, "REYESTRDƏ CƏMİ"), "value": payload["total_count"]},
    ]
    section["state_title"] = pgettext(_CTX, "İxtisas tapılmadı")
    section["state_body"] = pgettext(_CTX, "Süzgəcləri dəyişin və ya yeni ixtisas əlavə edin.")
    section["table_rows"] = [_program_row(row, can_manage=payload["can_manage"]) for row in payload["rows"]]
    # Dialoq gizli sahələri — SAHƏ ADLARI serverdən, DƏYƏRLƏR JS-in
    # `data-tof-prefill` JSON-undan (sətirdən asılıdır).
    section["dialog_hidden"] = [{"name": "action"}, {"name": "id"}]
    section["archive_hidden"] = [{"name": "action"}, {"name": "kind"}, {"name": "id"}]
    section["form_data"] = {"data-tof-form": "1", "data-tof-url": section["action_url"]}
    # Səhifələmə linki tətbiq olunmuş filtrləri SAXLAYIR (səhifə dəyişəndə
    # süzgəc itməsin) — `partials/_pagination.html` `extra_query` müqaviləsi.
    section["pagination_query"] = urlencode(
        {key: value for key, value in base_params.items() if value not in ("", None)}
    )

    yes_no = [{"value": "", "label": pgettext(_CTX, "Hamısı")}, {"value": "1", "label": pgettext(_CTX, "Bəli")}]
    section["filter_fields"] = [
        {
            "name": "pg_q",
            "label": pgettext(_CTX, "Axtarış"),
            "kind": "search",
            "value": filters["search"],
            "placeholder": pgettext(_CTX, "Ad və ya rəsmi şifr"),
            "wide": True,
        },
        {
            "name": "pg_degree",
            "label": pgettext(_CTX, "Təhsil pilləsi"),
            "kind": "select",
            "value": filters["degree"],
            "options": [{"value": "", "label": pgettext(_CTX, "Hamısı")}] + payload["degree_options"],
        },
        {
            "name": "pg_form",
            "label": pgettext(_CTX, "Təhsil forması"),
            "kind": "select",
            "value": filters["form"],
            "options": [{"value": "", "label": pgettext(_CTX, "Hamısı")}] + payload["form_options"],
        },
        {
            "name": "pg_chair",
            "label": pgettext(_CTX, "Kafedra"),
            "kind": "select",
            "value": filters["chair"],
            "options": [{"value": "", "label": pgettext(_CTX, "Hamısı")}] + payload["chair_options"],
        },
        {
            "name": "pg_noplan",
            "label": pgettext(_CTX, "Yalnız «Plan yoxdur»"),
            "kind": "select",
            "value": "1" if filters["only_no_plan"] else "",
            "options": yes_no,
        },
        {
            "name": "pg_arch",
            "label": pgettext(_CTX, "Arxiv"),
            "kind": "select",
            "value": "1" if filters["show_archived"] else "",
            "options": [
                {"value": "", "label": pgettext(_CTX, "Aktivlər")},
                {"value": "1", "label": pgettext(_CTX, "Arxivdəkilər")},
            ],
        },
    ]
    section["filter_count_label"] = pgettext(_CTX, "Nəticə: %(count)d sətir") % {"count": payload["filtered_count"]}


def build_subjects_section(request, section, *, active_organization, allowed_sections, active_section):
    """«Fənn kataloqu» reyestri (yerində mutasiya)."""
    if "subject-catalog" not in allowed_sections or active_section != "subject-catalog":
        return
    if active_organization is None:
        section["has_access"] = False
        return

    payload = build_subject_catalog(request, active_organization)
    section.update(payload)
    if not payload.get("has_access"):
        return

    filters = payload["filters"]
    base_params = {
        "section": "subject-catalog",
        "sb_q": filters["search"],
        "sb_chair": filters["chair"],
        "sb_kind": filters["kind"],
        "sb_dup": "1" if filters["only_duplicates"] else "",
        "sb_arch": "1" if filters["show_archived"] else "",
    }
    subject_specs = [
        ("code", pgettext(_CTX, "Reyestr kodu")),
        ("name", pgettext(_CTX, "Fənnin adı")),
        ("ects", pgettext(_CTX, "Kredit (ECTS)")),
        ("", pgettext(_CTX, "Növ")),
        ("", pgettext(_CTX, "Sahibi kafedra")),
        ("usage", pgettext(_CTX, "Planlarda istifadə")),
        ("", pgettext(_CTX, "Vəziyyət")),
    ]
    if payload["can_manage"]:
        subject_specs.append(("", pgettext(_CTX, "Əməllər")))
    section["columns"] = _columns(subject_specs, base_params, param="sb_sort", current=filters["sort"])
    section["base_params"] = base_params
    section["action_url"] = reverse("registrar:catalog_action")
    section["kpi_tiles"] = [
        {"label": pgettext(_CTX, "FƏNN"), "value": payload["filtered_count"]},
        {
            "label": pgettext(_CTX, "AD DUBLİKATI"),
            "value": payload["duplicate_name_total"],
            "tone": "warning" if payload["duplicate_name_total"] else None,
            "note": pgettext(_CTX, "Eyni adlı yazılar"),
        },
        {"label": pgettext(_CTX, "PLANDA İSTİFADƏDƏ"), "value": payload["in_use_total"]},
        {"label": pgettext(_CTX, "ARXİVDƏ"), "value": payload["archived_total"], "tone": "muted"},
    ]
    section["state_title"] = pgettext(_CTX, "Fənn tapılmadı")
    section["state_body"] = pgettext(_CTX, "Süzgəcləri dəyişin və ya yeni fənn əlavə edin.")
    section["table_rows"] = [_subject_row(row, can_manage=payload["can_manage"]) for row in payload["rows"]]
    # Dialoq gizli sahələri — SAHƏ ADLARI serverdən, DƏYƏRLƏR JS-in
    # `data-tof-prefill` JSON-undan (sətirdən asılıdır).
    section["dialog_hidden"] = [{"name": "action"}, {"name": "id"}]
    section["archive_hidden"] = [{"name": "action"}, {"name": "kind"}, {"name": "id"}]
    section["form_data"] = {"data-tof-form": "1", "data-tof-url": section["action_url"]}
    # Səhifələmə linki tətbiq olunmuş filtrləri SAXLAYIR (səhifə dəyişəndə
    # süzgəc itməsin) — `partials/_pagination.html` `extra_query` müqaviləsi.
    section["pagination_query"] = urlencode(
        {key: value for key, value in base_params.items() if value not in ("", None)}
    )

    section["filter_fields"] = [
        {
            "name": "sb_q",
            "label": pgettext(_CTX, "Axtarış"),
            "kind": "search",
            "value": filters["search"],
            "placeholder": pgettext(_CTX, "Fənn kodu və ya adı"),
            "wide": True,
        },
        {
            "name": "sb_chair",
            "label": pgettext(_CTX, "Sahibi kafedra"),
            "kind": "select",
            "value": filters["chair"],
            "options": [{"value": "", "label": pgettext(_CTX, "Hamısı")}] + payload["chair_options"],
        },
        {
            "name": "sb_kind",
            "label": pgettext(_CTX, "Fənn növü"),
            "kind": "select",
            "value": filters["kind"],
            "options": [{"value": "", "label": pgettext(_CTX, "Hamısı")}] + payload["kind_options"],
        },
        {
            "name": "sb_dup",
            "label": pgettext(_CTX, "Yalnız dublikatlar"),
            "kind": "select",
            "value": "1" if filters["only_duplicates"] else "",
            "options": [
                {"value": "", "label": pgettext(_CTX, "Hamısı")},
                {"value": "1", "label": pgettext(_CTX, "Bəli")},
            ],
        },
        {
            "name": "sb_arch",
            "label": pgettext(_CTX, "Arxiv"),
            "kind": "select",
            "value": "1" if filters["show_archived"] else "",
            "options": [
                {"value": "", "label": pgettext(_CTX, "Aktivlər")},
                {"value": "1", "label": pgettext(_CTX, "Arxivdəkilər")},
            ],
        },
    ]
    section["filter_count_label"] = pgettext(_CTX, "Nəticə: %(count)d sətir") % {"count": payload["filtered_count"]}
    section["duplicate_note"] = pgettext(
        _CTX,
        "Eyni adlı fənlər birləşdirilmir — birləşdirmə (merge) destruktiv əməldir və "
        "plan sətirləri ilə sillabusların köçürülməsini tələb edir (növbəti mərhələ).",
    )


__all__ = ["build_programs_section", "build_subjects_section"]
