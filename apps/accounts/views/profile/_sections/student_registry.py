"""Ekran 09 «Tələbə reyestri və hərəkəti» — bölmə context-i (GLUE qatı).

Bütün məntiq servislərdədir:

* oxu  → ``apps.accounts.services.people.registry``
* yazı → ``apps.accounts.services.people.movements`` (JSON endpoint-i ayrıdır)

Burada yalnız context-in ``ems_ui`` komponent müqavilələrinə (KPI sırası,
filtr paneli, cədvəl, çekmecə, səbəb dialoqu) uyğun forması var.

FİLTR SEMANTİKASI (handoff §8/14): `applied` state URL sorğu parametrləridir
(`sr_` prefiksi); draft dəyər sorğu göndərmir. Sıralama və səhifələmə də
SERVER tərəfdədir — sütun başlığı adi linkdir.
"""

from __future__ import annotations

from urllib.parse import urlencode

from django.urls import reverse
from django.utils.translation import pgettext

from apps.accounts.services import people
from apps.accounts.services.people import movements as movement_service
from apps.accounts.services.people import registry as registry_service

_CTX = "accounts.student_registry"


def _sort_url(base_params: dict, *, key: str, current: str) -> str:
    params = dict(base_params)
    params["sr_sort"] = f"-{key}" if current == key else key
    query = urlencode({name: value for name, value in params.items() if value not in ("", None)})
    return f"{reverse('accounts:profile')}?{query}"


def _sort_dir(current: str, key: str):
    if current == key:
        return "ascending"
    if current == f"-{key}":
        return "descending"
    return None


def _columns(base_params, current, *, can_move):
    specs = [
        ("name", pgettext(_CTX, "Tələbə")),
        ("program", pgettext(_CTX, "İxtisas və qrup")),
        ("", pgettext(_CTX, "Kurs")),
        ("", pgettext(_CTX, "Forma")),
        ("", pgettext(_CTX, "Təhsil haqqı")),
        ("year", pgettext(_CTX, "Qəbul ili")),
        ("status", pgettext(_CTX, "Statusu")),
        ("", pgettext(_CTX, "Əmr")),
    ]
    if can_move:
        specs.append(("", pgettext(_CTX, "Əməllər")))
    return [
        {
            "key": key,
            "label": label,
            "sortable": bool(key),
            "sort_url": _sort_url(base_params, key=key, current=current) if key else "",
            "sort_dir": _sort_dir(current, key) if key else None,
        }
        for key, label in specs
    ]


def _table_row(row, *, can_move):
    """`_data_table.html` müqaviləsi — birinci sütun `th scope="row"`."""
    return {
        "row_head": row["student_code"] or "—",
        "cells": [
            {"text": row["name"]},
            {"text": " · ".join(part for part in (row["program_label"], row["group_name"]) if part) or "—"},
            {"text": row["course_label"] or "—"},
            {"text": row["form_label"]},
            {"text": row["funding_label"]},
            {"text": row["admission_year"], "num": True},
            {"badge_family": "student_status", "badge_key": row["status"]},
            {"text": row["movement_count"], "num": True},
        ],
        "actions_include": ("accounts/profile/sections/student_services/_registry_actions.html" if can_move else ""),
        "data": row,
    }


