"""Rəsmi akademik transkript PDF-i (U9) — PyMuPDF renderer.

Renders :func:`transcript.build_student_transcript` data into an A4 PDF using
the already-shipped PyMuPDF dependency (no new packages). The vendored DejaVu
Sans fonts (``static/fonts/``) provide full Azerbaijani glyph coverage (ə ğ ı
ö ş ü ç) — PDF base-14 fonts cannot render them. Fonts are subset on save so
the document stays small (~70KB instead of ~1.5MB).

Layout mirrors the official "AKADEMİK TRANSKRİPT" format used by AZ public
universities (UNEC reference): a ministry/university letterhead, a student
info block, one block per academic year with its (up to two) semesters laid
out side by side, a running "Semestrin sonu" / "İlin sonu" subtotal under each
semester/year, and a final "Ümumi" (cumulative credit + ÜOMG) + signature line.

The document is generated on the fly (never stored) and carries a footer note
that it is system-generated; issuance is written to the audit log by the view.
"""

from __future__ import annotations

from django.conf import settings
from django.utils import timezone
from django.utils.translation import pgettext

from core.constants import OrgUnitType


def _(text):
    """PDF labels live in their own i18n context — short words like "Kod" or
    "Yekun" already exist context-free elsewhere with unrelated translations."""
    return pgettext("registrar.pdf", text)


# ── Layout constants (A4 = 595 × 842 pt) ────────────────────────────────────
_PAGE_W, _PAGE_H = 595, 842
_MARGIN = 46
_CONTENT_W = _PAGE_W - 2 * _MARGIN
_BOTTOM_LIMIT = _PAGE_H - 64  # keep clear of the footer band
_COL_GAP = 18  # gap between the two semester columns of an academic year

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

# Well-known AZ brand name → its official English name. ``Organization`` has no
# dedicated English-name field, so this is a best-effort bilingual header for
# the tenants we know; unrecognised org names simply omit the English line.
_BRAND_EN_NAMES = {
    "Qərbi Kaspi Universiteti": "Western Caspian University",
}


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
    """Cursor-based page writer: tracks y, adds pages, draws the footer.

    Most drawing goes through the ``y``-cursor helpers (``text``/``rule``/
    ``fill_band``), but the two-column academic-year layout needs to place
    text at explicit coordinates without disturbing the cursor — the
    ``*_at``/``rule_at``/``fill_rect`` siblings do that.
    """

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
        self.text_at(x, self.y, value, size=size, bold=bold, color=color, right_edge=right_edge)

    def text_at(self, x, y, value, *, size=9, bold=False, color=_DARK, right_edge=None):
        """Draw text at an explicit ``(x, y)`` — does not touch the cursor."""
        font = _FONT_BOLD if bold else _FONT
        value = str(value)
        if right_edge is not None:
            x = right_edge - _text_width(value, size=size, bold=bold)
        self.page.insert_text((x, y), value, fontname=font, fontsize=size, color=color)

    def center(self, value, *, size=9, bold=False, color=_DARK):
        """Draw one line centered within the content width, at the cursor."""
        width = _text_width(str(value), size=size, bold=bold)
        x = _MARGIN + (_CONTENT_W - width) / 2
        self.text_at(x, self.y, value, size=size, bold=bold, color=color)

    def rule(self, *, color=_LINE, width=0.6):
        self.rule_at(_MARGIN, _PAGE_W - _MARGIN, self.y, color=color, width=width)

    def rule_at(self, x0, x1, y, *, color=_LINE, width=0.6):
        self.page.draw_line((x0, y), (x1, y), color=color, width=width)

    def fill_band(self, height, color):
        self.fill_rect(_MARGIN - 6, self.y - 9, _PAGE_W - _MARGIN + 6, self.y - 9 + height, color)

    def fill_rect(self, x0, y0, x1, y1, color):
        import fitz

        self.page.draw_rect(fitz.Rect(x0, y0, x1, y1), color=None, fill=color)

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


