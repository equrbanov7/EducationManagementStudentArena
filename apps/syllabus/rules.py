"""Sillabusa tətbiq olunan akademik qayda — dövrə görə TƏK qərar nöqtəsi (sahib 2026-10-10).

``core.academic_rules`` üzərində nazik qat: sillabusun / versiyanın / açılışın semestri → «sərbəst iş
görünürmü və faizə daxildirmi», «seminar + laboratoriya 5 + 5-mi». Semestrin mənbəyi (prioritetlə):
çağıranın verdiyi semestr (jurnal / tələbə kabineti — baxılan açılışın öz semestri) → versiyanın tətbiq
semestri → dosyenin semestri → dosyenin açılışının semestri. Semestri olmayan «baza sillabus» CARİ
qaydaya tabedir (dövr məlum deyil → yeni qayda).

Köhnə (K1–K3 kollokvium) semestrlərin sillabusu DƏYİŞMİR — sərbəst iş bölməsi, düsturu və tamamlanma
qaydası əvvəlki kimidir. ``self`` bölməsinin datası heç vaxt silinmir: qayda yalnız onu göstərib-
göstərməməyi və faizə daxil edib-etməməyi təyin edir (RİM tənzimləməsi yandırılanda geri qayıdır).

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


#: Köhnə (2026/2027-dən əvvəlki) semestrlərin qaydası — sərbəst iş var, fəallıq birgə orta.
LEGACY = SyllabusRule(selfwork=True, split=False)


def for_period(period, organization=None) -> SyllabusRule:
    """Semestrin qaydası; ``period=None`` → CARİ (yeni) qayda."""
    if not academic_rules.period_uses_new_rules(period, organization):
        return LEGACY
    return SyllabusRule(selfwork=academic_rules.selfwork_enabled(), split=academic_rules.activity_split())


def current(organization=None) -> SyllabusRule:
    """Semestri bilinməyən görünüş (məs. siyahı dialoqları) — CARİ qayda."""
    return for_period(None, organization)


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
