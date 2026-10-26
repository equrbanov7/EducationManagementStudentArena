"""Registrar ictimai səthi — rəsmi sənəd buraxılışı (transkript, arayış; sahib 2026-10-19).

Kənar modullar (accounts «Tələbə reyestri», applications «Müraciətlər») YALNIZ bu adları
``apps.registrar.public`` üzərindən işlədir:

* ``can_issue_documents(user, organization, request=None)`` — düymələrin qapısı (``transcript.issue`` və ya
  köhnə org-wide ``course.edit``);
* ``documents_blocked_by_view_as(request)`` — view-as rejimində sənəd verilmir;
* ``issuable_record_for_student(user, organization, student, request=None)`` — aktorun əhatəsindəki aktiv
  akademik qeyd (yoxdursa ``None``);
* ``issue_enrollment_certificate(...)`` → ``(pdf_bytes, seal)``; :class:`CertificateRefused` (``code``,
  ``message``) — tələbə aktiv deyil;
* ``issue_student_transcript(...)`` → ``(pdf_bytes, seal)`` — əməkdaş yükləməsi ilə EYNİ möhürlü transkript
  (sahib 2026-10-26, «Transkript sorğusu»); qiymətləndiriləcək nəticə yoxdursa :class:`CertificateRefused`
  (``no_record``); ``transcript_filename`` + ``audit_transcript_issue`` — fayl adı və rəsmi sənəd izi.
"""

from __future__ import annotations

from . import document_access
from .enrollment_certificate import MAX_PLACE_LENGTH as ENROLLMENT_CERTIFICATE_PLACE_MAX
from .enrollment_certificate import CertificateRefused, certificate_filename, issue_enrollment_certificate
from .enrollment_certificate import refusal_for as enrollment_certificate_refusal

TRANSCRIPT_ISSUE_PERMISSION = document_access.PERM_TRANSCRIPT_ISSUE


def can_issue_documents(user, organization, request=None) -> bool:
    return document_access.can_issue(user, organization, request=request)


def documents_blocked_by_view_as(request) -> bool:
    return document_access.blocked_by_view_as(request)


def enrollment_certificate_places(organization, codes) -> dict:
    """``{yoxlama kodu: təqdim yeri}`` — müraciətə əlavə olunmuş arayışların siyahısı üçün (boş → default)."""
    from apps.verification.public import DocType, payloads_by_code

    payloads = payloads_by_code(organization=organization, codes=codes, doc_type=DocType.ENROLLMENT_CERTIFICATE)
    return {code: str(payload.get("place") or "") for code, payload in payloads.items()}


def issue_student_transcript(*, organization, student, record, issued_by, request=None):
    from .transcript_issue import issue_student_transcript as _issue

    return _issue(organization=organization, student=student, record=record, issued_by=issued_by, request=request)


def transcript_filename(student, code: str = "") -> str:
    from .transcript_issue import transcript_filename as _filename

    return _filename(student, code)


def audit_transcript_issue(organization, record, by_user, seal=None, *, reason: str):
    from .transcript_issue import audit_transcript_issue as _audit

    _audit(organization, record, by_user, seal, reason=reason)


def issuable_record_for_student(user, organization, student, request=None):
    """Aktorun sənəd verə bildiyi qeyd (bir tələbənin bir neçə qeydi varsa aktiv ``enrolled`` üstündür)."""
    if student is None or organization is None:
        return None
    records = (
        document_access.issuable_records(user, organization, request=request)
        .filter(student=student)
        .select_related("program", "group", "student", "student__profile")
        .order_by("-is_active", "status", "-admission_year")
    )
    rows = list(records[:5])
    for record in rows:
        if record.is_active and record.status == "enrolled":
            return record
    return rows[0] if rows else None


__all__ = [
    "ENROLLMENT_CERTIFICATE_PLACE_MAX",
    "TRANSCRIPT_ISSUE_PERMISSION",
    "audit_transcript_issue",
    "CertificateRefused",
    "can_issue_documents",
    "certificate_filename",
    "documents_blocked_by_view_as",
    "enrollment_certificate_places",
    "enrollment_certificate_refusal",
    "issuable_record_for_student",
    "issue_enrollment_certificate",
    "issue_student_transcript",
    "transcript_filename",
]
