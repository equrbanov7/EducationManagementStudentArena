"""«Təhsil aldığı yer haqqında arayış» — faktlar, buraxılış qaydası və QR möhürü (sahib 2026-10-19).

Arayış RƏSMİ sənəddir: «… həqiqətən Qərbi Kaspi Universitetinin … fakültəsinin «…» ixtisası (şifr …) üzrə
… pilləsinin … kurs, … qrup tələbəsidir». Buna görə yalnız HƏQİQƏTƏN təhsil alan tələbəyə verilir
(:func:`refusal_for`) — reyestrin hesablanan «təhsil vəziyyəti» ilə EYNİ qaydalar
(``accounts.services.people.study_state``; registrar accounts-u idxal edə bilmir — modul dövrü, ona görə
qayda burada bir qeyd üçün təkrarlanıb):

* rəsmi status ``enrolled`` deyilsə / qeyd deaktivdirsə → imtina;
* hesab arxivdədirsə (köçürmədə «azad edilib»: məzun və ya xaric) → imtina;
* qəbul ili bilinmirsə (köçürmə sentineli 1950) → imtina;
* oxu müddəti (ECTS / 60 il) bitibsə → imtina (status rəsmiləşdirilməlidir).

Sənəd həmişə AZƏRBAYCAN dilində qurulur (dövlət dilində rəsmi blank; cümlənin hal şəkilçiləri dilə
bağlıdır). Möhür ``verification.public.issue_sealed_document`` ilə: publik səhifədə maskalı ad, ixtisas,
pillə, kurs, forma, «Aktiv tələbə» və verilmə tarixi; ad-soyad, ata adı, qrup, qəbul ili, təqdim yeri publik
``payload``-a DÜŞMÜR.
"""

from __future__ import annotations

import datetime as dt
import re
import unicodedata
from dataclasses import dataclass

from django.utils import timezone, translation
from django.utils.translation import pgettext

from apps.registrar import enrollment_certificate_pdf, transcript_pdf
from apps.registrar.models import AcademicStatus
from apps.verification.public import DocType, issue_sealed_document, mask_holder_name

_CTX = "registrar.arayis"
#: Köçürmənin «qəbul ili bilinmir» sentineli (``legacy_import`` / ``study_state`` ilə EYNİ).
UNKNOWN_ADMISSION_YEAR = 1950
MAX_PLACE_LENGTH = 200
_ROMANS = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI"}


