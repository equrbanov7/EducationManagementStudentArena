"""Tam-səhifə sillabus sənədinin CONTEXT MÜQAVİLƏSİ (``detail.html``).

⚠️ Burada YENİ sənəd qurucusu YOXDUR. Mətn eyni iki mənbədən gəlir ki, ekran,
drawer, təsdiq paneli, jurnal və PDF bir-birindən sürüşməsin:

* bölmə gövdələri — :func:`apps.accounts.views.syllabus.review_panel.compose_bodies`
  (o da :func:`apps.syllabus.document.build_preview_blocks`-in üstündə dayanır);
* audit xronologiyası — :func:`…review_panel.build_timeline`.

──────────────────────────────────────────────────────────────────────────────
CONTEXT MÜQAVİLƏSİ — ``syllabus_detail`` (dict)
──────────────────────────────────────────────────────────────────────────────
    code, name        str                — fənn kodu və adı (səhifə başlığı)
    identity          [{label, value}]   — proqram/kafedra/il/semestr/versiya/…
    status            {key,label,tone,banner,reason}
    percent           int                — tamamlanma faizi
    percent_tone      str                — zolağın tonu (`success`/`primary`/…)
    sections          [{id,label,lines}] — 8 məzmun bölməsi, sətirlərə bölünmüş
    timeline          [{what,when,who,body,tone}] — YALNIZ ``TIMELINE_MODES``
    pdf_url           str
    is_student        bool               — tələbə rejimi (yalnız APPROVED nüsxə)
    student_note      str                — tələbəyə göstərilən izah (yoxsa "")

──────────────────────────────────────────────────────────────────────────────
DAXİLİ TARİXÇƏ TƏLƏBƏYƏ VERİLMİR (ağ siyahı, fail-closed)
──────────────────────────────────────────────────────────────────────────────
``version_timeline`` dosyenin BÜTÜN versiyalarını və BÜTÜN ``SyllabusReview``
sətirlərini qaytarır: təsdiqlənməmiş versiyanın etiketi/statusu, rəyçinin adı və
müəllimə yazılmış SƏRBƏST MƏTNLİ rədd səbəbi. Bunlar kafedra daxili gedişatdır;
tələbəyə yalnız TƏSDİQLƏNMİŞ sənədin özü lazımdır (jurnal səthi
``registrar.syllabus_views`` da xronologiya vermir — iki səth üst-üstə düşür).

Ona görə qapı ``not is_student`` DEYİL, **AÇIQ AĞ SİYAHIDIR**: xronologiyanı
yalnız ``TIMELINE_MODES``-dakı rejim alır. Sabah yeni rejim (məs. «valideyn»,
«auditor») əlavə olunanda defolt davranış «GÖSTƏRMƏ» olur — göstərmək üçün bu
faylı bilərəkdən redaktə etmək lazımdır.
"""

from __future__ import annotations

from django.urls import reverse
from django.utils.translation import pgettext_lazy

from apps.syllabus.constants import RULE_SECTIONS, SectionKey, SyllabusStatus
from apps.syllabus.services import section_data_map, version_timeline

from .labels import STATUS_TONES
from .preview import BANNERS
from .review_panel import build_timeline, compose_bodies
from .rows import percent_tone

_CTX = "accounts.syllabus"

_DASH = "—"

#: Sənəd səhifəsinin giriş rejimləri (``detail.py`` bunları yenidən ixrac edir).
MODE_STAFF = "staff"
MODE_STUDENT = "student"

#: Daxili təsdiq xronologiyasını GÖRƏ BİLƏN rejimlər — AÇIQ AĞ SİYAHI.
#: Siyahıda olmayan hər rejim BOŞ xronologiya alır (fail-closed).
TIMELINE_MODES = frozenset({MODE_STAFF})
REASON_MODES = frozenset({MODE_STAFF})

DOCUMENT_TITLE = pgettext_lazy(_CTX, "Sillabus sənədi")
PRINT_LABEL = pgettext_lazy(_CTX, "Çap et")
PDF_LABEL = pgettext_lazy(_CTX, "PDF yüklə")

STUDENT_NOTE = pgettext_lazy(
    _CTX,
    "Tələbələr yalnız təsdiqlənmiş versiyanı görür. Yeni versiya təsdiqlənənə qədər bu nüsxə qüvvədədir.",
)

#: Şapka sətirlərinin etiketləri — ardıcıllıq şablonda deyil, BURADA saxlanılır.
_IDENTITY_LABELS = {
    "program": pgettext_lazy(_CTX, "Təhsil proqramı"),
    "chair": pgettext_lazy(_CTX, "Kafedra"),
    "year": pgettext_lazy(_CTX, "Akademik il"),
    "period": pgettext_lazy(_CTX, "Semestr"),
    "version": pgettext_lazy(_CTX, "Versiya"),
    "author": pgettext_lazy(_CTX, "Müəllif"),
    "approver": pgettext_lazy(_CTX, "Təsdiqləyən"),
}


