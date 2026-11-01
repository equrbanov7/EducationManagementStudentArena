"""Fixed five confirmed home students: append only to four reviewed LEGACY scopes."""

import copy
import hashlib
import json
from types import SimpleNamespace

from django.apps import apps
from django.core.exceptions import ValidationError
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.db.models import Q

from core.audit import log_action
from core.constants import AuditAction

from .integrity import is_authorized_instructor
from .journal_shares import _MEMO_ATTR, ALL_KINDS, active_shares, forget, journal_scope
from .models import (
    CourseOffering,
    Enrollment,
    JournalShare,
    Lesson,
    LessonMark,
    StudentAcademicRecord,
    TeachingHandover,
)
from .reviewed_workload_share import _actor

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
SOURCE_SHA = "765ff7cfa1a8999e98c7b2ea169df4cd204a0d36dd66a9982041982f5764aeff"
BROWSER_SHA = "a022d1d77c1d583a1f9c21c18a8145a2a75955324648702893d04a8b1eb3452f"
PROGRAM_NAME = "Azərbaycan dili və ədəbiyyatı"
OWNER = 7824
KINDS = {7824: ["lecture"], 9526: ["seminar"]}
SUBJECT = "4b9f247f-a2db-4c8a-b42a-125c8418f614"
PERIOD = "a4f88744-8d49-4772-84ef-c28a96c3b372"
ORIGINAL_THROUGHS = {
    "0ad85d3e-a9a3-480e-926a-68a384cb2435": "b16eab6382fcb81fa0134d25713e78230f52fe314e48b2c9b4fdadfb2785120a",
    "e3071d54-4e9a-48fb-8243-5fcd293f590e": "938fddf8769aaa58b8000a9cdba13f6511f46312429f913bfc5cabce2312dbb0",
}
SHARES = {
    "b2a81157-3daf-4c25-88a7-b81b29b9e7a6": "902c07ffd1bb56c41e990171529c61447339e15175b8594beb04ddfd92341278",
    "cf1e6054-61dd-4002-9777-7b0774da2c2a": "e040adec85f4cc29e46fcfb0a92ccbf767f6b17e36e1cf026e8d578a3327527c",
    "0005d781-1014-4760-83f4-1417eda101c5": "d6fe94dbe0f34b9734b9023c615e1299750e41c4bc6598cab5a5ea1705cfa2d9",
    "2a4efcc5-1d7e-48ec-911c-665f545c8d75": "f33e9c4fd28bd7439e5a7c5cc1f1ebe4025805de72eec2f4b999e48c9d9b5a1d",
}

ROSTER = {
    "0339b6b5-0515-4ac6-bc6b-b9ea81ff8bd0": {
        "group_id": "bf9986dc-1366-4a42-8ba0-f9e7636ec78c",
        "offering_id": "0ad85d3e-a9a3-480e-926a-68a384cb2435",
        "record_id": "1f34f648-c539-4628-bab0-64b63d01768b",
        "student_id": 5418,
    },
    "4ba3f40d-8cd6-4e29-886d-493def462565": {
        "group_id": "bf9986dc-1366-4a42-8ba0-f9e7636ec78c",
        "offering_id": "0ad85d3e-a9a3-480e-926a-68a384cb2435",
        "record_id": "55923f0a-bed9-4952-92e2-c3f030148671",
        "student_id": 5426,
    },
    "89604517-6ab1-4236-aeda-d9d55fa45037": {
        "group_id": "bf9986dc-1366-4a42-8ba0-f9e7636ec78c",
        "offering_id": "0ad85d3e-a9a3-480e-926a-68a384cb2435",
        "record_id": "cb41e3e5-38be-47bb-981e-c83c22f408bb",
        "student_id": 5434,
    },
    "91f8c4ac-04c3-4aa7-b5c4-5029d5c49f02": {
        "group_id": "aba7f830-e116-4d2f-b0c6-e165da2bd495",
        "offering_id": "e3071d54-4e9a-48fb-8243-5fcd293f590e",
        "record_id": "9b8877c5-ebdf-4dfb-a811-d9d95549302c",
        "student_id": 5446,
    },
    "eb3c481c-cb6b-4095-bb09-f6cb100d7c4c": {
        "group_id": "bf9986dc-1366-4a42-8ba0-f9e7636ec78c",
        "offering_id": "0ad85d3e-a9a3-480e-926a-68a384cb2435",
        "record_id": "c9ea3a96-8f30-4d03-bf15-6b7a61b3af40",
        "student_id": 5425,
    },
}


