"""question_library paketi — export."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.translation import pgettext

from apps.exams.services.access_policy import _ensure_teacher
from apps.exams.services.question_bank_attach import accessible_banks
from core.tenancy import get_request_organization

from ._shared import (
    _BANK_TEMPLATE_TEST_TXT,
    _BANK_TEMPLATE_WRITTEN_TXT,
    _normalize_format,
)


@login_required
def question_bank_template_download(request, bank_id):
    _ensure_teacher(request.user)
    organization = get_request_organization(request)
    bank = get_object_or_404(accessible_banks(request.user, organization), id=bank_id)

    q_format = _normalize_format(bank.default_question_type)
    template_text = _BANK_TEMPLATE_WRITTEN_TXT if q_format == "written" else _BANK_TEMPLATE_TEST_TXT

    # Yalnız TXT — DOCX importu söndürüldüyü üçün DOCX şablonu da verilmir.
    response = HttpResponse(template_text, content_type="text/plain; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="sual_sablonu.txt"'
    return response


@login_required
def question_bank_word_export(request, bank_id):
    """
    Bankdakı sualları Word (.docx) faylı kimi export edir.

    Format import parseri ilə uyğundur (düz cavab `*` prefiksi ilə) —
    müəllim faylı redaktə edib yenidən toplu yükləmə ilə import edə bilər.
    İcazə: bankın əlçatan olduğu istifadəçi (accessible_banks → tenant scoped).
    ?language=az kimi parametrlə dil üzrə filtr mümkündür.
    """
    from urllib.parse import quote

    from apps.exams.services.question_word_export import bank_questions_payload, build_questions_docx

    _ensure_teacher(request.user)
    organization = get_request_organization(request)
    bank = get_object_or_404(accessible_banks(request.user, organization), id=bank_id)

    language = (request.GET.get("language") or "").strip().lower() or None

    # C2 (2026-07-03): böyük banklar worker-də hazırlanır (export job).
    from django.conf import settings as _settings

    threshold = getattr(_settings, "EXPORT_SYNC_MAX_ROWS", 500)
    if bank.library_questions.count() > threshold:
        from apps.exams.views.teacher.extract_jobs import start_export_job

        return start_export_job(
            request,
            export_name="bank_word",
            params={"bank_id": bank.pk, "language": language or ""},
        )

    payload = bank_questions_payload(bank, language=language)
    if not payload:
        messages.warning(request, pgettext("exams.view.bank.message", "Export üçün aktiv sual tapılmadı."))
        return redirect("exams:question_bank_detail", bank_id=bank.id)

    subtitle_parts = [f"Sual sayı: {len(payload)}"]
    if bank.subject:
        subtitle_parts.insert(0, f"Fənn: {bank.subject}")
    if language:
        subtitle_parts.append(f"Dil: {language.upper()}")

    buffer = build_questions_docx(
        title=f"Sual bankı — {bank.name}",
        subtitle=" · ".join(subtitle_parts),
        questions=payload,
    )
    response = HttpResponse(
        buffer.read(),
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    safe_name = quote(f"{bank.name}_suallar.docx")
    response["Content-Disposition"] = f"attachment; filename*=UTF-8''{safe_name}"
    return response
