"""Kabinet «Registrar (kataloq)» bölməsi — akademik kataloqun idarəetməsi.

Niyə bu bölmə var (sahib, 2026-09-09)
--------------------------------------
Sidebar-dakı «Registrar (kataloq)» keçidi `registrar:console` MÜSTƏQİL səhifəsinə
aparırdı: kabinet qabığı və sol sidebar itirdi. Sahibin tələbi — «yeni səhifəyə
atmamalıdı, sidebar solda qalıb sağda bu açmalıdı». İndi konsol kabinetin öz
bölməsidir (`?section=registrar-catalog`), yaratma/redaktə isə səhifə əvəzinə
DİALOQ-dadır.

İcazə və məntiq DƏYİŞMİR: hər ikisi `apps/registrar/catalog_console.py`-dədir
(org-wide `course.edit`, mövcud `forms.py` validasiyası, tenant süzgəci).

Tab-lar LAZY: yalnız seçilmiş tabın sətirləri hesablanır (`?rc_tab=`), qalanlar
üçün ancaq nişan rəqəmi (COUNT) alınır.
"""

from __future__ import annotations

from django.urls import reverse
from django.utils.translation import pgettext

from apps.registrar import catalog_console as console

_CTX = "registrar.catalog"
PREFIX = "rc_"
SECTION = "registrar-catalog"

TAB_LABELS = {
    "programs": "İxtisaslar",
    "subjects": "Fənlər",
    "curricula": "Tədris planları",
    "offerings": "Semestr açılışları",
    "rubrics": "Rubriklər",
    "students": "Tələbə təyinatları",
}

NEW_LABELS = {
    "programs": "Yeni ixtisas",
    "subjects": "Yeni fənn",
    "curricula": "Yeni tədris planı",
    "offerings": "Fənn aç",
    "rubrics": "Yeni rubrik",
    "students": "Tələbə təyin et",
}

EMPTY_ICONS = {
    "programs": "fa-graduation-cap",
    "subjects": "fa-book",
    "curricula": "fa-clipboard-list",
    "offerings": "fa-chalkboard",
    "rubrics": "fa-list-check",
    "students": "fa-user-graduate",
}


def _t(text: str) -> str:
    return pgettext(_CTX, text)


def _columns(tab):
    """Hər tabın sütunları — BİRİNCİ sütun sətir başlığı, SONUNCU əməllərdir.

    (Fakültə/kafedra reyestrlərində bu iki başlığın buraxılması başlıqların bir
    xana sürüşməsinə səbəb olmuşdu — həmin səhv burada təkrarlanmır.)
    """
    end = {"key": "actions", "label": _t("Əməl"), "align": "end"}
    if tab == "programs":
        return [
            {"key": "name", "label": _t("İxtisas")},
            {"key": "degree", "label": _t("Səviyyə")},
            {"key": "ects", "label": _t("ECTS"), "align": "num"},
            {"key": "absence", "label": _t("Qayıb limiti"), "align": "num"},
            end,
        ]
    if tab == "subjects":
        return [
            {"key": "name", "label": _t("Fənn")},
            {"key": "ects", "label": _t("ECTS"), "align": "num"},
            end,
        ]
    if tab == "curricula":
        return [
            {"key": "name", "label": _t("Tədris planı")},
            {"key": "rows", "label": _t("Fənn sətri"), "align": "num"},
            end,
        ]
    if tab == "offerings":
        return [
            {"key": "subject", "label": _t("Fənn")},
            {"key": "group", "label": _t("Qrup")},
            {"key": "instructor", "label": _t("Müəllim")},
            {"key": "hours", "label": _t("Saat"), "align": "num"},
            end,
        ]
    if tab == "rubrics":
        return [
            {"key": "name", "label": _t("Rubrik")},
            {"key": "criteria", "label": _t("Meyar"), "align": "num"},
            end,
        ]
    return [
        {"key": "student", "label": _t("Tələbə")},
        {"key": "program", "label": _t("İxtisas")},
        {"key": "group", "label": _t("Qrup")},
        {"key": "year", "label": _t("Qəbul ili"), "align": "num"},
        {"key": "status", "label": _t("Status")},
        end,
    ]


