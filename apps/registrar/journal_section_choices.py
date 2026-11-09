"""Jurnalın alt bölmələri — lab qrupları və seminar alt qrupları — dərs yükü seçicisi üçün (sahib 2026-11-09).

«Yük bölgüsü» kartı hər qrup üçün «Lab-1 / Lab-2» və «234 K1 / 234 K2» variantlarını göstərir ki, kafedra müdiri
bölgünü alt qrupa qədər seçə bilsin (``TeacherAssignment.sub_number``). Mənbə — mövcud qaydalar:
:func:`apps.registrar.lab_groups.offering_groups` (``LabGroup`` sətirləri ∪ aktiv siyahının ``lab_group`` dəyərləri)
və :func:`apps.registrar.seminar_groups.offering_groups`; adlar da həmin modulların :func:`label`-i ilə.

Toplu oxu: (fənn, dövr, qrup) açarları üçün BİR açılış sorğusu + üç toplu sorğu (lab sətirləri, seminar sətirləri,
siyahı nömrələri) — kart sayından asılı deyil.
"""

from __future__ import annotations

from collections import defaultdict

from . import lab_groups, seminar_groups
from .models import CourseOffering, Enrollment, LabGroup, SeminarGroup


def offering_section_choices(*, organization, keys) -> dict:
    """``{(fənn, dövr, qrup): {"lab": [{"number", "label"}], "seminar": [...]}}`` — yalnız bölməsi olan açılışlar."""
    keys = {tuple(key) for key in keys if key and all(key)}
    if not keys:
        return {}
    offerings = [
        offering
        for offering in CourseOffering.objects.filter(
            organization=organization,
            is_active=True,
            subject_id__in={key[0] for key in keys},
            period_id__in={key[1] for key in keys},
            group_id__in={key[2] for key in keys},
        ).select_related("group")
        if (offering.subject_id, offering.period_id, offering.group_id) in keys
    ]
    if not offerings:
        return {}
    by_pk = {offering.pk: offering for offering in offerings}
    ids = list(by_pk)
    lab_numbers, lab_names = defaultdict(set), defaultdict(dict)
    for offering_id, number, name in LabGroup.objects.filter(offering_id__in=ids).values_list(
        "offering_id", "number", "name"
    ):
        lab_numbers[offering_id].add(number)
        if name:
            lab_names[offering_id][number] = name
    seminar_numbers, seminar_names = defaultdict(set), defaultdict(dict)
    for offering_id, number, name in SeminarGroup.objects.filter(offering_id__in=ids).values_list(
        "offering_id", "number", "name"
    ):
        seminar_numbers[offering_id].add(number)
        if name:
            seminar_names[offering_id][number] = name
    roster = Enrollment.objects.filter(offering_id__in=ids, status=Enrollment.Status.ENROLLED)
    for offering_id, lab, seminar in roster.values_list("offering_id", "lab_group", "seminar_group"):
        if lab:
            lab_numbers[offering_id].add(lab)
        if seminar:
            seminar_numbers[offering_id].add(seminar)
    result = {}
    for offering in offerings:
        # Adlar memo-ya yazılır — ``label`` əlavə sorğu açmır (modulun öz memo açarı).
        setattr(offering, lab_groups._NAMES_ATTR, lab_names.get(offering.pk, {}))
        setattr(offering, seminar_groups._NAMES_ATTR, seminar_names.get(offering.pk, {}))
        labs = [
            {"number": number, "label": lab_groups.label(number, offering)}
            for number in sorted(lab_numbers.get(offering.pk, ()))
        ]
        seminars = [
            {"number": number, "label": seminar_groups.label(number, offering)}
            for number in sorted(seminar_numbers.get(offering.pk, ()))
        ]
        if labs or seminars:
            result[(offering.subject_id, offering.period_id, offering.group_id)] = {"lab": labs, "seminar": seminars}
    return result


__all__ = ["offering_section_choices"]
