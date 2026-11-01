"""Exact course closure, live identity and opaque academic preservation evidence."""

from django.db.models import Q

from apps.registrar.public import absence_limit, attendance_score

from ..group_projection import project_group_settings
from ..people import is_assignable_teacher
from ..repair_fingerprints import academic_database_fingerprint, academic_queries
from ..sbio235_state import RepairError, digest, model, records
from . import retained_rights, spec

KINDS = ("lecture", "seminar", "lab")
RESOURCE = "workload.reviewed_chair_contacts"


def selection(names):
    selected = names.split(",") if names else list(spec.CASES)
    if not selected or len(set(selected)) != len(selected) or set(selected) - set(spec.CASES):
        raise RepairError("fixed_course_selection_invalid")
    return {key: spec.CASES[key] for key in sorted(selected)}


def flat(cases, name):
    if name == "rows":
        return {r["id"]: r for value in cases.values() for r in value["rows"]}
    return {pk: value for case in cases.values() for pk, value in case[name].items()}


def _hours(value):
    if not isinstance(value, dict) or set(value) - set(KINDS):
        raise RepairError("syllabus_plan_kind_changed")
    return {key: int(value.get(key) or 0) for key in KINDS}


def _identities(organization, cases):
    row_pins, offering_pins = flat(cases, "rows"), flat(cases, "offerings")
    rows = list(model("workload.TeachingTaskRow").objects.filter(organization=organization, pk__in=row_pins))
    offerings = list(model("registrar.CourseOffering").objects.filter(organization=organization, pk__in=offering_pins))
    if {str(r.pk) for r in rows} != set(row_pins) or {str(o.pk) for o in offerings} != set(offering_pins):
        raise RepairError("exact_course_rows_or_journals_missing")
    if (
        model("registrar.TeachingHandover")
        .objects.filter(offering_id__in=offering_pins, reverted_at__isnull=True)
        .exists()
    ):
        raise RepairError("manual_handover_requires_separate_review")
    teacher_ids = {
        a[side]["teacher_id"] for r in row_pins.values() for a in r["assignments"] for side in ("old", "new") if a[side]
    }
    reviewed = retained_rights.validate(organization, offering_pins)
    if (
        model("registrar.JournalShare")
        .objects.filter(offering_id__in=offering_pins, teacher_id__in=teacher_ids, is_active=True)
        .exclude(source="workload")
        .exclude(offering_id__in=reviewed)
        .exists()
    ):
        raise RepairError("source_teacher_manual_share_requires_separate_review")
    profiles = {
        p.user_id: p
        for p in model("accounts.UserProfile").objects.filter(organization=organization, user_id__in=teacher_ids)
    }
    teachers = {u.pk: u for u in model("auth.User").objects.filter(pk__in=teacher_ids, is_active=True)}
    if set(teachers) != teacher_ids or set(profiles) != teacher_ids:
        raise RepairError("source_teacher_identity_missing")
    for tid, user in teachers.items():
        if digest([user.first_name, user.last_name, profiles[tid].patronymic]) != spec.TEACHER_IDENTITIES[tid]:
            raise RepairError("source_full_teacher_identity_changed")
    keys = Q(pk__in=[])
    for row in rows:
        pin = row_pins[str(row.pk)]
        if (
            any(str(getattr(row, field)) != pin[field] for field in ("subject_id", "period_id", "task_id"))
            or row.task.academic_year != spec.YEAR
            or str(row.task.chair_id) != spec.TASK_CHAIRS[pin["task_id"]]
            or row.task.organization_id != organization.pk
            or row.task.status not in ("approved", "distributed", "amended")
            or row.row_kind != "teaching"
            or row.season != "fall"
            or {str(pk) for pk in row.groups.values_list("pk", flat=True)} != set(pin["groups"])
        ):
            raise RepairError("source_row_identity_changed")
        for gid in pin["groups"]:
            keys |= Q(subject_id=row.subject_id, period_id=row.period_id, groups__pk=gid)
        for assignment in pin["assignments"]:
            for side in ("old", "new"):
                value = assignment[side]
                if value and not is_assignable_teacher(organization, row.task.chair, teachers[value["teacher_id"]]):
                    raise RepairError("source_teacher_chair_authority_changed")
    siblings = (
        model("workload.TeachingTaskRow")
        .objects.filter(organization=organization)
        .filter(keys)
        .exclude(task__status="cancelled")
    )
    if set(map(str, siblings.values_list("pk", flat=True).distinct())) != set(row_pins):
        raise RepairError("unreviewed_sibling_source_row")
    tenant_group_ids = set(
        model("organizations.OrgUnit")
        .objects.filter(organization=organization, unit_type="group")
        .values_list("pk", flat=True)
    )
    for offering in offerings:
        group = offering.group
        if (
            digest(
                [
                    group.name,
                    group.code,
                    str(group.parent_id),
                    project_group_settings(group.settings, canonical_group_ids=tenant_group_ids),
                    group.unit_type,
                    group.is_active,
                ]
            )
            != spec.GROUP_IDENTITIES[str(group.pk)]
        ):
            raise RepairError("source_group_identity_changed")
        pin = offering_pins[str(offering.pk)]
        if (
            any(str(getattr(offering, name)) != pin[name] for name in ("subject_id", "period_id", "group_id"))
            or not offering.is_active
            or offering.is_intensive
            or offering.period.locked_at
            or not offering.period.is_active
            or not offering.period.is_current
            or offering.period.academic_year != spec.YEAR
        ):
            raise RepairError("source_journal_identity_or_period_changed")
    return rows, offerings, teacher_ids


