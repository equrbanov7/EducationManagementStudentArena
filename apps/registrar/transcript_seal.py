"""Transkriptin «möhürü» — QR + yoxlama kodu (sahib 2026-10-18, ``apps.verification``).

Hər buraxılış ``verification.public.issue_sealed_document`` ilə möhürlənir: PDF-in imza zolağında QR +
qısa ünvan + kod, hər səhifənin altlığında kod. İstənilən şəxs ``/yoxla/<kod>/`` açıb sənədin etibarlı /
ləğv edilmiş olduğunu, sahibin MASKALI adını və yekun faktları (ixtisas, kredit, ÜOMG) görür.

Publik ``payload`` QƏSDƏN minimaldır — fənn-fənn qiymətlər, qrup, tələbə №, qəbul ili YOXDUR. Eyni gün eyni
faktlarla təkrar yükləmə eyni möhürü (eyni kod, eyni baytlar) qaytarır — servisin təkrar istifadə qaydası.

Rəsm funksiyası (``draw_verification_block``) ``transcript_pdf``-dən LOKAL import olunur (modul dövrü yox).
"""

from __future__ import annotations

from django.utils.translation import pgettext

from apps.registrar import transcript_pdf
from apps.verification.public import DocType, issue_sealed_document, mask_holder_name, qr_matrix

_QR_SIZE = 56
_QR_GAP = 8
_LABEL_SIZE = 6.8


def public_payload(*, organization, student, record, data) -> dict:
    """Publik səhifənin faktları — ``verification.facts.FACT_LABELS`` açarları ilə."""
    facts = []
    program = record.program if record is not None and record.program_id else None
    if program is not None:
        facts.append(["program", program.display_label_full])
        facts.append(["degree", str(program.get_degree_level_display())])
    facts.append(["credits", str(data.get("total_credits_earned", 0))])
    facts.append(["gpa", transcript_pdf._uomg_text(data.get("cumulative_gpa"))])
    if data.get("ects_total"):
        facts.append(["ects", str(data["ects_total"])])
    return {"org": organization.name, "holder": mask_holder_name(student), "facts": facts}


def _fit_size(value: str, *, width: float, size: float, bold=False) -> float:
    while size > 4.6 and transcript_pdf._text_width(value, size=size, bold=bold) > width:
        size -= 0.2
    return size


def draw_verification_block(sheet, mark, *, x: float, top: float, width: float) -> None:
    """İmza zolağının ortasına: vektor QR (``_QR_SIZE`` pt) + «Sənədi yoxlayın» + qısa ünvan + kod."""
    import fitz

    matrix = qr_matrix(mark.url)
    modules = len(matrix) or 1
    cell = _QR_SIZE / modules
    y0 = top - 10
    shape = sheet.page.new_shape()
    for row_index, row in enumerate(matrix):
        for col_index, dark in enumerate(row):
            if dark:
                left, upper = x + col_index * cell, y0 + row_index * cell
                shape.draw_rect(fitz.Rect(left, upper, left + cell, upper + cell))
    shape.finish(color=None, fill=transcript_pdf._DARK, width=0)
    shape.commit()

    text_x = x + _QR_SIZE + _QR_GAP
    text_w = max(20.0, width - _QR_SIZE - _QR_GAP)
    title = pgettext("registrar.pdf", "Sənədin həqiqiliyini yoxlayın")
    sheet.text_at(text_x, top, title, size=_fit_size(title, width=text_w, size=_LABEL_SIZE, bold=True), bold=True)
    sheet.text_at(
        text_x,
        top + 12,
        mark.short_url,
        size=_fit_size(mark.short_url, width=text_w, size=_LABEL_SIZE),
        color=transcript_pdf._BLUE,
    )
    code_label = pgettext("registrar.pdf", "Kod")
    sheet.text_at(text_x, top + 24, code_label, size=6.2, color=transcript_pdf._MUTED)
    sheet.text_at(text_x, top + 34, mark.code, size=_fit_size(mark.code, width=text_w, size=7.4, bold=True), bold=True)


def render_sealed_transcript(*, organization, student, record, data, issued_by, request=None):
    """Möhürlənmiş transkript → ``(pdf_bytes, seal)``. Səlahiyyət çağıran görünüşdə YOXLANILIB."""
    group = record.group if record is not None and record.group_id else None

    def _render(mark):
        return transcript_pdf.render_transcript_pdf(
            organization=organization, student=student, record=record, data=data, seal_mark=mark
        )

    return issue_sealed_document(
        organization=organization,
        doc_type=DocType.TRANSCRIPT,
        subject_user=student,
        title=pgettext("registrar.pdf", "Akademik transkript"),
        payload=public_payload(organization=organization, student=student, record=record, data=data),
        issued_by=issued_by,
        render=_render,
        scope_path=getattr(group, "path", "") or "",
        request=request,
    )


__all__ = ["draw_verification_block", "public_payload", "render_sealed_transcript"]
