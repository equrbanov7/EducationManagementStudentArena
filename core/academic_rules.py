"""Akademik qaydaların TƏK oxu nöqtəsi (sahib 2026-10-10 «Yeni qayda var»).

Sahib: «sərbəst iş ləğv olur — kodu saxla, lazım olsa yenidən yazmadan əlavə edək; 10 bal davamiyyət,
10 bal seminar, 30 bal midterm; fəndə laboratoriya da varsa 5 + 5; jurnaldakı «Aktivləşdir»-i yığışdır;
hamısını tənzimləmələrdə əlavə edib çıxarmaq olsun».

Bayraqlar RİM-in «Sistem tənzimləmələri» səhifəsindən dəyişir (``core.runtime_settings``, qrup
``academic`` + ``journal.lesson_activation`` + ``ai.assistant_button``). Defolt = YENİ qayda. Çağıranlar
açarları birbaşa oxumur — yalnız bu funksiyaları çağırır, ki qayda bir yerdə dəyişsin.

⚠️ Bu bayraqlar yalnız «midterm rejimi» semestrlərinə (2026/2027+) aiddir. Köhnə semestrlərin (K1–K3
kollokvium, sərbəst iş) hesabı və görüntüsü DƏYİŞMİR — dövr qərarı ``apps.registrar.interim_assessment``-dədir.

Testlər ``RUNTIME_SETTINGS_ENABLED=False`` ilə işləyir (defolt oxunur); köhnə qaydanı yoxlamaq üçün
``@override_settings(ACADEMIC_SELFWORK_ENABLED=True)`` / ``ACADEMIC_ACTIVITY_SPLIT=False`` /
``JOURNAL_LESSON_ACTIVATION=True`` / ``AI_ASSISTANT_BUTTON=False`` / ``EXAM_AVAILABLE_PAGE=True`` /
``ACADEMIC_COURSEWORK_ENABLED=True``.
"""

from __future__ import annotations

import re

from core import runtime_settings

#: Yeni qaydalar («midterm rejimi») bu tədris ilindən başlayır (2026 → «2026/2027»). Təşkilat
#: ``Organization.settings["registrar"]["midterm_from_year"]`` ilə dəyişə bilər.
MIDTERM_FROM_YEAR = 2026
_YEAR_RE = re.compile(r"\d{4}")

#: Semestr (imtahanaqədər) balının hissələri — cəm həmişə 50.
ATTENDANCE_MAX = 10
ACTIVITY_MAX = 10
SELFWORK_POINTS = 10
#: Sərbəst iş söndürüləndə onun balı midterm-ə keçir: 20 + 10 = 30.
MIDTERM_MAX_WITH_SELFWORK = 20
MIDTERM_MAX_WITHOUT_SELFWORK = MIDTERM_MAX_WITH_SELFWORK + SELFWORK_POINTS


def selfwork_enabled() -> bool:
    """Sərbəst iş (2026/2027+ semestrlərdə) görünür və bala daxildirmi."""
    return runtime_settings.get_bool("academic.selfwork_enabled")


def selfwork_max() -> int:
    return SELFWORK_POINTS if selfwork_enabled() else 0


def midterm_max() -> int:
    """Midterm-in maksimum balı: sərbəst iş varsa 20, yoxdursa 30 (cəm 50 qalır)."""
    return MIDTERM_MAX_WITH_SELFWORK if selfwork_enabled() else MIDTERM_MAX_WITHOUT_SELFWORK


def activity_split() -> bool:
    """Seminar + laboratoriya olan fəndə fəallıq 5 + 5 (ayrı ortalar); söndürülüdə birgə orta."""
    return runtime_settings.get_bool("academic.activity_split")


def coursework_enabled() -> bool:
    """Jurnalda «Kurs işi» (2026/2027+ semestrlərdə) görünürmü (sahib 2026-10-11: hələlik söndür)."""
    return runtime_settings.get_bool("academic.coursework_enabled")


def syllabus_hours_from_load() -> bool:
    """Sillabus saatları kafedra yükündən (əsas mənbə) + yükdə olmayan növ gizli (sahib 2026-10-12)."""
    return runtime_settings.get_bool("syllabus.hours_from_load")


def lesson_activation_enabled() -> bool:
    """Jurnalda cədvəl dərsinin «Aktivləşdir» düyməsi (söndürülüdə yalnız «Yeni dərs»)."""
    return runtime_settings.get_bool("journal.lesson_activation")


def ai_assistant_button_enabled() -> bool:
    """Küncdəki AI köməkçi düyməsi ümumiyyətlə göstərilirmi (istifadəçi öz ekranında ayrıca gizlədə bilər)."""
    return runtime_settings.get_bool("ai.assistant_button")


def available_exams_page_enabled() -> bool:
    """«Mövcud imtahanlar» siyahısı (``exams:available``) və ona aparan keçidlər (sahib 2026-10-10: hələlik yox)."""
    return runtime_settings.get_bool("exam.available_page")


