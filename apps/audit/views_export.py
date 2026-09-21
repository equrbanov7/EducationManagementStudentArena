"""Audit jurnalı — cari filtrin CSV ixracı (``audit_log_export``).

``apps/audit/views.py``-dan ayrılıb (modul-ölçü qapısı, 2026-09-21); ``views.py``
görünüşü yenidən ixrac edir (``urls.py`` ``views.audit_log_export`` ilə qalır).
"""

from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, StreamingHttpResponse
from django.utils import timezone
from django.utils.translation import pgettext
from django.views.decorators.http import require_GET

from core.constants import AuditAction
from core.export_safety import safe_csv_writer
from core.permissions import is_superadmin_user
from core.tenancy import get_request_organization

from .views_filters import (
    EXPORT_CAP,
    _query_params,
    _run_scoped,
    apply_filters,
    can_export_audit,
    parse_filters,
    scoped_queryset,
)
from .views_serializers import _display_name, _resource_bits, action_label

# i18n skaneri kontekst sabitini MODUL daxilində axtarır (bax
# ``scripts/i18n_source_scan.py``) — ona görə import yox, yerli təyin.
_CTX = "audit.section"


class _Echo:
    """CSV yazıcısı üçün olduğu kimi qaytaran bufer; `reason` istifadəçi mətnidir → F-07 (2026-09-13) neytrallaşdırma."""

    def write(self, value):
        return value


def _csv_header() -> list[str]:
    return [
        pgettext(_CTX, "Vaxt"),
        pgettext(_CTX, "İcraçı (istifadəçi adı)"),
        pgettext(_CTX, "İcraçı (ad)"),
        pgettext(_CTX, "Əməliyyat"),
        pgettext(_CTX, "Resurs tipi"),
        pgettext(_CTX, "Resurs ID"),
        pgettext(_CTX, "Resurs"),
        pgettext(_CTX, "Təşkilat"),
        pgettext(_CTX, "Səbəb"),
        pgettext(_CTX, "IP ünvanı"),
        pgettext(_CTX, "Sorğu ID"),
        pgettext(_CTX, "Dəyişikliklər (JSON)"),
    ]


def _csv_row(log) -> list:
    user = log.user if log.user_id else None
    type_label, identifier, repr_text = _resource_bits(log)
    changes = (
        log.changes
        if log.changes
        else ({"old": log.old_values, "new": log.new_values} if (log.old_values or log.new_values) else None)
    )
    return [
        timezone.localtime(log.created_at).strftime("%Y-%m-%d %H:%M:%S"),
        user.username if user is not None else "",
        _display_name(user) if user is not None else "",
        action_label(log.action),
        log.resource_type or (log.content_type.model if log.content_type_id else ""),
        identifier,
        repr_text,
        log.organization.name if log.organization_id else "",
        log.reason or "",
        log.ip_address or "",
        str(log.request_id) if log.request_id else "",
        json.dumps(changes, ensure_ascii=False, default=str) if changes is not None else "",
    ]


@login_required
@require_GET
def audit_log_export(request):
    """Cari filtrin CSV ixracı (UTF-8 BOM, axınla; tavan `EXPORT_CAP`).

    Sətirlər GÖRÜNÜŞ İÇİNDƏ materiallaşdırılır: axın middleware zəncirindən
    SONRA oxunur və tenant/RLS konteksti o vaxt artıq sıfırlanmış ola bilər.
    İxracın özü də auditə düşür («auditçini audit et»).
    """
    if not can_export_audit(request):
        return JsonResponse({"ok": False, "error": "forbidden"}, status=403)
    is_superadmin = is_superadmin_user(request.user)
    organization = get_request_organization(request)
    filters = parse_filters(request, is_superadmin=is_superadmin)

    def _materialize():
        queryset = apply_filters(scoped_queryset(is_superadmin=is_superadmin, organization=organization), filters)
        rows = [_csv_row(log) for log in queryset[: EXPORT_CAP + 1].iterator(chunk_size=500)]
        truncated = len(rows) > EXPORT_CAP
        rows = rows[:EXPORT_CAP]
        from core.audit import log_action

        log_action(
            AuditAction.EXPORT,
            user=request.user,
            organization=organization,
            request=request,
            resource_type="audit_log",
            resource_repr="CSV",
            reason=pgettext(_CTX, "Audit jurnalı CSV ixracı: %(n)d sətir") % {"n": len(rows)},
            new_values={"filters": _query_params(filters, is_superadmin), "rows": len(rows), "truncated": truncated},
        )
        return rows, truncated

    rows, truncated = _run_scoped(is_superadmin, _materialize)
    writer = safe_csv_writer(_Echo())

    def _stream():
        yield "\ufeff"  # BOM — Excel UTF-8 Azərbaycan hərflərini düzgün oxusun
        yield writer.writerow(_csv_header())
        for row in rows:
            yield writer.writerow(row)

    filename = "audit-jurnali-%s.csv" % timezone.localdate().isoformat()
    response = StreamingHttpResponse(_stream(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="%s"' % filename
    response["X-Audit-Export-Rows"] = str(len(rows))
    response["X-Audit-Export-Truncated"] = "1" if truncated else "0"
    return response
