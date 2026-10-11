"""Fənn qovluğunda sərbəst iş AKTİVDİRMİ — sahib 2026-10-10 qaydası (dövrə görə TƏK qərar).

Yeni qayda dövrlərində (2026/2027+) sərbəst iş RİM «Sistem tənzimləmələri» ilə söndürülür (defolt):
qovluqda slot yaradılmır, mövcud sərbəst iş tapşırıqları tələbəyə və müəllimə göstərilmir, göndəriş
və qəbul olunmur, jurnal sinxronu və «Yeni sərbəst iş» bildirişi yoxdur. Data (tapşırıq, göndəriş,
bal) TOXUNULMUR — tənzimləmə yandırılanda hamısı geri qayıdır. Köhnə semestrlər həmişə əvvəlki kimidir.

Qərar ``core.academic_rules``-dandır; registrar modelləri yalnız app registry ilə oxunur (modul sərhədi).
"""

from __future__ import annotations

from core import academic_rules

from . import lookups


def offering_active(offering, organization=None) -> bool:
    """Açılışın (qrupun) sərbəst işi — açılışın semestrinə görə."""
    if academic_rules.selfwork_enabled():
        return True  # bayraq yanılıdır → köhnə və yeni bütün dövrlərdə var (sorğusuz)
    if offering is None:
        return False
    if organization is None:
        return academic_rules.selfwork_active_for_offering(offering)
    return academic_rules.selfwork_active_for_period(getattr(offering, "period", None), organization)


def folder_active(folder, *, organization=None, offering=None, version=None) -> bool:
    """Qovluğun sərbəst işi: verilən açılışın semestri → qovluğun semestri → semestrsiz qovluqda
    sinxron sillabus versiyasının semestri → CARİ qayda."""
    if academic_rules.selfwork_enabled():
        return True
    if offering is not None:
        return offering_active(offering, organization)
    organization = organization or getattr(folder, "organization", None)
    if getattr(folder, "period_id", None):
        return academic_rules.selfwork_active_for_period(folder.period, organization)
    if version is not None:
        from apps.syllabus import public as syllabus_public

        return syllabus_public.selfwork_active_for_version(version, organization)
    return academic_rules.selfwork_active_for_period(None, organization)


def active_offering_ids(offering_ids, organization=None) -> set:
    """Verilən açılışlardan sərbəst işi AKTİV olanlar — bir sorğu (bayraq yanılıdırsa sorğusuz)."""
    ids = {pk for pk in offering_ids if pk}
    if not ids or academic_rules.selfwork_enabled():
        return ids  # bayraq yanılıdır → köhnə və yeni bütün dövrlərdə sərbəst iş var
    rows = lookups.offering_model().objects.filter(pk__in=ids).select_related("period", "organization")
    return {row.pk for row in rows if offering_active(row, organization)}


def inactive_offering_ids(offering_ids, organization=None) -> set:
    """Sərbəst işi ləğv olunmuş açılışlar; bayraq yanılıdırsa boş (``offering_ids`` oxunmur — sorğusuz)."""
    if academic_rules.selfwork_enabled():
        return set()
    ids = {pk for pk in offering_ids if pk}
    return ids - active_offering_ids(ids, organization)


__all__ = ["active_offering_ids", "folder_active", "inactive_offering_ids", "offering_active"]
