"""«Təhsil aldığı yer haqqında arayış» PDF-i — PyMuPDF renderer (sahib 2026-10-19).

Transkriptlə EYNİ yığın: ``transcript_pdf`` vərəq sinfi (DejaVu şriftləri — ə ğ ı ö ş ü ç), ölçü funksiyası,
loqo mənbəyi; QR bloku ``transcript_seal.draw_verification_block``-dır (rəng parametri ilə qara). Transkript
modulu ölçü büdcəsindədir (600) — arayış ona əlavə edilmir, köməkçiləri buradan idxal edir.

Rəsmi blank: ağ fon, qara mətn, universitet başlığı, «Arayış № …» + tarix, mətn bəndi, «Dekan» və «Tədris
şöbəsinin müdiri / Tələbə Xidmətləri» imza xətləri, «M.Y.» (möhür yeri), QR + yoxlama kodu. Renderer
DETERMİNİSTİKDİR: eyni ``facts`` + eyni ``mark`` → eyni baytlar (``no_new_id=True``) — möhür servisinin
gündaxili təkrar istifadə qaydası bunun üzərində qurulub.
"""

from __future__ import annotations

import hashlib

from django.conf import settings
from django.utils.translation import pgettext

from apps.registrar import transcript_pdf as tp
from apps.registrar.transcript_pdf_text import line_height, wrap_lines

_BLACK = (0, 0, 0)
_RULE = (0.25, 0.25, 0.25)
_PREFIX = "AR"
_BODY_SIZE = 11.5
_CTX = "registrar.arayis"

#: Azərbaycan hərflərinin BÖYÜK yazılışı — ``str.upper()`` «i»-ni nöqtəsiz «I» edir («UNIVERSITETI»).
_AZ_UPPER = str.maketrans({"i": "İ", "ı": "I"})


def az_upper(value: str) -> str:
    return str(value or "").translate(_AZ_UPPER).upper()


def build_document_number(*, record_id, issued_at) -> str:
    """«AR-20261019-1A2B3C4D» — qeyd + buraxılış anından DETERMİNİSTİK (transkript naxışı, prefiks «AR»)."""
    digest = hashlib.sha256(f"arayis|{record_id}|{issued_at.isoformat()}".encode()).hexdigest()
    return f"{_PREFIX}-{issued_at:%Y%m%d}-{digest[:8].upper()}"


def _width(value, *, size, bold=False) -> float:
    return tp._text_width(str(value), size=size, bold=bold)


def _centered(sheet, value, *, size, bold=False):
    x = tp._MARGIN + (tp._CONTENT_W - _width(value, size=size, bold=bold)) / 2
    sheet.text_at(x, sheet.y, value, size=size, bold=bold, color=_BLACK)


def _draw_header(sheet, organization):
    """Loqo (varsa) + nazirlik sətri + «QƏRBİ KASPİ UNİVERSİTETİ» + əlaqə sətri, altında qara xətt."""
    logo = tp._logo_bytes(organization)
    if logo:
        try:
            import fitz

            left = tp._MARGIN + (tp._CONTENT_W - 46) / 2
            sheet.page.insert_image(fitz.Rect(left, sheet.y - 8, left + 46, sheet.y + 38), stream=logo)
            sheet.y += 52
        except Exception:  # noqa: BLE001 — loqo problemi rəsmi blankı dayandırmır
            pass
    _centered(sheet, az_upper(pgettext(_CTX, "Azərbaycan Respublikası Təhsil Nazirliyi")), size=8.5)
    sheet.y += 18
    _centered(sheet, az_upper(organization.name), size=16, bold=True)
    sheet.y += 15
    contact = "  ·  ".join(
        part.strip() for part in (organization.address, organization.phone, organization.email) if part and part.strip()
    )
    if contact:
        _centered(sheet, contact, size=8)
        sheet.y += 10
    sheet.y += 4
    sheet.rule_at(tp._MARGIN, tp._PAGE_W - tp._MARGIN, sheet.y, color=_BLACK, width=1.2)
    sheet.y += 26


def _draw_number_and_date(sheet, number, issued_at):
    label = pgettext(_CTX, "Arayış № %(number)s") % {"number": number}
    sheet.text_at(tp._MARGIN, sheet.y, label, size=10, bold=True, color=_BLACK)
    date_text = pgettext(_CTX, "Tarix: %(date)s") % {"date": f"{issued_at:%d.%m.%Y}"}
    sheet.text_at(0, sheet.y, date_text, size=10, color=_BLACK, right_edge=tp._PAGE_W - tp._MARGIN)
    sheet.y += 46
    _centered(sheet, az_upper(pgettext(_CTX, "Arayış")), size=18, bold=True)
    sheet.y += 34