def _truncate(value: str, limit: int) -> str:
    value = str(value)
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _fmt_score(value) -> str:
    if value is None:
        return "—"
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text or "0"


def _faculty_name(group) -> str:
    """Walk the group OrgUnit's ancestor chain to find its Fakültə — groups sit
    several levels below (Faculty → Chair/Kafedra → Specialty → Group)."""
    if group is None:
        return ""
    if getattr(group, "unit_type", None) == OrgUnitType.FACULTY:
        return group.name
    try:
        ancestors = group.get_ancestors()
    except Exception:  # noqa: BLE001 — a broken hierarchy must never break the PDF
        return ""
    for ancestor in ancestors:
        if getattr(ancestor, "unit_type", None) == OrgUnitType.FACULTY:
            return ancestor.name
    return ""


def _draw_logo(sheet, organization, *, top, size):
    """Best-effort org logo at the top-left of the letterhead; never fatal."""
    logo = getattr(organization, "logo", None)
    if not logo:
        return False
    try:
        data = logo.open("rb").read()
        import fitz

        rect = fitz.Rect(_MARGIN, top - 2, _MARGIN + size, top - 2 + size)
        sheet.page.insert_image(rect, stream=data)
        return True
    except Exception:  # noqa: BLE001 — storage/format issues must not break the PDF
        return False


def _draw_letterhead(sheet, organization):
    """Ministry + university header — the official AZ transcript letterhead."""
    sheet.y += 4
    top = sheet.y
    sheet.text(_MARGIN, _("Azərbaycan Respublikası Təhsil Nazirliyi"), size=7.8, color=_MUTED)
    sheet.text(
        0,
        "Ministry of Education of the Republic of Azerbaijan",
        size=7.8,
        color=_MUTED,
        right_edge=_PAGE_W - _MARGIN,
    )
    sheet.y += 13

    logo_drawn = _draw_logo(sheet, organization, top=top, size=42)
    name_x = _MARGIN + (52 if logo_drawn else 0)

    sheet.text(name_x, organization.name, size=14.5, bold=True, color=_BLUE)
    sheet.y += 16
    en_name = _BRAND_EN_NAMES.get(organization.name, "")
    if en_name:
        sheet.text(name_x, en_name, size=9.5, color=_MUTED)
        sheet.y += 12
    sheet.text(name_x, _("PUBLİK HÜQUQİ ŞƏXS / PUBLIC LEGAL ENTITY"), size=7.3, bold=True, color=_MUTED)
    sheet.y += 11
    contact_bits = [
        b.strip() for b in (organization.address, organization.phone, organization.email) if b and b.strip()
    ]
    if contact_bits:
        sheet.text(name_x, "  ·  ".join(contact_bits), size=7.3, color=_MUTED)
        sheet.y += 11

    if logo_drawn:
        sheet.y = max(sheet.y, top + 42 + 6)
    sheet.y += 6
    sheet.rule(color=_BLUE, width=1.4)
    sheet.y += 20
    sheet.center(_("AKADEMİK TRANSKRİPT"), size=17, bold=True)
    sheet.y += 22


