"""«Struktur üzvləri» — cari süzgəcin CSV ixracı (sahib 2026-10-01).

``GET /organizations/<slug>/members/export/?om_q=…&om_role=…`` — reyestrlə EYNİ
süzgəc (``read_filters`` + ``filter_memberships``) və EYNİ əhatə
(``resolve_members_access``): dekan yalnız öz alt-ağacını, əhatəsiz unit-rolu heç
nə ixrac edir. Qapı daha sərtdir — ``can_export_members`` (idarəetmə rolu və ya
``member.edit``; URL-dəki təşkilat aktiv olmalıdır). Naxış
``accounts/views/student_registry.py::student_registry_export`` ilə eynidir:
UTF-8 BOM, formula neytrallaşdırması (``safe_csv_writer``), tavan ``EXPORT_CAP``,
ixracın özü audit jurnalına yazılır («auditçini audit et»).
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import pgettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from core.constants import AuditAction
from core.export_safety import safe_csv_writer

from .models import Organization
from .services import create_audit_log
from .structure_views.members import (
    UnitIndex,
    can_export_members,
    filter_memberships,
    format_date,
    read_filters,
    resolve_members_access,
    role_label,
)
from .structure_views.registry import _display_name

_CTX = "organizations.members"

#: Bir ixracın sətir tavanı (tələbə reyestri ilə eyni tərtib).
EXPORT_CAP = 10000


def _header() -> list[str]:
    return [
        pgettext(_CTX, "Ad Soyad"),
        pgettext(_CTX, "İstifadəçi adı"),
        pgettext(_CTX, "E-poçt"),
        pgettext(_CTX, "Rol"),
        pgettext(_CTX, "Vəzifə"),
        pgettext(_CTX, "Tabel №"),
        pgettext(_CTX, "Bölmə"),
        pgettext(_CTX, "Üst bölmə"),
        pgettext(_CTX, "Hesab"),
        pgettext(_CTX, "Qoşulma"),
    ]


def _row(membership, index) -> list:
    user = membership.user
    unit = membership.scope_unit
    trail = " · ".join(index.trail(unit.id)) if unit is not None else ""
    return [
        _display_name(user),
        user.username,
        user.email or "",
        role_label(membership.role),
        membership.title or "",
        membership.employee_id or "",
        unit.name if unit is not None else pgettext(_CTX, "Bütün təşkilat"),
        trail,
        pgettext(_CTX, "Aktiv") if user.is_active else pgettext(_CTX, "Dayandırılıb"),
        format_date(membership.created_at),
    ]


@never_cache
@login_required
@require_GET
def members_export(request, slug):
    organization = get_object_or_404(Organization, slug=slug, is_active=True)
    access = resolve_members_access(request, organization)
    if not access.has_access or not can_export_members(request, organization):
        return JsonResponse(
            {"ok": False, "error": "permission_denied", "message": pgettext(_CTX, "İxrac üçün icazəniz yoxdur.")},
            status=403,
        )

    filters = read_filters(request)
    visible_ids = None if access.is_org_wide else set(access.units.order_by().values_list("id", flat=True))
    index = UnitIndex(organization, visible_ids)
    queryset, unit_id = filter_memberships(access.memberships, access, filters, set(index.heads))
    memberships = list(queryset[: EXPORT_CAP + 1])
    truncated = len(memberships) > EXPORT_CAP
    memberships = memberships[:EXPORT_CAP]

    create_audit_log(
        request.user,
        organization,
        AuditAction.EXPORT,
        resource_type="organizations.members",
        resource_repr="CSV",
        new_values={
            "filters": {**{k: v for k, v in filters.items() if v and k != "unit_id"}, "unit": unit_id},
            "rows": len(memberships),
            "truncated": truncated,
        },
        reason=pgettext(_CTX, "Üzv reyestri CSV ixracı: %(n)d sətir") % {"n": len(memberships)},
        request=request,
    )

    filename = "uzvler-%s-%s.csv" % (organization.slug, timezone.localdate().isoformat())
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="%s"' % filename
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    response["X-Export-Rows"] = str(len(memberships))
    response["X-Export-Truncated"] = "1" if truncated else "0"
    response.write("﻿")  # BOM — Excel AZ hərflərini düzgün açsın
    writer = safe_csv_writer(response)
    writer.writerow(_header())
    for membership in memberships:
        writer.writerow(_row(membership, index))
    return response


__all__ = ["EXPORT_CAP", "members_export"]
