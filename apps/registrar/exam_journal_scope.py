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


def twin_subject_ids(organization, subject_id, period, *, strict=False) -> set:
    """Dövrdə açılışı olan, adı (normallaşdırılmış) imtahanın fənni ilə EYNİ olan BAŞQA fənn kartları.

    ``strict`` (körpünün bağlantısız son ehtiyatı, 2026-11-11): kredit (ECTS) və növ də EYNİ olmalıdır — kataloq
    birləşməsinin avtomatik qaydası ilə eyni; eyni adlı, amma fərqli kreditli kart ayrı fənn ola bilər."""
    if organization is None or not subject_id or period is None:
        return set()
    own = Subject.objects.filter(organization=organization, pk=subject_id).values_list("name", "ects", "kind").first()
    key = normalized_subject_key(own[0] if own else "")
    if not key:
        return set()
    rows = (
        Subject.objects.filter(organization=organization, offerings__period=period, offerings__is_active=True)
        .exclude(pk=subject_id)
        .values_list("pk", "name", "ects", "kind")
        .distinct()
    )
    return {
        pk
        for pk, other, ects, kind in rows
        if normalized_subject_key(other) == key and (not strict or (ects, kind) == own[1:])
    }


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


def linked_twin_offering_ids(organization, subject_id, offerings) -> set:
    """Açıq bağlı jurnallardan hazırkı rəsmi əkiz/ailə qaydasına uyğun olanlar.

    Link köhnəlmiş ola bilər: hər dövrün ailəsi yenidən yoxlanır. Ailədə exact
    fənn açılışı varsa əkiz qəbul edilmir; oxşar ad üçün ayrıca təxmin yoxdur.
    """
    by_period = {}
    for offering in offerings:
        if offering.is_active:
            by_period.setdefault(offering.period, []).append(offering)
    accepted = set()
    for period, rows in by_period.items():
        _, _, families = unit_families(organization, [row.group_id for row in rows])
        coverage = journal_offerings_by_unit(organization, period, subject_id, families)
        for row in rows:
            twins = coverage.get(row.group_id, {}).get("twin", ())
            if any(pk == row.pk for pk, _group in twins):
                accepted.add(row.pk)
    return accepted


def family_enrollments(organization, subject_id, student_ids, period) -> dict:
    """``{tələbə id: [Enrollment]}`` — imtahanın fənni üzrə qeydiyyatı OLMAYAN tələbənin əkiz kartdakı jurnalı.

    Sahib 2026-11-11 («Fənnin jurnalında olmayan tələbə: 35 / 35»): imtahan dublikat kartın BİRİ ilə yaradılıb, qrupun
    jurnalı isə o biri kartın altındadır və imtahan jurnala açıq bağlanmayıb — körpü ``offering.subject == exam.subject``
    axtarıb heç nə tapmırdı. Qayda (``linked_twin_offering_ids`` ilə EYNİ, fail-closed): CARİ dövr, aktiv jurnal,
    ``enrolled`` qeydiyyat, fənnin normallaşdırılmış adı + krediti + növü imtahanın fənni ilə EYNİ, jurnalın qrup ailəsində imtahanın
    öz fənninin aktiv açılışı YOXDUR. Tələbənin belə jurnalları İKİ fərqli kartdadırsa (qeyri-müəyyən) — heç nə."""
    from apps.registrar.models import Enrollment

    ids = [value for value in student_ids or () if value is not None]
    if organization is None or not subject_id or period is None or not ids:
        return {}
    twins = twin_subject_ids(organization, subject_id, period, strict=True)
    if not twins:
        return {}
    rows = list(
        Enrollment.objects.filter(
            organization=organization,
            student_id__in=ids,
            offering__period=period,
            offering__is_active=True,
            offering__subject_id__in=twins,
            status=Enrollment.Status.ENROLLED,
        ).select_related("offering", "offering__period", "offering__subject")
    )
    if not rows:
        return {}
    exact = set(  # fənnin ÖZ kartında (istənilən dövr) aktiv qeydiyyatı olan tələbə üçün əkiz axtarılmır
        Enrollment.objects.filter(
            organization=organization,
            student_id__in={row.student_id for row in rows},
            offering__subject_id=subject_id,
            status=Enrollment.Status.ENROLLED,
        ).values_list("student_id", flat=True)
    )
    rows = [row for row in rows if row.student_id not in exact]
    if not rows:
        return {}
    accepted = linked_twin_offering_ids(
        organization, subject_id, {row.offering_id: row.offering for row in rows}.values()
    )
    out: dict = {}
    for row in rows:
        if row.offering_id in accepted:
            out.setdefault(row.student_id, []).append(row)
    return {student: items for student, items in out.items() if len({item.offering.subject_id for item in items}) == 1}


def family_enrollment(student, subject_id, organization, period):
    """Körpünün son ehtiyatı: fənn üzrə qeydiyyat YOXDURSA tələbənin dublikat kartdakı jurnal qeydiyyatı (və ya ``None``)."""
    import logging

    from .exam_bridge import pick_enrollment

    found = family_enrollments(organization, subject_id, [student.pk], period).get(student.pk)
    if not found:
        return None
    chosen = pick_enrollment(found)
    logging.getLogger("apps.registrar.exam_bridge").warning(
        "exam_bridge: subject %s has no enrollment for student %s — duplicate subject card journal %s used",
        subject_id,
        student.pk,
        chosen.offering_id,
    )
    return chosen


__all__ = [
    "family_enrollment",
    "family_enrollments",
    "journal_offerings_by_unit",
    "linked_twin_offering_ids",
    "twin_subject_ids",
    "unit_families",
]
