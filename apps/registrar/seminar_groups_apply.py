"""Seminar alt qruplarını reyestrdən doldur (sahib 2026-11-07: «234 K1 və 234 K2-ni ayrı göstərsin … 234 K1 · Lab-1»).

Namizəd jurnal: cari dövrün aktiv açılışı, qrupu ANA qrupdur (reyestr ``settings.parent_group`` izi və ya ad qaydası —
:func:`apps.registrar.subgroup_rollup.subgroup_map`) və aktiv siyahısında ən azı İKİ alt qrupun tələbəsi var
(tələbənin cari akademik qrupu üzrə). Hər namizəddə:

* ailənin alt qrupları ad sırası ilə nömrələnir — ``SeminarGroup`` (ad = «234 K1», mənbə = alt qrup) yaradılır;
* ``Enrollment.seminar_group`` YALNIZ boşdursa yazılır (başqa dəyər — ``*_conflict``, toxunulmur);
* lab qrupunun bütün tələbələri bir alt qrupdadırsa və adı boşdursa ad «234 K1 · Lab-1» olur.

Mövcud dərslər dəyişmir (``Lesson.seminar_group`` boş = bütün qrup) — yəni yazı davranışı DƏYİŞMİR, yalnız alt qrup
seçimi və bölmə düymələri açılır. İdempotentdir. Stdout-da yalnız saylar.
"""

from __future__ import annotations

from collections import defaultdict

from django.apps import apps as django_apps

from core.audit import log_action
from core.constants import AuditAction

from .subgroup_rollup import subgroup_map

REASON = "Sahib 2026-11-07: seminar alt qrupları reyestrin alt qruplarından (234 K1 / 234 K2)"
RESOURCE = "registrar.seminar_groups"
MIN_FAMILIES = 2


def _model(app, name):
    return django_apps.get_model(app, name)


def _offerings(organization, offering_ids):
    CourseOffering = _model("registrar", "CourseOffering")
    rows = CourseOffering.objects.filter(
        organization=organization, is_active=True, group__isnull=False, period__is_current=True
    ).select_related("group")
    if offering_ids:
        rows = rows.filter(pk__in=offering_ids)
    return list(rows)


def _record_groups(organization, student_ids) -> dict:
    Record = _model("registrar", "StudentAcademicRecord")
    return dict(
        Record.objects.filter(organization=organization, student_id__in=student_ids, is_active=True)
        .exclude(group__isnull=True)
        .values_list("student_id", "group_id")
    )


def _name_labs(offering, numbers_by_child, children_by_pk, enrolled, counts) -> None:
    LabGroup = _model("registrar", "LabGroup")
    members = defaultdict(set)
    for row in enrolled:
        if row.lab_group and row.seminar_group:
            members[row.lab_group].add(row.seminar_group)
    by_number = {number: child for child, number in numbers_by_child.items()}
    for lab_number, seminar_numbers in sorted(members.items()):
        if len(seminar_numbers) != 1:
            counts["lab_mixed"] += 1
            continue
        child = children_by_pk[by_number[next(iter(seminar_numbers))]]
        name = f"{child.name} · Lab-{lab_number}"[:40]
        row = LabGroup.objects.filter(offering=offering, number=lab_number).first()
        if row is None:
            LabGroup.objects.create(
                organization_id=offering.organization_id, offering=offering, number=lab_number, name=name
            )
            counts["lab_named"] += 1
        elif not row.name:
            row.name = name
            row.save(update_fields=["name", "updated_at"])
            counts["lab_named"] += 1
        else:
            counts["lab_name_kept"] += 1


def _apply_offering(offering, family, actor, counts) -> None:
    Enrollment = _model("registrar", "Enrollment")
    SeminarGroup = _model("registrar", "SeminarGroup")
    enrolled = list(Enrollment.objects.select_for_update().filter(offering=offering, status=Enrollment.Status.ENROLLED))
    groups = _record_groups(offering.organization, [row.student_id for row in enrolled])
    children_by_pk = {child.pk: child for child in family}
    numbers_by_child = {child.pk: index for index, child in enumerate(family, start=1)}
    present = {groups.get(row.student_id) for row in enrolled} & set(children_by_pk)
    if len(present) < MIN_FAMILIES:
        counts["journals_single_subgroup_skipped"] += 1
        return
    counts["journals"] += 1
    existing = {row.number: row for row in SeminarGroup.objects.filter(offering=offering)}
    for child_pk, number in numbers_by_child.items():
        child = children_by_pk[child_pk]
        row = existing.get(number)
        if row is None:
            SeminarGroup.objects.create(
                organization_id=offering.organization_id, offering=offering, number=number, name=child.name, unit=child
            )
            counts["seminar_groups_created"] += 1
        elif row.unit_id not in (None, child.pk):
            counts["seminar_group_conflict"] += 1
            return
    changed = []
    for row in enrolled:
        number = numbers_by_child.get(groups.get(row.student_id))
        if number is None:
            counts["students_outside_subgroups"] += 1
        elif row.seminar_group == number:
            counts["students_already"] += 1
        elif row.seminar_group is not None:
            counts["students_conflict"] += 1
        else:
            row.seminar_group = number
            changed.append(row)
    if changed:
        Enrollment.objects.bulk_update(changed, ["seminar_group"])
        counts["students_placed"] += len(changed)
    _name_labs(offering, numbers_by_child, children_by_pk, enrolled, counts)
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=offering.organization,
        obj=offering,
        old_values={},
        new_values={
            "seminar_groups": {str(n): children_by_pk[c].name for c, n in numbers_by_child.items()},
            "placed": [str(row.pk) for row in changed],
        },
        reason=REASON,
        resource_type=RESOURCE,
        resource_id=str(offering.pk),
    )


def run(*, organization, actor, counts, offering_ids=()) -> None:
    offerings = _offerings(organization, offering_ids)
    families = subgroup_map(organization, list({offering.group_id: offering.group for offering in offerings}.values()))
    counts["candidates"] += sum(1 for offering in offerings if offering.group_id in families)
    for offering in offerings:
        family = families.get(offering.group_id)
        if family:
            _apply_offering(offering, family, actor, counts)


__all__ = ["MIN_FAMILIES", "REASON", "run"]
