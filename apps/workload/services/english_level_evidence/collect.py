"""Tenant-local metadata closure and aggregate activity; no marks, names, scores or FIN export."""

from django.apps import apps
from django.db.models import Count, F, Max, Q

from apps.workload.services.scoped_snapshot import SnapshotError

from . import spec
from .identity import fingerprint, resolve
from .teaching import collect as teaching_evidence

COURSE = (
    "id",
    "organization_id",
    "subject_id",
    "period_id",
    "group_id",
    "instructor_id",
    "is_active",
    "lesson_hours",
    "course_format",
    "created_at",
    "updated_at",
)
COHORT = (
    "id",
    "organization_id",
    "department_id",
    "group_id",
    "offering_id",
    "period_id",
    "source_offering_id",
    "lecture_hours",
    "seminar_hours",
    "lab_hours",
    "created_by_id",
    "created_at",
    "updated_at",
)
PLACEMENT = (
    "id",
    "organization_id",
    "cohort_id",
    "student_id",
    "home_group_id",
    "action",
    "source_enrollment_id",
    "target_enrollment_id",
    "actor_id",
    "created_at",
    "updated_at",
)
ENROLLMENT = (
    "id",
    "organization_id",
    "offering_id",
    "student_id",
    "kind",
    "status",
    "source_group_id",
    "superseded_by_id",
    "added_by_id",
    "created_at",
    "updated_at",
)
SAR = (
    "id",
    "organization_id",
    "student_id",
    "program_id",
    "curriculum_id",
    "group_id",
    "admission_year",
    "status",
    "is_active",
    "national_athlete_exemption",
    "created_at",
    "updated_at",
)


def model(label):
    return apps.get_model(label)


def rows(label, fields, cap, **filters):
    data = list(
        model(label).objects.filter(organization_id=spec.ORG, **filters).order_by("pk").values(*fields)[: cap + 1]
    )
    if len(data) > cap:
        raise SnapshotError("english_level_row_budget_exceeded")
    return data


def same_tenant_refs(label, ids):
    ids = {pk for pk in ids if pk is not None}
    found = set(model(label).objects.filter(organization_id=spec.ORG, pk__in=ids).values_list("pk", flat=True))
    if found != ids:
        raise SnapshotError("english_level_foreign_or_missing_reference")


