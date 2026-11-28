"""Seçilmiş həftənin tarixli dərsləri və semestrin təkrarlanan planı üçün XLSX."""

from io import BytesIO

from django.apps import apps

from openpyxl import Workbook
from openpyxl.cell.cell import ERROR_CODES, ILLEGAL_CHARACTERS_RE, Cell
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from core.constants import OrgUnitType
from core.export_safety import sheet_append, sheet_cell

from . import design_practical_scope, schedule
from .models import CourseOffering, WeekType
from .offering_chairs import official_offering_chairs

HEADINGS = (
    "Gün",
    "Başlanğıc",
    "Son",
    "Həftə",
    "Fakültə",
    "Kafedra",
    "Qrup",
    "Fənn",
    "Dərsin növü",
    "Müəllim",
    "Auditoriya",
)
WIDTHS = (19, 11, 11, 15, 33, 34, 18, 44, 20, 29, 17)
PARITY = {WeekType.ALL: "Hər həftə", WeekType.ODD: "Üst həftə", WeekType.EVEN: "Alt həftə"}
NAVY = "17365A"
TEAL = "176970"


def _append(ws, row):
    cells = []
    for value in row:
        if isinstance(value, str):
            value = ILLEGAL_CHARACTERS_RE.sub("", value)
            if value in ERROR_CODES:
                # Excel xəta kodu ilə eyni olan ad da (məs. "#N/A") hərfi mətndir.
                value = Cell(ws, value=value)
                value.data_type = "s"
        cells.append(value)
    sheet_append(ws, cells)


def _sheet(book, name, title, caption, headers, widths):
    ws = book.create_sheet(name)
    last = get_column_letter(len(headers))
    for row, text in ((1, title), (2, caption)):
        ws.merge_cells(f"A{row}:{last}{row}")
        cell = sheet_cell(ws, row=row, column=1, value=ILLEGAL_CHARACTERS_RE.sub("", text))
        cell.data_type = "s"
        cell.fill = PatternFill("solid", fgColor=NAVY)
        cell.font = Font(name="Calibri", color="FFFFFF", bold=row == 1, size=17 if row == 1 else 11)
        cell.alignment = Alignment(vertical="center", indent=1, wrap_text=True)
        ws.row_dimensions[row].height = 33 if row == 1 else 31
    # A3 is a real table heading, including when the selected week has no teaching.
    sheet_append(ws, headers)
    for cell in ws[3]:
        cell.fill = PatternFill("solid", fgColor=TEAL)
        cell.font = Font(name="Calibri", color="FFFFFF", bold=True)
        cell.alignment = Alignment(vertical="center", indent=1)
    ws.row_dimensions[3].height = 25
    for number, width in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(number)].width = width
    ws.freeze_panes = "B4"
    ws.sheet_view.showGridLines = False
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.sheet_properties.outlinePr.summaryBelow = False
    ws.sheet_properties.pageSetUpPr.autoPageBreaks = False
    ws.page_setup.orientation = "landscape"
    ws.page_setup.paperSize = ws.PAPERSIZE_A3
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.print_title_rows = "1:3"
    return ws


def _finish(ws, *, dated):
    last = get_column_letter(ws.max_column)
    ws.auto_filter.ref = f"A3:{last}{ws.max_row}"
    if ws.max_row == 3:
        sheet_cell(ws, row=4, column=1, value="Seçimə uyğun dərs yoxdur.")
        ws.merge_cells(start_row=4, start_column=1, end_row=4, end_column=ws.max_column)
        return
    stripe = PatternFill("solid", fgColor="EEF5F7")
    wrap = Alignment(horizontal="left", vertical="center", wrap_text=True, indent=1)
    center = Alignment(horizontal="center", vertical="center")
    for row in ws.iter_rows(min_row=4):
        for cell in row:
            cell.alignment = wrap
            if cell.row % 2 == 0:
                cell.fill = stripe
        ws.row_dimensions[row[0].row].height = 38
        if dated:
            row[0].number_format = "dd.mm.yyyy"
            row[0].alignment = center
        for col in ((2, 3) if dated else (1, 2)):
            row[col].number_format = "hh:mm"
            row[col].alignment = center


def workbook_bytes(organization, period, week, slots, labels, teacher_name=""):
    book = Workbook()
    book.remove(book.active)
    scope = " · ".join(labels) or "Səlahiyyət daxilində bütün dərslər"
    context = f"{organization.name} · {period.year_display} · {period.name} · {scope}"
    dates = f"{week['monday']:%d.%m.%Y} – {week['sunday']:%d.%m.%Y} · {PARITY[week['parity']]}"
    dated = _sheet(book, "Seçilmiş həftə", f"Dərs cədvəli · {dates}", context, ("Tarix", *HEADINGS), (15, *WIDTHS))
    plan = _sheet(book, "Semestr planı", "Semestr üzrə həftəlik dərs cədvəli", context, HEADINGS, WIDTHS)
    faculties, chairs = {}, {}
    unit_model = apps.get_model("organizations", "OrgUnit")
    units = unit_model.objects.filter(
        organization=organization, unit_type__in=(OrgUnitType.FACULTY, OrgUnitType.CHAIR, OrgUnitType.DEPARTMENT)
    )
    for key, name, kind in units.values_list("pk", "name", "unit_type"):
        if kind == OrgUnitType.FACULTY:
            faculties[str(key)] = name
        else:
            chairs[str(key)] = name
    ids = {slot.offering_id for slot in slots}
    owners = official_offering_chairs(CourseOffering.objects.filter(pk__in=ids), organization.pk) if ids else {}
    design_practical_scope.prime(slot.offering for slot in slots if slot.kind == "seminar")
    days = dict(schedule.WEEKDAYS)
    for slot in slots:
        offering = slot.offering
        group, subject = offering.group, offering.subject
        faculty = next((faculties[i] for i in reversed(group.path.split("/")) if i in faculties), "") if group else ""
        teacher = schedule.effective_instructor(slot)
        label = teacher_name or ((teacher.get_full_name() or teacher.username) if teacher else "")
        row = (
            str(days[slot.weekday]),
            slot.start_time,
            slot.end_time,
            PARITY[slot.week_type],
            faculty,
            ", ".join(sorted(chairs[key] for key in owners.get(offering.pk, ()) if key in chairs)),
            group.name if group else "",
            subject.name,
            str(slot.get_kind_display()),
            label,
            slot.room,
        )
        _append(plan, row)
        date = week["dates"][slot.weekday]
        if (
            slot.week_type in (WeekType.ALL, week["parity"])
            and (not period.start_date or period.start_date <= date)
            and (not period.end_date or date <= period.end_date)
        ):
            _append(dated, (date, *row))
    _finish(dated, dated=True)
    _finish(plan, dated=False)
    buf = BytesIO()
    book.save(buf)
    return buf.getvalue()