def _sha(value):
    return hashlib.sha256(json.dumps(value, cls=DjangoJSONEncoder, sort_keys=True).encode()).hexdigest()


def reviewed_onomastics_spec():
    return copy.deepcopy(
        {
            "organization": ORG,
            "source_sha256": SOURCE_SHA,
            "browser_sha256": BROWSER_SHA,
            "shares": SHARES,
            "roster": ROSTER,
        }
    )


def _home_roster(organization, *, lock):
    found = {}
    for eid, pin in ROSTER.items():
        enrollments = Enrollment.objects.select_related("offering", "student")
        if lock:
            enrollments = enrollments.select_for_update(of=("self",))
        enrollment = enrollments.get(pk=eid)
        records = StudentAcademicRecord.objects.select_related("program", "curriculum").filter(
            organization=organization, student_id=pin["student_id"], is_active=True
        )
        if lock:
            records = records.select_for_update(of=("self",))
        if records.count() != 1:
            raise ValidationError("exact_active_home_record_required")
        record = records.get()
        if (
            str(enrollment.organization_id) != ORG
            or str(enrollment.offering_id) != pin["offering_id"]
            or enrollment.student_id != pin["student_id"]
            or not enrollment.student.is_active
            or enrollment.kind not in ("mandatory", "elective")
            or enrollment.status != "enrolled"
            or enrollment.superseded_by_id is not None
            or (enrollment.source_group_id is not None and str(enrollment.source_group_id) != pin["group_id"])
            or str(record.pk) != pin["record_id"]
            or str(record.group_id) != pin["group_id"]
            or record.status != "enrolled"
            or record.admission_year != 2024
            or record.program.organization_id != organization.pk
            or not record.program.is_active
            or record.program.official_code != "6002006"
            or record.program.name != PROGRAM_NAME
            or record.program.degree_level != "bachelor"
            or record.curriculum.organization_id != organization.pk
            or record.curriculum.program_id != record.program_id
        ):
            raise ValidationError("confirmed_home_roster_changed_or_guest")
        if (
            enrollment.guest_documents.exists()
            or enrollment.subgroup_placement_events.filter(kind="place", undone_by__isnull=True).exists()
        ):
            raise ValidationError("current_guest_or_placement_requires_review")
        found[eid] = enrollment
    return found


