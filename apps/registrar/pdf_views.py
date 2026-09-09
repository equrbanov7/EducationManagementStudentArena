"""Transkript PDF ixracı (U9) — tələbənin özü + registrar səlahiyyətli işçi.

Two thin views over :func:`transcript_pdf.render_transcript_pdf`:

* ``my_transcript_pdf`` — the requesting student downloads their **own**
  transcript (tenant scoping from the active org / RLS).
* ``student_transcript_pdf`` — registrar səlahiyyətli işçi İSTƏNİLƏN tələbənin
  transkriptini yükləyir. Qapı akademik kataloqun qapısı ilə EYNİDİR
  (``catalog_console.can_manage`` — org-wide ``course.edit``); köhnə
  «Registrar idarəetməsi» konsolu 2026-09-10-da silinəndə bu səth toxunulmaz
  qaldı, yalnız icazə köməkçisinin YERİ dəyişdi.

The PDF is generated on the fly and never stored; each issuance is written to
the audit log (official-document trail).
"""

from __future__ import annotations

import re
from urllib.parse import quote

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404

from apps.registrar import transcript as transcript_service
from apps.registrar import transcript_pdf
from apps.registrar.catalog_console import can_manage as _can_manage_registrar
from apps.registrar.models import StudentAcademicRecord


def _audit_issue(organization, record, by_user):
    """Best-effort audit entry for an issued transcript (never blocks the download)."""
    try:
        from django.apps import apps as django_apps

        from core.constants import AuditAction

        AuditLog = django_apps.get_model("audit", "AuditLog")
        student = record.student if record else by_user
        AuditLog.objects.create(
            user=by_user if getattr(by_user, "pk", None) else None,
            organization=organization,
            action=AuditAction.UPDATE,
            resource_type="registrar.transcript_pdf",
            resource_id=str(record.pk) if record else "",
            resource_repr=f"Transkript PDF — {student.get_full_name() or student.username}",
            reason="Akademik transkript PDF olaraq yükləndi.",
        )
    except Exception:  # noqa: BLE001 — audit must never block the download
        pass


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
    """`Transkript_Ad_Soyad_2026-09-10.pdf` — arxivə düşəndə oxunan ad.

    Rəsmi sənəddir: fayl adı da tələbənin adını daşımalıdır ki, onlarla
    yüklənmiş transkript bir qovluqda qarışmasın."""
    from django.utils import timezone

    full_name = (student.get_full_name() or student.username).strip()
    safe_name = re.sub(r"[^\w\-]+", "_", full_name, flags=re.U).strip("_") or str(student.username)
    return f"Transkript_{safe_name}_{timezone.localdate():%Y-%m-%d}.pdf"


def _attachment(payload: bytes, filename: str) -> HttpResponse:
    """`Content-Disposition: attachment` — ASCII geri dönüşü + RFC 5987 UTF-8 adı."""
    response = HttpResponse(payload, content_type="application/pdf")
    ascii_name = filename.translate(_ASCII_FOLD).encode("ascii", "ignore").decode("ascii") or "transkript.pdf"
    response["Content-Disposition"] = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"
    return response


def _render_response(*, organization, student, record) -> HttpResponse:
    program = record.program if record and record.program_id else None
    data = transcript_service.build_student_transcript(student=student, organization=organization, program=program)
    if not data["has_record"]:
        raise Http404  # nothing to certify yet
    payload = transcript_pdf.render_transcript_pdf(organization=organization, student=student, record=record, data=data)
    return _attachment(payload, _transcript_filename(student))


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
    organization = getattr(request, "organization", None)
    if organization is None:
        raise Http404
    record = (
        StudentAcademicRecord.objects.filter(organization=organization, student=request.user)
        .select_related("program", "group", "student")
        .first()
    )
    response = _render_response(organization=organization, student=request.user, record=record)
    _audit_issue(organization, record, request.user)
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

    payload = journal_export.build_journal_workbook(
        offering=offering,
        journal=gradebook.get_offering_journal(offering=offering),
        finals=finals.get_offering_results(offering=offering),
    )
    filename = f"jurnal-{offering.subject.code}.xlsx"
    response = HttpResponse(payload, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    _audit_export(offering, request.user)
    return response


def _audit_export(offering, by_user):
    """Best-effort audit entry for a journal export (never blocks the download)."""
    try:
        from django.apps import apps as django_apps

        from core.constants import AuditAction

        AuditLog = django_apps.get_model("audit", "AuditLog")
        AuditLog.objects.create(
            user=by_user if getattr(by_user, "pk", None) else None,
            organization=offering.organization,
            action=AuditAction.UPDATE,
            resource_type="registrar.journal_export",
            resource_id=str(offering.pk),
            resource_repr=f"{offering.subject.code} jurnalı — xlsx ixracı",
            reason="Elektron jurnal xlsx olaraq ixrac edildi.",
        )
    except Exception:  # noqa: BLE001 — audit must never block the download
        pass


@login_required
def student_transcript_pdf(request, pk):
    """Registrar console: any student's transcript as PDF (staff only)."""
    organization = getattr(request, "organization", None)
    if not _can_manage_registrar(request.user, organization):
        raise Http404  # do not leak console URLs to unauthorised users
    record = get_object_or_404(
        StudentAcademicRecord.objects.filter(organization=organization).select_related("program", "group", "student"),
        pk=pk,
    )
    response = _render_response(organization=organization, student=record.student, record=record)
    _audit_issue(organization, record, request.user)
    return response


@login_required
def schedule_ics(request):
    """Rol-aware dərs cədvəlinin iCal exportu (U19).

    Tələbə → qrup cədvəli; digərləri → öz tədris slotları. Yalnız istifadəçinin
    onsuz da gördüyü slotlar ixrac edilir — əlavə icazə səthi açılmır."""
    from apps.registrar import ical, schedule
    from apps.registrar.page_contexts import _current_period

    organization = getattr(request, "organization", None)
    if organization is None:
        raise Http404
    period = _current_period(organization)
    record = (
        StudentAcademicRecord.objects.filter(organization=organization, student=request.user)
        .select_related("group")
        .first()
    )
    if record and record.group and period:
        slots = schedule.get_group_schedule(organization=organization, group=record.group, period=period)
        calendar_name = record.group.name
    elif period:
        slots = schedule.get_teacher_schedule(organization=organization, teacher=request.user, period=period)
        calendar_name = request.user.get_full_name() or request.user.username
    else:
        slots, calendar_name = [], organization.name
    payload = ical.build_schedule_ics(
        slots=slots, period=period, calendar_name=f"{calendar_name} — {organization.name}"
    )
    response = HttpResponse(payload, content_type="text/calendar; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="ders-cedveli.ics"'
    return response
