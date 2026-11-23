"""
Sualların Word (.docx) exportu — sual bankı və imtahan sualları üçün.

Format QƏSDƏN import parserinin qəbul etdiyi formatla eynidir (round-trip):

    1. Sual mətni
    A) variant
    *B) düz variant     <- düz cavab * prefiksi ilə
    C) variant

    2. Növbəti sual ...

Beləliklə müəllim export etdiyi faylı (redaktədən sonra) yenidən toplu
yükləmə ilə geri import edə bilər. Yazılı suallar sadəcə nömrələnmiş
mətn kimi yazılır.

Performans: suallar `prefetch_related("options")` ilə gəlir — option-lar
üçün əlavə sorğu yoxdur; sənəd yaddaşda (BytesIO) qurulur.
"""

from io import BytesIO

from django.utils.translation import pgettext

OPTION_LABELS = "ABCDEFGH"


def _question_lines(index, text, options):
    """
    Bir sualın sətirlərini qaytarır: nömrəli mətn + (varsa) variantlar.
    options: iterable of (label_or_None, text, is_correct)
    """
    lines = [f"{index}. {(text or '').strip()}"]
    for opt_index, (label, opt_text, is_correct) in enumerate(options):
        letter = (label or "").strip().upper() or OPTION_LABELS[opt_index % len(OPTION_LABELS)]
        prefix = "*" if is_correct else ""
        lines.append(f"{prefix}{letter}) {(opt_text or '').strip()}")
    return lines


class WordExportImageError(ValueError):
    """A complete visual question sheet could not be exported."""


def _append_picture(paragraph, field, remaining_bytes, max_width):
    from docx.shared import Inches

    from apps.exams.services.parsing.docx_reader import MAX_IMAGE_BYTES, normalize_image_bytes

    try:
        with field.storage.open(field.name, "rb") as source:
            picture = normalize_image_bytes(source.read(MAX_IMAGE_BYTES + 1))
    except (OSError, ValueError):
        picture = None
    if not picture or len(picture[0]) > remaining_bytes:
        raise WordExportImageError(pgettext("exams.export", "question_picture_export_failed"))
    data, _, width, height = picture
    # Preserve aspect ratio and fit both wide charts and long formula screenshots on a page.
    display_width = min(max_width, Inches(width / 96), Inches(7.5 * width / height))
    run = paragraph.add_run()
    run.add_break()
    run.add_picture(BytesIO(data), width=int(display_width))
    return len(data)


def build_questions_docx(*, title, questions, subtitle=""):
    """
    Sualları .docx sənədinə yazır və BytesIO qaytarır.

    questions: iterable of dicts:
        {"text": str, "options": [(label, text, is_correct), ...]}
        (options boş ola bilər — yazılı sual)
    """
    from docx import Document

    from apps.exams.services.parsing import MAX_UPLOAD_BYTES

    doc = Document()
    doc.add_heading(title, level=1)
    if subtitle:
        doc.add_paragraph(subtitle)
    doc.add_paragraph(
        pgettext(
            "exams.export",
            "Qeyd: düz cavablar variantın əvvəlindəki * işarəsi ilə qeyd olunub. "
            "Bu faylı redaktə edib yenidən toplu yükləmə ilə import edə bilərsiniz.",
        )
    )

    section = doc.sections[0]
    max_width = section.page_width - section.left_margin - section.right_margin
    remaining_bytes = MAX_UPLOAD_BYTES
    for index, question in enumerate(questions, start=1):
        images = question.get("images", {})
        for line_no, line in enumerate(_question_lines(index, question["text"], question["options"])):
            paragraph = doc.add_paragraph(line)
            if line_no == 0:
                # Sual mətni qalın — oxunaqlıq üçün (parser üçün əhəmiyyətsizdir).
                for run in paragraph.runs:
                    run.bold = True
            if line_no in images:
                remaining_bytes -= _append_picture(paragraph, images[line_no], remaining_bytes, max_width)
        # Suallar arası boş sətir — import parseri bölgü üçün bundan istifadə edir.
        doc.add_paragraph("")

    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer


def _questions_payload(questions):
    payload = []
    for question in questions:
        images = {0: question.image} if question.image else {}
        options = []
        for position, option in enumerate(question.options.all(), start=1):
            options.append((option.label, option.text, option.is_correct))
            if option.image:
                images[position] = option.image
        payload.append({"text": question.text, "options": options, "images": images})
    return payload


def bank_questions_payload(bank, *, language=None, only_active=True):
    """
    BankQuestion → export payload. Options tək prefetch ilə yüklənir.
    """
    questions = bank.library_questions.all()
    if only_active:
        questions = questions.filter(is_active=True)
    if language:
        questions = questions.filter(language=language)
    questions = questions.order_by("created_at", "id").prefetch_related("options")

    return _questions_payload(questions)


def exam_questions_payload(exam, *, language=None):
    """
    ExamQuestion → export payload (imtahanın snapshot sualları).
    """
    questions = exam.questions.all()
    if language:
        questions = questions.filter(language=language)
    questions = questions.order_by("order", "id").prefetch_related("options")

    return _questions_payload(questions)


__all__ = ["bank_questions_payload", "build_questions_docx", "exam_questions_payload"]
