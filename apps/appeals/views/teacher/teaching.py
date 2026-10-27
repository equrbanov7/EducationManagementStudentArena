"""«Fənnimə aid apellyasiyalar» — müəllimin YALNIZ-OXU görünüşü (sahib 2026-10-21; kabinet bölməsi 2026-10-27).

Sahib 2026-10-27: «ayrıca səhifə kimi açılmasın — şəxsi kabinetdə, sol menyu qalmaqla sağda açılsın». Siyahı
artıq kabinet bölməsidir (``/accounts/profile/?section=teaching-appeals``, data ``{% teaching_appeals_panel %}``
tag-ından). Bu modulda yalnız HTTP qatı qalır:

* ``teaching_appeals`` — köhnə ``/appeals/teaching/`` URL-i (bildiriş / əlfəcin) → bölməyə yönləndirmə
  (``status`` → ``ta_status``, ``open`` → ``ta_open``: çekməcə avtomatik açılır);
* ``teaching_appeal_detail`` — bir apellyasiyanın çekməcəsi (JSON ``{ok, html, title, subtitle}``);
* ``teaching_appeals_export`` — süzülmüş siyahının Excel faylı.

QƏRAR HÜQUQU VERİLMİR — qərar imtahan mərkəzinin ``appeal.respond`` + ``appeal.decide`` açarı ilədir. Əhatə hər
sorğuda ``services.teaching_scope.scoped_appeals``-dan: əhatədən kənar apellyasiya 404 (mövcudluq sızmasın).
"""

from __future__ import annotations

from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import pgettext
from django.views.decorators.http import require_GET

from core.tenancy import get_request_organization

from ...constants import APPEAL_STATUS_VALUES
from ...services.teachers import subject_teacher_names
from ...services.teaching_scope import scoped_appeals
from ._review_context import appeal_timeline
from ._review_decision import decision_timeline_events
from .teaching_export import MAX_EXPORT_ROWS, XLSX_CONTENT_TYPE, build_xlsx, export_filename
from .teaching_panel import build_teaching_panel
from .teaching_rows import CTX, SECTION, apply_filters, build_row, read_filters, student_group_map, with_row_data

#: Köhnə ad — ``apps.appeals.public`` səthi dəyişməsin (indi bölmə panelinin konteksti).
build_teaching_appeals_context = build_teaching_panel

_TIMELINE_TONES = {
    "fa-paper-plane": "primary",
    "fa-check": "success",
    "fa-plus": "success",
    "fa-xmark": "danger",
    "fa-rotate-left": "warning",
    "fa-key": "info",
    "fa-user-check": "info",
}


def section_url(**params) -> str:
    query = {"section": SECTION, **{key: value for key, value in params.items() if value}}
    return reverse("accounts:profile") + "?" + urlencode(query)


@login_required
@require_GET
def teaching_appeals(request):
    """Köhnə müstəqil səhifə → kabinet bölməsi (filtr və «aç» parametrləri qorunur)."""
    status = (request.GET.get("status") or "").strip()
    open_id = (request.GET.get("open") or "").strip()
    return redirect(
        section_url(
            ta_status=status if status in APPEAL_STATUS_VALUES else "",
            ta_open=open_id if open_id.isdigit() else "",
        )
    )


def _scoped(request):
    organization = get_request_organization(request)
    if organization is None:
        raise Http404
    return scoped_appeals(request.user, organization)


def _timeline(request, appeal, items):
    events = appeal_timeline(appeal, items) + decision_timeline_events(request, appeal)
    events.sort(key=lambda event: event["at"])
    return [
        {
            "who": event.get("actor") or "—",
            "when": date_format(timezone.localtime(event["at"]), "d.m.Y H:i"),
            "what": event["text"],
            "tone": _TIMELINE_TONES.get(event.get("icon"), "neutral"),
            "current": index == len(events) - 1,
        }
        for index, event in enumerate(events)
    ]


def _documents(request, appeal):
    from ...services.documents import can_download_document

    records = [record for record in appeal.decision_records.all() if record.document]
    allowed = bool(records) and can_download_document(request.user, records[0])
    return [
        {"name": record.document_name or record.document.name, "record": record, "can_download": allowed}
        for record in records
    ]


@login_required
@require_GET
def teaching_appeal_detail(request, appeal_id):
    """Çekməcə: tələbənin səbəbi, sual-sual qərarlar, mərkəzin qeydi, sənədlər, tarixçə (yalnız-oxu)."""
    is_xhr = request.headers.get("x-requested-with") == "XMLHttpRequest"
    if not is_xhr:
        return redirect(section_url(ta_open=str(appeal_id)))
    scoped, org_wide = _scoped(request)
    appeal = with_row_data(scoped.filter(pk=appeal_id)).first()
    if appeal is None:
        message = pgettext(CTX, "Apellyasiya tapılmadı və ya baxmaq icazəniz yoxdur.")
        return JsonResponse({"ok": False, "message": str(message)}, status=404)
    items = list(
        appeal.items.select_related(
            "question", "decided_by_teacher", "resolved_by", "score_adjustment__applied_by"
        ).order_by("id")
    )
    row = build_row(appeal, student_group_map(scoped.filter(pk=appeal.pk)))
    context = {
        "row": row,
        "appeal": appeal,
        "items": items,
        "documents": _documents(request, appeal),
        "timeline": _timeline(request, appeal, items),
        "subject_teachers": subject_teacher_names(appeal),
        "org_wide": org_wide,
    }
    html = render_to_string("appeals/teaching/_drawer_body.html", context, request=request)
    return JsonResponse(
        {
            "ok": True,
            "html": html,
            "title": row["student_name"],
            "subtitle": " · ".join(part for part in (row["exam_title"], row["subject"], row["group"]) if part),
        }
    )


@login_required
@require_GET
def teaching_appeals_export(request):
    """Süzülmüş siyahı (ekranla eyni əhatə və süzgəclər) → .xlsx."""
    scoped, _org_wide = _scoped(request)
    filters = read_filters(request)
    group_map = student_group_map(scoped)
    queryset = apply_filters(scoped, filters, group_map=group_map).order_by("-created_at", "-id")
    rows = [build_row(appeal, group_map) for appeal in with_row_data(queryset)[: MAX_EXPORT_ROWS + 1]]
    truncated = len(rows) > MAX_EXPORT_ROWS
    response = HttpResponse(build_xlsx(rows[:MAX_EXPORT_ROWS], truncated=truncated), content_type=XLSX_CONTENT_TYPE)
    if truncated:
        response["X-Export-Truncated"] = str(MAX_EXPORT_ROWS)
    response["Content-Disposition"] = f'attachment; filename="{export_filename()}"'
    response["Cache-Control"] = "no-store"
    return response


__all__ = [
    "build_teaching_appeals_context",
    "section_url",
    "teaching_appeal_detail",
    "teaching_appeals",
    "teaching_appeals_export",
]
