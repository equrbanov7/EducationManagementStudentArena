"""İmtahan qrupunun jurnal «ailəsi» + dublikat fənn kartı (əkiz) — ``exam_journal_link`` / ``exam_journal_gaps``.

Sahib 2026-10-27: «bəzilərini deyir ki jurnalı yoxdur». İmtahan sehrbazının qrup yoxlaması
(:func:`apps.registrar.exam_journal_link.group_subject_coverage`) və imtahan ↔ jurnal bağlantısı
(:func:`~apps.registrar.exam_journal_link.link_offering_ids`) EYNİ qaydanı bu moduldan alır:

* **Ailə** — seçilmiş reyestr qrupu + alt qrupları («234 K az» → 234 K-1/-2) + ana qrup namizədləri
  (``subgroup_rollup.group_family``; hamısı üçün BİR sorğu).
* **Əkiz fənn** — fənn kataloqunda normallaşdırılmış adı EYNİ olan başqa kart («VoİP …» ↔ «Vo İP …»,
  ``subject_duplicates.normalized_subject_key``). Legacy köçürmədə qrupun jurnalı bəzən əkiz kartın altına
  düşüb; imtahan isə başqa kartla yaradılır → sehrbaz «jurnalı yoxdur» deyirdi, nəticə də jurnala düşmürdü.
  Qayda (fail-closed): əkizin açılışı YALNIZ qrupun ailəsində imtahanın öz fənninin açılışı OLMAYANDA sayılır
  (iki jurnallı qrupda balı təsadüfi jurnala yazmamaq üçün). Adı yalnız oxşar olan («Azərbaycan tarixi» ↔
  «Azərbaycanın tarixi») kart əkiz DEYİL — o, insan qərarıdır (``merge_subjects`` / ``merge_twin_offerings``).
"""

from __future__ import annotations

from django.apps import apps as django_apps

from apps.registrar import subgroup_rollup
from apps.registrar.models import CourseOffering, Subject
from apps.registrar.subject_duplicates import normalized_subject_key


def unit_families(organization, group_ids) -> tuple[list, dict, dict]:
    """→ ``(qruplar, own, linked)``: ``own[pk]`` — qrup + alt qrupları, ``linked[pk]`` — ``own`` + ana qruplar."""
    group_ids = {str(value) for value in group_ids or () if value}
    if organization is None or not group_ids:
        return [], {}, {}
    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    units = list(
        OrgUnit.objects.filter(organization=organization, pk__in=group_ids, unit_type="group").only(
            "id", "name", "parent_id", "settings"
        )
    )
    family = subgroup_rollup.group_family(organization, units) if units else {}
    own, linked = {}, {}
    for unit in units:
        subs, parents = family.get(unit.pk, ((), ()))
        own[unit.pk] = {unit.pk} | {sub.pk for sub in subs}
        linked[unit.pk] = own[unit.pk] | {parent.pk for parent in parents}
    return units, own, linked


def twin_subject_ids(organization, subject_id, period) -> set:
    """Dövrdə açılışı olan, adı (normallaşdırılmış) imtahanın fənni ilə EYNİ olan BAŞQA fənn kartları."""
    if organization is None or not subject_id or period is None:
        return set()
    name = Subject.objects.filter(organization=organization, pk=subject_id).values_list("name", flat=True).first()
    key = normalized_subject_key(name or "")
    if not key:
        return set()
    rows = (
        Subject.objects.filter(organization=organization, offerings__period=period, offerings__is_active=True)
        .exclude(pk=subject_id)
        .values_list("pk", "name")
        .distinct()
    )
    return {pk for pk, other in rows if normalized_subject_key(other) == key}


def journal_offerings_by_unit(organization, period, subject_id, linked) -> dict:
    """``{qrup_pk: {"exact": [(açılış, qrup)], "twin": [(açılış, qrup)]}}`` — qrupun ailəsindəki aktiv jurnallar.

    ``twin`` yalnız ailədə imtahanın öz fənninin açılışı YOXDURSA doludur (bax modulun sənədi)."""
    out = {pk: {"exact": [], "twin": []} for pk in linked or {}}
    all_ids = set().union(*linked.values()) if linked else set()
    if organization is None or period is None or not subject_id or not all_ids:
        return out
    base = CourseOffering.objects.filter(
        organization=organization, period=period, is_active=True, group_id__in=all_ids
    ).order_by("pk")
    exact = list(base.filter(subject_id=subject_id).values_list("pk", "group_id"))
    covered = {unit for unit, ids in linked.items() if any(gid in ids for _pk, gid in exact)}
    twin_rows = []
    if len(covered) < len(linked):
        twins = twin_subject_ids(organization, subject_id, period)
        if twins:
            twin_rows = list(base.filter(subject_id__in=twins).values_list("pk", "group_id"))
    for unit, ids in linked.items():
        out[unit]["exact"] = [row for row in exact if row[1] in ids]
        if unit not in covered:
            out[unit]["twin"] = [row for row in twin_rows if row[1] in ids]
    return out


__all__ = ["journal_offerings_by_unit", "twin_subject_ids", "unit_families"]
