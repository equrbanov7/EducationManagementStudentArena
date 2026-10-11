"""«Kadr analitikası» — Excel ixracı (sahib 2026-10-11).

``GET /accounts/hr-analytics/export/?hr_*`` — panelin cari filtr dəsti (il, fakültə, kafedra, elmi ad,
ştat növü, axtarış) üzrə bütün cədvəllər bir XLSX faylında. Qapı panellə EYNİDİR
(``services.hr_analytics.resolve`` — fail-closed, icazəsiz 403). «Başqasının adından» rejimində ixrac
BAĞLIDIR (şəxsi siyahı başqasının adına çıxarılmasın). Hər ixrac audit jurnalına yazılır
(``AuditAction.EXPORT``, ``resource_type="accounts.hr_analytics"``, filtrlər və sətir sayı ilə).
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.utils.translation import pgettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from ..services.hr_analytics import constants as C
from ..services.hr_analytics.export import build_tables, xlsx_bytes
from ..services.hr_analytics.filters import apply_filters
from ..services.hr_analytics.panel import resolve

AUDIT_RESOURCE = "accounts.hr_analytics"
_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _audit(request, actor, filters, rows: int) -> None:
    from core.audit import log_action
    from core.constants import AuditAction

    log_action(
        AuditAction.EXPORT,
        user=request.user,
        organization=actor.organization,
        request=request,
        resource_type=AUDIT_RESOURCE,
        resource_repr=f"XLSX · {filters.year}",
        reason=pgettext(C.CTX, "Kadr analitikasının ixracı"),
        new_values={"format": "xlsx", "filters": filters.as_params(tab=C.TAB_OVERVIEW, page=1), "rows": rows},
    )


@never_cache
@login_required
@require_GET
def hr_analytics_export(request):
    actor, filters, _options, all_rows = resolve(request)
    if not actor.has_access:
        return JsonResponse({"ok": False, "error": "forbidden"}, status=403)
    if actor.view_as:
        return JsonResponse({"ok": False, "error": "view_as_read_only"}, status=403)
    rows = apply_filters(all_rows, filters, with_issue=False)
    payload = xlsx_bytes(build_tables(rows, demographics=actor.can_view_demographics))
    _audit(request, actor, filters, len(rows))
    stamp = timezone.localdate().isoformat()
    response = HttpResponse(payload, content_type=_XLSX)
    response["Content-Disposition"] = f'attachment; filename="kadr-analitikasi-{stamp}.xlsx"'
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    return response


__all__ = ["hr_analytics_export"]