def _draw_student_info(sheet, record, student):
    """Fakültə / Tələbə № / İxtisas / Soyadı-adı / Təhsil pilləsi … — two columns."""
    full_name = student.get_full_name() or student.username
    pairs = []
    if record is not None and record.group_id:
        faculty = _faculty_name(record.group)
        if faculty:
            pairs.append((_("Fakültə"), faculty))
    pairs.append((_("Tələbə №"), student.username))
    if record is not None and record.program_id:
        pairs.append((_("İxtisas"), f"{record.program.code} — {record.program.name}"))
        pairs.append((_("Təhsil pilləsi"), record.program.get_degree_level_display()))
    pairs.append((_("Soyadı, adı"), full_name))
    if record is not None:
        if record.group_id:
            pairs.append((_("Qrup"), record.group.name))
        pairs.append((_("Qəbul ili"), str(record.admission_year)))
        pairs.append((_("Status"), record.get_status_display()))

    col_w = _CONTENT_W / 2
    for i in range(0, len(pairs), 2):
        sheet.ensure(16)
        for col, (label, value) in enumerate(pairs[i : i + 2]):
            x = _MARGIN + col * col_w
            sheet.text_at(x, sheet.y, f"{label}:", size=8.7, color=_MUTED)
            sheet.text_at(x + 92, sheet.y, _truncate(value, 40), size=8.7, bold=True)
        sheet.y += 15

    sheet.y += 6
    sheet.rule()
    sheet.y += 18


def _mini_cols(width):
    """Column layout (key, header, x-offset, width, right-aligned) for one
    semester's subject table, scaled to the column's ``width``."""
    name_w = width * 0.50
    credit_w = width * 0.16
    bal_w = width * 0.18
    letter_w = width - name_w - credit_w - bal_w
    return (
        ("name", _("Fənnin şifri və adı"), 0, name_w, False),
        ("credit", _("Kredit"), name_w, credit_w, True),
        ("bal", _("Bal"), name_w + credit_w, bal_w, True),
        ("letter", _("Dərəcə"), name_w + credit_w + bal_w, letter_w, True),
    )


def _draw_semester_column(sheet, semester, *, x, width, top):
    """Draw one semester's "Semestr | Fənn | Kredit | Bal | Dərəcə" mini-table
    at explicit coordinates (so two semesters can sit side by side); returns
    the y just below its "Semestrin sonu" subtotal row."""
    if semester is None:
        return top

    y = top
    sheet.text_at(x, y, f"{semester['season']} semestri", size=9.5, bold=True, color=_BLUE)
    sheet.text_at(0, y, f"ÜOMG {semester['gpa']:.2f}", size=7.8, color=_MUTED, right_edge=x + width)
    y += 13

    cols = _mini_cols(width)
    sheet.fill_rect(x - 3, y - 9, x + width + 3, y - 9 + 12.5, _ROW_ALT)
    for _key, label, offset, colw, right in cols:
        if right:
            sheet.text_at(0, y, label, size=6.6, bold=True, color=_MUTED, right_edge=x + offset + colw)
        else:
            sheet.text_at(x + offset, y, label, size=6.6, bold=True, color=_MUTED)
    y += 11

    name_limit = max(10, int(width / 4.4))
    for index, row in enumerate(semester["rows"]):
        if y > _BOTTOM_LIMIT - 24:
            break  # safety valve — a real semester never has enough rows to hit this
        if index % 2 == 1:
            sheet.fill_rect(x - 3, y - 9, x + width + 3, y - 9 + 12, _ROW_ALT)
        result = row["result"]
        definite = result["passed"] or result["failed"]
        code_name = f"{row['subject'].code}  {_truncate(row['subject'].name, name_limit)}"
        sheet.text_at(x, y, code_name, size=7.6)
        values = {
            "credit": str(row["credit"]),
            "bal": _fmt_score(result["total"]) if definite else "—",
            "letter": result["letter"] if row["in_gpa"] else "—",
        }
        for key, _label, offset, colw, _right in cols[1:]:
            bold = key == "bal" and definite
            sheet.text_at(0, y, values[key], size=7.6, bold=bold, right_edge=x + offset + colw)
        y += 12

    y += 4
    sheet.rule_at(x, x + width, y)
    y += 10
    sheet.text_at(x, y, _("Semestrin sonu"), size=7.4, color=_MUTED)
    figures = _("Kredit %(credit)s · ÜOMG %(gpa)s") % {
        "credit": semester["credits_earned"],
        "gpa": f"{semester['gpa']:.2f}",
    }
    sheet.text_at(0, y, figures, size=7.4, bold=True, right_edge=x + width)
    y += 16
    return y


