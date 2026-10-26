"""Transkript PDF ixracı (U9) — tələbənin özü + registrar səlahiyyətli işçi.

Two thin views over :func:`transcript_pdf.render_transcript_pdf`:

* ``my_transcript_pdf`` — the requesting student downloads their **own**
  transcript (tenant scoping from the active org / RLS).
* ``student_transcript_pdf`` — sənəd verə bilən işçi tələbənin transkriptini yükləyir. Qapı
  ``document_access`` (sahib 2026-10-19): org-wide ``course.edit`` (köhnə yol — rektor, prorektor, RİM)
  və ya ``transcript.issue`` (Tədris şöbəsinin müdiri, Tələbə xidmətləri, RİM rəhbəri — bütün təşkilat;
  dekan / dekan müavini — yalnız öz fakültəsi). Əhatədən kənar qeyd 404.
* ``student_enrollment_certificate_pdf`` — «Təhsil aldığı yer haqqında arayış» (POST, eyni qapı); yalnız
  aktiv tələbəyə, əks halda 409 (``enrollment_certificate.refusal_for``).

Möhürlü sənəd buraxılışı möhür sətri YAZIR — «başqasının adından» (view-as) rejimində hər üç yol 403.

The PDF is generated on the fly and never stored; each issuance is written to
the audit log (official-document trail).
"""

from __future__ import annotations

from urllib.parse import quote

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.translation import pgettext
from django.views.decorators.http import require_POST

from apps.registrar import document_access, enrollment_certificate, transcript_issue
from apps.registrar.audit_write import create_audit_row
from apps.registrar.models import StudentAcademicRecord


def _audit_issue(organization, record, by_user, seal=None):
    """Best-effort audit entry for an issued transcript — ``transcript_issue.audit_transcript_issue``."""
    transcript_issue.audit_transcript_issue(organization, record, by_user, seal)


#: AZ hərflərinin ASCII qarşılığı — `Content-Disposition`-un ASCII geri dönüşü
#: oxunaqlı qalsın («Əli Şıxlınski» → `Eli_Sixlinski`, `li_xlnski` YOX). UTF-8
#: adı (RFC 5987) onsuz da tam gedir; bu yalnız köhnə müştəri üçündür.
_ASCII_FOLD = str.maketrans(
    {
        "ə": "e",
        "Ə": "E",
        "ö": "o",
        "Ö": "O",
        "ü": "u",
        "Ü": "U",
        "ğ": "g",
        "Ğ": "G",
        "ı": "i",
        "İ": "I",
        "ç": "c",
        "Ç": "C",
        "ş": "s",
        "Ş": "S",
    }
)


def _transcript_filename(student) -> str:
    """`Transkript_Ad_Soyad_2026-09-10.pdf` — ``transcript_issue.transcript_filename`` (müraciət yolu ilə ortaq)."""
    return transcript_issue.transcript_filename(student)


def _attachment(payload: bytes, filename: str) -> HttpResponse:
    """`Content-Disposition: attachment` — ASCII geri dönüşü + RFC 5987 UTF-8 adı."""
    response = HttpResponse(payload, content_type="application/pdf")
    ascii_name = filename.translate(_ASCII_FOLD).encode("ascii", "ignore").decode("ascii") or "transkript.pdf"
    response["Content-Disposition"] = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"
    return response


def _render_response(*, organization, student, record, request):
    """``(HttpResponse, seal)`` — hər buraxılış QR + yoxlama kodu ilə möhürlənir (``transcript_seal``)."""
    try:
        payload, seal = transcript_issue.issue_student_transcript(
            organization=organization,
            student=student,
            record=record,
            issued_by=getattr(request, "real_user", None) or request.user,
            request=request,
        )
    except enrollment_certificate.CertificateRefused as refusal:
        raise Http404 from refusal  # nothing to certify yet
    return _attachment(payload, _transcript_filename(student)), seal


@login_required
def my_transcript_pdf(request):
    """The requesting student's own transcript as PDF.

    FAIL-CLOSED: ``public.STUDENT_TRANSCRIPT_SELF_SERVICE`` bağlı ikən 404 —
    kabinetdə bölmə gizlədildiyi halda faylın birbaşa URL ilə yüklənməsi
    gizlətməni mənasız edərdi. Əməkdaş yolu (``student_transcript_pdf``)
    bu qapıdan KEÇMİR.
    """
    from apps.registrar.public import STUDENT_TRANSCRIPT_SELF_SERVICE

    if not STUDENT_TRANSCRIPT_SELF_SERVICE:
        raise Http404
    if document_access.blocked_by_view_as(request):
        return _view_as_refusal(request)
    organization = getattr(request, "organization", None)
    if organization is None:
        raise Http404
    record = (
        StudentAcademicRecord.objects.filter(organization=organization, student=request.user)
        .select_related("program", "group", "student")
        .first()
    )
    response, seal = _render_response(organization=organization, student=request.user, record=record, request=request)
    _audit_issue(organization, record, request.user, seal)
    return response


