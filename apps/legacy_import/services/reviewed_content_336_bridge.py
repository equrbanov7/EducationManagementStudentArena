"""Reviewed seventeen identities in one exact roster; never writes identity ledgers."""

import hashlib
import html
import json
import unicodedata
from collections import Counter
from uuid import UUID

from django.apps import apps
from django.db.models import F

from apps.workload.public import queryset_database_fingerprint

from . import reviewed_content_336_spec as fixed
from .reviewed_content_contract import ContentError
from .reviewed_content_spec import ORG


def canonical_part(value):
    value = unicodedata.normalize("NFC", html.unescape(value)).replace("İ", "i").replace("I", "ı")
    return " ".join(unicodedata.normalize("NFC", value.casefold()).replace("i\u0307", "i").split())


def identity_hash(first, last, father):
    parts = [canonical_part(v) for v in (first, last, father)]
    words = parts[2].split()
    if len(words) > 1 and words[-1] in {"qızı", "oğlu"}:
        parts[2] = " ".join(words[:-1])
    return hashlib.sha256(json.dumps(parts, separators=(",", ":")).encode()).hexdigest()


def source_guard(data, source_sha256):
    if fixed.TARGET not in data["selected_target_ids"]:
        return
    raw = {k: v for k, v in data.items() if k not in {"selected_target_ids", "until_date"}}
    actual = hashlib.sha256(json.dumps(raw, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()
    if (
        data["selected_target_ids"] != [fixed.TARGET]
        or source_sha256 != fixed.SOURCE_SHA
        or actual != fixed.PAYLOAD_DIGEST
    ):
        raise ContentError("reviewed_336_exact_source_and_single_target_required")


def _query(label, *, lock=False, **filters):
    query = apps.get_model(label).objects.filter(**filters)
    return query.select_for_update() if lock else query


def _require(condition, code):
    if not condition:
        raise ContentError("reviewed_336_" + code)


def bridge(data, mappings, *, lock=False):
    if fixed.TARGET not in data["selected_target_ids"]:
        return {}
    _require(data["selected_target_ids"] == [fixed.TARGET], "single_target_required")
    # Source names are SHA-attested by the immutable private proof and payload.
    # Runtime matching uses only the fixed seventeen pairs, never name discovery.
    _require(len(fixed.PAIRS) == 17 and len({v[0] for v in fixed.PAIRS.values()}) == 17, "pair_uniqueness_changed")
    _require(len({v[1] for v in fixed.PAIRS.values()}) == 17, "source_identity_hash_collision")
    groups = _query("organizations.OrgUnit", lock=lock, organization_id=ORG, pk=fixed.GROUP)
    group = groups.get()
    settings = group.settings or {}
    _require(
        group.slug == "myedu-grp-937"
        and group.is_active
        and group.unit_type == "group"
        and str(group.parent_id) == fixed.PARENT
        and all(
            settings.get(k) == v
            for k, v in {"degree_level": "bachelor", "education_form": "full_time", "sector": "az"}.items()
        ),
        "group_identity_changed",
    )
    legacy = settings.get("legacy")
    if legacy is not None:
        _require(
            all(
                legacy.get(k) == v
                for k, v in {
                    "id": 937,
                    "table": "groups",
                    "source_system": "myedu_mariadb",
                    "speciality_id": 26,
                    "department_id": 9,
                }.items()
            ),
            "group_legacy_metadata_changed",
        )
    offerings = _query("registrar.CourseOffering", lock=lock, organization_id=ORG, pk=fixed.TARGET)
    offering = offerings.get()
    _require(
        (
            str(offering.group_id),
            str(offering.subject_id),
            str(offering.period_id),
            offering.instructor_id,
            offering.lesson_hours,
            offering.is_active,
        )
        == (fixed.GROUP, fixed.SUBJECT, fixed.PERIOD, fixed.TEACHER, 30, True),
        "offering_changed",
    )
    teacher_maps = _query(
        "legacy_import.LegacyEntityMap",
        lock=lock,
        organization_id=ORG,
        source_system="myedu_mariadb",
        entity_type="worker",
        legacy_pk="23",
        state="migrated",
        target_model_label="auth.user",
    )
    _require(list(teacher_maps.values_list("target_pk", flat=True)) == [str(fixed.TEACHER)], "teacher_ledger_required")
    tasks = _query("workload.TeachingTask", lock=lock, organization_id=ORG, pk=fixed.TASK)
    task = tasks.get()
    _require(
        (task.academic_year, task.status, task.revision, str(task.chair_id))
        == ("2026/2027", "amended", 0, "6cb37f21-4d0f-4858-8c53-1f09d4d0efda"),
        "official_task_changed",
    )
    rows = _query("workload.TeachingTaskRow", lock=lock, organization_id=ORG, pk=fixed.ROW)
    row = rows.get()
    _require(
        (
            str(row.task_id),
            str(row.subject_id),
            str(row.period_id),
            row.lecture_plan,
            row.lecture_total,
            row.seminar_plan,
            row.seminar_total,
            row.lab_plan,
            row.lab_total,
        )
        == (fixed.TASK, fixed.SUBJECT, fixed.PERIOD, 15, 0, 15, 15, 0, 0)
        and set(map(str, row.groups.values_list("pk", flat=True))) == {fixed.GROUP, fixed.OTHER_GROUP},
        "official_row_changed",
    )
    _require(
        (
            row.row_kind,
            row.season,
            row.total_hours,
            row.union_count,
            row.subgroup_count,
            row.student_count,
            row.credits,
            row.degree_level,
            row.education_form,
            str(row.specialty_id),
        )
        == ("teaching", "fall", 15, 0, 1, 0, "3", "bachelor", "eyani", fixed.PARENT),
        "official_row_totals_changed",
    )
    assignments = _query("workload.TeacherAssignment", lock=lock, organization_id=ORG, row_id=fixed.ROW)
    _require(
        list(assignments.values_list("id", "teacher_id", "activity", "hours", "is_hourly_paid"))
        == [(UUID(fixed.ASSIGNMENT), fixed.TEACHER, "seminar", 15, False)],
        "official_assignment_changed",
    )
    enrollments = _query("registrar.Enrollment", lock=lock, organization_id=ORG, offering_id=fixed.TARGET)
    roster = list(enrollments.values("student_id", "status", "superseded_by_id"))
    _require(
        len(roster) == len(fixed.ROSTER)
        and {r["student_id"] for r in roster} == fixed.ROSTER
        and all(r["status"] == "enrolled" and r["superseded_by_id"] is None for r in roster),
        "roster_changed",
    )
    profiles = _query("accounts.UserProfile", lock=lock, user_id__in=fixed.ROSTER)
    users = _query("auth.User", lock=lock, pk__in=fixed.ROSTER)
    user_map = {u.pk: u for u in users}
    profile_map = {p.user_id: p for p in profiles}
    _require(
        set(user_map) == fixed.ROSTER and len(profile_map) == profiles.count() and set(profile_map) == fixed.ROSTER,
        "profile_missing_or_duplicate",
    )
    hashes = {}
    for uid, profile in profile_map.items():
        user = user_map[uid]
        _require(
            str(profile.organization_id) == ORG and profile.access_state == "active" and user.is_active,
            "student_tenant_or_activity_changed",
        )
        hashes[uid] = identity_hash(user.first_name, user.last_name, profile.patronymic)
    counts = Counter(hashes.values())
    _require(all(count == 1 for count in counts.values()), "current_roster_identity_not_unique")
    memberships = _query(
        "organizations.Membership", lock=lock, organization_id=ORG, user_id__in=fixed.ROSTER, is_active=True
    )
    _require(set(memberships.values_list("user_id", flat=True)) == fixed.ROSTER, "student_active_membership_missing")
    records = _query(
        "registrar.StudentAcademicRecord",
        lock=lock,
        organization_id=ORG,
        student_id__in=fixed.ROSTER,
        is_active=True,
        status="enrolled",
    )
    record_groups = {}
    for record in records:
        record_groups.setdefault(record.student_id, []).append(str(record.group_id))
    _require(all(record_groups.get(uid) == [fixed.GROUP] for uid in fixed.ROSTER), "student_current_group_changed")
    students = {s["id"]: s for s in data["students"]}
    for sid, (uid, expected_hash) in fixed.PAIRS.items():
        _require(students.get(sid, {}).get("group_id") == 937, "source_student_group_changed")
        _require(hashes[uid] == expected_hash, "student_identity_hash_changed")
        _require(not mappings.get(str(sid)) or mappings[str(sid)] == {str(uid)}, "student_ledger_conflict")
        mappings[str(sid)] = {str(uid)}
    # A later ledger addition must not expand this reviewed seventeen-person scope.
    for sid in students.keys() - fixed.PAIRS.keys():
        mappings.pop(str(sid), None)
    fingerprints = {
        name: queryset_database_fingerprint(q)
        for name, q in {
            "memberships": memberships,
            "profiles": profiles,
            "users": users,
            "records": records,
            "roster": enrollments,
            "task": tasks,
            "row": rows,
            "assignments": assignments,
            # The shared SQL helper aliases its subquery "state". Rename the
            # ledger's state column so PostgreSQL resolves a composite row.
            "teacher_ledger": teacher_maps.values(
                *[f.attname for f in teacher_maps.model._meta.concrete_fields if f.name != "state"],
                ledger_state=F("state"),
            ),
        }.items()
    }
    return {
        "source_sha256": fixed.SOURCE_SHA,
        "identity_proof_sha256": fixed.PROOF_SHA,
        "current_contract_sha256": fixed.CONTRACT_SHA,
        "excuse_window_proof_sha256": fixed.EXCUSE_PROOF_SHA,
        "fingerprints": fingerprints,
        "source_historical_slots": {"lecture": 3, "seminar": 3},
        "current_assignment": {"seminar_hours": 15, "lecture_hours": 0},
        "source_owner_is_not_lesson_or_mark_author": True,
    }