def _scope(organization, actor, *, lock):
    _actor(actor, organization, lock=lock)
    if str(organization.pk) != ORG:
        raise ValidationError("fixed_onomastics_tenant_required")
    ids = {p["offering_id"] for p in ROSTER.values()}
    query = CourseOffering.objects.select_related("period", "group").filter(organization=organization, pk__in=ids)
    if lock:
        query = query.select_for_update(of=("self",))
    offerings = list(query)
    if len(offerings) != 2:
        raise ValidationError("fixed_onomastics_offerings_required")
    for offering in offerings:
        pin = next(p for p in ROSTER.values() if p["offering_id"] == str(offering.pk))
        if (
            not offering.is_active
            or offering.is_intensive
            or offering.instructor_id != OWNER
            or offering.lesson_hours != 60
            or str(offering.group_id) != pin["group_id"]
            or str(offering.subject_id) != SUBJECT
            or str(offering.period_id) != PERIOD
            or offering.period.locked_at is not None
            or not offering.period.is_current
            or not offering.period.is_active
            or offering.period.organization_id != organization.pk
            or offering.period.academic_year != "2026/2027"
            or offering.period.period_type != "semester"
            or offering.group.organization_id != organization.pk
            or not offering.group.is_active
            or offering.group.unit_type != "group"
        ):
            raise ValidationError("prior_contact_correction_required")
    if TeachingHandover.objects.filter(offering_id__in=ids, reverted_at__isnull=True).exists():
        raise ValidationError("handover_requires_separate_review")
    query = JournalShare.objects.select_related("teacher").filter(offering_id__in=ids).order_by("pk")
    if lock:
        query = query.select_for_update(of=("self",))
    shares = list(query)
    if {str(s.pk) for s in shares} != set(SHARES):
        raise ValidationError("fixed_legacy_share_set_required")
    for share in shares:
        raw = JournalShare.objects.filter(pk=share.pk).values().get()
        if (
            _sha(raw) != SHARES[str(share.pk)]
            or share.organization_id != organization.pk
            or share.source != "legacy"
            or not share.is_active
            or share.kinds != KINDS.get(share.teacher_id)
            or not is_authorized_instructor(organization=organization, instructor=share.teacher)
        ):
            raise ValidationError("fixed_legacy_share_changed")
    return offerings, shares, _home_roster(organization, lock=lock)


def _original_links(shares, links):
    if any(not any(str(r["journalshare_id"]) == str(s.pk) for r in links) for s in shares):
        raise ValidationError("original_explicit_rosters_required")
    for oid, expected in ORIGINAL_THROUGHS.items():
        selected = {str(s.pk) for s in shares if str(s.offering_id) == oid}
        rows = [r for r in links if str(r["journalshare_id"]) in selected]
        if _sha(rows) != expected:
            raise ValidationError("original_reviewed_roster_links_changed")


@transaction.atomic
def append_reviewed_onomastics_roster(*, organization, actor, source_sha256, expected_links):
    """No caller-selected IDs/kinds/teacher; only five fixed home students, ten links."""
    if source_sha256 != SOURCE_SHA:
        raise ValidationError("reviewed_onomastics_source_required")
    offerings, shares, roster = _scope(organization, actor, lock=True)
    through = JournalShare.enrollments.through
    before = list(through.objects.select_for_update().filter(journalshare_id__in=SHARES).order_by("pk").values())
    if _sha(before) != _sha(sorted(expected_links, key=lambda row: row["id"])) or not before:
        raise ValidationError("reviewed_legacy_links_changed")
    _original_links(shares, before)
    existing = {(str(row["journalshare_id"]), str(row["enrollment_id"])) for row in before}
    desired = {(str(s.pk), eid) for s in shares for eid, e in roster.items() if e.offering_id == s.offering_id}
    if existing & desired or len(desired) != 10:
        raise ValidationError("exact_ten_missing_links_required")
    for share in shares:
        share.enrollments.add(*(eid for sid, eid in sorted(desired) if sid == str(share.pk)))
    created = list(
        through.objects.filter(journalshare_id__in=SHARES)
        .exclude(pk__in=[r["id"] for r in before])
        .order_by("pk")
        .values()
    )
    if len(created) != 10:
        raise ValidationError("ten_reviewed_links_not_created")
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        resource_type="onomastics_roster",
        resource_id="fixed-five",
        reason="reviewed_home_roster_append",
        new_values={
            "source_sha256": SOURCE_SHA,
            "browser_sha256": BROWSER_SHA,
            "links": 10,
            "created_links_sha256": _sha(created),
        },
    )
    for offering in offerings:
        forget(offering)
    return created