@login_required
def journal_xlsx(request, offering_id):
    """Jurnalın xlsx ixracı (U14): davamiyyət+ballar vərəqi + yekun vərəqi.

    Giriş jurnal detalı ilə eynidir: müəllim/org sahibi/superuser + korrektor
    (İKT/RİM rəhbəri). Təsdiq zənciri ləğv edildiyi üçün ayrıca «rəyçi» yolu
    YOXDUR — kafedra/dekan jurnal faylını burdan almır."""
    from apps.registrar import finals, gradebook, journal_access, journal_export
    from apps.registrar.views import _can_edit_journal

    offering = journal_access.offering_or_404(request, offering_id)
    if not _can_edit_journal(request.user, offering):
        raise Http404

    # Bölünmüş jurnal (sahib 2026-10-26): pay sahibinin faylında yalnız öz sətir/sütunları.
    from apps.registrar import journal_share_guard

    scope = journal_share_guard.scope(request.user, offering)
    payload = journal_export.build_journal_workbook(
        offering=offering,
        journal=gradebook.get_offering_journal(offering=offering, scope=scope),
        finals=journal_share_guard.restrict_export(finals.get_offering_results(offering=offering), scope),
    )
    filename = f"jurnal-{offering.subject.code}.xlsx"
    response = HttpResponse(payload, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    _audit_export(offering, request.user)
    return response


def _audit_export(offering, by_user):
    """Best-effort audit entry for a journal export (never blocks the download).

    Audit 2026-09-28 DB-01: SAVEPOINT-li yazı (audit_write)."""
    from core.constants import AuditAction

    create_audit_row(
        user=by_user if getattr(by_user, "pk", None) else None,
        organization=offering.organization,
        action=AuditAction.UPDATE,
        resource_type="registrar.journal_export",
        resource_id=str(offering.pk),
        resource_repr=f"{offering.subject.code} jurnalı — xlsx ixracı",
        reason="Elektron jurnal xlsx olaraq ixrac edildi.",
    )


def _wants_json(request) -> bool:
    accept = (request.headers.get("Accept") or "").lower()
    return request.headers.get("x-requested-with") == "XMLHttpRequest" or "application/json" in accept


def _view_as_refusal(request):
    """View-as-da sənəd verilmir: fetch/AJAX → JSON 403; adi link (yeni tab) → layihənin 403 səhifəsi."""
    message = pgettext(
        "registrar.documents",
        "«Başqasının adından» rejimində rəsmi sənəd verilmir — sənəd möhür yazır. Öz hesabınıza qayıdın.",
    )
    if not _wants_json(request):
        raise PermissionDenied(message)
    return JsonResponse({"detail": message, "message": message, "view_as_blocked": True}, status=403)


def _issuable_record_or_404(request, pk):
    """Sənəd verə bilən aktorun ƏHATƏSİNDƏKİ qeyd; açarsız və ya əhatədən kənar → 404 (mövcudluq sızmır)."""
    organization = getattr(request, "organization", None)
    if not document_access.can_issue(request.user, organization, request=request):
        raise Http404  # do not leak console URLs to unauthorised users
    records = document_access.issuable_records(request.user, organization, request=request)
    record = get_object_or_404(records.select_related("program", "group", "student", "student__profile"), pk=pk)
    return organization, record


@login_required
def student_transcript_pdf(request, pk):
    """Sənəd verə bilən işçi: əhatəsindəki tələbənin transkripti PDF olaraq (``document_access``)."""
    if document_access.blocked_by_view_as(request):
        return _view_as_refusal(request)
    organization, record = _issuable_record_or_404(request, pk)
    response, seal = _render_response(organization=organization, student=record.student, record=record, request=request)
    _audit_issue(organization, record, request.user, seal)
    return response


@login_required
@require_POST
def student_enrollment_certificate_pdf(request, pk):
    """«Təhsil aldığı yer haqqında arayış» — möhürlü PDF; ``place`` (təqdim ediləcəyi yer) istəyə bağlıdır."""
    if document_access.blocked_by_view_as(request):
        return _view_as_refusal(request)
    organization, record = _issuable_record_or_404(request, pk)
    place = enrollment_certificate.clean_place(request.POST.get("place", ""))
    try:
        payload, seal = enrollment_certificate.issue_enrollment_certificate(
            organization=organization,
            record=record,
            issued_by=getattr(request, "real_user", None) or request.user,
            place=place,
            request=request,
        )
    except enrollment_certificate.CertificateRefused as refusal:
        return JsonResponse({"detail": refusal.message, "message": refusal.message, "code": refusal.code}, status=409)
    create_audit_row(
        user=request.user,
        organization=organization,
        action=_audit_update_action(),
        resource_type="registrar.enrollment_certificate_pdf",
        resource_id=str(record.pk),
        resource_repr=f"Arayış PDF — {record.student.get_full_name() or record.student.username}"[:200],
        reason=f"Təhsil aldığı yer haqqında arayış verildi. Yoxlama kodu: {seal.code}.",
        # Sonradan «arayış hara verilib» görünsün — təmizlənmiş təqdim yeri (PDF-də çap olunanla eyni).
        new_values={"code": seal.code, "place": place},
    )
    return _attachment(payload, enrollment_certificate.certificate_filename(record))


def _audit_update_action():
    from core.constants import AuditAction

    return AuditAction.UPDATE
