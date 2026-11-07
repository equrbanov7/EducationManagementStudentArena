"""Jurnal bölmələri — «Mühazirə · 234 K», «234 K1 · Seminar», «234 K1 · Lab-1» düymələri (sahib 2026-11-07).

Sahib: «mühazirədə 234 K bir göstərsin, seminarda 234 K1 və 234 K2-ni ayrı … lab-1, lab-2 … onu vurub açıb daxilini
yazsın, elə daha rahat olacaq». Jurnal BİR olaraq qalır; bölmə yalnız GÖRÜNÜŞDÜR (``journal_sections.js``): seçilmiş
bölmənin dərs sütunları və tələbə sətirləri göstərilir, yazı qaydaları dəyişmir (:func:`apps.registrar.lab_groups.applies`).

Bölmələr yalnız jurnal seminar alt qruplarına və ya lab qruplarına bölünəndə çıxır.
"""

from __future__ import annotations

from django.utils.translation import pgettext

_CTX = "registrar.journal_sections"


def build(offering, *, lab_groups_list, seminar_groups_list, lab_label, seminar_label) -> list:
    """``[{"kind", "group", "label"}, …]`` — boş siyahı = jurnal bölünməyib (düymə zolağı yoxdur)."""
    if not lab_groups_list and not seminar_groups_list:
        return []
    group_name = getattr(getattr(offering, "group", None), "name", "") or ""
    sections = [
        {"kind": "", "group": "", "label": pgettext(_CTX, "Hamısı")},
        {"kind": "lecture", "group": "", "label": " · ".join(filter(None, [group_name, pgettext(_CTX, "Mühazirə")]))},
    ]
    if seminar_groups_list:
        for number in seminar_groups_list:
            label = f"{seminar_label(number)} · {pgettext(_CTX, 'Seminar')}"
            sections.append({"kind": "seminar", "group": str(number), "label": label})
    else:
        sections.append({"kind": "seminar", "group": "", "label": pgettext(_CTX, "Seminar")})
    for number in lab_groups_list:
        sections.append({"kind": "lab", "group": str(number), "label": lab_label(number)})
    return sections


def for_offering(offering) -> list:
    """Jurnal qridi üçün bölmələr (memo-lar ``gradebook`` primingindən gəlir — əlavə sorğu yoxdur)."""
    from . import lab_groups, seminar_groups

    return build(
        offering,
        lab_groups_list=lab_groups.offering_groups(offering),
        seminar_groups_list=seminar_groups.offering_groups(offering),
        lab_label=lambda number: lab_groups.label(number, offering),
        seminar_label=lambda number: seminar_groups.label(number, offering),
    )


__all__ = ["build", "for_offering"]
