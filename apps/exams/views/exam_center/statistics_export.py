"""«İmtahan statistikaları» — Excel (.xlsx) ixracının qurulması (sorğuda və ya worker-də).

2026-11-17 (sahib: «236 bio excel yüklə — download.htm»): geniş filtrdə ixrac minlərlə test cəhdinin cavablarından
balı yenidən hesablayır (``attach_test_result_summaries``) və sorğu limitini aşırdı; brauzer serverin HTML xəta
səhifəsini «download.htm» kimi endirirdi. Qurucu indi sorğudan asılı deyil — ``params`` (GET və ya job-a yazılmış
lüğət) qəbul edir; kiçik dəst view-da dərhal, böyüyü ``export_registry`` (``exam_center_stats_xlsx``) ilə worker-də.
Sütunlar və 5000 sətir tavanı əvvəlki kimidir.
"""

from __future__ import annotations

import io

from django.utils import timezone

from apps.exams.services.result_calculation import attach_test_result_summaries
from apps.exams.services.supervision import attach_attempt_interventions
from core.export_safety import sheet_cell

from .statistics import _row, filtered_attempts, sorted_attempts

EXPORT_NAME = "exam_center_stats_xlsx"
XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_ROWS = 5000

#: Filtr parametrləri — job-a yalnız bunlar yazılır (``filtered_attempts`` / ``sorted_attempts`` oxuyur).
FILTER_KEYS = (
    "q",
    "subjects",
    "groups",
    "units",
    "faculties",
    "departments",
    "teachers",
    "type",
    "format",
    "status",
    "year",
    "semester",
    "sort",
)

COLUMNS = [
    ("Tələbə", "student"),
    ("İstifadəçi", "username"),
    ("Qrup", "group"),
    ("Kafedra", "kafedra"),
    ("Fakültə / dekanlıq", "faculty"),
    ("Müəllim", "teacher"),
    ("İmtahan", "exam"),
    ("Fənn", "subject"),
    ("Tip", "type"),
    ("Bal", "score"),
    ("Faiz", "percentage"),
    ("Status", "status"),
    ("Uzaqlaşdırma səbəbi", "removal_reason"),
    ("Tarix", "date"),
]


def export_params(params) -> dict:
    """GET → job üçün JSON-a yazıla bilən filtr lüğəti (naməlum açarlar atılır)."""
    return {key: str(params.get(key) or "") for key in FILTER_KEYS if params.get(key)}


def build_stats_xlsx(organization, params):
    """``(filename, content_type, bytes)`` — filtrlənmiş bitmiş cəhdlər (ən çox :data:`MAX_ROWS`)."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill
    from openpyxl.utils import get_column_letter

    attempts = list(sorted_attempts(filtered_attempts(params, organization), params)[:MAX_ROWS])
    attach_test_result_summaries(attempts)
    attach_attempt_interventions(attempts)

    wb = Workbook()
    ws = wb.active
    ws.title = "Statistika"
    for col, (title, _key) in enumerate(COLUMNS, start=1):
        cell = sheet_cell(ws, row=1, column=col, value=title)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="2563EB")
    # 2026-09-14 (audit F-07): tələbə/qrup/imtahan adı və uzaqlaşdırma səbəbi
    # istifadəçi mətnidir → formula neytrallaşdırması (`sheet_cell`).
    for r, attempt in enumerate(attempts, start=2):
        row = _row(attempt)
        for c, (_title, key) in enumerate(COLUMNS, start=1):
            sheet_cell(ws, row=r, column=c, value=row[key])
    for col in range(1, len(COLUMNS) + 1):
        ws.column_dimensions[get_column_letter(col)].width = 22

    buffer = io.BytesIO()
    wb.save(buffer)
    stamp = timezone.localtime().strftime("%Y%m%d-%H%M")
    return f"imtahan-statistika-{stamp}.xlsx", XLSX_CONTENT_TYPE, buffer.getvalue()


__all__ = ["EXPORT_NAME", "FILTER_KEYS", "MAX_ROWS", "build_stats_xlsx", "export_params"]
