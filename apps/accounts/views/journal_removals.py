"""«Jurnaldan çıxarılmalar» kabinet bölməsi — panel çərçivəsi + Excel ixracı (sahib 2026-11-04).

Sahib: «Daha sonra mən harada isə onda baxa bilim o tip hadisələrə — nəyə görə olub.» Jurnaldan hər çıxarılma
(«Fəndən azad et», alt qrupdan əlavənin «Çıxar»-ı, xarici nəticənin tanınması) səbəb kateqoriyası + qeydlə
yazılır (:mod:`apps.registrar.journal_removal`); bu bölmə onları süzgəclərlə siyahılayır.

Qapı «Jurnal təmizliyi» ilə EYNİDİR — YALNIZ RİM rəhbəri (``ikt_rehber``) və superadmin
(:func:`apps.accounts.views.journal_hygiene.policy.resolve_actor`; menyu qapısı ``_helpers/rbac_sections.py``).
Panel yalnız oxudur (view-as altında da baxılır); ixrac «başqasının adından» rejimində BAĞLIDIR və hər ixrac
audit jurnalına yazılır (``AuditAction.EXPORT``, ``resource_type="accounts.journal_removals"``).
"""

from __future__ import annotations

from datetime import datetime
from io import BytesIO
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from apps.registrar.public import journal_removal_read as removals

from .journal_hygiene.policy import resolve_actor

SECTION = "journal-removals"
CTX = "accounts.journal_removals"
AUDIT_RESOURCE = "accounts.journal_removals"
_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _option_list(options, *, all_label) -> list:
    return [{"value": "", "label": all_label}, *options]


def _filter_fields(organization, filters) -> list:
    prefix = removals.PREFIX
    every = pgettext(CTX, "Hamısı")
    return [
        {
            "name": f"{prefix}reason",
            "label": pgettext(CTX, "Səbəb"),
            "kind": "select",
            "options": _option_list(removals.reason_options(), all_label=every),
            "value": filters.reason,
        },
        {
            "name": f"{prefix}action",
            "label": pgettext(CTX, "Əməl"),
            "kind": "select",
            "options": _option_list(removals.action_options(), all_label=every),
            "value": filters.action,
        },
        {
            "name": f"{prefix}from",
            "label": pgettext(CTX, "Tarixdən"),
            "kind": "date",
            "value": filters.date_from.isoformat() if filters.date_from else "",
        },
        {
            "name": f"{prefix}to",
            "label": pgettext(CTX, "Tarixədək"),
            "kind": "date",
            "value": filters.date_to.isoformat() if filters.date_to else "",
        },
        {
            "name": f"{prefix}faculty",
            "label": pgettext(CTX, "Fakültə"),
            "kind": "select",
            "searchable": True,
            "options": _option_list(removals.faculty_options(organization), all_label=every),
            "value": filters.faculty,
        },
        {
            "name": f"{prefix}chair",
            "label": pgettext(CTX, "Kafedra"),
            "kind": "select",
            "searchable": True,
            "options": _option_list(removals.chair_options(organization), all_label=every),
            "value": filters.chair,
        },
        {
            "name": f"{prefix}teacher",
            "label": pgettext(CTX, "Müəllim"),
            "kind": "search",
            "value": filters.teacher,
            "placeholder": pgettext(CTX, "Müəllimin adı"),
        },
        {
            "name": f"{prefix}q",
            "label": pgettext(CTX, "Tələbə"),
            "kind": "search",
            "value": filters.student,
            "placeholder": pgettext(CTX, "Ad, soyad və ya istifadəçi adı"),
            "wide": True,
        },
    ]


def _section_url(params) -> str:
    query = urlencode({"section": SECTION, **params})
    return f"{reverse('accounts:profile')}?{query}"


def _export_url(filters) -> str:
    url = reverse("accounts:journal_removals_export")
    params = filters.as_params(page=1)
    return f"{url}?{urlencode(params)}" if params else url


def build_panel_context(request) -> dict:
    actor = resolve_actor(request)
    panel = {
        "has_access": actor.has_access,
        "access_denied_message": pgettext(CTX, "Bu bölmə yalnız RİM rəhbəri və superadmin üçündür."),
    }
    if not actor.has_access:
        return panel
    organization = actor.organization
    filters = removals.parse_filters(request.GET)
    result = removals.page(organization, filters)
    counts = removals.reason_counts(organization, filters)
    for item in counts:
        item["url"] = _section_url({**filters.as_params(page=1), f"{removals.PREFIX}reason": item["value"]})
        item["active"] = item["value"] == filters.reason
    panel.update(
        filters=filters,
        filter_fields=_filter_fields(organization, filters),
        filter_count_label=pgettext(CTX, "Nəticə: %(n)s qeyd") % {"n": result["total"]},
        reason_counts=counts,
        is_filtered=filters.is_filtered,
        view_as=actor.view_as,
        export_url="" if actor.view_as else _export_url(filters),
        prev_url=_section_url(filters.as_params(page=result["page"] - 1)) if result["has_prev"] else "",
        next_url=_section_url(filters.as_params(page=result["page"] + 1)) if result["has_next"] else "",
        **result,
    )
    return panel


