"""Relevant teaching flags and exact shares, never a can-write authority decision."""

from collections import defaultdict
from types import SimpleNamespace

from django.apps import apps
from django.contrib.auth import get_user_model

from apps.workload.services.offering_rules import plan_reached_chair
from apps.workload.services.scoped_snapshot import SnapshotError
from core.permissions import has_permission

from . import spec
from .identity import fingerprint


def collect(courses, enrollments, rows, same_tenant_refs):
    enrollment_offerings = {r["id"]: r["offering_id"] for r in enrollments}
    enrollment_ids = set(enrollment_offerings)
    course_ids = {r["id"] for r in courses}
    shares = rows(
        "registrar.JournalShare",
        (
            "id",
            "organization_id",
            "offering_id",
            "teacher_id",
            "kinds",
            "source",
            "batch",
            "is_active",
            "created_by_id",
            "created_at",
            "updated_at",
        ),
        spec.MAX_SHARE_LINKS,
        offering_id__in=course_ids,
    )
    share_ids = {r["id"] for r in shares}
    for row in shares:
        kinds = row["kinds"]
        if kinds is not None and (
            not isinstance(kinds, list) or any(k not in ("lecture", "seminar", "lab") for k in kinds)
        ):
            raise SnapshotError("english_level_share_kind_unknown")
        row["batch_sha256"] = fingerprint(row.pop("batch"))
    through = apps.get_model("registrar", "JournalShare").enrollments.through
    links = list(
        through.objects.filter(journalshare_id__in=share_ids)
        .order_by("pk")
        .values("id", "journalshare_id", "enrollment_id")[: spec.MAX_SHARE_LINKS + 1]
    )
    if len(links) > spec.MAX_SHARE_LINKS:
        raise SnapshotError("english_level_share_link_budget_exceeded")
    if any(r["enrollment_id"] not in enrollment_ids for r in links):
        raise SnapshotError("english_level_share_roster_outside_fixed_scope")
    share_offerings = {r["id"]: r["offering_id"] for r in shares}
    if any(enrollment_offerings[r["enrollment_id"]] != share_offerings[r["journalshare_id"]] for r in links):
        raise SnapshotError("english_level_share_course_reference_mismatch")
    links = [
        {
            "link_id": r["id"],
            "share_id": r["journalshare_id"],
            "enrollment_id": r["enrollment_id"],
        }
        for r in links
    ]
    assignments = rows(
        "workload.TeacherAssignment",
        (
            "id",
            "organization_id",
            "row_id",
            "teacher_id",
            "activity",
            "hours",
            "is_hourly_paid",
            "groups_note",
            "row__task__status",
            "row__task__submitted_at",
            "created_at",
            "updated_at",
        ),
        spec.MAX_ROWS,
        row__organization_id=spec.ORG,
        row__row_kind="teaching",
        row__task__academic_year=spec.YEAR,
        row__task__organization_id=spec.ORG,
        row__period_id=spec.PERIOD,
        row__subject_id__in=spec.SUBJECTS,
        teacher_id__isnull=False,
        hours__gt=0,
        activity__in=("lecture", "seminar", "lab"),
    )
    assignments = [
        r
        for r in assignments
        if plan_reached_chair(SimpleNamespace(status=r["row__task__status"], submitted_at=r["row__task__submitted_at"]))
    ]
    for row in assignments:
        note = row.pop("groups_note")
        row["groups_note_present"] = bool(note)
        row["groups_note_sha256"] = fingerprint(note)
        row.pop("row__task__status")
        row.pop("row__task__submitted_at")
    row_ids = {r["row_id"] for r in assignments}
    row_through = apps.get_model("workload", "TeachingTaskRow").groups.through
    group_links = list(
        row_through.objects.filter(teachingtaskrow_id__in=row_ids)
        .order_by("pk")
        .values("id", "teachingtaskrow_id", "orgunit_id")[: spec.MAX_SHARE_LINKS + 1]
    )
    if len(group_links) > spec.MAX_SHARE_LINKS:
        raise SnapshotError("english_level_assignment_group_budget_exceeded")
    group_links = [
        {
            "link_id": r["id"],
            "row_id": r["teachingtaskrow_id"],
            "group_id": r["orgunit_id"],
        }
        for r in group_links
    ]
    owner_ids = {r["instructor_id"] for r in courses if r["instructor_id"] is not None}
    assignment_ids = {r["teacher_id"] for r in assignments}
    share_teacher_ids = {r["teacher_id"] for r in shares}
    teachers = owner_ids | assignment_ids | share_teacher_ids
    if len(teachers) > spec.MAX_TEACHERS:
        raise SnapshotError("english_level_teacher_budget_exceeded")
    users = {r["id"]: r for r in get_user_model().objects.filter(pk__in=teachers).values("id", "is_active")}
    if set(users) != teachers:
        raise SnapshotError("english_level_teacher_user_missing")
    profile_rows = (
        apps.get_model("accounts", "UserProfile")
        .objects.filter(user_id__in=teachers)
        .values("user_id", "organization_id", "access_state", "is_deleted", "blocked_at", "deleted_at", "updated_at")
    )
    profiles = {r["user_id"]: r for r in profile_rows}
    memberships = rows(
        "organizations.Membership",
        (
            "id",
            "organization_id",
            "user_id",
            "role_id",
            "scope_unit_id",
            "is_active",
            "role__is_active",
            "role__organization_id",
            "role__scope_type",
            "role__permissions",
            "created_at",
            "updated_at",
        ),
        spec.MAX_ROWS,
        user_id__in=teachers,
    )
    active, grade_input = defaultdict(bool), defaultdict(bool)
    for row in memberships:
        if row["role__organization_id"] != row["organization_id"]:
            raise SnapshotError("english_level_teacher_role_foreign")
        row["grade_input_role"] = has_permission(row.pop("role__permissions") or [], "grade.input")
        live = row["is_active"] and row["role__is_active"]
        active[row["user_id"]] |= live
        grade_input[row["user_id"]] |= live and row["grade_input_role"]
    same_tenant_refs(
        "organizations.OrgUnit",
        [r["scope_unit_id"] for r in memberships] + [r["group_id"] for r in group_links],
    )
    flags = []
    for uid in sorted(teachers):
        profile = profiles.get(uid)
        local = bool(profile and str(profile["organization_id"]) == spec.ORG)
        flags.append(
            {
                "user_id": uid,
                "user_is_active": users[uid]["is_active"],
                "profile_present": profile is not None,
                "profile_in_fixed_tenant": local,
                "access_state": profile["access_state"] if local else None,
                "profile_updated_at": profile["updated_at"] if local else None,
                "profile_is_deleted": profile["is_deleted"] if local else None,
                "profile_blocked_at": profile["blocked_at"] if local else None,
                "profile_deleted_at": profile["deleted_at"] if local else None,
                "active_org_membership": active[uid],
                "grade_input_role_active": grade_input[uid],
                "is_current_owner": uid in owner_ids,
                "has_positive_current_assignment": uid in assignment_ids,
                "has_journal_share": uid in share_teacher_ids,
            }
        )
    return {
        "teachers": flags,
        "teacher_memberships": memberships,
        "assignments": assignments,
        "assignment_group_links": group_links,
        "shares": shares,
        "share_links": links,
    }
