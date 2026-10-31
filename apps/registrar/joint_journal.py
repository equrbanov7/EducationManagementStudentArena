"""Virtual joint journal: physical enrollment/lesson/mark IDs never change.

Each operation resolves current official workload evidence and every member's
canonical journal authority again. A timetable alone grants no access. Different
contact kinds are separate selections; partial/level rosters never combine.
"""

from collections import defaultdict
from dataclasses import dataclass

from django.core.exceptions import PermissionDenied
from django.db import transaction

from . import gradebook, journal_access, journal_shares, schedule
from .journal_assignment_sources import joint_journal_candidates
from .models import CourseOffering, Enrollment, Lesson, LessonMark, ScheduleSlot


class JointJournalError(gradebook.LessonRuleError):
    """The joint selection changed, or an atomic member write was refused."""


@dataclass(frozen=True)
class JointJournal:
    source_row_id: object
    kind: str
    offerings: tuple

    @property
    def offering_ids(self):
        return frozenset(offering.pk for offering in self.offerings)

    @property
    def group_label(self):
        return " + ".join(offering.group.name for offering in self.offerings)


def _signature(slot):
    return (slot.weekday, slot.start_time, slot.end_time, slot.week_type)


def selections(*, organization, user):
    """Conservative current joint sets: exact row groups and identical full kind schedules.

    A shared lecture with separately scheduled seminars produces a lecture set
    only. A single coinciding slot among otherwise separate schedules is unsafe.
    Missing/parked schedules or ambiguous duplicate offerings supply no set.
    """
    result = []
    occupied = set()
    candidates = joint_journal_candidates(organization=organization, teacher_id=user.pk)
    for candidate in candidates:
        kind = candidate["kind"]
        offerings = tuple(
            CourseOffering.objects.filter(
                organization=organization,
                is_active=True,
                subject_id=candidate["subject_id"],
                period_id=candidate["period_id"],
                group_id__in=candidate["group_ids"],
            )
            .exclude(course_format="intensive")
            .select_related("organization", "period", "group", "subject", "instructor")
            .order_by("group__name", "pk")
        )
        if len(offerings) != len(candidate["group_ids"]):
            continue
        if {offering.group_id for offering in offerings} != set(candidate["group_ids"]):
            continue
        if any(not _eligible(user, offering, kind) for offering in offerings):
            continue
        signatures = defaultdict(set)
        rooms = defaultdict(set)
        slots = ScheduleSlot.objects.filter(
            organization=organization, offering_id__in=[o.pk for o in offerings], kind=kind, is_parked=False
        ).select_related("offering")
        foreign_teacher = False
        duplicate_slot = False
        for slot in slots:
            foreign_teacher |= schedule.effective_instructor_id(slot) != user.pk
            duplicate_slot |= _signature(slot) in signatures[slot.offering_id]
            signatures[slot.offering_id].add(_signature(slot))
            room = (slot.room or "").strip().casefold()
            if room:
                rooms[_signature(slot)].add(room)
        first = signatures[offerings[0].pk]
        if (
            foreign_teacher
            or duplicate_slot
            or not first
            or any(signatures[o.pk] != first for o in offerings)
            or any(len(values) > 1 for values in rooms.values())
        ):
            continue
        key = frozenset((offering.pk, kind) for offering in offerings)
        if key & occupied:
            continue  # repeated official row evidence must not multiply a journal
        occupied.update(key)
        result.append(JointJournal(candidate["source_row_id"], kind, offerings))
    return result


def _eligible(user, offering, kind):
    if not journal_access.is_direct_editor(user, offering):
        return False
    # Even an owner's computed scope can expand unclaimed rows. Explicit level
    # partitions are not whole-group joint evidence, regardless of that union.
    if any(share.enrollment_id_set for share in journal_shares.active_shares(offering)):
        return False
    scope = journal_shares.journal_scope(user, offering)
    return scope.enrollment_ids is None and scope.allows_kind(kind)


def resolve(*, organization, user, source_row_id, kind):
    found = [
        item
        for item in selections(organization=organization, user=user)
        if str(item.source_row_id) == str(source_row_id) and item.kind == kind
    ]
    if len(found) != 1:
        raise PermissionDenied("Birgə jurnalın cari yük, cədvəl və giriş sübutu tapılmadı.")
    return found[0]


def roster(*, organization, user, source_row_id, kind):
    """Full physical roster; callers keep each enrollment's own offering_id."""
    joint = resolve(organization=organization, user=user, source_row_id=source_row_id, kind=kind)
    return list(
        Enrollment.objects.filter(
            organization=organization, offering_id__in=joint.offering_ids, status=Enrollment.Status.ENROLLED
        )
        .select_related("student", "offering__group")
        .order_by("offering__group__name", "student__last_name", "student__first_name", "pk")
    )


