"""Müraciətə «hazırla və əlavə et» edilən rəsmi sənədlərin CƏDVƏLİ (``services.documents`` bunu işlədir).

Hər növ (``kind.code``) üçün: sənədi necə buraxmaq, fayl adı naxışı, imtina qaydası, siyahıdakı ikinci sətir və
UI mətnləri. Axın (emalçı + ``transcript.issue`` əhatəsi, kilid, təkrar əlavə yoxdur, view-as 403) hamısı üçün
eynidir — yeni sənəd növü bu cədvələ bir sətir əlavə etməklə qoşulur.

* «Arayış sorğusu» (``arayis``, 2026-10-19) — «Təhsil aldığı yer haqqında arayış»; «Təqdim ediləcəyi yer»
  istəyə bağlıdır; yalnız aktiv tələbəyə.
* «Transkript sorğusu» (``transkript``, sahib 2026-10-26) — staff yükləməsi ilə EYNİ möhürlü transkript
  (``registrar.public.issue_student_transcript``) + ``registrar.transcript_pdf`` audit sətri; yer sahəsi yoxdur;
  qiymətləndiriləcək nəticə yoxdursa 409.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from django.utils import timezone
from django.utils.translation import pgettext

from apps.registrar.public import (
    ENROLLMENT_CERTIFICATE_PLACE_MAX,
    TRANSCRIPT_APPLICATION_KIND,
    audit_transcript_issue,
    certificate_filename,
    enrollment_certificate_places,
    enrollment_certificate_refusal,
    issue_enrollment_certificate,
    issue_student_transcript,
    transcript_filename,
)

ARAYIS_KIND_CODE = "arayis"
TRANSCRIPT_KIND_CODE = TRANSCRIPT_APPLICATION_KIND

_ARAYIS = "applications.arayis"
_TRANSCRIPT = "applications.transcript"

#: Yoxlama kodu (``verification``): «QKU-ABCD-EFGH-JKLM-NPQR» kimi.
_CODE = r"(?P<code>[A-Z0-9]{2,6}(?:-[0-9A-Z]{4}){4})"


@dataclass(frozen=True)
class DocumentKind:
    code: str
    url_name: str
    #: Fayl adının prefiksi — «<prefix>_<ad>_<YYYY-MM-DD>_<kod>.pdf»; kod möhürə bir mənalı bağlayır.
    prefix: str
    has_place: bool
    #: ``(organization, record, issued_by, place, request)`` → ``(pdf_bytes, seal)``; ``CertificateRefused``.
    issue: Callable
    filename: Callable  # (record, code) → str
    refusal: Callable  # (record) → refusal | None (detal blokunda öncədən göstərilir)
    notes: Callable  # (application, codes, attachments) → [ikinci sətir, …]
    texts: Callable  # () → {UI açarı: mətn}
    comment: Callable  # (code) → açıq qeydin mətni
    #: Yeni əlavədən SONRA (eyni tranzaksiyada) — rəsmi sənəd izi; ``None`` → yoxdur.
    after_issue: Callable | None = None

    @property
    def name_pattern(self):
        return re.compile(rf"^{re.escape(self.prefix)}_.+_\d{{4}}-\d{{2}}-\d{{2}}_{_CODE}\.pdf$")


# ── «Arayış sorğusu» ─────────────────────────────────────────────────────────


def _arayis_issue(organization, record, issued_by, place, request):
    return issue_enrollment_certificate(
        organization=organization, record=record, issued_by=issued_by, place=place, request=request
    )


def _arayis_notes(application, codes, attachments):
    places = enrollment_certificate_places(application.organization, codes)
    default_place = pgettext(_ARAYIS, "tələb olunan yerə")
    return [places.get(code) or default_place for code in codes]


def _arayis_texts():
    return {
        "title": pgettext(_ARAYIS, "Təhsil aldığı yer haqqında arayış"),
        "hint": pgettext(
            _ARAYIS,
            "Arayış QR və yoxlama kodu ilə möhürlənir və müraciətə açıq qeyd kimi əlavə olunur — sahib onu "
            "müraciətdən endirir. «Təqdim ediləcəyi yer» istəyə bağlıdır (yönlük halda: «… bankına»).",
        ),
        "place_label": pgettext(_ARAYIS, "Təqdim ediləcəyi yer"),
        "place_placeholder": pgettext(_ARAYIS, "məs.: Səbail rayon hərbi komissarlığına"),
        "button": pgettext(_ARAYIS, "Arayışı hazırla və əlavə et"),
        "attached_label": pgettext(_ARAYIS, "Arayış əlavə olunub"),
        "open_label": pgettext(_ARAYIS, "Arayışı aç"),
        "again_label": pgettext(_ARAYIS, "Yeni arayış hazırla (başqa yer üçün)"),
        "same_place_hint": pgettext(
            _ARAYIS, "Eyni yer üçün yenidən hazırlasanız, artıq əlavə olunmuş arayış qaytarılır — ikinci fayl yaranmır."
        ),
        "unavailable": pgettext(_ARAYIS, "Bu müraciətə arayış hazırlamaq mümkün deyil."),
    }


def _arayis_comment(code):
    return pgettext(
        _ARAYIS, "Təhsil aldığı yer haqqında arayış hazırlandı və əlavə olundu. Yoxlama kodu: %(code)s."
    ) % {"code": code}


# ── «Transkript sorğusu» ─────────────────────────────────────────────────────


def _transcript_issue(organization, record, issued_by, place, request):
    return issue_student_transcript(
        organization=organization, student=record.student, record=record, issued_by=issued_by, request=request
    )


def _transcript_notes(application, codes, attachments):
    """İkinci sətir — hazırlanma tarixi (transkriptin «yeri» yoxdur; hər gün yeni möhür ola bilər)."""
    return [
        pgettext(_TRANSCRIPT, "hazırlanıb: %(date)s")
        % {"date": timezone.localtime(row.created_at).strftime("%d.%m.%Y")}
        for row in attachments
    ]


def _transcript_texts():
    return {
        "title": pgettext(_TRANSCRIPT, "Akademik transkript"),
        "hint": pgettext(
            _TRANSCRIPT,
            "Transkript QR və yoxlama kodu ilə möhürlənir və müraciətə açıq qeyd kimi əlavə olunur — sahib onu "
            "müraciətdən endirir.",
        ),
        "place_label": "",
        "place_placeholder": "",
        "button": pgettext(_TRANSCRIPT, "Transkripti hazırla və əlavə et"),
        "attached_label": pgettext(_TRANSCRIPT, "Transkript əlavə olunub"),
        "open_label": pgettext(_TRANSCRIPT, "Transkripti aç"),
        "again_label": pgettext(_TRANSCRIPT, "Transkripti yenidən hazırla"),
        "same_place_hint": pgettext(
            _TRANSCRIPT,
            "Nəticələr dəyişməyibsə, bu gün artıq əlavə olunmuş transkript qaytarılır — ikinci fayl yaranmır.",
        ),
        "unavailable": pgettext(_TRANSCRIPT, "Bu müraciətə transkript hazırlamaq mümkün deyil."),
    }


def _transcript_comment(code):
    return pgettext(_TRANSCRIPT, "Akademik transkript hazırlandı və əlavə olundu. Yoxlama kodu: %(code)s.") % {
        "code": code
    }


def _transcript_audit(application, record, user, seal):
    audit_transcript_issue(
        application.organization,
        record,
        user,
        seal,
        reason="Akademik transkript «Transkript sorğusu» müraciətinə əlavə olundu.",
    )


KINDS = {
    ARAYIS_KIND_CODE: DocumentKind(
        code=ARAYIS_KIND_CODE,
        url_name="applications:issue_arayis",
        prefix="Arayış",
        has_place=True,
        issue=_arayis_issue,
        filename=certificate_filename,
        refusal=enrollment_certificate_refusal,
        notes=_arayis_notes,
        texts=_arayis_texts,
        comment=_arayis_comment,
    ),
    TRANSCRIPT_KIND_CODE: DocumentKind(
        code=TRANSCRIPT_KIND_CODE,
        url_name="applications:issue_transcript",
        prefix="Transkript",
        has_place=False,
        issue=_transcript_issue,
        filename=lambda record, code: transcript_filename(record.student, code),
        # Transkript keçmiş tələbəyə də verilir (məzun, xaric) — staff yükləməsi kimi; aktivlik şərti YOXDUR.
        refusal=lambda record: None,
        notes=_transcript_notes,
        texts=_transcript_texts,
        comment=_transcript_comment,
        after_issue=_transcript_audit,
    ),
}

PLACE_MAX = ENROLLMENT_CERTIFICATE_PLACE_MAX


def kind_for(application) -> DocumentKind | None:
    return KINDS.get(getattr(application.kind, "code", "") or "")


__all__ = ["ARAYIS_KIND_CODE", "KINDS", "PLACE_MAX", "TRANSCRIPT_KIND_CODE", "DocumentKind", "kind_for"]