# ── Excel ixracı ─────────────────────────────────────────────────────────────


def _columns():
    return [
        ("index", "№", 6),
        ("created_at", pgettext(CTX, "Tarix"), 17),
        ("student", pgettext(CTX, "Tələbə"), 30),
        ("student_username", pgettext(CTX, "İstifadəçi adı"), 18),
        ("group", pgettext(CTX, "Qrup"), 14),
        ("subject_code", pgettext(CTX, "Fənn kodu"), 12),
        ("subject_name", pgettext(CTX, "Fənn"), 30),
        ("period", pgettext(CTX, "Semestr"), 20),
        ("teacher", pgettext(CTX, "Müəllim"), 26),
        ("action_label", pgettext(CTX, "Əməl"), 24),
        ("reason_label", pgettext(CTX, "Səbəb"), 30),
        ("note", pgettext(CTX, "Qeyd"), 40),
        ("actor", pgettext(CTX, "Çıxaran"), 26),
        ("state_label", pgettext(CTX, "Vəziyyət"), 14),
    ]


def _state_label(state) -> str:
    return pgettext(CTX, "Bərpa olunub") if state == "restored" else pgettext(CTX, "Qüvvədə")


def build_xlsx(rows, *, truncated=False) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    from core.export_safety import sheet_cell

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Removals"
    columns = _columns()
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="2563EB")
    wrap = Alignment(vertical="center", wrap_text=True)
    for column, (_key, header, width) in enumerate(columns, start=1):
        cell = sheet_cell(sheet, row=1, column=column, value=header)
        cell.font, cell.fill, cell.alignment = header_font, header_fill, wrap
        sheet.column_dimensions[get_column_letter(column)].width = width
    for row_index, row in enumerate(rows, start=2):
        values = {**row, "index": row_index - 1, "state_label": _state_label(row.get("state"))}
        for column, (key, _header, _width) in enumerate(columns, start=1):
            value = values.get(key)
            if isinstance(value, datetime):
                value = (timezone.localtime(value) if timezone.is_aware(value) else value).replace(tzinfo=None)
            cell = sheet_cell(sheet, row=row_index, column=column, value="" if value is None else value)
            cell.alignment = wrap
            if isinstance(value, datetime):
                cell.number_format = "DD.MM.YYYY HH:MM"
    if truncated:
        note = pgettext(CTX, "Fayl ilk %(n)s sətirlə məhdudlaşdırılıb — süzgəcləri daraldıb yenidən yükləyin.")
        cell = sheet_cell(sheet, row=len(rows) + 3, column=2, value=note % {"n": removals.MAX_EXPORT_ROWS})
        cell.font = Font(bold=True, color="B91C1C")
    sheet.freeze_panes = "A2"
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def _audit(request, organization, filters, rows: int) -> None:
    from core.audit import log_action
    from core.constants import AuditAction

    log_action(
        AuditAction.EXPORT,
        user=request.user,
        organization=organization,
        request=request,
        resource_type=AUDIT_RESOURCE,
        resource_repr=f"XLSX · {rows}",
        reason=pgettext(CTX, "Jurnaldan çıxarılmaların ixracı"),
        new_values={"format": "xlsx", "filters": filters.as_params(page=1), "rows": rows},
    )


@never_cache
@login_required
@require_GET
def journal_removals_export(request):
    actor = resolve_actor(request)
    if not actor.has_access:
        return JsonResponse({"ok": False, "error": "forbidden"}, status=403)
    if actor.view_as:
        return JsonResponse({"ok": False, "error": "view_as_read_only"}, status=403)
    filters = removals.parse_filters(request.GET)
    rows, truncated = removals.export_rows(actor.organization, filters)
    payload = build_xlsx(rows, truncated=truncated)
    _audit(request, actor.organization, filters, len(rows))
    stamp = timezone.localtime().strftime("%Y%m%d-%H%M")
    response = HttpResponse(payload, content_type=_XLSX)
    response["Content-Disposition"] = f'attachment; filename="jurnaldan-cixarilmalar-{stamp}.xlsx"'
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    return response


__all__ = ["SECTION", "build_panel_context", "build_xlsx", "journal_removals_export"]