def _cells(tab, row):
    if tab == "programs":
        meta = row["meta"]
        return [
            {"text": meta[0], "muted": True},
            {"text": meta[1].replace(" ECTS", ""), "num": True},
            {"text": meta[2], "num": True},
        ]
    if tab == "subjects":
        return [{"text": row["meta"][0].replace(" ECTS", ""), "num": True}]
    if tab == "curricula":
        return [{"text": row["meta"][0], "num": True}]
    if tab == "offerings":
        return [
            {"text": row["group"] or "—", "muted": not row["group"]},
            {"text": row["instructor"] or _t("Təyin edilməyib"), "muted": not row["instructor"]},
            {"text": row["meta"][0], "num": True},
        ]
    if tab == "rubrics":
        return [{"text": row["meta"][0], "num": True}]
    return [
        {"text": row["program"], "muted": True},
        {"text": row["group"] or "—", "muted": not row["group"]},
        {"text": row["meta"][0], "num": True},
        {"text": row["status_label"]},
    ]


def _filter_fields(tab, params, organization):
    query = (params.get(PREFIX + "q") or "").strip()
    status = (params.get(PREFIX + "status") or "").strip()
    program = (params.get(PREFIX + "program") or "").strip()
    flag = (params.get(PREFIX + "flag") or "").strip()

    fields = [
        {
            "name": "q",
            "label": _t("Axtarış"),
            "kind": "search",
            "value": query,
            "wide": True,
            "placeholder": _t("Ad, kod və ya şifr"),
        }
    ]
    if tab in ("programs", "subjects", "curricula", "rubrics"):
        fields.append(
            {
                "name": "status",
                "label": _t("Vəziyyət"),
                "kind": "select",
                "value": status,
                "options": [
                    {"value": "", "label": _t("Hamısı")},
                    {"value": "active", "label": _t("Aktiv")},
                    {"value": "inactive", "label": _t("Deaktiv")},
                ],
            }
        )
    if tab in ("curricula", "students"):
        fields.append(
            {
                "name": "program",
                "label": _t("İxtisas"),
                "kind": "select",
                "searchable": True,
                "value": program,
                "options": [{"value": "", "label": _t("Bütün ixtisaslar")}] + console.program_options(organization),
            }
        )
    if tab == "offerings":
        fields.append(
            {
                "name": "flag",
                "label": _t("Müəllim"),
                "kind": "select",
                "value": flag,
                "options": [
                    {"value": "", "label": _t("Hamısı")},
                    {"value": "no_instructor", "label": _t("Müəllim təyin edilməyib")},
                    {"value": "with_instructor", "label": _t("Müəllimi var")},
                ],
            }
        )
    if tab == "students":
        fields.append(
            {
                "name": "status",
                "label": _t("Status"),
                "kind": "select",
                "searchable": True,
                "value": status,
                "options": [{"value": "", "label": _t("Bütün statuslar")}] + console.status_options(),
            }
        )
    return fields, {"q": query, "status": status, "program": program, "flag": flag}


def _kpi_tiles(stats, period):
    return [
        {"label": _t("İxtisas"), "value": stats["programs"], "tone": "accent-primary"},
        {"label": _t("Fənn"), "value": stats["subjects"]},
        {
            "label": _t("Tədris planı"),
            "value": stats["curricula"],
            "note": _t("%(n)s-i boşdur") % {"n": stats["empty_curricula"]} if stats["empty_curricula"] else None,
            "tone": "accent-warning" if stats["empty_curricula"] else None,
        },
        {
            "label": _t("Semestr açılışı"),
            "value": stats["offerings"],
            "note": period.name if period is not None else _t("aktiv semestr yoxdur"),
        },
        {
            "label": _t("Müəllimsiz açılış"),
            "value": stats["offerings_no_instructor"],
            "note": _t("jurnal sahibi yoxdur"),
            "tone": "accent-danger" if stats["offerings_no_instructor"] else None,
        },
    ]


