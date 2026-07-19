"""Rəsmi akademik transkript PDF-i (U9) — PyMuPDF renderer.

Renders :func:`transcript.build_student_transcript` data into an A4 PDF using
the already-shipped PyMuPDF dependency (no new packages). The vendored DejaVu
Sans fonts (``static/fonts/``) provide full Azerbaijani glyph coverage (ə ğ ı
ö ş ü ç) — PDF base-14 fonts cannot render them. Fonts are subset on save so
the document stays small (~70KB instead of ~1.5MB).

The document is generated on the fly (never stored) and carries a footer note
that it is system-generated; issuance is written to the audit log by the view.
"""

from __future__ import annotations

from django.conf import settings
from django.utils import timezone
from django.utils.translation import pgettext


def _(text):
    """PDF labels live in their own i18n context — short words like "Kod" or
    "Yekun" already exist context-free elsewhere with unrelated translations."""
    return pgettext("registrar.pdf", text)


# ── Layout constants (A4 = 595 × 842 pt) ────────────────────────────────────
_PAGE_W, _PAGE_H = 595, 842
_MARGIN = 46
_CONTENT_W = _PAGE_W - 2 * _MARGIN
_BOTTOM_LIMIT = _PAGE_H - 64  # keep clear of the footer band

# WCU palette (design-tokens mirror): primary-600 / neutral tones.
_BLUE = (0.145, 0.388, 0.922)
_DARK = (0.06, 0.09, 0.16)
_MUTED = (0.39, 0.45, 0.55)
_LINE = (0.89, 0.91, 0.94)
_ROW_ALT = (0.97, 0.98, 0.99)
_GREEN = (0.02, 0.59, 0.41)
_RED = (0.86, 0.15, 0.15)

_FONT = "wcu"
_FONT_BOLD = "wcub"

# Table column x-offsets (relative to _MARGIN) and widths.
_COLS = (
    ("code", 0, 58),
    ("name", 62, 205),
    ("credit", 271, 38),
    ("entry", 313, 42),
    ("exam", 359, 46),
    ("total", 409, 42),
    ("letter", 455, 30),
    ("status", 489, 68),
)


def _font_path(bold=False) -> str:
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    return str(settings.BASE_DIR / "static" / "fonts" / name)


_measure_fonts: dict = {}


def _text_width(value: str, *, size: float, bold=False) -> float:
    """Measured width of ``value`` at ``size`` pt (cached fitz.Font per face)."""
    import fitz

    font = _measure_fonts.get(bold)
    if font is None:
        font = _measure_fonts[bold] = fitz.Font(fontfile=_font_path(bold=bold))
    return font.text_length(value, fontsize=size)


class _Sheet:
    """Cursor-based page writer: tracks y, adds pages, draws the footer."""

    def __init__(self, doc, title):
        self.doc = doc
        self.title = title
        self.page = None
        self.y = 0.0
        self._new_page()

    def _new_page(self):
        self.page = self.doc.new_page(width=_PAGE_W, height=_PAGE_H)
        self.page.insert_font(fontname=_FONT, fontfile=_font_path())
        self.page.insert_font(fontname=_FONT_BOLD, fontfile=_font_path(bold=True))
        self.y = _MARGIN

    def ensure(self, height):
        if self.y + height > _BOTTOM_LIMIT:
            self._new_page()

    def text(self, x, value, *, size=9, bold=False, color=_DARK, right_edge=None):
        """Draw one line at the current cursor; optionally right-align to ``right_edge``."""
        font = _FONT_BOLD if bold else _FONT
        value = str(value)
        if right_edge is not None:
            x = right_edge - _text_width(value, size=size, bold=bold)
        self.page.insert_text((x, self.y), value, fontname=font, fontsize=size, color=color)

    def rule(self, *, color=_LINE, width=0.6):
        self.page.draw_line((_MARGIN, self.y), (_PAGE_W - _MARGIN, self.y), color=color, width=width)

    def fill_band(self, height, color):
        import fitz

        rect = fitz.Rect(_MARGIN - 6, self.y - 9, _PAGE_W - _MARGIN + 6, self.y - 9 + height)
        self.page.draw_rect(rect, color=None, fill=color)

    def finish_footers(self, generated_at):
        note = _("Bu sənəd sistem tərəfindən yaradılıb və elektron formada etibarlıdır.")
        stamp = generated_at.strftime("%d.%m.%Y %H:%M")
        total = len(self.doc)
        for index, page in enumerate(self.doc, start=1):
            y = _PAGE_H - 40
            page.draw_line((_MARGIN, y - 10), (_PAGE_W - _MARGIN, y - 10), color=_LINE, width=0.6)
            page.insert_text((_MARGIN, y), f"{note}  ·  {stamp}", fontname=_FONT, fontsize=7, color=_MUTED)
            label = f"{index} / {total}"
            width = _text_width(label, size=7)
            page.insert_text((_PAGE_W - _MARGIN - width, y), label, fontname=_FONT, fontsize=7, color=_MUTED)


def _truncate(sheet_text: str, limit: int) -> str:
    return sheet_text if len(sheet_text) <= limit else sheet_text[: limit - 1] + "…"


def _fmt_score(value) -> str:
    if value is None:
        return "—"
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text or "0"


def _status_of(result):
    if result["barred"] or result["failed"]:
        return _("Kəsildi"), _RED
    if result["passed"]:
        return _("Keçdi"), _GREEN
    return _("Davam edir"), _MUTED


