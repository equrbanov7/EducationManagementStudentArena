"""Köçürülmüş imtahansız səviyyə kursu — «yekun = giriş balı» statusunun mətnləri (sahib qərarı 2026-11-09).

Köhnə sistem 2024/2025–2025/2026 xarici dil səviyyə kurslarını imtahansız aparıb; nəticə
:func:`apps.registrar.finals.legacy_level_entry_only` ilə seçilir. Kodu ``exam_eligibility.status_code``
ailəsinə paraleldir (``live`` / ``legacy`` / ``legacy_no_result``), mətnləri isə burada saxlanır.
"""

from django.utils.translation import pgettext_lazy

STATUS_LEGACY_ENTRY_ONLY = "legacy_entry_only"

LABEL = pgettext_lazy("registrar.eligibility", "Köhnə sistem: imtahansız kurs, yekun = giriş balı")

NOTICE = pgettext_lazy(
    "registrar.eligibility",
    "Köhnə sistemdə xarici dil səviyyə kursları imtahansız aparılıb: yekun bal giriş balına bərabərdir və fənn "
    "keçilmiş sayılır. Bu nəticə ÜOMG-yə daxil edilmir.",
)

__all__ = ["LABEL", "NOTICE", "STATUS_LEGACY_ENTRY_ONLY"]