def _syllabus_closure(cases, offerings):
    ids = [o.pk for o in offerings]
    syllabi = list(
        model("syllabus.Syllabus").objects.filter(organization_id=spec.ORG, offering_id__in=ids, is_active=True)
    )
    if len(syllabi) != len(ids) or {s.offering_id for s in syllabi} != set(ids):
        raise RepairError("one_active_approved_syllabus_per_journal_required")
    targets = {o.pk: o for o in offerings}
    if any(
        (s.subject_id, s.period_id, s.organization_id)
        != (targets[s.offering_id].subject_id, targets[s.offering_id].period_id, targets[s.offering_id].organization_id)
        for s in syllabi
    ):
        raise RepairError("syllabus_course_identity_changed")
    syllabus_ids = [s.pk for s in syllabi]
    versions = list(
        model("syllabus.SyllabusVersion").objects.filter(syllabus_id__in=syllabus_ids).exclude(status="archived")
    )
    if any(s.current_version_id != s.approved_version_id or s.approved_version_id is None for s in syllabi):
        raise RepairError("current_approved_version_identity_changed")
    if any(v.status != "approved" or v.organization_id != offerings[0].organization_id for v in versions):
        raise RepairError("nonapproved_live_syllabus_version_requires_separate_review")
    if any(not any(v.pk == s.approved_version_id and v.syllabus_id == s.pk for v in versions) for s in syllabi):
        raise RepairError("approved_syllabus_foreign_version")
    if (
        model("syllabus.SyllabusShare")
        .objects.filter(syllabus_id__in=syllabus_ids)
        .exclude(offering_id__in=ids)
        .exists()
        or model("syllabus.Syllabus")
        .objects.filter(reused_from_id__in=syllabus_ids)
        .exclude(pk__in=syllabus_ids)
        .exists()
        or model("syllabus.SyllabusVersion")
        .objects.filter(source_version_id__in=[v.pk for v in versions])
        .exclude(syllabus_id__in=syllabus_ids)
        .exists()
    ):
        raise RepairError("syllabus_has_outside_dependants")
    return syllabi


def impact(cases, offerings):
    pins = flat(cases, "offerings")
    result = {}
    for offering in offerings:
        enrollments = list(model("registrar.Enrollment").objects.filter(organization_id=spec.ORG, offering=offering))
        limits = absence_limit.limit_percent_map_for_students(
            organization_id=spec.ORG, student_ids=[e.student_id for e in enrollments]
        )
        exemptions = {}
        for record in (
            model("registrar.StudentAcademicRecord")
            .objects.filter(organization_id=spec.ORG, student_id__in=limits)
            .order_by("pk")
        ):
            exemptions.setdefault(record.student_id, record.national_athlete_exemption)
        changes, barred_changes = 0, 0
        for enrollment in enrollments:
            options = {
                "limit_percent": limits.get(enrollment.student_id, 25),
                "exempt": exemptions.get(enrollment.student_id, False),
            }
            old = attendance_score(pins[str(offering.pk)]["old_hours"], enrollment.absence_hours, **options)
            new = attendance_score(pins[str(offering.pk)]["new_hours"], enrollment.absence_hours, **options)
            changes += old != new
            barred_changes += old[1] != new[1]
        result[str(offering.pk)] = {
            "enrollments": len(enrollments),
            "derived_attendance_changes": changes,
            "derived_barred_changes": barred_changes,
        }
    return result


