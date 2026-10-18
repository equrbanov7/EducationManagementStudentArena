"""«Mühasibatlıq» — Excel ixracı (sahib 2026-10-18) və müəllim pəncərəsi (modal, sahib 2026-10-19).

``GET /accounts/accounting/export/?ac_*`` — panelin cari filtr dəsti (semestr, ay, fakültə, kafedra, axtarış,
kənarlaşma; drill-down açıqdırsa həmin müəllimin dərsləri də) bir XLSX faylında. Qapı panellə EYNİDİR
(``services.accounting.resolve`` — fail-closed, icazəsiz 403). «Başqasının adından» rejimində ixrac BAĞLIDIR.
Hər ixrac audit jurnalına yazılır (``AuditAction.EXPORT``, ``resource_type="accounts.accounting"``).
Drill-down ixracı (``ac_teacher``) yalnız HƏMİN müəllimi çıxarır (modalın «Excel-ə ixrac (bu müəllim)» düyməsi).

``GET /accounts/accounting/teacher/<id>/?ac_*`` — müəllim pəncərəsinin JSON-u (``title``, ``subtitle``, ``html``,
``foot``); ``ac_part=lessons`` — «Daha çox» üçün yalnız dərs sətirləri (``rows``, ``more_url``). Qapı panellə
eynidir: açarsız 403, əhatədən kənar / mövcud olmayan müəllim 404. «Başqasının adından» rejimində baxış açıqdır
(bölmə kimi yalnız oxu), ixrac düyməsi göstərilmir.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import pgettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from ..services.accounting import constants as C
from ..services.accounting.export import build_tables, export_caption, used_rate_ids, xlsx_bytes
from ..services.accounting.modal import PART_LESSONS, teacher_modal
from ..services.accounting.panel import resolve
from ..services.accounting.rows import apply_filters, sort_rows

AUDIT_RESOURCE = "accounts.accounting"
_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _audit(request, resolved, rows: int) -> None:
    from core.audit import log_action
    from core.constants import AuditAction

    log_action(
        AuditAction.EXPORT,
        user=request.user,
        organization=resolved.actor.organization,
        request=request,
        resource_type=AUDIT_RESOURCE,
        resource_repr=f"XLSX · {resolved.semester.key if resolved.semester else '—'}",
        reason=pgettext(C.CTX, "Mühasibatlıq ixracı"),
        new_values={
            "format": "xlsx",
            "filters": resolved.filters.as_params(page=1, lpage=1),
            "rows": rows,
            # 2026-10-19: ixracın məbləğləri hansı dərəcələrlə hesablanıb (sətirlər silinmir — sonradan da oxunur).
            "pay_rates": used_rate_ids(resolved),
        },
    )


@never_cache
@login_required
@require_GET
def accounting_export(request):
    resolved = resolve(request)
    if not resolved.actor.has_access:
        return JsonResponse({"ok": False, "error": "forbidden"}, status=403)
    if resolved.actor.view_as:
        return JsonResponse({"ok": False, "error": "view_as_read_only"}, status=403)
    if resolved.semester is None:
        return JsonResponse({"ok": False, "error": "no_semester"}, status=404)
    if resolved.filters.teacher and int(resolved.filters.teacher) not in resolved.persons:
        # Drill-down ixracı yalnız əhatədəki müəllim üçün (mövcudluq sızdırılmır — «tapılmadı» ilə eyni).
        return JsonResponse({"ok": False, "error": "teacher_not_found"}, status=404)
    if resolved.filters.teacher:
        rows = [row for row in resolved.rows if str(row["id"]) == resolved.filters.teacher]
    else:
        rows = sort_rows(apply_filters(resolved.rows, resolved.filters), resolved.filters)
    payload = xlsx_bytes(build_tables(resolved, rows), caption=export_caption(resolved))
    _audit(request, resolved, len(rows))
    stamp = timezone.localdate().isoformat()
    response = HttpResponse(payload, content_type=_XLSX)
    response["Content-Disposition"] = f'attachment; filename="muhasibatliq-{stamp}.xlsx"'
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    return response


_MODAL_TEMPLATE = "accounts/profile/sections/accounting/modal/_body.html"
_MODAL_FOOT = "accounts/profile/sections/accounting/modal/_foot.html"
_MODAL_ROWS = "accounts/profile/sections/accounting/detail/_lesson_rows.html"


@never_cache
@login_required
@require_GET
def accounting_teacher_detail(request, teacher_id: int):
    result = teacher_modal(request, teacher_id)
    if result.status != 200:
        return JsonResponse({"ok": False, "error": result.error}, status=result.status)
    context = result.context
    if str(request.GET.get(f"{C.PARAM_PREFIX}part") or "") == PART_LESSONS:
        payload = {
            "ok": True,
            "rows": render_to_string(_MODAL_ROWS, context, request=request),
            "more_url": context["more_url"],
            "remaining": context["remaining"],
        }
    else:
        payload = {
            "ok": True,
            "title": context["title"],
            "subtitle": context["subtitle"],
            "html": render_to_string(_MODAL_TEMPLATE, context, request=request),
            "foot": render_to_string(_MODAL_FOOT, context, request=request),
        }
    response = JsonResponse(payload)
    response["Cache-Control"] = "private, no-store"
    return response


__all__ = ["accounting_export", "accounting_teacher_detail"]