def collect(source):
    # Both active and archived/blocked profiles participate in identity evidence.
    profiles = list(
        model("accounts.UserProfile")
        .objects.filter(organization_id=spec.ORG)
        .order_by("pk")
        .values(
            "user_id",
            "organization_id",
            "institutional_identifier",
            "fin",
            "access_state",
            "is_deleted",
            "blocked_at",
            "deleted_at",
            "user__is_active",
            "updated_at",
        )[: spec.MAX_PROFILES + 1]
    )
    if len(profiles) > spec.MAX_PROFILES:
        raise SnapshotError("english_level_profile_scan_budget_exceeded")
    source_ids = [str(row["id"]) for row in source["records"]]
    ledger_rows = rows(
        "legacy_import.LegacyEntityMap",
        (
            "id",
            "organization_id",
            "legacy_pk",
            "target_pk",
            "source_row_hash",
            "updated_at",
        ),
        spec.MAX_ROWS,
        source_system="myedu_mariadb",
        entity_type="student",
        state="migrated",
        target_model_label="auth.user",
        legacy_pk__in=source_ids,
    )
    ledger = {}
    for row in ledger_rows:
        value = row["target_pk"]
        if not isinstance(value, str) or not value.isascii() or not value.isdigit() or int(value) <= 0:
            raise SnapshotError("english_level_ledger_target_invalid")
        ledger.setdefault(row["legacy_pk"], set()).add(int(value))
    mappings = resolve(source["records"], profiles, ledger)
    courses = rows(
        "registrar.CourseOffering",
        COURSE,
        spec.MAX_COURSES,
        period_id=spec.PERIOD,
        subject_id__in=spec.SUBJECTS,
    )
    course_ids = {r["id"] for r in courses}
    cohorts = rows(
        "registrar.LanguageLevelCohort",
        (*COHORT, "name", "family", "level"),
        spec.MAX_COURSES,
        period_id=spec.PERIOD,
    )
    for row in cohorts:
        if row["offering_id"] not in course_ids or (
            row["source_offering_id"] and row["source_offering_id"] not in course_ids
        ):
            raise SnapshotError("english_level_cohort_outside_fixed_course_scope")
        row["name_sha256"] = fingerprint(row.pop("name"))
        row["family_sha256"] = fingerprint(row.pop("family"))
        if row["level"] not in (
            "beginner",
            "elementary",
            "pre-intermediate",
            "intermediate",
            "upper-intermediate",
            "advanced",
            "a1",
            "a2",
            "b1",
            "b2",
            "c1",
            "c2",
        ):
            raise SnapshotError("english_level_cohort_level_unknown")
    placements = rows(
        "registrar.LanguageLevelPlacement",
        (*PLACEMENT, "reason"),
        spec.MAX_PLACEMENTS,
        cohort_id__in=[r["id"] for r in cohorts],
    )
    for row in placements:
        if row["action"] not in ("add", "remove", "move"):
            raise SnapshotError("english_level_placement_action_unknown")
        reason = row.pop("reason")
        row["reason_present"] = bool(reason)
        row["reason_sha256"] = fingerprint(reason)
    enrollments = rows(
        "registrar.Enrollment",
        ENROLLMENT,
        spec.MAX_ENROLLMENTS,
        offering_id__in=course_ids,
    )
    enrollment_ids = {r["id"] for r in enrollments}
    if any(r["superseded_by_id"] and r["superseded_by_id"] not in enrollment_ids for r in enrollments):
        raise SnapshotError("english_level_supersession_outside_fixed_scope")
    if any(
        r[field] and r[field] not in enrollment_ids
        for r in placements
        for field in ("source_enrollment_id", "target_enrollment_id")
    ):
        raise SnapshotError("english_level_placement_outside_fixed_scope")
    user_ids = {r["student_id"] for r in enrollments} | {r["student_id"] for r in placements}
    user_ids |= {uid for row in mappings for uid in row["same_tenant_candidate_user_ids"]}
    profile_ids = {row["user_id"] for row in profiles}
    if not user_ids <= profile_ids:
        raise SnapshotError("english_level_student_profile_outside_fixed_tenant")
    profile_flags = []
    for row in profiles:
        if row["user_id"] in user_ids:
            if row["access_state"] not in ("active", "staged", "archived"):
                raise SnapshotError("english_level_access_state_unknown")
            profile_flags.append(
                {
                    key: row[key]
                    for key in (
                        "user_id",
                        "organization_id",
                        "access_state",
                        "is_deleted",
                        "blocked_at",
                        "deleted_at",
                        "user__is_active",
                        "updated_at",
                    )
                }
            )
    academic_records = rows("registrar.StudentAcademicRecord", SAR, spec.MAX_ROWS, student_id__in=user_ids)
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
            "created_at",
            "updated_at",
        ),
        spec.MAX_ROWS,
        user_id__in=user_ids,
    )
    if any(r["role__organization_id"] != r["organization_id"] for r in memberships):
        raise SnapshotError("english_level_membership_role_foreign")
    same_tenant_refs(
        "organizations.OrgUnit",
        [r["group_id"] for r in courses]
        + [r["group_id"] for r in academic_records]
        + [r["home_group_id"] for r in placements]
        + [r["source_group_id"] for r in enrollments]
        + [r["department_id"] for r in cohorts]
        + [r["scope_unit_id"] for r in memberships],
    )
    same_tenant_refs("registrar.Program", [r["program_id"] for r in academic_records])
    same_tenant_refs("registrar.Curriculum", [r["curriculum_id"] for r in academic_records])
    mark_query = model("registrar.LessonMark").objects.filter(
        organization_id=spec.ORG, enrollment_id__in=enrollment_ids
    )
    if mark_query.exclude(
        lesson__organization_id=spec.ORG,
        enrollment__organization_id=spec.ORG,
        lesson__offering_id=F("enrollment__offering_id"),
    ).exists():
        raise SnapshotError("english_level_mark_reference_invalid")
    activity = list(
        mark_query.values("enrollment_id")
        .annotate(
            mark_count=Count("pk"),
            numeric_count=Count("pk", filter=Q(score__isnull=False)),
            absent_count=Count("pk", filter=Q(status="absent")),
            excused_count=Count("pk", filter=Q(status="excused")),
            human_actor_count=Count("pk", filter=Q(entered_by_id__isnull=False)),
            latest_created_at=Max("created_at"),
            latest_updated_at=Max("updated_at"),
            latest_human_updated_at=Max("updated_at", filter=Q(entered_by_id__isnull=False)),
        )
        .order_by("enrollment_id")
    )
    staff = teaching_evidence(courses, enrollments, rows, same_tenant_refs)
    group_ids = (
        {r["group_id"] for r in courses}
        | {r["group_id"] for r in academic_records}
        | {r["home_group_id"] for r in placements}
        | {r["source_group_id"] for r in enrollments}
        | {r["department_id"] for r in cohorts}
    )
    group_ids |= {r["group_id"] for r in staff["assignment_group_links"]}
    group_ids |= {r["scope_unit_id"] for r in staff["teacher_memberships"]}
    group_ids.discard(None)
    group_rows = rows(
        "organizations.OrgUnit",
        ("id", "organization_id", "parent_id", "unit_type", "is_active", "settings"),
        spec.MAX_ROWS,
        pk__in=group_ids,
    )
    same_tenant_refs("organizations.OrgUnit", [r["parent_id"] for r in group_rows])
    for row in group_rows:
        raw = row.pop("settings") or {}
        if not isinstance(raw, dict):
            raise SnapshotError("english_level_group_settings_invalid")
        for key in ("sector", "language_sector", "language"):
            value = raw.get(key)
            row[key] = value if value in ("az", "en", "ru") else None
            row[key + "_unrecognized"] = value not in (None, "", "az", "en", "ru")
        row["language_level_cohort"] = raw.get("language_level_cohort") is True
        row["settings_sha256"] = fingerprint(__import__("json").dumps(raw, sort_keys=True, default=str))
    ledger_proofs = []
    for row in ledger_rows:
        uid = int(row["target_pk"])
        ledger_proofs.append(
            {
                "id": row["id"],
                "organization_id": row["organization_id"],
                "source_id": int(row["legacy_pk"]),
                "target_user_id": uid if uid in profile_ids else None,
                "target_reference_sha256": fingerprint(row["target_pk"]),
                "source_row_hash": row["source_row_hash"],
                "updated_at": row["updated_at"],
            }
        )
    return {
        **staff,
        "identity": mappings,
        "profiles": profile_flags,
        "memberships": memberships,
        "academic_records": academic_records,
        "groups": group_rows,
        "offerings": courses,
        "cohorts": cohorts,
        "placements": placements,
        "enrollments": enrollments,
        "mark_activity": activity,
        "identity_ledger_proofs": ledger_proofs,
    }
