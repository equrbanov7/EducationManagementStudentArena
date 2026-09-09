"""«Heyət idarəetməsi» bölməsi — kabinet context-i (2026-09-09 yenidən qurulub).

SAHİB TAPŞIRIĞI: ekran YALNIZ təşkilatın MÖVCUD ÜZVLƏRİNİ idarə edir. Dəvət və
müraciət səthləri — «təsdiq gözləyən tələbələr», «təşkilata bağlı olmayan
tələbə/müəllim/heyət», «göndərilmiş dəvətlər», «müəllim/heyət müraciətləri» —
BURADAN ÇIXARILDI (bu tenantda heç kim dəvətlə gəlmir; şəxsi təşkilat özü
«Tələbə əlavəsi» / «Müəllim əlavəsi» bölmələrindən əlavə edir).

⚠️ `StudentOrganizationRequest` modeli, tələbənin «Təşkilata qoşul» axını və
`student_organization_management` POST əməlləri (dəvət göndər/geri çək, müraciət
təsdiq/rədd) TOXUNULMAYIB — yalnız BU EKRANIN UI-ı və context-i sadələşdi.

Komponentlər `ems_ui`-dəndir (KPI · AVTO filtr · cədvəl · çekmecə · səbəb
dialoqu); sorğular `_members_registry.py`-dədir.
"""

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.urls import reverse
from django.utils.translation import pgettext

from ....models import ProfileRole
from ..constants import STUDENT_ORG_MANAGEMENT_MIN_LEVEL
from ..formatting import _append_query_params, _query_string
from . import _members_ui as ui
from ._members_registry import PAGE_SIZE, build_members_registry

User = get_user_model()

CELL_DIR = "accounts/profile/sections/staff_management/"
PAGE_PARAM = f"{ui.PREFIX}page"


def _empty_section(*, organization=None, is_superadmin=False, teacher_student_only=False):
    """Bütün açarların DEFOLT dəyəri — şablon heç bir halda sınmır."""
    return {
        "has_access": False,
        "access_denied_message": "",
        "organization": organization,
        "is_superadmin": is_superadmin,
        "teacher_student_only": teacher_student_only,
        "active_management_view": "members",
        "subtitle": "",
        "header_note": "",
        "kpi_tiles": [],
        "filter_fields": [],
        "filter_count_label": "",
        "columns": [],
        "table_rows": [],
        "table_state": "empty",
        "rows": [],
        "page_obj": None,
        "page_param": PAGE_PARAM,
        "pagination_query": "",
        "state_title": "",
        "state_body": "",
        "member_total_count": 0,
        "students_total_count": 0,
        "teacher_members_total_count": 0,
        "staff_members_total_count": 0,
        "leader_total_count": 0,
        "unit_scope_active": False,
        "can_manage_students": False,
        "can_remove_members": False,
        "action_url": reverse("accounts:student_organization_management"),
        "post_next_url": "",
        "remove_hidden": [],
        "organization_records": [],
        "organizations_page_param": "organization_page",
        "organizations_pagination_query": "",
        "organization_search_query": "",
        "organization_status_filter": "",
        "organization_type_filter": "",
        "pending_org_count": 0,
    }


def _table_rows(rows):
    return [
        {
            "row_head": row["name"],
            "head_include": f"{CELL_DIR}_cell_member.html",
            "cells": [
                {"include": f"{CELL_DIR}_cell_roles.html"},
                {"text": row["position"] or "—", "muted": not row["position"]},
                {"include": f"{CELL_DIR}_cell_unit.html"},
                {"text": row["joined"] or "—", "nowrap": True, "muted": not row["joined"]},
            ],
            "actions_include": f"{CELL_DIR}_row_actions.html",
            "data": row,
        }
        for row in rows
    ]