class CertificateRefused(ValueError):
    """Arayış verilə bilmir — ``code`` maşın açarı, ``message`` istifadəçi mətni (görünüş 409 qaytarır)."""

    def __init__(self, code: str, message: str):
        super().__init__(code, message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return str(self.message)


@dataclass(frozen=True)
class CertificateFacts:
    record_id: str
    full_name: str
    faculty: str
    program_name: str
    program_code: str
    degree_key: str
    course: str
    group: str
    education_form: str
    admission_year: int


def _academic_year_start(today: dt.date) -> int:
    """Tədris ili sentyabrda başlayır: 2026-10 → 2026, 2027-03 → 2026."""
    return today.year if today.month >= 9 else today.year - 1


def _study_years(program) -> int:
    ects = int(getattr(program, "ects_total", 0) or 0) or 240
    return (ects + 59) // 60


def course_number(record, *, today=None) -> int:
    today = today or timezone.localdate()
    return _academic_year_start(today) - int(record.admission_year) + 1


def refusal_for(record, *, today=None):
    """Arayış verilə bilmirsə ``CertificateRefused``, verilə bilirsə ``None``."""
    if record.status != AcademicStatus.ENROLLED or not record.is_active:
        status = record.get_status_display() if record.is_active else pgettext(_CTX, "qeyd deaktivdir")
        return CertificateRefused(
            "not_active",
            pgettext(_CTX, "Arayış yalnız təhsil alan (aktiv) tələbəyə verilir — tələbənin statusu: «%(status)s».")
            % {"status": status},
        )
    profile = getattr(record.student, "profile", None)
    if getattr(profile, "access_state", "") == "archived":
        return CertificateRefused(
            "archived", pgettext(_CTX, "Tələbənin hesabı arxivdədir (məzun və ya xaric) — arayış verilmir.")
        )
    if not record.admission_year or int(record.admission_year) == UNKNOWN_ADMISSION_YEAR:
        return CertificateRefused(
            "year_unknown", pgettext(_CTX, "Tələbənin qəbul ili məlum deyil — əvvəlcə akademik qeydi düzəldin.")
        )
    course = course_number(record, today=today)
    if course < 1 or course > _study_years(record.program):
        return CertificateRefused(
            "period_ended",
            pgettext(_CTX, "Tələbənin oxu müddəti bitib — əvvəlcə statusunu rəsmiləşdirin (məzun, xaric və ya bərpa)."),
        )
    return None


#: Ata adından sonra gələn «oğlu/qızı» və qısaltmaları (``accounts.services.teacher_roster.parsing``
#: ``_PATRONYMIC_SUFFIXES`` + «ogl.»). registrar accounts-u idxal edə bilmir (modul dövrü) — sabit KÖÇÜRÜLÜB.
_PATRONYMIC_SUFFIXES = frozenset({"oglu", "ogly", "ogl", "qizi", "kizi", "gizi", "o", "q"})
_FOLD = str.maketrans({"ə": "e", "ı": "i", "ş": "s", "ç": "c", "ğ": "g", "ö": "o", "ü": "u", "â": "a", "î": "i"})


def _suffix_key(token: str) -> str:
    """«Oğlu» / «OĞLU» / «oglu» / «ogl.» / «q.» → registr və diakritikdən asılı olmayan açar."""
    value = unicodedata.normalize("NFC", str(token or "")).replace("İ", "i").replace("I", "ı").lower()
    value = unicodedata.normalize("NFC", unicodedata.normalize("NFD", value).replace("\u0307", ""))
    return re.sub(r"[^a-z0-9]+", "", value.translate(_FOLD))


def patronymic_phrase(patronymic, gender) -> str:
    """Rəsmi «Ata adı oğlu/qızı»: yazılmış şəkilçi (oğlu, oglu, ogl., q., qızı, qizi …) əvvəlcə atılır, sonra
    cinsə görə DÜZGÜN şəkilçi əlavə olunur. Cins bilinmirsə ata adı yazıldığı kimi qalır (yalnız boşluqlar
    normallaşır) — şəkilçi uydurulmur."""
    value = " ".join(unicodedata.normalize("NFC", str(patronymic or "")).split())
    if not value or gender not in ("male", "female"):
        return value
    tokens = value.split(" ")
    while tokens and _suffix_key(tokens[-1]) in _PATRONYMIC_SUFFIXES:
        tokens.pop()
    if not tokens:
        return ""
    return f"{' '.join(tokens)} {'oğlu' if gender == 'male' else 'qızı'}"


def _patronymic(student) -> str:
    profile = getattr(student, "profile", None)
    return patronymic_phrase(getattr(profile, "patronymic", ""), getattr(profile, "gender", ""))


def _full_name(student) -> str:
    """Rəsmi yazılış: «Soyad Ad Ata adı oğlu/qızı» (ata adı varsa)."""
    parts = [" ".join(str(part or "").split()) for part in (student.last_name, student.first_name)]
    parts.append(_patronymic(student))
    name = " ".join(part for part in parts if part)
    return name or student.username


def build_facts(record, *, today=None) -> CertificateFacts:
    program = record.program
    group = record.group if record.group_id else None
    faculty = transcript_pdf._faculty_name(group) if group is not None else ""
    if not faculty and getattr(program, "specialty_unit_id", None):
        faculty = transcript_pdf._faculty_name(program.specialty_unit)
    education_form = record.get_education_form_display() if record.education_form else ""
    if not education_form and getattr(program, "education_form", ""):
        education_form = program.get_education_form_display()
    return CertificateFacts(
        record_id=str(record.pk),
        full_name=_full_name(record.student),
        faculty=faculty,
        program_name=" ".join(str(program.name or "").split()),
        program_code=program.display_code,
        degree_key=str(program.degree_level or ""),
        course=_ROMANS.get(course_number(record, today=today), str(course_number(record, today=today))),
        group=str(getattr(group, "name", "") or ""),
        education_form=str(education_form),
        admission_year=int(record.admission_year),
    )


def _degree_phrase(key: str) -> str:
    return {
        "bachelor": pgettext(_CTX, "bakalavriat"),
        "master": pgettext(_CTX, "magistratura"),
        "phd": pgettext(_CTX, "doktorantura"),
    }.get(key, pgettext(_CTX, "ali təhsil"))


_BACK_VOWELS = {"a": "ın", "ı": "ın", "o": "un", "u": "un", "e": "in", "ə": "in", "i": "in", "ö": "ün", "ü": "ün"}


def genitive(name: str) -> str:
    """Azərbaycan dilində yiyəlik hal: «Qərbi Kaspi Universiteti» → «… Universitetinin» (ahəng qanunu)."""
    name = " ".join(str(name or "").split())
    if not name:
        return ""
    last_vowel = next((char for char in reversed(name.casefold()) if char in _BACK_VOWELS), "i")
    suffix = _BACK_VOWELS[last_vowel]
    return f"{name}{'n' if name.casefold()[-1] in _BACK_VOWELS else ''}{suffix}"


def _faculty_phrase(faculty: str) -> str:
    name = " ".join(str(faculty or "").split())
    if not name:
        return ""
    if name.casefold().endswith("fakültəsi"):
        return f"{name}nin"
    return f"«{name}» {pgettext(_CTX, 'fakültəsinin')}"


def clean_place(value) -> str:
    """«Təqdim ediləcəyi yer»: idarəetmə (Cc) və format/bidi-override (Cf) simvolları atılır, boşluqlar
    normallaşır, uzunluq ``MAX_PLACE_LENGTH``-dir (PDF-də «‮» kimi gizli istiqamət dəyişdirən simvol qalmasın)."""
    text = unicodedata.normalize("NFC", str(value or ""))
    text = "".join(" " if char in "\t\n\r\v\f" else char for char in text)
    text = "".join(char for char in text if unicodedata.category(char) not in ("Cc", "Cf"))
    return " ".join(text.split())[:MAX_PLACE_LENGTH].strip()


def body_paragraphs(*, organization, facts: CertificateFacts, place: str) -> list[str]:
    """Arayışın mətn bəndləri (Azərbaycan dilində qurulmuş çağırışda)."""
    program = f"«{facts.program_name}»"
    if facts.program_code:
        program = f"{program} {pgettext(_CTX, 'ixtisası (şifr %(code)s)') % {'code': facts.program_code}}"
    else:
        program = f"{program} {pgettext(_CTX, 'ixtisası')}"
    where = " ".join(part for part in (genitive(organization.name), _faculty_phrase(facts.faculty)) if part)
    group = pgettext(_CTX, "%(group)s qrup ") % {"group": facts.group} if facts.group else ""
    main = pgettext(
        _CTX,
        "Bu arayış ona verilir ki, %(name)s həqiqətən %(where)s %(program)s üzrə %(degree)s təhsil pilləsinin "
        "%(course)s kurs, %(group)stələbəsidir.",
    ) % {
        "name": facts.full_name,
        "where": where,
        "program": program,
        "degree": _degree_phrase(facts.degree_key),
        "course": facts.course,
        "group": group,
    }
    paragraphs = [main]
    if facts.education_form:
        paragraphs.append(pgettext(_CTX, "Təhsil forması: %(form)s.") % {"form": facts.education_form.lower()})
    paragraphs.append(pgettext(_CTX, "Qəbul ili: %(year)s.") % {"year": facts.admission_year})
    if place:
        paragraphs.append(pgettext(_CTX, "Arayış %(place)s təqdim edilmək üçün verilir.") % {"place": place})
    else:
        paragraphs.append(pgettext(_CTX, "Arayış tələb olunan yerə təqdim edilmək üçün verilir."))
    return paragraphs


def public_payload(*, organization, record, facts: CertificateFacts, place: str = "") -> dict:
    """Publik yoxlama səhifəsinin faktları — ``verification.facts.FACT_LABELS`` açarları ilə (PII YOX).

    ``place`` (PDF-də çap olunan «təqdim ediləcəyi yer») yuxarı səviyyəli açardır, ``facts``-a DÜŞMÜR —
    publik səhifədə görünmür, amma möhür sətrində qalır: sonradan arayışın hara verildiyi bilinir."""
    program = record.program
    facts_list = [
        ["program", program.display_label_full],
        ["degree", str(program.get_degree_level_display())],
        ["course", facts.course],
    ]
    if facts.education_form:
        facts_list.append(["education_form", facts.education_form])
    facts_list.append(["student_status", pgettext(_CTX, "Aktiv tələbə")])
    return {
        "org": organization.name,
        "holder": mask_holder_name(record.student),
        "facts": facts_list,
        "place": place,
    }


def issue_enrollment_certificate(*, organization, record, issued_by, place="", request=None):
    """Möhürlənmiş arayış → ``(pdf_bytes, seal)``. Səlahiyyət/əhatə çağıranda YOXLANILIB.

    ``CertificateRefused`` — tələbə aktiv deyil (görünüş 409 qaytarır)."""
    refusal = refusal_for(record)
    if refusal is not None:
        raise refusal
    place = clean_place(place)
    group = record.group if record.group_id else None
    with translation.override("az"):
        facts = build_facts(record)
        body = body_paragraphs(organization=organization, facts=facts, place=place)

        def _render(mark):
            return enrollment_certificate_pdf.render_certificate_pdf(
                organization=organization, facts=facts, body=body, seal_mark=mark
            )

        return issue_sealed_document(
            organization=organization,
            doc_type=DocType.ENROLLMENT_CERTIFICATE,
            subject_user=record.student,
            title=pgettext("verification.doc_type", "Təhsil aldığı yer haqqında arayış"),
            payload=public_payload(organization=organization, record=record, facts=facts, place=place),
            issued_by=issued_by,
            render=_render,
            scope_path=getattr(group, "path", "") or "",
            request=request,
        )


def certificate_filename(record, code: str = "") -> str:
    """«Arayış_Ad_Soyad_2026-10-19[_KOD].pdf» — transkriptin fayl adı naxışı; ``code`` verilərsə yoxlama kodu
    da addadır (müraciətə əlavə olunmuş nüsxə möhürünə bir mənalı bağlanır — təkrar əlavənin qarşısı)."""
    student = record.student
    full_name = (student.get_full_name() or student.username).strip()
    safe = re.sub(r"[^\w\-]+", "_", full_name, flags=re.U).strip("_") or str(student.username)
    suffix = f"_{code}" if code else ""
    return f"Arayış_{safe}_{timezone.localdate():%Y-%m-%d}{suffix}.pdf"


__all__ = [
    "MAX_PLACE_LENGTH",
    "patronymic_phrase",
    "CertificateFacts",
    "CertificateRefused",
    "body_paragraphs",
    "build_facts",
    "certificate_filename",
    "clean_place",
    "genitive",
    "issue_enrollment_certificate",
    "public_payload",
    "refusal_for",
]
