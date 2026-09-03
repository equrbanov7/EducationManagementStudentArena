"""Ekran 13 «Yük vizası» · 15 «Yük təsdiqi» · 17 «Ümumi baxış» — GLUE qatı.

Məntiq ``apps.workload.{review,approval,overview}_registry``-dədir; burada
YALNIZ `ems_ui` müqavilələrinə (KPI, filtr, cədvəl, tab, timeline) uyğunlaşma
var.

⚠️ Ekran 17-də SƏTİR SƏVİYYƏSİNDƏ REDAKTƏ YOXDUR — heç bir əməl düyməsi
render olunmur (handoff «sətir səviyyəsində redaktə YOXDUR»).
"""

from __future__ import annotations

from urllib.parse import urlencode

from django.urls import reverse
from django.utils.translation import pgettext

_CTX_VISA = "accounts.workload_visa"
_CTX_APPROVAL = "accounts.workload_approval"
_CTX_OVERVIEW = "accounts.workload_overview"


def _profile_url(params: dict) -> str:
    clean = {key: value for key, value in params.items() if value not in ("", None)}
    return f"{reverse('accounts:profile')}?{urlencode(clean)}"


def _visa_key(value: str) -> str:
    return {"flagged": "remarked", "returned": "remarked"}.get(value, value or "pending")


def _year_field(name: str, label: str, value: str, years) -> dict:
    return {
        "name": name,
        "label": label,
        "kind": "select",
        "value": value,
        "options": [{"value": year, "label": year} for year in years] or [{"value": value, "label": value or "—"}],
    }


def _season_field(name: str, label: str, value: str, context: str) -> dict:
    return {
        "name": name,
        "label": label,
        "kind": "select",
        "value": value,
        "options": [
            {"value": "", "label": pgettext(context, "Hamısı")},
            {"value": "fall", "label": pgettext(context, "Payız")},
            {"value": "spring", "label": pgettext(context, "Yaz")},
            {"value": "summer", "label": pgettext(context, "Yay")},
        ],
    }


# --------------------------------------------------------------------------- #
# 13 · Koordinator — Yük vizası
# --------------------------------------------------------------------------- #


