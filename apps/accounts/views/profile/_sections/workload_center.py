"""Ekran 12 «Dərs yükü mərkəzi» — GLUE qatı (tədris şöbəsi).

Bütün məntiq ``apps.workload.center_registry``-dədir; burada YALNIZ kontekstin
`ems_ui` komponent müqavilələrinə (KPI sırası, filtr paneli, cədvəl, tab,
timeline) uyğun formaya salınması var — Mərhələ 1/2-nin `catalog_sections` /
`curriculum_sections` naxışı.

FİLTR SEMANTİKASI (§8/14): `applied` = URL parametrləri; draft dəyər sorğu
göndərmir. Sıralama və səhifələmə serverdədir.
"""

from __future__ import annotations

from urllib.parse import urlencode

from django.urls import reverse
from django.utils.translation import pgettext

_CTX = "accounts.workload_center"


def _row_columns() -> tuple:
    """Dizayn 12 «SEMESTR … KREDİT» sütun sırası (rəsmi TAPŞIRIQ şablonu).

    Etiketlər AÇIQ ``pgettext`` çağırışlarıdır — dəyişənlə çağırış mənbə
    skanerinə (``scripts/i18n_source_scan.py``) görünmür.
    """
    return (
        pgettext(_CTX, "Semestr"),
        pgettext(_CTX, "Qruplar"),
        pgettext(_CTX, "Fənn"),
        pgettext(_CTX, "İxtisas"),
        pgettext(_CTX, "Forma"),
        pgettext(_CTX, "Səviyyə"),
        pgettext(_CTX, "Tələbə"),
        pgettext(_CTX, "Birl."),
        pgettext(_CTX, "Yarımq."),
        pgettext(_CTX, "Mühazirə (plan/cəmi)"),
        pgettext(_CTX, "Seminar (plan/cəmi)"),
        pgettext(_CTX, "Laboratoriya (plan/cəmi)"),
        pgettext(_CTX, "Məsləhət"),
        pgettext(_CTX, "İmtahan"),
        pgettext(_CTX, "Buraxılış"),
        pgettext(_CTX, "Doktorant"),
        pgettext(_CTX, "Təcrübə"),
        pgettext(_CTX, "Cəmi"),
        pgettext(_CTX, "Kredit"),
        pgettext(_CTX, "Viza"),
    )


def _profile_url(params: dict) -> str:
    clean = {key: value for key, value in params.items() if value not in ("", None)}
    return f"{reverse('accounts:profile')}?{urlencode(clean)}"


def _row(row) -> dict:
    """`_data_table.html` müqaviləsi — bir tapşırıq sətri."""
    return {
        "row_head": row["season_label"],
        "cells": [
            {"text": row["groups"] or "—"},
            {"text": row["subject"]},
            {"text": row["specialty"] or "—"},
            {"text": row["education_form"]},
            {"text": row["degree_level"]},
            {"text": row["students"], "num": True},
            {"text": row["union_count"], "num": True},
            {"text": row["subgroup_count"], "num": True},
            {"text": f"{row['lecture_plan']} / {row['lecture_total']}", "num": True},
            {"text": f"{row['seminar_plan']} / {row['seminar_total']}", "num": True},
            {"text": f"{row['lab_plan']} / {row['lab_total']}", "num": True},
            {"text": row["consult_hours"], "num": True},
            {"text": row["exam_hours"], "num": True},
            {"text": row["thesis_hours"], "num": True},
            {"text": row["postgrad_hours"], "num": True},
            {"text": row["practice_hours"], "num": True},
            {"text": row["total_hours"], "num": True},
            {"text": row["credits"] or "—", "num": True},
            {"badge_family": "workload_visa", "badge_key": _visa_key(row["review_status"])},
        ],
        "data": row,
    }


def _visa_key(value: str) -> str:
    """DB kataloqu 4 dəyər saxlayır, dizayn palitrası 3 pill verir."""
    return {"flagged": "remarked", "returned": "remarked"}.get(value, value or "pending")


