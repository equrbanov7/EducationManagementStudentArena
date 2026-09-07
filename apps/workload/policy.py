"""Dərs yükü SİYASƏTİ — dekan təsdiqi üçün koordinator vizası (QA 2026-09-05 P2-36).

Auditdə dekan **0 viza** ilə və **iradlı (flagged) sətir ola-ola** fakültə
dilimini təsdiqləyə bilirdi — yəni koordinator baxışı praktikada məcburi deyildi.

Qayda org səviyyəsində açar/bağlıdır; saxlama yeri mövcud ``Organization.settings``
JSON sahəsidir — YENİ CƏDVƏL YOX, migration YOX (``registrar/journal_policy.py``
və ``syllabus/policy.py`` ilə eyni naxış)::

    organization.settings = {"workload": {"visa_required": false}}

**Default = AÇIQ** (sahib tövsiyəsi): dilim təsdiqindən əvvəl həmin fakültənin
bütün sətirlərinə koordinator baxmalıdır. Köçürülmüş semestri təsdiqləmək
lazım gələrsə açar tenant üçün söndürülür.

İradlı sətir qapısı siyasətdən ASILI DEYİL: irad qaldırılıbsa dilim
təsdiqlənmir — əvvəl irad həll olunmalı və ya sətir geri qaytarılmalıdır.

Modul sərhədi: ``apps.organizations`` import EDİLMİR — yalnız ötürülən obyektin
``settings`` atributu oxunur (ördək tipi).
"""

from __future__ import annotations

#: ``Organization.settings`` içindəki bölmə açarı.
POLICY_SECTION = "workload"

#: Siyasət açarının adı.
VISA_REQUIRED = "visa_required"

#: Sahib qərarı (2026-09-06): default AÇIQ.
VISA_REQUIRED_DEFAULT = True


def visa_required(organization) -> bool:
    """Dilim təsdiqi koordinator vizası tələb edirmi (org açarı, default açıq)."""
    settings = getattr(organization, "settings", None) or {}
    if not isinstance(settings, dict):
        return VISA_REQUIRED_DEFAULT
    section = settings.get(POLICY_SECTION) or {}
    if not isinstance(section, dict) or VISA_REQUIRED not in section:
        return VISA_REQUIRED_DEFAULT
    return bool(section.get(VISA_REQUIRED))


__all__ = ["POLICY_SECTION", "VISA_REQUIRED", "VISA_REQUIRED_DEFAULT", "visa_required"]
