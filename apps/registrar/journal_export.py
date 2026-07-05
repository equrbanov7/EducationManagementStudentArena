"""Jurnal xlsx ixracı (U14) — müəllim/rəhbərlik üçün rəsmi cədvəl.

Bir offering-in tam jurnalını iki vərəqdə ixrac edir (openpyxl — artıq base
asılılıqdır): «Davamiyyət» (dərs-bə-dərs iə/qb + bal + qayıb + giriş balı) və
«Yekun» (giriş + imtahan + ümumi + hərf + nəticə). Sənəd anında yaradılır,
saxlanmır; hər ixrac audit-ə yazılır (view qatında).
"""

from __future__ import annotations

from io import BytesIO

from django.utils import timezone
from django.utils.translation import pgettext


def _(text):
    return pgettext("registrar.pdf", text)  # PDF ilə eyni kontekst — etiketlər üst-üstə düşür


_HEADER_FILL = "2563EB"  # --ems-primary-600 (WCU göy)
_HEADER_FONT = "FFFFFF"
_ABSENT_FILL = "FEE2E2"  # --ems-danger-100
_BARRED_FONT = "B91C1C"


def build_journal_workbook(*, offering, journal, finals) -> bytes:
    """Offering jurnalı → xlsx bytes. ``journal``/`finals`` — mövcud servis
    strukturları (gradebook.get_offering_journal / finals.get_offering_results)."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    header_fill = PatternFill("solid", fgColor=_HEADER_FILL)
    header_font = Font(color=_HEADER_FONT, bold=True)
    absent_fill = PatternFill("solid", fgColor=_ABSENT_FILL)
    barred_font = Font(color=_BARRED_FONT, bold=True)
    center = Alignment(horizontal="center")

    workbook = Workbook()

    # ── Vərəq 1: Davamiyyət və ballar ────────────────────────────────────────
    ws = workbook.active
    ws.title = pgettext("registrar.journal", "Davamiyyət və ballar")[:31]

    meta = f"{offering.subject.code} — {offering.subject.name}"
    if offering.group_id:
        meta += f" · {offering.group.name}"
    if offering.period_id:
        meta += f" · {offering.period.name}"
    ws.append([meta])
    ws.append([])

    lessons = journal["lessons"]
    head = [_("Tələbə")]
    head += [
        f"{i + 1} · {lesson.date.strftime('%d.%m')} ({lesson.kind[:1].upper()})" for i, lesson in enumerate(lessons)
    ]
    head += [pgettext("registrar.journal", "Qayıb"), pgettext("registrar.journal", "Giriş balı")]
    ws.append(head)
    header_row = ws.max_row
    for col in range(1, len(head) + 1):
        cell = ws.cell(row=header_row, column=col)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center

    for row in journal["rows"]:
        values = [row["student"].get_full_name() or row["student"].username]
        for cell_data in row["cells"]:
            mark = cell_data["mark"]
            if mark is None:
                values.append("")
            elif mark.status == "absent":
                values.append("qb")
            elif mark.score is not None:
                values.append(float(mark.score))
            else:
                values.append("+")
        values.append(float(row["absence_hours"]))
        values.append(float(row["entry_score"]))
        ws.append(values)
        excel_row = ws.max_row
        for idx, cell_data in enumerate(row["cells"], start=2):
            if cell_data["mark"] is not None and cell_data["mark"].status == "absent":
                ws.cell(row=excel_row, column=idx).fill = absent_fill
        if row["barred"]:
            ws.cell(row=excel_row, column=1).font = barred_font

    ws.column_dimensions["A"].width = 30
    for col in range(2, len(head) + 1):
        ws.column_dimensions[get_column_letter(col)].width = 9
    ws.freeze_panes = ws.cell(row=header_row + 1, column=2)

    # ── Vərəq 2: Yekun nəticə ────────────────────────────────────────────────
    ws2 = workbook.create_sheet(pgettext("registrar.finals", "Yekun nəticə")[:31])
    head2 = [
        _("Tələbə"),
        _("Giriş"),
        _("İmtahan"),
        _("Yekun"),
        _("Hərf"),
        _("Nəticə"),
        pgettext("registrar.finals", "Təkrar imtahan"),
    ]
    ws2.append(head2)
    for col in range(1, len(head2) + 1):
        cell = ws2.cell(row=1, column=col)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center

    for row in finals["rows"]:
        result = row["result"]
        if result["barred"] or result["failed"]:
            outcome = _("Kəsildi")
        elif result["passed"]:
            outcome = _("Keçdi")
        else:
            outcome = _("Davam edir")
        resit = result.get("resit")
        ws2.append(
            [
                row["student"].get_full_name() or row["student"].username,
                float(result["entry_score"]),
                float(result["exam_score"]) if result["exam_score"] is not None else "",
                float(result["total"]) if result["graded"] else "",
                result["letter"] if result["graded"] else "",
                str(outcome),
                float(resit.resit_score) if resit is not None and resit.resit_score is not None else "",
            ]
        )
        if result["barred"] or result["failed"]:
            ws2.cell(row=ws2.max_row, column=6).font = barred_font

    ws2.column_dimensions["A"].width = 30
    for col in range(2, len(head2) + 1):
        ws2.column_dimensions[get_column_letter(col)].width = 13
    ws2.freeze_panes = "A2"

    stamp = timezone.localtime().strftime("%d.%m.%Y %H:%M")
    ws2.append([])
    ws2.append([f"{_('Bu sənəd sistem tərəfindən yaradılıb və elektron formada etibarlıdır.')} · {stamp}"])

    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
