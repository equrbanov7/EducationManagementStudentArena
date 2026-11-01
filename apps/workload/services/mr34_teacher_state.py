"""Locked exact identity and opaque preservation graph for the MR34 correction."""

from core.permissions import has_permission

from . import mr34_teacher_spec as spec
from .repair_fingerprints import academic_database_fingerprint, queryset_database_fingerprint
from .sbio235_state import RepairError, digest, model, records

RESOURCE = "workload.mr34_teacher_identity"


def active_teacher(organization, user):
    if not user.is_active:
        return False
    memberships = (
        model("organizations.Membership")
        .objects.filter(
            organization=organization,
            user=user,
            is_active=True,
            role__organization=organization,
            role__is_active=True,
        )
        .select_related("role")
    )
    return any(has_permission(row.role.permissions or [], "grade.input") for row in memberships)


def snapshot(organization):
    if str(organization.pk) != spec.ORG or not organization.is_active or organization.status != "active":
        raise RepairError("mr34_active_fixed_tenant_required")
    tasks = list(
        model("workload.TeachingTask")
        .objects.select_for_update()
        .filter(
            organization=organization,
            pk__in={v["task_id"] for v in spec.ROWS.values()},
        )
    )
    if len(tasks) != len({v["task_id"] for v in spec.ROWS.values()}) or any(
        str(t.chair_id) != spec.CHAIR or t.academic_year != spec.YEAR or t.status not in {"amended", "distributed"}
        for t in tasks
    ):
        raise RepairError("mr34_released_exact_task_required")
    rows = list(
        model("workload.TeachingTaskRow")
        .objects.select_for_update()
        .filter(
            organization=organization,
            pk__in=spec.ROWS,
        )
    )
    if {str(r.pk) for r in rows} != set(spec.ROWS):
        raise RepairError("mr34_exact_rows_required")
    group_links = []
    for row in rows:
        pin = spec.ROWS[str(row.pk)]
        actual = sorted(str(pk) for pk in row.groups.filter(organization=organization).values_list("pk", flat=True))
        if actual != pin["groups"] or any(
            str(getattr(row, key)) != str(value) for key, value in pin.items() if key != "groups"
        ):
            raise RepairError("mr34_row_identity_or_hours_changed")
        group_links.append({"row_id": str(row.pk), "groups": actual})
    offerings = list(
        model("registrar.CourseOffering")
        .objects.select_for_update()
        .filter(
            organization=organization,
            pk__in=spec.OFFERINGS,
        )
    )
    if {str(o.pk) for o in offerings} != set(spec.OFFERINGS):
        raise RepairError("mr34_five_approved_journals_required")
    for offering in offerings:
        if offering.instructor_id != spec.CANONICAL or any(
            str(getattr(offering, key)) != str(value) for key, value in spec.OFFERINGS[str(offering.pk)].items()
        ):
            raise RepairError("mr34_canonical_existing_owner_changed")
    profiles = {
        p.user_id: p
        for p in model("accounts.UserProfile")
        .objects.select_for_update()
        .filter(
            organization=organization,
            user_id__in=(spec.OLD, spec.CANONICAL),
        )
    }
    users = {u.pk: u for u in model("auth.User").objects.select_for_update().filter(pk__in=profiles, is_active=True)}
    if set(users) != {spec.OLD, spec.CANONICAL}:
        raise RepairError("mr34_reviewed_principal_missing")
    for uid, user in users.items():
        if digest([user.first_name, user.last_name, profiles[uid].patronymic]) != spec.IDENTITY_HASHES[uid]:
            raise RepairError("mr34_reviewed_identity_changed")
        if profiles[uid].access_state != "active" or not active_teacher(organization, user):
            raise RepairError("mr34_active_grade_input_required")
    assignments = records(
        model("workload.TeacherAssignment").objects.filter(
            organization=organization,
            row_id__in=spec.ROWS,
        ),
        lock=True,
    )
    if {a["id"] for a in assignments} != set(spec.ASSIGNMENTS):
        raise RepairError("mr34_assignment_set_changed_or_duplicate")
    for assignment in assignments:
        if any(str(assignment[k]) != str(v) for k, v in spec.ASSIGNMENTS[assignment["id"]].items()):
            raise RepairError("mr34_assignment_identity_or_hours_changed")
    teachers = {a["teacher_id"] for a in assignments}
    if teachers not in ({spec.OLD}, {spec.CANONICAL}):
        raise RepairError("mr34_mixed_or_unreviewed_teacher_state")
    # A later manual handover of this very same reviewed duplicate pair can be
    # retained; unrelated manual owners must not acquire this source authority.
    handovers = records(
        model("registrar.TeachingHandover").objects.filter(
            organization=organization,
            offering_id__in=spec.OFFERINGS,
        ),
        lock=True,
    )
    if any(
        h["reverted_at"] is None and (h["from_instructor_id"], h["to_instructor_id"]) != (spec.OLD, spec.CANONICAL)
        for h in handovers
    ):
        raise RepairError("mr34_unreviewed_handover_graph")
    shares = model("registrar.JournalShare").objects.filter(organization=organization, offering_id__in=spec.OFFERINGS)
    if shares.filter(teacher_id=spec.OLD, is_active=True).exists():
        raise RepairError("mr34_duplicate_still_has_active_share")
    protected = academic_database_fingerprint(organization_id=organization.pk, offerings=offerings)
    student_ids = (
        model("registrar.Enrollment")
        .objects.filter(
            organization=organization,
            offering_id__in=spec.OFFERINGS,
        )
        .values("student_id")
    )
    for key, qs in {
        "memberships": model("organizations.Membership").objects.filter(organization=organization),
        "roles": model("organizations.Role").objects.filter(organization=organization),
        "profiles": model("accounts.UserProfile").objects.filter(organization=organization),
        "SAR": model("registrar.StudentAcademicRecord").objects.filter(
            organization=organization, student_id__in=student_ids
        ),
        "groups": model("organizations.OrgUnit").objects.filter(organization=organization),
        "outside_assignments": model("workload.TeacherAssignment")
        .objects.filter(organization=organization)
        .exclude(pk__in=spec.ASSIGNMENTS),
        "outside_rows": model("workload.TeachingTaskRow")
        .objects.filter(organization=organization)
        .exclude(pk__in=spec.ROWS),
    }.items():
        protected[key] = queryset_database_fingerprint(qs)
    through = model("registrar.JournalShare").enrollments.through
    protected["share_rows"] = records(through.objects.filter(journalshare_id__in=shares.values("pk")), lock=True)
    return {
        "approval_sha": spec.APPROVAL_SHA,
        "selection_sha": digest([spec.ASSIGNMENTS, spec.ROWS, spec.OFFERINGS, spec.IDENTITY_HASHES]),
        "assignments": assignments,
        "rows": records(model("workload.TeachingTaskRow").objects.filter(pk__in=spec.ROWS)),
        "tasks": records(model("workload.TeachingTask").objects.filter(pk__in=[t.pk for t in tasks])),
        "groups": sorted(group_links, key=lambda r: r["row_id"]),
        "handovers": handovers,
        "protected": protected,
        "amendments": records(model("workload.WorkloadAmendment").objects.filter(task_id__in=[t.pk for t in tasks])),
        "phase": "before" if teachers == {spec.OLD} else "after",
    }
