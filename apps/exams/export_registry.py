"""Export job builder registry (C2, 2026-07-03).

Böyük datasetli fayl exportları (xlsx/docx) sorğu yerinə worker-də qurulur.
Hər builder `(filename, content_type, bytes)` qaytarır. İcazə yoxlaması VIEW
qatında (job yaradılmazdan əvvəl) aparılır; burada yalnız job sahibliyi ilə
uyğunluq guard-ları var (org mismatch → ValueError).

Yeni export əlavə etmək: builder yaz → `_BUILDERS`-ə ad ver → view-da
`start_export_job(request, export_name=..., params=...)` çağır.
"""

DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _guard_org(obj_org_id, job_organization):
    """View icazə verdiyi konteksti worker-də təsdiqləyir."""
    job_org_id = job_organization.id if job_organization is not None else None
    if job_org_id is not None and obj_org_id is not None and obj_org_id != job_org_id:
        raise ValueError("export job organization mismatch")


def _build_exam_results_xlsx(*, user, organization, params):
    from apps.exams.models import Exam
    from apps.exams.views.teacher.results._export_builder import build_exam_results_xlsx_export
    from apps.exams.views.teacher.results._helpers import _apply_results_filters_from_params

    exam = Exam.objects.select_related("organization").get(pk=params["exam_id"])
    _guard_org(exam.organization_id, organization)

    attempts_qs, _ = _apply_results_filters_from_params(exam, params.get("filters") or {})
    return build_exam_results_xlsx_export(exam, list(attempts_qs))


def _build_bank_word(*, user, organization, params):
    from urllib.parse import quote

    from apps.exams.models import QuestionBank
    from apps.exams.services.question_word_export import bank_questions_payload, build_questions_docx

    bank = QuestionBank.objects.get(pk=params["bank_id"])
    _guard_org(bank.organization_id, organization)

    language = (params.get("language") or "").strip().lower() or None
    payload = bank_questions_payload(bank, language=language)
    if not payload:
        raise ValueError("empty_export")

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
    filename = quote(f"{bank.name}_suallar.docx")
    return filename, DOCX_CONTENT_TYPE, buffer.read()


_BUILDERS = {
    "exam_results_xlsx": _build_exam_results_xlsx,
    "bank_word": _build_bank_word,
}


def run_export(name, *, user, organization, params):
    """Builder-i icra edir → (filename, content_type, bytes)."""
    try:
        builder = _BUILDERS[name]
    except KeyError:
        raise ValueError(f"Naməlum export: {name!r}")
    return builder(user=user, organization=organization, params=params)