def build_registrar_catalog_section(request, section, *, active_organization, allowed_sections, active_section):
    """`registrar-catalog` bölməsinin context-i (LAZY: yalnız aktiv tab)."""
    if SECTION not in allowed_sections or active_section != SECTION:
        return
    section["access_denied_message"] = _t(
        "Akademik kataloqu idarə etmək üçün icazəniz yoxdur — bu bölmə təşkilat üzrə "
        "`course.edit` açarı olan rollar üçündür."
    )
    has_access = console.can_manage(request.user, active_organization)
    section["has_access"] = has_access
    if not has_access:
        return

    params = request.GET
    tab = (params.get(PREFIX + "tab") or "programs").strip()
    if tab not in console.TAB_KEYS:
        tab = "programs"
    period = console.current_period(active_organization)

    stats = console.health(active_organization, period)
    tab_counts = console.counts(active_organization, period)
    fields, values = _filter_fields(tab, params, active_organization)
    rows = console.rows(
        active_organization,
        tab=tab,
        period=period,
        query=values["q"],
        status=values["status"],
        program=values["program"],
        flag=values["flag"],
    )

    section.update(
        {
            "tab": tab,
            "tab_param": PREFIX + "tab",
            "prefix": PREFIX,
            "action_url": reverse("accounts:registrar_catalog_action"),
            "header_subtitle": _t(
                "Akademik kataloq: ixtisaslar, fənlər, tədris planları, semestr açılışları, "
                "qiymətləndirmə rubrikləri və tələbə təyinatları. Hər əməl bu səhifədə, "
                "dialoqda aparılır — kabinetdən çıxmır."
            ),
            "header_note": period.name if period is not None else _t("Aktiv semestr yoxdur"),
            "kpi_tiles": _kpi_tiles(stats, period),
            "tabs_label": _t("Kataloq bölmələri"),
            "tabs": [
                {
                    "key": key,
                    "label": _t(TAB_LABELS[key]),
                    "count": tab_counts.get(key, 0),
                    "current": key == tab,
                    "url": f"{reverse('accounts:profile')}?section={SECTION}&{PREFIX}tab={key}",
                }
                for key in console.TAB_KEYS
            ],
            "filter_fields": fields,
            "filter_count_label": _t("Nəticə: %(n)s sətir") % {"n": len(rows)},
            "columns": _columns(tab),
            "table_rows": [
                {
                    "data": row,
                    "tab": tab,
                    "head_include": "accounts/profile/sections/registrar_catalog/_cell_name.html",
                    "cells": _cells(tab, row),
                    "actions_include": "accounts/profile/sections/registrar_catalog/_row_actions.html",
                }
                for row in rows
            ],
            "table_state": "ready" if rows else "empty",
            "state_icon": EMPTY_ICONS[tab],
            "state_title": _t("Bu siyahıda sətir yoxdur"),
            "state_body": _t("Süzgəci sıfırlayın və ya sağ yuxarıdakı düymə ilə yenisini əlavə edin."),
            "new_label": _t(NEW_LABELS[tab]),
            # «Tələbə təyinatları» tabı OXU-ONLY: tələbə seçicisi 7 800+ sətirdir və
            # client-side select onu daşımır. Yaratma/redaktə üçün ekran «Tələbə
            # reyestri» / «Tələbə qəbulu» bölmələrinə YÖNLƏNDİRİR (çarpaz keçid).
            "can_create": tab != "students" and (tab != "offerings" or period is not None),
            "readonly_tab": tab == "students",
            "readonly_note": _t(
                "Tələbə təyinatları burada YALNIZ oxunur. Yeni təyinat və köçürmə "
                "«Tələbə reyestri» bölməsindən aparılır — orada axtarışlı tələbə seçicisi var."
            ),
            "registry_url": f"{reverse('accounts:profile')}?section=student-registry",
            "dialog_title": _t(NEW_LABELS[tab]),
            "dialog_submit_label": _t("Yadda saxla"),
            "options": {
                "programs": console.program_options(active_organization),
                "subjects": console.subject_options(active_organization),
                "curricula": console.curriculum_options(active_organization),
                "periods": console.period_options(active_organization),
                "groups": console.group_options(active_organization),
                "instructors": console.instructor_options(active_organization) if tab == "offerings" else [],
                "statuses": console.status_options(),
                "degrees": console.degree_options(),
            },
        }
    )


__all__ = ["build_registrar_catalog_section"]