def contact_page_enabled() -> bool:
    """Açıq «Əlaqə» səhifəsi (``/contact/``) və ona aparan keçidlər (sahib 2026-10-20: hələlik gizli)."""
    return runtime_settings.get_bool("site.contact_page")


def midterm_from_year(organization=None) -> int:
    """Təşkilatın midterm başlanğıc ili — ``settings["registrar"]["midterm_from_year"]`` və ya 2026."""
    settings = getattr(organization, "settings", None)
    section = settings.get("registrar") if isinstance(settings, dict) else None
    raw = section.get("midterm_from_year") if isinstance(section, dict) else None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return MIDTERM_FROM_YEAR
    return value if 2000 <= value <= 2100 else MIDTERM_FROM_YEAR


def period_start_year(period) -> int | None:
    """Dövrün tədris ilinin BAŞLANĞIC ili: «2026/2027» → 2026.

    ``academic_year`` sərbəst mətndir («2026/2027», «2026-2027», «2026»); ondan il tapılmasa
    ``start_date``-dən çıxarılır (avqustdan əvvəlki aylar əvvəlki tədris ilinə aiddir)."""
    if period is None:
        return None
    match = _YEAR_RE.search(str(getattr(period, "academic_year", "") or ""))
    if match:
        return int(match.group())
    start = getattr(period, "start_date", None)
    if start is None:
        return None
    return start.year if start.month >= 8 else start.year - 1


def period_uses_new_rules(period, organization=None) -> bool:
    """Dövr «midterm rejimi»ndədirmi (2026/2027+). Dövr/il məlum deyilsə — bəli (cari qayda).

    ``apps.registrar.interim_assessment.mode_for_period`` bu funksiyanın üzərində qurulub — ikisi eyni cavab verir."""
    if organization is None and period is not None:
        organization = getattr(period, "organization", None)
    year = period_start_year(period)
    return True if year is None else year >= midterm_from_year(organization)


def selfwork_active_for_period(period, organization=None) -> bool:
    """Bu dövrdə sərbəst iş görünürmü və bala daxildirmi — jurnal, sillabus, fənn qovluğu, kabinet üçün TƏK qərar.

    Köhnə (K1–K3 kollokvium) dövrlərdə sərbəst iş TARİXDİR — həmişə qalır (keçmiş qiymətlər dəyişməsin).
    Yeni qayda dövrlərində RİM tənzimləməsi qərar verir (defolt söndürülü)."""
    if not period_uses_new_rules(period, organization):
        return True
    return selfwork_enabled()


def selfwork_active_for_offering(offering) -> bool:
    if offering is None:
        return selfwork_enabled()
    return selfwork_active_for_period(getattr(offering, "period", None), getattr(offering, "organization", None))


def coursework_active_for_period(period, organization=None) -> bool:
    """Kurs işi bu dövrdə görünürmü — köhnə (K1–K3) dövrlərdə həmişə (tarix), yenilərdə RİM tənzimləməsi."""
    if not period_uses_new_rules(period, organization):
        return True
    return coursework_enabled()


def coursework_active_for_offering(offering) -> bool:
    if offering is None:
        return coursework_enabled()
    return coursework_active_for_period(getattr(offering, "period", None), getattr(offering, "organization", None))


def snapshot() -> dict:
    """Şablonlar üçün (``core.context_processors.feature_flags`` → ``academic_rules``)."""
    selfwork = selfwork_enabled()
    return {
        "selfwork": selfwork,
        "selfwork_max": SELFWORK_POINTS if selfwork else 0,
        "midterm_max": MIDTERM_MAX_WITH_SELFWORK if selfwork else MIDTERM_MAX_WITHOUT_SELFWORK,
        "attendance_max": ATTENDANCE_MAX,
        "activity_max": ACTIVITY_MAX,
        "activity_split": activity_split(),
        "coursework": coursework_enabled(),
        "lesson_activation": lesson_activation_enabled(),
        "ai_button": ai_assistant_button_enabled(),
        "available_exams": available_exams_page_enabled(),
        "contact_page": contact_page_enabled(),
    }


__all__ = [
    "ACTIVITY_MAX",
    "ATTENDANCE_MAX",
    "MIDTERM_FROM_YEAR",
    "MIDTERM_MAX_WITHOUT_SELFWORK",
    "MIDTERM_MAX_WITH_SELFWORK",
    "SELFWORK_POINTS",
    "activity_split",
    "ai_assistant_button_enabled",
    "coursework_active_for_offering",
    "coursework_active_for_period",
    "coursework_enabled",
    "available_exams_page_enabled",
    "contact_page_enabled",
    "lesson_activation_enabled",
    "midterm_from_year",
    "midterm_max",
    "period_start_year",
    "period_uses_new_rules",
    "selfwork_active_for_offering",
    "selfwork_active_for_period",
    "selfwork_enabled",
    "selfwork_max",
    "syllabus_hours_from_load",
    "snapshot",
]