def build_workload_visa_section(request, section, *, active_organization, allowed_sections, active_section):
    if "workload-visa" not in allowed_sections or active_section != "workload-visa":
        return
    if active_organization is None:
        section["has_access"] = False
        return

    from apps.workload.review_registry import build_visa

    payload = build_visa(request, active_organization)
    section.update(payload)
    if not payload.get("has_access"):
        section["access_denied_message"] = pgettext(
            _CTX_VISA, "Viza vermək üçün «Tapşırıq sətirlərinə viza vermək» səlahiyyəti tələb olunur."
        )
        return

    action_url = reverse("workload:action")
    section["action_url"] = action_url
    section["form_data"] = {"data-tof-form": "1", "data-tof-url": action_url}
    section["reason_hidden"] = [{"name": "action"}, {"name": "row"}, {"name": "state"}]

    base = {"section": "workload-visa", "wv_year": payload["year"]}
    section["base_params"] = base
    section["view_tabs"] = [
        {
            "key": key,
            "label": label,
            "current": payload["view"] == key,
            "url": _profile_url({**base, "wv_view": key}),
        }
        for key, label in (
            ("queue", pgettext(_CTX_VISA, "Viza növbəsi")),
            ("history", pgettext(_CTX_VISA, "Mənim hərəkətlərim")),
        )
    ]

    counts = payload["counts"]
    section["kpi_tiles"] = [
        {"label": pgettext(_CTX_VISA, "SƏTİR"), "value": counts["total"]},
        {"label": pgettext(_CTX_VISA, "BAXILIB"), "value": counts["reviewed"], "tone": "success"},
        {
            "label": pgettext(_CTX_VISA, "İRADLI"),
            "value": counts["flagged"],
            "tone": "warning" if counts["flagged"] else None,
        },
        {
            "label": pgettext(_CTX_VISA, "GÖZLƏYİR"),
            "value": counts["pending"],
            "note": pgettext(_CTX_VISA, "%(pct)d%% baxılıb") % {"pct": counts["percent"]},
            "has_bar": True,
            "pct": counts["percent"],
        },
    ]

    section["filter_fields"] = [
        _year_field("wv_year", pgettext(_CTX_VISA, "Tədris ili"), payload["year"], payload["years"]),
        _season_field("wv_sem", pgettext(_CTX_VISA, "Semestr"), payload["filters"]["season"], _CTX_VISA),
        {
            "name": "wv_state",
            "label": pgettext(_CTX_VISA, "Viza"),
            "kind": "select",
            "value": payload["filters"]["state"],
            "options": [
                {"value": "", "label": pgettext(_CTX_VISA, "Hamısı")},
                {"value": "pending", "label": pgettext(_CTX_VISA, "Gözləyir")},
                {"value": "reviewed", "label": pgettext(_CTX_VISA, "Baxılıb")},
                {"value": "flagged", "label": pgettext(_CTX_VISA, "İradlı")},
            ],
        },
        {
            "name": "wv_q",
            "label": pgettext(_CTX_VISA, "Axtarış"),
            "kind": "search",
            "value": payload["filters"]["search"],
            "placeholder": pgettext(_CTX_VISA, "Fənn və ya qrup"),
        },
    ]
    section["filter_count_label"] = pgettext(_CTX_VISA, "Nəticə: %(count)d sətir") % {"count": payload["row_total"]}

    columns = [
        pgettext(_CTX_VISA, "Fənn"),
        pgettext(_CTX_VISA, "Qruplar"),
        pgettext(_CTX_VISA, "Semestr"),
        pgettext(_CTX_VISA, "Səviyyə"),
        pgettext(_CTX_VISA, "Saat"),
        pgettext(_CTX_VISA, "Kredit"),
        pgettext(_CTX_VISA, "Viza"),
    ]
    if payload["can_write"]:
        columns.append(pgettext(_CTX_VISA, "Əməllər"))
    section["columns"] = [{"key": "", "label": label, "sortable": False} for label in columns]
    section["table_rows"] = [
        {
            "row_head": row["subject"],
            "cells": [
                {"text": row["groups"] or "—"},
                {"text": row["season_label"]},
                {"text": row["degree_level"]},
                {"text": row["total_hours"], "num": True},
                {"text": row["credits"] or "—", "num": True},
                {"badge_family": "workload_visa", "badge_key": _visa_key(row["review_status"])},
            ],
            "actions_include": (
                "accounts/profile/sections/workload/_visa_row_actions.html" if payload["can_write"] else ""
            ),
            "data": row,
        }
        for row in payload["rows"]
    ]
    section["table_state"] = "ready" if section["table_rows"] else "empty"
    section["state_title"] = pgettext(_CTX_VISA, "Seçilmiş filtrlərə uyğun sətir tapılmadı")
    section["state_body"] = (
        pgettext(_CTX_VISA, "Sizin ixtisasınıza aid göndərilmiş tapşırıq sətri yoxdur.")
        if payload["has_scope"]
        else pgettext(
            _CTX_VISA,
            "Üzvlüyünüzdə ixtisas əhatəsi təyin edilməyib — administrator ilə əlaqə saxlayın.",
        )
    )
    section["archive_key"] = "archived" if payload["is_archive"] else "open"


# --------------------------------------------------------------------------- #
# 15 · Dekanlıq — Yük təsdiqi
# --------------------------------------------------------------------------- #


