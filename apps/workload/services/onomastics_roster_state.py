"""Fixed home-roster supplement: source geometry and complete preserved reverse graph."""

from decimal import Decimal, InvalidOperation

from django.db.models import Q

from apps.registrar.public import (
    reviewed_onomastics_access_snapshot,
    reviewed_onomastics_spec,
    validate_reviewed_onomastics_roster,
)

from .group_projection import project_group_settings
from .offering_rules import plan_reached_chair
from .offering_shares import _assignment_group
from .reviewed_chair_contacts import retained_rights, spec
from .reviewed_kind_share_state import _graph
from .sbio235_state import RepairError, digest, model, records
from .scoped_snapshot.repair_contact_rights import sha

CASE = spec.CASES["az_onomastics"]
ROOT_OFFERINGS = tuple(retained_rights.PINS)
RESOURCE = "ReviewedOnomasticsHomeRoster"
TEACHERS = (7824, 9526)


def _plan(value):
    kinds = ("lecture", "seminar", "lab")
    if not isinstance(value, dict) or set(value) - set(kinds):
        raise RepairError("invalid_official_syllabus_plan")
    try:
        result = {kind: Decimal(str(value.get(kind) or 0)) for kind in kinds}
        if any(not number.is_finite() for number in result.values()):
            raise ValueError
        return result
    except (InvalidOperation, TypeError, ValueError):
        raise RepairError("invalid_official_syllabus_plan") from None


def _source(organization, lock):
    pins = {r["id"]: r for r in CASE["rows"]}
    rows = model("workload.TeachingTaskRow").objects.filter(pk__in=pins).select_related("task")
    if lock:
        rows = rows.select_for_update(of=("self",))
    rows = list(rows)
    if len(rows) != len(pins):
        raise RepairError("exact_source_rows_required")
    allowed = Q(pk__in=[])
    for row in rows:
        pin = pins[str(row.pk)]
        if (
            str(row.organization_id) != spec.ORG
            or str(row.subject_id) != pin["subject_id"]
            or str(row.period_id) != pin["period_id"]
            or str(row.task_id) != pin["task_id"]
            or str(row.task.chair_id) != spec.TASK_CHAIRS[pin["task_id"]]
            or row.task.organization_id != organization.pk
            or row.task.academic_year != spec.YEAR
            or not plan_reached_chair(row.task)
            or row.row_kind != "teaching"
            or row.season != "fall"
            or any(getattr(row, field) != value for field, value in pin["new"].items())
            or set(map(str, row.groups.values_list("pk", flat=True))) != set(pin["groups"])
        ):
            raise RepairError("prior_official_contacts_correction_required")
        assignments = list(row.assignments.order_by("pk").values())
        expected = {a["id"]: a["new"] for a in pin["assignments"] if a["new"]}
        if {str(a["id"]) for a in assignments} != set(expected) or any(
            any(a[k] != v for k, v in expected[str(a["id"])].items()) for a in assignments
        ):
            raise RepairError("exact_kind_teacher_hours_required")
        groups = list(row.groups.all())
        if any(
            _assignment_group(assignment, row, group, known_groups=groups) is not True
            for assignment in row.assignments.all()
            for group in groups
        ):
            raise RepairError("whole_source_group_assignment_required")
        allowed |= Q(subject_id=row.subject_id, period_id=row.period_id, groups__pk__in=pin["groups"])
    if (
        model("workload.TeachingTaskRow")
        .objects.filter(organization=organization, row_kind="teaching")
        .filter(allowed)
        .exclude(task__status="cancelled")
        .exclude(pk__in=pins)
        .exists()
    ):
        raise RepairError("other_samecourse_source_row_requires_review")
    group_ids = {str(g) for pin in CASE["offerings"].values() for g in (pin["group_id"],)}
    tenant_groups = set(
        map(
            str,
            model("organizations.OrgUnit")
            .objects.filter(organization=organization, unit_type="group")
            .values_list("pk", flat=True),
        )
    )
    groups = model("organizations.OrgUnit").objects.filter(pk__in=group_ids, organization=organization)
    if groups.count() != len(group_ids):
        raise RepairError("official_tenant_groups_required")
    for group in groups:
        value = [
            group.name,
            group.code,
            str(group.parent_id),
            project_group_settings(group.settings, canonical_group_ids=tenant_groups),
            group.unit_type,
            group.is_active,
        ]
        if digest(value) != spec.GROUP_IDENTITIES[str(group.pk)]:
            raise RepairError("official_group_identity_changed")
    for teacher_id in TEACHERS:
        user = model("auth.User").objects.get(pk=teacher_id, is_active=True)
        profile = model("accounts.UserProfile").objects.get(user_id=teacher_id, organization=organization)
        if digest([user.first_name, user.last_name, profile.patronymic]) != spec.TEACHER_IDENTITIES[teacher_id]:
            raise RepairError("source_full_teacher_identity_changed")
    syllabi = model("syllabus.Syllabus").objects.filter(offering_id__in=CASE["offerings"], is_active=True)
    expected_plan = _plan(CASE["plan_hours"])
    if any(_plan(syllabus.plan_hours_override) != expected_plan for syllabus in syllabi):
        raise RepairError("prior_contact_syllabus_plan_required")
    versions = model("syllabus.SyllabusVersion").objects.filter(syllabus__in=syllabi).exclude(status="archived")
    if any(_plan(version.plan_hours) != expected_plan for version in versions):
        raise RepairError("prior_contact_syllabus_version_plan_required")
    return rows, group_ids