def build_student_registry_section(request, section, *, active_organization, allowed_sections, active_section):
    """«Tələbə reyestri» bölməsi (yerində mutasiya)."""
    if "student-registry" not in allowed_sections or active_section != "student-registry":
        return
    if active_organization is None:
        section["has_access"] = False
        return

    actor = people.resolve_actor(request)
    values = registry_service.parse_registry_filters(request)
    payload = registry_service.build_registry_page(actor=actor, request=request, values=values)
    section.update(payload)
    if not payload.get("has_access"):
        section["access_denied_message"] = pgettext(
            _CTX, "Tələbə reyestrinə baxış üçün icazəniz yoxdur — administratorla əlaqə saxlayın."
        )
        return

    can_move = bool(actor.can_move_students and actor.can_manage_academic)
    section["can_move"] = can_move
    section["options"] = registry_service.registry_options(actor, request=request)
    section["movement_kinds"] = movement_service.movement_kinds()

    base_params = {
        "section": "student-registry",
        "sr_q": values["search"],
        "sr_faculty": values["faculty"],
        "sr_program": values["program"],
        "sr_group": values["group"],
        "sr_year": values["year"],
        "sr_sector": values["sector"],
        "sr_form": values["form"],
        "sr_funding": values["funding"],
        "sr_status": values["status"],
    }
    section["base_params"] = base_params
    section["columns"] = _columns(base_params, values["sort"], can_move=can_move)
    section["table_rows"] = [_table_row(row, can_move=can_move) for row in payload["rows"]]
    section["table_state"] = "ready" if payload["rows"] else "empty"
    section["pagination_query"] = urlencode(
        {key: value for key, value in base_params.items() if value not in ("", None)}
    )
    section["card_url_base"] = reverse("accounts:student_registry_card", args=["00000000-0000-0000-0000-000000000000"])
    section["action_url"] = reverse("accounts:student_registry_action")
    section["export_url"] = "%s?%s" % (
        reverse("accounts:student_registry_export"),
        section["pagination_query"],
    )
    section["programs_url"] = reverse("accounts:student_registry_programs")
    section["groups_url"] = reverse("accounts:people_academic_groups")
    section["document_url_base"] = reverse(
        "accounts:student_registry_document", args=["00000000-0000-0000-0000-000000000000"]
    )

    kpis = payload["kpis"]
    section["kpi_tiles"] = [
        {"label": pgettext(_CTX, "CƏMİ TƏLƏBƏ"), "value": kpis.get("total", 0)},
        {"label": pgettext(_CTX, "ƏYANİ"), "value": kpis.get("full_time", 0)},
        {"label": pgettext(_CTX, "QİYABİ"), "value": kpis.get("part_time", 0)},
        {
            "label": pgettext(_CTX, "XÜSUSİ STATUSLU"),
            "value": kpis.get("special", 0),
            "tone": "warning" if kpis.get("special") else None,
            "note": pgettext(_CTX, "Məzuniyyət / xaric / məzun"),
        },
        {"label": pgettext(_CTX, "DÖVLƏT SİFARİŞİ"), "value": kpis.get("state_funded", 0)},
    ]
    section["form_options"] = _form_options()
    # Gizli sahələr: DƏYƏRLƏR sətirdən (JS `data-tof-prefill` naxışı ilə),
    # ADLAR isə yalnız serverdən — şablona xam GET dəyəri düşmür.
    section["movement_hidden"] = [{"name": "record_id"}]
    # Form atributları YALNIZ serverdən gəlir (şablon müqaviləsi) — JS həmin
    # seçici ilə formu tapır və `FormData` kimi (multipart: sənəd faylı) göndərir.
    section["movement_form_data"] = {"data-sr-form": "1", "data-sr-url": section["action_url"]}
    if payload.get("has_scope"):
        section["state_title"] = pgettext(_CTX, "Filtrə uyğun tələbə yoxdur")
        section["state_body"] = pgettext(_CTX, "Süzgəcləri dəyişin və ya axtarış sözünü qısaldın.")
    else:
        # §8/8 — əhatəsiz istifadəçiyə data QAYTARILMIR; boş vəziyyət + kanal.
        section["state_title"] = pgettext(_CTX, "Sizə təyin olunmuş əhatə yoxdur")
        section["state_body"] = pgettext(
            _CTX,
            "Rolunuzda struktur əhatəsi (fakültə/ixtisas) təyin edilməyib — "
            "administratorla əlaqə saxlayın. Əhatəsiz rol bütün universiteti görmür.",
        )
    section["filter_fields"] = _filter_fields(values, section["options"])
    section["filter_count_label"] = pgettext(_CTX, "Nəticə: %(count)d sətir") % {"count": payload["total"]}


def _filter_fields(values, options) -> list:
    everything = [{"value": "", "label": pgettext(_CTX, "Hamısı")}]
    return [
        {
            "name": "sr_q",
            "label": pgettext(_CTX, "Axtarış"),
            "kind": "search",
            "value": values["search"],
            "placeholder": pgettext(_CTX, "Ad, FİN və ya tələbə kodu"),
            "wide": True,
        },
        {
            "name": "sr_faculty",
            "label": pgettext(_CTX, "Fakültə"),
            "kind": "select",
            "value": values["faculty"],
            "options": everything + options["faculties"],
        },
        {
            "name": "sr_program",
            "label": pgettext(_CTX, "İxtisas"),
            "kind": "select",
            "value": values["program"],
            "options": everything + options["programs"],
        },
        {
            "name": "sr_group",
            "label": pgettext(_CTX, "Qrup"),
            "kind": "select",
            "value": values["group"],
            "options": everything + options["groups"],
        },
        {
            "name": "sr_year",
            "label": pgettext(_CTX, "Qəbul ili"),
            "kind": "select",
            "value": values["year"],
            "options": everything + options["years"],
        },
        {
            "name": "sr_sector",
            "label": pgettext(_CTX, "Dil bölməsi"),
            "kind": "select",
            "value": values["sector"],
            "options": everything + options["sectors"],
        },
        {
            "name": "sr_form",
            "label": pgettext(_CTX, "Təhsil forması"),
            "kind": "select",
            "value": values["form"],
            "options": everything + _form_options(),
        },
        {
            "name": "sr_funding",
            "label": pgettext(_CTX, "Təhsil haqqı"),
            "kind": "select",
            "value": values["funding"],
            "options": everything + _funding_options(),
        },
        {
            "name": "sr_status",
            "label": pgettext(_CTX, "Status"),
            "kind": "select",
            "value": values["status"],
            "options": everything + _status_options(),
        },
    ]


def _form_options() -> list:
    from apps.registrar.models.catalog_meta import EducationForm

    return [{"value": key, "label": str(label)} for key, label in EducationForm.choices]


def _funding_options() -> list:
    from apps.registrar.models import FundingType

    return [{"value": key, "label": str(label)} for key, label in FundingType.choices]


def _status_options() -> list:
    from apps.accounts.services.people.academic import STATUS_LABELS

    return [{"value": key, "label": str(label)} for key, label in STATUS_LABELS.items()]


__all__ = ["build_student_registry_section"]
