"""«Alt qrup tələbələri» — Excel ixracı (sahib 2026-11-05).

Qapı bölmə ilə EYNİDİR (:func:`apps.accounts.views.subgroup_students.resolve_actor`, əhatə daxil); «başqasının
adından» rejimində BAĞLIDIR və hər ixrac audit jurnalına yazılır (``AuditAction.EXPORT``,
``resource_type="accounts.subgroup_students"``). Hücrələr ``core.export_safety.sheet_cell`` ilə yazılır (formula
inyeksiyası yoxdur); sənəd sütunu qorunan media linkidir (oxu siyasəti media qapısındadır).
"""

from __future__ import annotations

import datetime as dt
from io import BytesIO

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.utils.translation import pgettext
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from apps.registrar.public import subgroup_students_read as read

from .subgroup_students import CTX, resolve_actor

AUDIT_RESOURCE = "accounts.subgroup_students"
_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _columns():
    return [
        ("index", "№", 6),
        ("added_on", pgettext(CTX, "Tarix"), 17),
        ("student", pgettext(CTX, "Tələbə"), 30),
        ("student_username", pgettext(CTX, "İstifadəçi adı"), 18),
        ("home_group", pgettext(CTX, "Öz qrupu"), 14),
        ("current_group", pgettext(CTX, "Cari qrupu"), 14),
        ("target_group", pgettext(CTX, "Alt qrup olduğu qrup"), 16),
        ("subject_code", pgettext(CTX, "Fənn kodu"), 12),
        ("subject_name", pgettext(CTX, "Fənn"), 30),
        ("teacher", pgettext(CTX, "Müəllim"), 26),
        ("period", pgettext(CTX, "Semestr"), 20),
        ("kind_label", pgettext(CTX, "Növ"), 14),
        ("status_label", pgettext(CTX, "Vəziyyət"), 20),
        ("credits", pgettext(CTX, "Kredit"), 9),
        ("reason", pgettext(CTX, "Səbəb / qeyd"), 40),
        ("document_label", pgettext(CTX, "Sənəd"), 26),
        ("document_ref", pgettext(CTX, "Sənəd linki / sərəncam"), 40),
        ("actor", pgettext(CTX, "Əlavə edən"), 26),
    ]


def _cell_values(row, index, base_url) -> dict:
    document = row["document"]
    if document["url"]:
        reference = f"{base_url}{document['url']}"
    elif document["order_number"]:
        when = document["order_date"].strftime("%d.%m.%Y") if document["order_date"] else ""
        reference = f"№ {document['order_number']} {when}".strip()
    else:
        reference = ""
    status = row["status_label"]
    if row["released"] and row["status"] != "released":
        status = f"{status} · {read.label_of('released', read.STATUS_CHOICES)}"
    return {
        **row,
        "index": index,
        "status_label": status,
        "document_label": document["label"],
        "document_ref": reference,
    }


def build_xlsx(rows, *, base_url="", truncated=False) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    from core.export_safety import sheet_cell

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Subgroup students"
    columns = _columns()
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="2563EB")
    wrap = Alignment(vertical="center", wrap_text=True)
    for column, (_key, header, width) in enumerate(columns, start=1):
        cell = sheet_cell(sheet, row=1, column=column, value=header)
        cell.font, cell.fill, cell.alignment = header_font, header_fill, wrap
        sheet.column_dimensions[get_column_letter(column)].width = width
    for row_index, row in enumerate(rows, start=2):
        values = _cell_values(row, row_index - 1, base_url)
        for column, (key, _header, _width) in enumerate(columns, start=1):
            value = values.get(key)
            if isinstance(value, dt.datetime):
                value = (timezone.localtime(value) if timezone.is_aware(value) else value).replace(tzinfo=None)
            cell = sheet_cell(sheet, row=row_index, column=column, value="" if value is None else value)
            cell.alignment = wrap
            if isinstance(value, dt.datetime):
                cell.number_format = "DD.MM.YYYY HH:MM"
    if truncated:
        note = pgettext(CTX, "Fayl ilk %(n)s sətirlə məhdudlaşdırılıb — süzgəcləri daraldıb yenidən yükləyin.")
        cell = sheet_cell(sheet, row=len(rows) + 3, column=2, value=note % {"n": read.MAX_EXPORT_ROWS})
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
        reason=pgettext(CTX, "Alt qrup tələbələrinin ixracı"),
        new_values={"format": "xlsx", "filters": filters.as_params(page=1), "rows": rows},
    )


@never_cache
@login_required
@require_GET
def subgroup_students_export(request):
    actor = resolve_actor(request)
    if not actor.has_access:
        return JsonResponse({"ok": False, "error": "forbidden"}, status=403)
    if actor.view_as:
        return JsonResponse({"ok": False, "error": "view_as_read_only"}, status=403)
    filters = read.parse_filters(request.GET)
    rows, truncated = read.export_rows(actor.organization, filters, actor.scope)
    payload = build_xlsx(rows, base_url=request.build_absolute_uri("/").rstrip("/"), truncated=truncated)
    _audit(request, actor.organization, filters, len(rows))
    stamp = timezone.localtime().strftime("%Y%m%d-%H%M")
    response = HttpResponse(payload, content_type=_XLSX)
    response["Content-Disposition"] = f'attachment; filename="alt-qrup-telebeleri-{stamp}.xlsx"'
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store"
    return response


__all__ = ["build_xlsx", "subgroup_students_export"]