@transaction.atomic
def undo_reviewed_onomastics_roster(*, organization, actor, created_links):
    """Remove only exact repair-created through PKs; caller guards full academic graph."""
    offerings, _shares, _roster = _scope(organization, actor, lock=True)
    through = JournalShare.enrollments.through
    actual = list(
        through.objects.select_for_update().filter(pk__in=[r["id"] for r in created_links]).order_by("pk").values()
    )
    if len(actual) != 10 or _sha(actual) != _sha(created_links):
        raise ValidationError("created_roster_links_changed")
    desired = {
        (sid, eid)
        for sid in SHARES
        for eid, pin in ROSTER.items()
        if str(JournalShare.objects.get(pk=sid).offering_id) == pin["offering_id"]
    }
    if {(str(r["journalshare_id"]), str(r["enrollment_id"])) for r in actual} != desired:
        raise ValidationError("created_roster_scope_changed")
    audit = (
        apps.get_model("audit.AuditLog")
        .objects.filter(
            organization=organization,
            resource_type="onomastics_roster",
            resource_id="fixed-five",
            reason="reviewed_home_roster_append",
            new_values__created_links_sha256=_sha(created_links),
        )
        .order_by("-created_at", "-pk")
        .first()
    )
    if (
        audit is None
        or LessonMark.objects.filter(lesson__offering__in=offerings)
        .filter(Q(created_at__gt=audit.created_at) | Q(updated_at__gt=audit.created_at))
        .exists()
    ):
        raise ValidationError("undo_new_grades_or_missing_append_receipt")
    current = list(
        through.objects.filter(journalshare_id__in=SHARES)
        .exclude(pk__in=[r["id"] for r in actual])
        .order_by("pk")
        .values()
    )
    _original_links(_shares, current)
    if any(
        rel.auto_created and not rel.concrete and rel.related_model
        for rel in through._meta.get_fields(include_hidden=True)
    ):
        raise ValidationError("unknown_created_link_descendant")
    through.objects.filter(pk__in=[r["id"] for r in actual]).delete()
    log_action(
        AuditAction.UPDATE,
        user=actor,
        organization=organization,
        resource_type="onomastics_roster",
        resource_id="fixed-five",
        reason="reviewed_home_roster_append_undone",
        new_values={"links": 10},
    )
    for offering in offerings:
        forget(offering)


def validate_reviewed_onomastics_roster(*, organization, actor, lock=False):
    _scope(organization, actor, lock=lock)


def reviewed_onomastics_access_snapshot(*, organization, actor, projected=False):
    """Actual or pure fixed-ten-link projection through the canonical scope policy."""
    offerings, shares, _roster = _scope(organization, actor, lock=False)
    teachers = {s.teacher_id: s.teacher for s in shares}
    for teacher in teachers.values():
        teacher.set_active_organization_context(organization)
    result = {}
    for offering in offerings:
        forget(offering)
        if projected:
            additional = {eid for eid, pin in ROSTER.items() if pin["offering_id"] == str(offering.pk)}
            virtual = [
                SimpleNamespace(
                    teacher_id=s.teacher_id, kinds=s.kinds, enrollment_id_set=s.enrollment_id_set | additional
                )
                for s in active_shares(offering)
            ]
            setattr(offering, _MEMO_ATTR, virtual)
        current = list(Enrollment.objects.filter(offering=offering, status="enrolled").values_list("pk", flat=True))
        histories = list(Lesson.objects.filter(offering=offering, kind="seminar"))
        value = {}
        for teacher_id in KINDS:
            scope = journal_scope(teachers[teacher_id], offering)
            owned = [
                lesson
                for lesson in histories
                if lesson.instructor_id == teacher_id or lesson.created_by_id == teacher_id
            ]
            value[str(teacher_id)] = {
                "kinds": sorted(scope.kinds if scope.kinds is not None else ALL_KINDS),
                "active_roster": sorted(str(eid) for eid in current if scope.allows_enrollment(eid)),
                "can_manage_scores": scope.can_manage_scores,
                "owned_seminar_ids": sorted(str(lesson.pk) for lesson in owned),
                "owned_seminar_readable": all(scope.allows_lesson(lesson) for lesson in owned),
                "all_seminar_readable": all(scope.allows_lesson(lesson) for lesson in histories),
            }
        result[str(offering.pk)] = value
        forget(offering)
    return result