def _paragraph(sheet, text, *, size=_BODY_SIZE, indent=28):
    """Bənd: birinci sətir abzasla, qalanları tam endə; sözbəsöz ölçülərək bölünür (heç nə kəsilmir)."""
    text = " ".join(str(text or "").split())
    step = line_height(size) + 3
    width = tp._CONTENT_W
    first, *_ = wrap_lines(text, width=width - indent, measure=lambda t: _width(t, size=size)) or [""]
    sheet.text_at(tp._MARGIN + indent, sheet.y, first, size=size, color=_BLACK)
    sheet.y += step
    rest = text[len(first) :].strip()
    if rest:
        for line in wrap_lines(rest, width=width, measure=lambda t: _width(t, size=size)):
            sheet.text_at(tp._MARGIN, sheet.y, line, size=size, color=_BLACK)
            sheet.y += step
    sheet.y += 6


def _signature_line(sheet, label, *, top):
    x_line = tp._MARGIN + 300
    for index, line in enumerate(wrap_lines(label, width=290, measure=lambda t: _width(t, size=10.5, bold=True))):
        sheet.text_at(tp._MARGIN, top + index * 13, line, size=10.5, bold=True, color=_BLACK)
    sheet.rule_at(x_line, x_line + 140, top + 2, color=_BLACK, width=0.7)
    sheet.text_at(x_line + 34, top + 13, pgettext(_CTX, "(imza)"), size=7.5, color=_BLACK)


def _draw_signatures(sheet, seal_mark):
    sheet.y += 30
    top = sheet.y
    _signature_line(sheet, pgettext(_CTX, "Fakültə dekanı"), top=top)
    _signature_line(sheet, pgettext(_CTX, "Tədris şöbəsinin müdiri / Tələbə Xidmətləri"), top=top + 44)
    sheet.text_at(tp._PAGE_W - tp._MARGIN - 42, top + 70, pgettext(_CTX, "M.Y."), size=11, bold=True, color=_BLACK)
    sheet.y = top + 120
    if seal_mark is not None:
        from apps.registrar.transcript_seal import draw_verification_block

        draw_verification_block(sheet, seal_mark, x=tp._MARGIN, top=sheet.y, width=260, color=_BLACK)
        sheet.y += 60


def _draw_footer(sheet, number, issued_at, seal_mark):
    top = tp._PAGE_H - 54
    sheet.rule_at(tp._MARGIN, tp._PAGE_W - tp._MARGIN, top, color=_RULE, width=0.5)
    head = f"{pgettext(_CTX, 'Arayış №')} {number}  ·  {issued_at:%d.%m.%Y %H:%M}"
    if seal_mark is not None:
        head = f"{head}  ·  {pgettext('registrar.pdf', 'Yoxlama kodu')}: {seal_mark.code}"
    sheet.text_at(tp._MARGIN, top + 12, head, size=7, bold=True, color=_BLACK)
    note = pgettext("registrar.pdf", "Bu sənəd sistem tərəfindən yaradılıb və elektron formada etibarlıdır.")
    sheet.text_at(tp._MARGIN, top + 22, note, size=7, color=_BLACK)


def render_certificate_pdf(*, organization, facts, body: list[str], seal_mark=None) -> bytes:
    """Arayış PDF → baytlar. ``body`` — hazır mətn bəndləri (``enrollment_certificate.body_paragraphs``)."""
    from django.utils import timezone

    import fitz

    issued_at = timezone.localtime(seal_mark.issued_at) if seal_mark is not None else timezone.localtime()
    number = build_document_number(record_id=facts.record_id, issued_at=issued_at)

    doc = fitz.open()
    sheet = tp._Sheet(doc, pgettext(_CTX, "Arayış"))
    _draw_header(sheet, organization)
    _draw_number_and_date(sheet, number, issued_at)
    for paragraph in body:
        _paragraph(sheet, paragraph)
    _draw_signatures(sheet, seal_mark)
    _draw_footer(sheet, number, issued_at, seal_mark)

    brand = getattr(settings, "SITE_BRAND_NAME", "") or "Qərbi Kaspi Universiteti"
    doc.set_metadata(
        {
            "title": pgettext("verification.doc_type", "Təhsil aldığı yer haqqında arayış"),
            "author": organization.name,
            "creator": getattr(organization, "name", "") or brand,
            "producer": f"{brand} / PyMuPDF",
        }
    )
    doc.subset_fonts()
    return doc.tobytes(deflate=True, garbage=3, no_new_id=True)


__all__ = ["az_upper", "build_document_number", "render_certificate_pdf"]
