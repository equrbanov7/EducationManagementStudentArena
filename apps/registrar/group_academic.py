"""«Starosta» bölməsi — qrupun AKADEMİK MƏNZƏRƏSİ (OXU-YALNIZ), 2026-10-13 (gecə).

Sahib: «starosta kabinetdə əsas üstünlüyü o olmalıdır ki, seçmə fənn ya da başqa qrupun nə işi olarsa
görünsün». Adi tələbə yalnız ÖZ fənlərini/cədvəlini görür; starosta isə qrupun bütöv mənzərəsini:

* qrupun cari dövr fənləri — məcburi + SEÇMƏ (blok adı ilə) və hansı qrup yoldaşının hansı seçmə fənni
  götürdüyü (yalnız AD — sahibin 2026-10-13 məxfilik qərarı: yoldaşların balı/qayıbı GÖSTƏRİLMİR);
* BİRLƏŞMİŞ dərslər: qrupun tələbələri başqa qrupun jurnalında oxuyursa (alt qrup birləşməsi, seçmə) və ya
  qrupun jurnalına başqa qrupdan tələbə əlavə olunubsa («alt qrupdan əlavə», ``Enrollment.source_group``);
* ALT QRUPLAR: ana qrup → alt qruplar (``settings.parent_group`` izi / ad şablonu,
  :mod:`apps.registrar.subgroup_rollup`) və ya alt qrup → ana qrup;
* cədvəl və imtahanlar — :mod:`apps.registrar.group_timetable`.

MƏXFİLİK: təkrar (``retake``) qeydiyyatlar qrup mənzərəsinə DÜŞMÜR — kimin fənni təkrar götürdüyü
(yəni əvvəl keçmədiyi) şəxsi akademik məlumatdır. Bal, qayıb, imtahan buraxılışı burada yoxdur.

Qrupu çağıran VERİR (qapı accounts-dadır: ``rbac_my_group.my_group_unit``). Heç nə YAZMIR.
Sorğu sayı tələbə/fənn sayından asılı deyil (~7 sorğu).
"""

from __future__ import annotations

from django.db.models import F

from apps.registrar import subgroup_rollup
from apps.registrar.models import (
    AcademicStatus,
    CourseOffering,
    Enrollment,
    EnrollmentKind,
    GroupElectiveChoice,
    StudentAcademicRecord,
)

#: Qrup mənzərəsinə düşən qeydiyyat statusları (dondurulmuş / tarixçə sətirləri xaric).
LIVE_STATUSES = (Enrollment.Status.ENROLLED, Enrollment.Status.COMPLETED)

KIND_MANDATORY = "mandatory"
KIND_ELECTIVE = "elective"


def _name(first, last, username) -> str:
    full = f"{first or ''} {last or ''}".strip()
    return full or (username or "")


def group_students(group) -> list:
    """Qrupun aktiv + qeydiyyatlı tələbələri: ``[{"id", "name"}]`` (ad sırası, təkrarsız)."""
    rows = (
        StudentAcademicRecord.objects.filter(
            organization_id=group.organization_id, group=group, is_active=True, status=AcademicStatus.ENROLLED
        )
        .order_by("student__last_name", "student__first_name", "student__username", "pk")
        .values_list("student_id", "student__first_name", "student__last_name", "student__username")
    )
    seen: set = set()
    out = []
    for student_id, first, last, username in rows:
        if student_id in seen:
            continue
        seen.add(student_id)
        out.append({"id": student_id, "name": _name(first, last, username)})
    return out


def _instructor(first, last, username) -> str:
    return _name(first, last, username) if username else ""