def _build_student_org_management_section(
    *,
    request,
    organization,
    is_superadmin,
    user_level,
    teacher_student_only=False,
    can_manage_students=True,
):
    # `default_view` və `can_invite_members` parametrləri 2026-09-09-da
    # SİLİNDİ: birincisi köhnə tab-larla (tələbə/müəllim/heyət) birlikdə,
    # ikincisi isə dəvət panelləri ilə birlikdə mənasını itirdi.
    section = _empty_section(
        organization=organization,
        is_superadmin=is_superadmin,
        teacher_student_only=teacher_student_only,
    )
    organization_search = (request.GET.get("organization_search") or "").strip()
    organization_status_filter = (request.GET.get("organization_status", "") or "").strip().lower()
    organization_type_filter = (request.GET.get("organization_type", "") or "").strip().lower()
    section["organization_search_query"] = organization_search
    section["organization_status_filter"] = organization_status_filter
    section["organization_type_filter"] = organization_type_filter

    if organization is None:
        if is_superadmin:
            # Aktiv təşkilatı olmayan superadmin: idarə ediləcək üzv yoxdur,
            # ona görə təşkilat siyahısı göstərilir (bölmə seçimi üçün).
            from ....services.org_management import build_superadmin_organizations_view

            section["active_management_view"] = "organizations"
            section["has_access"] = True
            section["subtitle"] = pgettext(
                ui.CTX,
                "Aktiv təşkilat seçilməyib. Heyəti idarə etmək üçün əvvəlcə təşkilatı seçin — "
                "aşağıdakı siyahıda sistemdəki bütün təşkilatlar var.",
            )
            section = build_superadmin_organizations_view(
                request=request,
                section=section,
                organization_search=organization_search,
                organization_status_filter=organization_status_filter,
                organization_type_filter=organization_type_filter,
            )
            section["organizations_pagination_query"] = _query_string(
                section="student-organization-management",
                organization_search=organization_search,
                organization_status=organization_status_filter,
                organization_type=organization_type_filter,
            )
            return section

        section["access_denied_message"] = pgettext(ui.CTX, "Aktiv təşkilat tapılmadı.")
        return section

    if not is_superadmin and not teacher_student_only and user_level < STUDENT_ORG_MANAGEMENT_MIN_LEVEL:
        section["access_denied_message"] = pgettext(
            ui.CTX, "Bu bölmə üçün minimum HR, təşkilat admini və ya daha yüksək səviyyə tələb olunur."
        )
        return section

    superadmin_user_ids = list(
        User.objects.filter(Q(is_superuser=True) | Q(profile__role=ProfileRole.SUPERADMIN)).values_list("id", flat=True)
    )
    registry = build_members_registry(
        request=request,
        organization=organization,
        is_superadmin=is_superadmin,
        actor_level=user_level,
        superadmin_user_ids=superadmin_user_ids,
        can_remove_members=bool(can_manage_students),
    )
    filters = registry["filters"]
    totals = registry["totals"]
    page_obj = registry["page_obj"]
    state_title, state_body = ui.empty_state(filtered=filters["is_filtered"], scope_active=registry["scope_active"])
    base_params = {
        "section": "student-organization-management",
        f"{ui.PREFIX}q": filters["search"],
        f"{ui.PREFIX}kind": filters["kind"],
        f"{ui.PREFIX}role": filters["role"],
        f"{ui.PREFIX}unit": filters["unit_id"],
        f"{ui.PREFIX}sort": filters["sort"] if filters["sort"] != ui.DEFAULT_SORT else "",
    }
    # Uzaqlaşdırma adi POST-dur (JSON deyil) — server `next` ilə eyni filtrli
    # görünüşə qaytarır, ona görə `next` gizli sahə kimi dialoqa yazılır.
    post_next_url = _append_query_params(reverse("accounts:profile"), **base_params)
    section.update(
        {
            "has_access": True,
            "active_management_view": "members",
            "subtitle": ui.subtitle(scope_active=registry["scope_active"]),
            "header_note": organization.name,
            "kpi_tiles": ui.kpi_tiles(totals=totals, kind=filters["kind"]),
            "filter_fields": ui.filter_fields(
                search=filters["search"],
                kind=filters["kind"],
                role=filters["role"],
                unit_id=filters["unit_id"],
                sort=filters["sort"],
                role_options=filters["role_options"],
                unit_options=filters["unit_options"],
            ),
            "filter_count_label": ui.count_label(page_obj.paginator.count),
            "columns": ui.columns(),
            "table_rows": _table_rows(registry["rows"]),
            "table_state": "ready" if registry["rows"] else "empty",
            "rows": registry["rows"],
            "page_obj": page_obj,
            "pagination_query": _query_string(**base_params),
            "state_title": state_title,
            "state_body": state_body,
            "member_total_count": totals["members"],
            "students_total_count": totals["students"],
            "teacher_members_total_count": totals["teachers"],
            "staff_members_total_count": totals["staff"],
            "leader_total_count": totals["leaders"],
            "unit_scope_active": registry["scope_active"],
            "can_manage_students": bool(can_manage_students),
            "can_remove_members": bool(can_manage_students),
            "page_size": PAGE_SIZE,
            "post_next_url": post_next_url,
            "remove_hidden": [
                {"name": "action", "value": "remove_org_member", "keep": True},
                {"name": "next", "value": post_next_url, "keep": True},
                {"name": "user_id", "value": ""},
            ],
        }
    )
    return section
