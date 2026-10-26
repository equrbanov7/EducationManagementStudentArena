"""Möhürlü transkriptin buraxılışı — əməkdaş yükləməsi və «Transkript sorğusu» müraciəti üçün ORTAQ yol.

Əvvəl bu addımlar yalnız ``pdf_views._render_response``-in içində idi. Sahib 2026-10-26: Tələbə Xidmətləri
transkripti müraciətə bir düymə ilə əlavə edir (``applications.services.documents``) — eyni məlumat, eyni
möhür, eyni audit. Hər iki yol bu modulu işlədir (müraciət tərəfi ``registrar.public`` vasitəsilə):

* ``issue_student_transcript(...)`` → ``(pdf_bytes, seal)``; qiymətləndiriləcək heç nə yoxdursa
  :class:`~apps.registrar.enrollment_certificate.CertificateRefused` (``code="no_record"``);
* ``transcript_filename(student, code="")`` — «Transkript_Ad_Soyad_2026-10-26[_KOD].pdf»;
* ``audit_transcript_issue(...)`` — rəsmi sənəd izi (SAVEPOINT-li, yükləməni bloklamır).

Səlahiyyət/əhatə ÇAĞIRANDA yoxlanılır (``document_access``) — bu modul yalnız qurur və möhürləyir.
"""

from __future__ import annotations

import re

from django.utils import timezone
from django.utils.translation import pgettext

from apps.registrar import transcript as transcript_service
from apps.registrar import transcript_seal
from apps.registrar.audit_write import create_audit_row
from apps.registrar.enrollment_certificate import CertificateRefused

_DEFAULT_REASON = "Akademik transkript PDF olaraq yükləndi."


def issue_student_transcript(*, organization, student, record, issued_by, request=None):
    """Möhürlənmiş transkript → ``(pdf_bytes, seal)``; nəticə yoxdursa ``CertificateRefused("no_record")``."""
    program = record.program if record is not None and record.program_id else None
    # Sahib 2026-10-26: rəsmi (möhürlü) transkriptdə hələ başlamamış semestr yoxdur.
    data = transcript_service.build_student_transcript(
        student=student, organization=organization, program=program, started_only=True
    )
    if not data["has_record"]:
        raise CertificateRefused(
            "no_record",
            pgettext("registrar.documents", "Tələbənin transkriptə düşəcək akademik qeydi hələ yoxdur."),
        )
    return transcript_seal.render_sealed_transcript(
        organization=organization,
        student=student,
        record=record,
        data=data,
        issued_by=issued_by,
        request=request,
    )


def transcript_filename(student, code: str = "") -> str:
    """`Transkript_Ad_Soyad_2026-09-10[_KOD].pdf` — arxivə düşəndə oxunan ad.

    Rəsmi sənəddir: fayl adı da tələbənin adını daşıyır ki, onlarla transkript bir qovluqda qarışmasın.
    ``code`` verilərsə yoxlama kodu da addadır (müraciətə əlavə olunmuş nüsxə möhürünə bir mənalı bağlanır)."""
    full_name = (student.get_full_name() or student.username).strip()
    safe_name = re.sub(r"[^\w\-]+", "_", full_name, flags=re.U).strip("_") or str(student.username)
    suffix = f"_{code}" if code else ""
    return f"Transkript_{safe_name}_{timezone.localdate():%Y-%m-%d}{suffix}.pdf"


def audit_transcript_issue(organization, record, by_user, seal=None, *, reason: str = _DEFAULT_REASON):
    """Best-effort audit entry for an issued transcript (never blocks the download).

    Audit 2026-09-28 DB-01: SAVEPOINT-li yazı (audit_write) — ATOMIC_REQUESTS
    rejimində udulmuş xəta sorğu tranzaksiyasını zəhərləmir."""
    from core.constants import AuditAction

    student = record.student if record else by_user
    create_audit_row(
        user=by_user if getattr(by_user, "pk", None) else None,
        organization=organization,
        action=AuditAction.UPDATE,
        resource_type="registrar.transcript_pdf",
        resource_id=str(record.pk) if record else "",
        resource_repr=f"Transkript PDF — {student.get_full_name() or student.username}",
        reason=reason + (f" Yoxlama kodu: {seal.code}." if seal is not None else ""),
    )


__all__ = ["audit_transcript_issue", "issue_student_transcript", "transcript_filename"]