def snapshot(organization, cases):
    pins = flat(cases, "rows")
    teacher_ids = {
        a[side]["teacher_id"] for r in pins.values() for a in r["assignments"] for side in ("old", "new") if a[side]
    }
    scopes = {
        "workload.TeachingTaskRow": {"pk__in": pins},
        "workload.TeachingTask": {"pk__in": {r["task_id"] for r in pins.values()}},
        "organizations.OrgUnit": {"pk__in": {gid for r in pins.values() for gid in r["groups"]}},
        "organizations.AcademicPeriod": {"pk__in": {r["period_id"] for r in pins.values()}},
        "auth.User": {"pk__in": teacher_ids},
        "accounts.UserProfile": {"organization": organization, "user_id__in": teacher_ids},
        "organizations.Membership": {"organization": organization, "user_id__in": teacher_ids},
    }
    for label, filters in scopes.items():
        list(model(label).objects.filter(**filters).order_by("pk").select_for_update().values_list("pk", flat=True))
    role_ids = (
        model("organizations.Membership")
        .objects.filter(organization=organization, user_id__in=teacher_ids)
        .values("role_id")
    )
    roles = records(model("organizations.Role").objects.filter(pk__in=role_ids), lock=True)
    rows, offerings, teacher_ids = _identities(organization, cases)
    for query in academic_queries(organization_id=spec.ORG, offerings=offerings).values():
        list(query.select_for_update(of=("self",)).values_list("pk", flat=True))
    syllabi = _syllabus_closure(cases, offerings)
    row_ids = [r.pk for r in rows]
    share_rows = model("registrar.JournalShare").enrollments.through.objects.filter(
        journalshare__offering_id__in=[o.pk for o in offerings]
    )
    if share_rows.filter(journalshare__source="workload").exists():
        raise RepairError("limited_workload_share_needs_separate_review")
    queries = academic_queries(organization_id=spec.ORG, offerings=offerings)
    values = {
        "rows": records(model("workload.TeachingTaskRow").objects.filter(pk__in=row_ids), lock=True),
        "assignments": records(model("workload.TeacherAssignment").objects.filter(row_id__in=row_ids), lock=True),
        "tasks": records(model("workload.TeachingTask").objects.filter(pk__in={r.task_id for r in rows}), lock=True),
        "amendments": records(
            model("workload.WorkloadAmendment").objects.filter(task_id__in={r.task_id for r in rows}), lock=True
        ),
        "groups": records(
            model("organizations.OrgUnit").objects.filter(pk__in={o.group_id for o in offerings}), lock=True
        ),
        "memberships": records(
            model("organizations.Membership").objects.filter(organization=organization, user_id__in=teacher_ids),
            lock=True,
        ),
        "teacher_profiles": records(
            model("accounts.UserProfile").objects.filter(organization=organization, user_id__in=teacher_ids), lock=True
        ),
        "roles": roles,
        "offerings": records(queries["offering"]),
        "shares": records(queries["journal_share"]),
        "share_rows": records(share_rows, lock=True),
        "handovers": records(queries["handover"]),
        "syllabi": records(queries["syllabus"]),
        "versions": records(queries["version"]),
        "selected_syllabus_ids": sorted(str(s.pk) for s in syllabi),
        "protected": academic_database_fingerprint(
            organization_id=spec.ORG,
            offerings=offerings,
            exclude=("offering", "journal_share", "handover", "syllabus", "version"),
        ),
        "selection_sha256": digest(cases),
        "impact": impact(cases, offerings),
    }
    return values, values["impact"]


def ensure_old(cases, before):
    assignments = {a["id"]: a for a in before["assignments"]}
    pins = flat(cases, "rows")
    if set(assignments) != {a["id"] for pin in pins.values() for a in pin["assignments"]}:
        raise RepairError("source_assignment_set_changed")
    for row in before["rows"]:
        pin = pins[row["id"]]
        if any(row[key] != value for key, value in pin["old"].items()):
            raise RepairError("source_contact_state_changed")
        for assignment in pin["assignments"]:
            if any(assignments[assignment["id"]][key] != value for key, value in assignment["old"].items()):
                raise RepairError("source_assignment_identity_changed")
    for offering in before["offerings"]:
        pin = flat(cases, "offerings")[offering["id"]]
        if (offering["instructor_id"], offering["lesson_hours"]) != (pin["old_owner"], pin["old_hours"]):
            raise RepairError("journal_owner_or_capacity_changed")
    for case in cases.values():
        expected = {kind: max(row["old"][kind + "_plan"] for row in case["rows"]) for kind in KINDS}
        syllabus_ids = {s["id"] for s in before["syllabi"] if s["offering_id"] in case["offerings"] and s["is_active"]}
        for syllabus in before["syllabi"]:
            if (
                syllabus["id"] in syllabus_ids
                and syllabus["plan_hours_override"]
                and _hours(syllabus["plan_hours_override"]) != expected
            ):
                raise RepairError("explicit_syllabus_override_requires_separate_review")
        for version in before["versions"]:
            if (
                version["syllabus_id"] in syllabus_ids
                and version["status"] != "archived"
                and _hours(version["plan_hours"]) != expected
            ):
                raise RepairError("approved_source_plan_hours_changed")