def _draw_header(sheet, organization, record, student):
    sheet.y += 8
    sheet.text(_MARGIN, organization.name, size=13, bold=True, color=_BLUE)
    sheet.y += 24
    sheet.text(_MARGIN, _("AKADEMİK TRANSKRİPT"), size=18, bold=True)
    sheet.y += 14
    sheet.rule(color=_BLUE, width=1.4)
    sheet.y += 22

    full_name = student.get_full_name() or student.username
    pairs = [(_("Tələbə"), full_name)]
    if record is not None:
        if record.program_id:
            pairs.append((_("İxtisas (proqram)"), f"{record.program.code} — {record.program.name}"))
        if record.group_id:
            pairs.append((_("Qrup"), record.group.name))
        pairs.append((_("Qəbul ili"), str(record.admission_year)))
        pairs.append((_("Status"), record.get_status_display()))

    for label, value in pairs:
        sheet.ensure(16)
        sheet.text(_MARGIN, f"{label}:", size=9, color=_MUTED)
        sheet.text(_MARGIN + 118, _truncate(str(value), 78), size=9, bold=True)
        sheet.y += 15
    sheet.y += 8


def _draw_table_header(sheet):
    sheet.fill_band(16, _ROW_ALT)
    headers = {
        "code": _("Kod"),
        "name": _("Fənn"),
        "credit": _("Kredit"),
        "entry": _("Giriş"),
        "exam": _("İmtahan"),
        "total": _("Yekun"),
        "letter": _("Hərf"),
        "status": _("Nəticə"),
    }
    for key, offset, width in _COLS:
        right = key in ("credit", "entry", "exam", "total")
        if right:
            sheet.text(0, headers[key], size=7.5, bold=True, color=_MUTED, right_edge=_MARGIN + offset + width)
        else:
            sheet.text(_MARGIN + offset, headers[key], size=7.5, bold=True, color=_MUTED)
    sheet.y += 13


def _draw_semester(sheet, semester):
    period = semester["period"]
    head = f"{period.name}  ·  {period.year_display}"
    sheet.ensure(64)
    sheet.text(_MARGIN, head, size=10.5, bold=True, color=_BLUE)
    figures = _("GPA %(gpa)s · %(earned)s kredit") % {
        "gpa": f"{semester['gpa']:.2f}",
        "earned": semester["credits_earned"],
    }
    sheet.text(0, figures, size=8.5, color=_MUTED, right_edge=_PAGE_W - _MARGIN)
    sheet.y += 16
    _draw_table_header(sheet)

    for index, row in enumerate(semester["rows"]):
        sheet.ensure(15)
        if index % 2 == 1:
            sheet.fill_band(14.5, _ROW_ALT)
        result = row["result"]
        definite = result["passed"] or result["failed"]
        cells = {
            "code": row["subject"].code,
            "name": _truncate(row["subject"].name, 46),
            "credit": str(row["credit"]),
            "entry": _fmt_score(result["entry_score"]),
            "exam": _fmt_score(result["effective_exam"]) if result["graded"] else "—",
            "total": _fmt_score(result["total"]) if definite else "—",
            "letter": result["letter"] if row["in_gpa"] else "—",
        }
        for key, offset, width in _COLS[:-1]:
            right = key in ("credit", "entry", "exam", "total")
            bold = key == "total" and definite
            if right:
                sheet.text(0, cells[key], size=8, bold=bold, right_edge=_MARGIN + offset + width)
            else:
                sheet.text(_MARGIN + offset, cells[key], size=8, bold=bold)
        status_label, status_color = _status_of(result)
        status_offset = _COLS[-1][1]
        sheet.text(_MARGIN + status_offset, status_label, size=8, bold=True, color=status_color)
        sheet.y += 14.5

    sheet.y += 3
    sheet.rule()
    sheet.y += 18


def _draw_summary(sheet, data):
    sheet.ensure(70)
    sheet.y += 4
    sheet.rule(color=_BLUE, width=1.2)
    sheet.y += 18
    sheet.text(_MARGIN, _("YEKUN"), size=11, bold=True, color=_BLUE)
    sheet.y += 17
    stats = [
        (_("Kumulyativ GPA"), f"{data['cumulative_gpa']:.2f}"),
        (_("Toplanmış kredit"), str(data["total_credits_earned"])),
        (_("GPA-a daxil kredit"), str(data["total_credits_gpa"])),
    ]
    if data.get("ects_total"):
        stats.append((_("Məzuniyyət yükü (ECTS)"), str(data["ects_total"])))
    for label, value in stats:
        sheet.ensure(15)
        sheet.text(_MARGIN, f"{label}:", size=9, color=_MUTED)
        sheet.text(_MARGIN + 150, value, size=9.5, bold=True)
        sheet.y += 15


def render_transcript_pdf(*, organization, student, record, data) -> bytes:
    """Build the official transcript PDF → raw bytes (subset fonts, compressed)."""
    import fitz

    doc = fitz.open()
    sheet = _Sheet(doc, _("AKADEMİK TRANSKRİPT"))
    _draw_header(sheet, organization, record, student)

    for semester in data["semesters"]:
        _draw_semester(sheet, semester)

    _draw_summary(sheet, data)
    sheet.finish_footers(timezone.localtime())

    brand = getattr(settings, "SITE_BRAND_NAME", "") or "Qərbi Kaspi Universiteti"
    doc.set_metadata(
        {
            "title": _("Akademik transkript"),
            "author": organization.name,
            "creator": getattr(organization, "name", "") or brand,
            "producer": f"{brand} / PyMuPDF",
        }
    )
    doc.subset_fonts()
    return doc.tobytes(deflate=True, garbage=3)