def build_workload_approval_section(request, section, *, active_organization, allowed_sections, active_section):
    if "workload-approval" not in allowed_sections or active_section != "workload-approval":
        return
    if active_organization is None:
        section["has_access"] = False
        return

    from apps.workload.approval_registry import build_approval

    payload = build_approval(request, active_organization)
    section.update(payload)
    if not payload.get("has_access"):
        section["access_denied_message"] = pgettext(
            _CTX_APPROVAL, "Yük təsdiqi üçün «Tapşırığı təsdiqləmək» səlahiyyəti tələb olunur."
        )
        return

    action_url = reverse("workload:action")
    section["action_url"] = action_url
    section["form_data"] = {"data-tof-form": "1", "data-tof-url": action_url}
    section["reason_hidden"] = [{"name": "action"}, {"name": "slice"}]

    base = {"section": "workload-approval", "wa_year": payload["year"], "wa_faculty": payload["faculty_id"]}
    section["base_params"] = base
    section["view_tabs"] = [
        {
            "key": key,
            "label": label,
            "current": payload["view"] == key,
            "count": payload["pending_count"] if key == "queue" else 0,
            "url": _profile_url({**base, "wa_view": key}),
        }
        for key, label in (
            ("queue", pgettext(_CTX_APPROVAL, "Təsdiq növbəsi")),
            ("summary", pgettext(_CTX_APPROVAL, "Fakültə yükü")),
            ("history", pgettext(_CTX_APPROVAL, "Tarixçə")),
        )
    ]

    kpi = payload["kpi"]
    section["kpi_tiles"] = [
        {"label": pgettext(_CTX_APPROVAL, "DİLİMİN CƏMİ SAATI"), "value": kpi["hours"], "unit": "saat"},
        {"label": pgettext(_CTX_APPROVAL, "CƏMİ KREDİT"), "value": kpi["credits"]},
        {"label": pgettext(_CTX_APPROVAL, "İXTİSAS SAYI"), "value": kpi["specialties"]},
        {
            "label": pgettext(_CTX_APPROVAL, "İRADLI SƏTİR"),
            "value": kpi["flagged"],
            # Dizayn ekran 15: rəngli sol kontur variantı.
            "tone": "accent-warning" if kpi["flagged"] else None,
        },
    ]

    section["filter_fields"] = [
        _year_field("wa_year", pgettext(_CTX_APPROVAL, "Tədris ili"), payload["year"], payload["years"]),
        {
            "name": "wa_faculty",
            "label": pgettext(_CTX_APPROVAL, "Fakültə"),
            "kind": "select",
            "value": payload["faculty_id"],
            "options": payload["faculty_options"],
            "wide": True,
        },
        _season_field("wa_sem", pgettext(_CTX_APPROVAL, "Semestr"), payload["filters"]["season"], _CTX_APPROVAL),
        {
            "name": "wa_visa",
            "label": pgettext(_CTX_APPROVAL, "Viza"),
            "kind": "select",
            "value": payload["filters"]["visa"],
            "options": [
                {"value": "", "label": pgettext(_CTX_APPROVAL, "Hamısı")},
                {"value": "pending", "label": pgettext(_CTX_APPROVAL, "Gözləyir")},
                {"value": "reviewed", "label": pgettext(_CTX_APPROVAL, "Baxılıb")},
                {"value": "flagged", "label": pgettext(_CTX_APPROVAL, "İradlı")},
            ],
        },
    ]
    section["filter_count_label"] = pgettext(_CTX_APPROVAL, "Nəticə: %(count)d sətir") % {"count": payload["row_total"]}

    columns = [
        pgettext(_CTX_APPROVAL, "Fənn"),
        pgettext(_CTX_APPROVAL, "İxtisas"),
        pgettext(_CTX_APPROVAL, "Qruplar"),
        pgettext(_CTX_APPROVAL, "Semestr"),
        pgettext(_CTX_APPROVAL, "Saat"),
        pgettext(_CTX_APPROVAL, "Koordinator vizası"),
    ]
    can_decide = bool(payload.get("slice") and payload["slice"]["is_open"] and payload["can_write"])
    if can_decide:
        columns.append(pgettext(_CTX_APPROVAL, "Seç"))
    section["can_decide"] = can_decide
    section["columns"] = [{"key": "", "label": label, "sortable": False} for label in columns]
    section["table_rows"] = [
        {
            "row_head": row["subject"],
            "cells": [
                {"text": row["specialty"] or "—"},
                {"text": row["groups"] or "—"},
                {"text": row["season_label"]},
                {"text": row["total_hours"], "num": True},
                {"badge_family": "workload_visa", "badge_key": _visa_key(row["review_status"])},
            ],
            "actions_include": ("accounts/profile/sections/workload/_approval_row_actions.html" if can_decide else ""),
            "data": row,
        }
        for row in payload["rows"]
    ]
    section["table_state"] = "ready" if section["table_rows"] else "empty"
    section["state_title"] = pgettext(_CTX_APPROVAL, "Dilimdə sətir yoxdur")
    section["state_body"] = pgettext(_CTX_APPROVAL, "Bu fakültə üçün göndərilmiş tapşırıq sətri tapılmadı.")
    section["archive_key"] = "archived" if payload["is_archive"] else "open"
    section["timeline"] = [
        {
            "who": item["who"],
            "when": item["when"],
            "what": item["what"],
            "reason": item["reason"],
            "tone": "success" if item["status"] == "approved" else "danger",
        }
        for item in payload.get("history", [])
    ]