def capture(*, organization, actor, lock=False):
    if str(organization.pk) != spec.ORG or not organization.is_active or organization.status != "active":
        raise RepairError("fixed_active_tenant_required")
    validate_reviewed_onomastics_roster(organization=organization, actor=actor, lock=lock)
    source_rows, group_ids = _source(organization, lock)
    definition = reviewed_onomastics_spec()
    if CASE["source"]["sha256"] != definition["source_sha256"]:
        raise RepairError("official_source_fingerprint_changed")
    ids = set(ROOT_OFFERINGS)
    Enrollment = model("registrar.Enrollment")
    for _ in range(26):
        seed = Enrollment.objects.filter(offering_id__in=ids)
        linked = Enrollment.objects.filter(
            Q(pk__in=seed.values("superseded_by_id")) | Q(superseded_by__in=seed.values("pk"))
        )
        found = ids | set(map(str, linked.values_list("offering_id", flat=True)))
        if found == ids:
            break
        if len(found) > 25 or model("registrar.CourseOffering").objects.filter(
            pk__in=found, organization=organization, period_id=next(iter(CASE["offerings"].values()))["period_id"]
        ).count() != len(found):
            raise RepairError("history_scope_requires_separate_review")
        ids = found
    else:
        raise RepairError("history_closure_budget_exceeded")
    records_query = model("registrar.StudentAcademicRecord").objects.filter(
        pk__in=[p["record_id"] for p in definition["roster"].values()]
    )
    program_ids = records_query.values("program_id")
    curriculum_ids = records_query.values("curriculum_id")
    roots = {
        "registrar.CourseOffering": ids,
        "workload.TeachingTaskRow": {r.pk for r in source_rows},
        "registrar.StudentAcademicRecord": {p["record_id"] for p in definition["roster"].values()},
    }
    data = {
        "graph": _graph(roots, lock=lock),
        "access": reviewed_onomastics_access_snapshot(organization=organization, actor=actor),
        "groups": records(model("organizations.OrgUnit").objects.filter(pk__in=group_ids), lock=lock),
        "programs": records(model("registrar.Program").objects.filter(pk__in=program_ids), lock=lock),
        "curricula": records(model("registrar.Curriculum").objects.filter(pk__in=curriculum_ids), lock=lock),
        "tasks": records(
            model("workload.TeachingTask").objects.filter(pk__in={r.task_id for r in source_rows}), lock=lock
        ),
        "memberships": records(
            model("organizations.Membership").objects.filter(organization=organization, user_id__in=TEACHERS),
            lock=lock,
        ),
        "teachers": list(
            model("auth.User")
            .objects.filter(pk__in=TEACHERS)
            .order_by("pk")
            .values("id", "first_name", "last_name", "is_active")
        ),
        "profiles": records(
            model("accounts.UserProfile").objects.filter(organization=organization, user_id__in=TEACHERS), lock=lock
        ),
        "roles": records(
            model("organizations.Role").objects.filter(
                pk__in=model("organizations.Membership")
                .objects.filter(organization=organization, user_id__in=TEACHERS)
                .values("role_id")
            ),
            lock=lock,
        ),
        "source_sha256": definition["source_sha256"],
        "browser_sha256": definition["browser_sha256"],
    }
    return data


