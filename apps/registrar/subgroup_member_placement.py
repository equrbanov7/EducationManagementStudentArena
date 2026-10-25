"""Ana qrupda qalmış tələbəni jurnal sübutu ilə ALT QRUPA köçürür (sahib 2026-10-26).

Sahib: «ana qrupda 30 nəfər göstərir, bölünəndə birində 11, o birində 8 — 19 edir … göndərişdə olana baxaraq
alt qrupa yığ». Köhnə datadan gələn alt qruplarda (``3/336F1`` / ``3/336F2``) tələbələrin bir hissəsinin
reyestr qrupu ana qrup («3/336 F») qalıb, halbuki onlar faktiki olaraq bir alt qrupun jurnallarında oxuyur.

SÜBUT
─────
Tələbənin CARİ dövrdə alt qrup açılışlarındakı dərs xanaları (``LessonMark``). Xarici dil SƏVİYYƏ fənləri
(:mod:`apps.registrar.language_levels`) sayılmır — səviyyə jurnalı qrupları qarışdırır. Xanaların hamısı (və ya
≥ :data:`MAJORITY`) tək alt qrupdadırsa hədəf odur; xana yoxdursa və ya bölünübsə — toxunulmur (sayılır).

YAZI
────
Rəsmi köçürmə xidməti (``transfer.transfer_student_group``) — reyestrdəki «Qrupu dəyiş» ilə eyni yol (DB
qapısı, tarixçə, audit, PIN siqnalı). Ondan ƏVVƏL: ana qrupun BOŞ (heç bir sübutu olmayan) qeydiyyatı, hədəf alt
qrupda həmin fənnin açılışı YOXDURSA, «Jurnal təmizliyi» qərarı ilə ``dropped`` olur — əks halda köçürmə alt
qrupda ikinci, boş jurnal açardı (məs. ana qrupun «Müasir İKT…» jurnalı, alt qrupda isə eyni müəllimin başqa adlı
fənni). Qərar «Jurnal təmizliyi» → «Tarixçə»-dən geri qaytarılır.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from django.db import transaction
from django.db.models import Count

from . import journal_hygiene as hygiene
from . import journal_hygiene_actions as hygiene_actions
from . import subgroup_rollup
from .language_levels import is_level_subject
from .models import CourseOffering, Enrollment, LessonMark, StudentAcademicRecord

#: Xanaların bu payı bir alt qrupdadırsa hədəf sayılır.
MAJORITY = 0.75
REASON_CODE = "subgroup_placement"
CATEGORY = "empty_subject"


@dataclass
class Placement:
    record_id: object
    student_id: int
    parent_id: object
    target_id: object = None
    status: str = ""
    marks: dict = field(default_factory=dict)


def _parents(organization, names=()):
    from django.apps import apps as django_apps

    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    queryset = OrgUnit.objects.filter(organization=organization, unit_type="group", is_active=True)
    if names:
        queryset = queryset.filter(name__in=list(names))
    groups = list(queryset.select_related("parent"))
    mapping = subgroup_rollup.subgroup_map(organization, groups)
    out = {}
    for parent in groups:
        units = [unit for unit in mapping.get(parent.pk, []) if unit.is_active]
        if units:
            out[parent.pk] = units
    return out


def _marks(organization, period, student_ids, group_ids) -> dict:
    """``{student_id: {group_id: xana sayı}}`` — cari dövr, səviyyə fənləri xaric."""
    rows = (
        LessonMark.objects.filter(
            enrollment__organization=organization,
            enrollment__student_id__in=student_ids,
            enrollment__offering__period=period,
            enrollment__offering__group_id__in=group_ids,
        )
        .values("enrollment__student_id", "enrollment__offering__group_id", "enrollment__offering__subject__name")
        .annotate(total=Count("id"))
    )
    out: dict = defaultdict(Counter)
    for row in rows:
        if is_level_subject(row["enrollment__offering__subject__name"]):
            continue
        out[row["enrollment__student_id"]][row["enrollment__offering__group_id"]] += row["total"]
    return out


def _parent_journal_data(organization, period, records) -> set:
    """``{(student_id, ana_qrup_id)}`` — ana qrupun cari açılışlarında HƏR HANSI sübutu olan qeydiyyatlar."""
    if not records:
        return set()
    return set(
        Enrollment.objects.filter(
            organization=organization,
            offering__period=period,
            offering__group_id__in={row["group_id"] for row in records},
            student_id__in={row["student_id"] for row in records},
            status=Enrollment.Status.ENROLLED,
        )
        .filter(hygiene.evidence_q())
        .values_list("student_id", "offering__group_id")
    )


def plan(organization, period, *, names=()) -> list[Placement]:
    """Hər ana qrup tələbəsi üçün hədəf alt qrup (və ya imtina statusu)."""
    parents = _parents(organization, names)
    if not parents:
        return []
    records = list(
        StudentAcademicRecord.objects.filter(
            organization=organization, is_active=True, status="enrolled", group_id__in=list(parents)
        ).values("id", "student_id", "group_id")
    )
    sub_ids = {unit.pk for units in parents.values() for unit in units}
    marks = _marks(organization, period, [row["student_id"] for row in records], sub_ids)
    parent_data = _parent_journal_data(organization, period, records)
    out = []
    for row in records:
        item = Placement(record_id=row["id"], student_id=row["student_id"], parent_id=row["group_id"])
        own = {unit.pk for unit in parents[row["group_id"]]}
        counts = {gid: n for gid, n in marks.get(row["student_id"], {}).items() if gid in own}
        item.marks = counts
        total = sum(counts.values())
        if (row["student_id"], row["group_id"]) in parent_data:
            # Ana qrupun ÖZ jurnalında datası var — köçürmə onu tarixçəyə keçirərdi (mühazirə ana qrupda,
            # məşğələ alt qrupda ola bilər). Toxunulmur.
            item.status = "parent_journal_data"
        elif not total:
            item.status = "no_evidence"
        else:
            best, best_n = max(counts.items(), key=lambda pair: pair[1])
            if best_n == total or best_n / total >= MAJORITY:
                item.target_id, item.status = best, "place"
            else:
                item.status = "ambiguous"
        out.append(item)
    return out


def _orphan_empty_enrollments(organization, period, record, target):
    """Ana qrupun BOŞ qeydiyyatları ki, hədəf alt qrupda həmin fənnin açılışı yoxdur (köçürmə yeni jurnal açardı)."""
    target_subjects = set(
        CourseOffering.objects.filter(organization=organization, period=period, group=target).values_list(
            "subject_id", flat=True
        )
    )
    return list(
        Enrollment.objects.filter(
            organization=organization,
            student_id=record.student_id,
            offering__period=period,
            offering__group_id=record.group_id,
            status=Enrollment.Status.ENROLLED,
        )
        .exclude(offering__subject_id__in=target_subjects)
        .filter(*hygiene.no_evidence_filters())
    )


def apply_placement(organization, period, item: Placement, *, actor, reason: str) -> dict:
    """Bir tələbəni köçürür (çağıranın tranzaksiyasında). ``{"dropped": n, "moved": n, "created": n}``."""
    from django.apps import apps as django_apps

    from .transfer import transfer_student_group

    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    record = StudentAcademicRecord.objects.select_related("organization", "student", "group").get(pk=item.record_id)
    target = OrgUnit.objects.get(pk=item.target_id)
    orphans = _orphan_empty_enrollments(organization, period, record, target)
    if orphans:
        rows = [
            {
                "id": enrollment.pk,
                "status": enrollment.status,
                "reason": REASON_CODE,
                "evidence": {
                    "enrollment": str(enrollment.pk),
                    "category": CATEGORY,
                    "status": enrollment.status,
                    "reason": REASON_CODE,
                    "target_group": str(target.pk),
                    "counts": {},
                },
            }
            for enrollment in orphans
        ]
        hygiene_actions.record_decisions(
            organization=organization,
            category=CATEGORY,
            rows=rows,
            to_status=Enrollment.Status.DROPPED,
            reason=reason,
            actor=actor,
        )
    result = transfer_student_group(record=record, new_group=target, period=period, by_user=actor, reason=reason)
    return {"dropped": len(orphans), "moved": result["moved"], "created": result["created"]}


def run(organization, period, *, actor, reason: str, names=(), apply: bool = False) -> tuple[Counter, list]:
    """Plan + (apply olduqda) yazı. Dry-run eyni kodu işlədib geri qaytarır — saylar dəqiqdir."""
    items = plan(organization, period, names=names)
    counts = Counter({"students": len(items)})
    offerings_before = CourseOffering.objects.filter(organization=organization, period=period).count()
    with transaction.atomic():
        for item in items:
            counts[item.status] += 1
            if item.status != "place":
                continue
            with transaction.atomic():
                result = apply_placement(organization, period, item, actor=actor, reason=reason)
            counts["enrollments_dropped_empty"] += result["dropped"]
            counts["enrollments_moved"] += result["moved"]
            counts["enrollments_created"] += result["created"]
        counts["offerings_created"] = (
            CourseOffering.objects.filter(organization=organization, period=period).count() - offerings_before
        )
        if not apply:
            transaction.set_rollback(True)
    return counts, items


__all__ = ["MAJORITY", "Placement", "apply_placement", "plan", "run"]
