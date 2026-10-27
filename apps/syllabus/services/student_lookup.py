"""Tələbənin (və müşahidəçinin) GÖRDÜYÜ təsdiqlənmiş sillabus — kabinet keçidi və oxu səthi üçün TƏK qayda.

Sahib 2026-10-26: «digər fənlərdəki sillabus görünmədi, onu da göstər». Əvvəl kabinet keçidi pillələrin yalnız ilk
ikisinə baxırdı, oxu səthi isə ilk tapdığı dosyeni götürüb təsdiqlənməyibsə 404 verirdi. Tələbə ana qrupun («234 K
az») jurnalındadırsa, eyni müəllimin bölmə qrupunun («234 K-1») açılışına bağlı təsdiqlənmiş sillabusu da görünmürdü.

Qayda — YALNIZ təsdiqlənmiş versiyası olan aktiv dosyelər, pillə sırası ilə:

1. açılışın öz dosyesi;
2. paylaşım — açılış eyni müəllimin başqa qrupunun sillabusunu ÖZ YERİNDƏ istifadə edir (sahib 2026-10-27);
3. fənn + dövr (açılışsız);
4. fənn + müəllim (açılışsız, dövrsüz — köçürmə / ümumi sillabus);
5. eyni fənn, eyni dövr, EYNİ müəllimin başqa açılışının dosyesi (ana qrup ↔ bölmə qrupu).

Başqa müəllimin sillabusu heç vaxt götürülmür. Müəllim / redaktor rejimi bu modula toxunmur
(:func:`apps.syllabus.services.offerings.syllabus_for_offering`).
"""

from __future__ import annotations

from django.db.models import FilteredRelation, Q

from ..constants import SyllabusStatus
from ..models import Syllabus

_FIELDS = (
    "pk",
    "offering_id",
    "offering__period_id",
    "offering__instructor_id",
    "subject_id",
    "period_id",
    "author_id",
)


def _tier(row, offering, shared=None):
    pk, s_offering, s_offering_period, s_offering_teacher, subject_id, period_id, author_id = row
    if s_offering is not None and s_offering == offering.id:
        return 1
    if shared is not None and pk == shared:
        return 2
    if subject_id != offering.subject_id:
        return None
    if s_offering is None and period_id is not None and period_id == offering.period_id:
        return 3
    teacher = offering.instructor_id
    if s_offering is None and period_id is None and teacher is not None and author_id == teacher:
        return 4
    if s_offering is not None and teacher is not None and s_offering_period == offering.period_id:
        if s_offering_teacher == teacher or (s_offering_teacher is None and author_id == teacher):
            return 5
    return None


def student_syllabus_map(organization, offerings) -> dict:
    """``{offering_id: syllabus_pk}`` — təsdiqlənmiş sillabusu tapılan açılışlar (BİR sorğu).

    Paylaşım (sahib 2026-10-27) eyni sorğuda şərtli LEFT JOIN-dur (``FilteredRelation``): dosye hər uyğun paylaşım
    üçün bir sətir verir; tətbiq qapısı (açılışın müəllimi = dosyenin müəllifi / öz açılışının müəllimi) Python-dadır.
    """
    offerings = [offering for offering in offerings if offering is not None]
    if organization is None or not offerings:
        return {}
    offering_ids = [offering.id for offering in offerings]
    rows = list(
        Syllabus.objects.filter(
            organization=organization,
            is_active=True,
            approved_version__status=SyllabusStatus.APPROVED.value,
            subject_id__in={offering.subject_id for offering in offerings},
        )
        .annotate(_share=FilteredRelation("shares", condition=Q(shares__offering_id__in=offering_ids)))
        .order_by("subject__code", "pk")
        .values_list(*_FIELDS, "_share__offering_id")
    )
    shared: dict = {}
    for row in rows:
        share_offering, owners = row[-1], {row[3], row[6]}
        if share_offering is not None:
            shared.setdefault(share_offering, (row[0], owners))
    result: dict = {}
    for offering in offerings:
        share = shared.get(offering.id)
        share_pk = (
            share[0] if share and offering.instructor_id is not None and offering.instructor_id in share[1] else None
        )
        best = None
        for row in rows:
            tier = _tier(row[:-1], offering, share_pk)
            if tier is not None and (best is None or tier < best[0]):
                best = (tier, row[0])
        if best is not None:
            result[offering.id] = best[1]
    return result


def student_syllabus_for_offering(organization, offering):
    """Tələbəyə göstəriləcək təsdiqlənmiş sillabus dosyesi və ya ``None`` (≤ 2 sorğu)."""
    from .offerings import _RELATED

    pk = student_syllabus_map(organization, [offering]).get(getattr(offering, "id", None))
    if pk is None:
        return None
    return Syllabus.objects.select_related(*_RELATED).filter(pk=pk).first()


__all__ = ["student_syllabus_for_offering", "student_syllabus_map"]
