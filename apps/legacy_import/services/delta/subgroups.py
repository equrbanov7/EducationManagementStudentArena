"""Köhnə sistemin ALT QRUP tələbələri — yeni sistemdə rəsmi işarə (sahib 2026-10-25).

Sahib: «Alt qrup tələbələrini tapsan işarələ — yeni sistemdə işarələyərək göndər, görünsün ki alt qrupdur.»

Köhnə sistemdə (myedu) alt qrup AYRICA QRUPDUR («536 MU1», «536 MU2», «135 Si-1») — ana qrupla əlaqə
sütunu yoxdur, yalnız ad naxışı; tələbənin ``students.group_id``-si alt qrupa baxır. Yeni sistemdə həmin
tələbə çox vaxt ANA qrupdadır («536 MU»), alt qrupun jurnalına isə delta onu «alt qrupdan əlavə»
(``Enrollment.source_group``) kimi yazıb. Çatışmayan iki iz bu fazada yazılır — HƏR İKİSİ mövcud rəsmi
mexanizmdir, yeni model yoxdur:

1. **Alt qrup → ana qrup izi** (``OrgUnit.settings.parent_group``, ``group_split`` / ``ensure_parent_groups``
   açarı): paketdəki tələbələrin legacy qrupuna uyğun vahidin izi yoxdursa, EYNİ ixtisas altında ad
   ailəsinə uyğun TƏK aktiv ana qrup tapılanda yazılır («536 Bi 1» → «536 Bİ»; «İ/i» fərqi nəzərə alınmır —
   ``ensure_group``-un yaradılışda yaza bilmədiyi iz). Bir neçə namizəd / heç biri — yazılmır, sayılır.
2. **«Alt qrupa yerləşdirildi» tarixçə sətri** (``SubgroupPlacementEvent``,
   :func:`apps.registrar.public.record_imported_placement`): legacy-də alt qrupda (S) olan, yeni sistemdə
   başqa qrupda olan tələbənin S-in jurnalındakı canlı «alt qrupdan əlavə» qeydiyyatına — səbəb
   ``REASON``. Qeydiyyata, bala, davamiyyətə toxunulmur; bildiriş getmir.

Yalnız SAYILAN (yazılmayan) hallar — qərar sahibindir: legacy qrupu alt qrup deyil, amma yeni sistemdə
başqa qrupdadır (qrup fərqi); tələbə alt qrup fənnini ANA qrupun jurnalında keçir (köçürmə xanaları ora
yazıb — tələbəni köçürmək balları gizlədərdi); alt qrupun jurnalında qeydiyyatı yoxdur.

Dövr: paketin ``snapshot.full_semesters``-i (``dedupe`` ilə eyni). İdempotent: iz varsa yazılmır, qeydiyyatın
``place`` sətri varsa (geri götürülmüş olsa da) yenisi yazılmır.
"""

from __future__ import annotations

import re
from collections import defaultdict

from django.apps import apps as django_apps

from .resolve import text

REASON = "Köhnə sistemdən köçürmə: alt qrup"
LINK_REASON = "Köhnə sistemdən köçürmə: alt qrup — ana qrup izi (settings.parent_group)"
#: Ad alt qrup şəkilçisi ilə bitir: hərf + (ayırıcı) + 1–2 rəqəm (+ sektor) — «536 MU1», «135 Si-1», «534 TB 1».
_SUBGROUP_TAIL = re.compile(r"[^\W\d_]\s*[-/\s]?\s*\d{1,2}(?:\s*(?:az|ing|ru|en))?$", re.IGNORECASE)


def _fold(name) -> str:
    """«İ»/«ı» → «I»/«i»: ``casefold("İ")`` = «i̇» (nöqtəli), «Bİ» ilə «Bi» eyni ailə sayılsın."""
    return str(name or "").replace("İ", "I").replace("ı", "i")


def _trail(unit) -> str:
    return str((unit.settings if isinstance(unit.settings, dict) else {}).get("parent_group") or "")


def is_family(parent_name: str, sub_name: str) -> bool:
    from apps.registrar.public import subgroup_rollup

    return subgroup_rollup.is_subgroup_of(_fold(parent_name), _fold(sub_name))


def looks_like_subgroup(name: str) -> bool:
    return bool(_SUBGROUP_TAIL.search(" ".join(str(name or "").split())))


class _Units:
    def __init__(self, catalog):
        self.by_str = {str(pk): unit for pk, unit in catalog.units.items()}
        self.groups = [unit for unit in catalog.units.values() if unit.unit_type == "group" and unit.is_active]

    def parent_of(self, unit):
        """``(ana qrup | None, üsul)`` — üsul: trail / name / ambiguous / none."""
        trail = _trail(unit)
        if trail:
            return self.by_str.get(trail), "trail"
        found = [
            other
            for other in self.groups
            if other.pk != unit.pk
            and other.parent_id == unit.parent_id
            and not _trail(other)
            and is_family(other.name, unit.name)
        ]
        if len(found) == 1:
            return found[0], "name"
        return None, ("ambiguous" if found else "none")