# --------------------------------------------------------------------------- #
# 17 · Rektor — Ümumi baxış
# --------------------------------------------------------------------------- #


def build_workload_overview_section(request, section, *, active_organization, allowed_sections, active_section):
    if "workload-overview" not in allowed_sections or active_section != "workload-overview":
        return
    if active_organization is None:
        section["has_access"] = False
        return

    from apps.workload.overview_registry import build_overview_section

    payload = build_overview_section(request, active_organization)
    section.update(payload)
    if not payload.get("has_access"):
        section["access_denied_message"] = pgettext(
            _CTX_OVERVIEW, "Ümumi baxış üçün «Dərs yükü hesabatları» səlahiyyəti tələb olunur."
        )
        return

    totals = payload["totals"]
    base = {"section": "workload-overview", "wo_year": payload["year"]}
    section["base_params"] = base
    section["view_tabs"] = [
        {
            "key": key,
            "label": label,
            "current": payload["view"] == key,
            "url": _profile_url({**base, "wo_view": key}),
        }
        for key, label in (
            ("overview", pgettext(_CTX_OVERVIEW, "Ümumi baxış")),
            ("fac", pgettext(_CTX_OVERVIEW, "Fakültələr")),
            ("dep", pgettext(_CTX_OVERVIEW, "Kafedralar")),
            ("rep", pgettext(_CTX_OVERVIEW, "Hesabatlar")),
        )
    ]
    section["kpi_tiles"] = [
        {
            "label": pgettext(_CTX_OVERVIEW, "ÜMUMİ TƏDRİS YÜKÜ"),
            "value": totals["planned_hours"],
            "unit": "saat",
            "note": pgettext(_CTX_OVERVIEW, "%(fac)d fakültə · %(chair)d kafedra · %(teacher)d müəllim")
            % {"fac": totals["faculties"], "chair": totals["chairs"], "teacher": totals["teachers"]},
        },
        {
            "label": pgettext(_CTX_OVERVIEW, "BÖLÜNMÜŞ YÜK"),
            "value": totals["assigned_hours"],
            "unit": "saat",
            "has_bar": True,
            "pct": min(totals["percent"], 100),
            "note": pgettext(_CTX_OVERVIEW, "%(pct)d%% bölünüb") % {"pct": totals["percent"]},
        },
        {
            "label": pgettext(_CTX_OVERVIEW, "VAKANT SAAT"),
            "value": totals["vacant_hours"],
            "unit": "saat",
            "tone": "warning" if totals["vacant_hours"] else None,
        },
        {
            "label": pgettext(_CTX_OVERVIEW, "NORMA AŞIMI"),
            "value": totals["over_norm"],
            "note": pgettext(_CTX_OVERVIEW, "müəllim sayı"),
            "tone": "danger" if totals["over_norm"] else None,
        },
    ]
    section["filter_fields"] = [
        _year_field("wo_year", pgettext(_CTX_OVERVIEW, "Tədris ili"), payload["year"], payload["years"]),
        {
            "name": "wo_faculty",
            "label": pgettext(_CTX_OVERVIEW, "Fakültə"),
            "kind": "select",
            "value": payload["faculty_id"],
            "options": [{"value": "", "label": pgettext(_CTX_OVERVIEW, "Hamısı")}] + payload["faculty_options"],
            "wide": True,
        },
    ]
    section["filter_count_label"] = pgettext(_CTX_OVERVIEW, "Nəticə: %(count)d kafedra") % {
        "count": len(payload["chairs"])
    }

    section["faculty_columns"] = [
        {"key": "", "label": label, "sortable": False}
        for label in (
            pgettext(_CTX_OVERVIEW, "Fakültə"),
            pgettext(_CTX_OVERVIEW, "Kafedra"),
            pgettext(_CTX_OVERVIEW, "Müəllim"),
            pgettext(_CTX_OVERVIEW, "Tapşırıq"),
            pgettext(_CTX_OVERVIEW, "Bölünmüş"),
            pgettext(_CTX_OVERVIEW, "Gediş"),
            pgettext(_CTX_OVERVIEW, "Vakant"),
            pgettext(_CTX_OVERVIEW, "Status"),
        )
    ]
    section["faculty_rows"] = [
        {
            "row_head": row["name"],
            "cells": [
                {"text": row["chairs"], "num": True},
                {"text": row["teachers"], "num": True},
                {"text": row["planned_hours"], "num": True},
                {"text": row["assigned_hours"], "num": True},
                {"text": f"{row['percent']}%", "num": True},
                {"text": row["vacant_hours"], "num": True},
                {"badge_family": "load_band", "badge_key": row["band"]},
            ],
            "data": row,
        }
        for row in payload["faculties"]
    ]
    section["chair_columns"] = [
        {"key": "", "label": label, "sortable": False}
        for label in (
            pgettext(_CTX_OVERVIEW, "Kafedra"),
            pgettext(_CTX_OVERVIEW, "Fakültə"),
            pgettext(_CTX_OVERVIEW, "Müəllim"),
            pgettext(_CTX_OVERVIEW, "Tapşırıq"),
            pgettext(_CTX_OVERVIEW, "Bölgü"),
            pgettext(_CTX_OVERVIEW, "Vakant"),
            pgettext(_CTX_OVERVIEW, "Norma üstü"),
            pgettext(_CTX_OVERVIEW, "Status"),
        )
    ]
    section["chair_rows"] = [
        {
            "row_head": row["name"],
            "cells": [
                {"text": row["faculty_name"] or "—"},
                {"text": row["teachers"], "num": True},
                {"text": row["planned_hours"], "num": True},
                {"text": f"{row['assigned_hours']} ({row['percent']}%)", "num": True},
                {"text": row["vacant_hours"], "num": True},
                {"text": row["over_norm"], "num": True},
                {"badge_family": "workload_task", "badge_key": row["status"] or "none"},
            ],
            "data": row,
        }
        for row in payload["chairs"]
    ]
    section["table_state"] = "ready" if payload["chairs"] else "empty"
    section["state_title"] = pgettext(_CTX_OVERVIEW, "Bu tədris ili üçün tapşırıq yoxdur")
    section["state_body"] = pgettext(
        _CTX_OVERVIEW, "Tədris şöbəsi tapşırıqları yaradandan sonra rəqəmlər burada görünəcək."
    )


__all__ = [
    "build_workload_approval_section",
    "build_workload_overview_section",
    "build_workload_visa_section",
]