def _locked_joint(organization, user, source_row_id, kind):
    joint = resolve(organization=organization, user=user, source_row_id=source_row_id, kind=kind)
    # Stable ordering matches every joint operation; canonical APIs lock these
    # same rows again. No member may commit before the others pass.
    list(
        CourseOffering.objects.select_for_update()
        .filter(organization=organization, pk__in=joint.offering_ids)
        .order_by("pk")
    )
    refreshed = resolve(organization=organization, user=user, source_row_id=source_row_id, kind=kind)
    if refreshed.offering_ids != joint.offering_ids:
        raise JointJournalError("Birgə jurnalın qrupları dəyişib; səhifəni yeniləyin.")
    joint = refreshed
    if any(gradebook.journal_is_locked(offering) for offering in joint.offerings):
        raise JointJournalError("Birgə jurnalın açılışlarından biri kilidlidir; heç nə yazılmadı.")
    return joint


@transaction.atomic
def create_lessons(*, organization, user, source_row_id, kind, date, topic="", slot_signature):
    """One teacher action creates one real lesson per group using canonical rules.

    slot_signature is a server-returned _signature tuple, verified anew here;
    dates, hours, syllabus gates, duplicates and activation obey create_lesson.
    No override/full-edit flags are accepted through this ordinary teacher API.
    """
    joint = _locked_joint(organization, user, source_row_id, kind)
    created = []
    for offering in joint.offerings:
        slots = [
            slot
            for slot in ScheduleSlot.objects.filter(
                organization=organization, offering=offering, kind=kind, is_parked=False
            )
            if _signature(slot) == slot_signature
        ]
        if len(slots) != 1:
            raise JointJournalError("Birgə dərsin cədvəl slotu dəyişib; heç nə yazılmadı.")
        created.append(
            gradebook.create_lesson(
                offering=offering, created_by=user, instructor=user, date=date, topic=topic, slot=slots[0]
            )
        )
    return created


@transaction.atomic
def save_marks(*, organization, user, source_row_id, kind, entries, request=None):
    """Fan out real cell IDs atomically, preserving all canonical mark policies.

    Unknown/cross-paired IDs and wrong kinds fail closed. Any refused changed
    cell rolls back every member, including absence counters and audit rows.
    Unchanged cells remain successful no-ops, as in the ordinary journal.
    """
    joint = _locked_joint(organization, user, source_row_id, kind)
    entries = list(entries)
    lessons = {
        str(lesson.pk): lesson.offering_id
        for lesson in Lesson.objects.filter(organization=organization, offering_id__in=joint.offering_ids, kind=kind)
    }
    enrollments = {
        str(enrollment.pk): enrollment.offering_id
        for enrollment in Enrollment.objects.filter(
            organization=organization, offering_id__in=joint.offering_ids, status=Enrollment.Status.ENROLLED
        )
    }
    batches = defaultdict(list)
    seen = set()
    for entry in entries:
        lesson_id, enrollment_id = str(entry.get("lesson_id")), str(entry.get("enrollment_id"))
        offering_id = lessons.get(lesson_id)
        pair = (lesson_id, enrollment_id)
        if (
            offering_id is None
            or enrollments.get(enrollment_id) != offering_id
            or pair in seen
            or entry.get("status") not in ("present", "absent")
        ):
            raise JointJournalError("Xana birgə jurnalın dərs və tələbə əhatəsinə aid deyil.")
        seen.add(pair)
        batches[offering_id].append(entry)
    protected = (
        LessonMark.objects.filter(
            organization=organization,
            lesson_id__in=[pair[0] for pair in seen],
            enrollment_id__in=[pair[1] for pair in seen],
        )
        .exclude(status__in=("present", "absent"))
        .values_list("lesson_id", "enrollment_id")
    )
    if any((str(lesson_id), str(enrollment_id)) in seen for lesson_id, enrollment_id in protected):
        raise JointJournalError("Üzrlü və digər qorunan davamiyyət qeydləri burada dəyişdirilə bilməz.")
    written = 0
    for offering in joint.offerings:
        if not batches[offering.pk]:
            continue
        report = gradebook.save_marks(
            offering=offering, entries=batches[offering.pk], by_user=user, request=request, report=True
        )
        if any(report.get(key) for key in ("rejected", "blocked", "locked", "reason_required")):
            raise JointJournalError("Birgə jurnalın xanası yazılmadı; bütün dəyişikliklər geri alındı.")
        written += report["written"]
    return {"written": written, "rejected": 0}