def _link(run, unit, parent) -> None:
    from apps.audit.public import log_action
    from core.constants import AuditAction

    blob = dict(unit.settings) if isinstance(unit.settings, dict) else {}
    blob["parent_group"] = str(parent.pk)
    blob["parent_group_name"] = parent.name
    unit.settings = blob
    unit.save(update_fields=["settings", "updated_at"])
    log_action(
        action=AuditAction.UPDATE,
        user=run.actor,
        organization=run.organization,
        obj=unit,
        old_values={"parent_group": None},
        new_values={"parent_group": str(parent.pk), "parent_group_name": parent.name},
        reason=LINK_REASON,
    )


def _members(run, units: _Units) -> dict:
    """``{alt qrup vahidi: {user_id}}`` — legacy qrupu alt qrup olan, yeni sistemdə BAŞQA qrupda olan tələbələr.

    Əvvəl hər istinad olunan vahid üçün ana qrup izi yoxlanılır / yazılır (bir dəfə), sonra tələbələr.
    """

    placed: list = []
    parents: dict = {}
    for row in run.bundle["students"]:
        legacy_group = run.legacy_groups.get(row.get("group_id"))
        unit = run.catalog.group_for(legacy_group)[0] if legacy_group else None
        if unit is None or unit.unit_type != "group" or not unit.is_active:
            continue
        placed.append((row, unit))
        if unit.pk in parents:
            continue
        parent, how = units.parent_of(unit)
        if how == "name" and parent is not None and parent.is_active:
            _link(run, unit, parent)
            run.count("subgroups.unit_linked")
            run.touched("groups", unit.pk, ["settings"])
            run.names("subgroup_unit_linked", unit.name, parent.name)
        elif how == "ambiguous":
            run.count("subgroups.unit_parent_ambiguous")
            run.names("subgroup_unit_parent_ambiguous", unit.name, "")
        elif how == "trail":
            run.count("subgroups.unit_already_linked")
        parents[unit.pk] = parent
    members: dict = defaultdict(set)
    for row, unit in placed:
        user_id, _outcome = run.students.resolve(row["id"], create=False)
        if user_id is None:
            continue
        own = run.students.group_of.get(user_id)
        if own is None or own == unit.pk:
            run.count("subgroups.student_in_own_group" if own else "subgroups.student_without_record")
            continue
        if parents.get(unit.pk) is None and not looks_like_subgroup(unit.name):
            own_unit = units.by_str.get(str(own))
            run.count("subgroups.group_differs_report_only")
            run.names("student_group_differs", _display(row), f"{unit.name} ≠ {getattr(own_unit, 'name', '')}")
            continue
        members[unit].add(user_id)
    return members


def mark_subgroups(run, period_ids) -> None:
    from apps.registrar.public import credit_load, record_imported_placement

    period_ids = [pk for pk in period_ids if pk]
    if not period_ids:
        run.count("subgroups.no_period")
        return
    units = _Units(run.catalog)
    members = _members(run, units)
    if not members:
        return
    Enrollment = django_apps.get_model("registrar", "Enrollment")
    CourseOffering = django_apps.get_model("registrar", "CourseOffering")
    student_ids = {user_id for users in members.values() for user_id in users}
    rows: dict = defaultdict(list)
    for enrollment in Enrollment.objects.filter(
        organization=run.organization, status="enrolled", offering__period_id__in=period_ids, student_id__in=student_ids
    ).select_related("student", "offering__subject", "offering__period", "offering__organization"):
        rows[enrollment.student_id].append(enrollment)
    subjects: dict = defaultdict(set)
    for group_id, subject_id in CourseOffering.objects.filter(
        organization=run.organization, group__in=list(members), period_id__in=period_ids, is_active=True
    ).values_list("group_id", "subject_id"):
        subjects[group_id].add(subject_id)
    loads: dict = {}
    for unit in sorted(members, key=lambda item: item.name):
        for user_id in sorted(members[unit]):
            enrollments = rows.get(user_id, [])
            inside = [e for e in enrollments if e.offering.group_id == unit.pk]
            covered = {e.offering.subject_id for e in inside}
            elsewhere = {e.offering.subject_id for e in enrollments if e.offering.group_id != unit.pk}
            missing = subjects.get(unit.pk, set()) - covered
            run.count("subgroups.subject_in_other_journal", len(missing & elsewhere))
            run.count("subgroups.subject_not_enrolled", len(missing - elsewhere))
            if not inside:
                run.count("subgroups.student_without_subgroup_journal")
                continue
            marked = False
            for enrollment in inside:
                if enrollment.source_group_id is None:
                    run.count("subgroups.enrollment_without_source")
                    continue
                key = (user_id, enrollment.offering.period_id)
                if key not in loads:
                    loads[key] = credit_load(
                        enrollment.student, enrollment.offering.period, organization=run.organization
                    )
                event = record_imported_placement(
                    enrollment=enrollment,
                    actor=run.actor,
                    reason=REASON,
                    details={"source": "legacy_delta", "batch": run.tag},
                    load=loads[key],
                )
                run.count(
                    "subgroups.placement_recorded" if event is not None else "subgroups.placement_already_recorded"
                )
                if event is not None:
                    run.count("written.subgroup_placements")
                marked = True
            run.count("subgroups.student_marked" if marked else "subgroups.student_unmarked")


def _display(row: dict) -> str:
    return " ".join(part for part in (text(row.get("last_name")), text(row.get("first_name"))) if part)


__all__ = ["LINK_REASON", "REASON", "is_family", "looks_like_subgroup", "mark_subgroups"]