def group_subjects(group, *, period, students, viewer_id=None) -> dict:
    """Fənlər + seçmələr + birləşmiş dərslər.

    Qaytarır::

        {"subjects": [...], "electives": [...], "joint": [...], "offering_ids": set, "takers": {oid: set}}

    hər fənn: ``{"offering_id", "name", "code", "kind", "elective_block", "instructor", "journal_group",
    "is_own_journal", "other_groups", "takers", "group_size", "partial", "taker_names", "viewer_takes"}``.
    """
    result = {"subjects": [], "electives": [], "joint": [], "offering_ids": set(), "takers": {}}
    if group is None or period is None:
        return result
    organization_id = group.organization_id
    student_ids = {row["id"] for row in students}
    names = {row["id"]: row["name"] for row in students}

    offerings: dict = {}

    def _offering(oid, row):
        return offerings.setdefault(
            oid,
            {
                "offering_id": oid,
                "subject_id": row["subject_id"],
                "name": row["subject_name"] or "—",
                "code": row["subject_code"] or "",
                "instructor": _instructor(row["i_first"], row["i_last"], row["i_username"]),
                "journal_group_id": row["group_id"],
                "journal_group": row["group_name"] or "",
                "kinds": set(),
                "takers": set(),
                "guest_groups": set(),
            },
        )

    # 1) Qrupun ÖZ açılışları (hələ qeydiyyatı olmayanlar da görünsün).
    own = CourseOffering.objects.filter(
        organization_id=organization_id, group=group, period=period, is_active=True
    ).values(
        "pk",
        "group_id",
        "subject_id",
        subject_name=F("subject__name"),
        subject_code=F("subject__code"),
        group_name=F("group__name"),
        i_first=F("instructor__first_name"),
        i_last=F("instructor__last_name"),
        i_username=F("instructor__username"),
    )
    for row in own:
        _offering(row["pk"], row)

    # 2) Qrup tələbələrinin bu dövrdəki canlı qeydiyyatları (başqa qrupun jurnalı daxil). Təkrar YOX.
    if student_ids:
        enrollments = (
            Enrollment.objects.filter(
                organization_id=organization_id,
                student_id__in=student_ids,
                offering__period=period,
                offering__is_active=True,
                status__in=LIVE_STATUSES,
            )
            .exclude(kind=EnrollmentKind.RETAKE)
            .values(
                "student_id",
                "kind",
                "offering_id",
                group_id=F("offering__group_id"),
                subject_name=F("offering__subject__name"),
                subject_code=F("offering__subject__code"),
                subject_id=F("offering__subject_id"),
                group_name=F("offering__group__name"),
                i_first=F("offering__instructor__first_name"),
                i_last=F("offering__instructor__last_name"),
                i_username=F("offering__instructor__username"),
            )
        )
        for row in enrollments:
            item = _offering(row["offering_id"], row)
            item["kinds"].add(row["kind"])
            item["takers"].add(row["student_id"])

    if not offerings:
        return result

    # 3) Bu jurnallara BAŞQA qrupdan «alt qrupdan əlavə» olunanlar (mənbə qrupun ADI — tələbə adı yox).
    guest_rows = (
        Enrollment.objects.filter(
            organization_id=organization_id,
            offering_id__in=list(offerings),
            status__in=LIVE_STATUSES,
            source_group__isnull=False,
        )
        .exclude(source_group=group)
        .values_list("offering_id", "source_group__name")
        .distinct()
    )
    for offering_id, source_name in guest_rows:
        if source_name:
            offerings[offering_id]["guest_groups"].add(source_name)

    # 4) Qrupun seçmə blok qərarları (``GroupElectiveChoice``) — blok adı.
    blocks = dict(
        GroupElectiveChoice.objects.filter(organization_id=organization_id, group=group, period=period).values_list(
            "chosen_subject_id", "elective_group"
        )
    )

    group_size = len(student_ids)
    subjects = []
    for item in offerings.values():
        is_elective = EnrollmentKind.ELECTIVE in item["kinds"] or item["subject_id"] in blocks
        is_own = item["journal_group_id"] == group.pk
        other_groups = set(item["guest_groups"])
        if not is_own and item["journal_group"]:
            other_groups.add(item["journal_group"])
        other_groups.discard(group.name)
        takers = item["takers"]
        partial = bool(group_size) and 0 < len(takers) < group_size
        subjects.append(
            {
                "offering_id": item["offering_id"],
                "name": item["name"],
                "code": item["code"],
                "kind": KIND_ELECTIVE if is_elective else KIND_MANDATORY,
                "elective_block": blocks.get(item["subject_id"], ""),
                "instructor": item["instructor"],
                "journal_group": item["journal_group"],
                "is_own_journal": is_own,
                "other_groups": sorted(other_groups, key=str.lower),
                "takers": len(takers),
                "group_size": group_size,
                "partial": partial,
                # Yalnız qrupun bir HİSSƏSİ götürəndə adlar (seçmə / alt qrup) — hamı götürürsə siyahı lazımsızdır.
                "taker_names": sorted((names[sid] for sid in takers if sid in names), key=str.lower) if partial else [],
                "viewer_takes": viewer_id in takers if viewer_id is not None else False,
            }
        )
    subjects.sort(key=lambda s: (s["kind"] != KIND_MANDATORY, (s["name"] or "").lower()))
    result["subjects"] = subjects
    result["electives"] = [s for s in subjects if s["kind"] == KIND_ELECTIVE]
    result["joint"] = [s for s in subjects if s["other_groups"] or not s["is_own_journal"]]
    result["offering_ids"] = {s["offering_id"] for s in subjects}
    result["takers"] = {item["offering_id"]: set(item["takers"]) for item in offerings.values()}
    return result


def group_subgroups(group) -> dict:
    """Ana qrup ↔ alt qruplar: ``{"parent": {"name"} | None, "children": [{"name", "count", "students"}]}``."""
    result = {"parent": None, "children": []}
    if group is None:
        return result
    organization = group.organization
    parents = subgroup_rollup.parent_group_candidates(organization, group)
    if parents:
        parent = min(parents, key=lambda unit: (unit.name or "").lower())
        result["parent"] = {"name": parent.name}
    children = subgroup_rollup.subgroup_map(organization, [group]).get(group.pk, [])
    if not children:
        return result
    child_ids = [unit.pk for unit in children]
    rows = (
        StudentAcademicRecord.objects.filter(
            organization_id=group.organization_id,
            group_id__in=child_ids,
            is_active=True,
            status=AcademicStatus.ENROLLED,
        )
        .order_by("student__last_name", "student__first_name", "student__username")
        .values_list("group_id", "student_id", "student__first_name", "student__last_name", "student__username")
    )
    by_group: dict = {pk: [] for pk in child_ids}
    seen: set = set()
    for group_id, student_id, first, last, username in rows:
        if (group_id, student_id) in seen:
            continue
        seen.add((group_id, student_id))
        by_group[group_id].append(_name(first, last, username))
    result["children"] = [
        {"name": unit.name, "count": len(by_group[unit.pk]), "students": by_group[unit.pk]} for unit in children
    ]
    return result


def exam_unit_ids(group) -> list:
    """Imtahan təyinatı üçün qrupla əlaqəli vahidlər (özü + ana qrup(lar))."""
    if group is None:
        return []
    ids = [group.pk]
    ids.extend(unit.pk for unit in subgroup_rollup.parent_group_candidates(group.organization, group))
    return ids


__all__ = [
    "KIND_ELECTIVE",
    "KIND_MANDATORY",
    "group_students",
    "group_subgroups",
    "group_subjects",
    "exam_unit_ids",
]
