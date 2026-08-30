"""Sillabusun PDF nüsxəsi (tələbənin «PDF yüklə» düyməsi) — PyMuPDF renderer.

Məzmun :func:`apps.syllabus.document.build_document`-dən gəlir, yəni ekranda
göründüyü mətnin EYNİSİDİR — PDF ayrıca formatlaşdırma qaydası saxlamır.

⚠️ Səhifə primitivləri (``_Sheet``, font boru xətti, WCU palitrası, loqo)
``transcript_pdf``-dən idxal olunur. Onlar orada modul-private adlarla qalıb,
çünki indiyə qədər ikinci istehlakçı yox idi; İKİNCİ NÜSXƏ yazmaqdansa tək
tətbiqi paylaşmaq seçilib — belədə transkriptin və sillabusun blankı, şrift
subset-i və alt qeydi bir yerdən dəyişir. Blank başlığı fərqlidir, ona görə
``_draw_letterhead`` təkrar istifadə OLUNMUR: ona sabit «AKADEMİK TRANSKRİPT»
adı bişirilib.
"""

from __future__ import annotations

from django.conf import settings
from django.utils import timezone
from django.utils.translation import pgettext

from .transcript_pdf import (
    _BLUE,
    _BRAND_EN_NAMES,
    _CONTENT_W,
    _DARK,
    _MARGIN,
    _MUTED,
    _PAGE_W,
    _Sheet,
    _draw_logo,
    _text_width,
)


def _(text):
    return pgettext("registrar.pdf", text)


_BODY_SIZE = 8.6
_LINE_STEP = 12.0


def _wrap(value: str, *, size: float, width: float, bold=False) -> list:
    """Sətri verilmiş enə görə sözlərdən bölür (PyMuPDF avtomatik sarımır)."""
    words = str(value).split()
    if not words:
        return [""]
    lines, current = [], words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if _text_width(candidate, size=size, bold=bold) <= width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _draw_letterhead(sheet, organization, *, title):
    """Universitet blankı + sənədin adı (transkriptdəkinin sillabus variantı)."""
    sheet.y += 4
    top = sheet.y
    sheet.text(_MARGIN, _("Azərbaycan Respublikası Təhsil Nazirliyi"), size=7.8, color=_MUTED)
    sheet.y += 13

    logo_drawn = _draw_logo(sheet, organization, top=top, size=42)
    name_x = _MARGIN + (52 if logo_drawn else 0)

    sheet.text(name_x, organization.name, size=14.5, bold=True, color=_BLUE)
    sheet.y += 16
    en_name = _BRAND_EN_NAMES.get(organization.name, "")
    if en_name:
        sheet.text(name_x, en_name, size=9.5, color=_MUTED)
        sheet.y += 12

    if logo_drawn:
        sheet.y = max(sheet.y, top + 42 + 6)
    sheet.y += 6
    sheet.rule(color=_BLUE, width=1.4)
    sheet.y += 20
    sheet.center(title, size=16, bold=True)
    sheet.y += 20


def _draw_identity(sheet, document):
    """Fənn kodu/adı, ixtisas, semestr, versiya + status — iki sütunlu şapka."""
    pairs = [
        (_("Fənn"), f"{document['code']} — {document['name']}"),
        (_("İxtisas"), document["program"] or "—"),
        (_("Semestr"), document["period"] or "—"),
        (_("Müəllim"), document["author"] or "—"),
        (_("Versiya"), f"{document['version']} · {document['status_label']}"),
        (
            _("Təsdiq"),
            (
                f"{document['approved_at'].strftime('%d.%m.%Y')}"
                + (f" · {document['approved_by']}" if document["approved_by"] else "")
                if document["approved_at"]
                else _("təsdiqlənməyib")
            ),
        ),
    ]
    label_w = 74
    for label, value in pairs:
        sheet.ensure(_LINE_STEP + 2)
        sheet.text(_MARGIN, label, size=8, color=_MUTED)
        for index, line in enumerate(_wrap(value, size=8.6, width=_CONTENT_W - label_w)):
            sheet.text_at(_MARGIN + label_w, sheet.y, line, size=8.6, bold=(index == 0), color=_DARK)
            sheet.y += _LINE_STEP
    sheet.y += 4
    sheet.rule()
    sheet.y += 16


def _draw_block(sheet, block):
    """Bir məzmun bloku: başlıq + çoxsətirli gövdə (hər sətir ayrıca sarılır)."""
    sheet.ensure(46)
    sheet.text(_MARGIN, block["title"].upper(), size=9, bold=True, color=_BLUE)
    sheet.y += 6
    sheet.rule()
    sheet.y += 14
    for raw_line in str(block["body"]).split("\n"):
        for line in _wrap(raw_line, size=_BODY_SIZE, width=_CONTENT_W):
            sheet.ensure(_LINE_STEP)
            sheet.text(_MARGIN, line, size=_BODY_SIZE)
            sheet.y += _LINE_STEP
    sheet.y += 10


def render_syllabus_pdf(*, organization, syllabus, version, document) -> bytes:
    """Sillabus sənədini A4 PDF-ə çevirir → xam baytlar (subset şrift, sıxılmış)."""
    import fitz

    title = _("FƏNN SİLLABUSU")
    doc = fitz.open()
    sheet = _Sheet(doc, title)
    _draw_letterhead(sheet, organization, title=title)
    _draw_identity(sheet, document)
    for block in document["blocks"]:
        _draw_block(sheet, block)

    _draw_validity_note(sheet, document)
    generated_at = timezone.localtime()
    sheet.finish_footers(generated_at)

    brand = getattr(settings, "SITE_BRAND_NAME", "") or organization.name
    doc.set_metadata(
        {
            "title": f"{document['code']} — {document['name']} ({document['version']})",
            "author": organization.name,
            "creator": organization.name,
            "producer": f"{brand} / PyMuPDF",
        }
    )
    doc.subset_fonts()
    return doc.tobytes(deflate=True, garbage=3)


def _draw_validity_note(sheet, document):
    """Təsdiqlənməmiş versiyanın PDF-i RƏSMİ sənəd kimi oxunmamalıdır.

    Tələbə onsuz da yalnız ``APPROVED`` nüsxə alır, amma müəllim öz qaralamasını
    da yükləyə bilir — belə fayl əlbəyaxa paylanarsa yanlış anlaşılmasın deyə
    vəziyyət açıq yazılır.
    """
    from apps.syllabus.constants import SyllabusStatus

    sheet.ensure(40)
    sheet.y += 6
    sheet.rule(color=_BLUE, width=1.0)
    sheet.y += 14
    if document["status"] == SyllabusStatus.APPROVED.value:
        note = _("Bu sillabus kafedra tərəfindən təsdiqlənib və cari semestrdə qüvvədədir.")
    else:
        note = _("DİQQƏT: bu versiya təsdiqlənməyib — rəsmi sənəd deyil, yalnız iş nüsxəsidir.")
    for line in _wrap(note, size=8, width=_CONTENT_W):
        sheet.text(_MARGIN, line, size=8, color=_MUTED)
        sheet.y += _LINE_STEP
    sheet.y += 4
    sheet.text(0, f"{document['code']} · {document['version']}", size=8, color=_MUTED, right_edge=_PAGE_W - _MARGIN)


__all__ = ["render_syllabus_pdf"]