def _person(user) -> str:
    if user is None:
        return ""
    full = (user.get_full_name() or "").strip() if hasattr(user, "get_full_name") else ""
    return full or getattr(user, "username", "") or ""


def _author_name(syllabus) -> str:
    author = syllabus.author
    if author is None and syllabus.offering_id:
        author = getattr(syllabus.offering, "instructor", None)
    return _person(author)


def _approver_text(version) -> str:
    """«Kim, nə vaxt» — təsdiqlənməmiş versiyada boş qalır (uydurulmur)."""
    who = _person(version.approved_by)
    if version.approved_at is None:
        return who or _DASH
    stamp = version.approved_at.strftime("%d.%m.%Y")
    return f"{who}, {stamp}" if who else stamp


def _identity_rows(syllabus, version) -> list:
    period = syllabus.period
    values = {
        "program": syllabus.program.name if syllabus.program_id else _DASH,
        "chair": syllabus.chair_unit.name if syllabus.chair_unit_id else _DASH,
        "year": (period.year_display if period is not None else _DASH) or _DASH,
        "period": (period.name if period is not None else _DASH) or _DASH,
        "version": version.label,
        "author": _author_name(syllabus) or _DASH,
        "approver": _approver_text(version),
    }
    return [{"key": key, "label": label, "value": values[key]} for key, label in _IDENTITY_LABELS.items()]


def _section_rows(version) -> list:
    """8 məzmun bölməsi — gövdə SƏTİRLƏRƏ bölünür (şablon `<li>` kimi yazır)."""
    bodies = compose_bodies(section_data_map(version))
    rows = []
    for section_id in RULE_SECTIONS:
        body = bodies.get(section_id, "")
        rows.append(
            {
                "id": section_id,
                "label": str(SectionKey(section_id).label),
                "lines": [line for line in body.split("\n") if line.strip()],
            }
        )
    return rows


def _decision_reason(version, mode) -> str:
    """Qərar səbəbi — DAXİLİ mətndir, yalnız ``REASON_MODES`` onu görür.

    ``_timeline`` ilə eyni naxış, qəsdən: qoruma «APPROVED-da səbəb onsuz da
    boşdur» invariantına söykənə BİLMƏZ.  ``drafts.import_migrated_version``
    məhz APPROVED versiyaya ``decision_reason=note`` yazır, yəni sillabus
    köçürməsi qoşulan gün həmin invariant pozulur və səbəb tələbəyə görünərdi.
    Rejim ağ siyahısı bunu qabaqcadan bağlayır (fail-closed: siyahıda olmayan
    hər yeni rejim boş sətir alır).
    """

    if mode not in REASON_MODES:
        return ""
    return (version.decision_reason or "").strip()


def _timeline(syllabus, mode) -> list:
    """Daxili audit xronologiyası — YALNIZ ağ siyahıdakı rejim üçün.

    ⚠️ Sorğu da qurulmur: ``version_timeline`` siyahıdan kənar rejimdə
    ÇAĞIRILMIR, yəni rəy sətirləri ümumiyyətlə oxunmur.
    """
    if mode not in TIMELINE_MODES:
        return []
    return build_timeline(version_timeline(syllabus))


def build_detail_context(*, organization, syllabus, version, mode, is_student: bool) -> dict:
    """Tam-səhifə sənədin context-i (yuxarıdakı müqaviləyə bax)."""
    status = version.status
    percent = version.completion_percent or 0
    detail_kwargs = {"syllabus_id": str(syllabus.pk)}
    pdf_url = reverse("accounts:syllabus_detail_pdf", kwargs=detail_kwargs)
    if not is_student:
        pdf_url = f"{pdf_url}?version={version.pk}"

    return {
        "organization": organization,
        "syllabus": syllabus,
        "version": version,
        "mode": mode,
        "syllabus_detail": {
            "title": DOCUMENT_TITLE,
            "code": syllabus.subject.code,
            "name": syllabus.subject.name,
            "identity": _identity_rows(syllabus, version),
            "status": {
                "key": status,
                "label": str(SyllabusStatus(status).label),
                "tone": STATUS_TONES.get(status, "neutral"),
                "banner": str(BANNERS.get(status, "")),
                "reason": _decision_reason(version, mode),
            },
            "percent": percent,
            "percent_tone": percent_tone(percent),
            "sections": _section_rows(version),
            "timeline": _timeline(syllabus, mode),
            "pdf_url": pdf_url,
            "pdf_label": PDF_LABEL,
            "print_label": PRINT_LABEL,
            "is_student": is_student,
            "student_note": str(STUDENT_NOTE) if is_student else "",
        },
    }


__all__ = [
    "DOCUMENT_TITLE",
    "MODE_STAFF",
    "MODE_STUDENT",
    "PDF_LABEL",
    "PRINT_LABEL",
    "STUDENT_NOTE",
    "REASON_MODES",
    "TIMELINE_MODES",
    "build_detail_context",
]