def _draw_year(sheet, year):
    """One "Akademik il 2025-2026" block: up to two semester columns side by
    side (a third — Yay — falls back to full width below), then "İlin sonu"."""
    semesters = year["semesters"]
    left = semesters[0] if len(semesters) >= 1 else None
    right = semesters[1] if len(semesters) >= 2 else None
    extra = semesters[2:]

    max_rows = max((len(s["rows"]) for s in (left, right) if s), default=0)
    estimated = 34 + max_rows * 12 + 40
    sheet.ensure(min(estimated, _BOTTOM_LIMIT - _MARGIN - 10))

    sheet.text(_MARGIN, _("Akademik il %(year)s") % {"year": year["year_label"]}, size=11, bold=True, color=_BLUE)
    sheet.y += 16
    top = sheet.y
    col_w = (_CONTENT_W - _COL_GAP) / 2
    left_bottom = _draw_semester_column(sheet, left, x=_MARGIN, width=col_w, top=top)
    right_bottom = _draw_semester_column(sheet, right, x=_MARGIN + col_w + _COL_GAP, width=col_w, top=top)
    sheet.y = max(left_bottom, right_bottom, top)

    for extra_semester in extra:
        sheet.ensure(40)
        sheet.y = _draw_semester_column(sheet, extra_semester, x=_MARGIN, width=_CONTENT_W, top=sheet.y + 6)

    sheet.fill_rect(_MARGIN - 6, sheet.y - 2, _PAGE_W - _MARGIN + 6, sheet.y - 2 + 16, _ROW_ALT)
    sheet.text(_MARGIN, _("İlin sonu"), size=8.5, bold=True)
    figures = _("Kredit %(credit)s · ÜOMG %(gpa)s") % {"credit": year["credits_earned"], "gpa": f"{year['gpa']:.2f}"}
    sheet.text(0, figures, size=8.5, bold=True, right_edge=_PAGE_W - _MARGIN)
    sheet.y += 26


def _draw_footer(sheet, data, generated_at):
    """ "Ümumi" cumulative row + the dean signature / issue-date line."""
    sheet.ensure(100)
    sheet.y += 2
    sheet.rule(color=_BLUE, width=1.2)
    sheet.y += 18
    sheet.text(_MARGIN, _("Ümumi"), size=11, bold=True, color=_BLUE)
    figures = _("Kredit %(credit)s · Kumulyativ ÜOMG %(gpa)s") % {
        "credit": data["total_credits_earned"],
        "gpa": f"{data['cumulative_gpa']:.2f}",
    }
    sheet.text(0, figures, size=10, bold=True, right_edge=_PAGE_W - _MARGIN)
    sheet.y += 16
    if data.get("ects_total"):
        sheet.text(_MARGIN, f"{_('Məzuniyyət yükü (ECTS)')}: {data['ects_total']}", size=8.3, color=_MUTED)
        sheet.y += 17

    sheet.y += 26
    sheet.text(_MARGIN, f"{_('Fakültə dekanı')} " + "_" * 26, size=9.5)
    stamp = generated_at.strftime("%d.%m.%Y")
    sheet.text(0, f"{_('Verilmə tarixi')}: {stamp}", size=9.5, right_edge=_PAGE_W - _MARGIN)
    sheet.y += 20


def render_transcript_pdf(*, organization, student, record, data) -> bytes:
    """Build the official transcript PDF → raw bytes (subset fonts, compressed)."""
    import fitz

    doc = fitz.open()
    sheet = _Sheet(doc, _("AKADEMİK TRANSKRİPT"))
    _draw_letterhead(sheet, organization)
    _draw_student_info(sheet, record, student)

    for year in data["years"]:
        _draw_year(sheet, year)

    generated_at = timezone.localtime()
    _draw_footer(sheet, data, generated_at)
    sheet.finish_footers(generated_at)

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