def links(data):
    label = model("registrar.JournalShare").enrollments.through._meta.label
    return data["graph"].get(label, [])


def original(data):
    """The existing contact guard verifies all ten shares and original116throughPKs."""
    Share = model("registrar.JournalShare")
    through = Share.enrollments.through
    for oid in ROOT_OFFERINGS:
        pin = retained_rights.PINS[oid]
        shares = list(Share.objects.filter(offering_id=oid).order_by("pk").values())
        if {str(row["id"]): sha(row) for row in shares} != pin["shares"]:
            raise RepairError("original_legacy_share_records_changed")
        selected = list(through.objects.filter(journalshare_id__in=[r["id"] for r in shares]).order_by("pk").values())
        if sha(selected) != pin["through_sha256"]:
            raise RepairError("original_legacy_scope_changed")
        enrollments = list(
            model("registrar.Enrollment")
            .objects.filter(pk__in=[r["enrollment_id"] for r in selected])
            .order_by("pk")
            .values(*retained_rights.ENROLLMENT_FIELDS)
        )
        if sha(enrollments) != pin["selected_enrollments_sha256"]:
            raise RepairError("original_selected_enrollments_changed")
    if len(links(data)) != 116:
        raise RepairError("exact_original_116_links_required")


def validate_access(before, after):
    """Only completing the seminar claim may narrow owner kinds; retain history."""
    owner, seminar = map(str, TEACHERS)
    definition = reviewed_onomastics_spec()
    if set(before) != set(CASE["offerings"]) or set(before) != set(after):
        raise RepairError("unexpected_access_offering_scope")
    for oid in before:
        old_owner, new_owner = before[oid][owner], after[oid][owner]
        old_sem, new_sem = before[oid][seminar], after[oid][seminar]
        expected = set(old_owner["kinds"]) - {"seminar"}
        if "seminar" not in old_owner["kinds"] or set(new_owner["kinds"]) != expected:
            raise RepairError("unexpected_owner_kind_change")
        if (
            old_owner["active_roster"] != new_owner["active_roster"]
            or old_owner["can_manage_scores"] != new_owner["can_manage_scores"]
        ):
            raise RepairError("owner_lecture_roster_or_score_access_changed")
        additional = {eid for eid, pin in definition["roster"].items() if pin["offering_id"] == oid}
        if (
            old_sem["kinds"] != ["seminar"]
            or new_sem["kinds"] != ["seminar"]
            or set(new_sem["active_roster"]) != set(old_sem["active_roster"]) | additional
            or old_sem["can_manage_scores"] != new_sem["can_manage_scores"]
            or not old_sem["all_seminar_readable"]
            or not new_sem["all_seminar_readable"]
        ):
            raise RepairError("unexpected_seminar_source_access_change")
        for old, new in ((old_owner, new_owner), (old_sem, new_sem)):
            if (
                old["owned_seminar_ids"] != new["owned_seminar_ids"]
                or not old["owned_seminar_readable"]
                or not new["owned_seminar_readable"]
            ):
                raise RepairError("owned_historical_seminar_read_access_changed")