def build_workload_center_section(request, section, *, active_organization, allowed_sections, active_section):
    if "workload-center" not in allowed_sections or active_section != "workload-center":
        return
    if active_organization is None:
        section["has_access"] = False
        return

    from apps.workload.center_registry import build_center

    payload = build_center(request, active_organization)
    section.update(payload)
    if not payload.get("has_access"):
        section["access_denied_message"] = pgettext(
            _CTX, "Dərs yükü mərkəzinə giriş üçün «Tədris tapşırığını idarə etmək» səlahiyyəti tələb olunur."
        )
        return

    action_url = reverse("workload:action")
    section["action_url"] = action_url
    section["form_data"] = {"data-tof-form": "1", "data-tof-url": action_url}
    section["dialog_hidden"] = [{"name": "action"}, {"name": "task"}, {"name": "chair"}]
    section["reason_hidden"] = [{"name": "action"}, {"name": "task"}]

    base = {"section": "workload-center", "wc_year": payload["year"], "wc_view": payload["view"]}
    section["base_params"] = base
    section["view_tabs"] = [
        {
            "key": key,
            "label": label,
            "current": payload["view"] == key,
            "url": _profile_url({**base, "wc_view": key, "wc_chair": payload.get("chair_id", "")}),
        }
        for key, label in (
            ("dashboard", pgettext(_CTX, "İdarə paneli")),
            ("tasks", pgettext(_CTX, "Tapşırıqlar")),
            ("import", pgettext(_CTX, "Excel import")),
            ("reports", pgettext(_CTX, "Hesabatlar")),
            ("settings", pgettext(_CTX, "Parametrlər")),
        )
    ]
    section["inner_tabs"] = [
        {
            "key": key,
            "label": label,
            "current": payload["tab"] == key,
            "url": _profile_url({**base, "wc_view": "tasks", "wc_tab": key, "wc_chair": payload.get("chair_id", "")}),
        }
        for key, label in (
            ("editor", pgettext(_CTX, "Tapşırıq redaktoru")),
            ("tracking", pgettext(_CTX, "İzləmə")),
        )
    ]

    kpi = payload["kpi"]
    section["kpi_tiles"] = [
        {"label": pgettext(_CTX, "CƏMİ KAFEDRA"), "value": kpi["chairs"]},
        # Dizayn ekran 12: ağ kart + 4px rəngli sol kontur (tinted deyil).
        {"label": pgettext(_CTX, "GÖNDƏRİLMİŞ"), "value": kpi["submitted"], "tone": "accent-primary"},
        {"label": pgettext(_CTX, "TƏSDİQLƏNMİŞ"), "value": kpi["approved"], "tone": "accent-success"},
        {
            "label": pgettext(_CTX, "QAYTARILMIŞ"),
            "value": kpi["returned"],
            "tone": "accent-danger" if kpi["returned"] else None,
        },
    ]

    section["filter_fields"] = [
        {
            "name": "wc_year",
            "label": pgettext(_CTX, "Tədris ili"),
            "kind": "select",
            "value": payload["year"],
            "options": [{"value": year, "label": year} for year in payload["years"]]
            or [{"value": payload["year"], "label": payload["year"] or "—"}],
        },
        {
            "name": "wc_faculty",
            "label": pgettext(_CTX, "Fakültə"),
            "kind": "select",
            "value": payload["filters"]["faculty"],
            "options": [{"value": "", "label": pgettext(_CTX, "Hamısı")}] + payload["faculty_options"],
            "wide": True,
        },
        {
            "name": "wc_status",
            "label": pgettext(_CTX, "Status"),
            "kind": "select",
            "value": payload["filters"]["status"],
            "options": [{"value": "", "label": pgettext(_CTX, "Hamısı")}]
            + [
                {"value": "draft", "label": pgettext(_CTX, "Qaralama")},
                {"value": "submitted", "label": pgettext(_CTX, "Göndərilib")},
                {"value": "returned", "label": pgettext(_CTX, "Qaytarılıb")},
                {"value": "approved", "label": pgettext(_CTX, "Təsdiqlənib")},
                {"value": "distributed", "label": pgettext(_CTX, "Bölüşdürülüb")},
            ],
        },
    ]
    section["filter_count_label"] = pgettext(_CTX, "Nəticə: %(count)d kafedra") % {"count": len(payload["cards"])}

    for card in section["cards"]:
        card["open_url"] = _profile_url({**base, "wc_view": "tasks", "wc_tab": "editor", "wc_chair": card["chair_id"]})
        card["status_key"] = card["status"] or "none"

    section["columns"] = [{"key": "", "label": label, "sortable": False} for label in _row_columns()]
    section["table_rows"] = [_row(row) for row in payload.get("rows", [])]
    section["table_state"] = "ready" if section["table_rows"] else "empty"
    section["state_title"] = pgettext(_CTX, "Seçilmiş filtrlərə uyğun sətir tapılmadı")
    section["state_body"] = pgettext(_CTX, "«Sıfırla» ilə filtrləri təmizləyin və ya plandan sətir gətirin.")
    section["row_count_label"] = pgettext(_CTX, "Nəticə: %(count)d sətir") % {"count": payload.get("row_total", 0)}

    section["archive_key"] = "archived" if payload["is_archive"] else "open"
    section["can_edit_rows"] = bool(
        payload.get("task") and payload["task"]["is_office_editable"] and not payload["is_archive"]
    )
    section["slice_timeline"] = [
        {
            "who": item["faculty"],
            "when": item["decided_at"],
            "what": item["status"],
            "reason": item["comment"],
            "tone": {"approved": "success", "returned": "danger"}.get(item["status"], "primary"),
        }
        for item in payload.get("slices", [])
    ]
    section["page_urls"] = _pager(base, payload)
    section["import_steps_label"] = pgettext(_CTX, "Excel idxalının mərhələləri")
    has_preview = bool(payload.get("import_preview"))
    section["import_steps"] = [
        {
            "label": pgettext(_CTX, "Fayl yüklə"),
            "state": "done" if has_preview else "current",
        },
        {
            "label": pgettext(_CTX, "Uyğunlaşdırma"),
            "state": "current" if has_preview else "todo",
        },
        {"label": pgettext(_CTX, "Nəticə"), "state": "todo"},
    ]


def _pager(base, payload) -> list[dict]:
    """Server səhifələməsi — filtrləri saxlayan sadə linklər."""
    page_count = payload.get("page_count", 1)
    if page_count <= 1:
        return []
    params = {
        **base,
        "wc_view": "tasks",
        "wc_tab": "editor",
        "wc_chair": payload.get("chair_id", ""),
        "wc_sem": payload.get("row_filters", {}).get("season", ""),
        "wc_spec": payload.get("row_filters", {}).get("specialty", ""),
        "wc_form": payload.get("row_filters", {}).get("form", ""),
    }
    return [
        {
            "number": number,
            "url": _profile_url({**params, "wc_page": number}),
            "current": number == payload.get("page", 1),
        }
        for number in range(1, page_count + 1)
    ]


__all__ = ["build_workload_center_section"]
