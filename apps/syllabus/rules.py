"""Sillabusa tətbiq olunan akademik qayda — TƏK qərar nöqtəsi (sahib 2026-10-10, dəqiqləşmə 2026-10-11).

``core.academic_rules`` üzərində nazik qat: «sərbəst iş görünürmü və faizə daxildirmi», «seminar +
laboratoriya 5 + 5-mi». Qayda RİM-in «Sistem tənzimləmələri» açarlarından oxunur
(``academic.selfwork_enabled`` / ``academic.activity_split``).

Sahib 2026-10-11: sillabus İRƏLİYƏ baxan sənəddir — CARİ qayda HƏR semestrin (köhnə 2025/2026 daxil)
sillabusuna tətbiq olunur. Dövr (sillabusun / versiyanın / açılışın semestri) qaydanı DƏYİŞMİR:
«Midterm 20 + Sərbəst iş 10» köhnə semestrin redaktorunda da görünməməlidir. Sərbəst işi geri
qaytarmaq lazım olsa RİM ``academic.selfwork_enabled`` açarını yandırır — onda sərbəst iş bölməsi və
midterm 20 HƏR yerdə (bütün semestrlərdə) geri qayıdır. ``self`` bölməsinin datası heç vaxt silinmir:
qayda yalnız onu göstərib-göstərməməyi və faizə daxil edib-etməməyi təyin edir.

Jurnal (``apps.registrar``) bu modula TABE DEYİL — köhnə semestrlərin qiymət tarixi
``core.academic_rules.selfwork_active_for_period`` ilə əvvəlki kimi qalır.

``syllabus_period`` / ``version_period`` köməkçiləri saxlanılır (semestri göstərmək üçün başqa kod
onları idxal edir); ``for_*`` funksiyalarının ``period`` / ``organization`` parametrləri uyğunluq
üçün qalır və cavaba təsir etmir.

Modul sərhədi: ``apps.registrar`` idxal EDİLMİR (registrar → syllabus tək istiqamətlidir).
"""

from __future__ import annotations

from dataclasses import dataclass

from core import academic_rules

from .constants import RULE_SECTIONS, SECTION_ORDER, SectionKey

_SELF = SectionKey.SELF.value


@dataclass(frozen=True)
class SyllabusRule:
    """Bir sillabus görünüşünə (redaktor, sənəd, baxış, tamamlanma) tətbiq olunan qayda."""

    #: Sərbəst iş bölməsi görünür və tamamlanma faizinə daxildir.
    selfwork: bool = True
    #: Seminar + laboratoriya olan fəndə fəallıq 5 + 5 (ayrı ortalar); ``False`` — birgə orta.
    split: bool = False

    @property
    def rule_sections(self) -> tuple:
        """Tamamlanma faizinin hesablandığı bölmələr (sərbəst işsiz qaydada 7)."""
        return RULE_SECTIONS if self.selfwork else tuple(key for key in RULE_SECTIONS if key != _SELF)

    @property
    def section_order(self) -> tuple:
        """Redaktorun bölmələri sıra ilə (sərbəst işsiz qaydada 9)."""
        return SECTION_ORDER if self.selfwork else tuple(key for key in SECTION_ORDER if key != _SELF)


#: Sərbəst işli (midterm 20 + sərbəst iş 10, fəallıq birgə orta) qayda — 2026-10-11-dən dövrə görə
#: SEÇİLMİR; yalnız ``rule=`` açıq ötürən çağıranlar (testlər, müqayisə) üçün sabit kimi saxlanılır.
LEGACY = SyllabusRule(selfwork=True, split=False)


def current(organization=None) -> SyllabusRule:
    """CARİ qayda — RİM tənzimləmələrindən (``selfwork_enabled`` / ``activity_split``)."""
    return SyllabusRule(selfwork=academic_rules.selfwork_enabled(), split=academic_rules.activity_split())


def for_period(period, organization=None) -> SyllabusRule:
    """Semestrin qaydası — sahib 2026-10-11: semestrdən asılı DEYİL, həmişə CARİ qayda.

    ``period`` / ``organization`` çağıranların uyğunluğu üçün qəbul olunur, cavaba təsir etmir."""
    return current(organization)


def syllabus_period(syllabus):
    """Dosyenin semestri: öz semestri → açılışının semestri → ``None`` (baza sillabus)."""
    if syllabus is None:
        return None
    if getattr(syllabus, "period_id", None):
        return syllabus.period
    if getattr(syllabus, "offering_id", None):
        return getattr(syllabus.offering, "period", None)
    return None


def version_period(version):
    """Versiyanın semestri — tətbiq semestri, yoxdursa dosyeninki.

    Tətbiq semestri dosyeninki ilə eynidirsə (adi hal) dosyenin artıq yüklənmiş (``select_related``)
    obyekti götürülür — siyahılarda sətir başına əlavə sorğu olmasın."""
    if version is None:
        return None
    syllabus = getattr(version, "syllabus", None)
    period_id = getattr(version, "applies_to_period_id", None)
    if period_id and syllabus is not None and getattr(syllabus, "period_id", None) == period_id:
        return syllabus.period
    if period_id:
        return version.applies_to_period
    return syllabus_period(syllabus)


def for_syllabus(syllabus, organization=None) -> SyllabusRule:
    return for_period(syllabus_period(syllabus), organization)


def for_version(version, organization=None) -> SyllabusRule:
    if version is None:
        return current(organization)
    return for_period(version_period(version), organization)


def selfwork_active_for_version(version, organization=None) -> bool:
    return for_version(version, organization).selfwork


__all__ = [
    "LEGACY",
    "SyllabusRule",
    "current",
    "for_period",
    "for_syllabus",
    "for_version",
    "selfwork_active_for_version",
    "syllabus_period",
    "version_period",
]
