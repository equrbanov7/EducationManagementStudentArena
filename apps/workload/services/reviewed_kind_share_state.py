"""Full protected graph and explicit BIO roster for one source-reviewed grant."""

from django.db.models import Q

from apps.registrar.public import (
    eligible_instructor_user_ids,
    journal_access_diagnostics,
    reviewed_share_preserves_owner,
)

from . import reviewed_kind_share_source as spec
from .offering_rules import plan_reached_chair
from .offering_shares import _assignment_group
from .sbio235_state import RepairError, digest, model, records


def _graph(roots, *, lock):
    pending, seen, result = {k: set(v) for k, v in roots.items()}, {}, {}
    while pending:
        label, ids = pending.popitem()
        ids = set(map(str, ids)) - seen.get(label, set())
        if not ids:
            continue
        cls = model(label)
        values = records(cls._base_manager.filter(pk__in=ids), lock=lock)
        if len(values) != len(ids) or any(str(r.get("organization_id", spec.ORG)) != spec.ORG for r in values):
            raise RepairError("protected_graph_scope_changed")
        seen.setdefault(label, set()).update(ids)
        result.setdefault(label, []).extend(values)
        if sum(map(len, result.values())) > 30000:
            raise RepairError("protected_graph_budget_exceeded")
        for rel in cls._meta.get_fields(include_hidden=True):
            if rel.auto_created and not rel.concrete and rel.related_model:
                lookup = rel.field.name if rel.many_to_many else rel.field.attname
                children = rel.related_model._base_manager.filter(**{lookup + "__in": ids}).values_list("pk", flat=True)
                pending.setdefault(rel.related_model._meta.label, set()).update(map(str, children))
    return {k: sorted(v, key=lambda row: str(row[model(k)._meta.pk.attname])) for k, v in sorted(result.items()) if v}


def _history_ids():
    ids = {spec.OFFERING}
    enrollment = model("registrar.Enrollment")
    while True:
        seed = enrollment.objects.filter(organization_id=spec.ORG, offering_id__in=ids)
        if (
            seed.filter(superseded_by__isnull=False)
            .exclude(
                superseded_by__organization_id=spec.ORG,
                superseded_by__offering__organization_id=spec.ORG,
                superseded_by__offering__period_id=spec.PERIOD,
                superseded_by__offering__subject_id=spec.SUBJECT,
            )
            .exists()
        ):
            raise RepairError("supersession_history_scope_changed")
        linked = enrollment.objects.filter(organization_id=spec.ORG).filter(
            Q(id__in=seed.values("superseded_by_id")) | Q(superseded_by__in=seed.values("id"))
        )
        found = ids | set(map(str, linked.values_list("offering_id", flat=True)))
        if found == ids:
            return ids
        if len(found) > 25 or model("registrar.CourseOffering").objects.filter(
            id__in=found, organization_id=spec.ORG, period_id=spec.PERIOD, subject_id=spec.SUBJECT
        ).count() != len(found):
            raise RepairError("bounded_history_scope_changed")
        ids = found


def prepare(*, organization, lock=False):
    if str(organization.pk) != spec.ORG or not organization.is_active or organization.status != "active":
        raise RepairError("fixed_active_tenant_required")
    offerings = model("registrar.CourseOffering").objects.filter(pk=spec.OFFERING, organization=organization)
    if lock:
        offerings = offerings.select_for_update(of=("self",))
    offering = offerings.select_related("organization", "period", "subject", "group").get()
    if (
        str(offering.subject_id),
        str(offering.period_id),
        str(offering.group_id),
        offering.instructor_id,
        offering.lesson_hours,
        offering.is_active,
    ) != (spec.SUBJECT, spec.PERIOD, spec.GROUP, spec.OWNER, 45, True):
        raise RepairError("fixed_offering_identity_changed")
    if offering.is_intensive or spec.text_sha(offering.subject.name) != spec.CELL_HASHES["C101"]:
        raise RepairError("official_course_identity_changed")
    if offering.period.academic_year != "2026/2027":
        raise RepairError("official_academic_year_changed")
    group_settings = offering.group.settings or {}
    if (
        not offering.group.is_active
        or offering.group.unit_type != "group"
        or spec.text_sha(spec.normalized(offering.group.name).replace(" ", "")) != spec.GROUP_KEY_SHA
        or group_settings.get("parent_group")
        or any(
            spec.normalized(group_settings[key]) not in ("az", "aze", "azərbaycan", "azerbaijani", "azərbaycan dili")
            for key in ("sector", "language")
            if group_settings.get(key)
        )
    ):
        raise RepairError("official_physical_group_identity_changed")
    if offering.period.locked_at is not None or not offering.period.is_current:
        raise RepairError("current_open_period_required")
    row = (
        model("workload.TeachingTaskRow")
        .objects.select_related("task")
        .prefetch_related("groups", "assignments")
        .get(pk=spec.ROW, organization=organization)
    )
    if row.row_kind != "teaching" or row.season != "fall" or row.task.academic_year != "2026/2027":
        raise RepairError("official_teaching_period_changed")
    if (
        not plan_reached_chair(row.task)
        or str(row.task_id) != spec.TASK
        or str(row.subject_id) != spec.SUBJECT
        or str(row.period_id) != spec.PERIOD
    ):
        raise RepairError("released_exact_workload_required")
    if {str(g.pk) for g in row.groups.all()} != {spec.GROUP}:
        raise RepairError("physical_source_group_changed")
    if (
        row.lecture_plan,
        row.lecture_total,
        row.seminar_plan,
        row.seminar_total,
        row.lab_plan,
        row.lab_total,
        row.union_count,
        row.subgroup_count,
        row.total_hours,
    ) != (30, 30, 15, 15, 0, 0, 1, 1, 45):
        raise RepairError("fixed_contact_geometry_changed")
    assigned = {str(a.pk): (a.teacher_id, a.activity, a.hours) for a in row.assignments.all()}
    if assigned != spec.ASSIGNMENTS or any(
        _assignment_group(a, row, offering.group) is not True for a in row.assignments.all()
    ):
        raise RepairError("fixed_assignment_or_section_changed")
    # Any additional positive same-identity row is a separate authority question.
    extra = (
        model("workload.TeachingTaskRow")
        .objects.filter(
            organization=organization,
            subject_id=spec.SUBJECT,
            period_id=spec.PERIOD,
            groups__id=spec.GROUP,
            assignments__hours__gt=0,
        )
        .exclude(pk=spec.ROW)
    )
    if extra.exists():
        raise RepairError("additional_workload_authority_requires_review")
    if {spec.TEACHER, spec.OWNER} - eligible_instructor_user_ids(organization=organization):
        raise RepairError("active_authorized_teachers_required")
    teacher = (
        model("auth.User")
        .objects.only("id", "first_name", "last_name", "is_active", "is_superuser")
        .get(pk=spec.TEACHER)
    )
    teacher.set_active_organization_context(organization)
    profile = model("accounts.UserProfile").objects.only("user_id", "patronymic").get(user_id=spec.TEACHER)
    if (
        spec.teacher_identity_sha(" ".join((teacher.last_name, teacher.first_name, profile.patronymic or "")))
        != spec.TEACHER_NAME_SHA
    ):
        raise RepairError("official_teacher_account_identity_changed")
    if model("registrar.TeachingHandover").objects.filter(offering=offering, reverted_at__isnull=True).exists():
        raise RepairError("handover_requires_separate_review")
    diagnosis = journal_access_diagnostics(offering=offering, teacher_ids=[spec.TEACHER])[0]
    if diagnosis["journal_locked"] or diagnosis["period_locked"] or diagnosis["syllabus_locked"]:
        raise RepairError("journal_or_syllabus_gate_closed")
    shares = model("registrar.JournalShare").objects.filter(offering=offering, is_active=True)
    if (
        shares.exclude(source="workload").exists()
        or model("registrar.JournalShare")
        .objects.filter(offering=offering, teacher_id=spec.TEACHER, source="manual")
        .exists()
    ):
        raise RepairError("manual_or_legacy_share_requires_review")
    enrollments = list(
        model("registrar.Enrollment")
        .objects.filter(organization=organization, offering=offering, status="enrolled", superseded_by__isnull=True)
        .order_by("pk")
    )
    if not enrollments or any(
        e.source_group_id is not None and str(e.source_group_id) != spec.GROUP for e in enrollments
    ):
        raise RepairError("explicit_source_group_roster_required")
    students = {e.student_id for e in enrollments}
    sar = model("registrar.StudentAcademicRecord").objects.filter(organization=organization, student_id__in=students)
    verified = set(
        sar.filter(group_id=spec.GROUP, is_active=True, status="enrolled").values_list("student_id", flat=True)
    )
    if verified != students:
        raise RepairError("source_group_student_geometry_unproven")
    if (
        model("registrar.Lesson")
        .objects.filter(offering=offering, instructor_id=spec.TEACHER)
        .exclude(kind="seminar")
        .exists()
    ):
        raise RepairError("unreviewed_owned_lesson_kind_requires_review")
    roster = sorted(str(e.pk) for e in enrollments)
    active = shares.filter(teacher_id=spec.TEACHER).first()
    if active and (
        active.kinds != ["seminar"] or sorted(map(str, active.enrollments.values_list("pk", flat=True))) != roster
    ):
        raise RepairError("existing_teacher_share_requires_review")
    if not reviewed_share_preserves_owner(
        offering=offering, teacher_id=spec.TEACHER, kinds=["seminar"], enrollment_ids=roster
    ):
        raise RepairError("existing_owner_access_would_change")
    return offering, teacher, roster


def capture(*, organization, lock=False):
    offering, teacher, roster = prepare(organization=organization, lock=lock)
    history = _history_ids()
    graph = _graph({"registrar.CourseOffering": history, "workload.TeachingTaskRow": [spec.ROW]}, lock=lock)
    share_model = model("registrar.JournalShare")
    through = share_model.enrollments.through
    excluded = {share_model._meta.label, through._meta.label}
    protected = {
        label: {"count": len(rows), "sha256": digest(rows)} for label, rows in graph.items() if label not in excluded
    }
    for label, query in {
        "task": model("workload.TeachingTask").objects.filter(pk=spec.TASK, organization=organization),
        "group": model("organizations.OrgUnit").objects.filter(pk=spec.GROUP, organization=organization),
        "subject": model("registrar.Subject").objects.filter(pk=spec.SUBJECT, organization=organization),
        "period": model("organizations.AcademicPeriod").objects.filter(pk=spec.PERIOD, organization=organization),
        "memberships": model("organizations.Membership").objects.filter(
            organization=organization, user_id__in=(spec.TEACHER, spec.OWNER)
        ),
        "roles": model("organizations.Role").objects.filter(
            organization=organization,
            id__in=model("organizations.Membership")
            .objects.filter(organization=organization, user_id__in=(spec.TEACHER, spec.OWNER))
            .values("role_id"),
        ),
        "student_records": model("registrar.StudentAcademicRecord").objects.filter(
            organization=organization,
            student_id__in=model("registrar.Enrollment").objects.filter(offering=offering).values("student_id"),
        ),
    }.items():
        values = records(query, lock=lock)
        protected[label] = {"count": len(values), "sha256": digest(values)}
    student_ids = list(
        model("registrar.Enrollment").objects.filter(offering=offering).values_list("student_id", flat=True)
    )
    users = model("auth.User").objects.filter(pk__in=set(student_ids + [spec.TEACHER, spec.OWNER])).order_by("pk")
    if lock:
        users = users.select_for_update()
    protected["user_identity"] = digest(list(users.values("id", "is_active", "first_name", "last_name")))
    profiles = model("accounts.UserProfile").objects.filter(user_id=spec.TEACHER)
    if lock:
        profiles = profiles.select_for_update()
    protected["teacher_patronymic"] = digest(list(profiles.values("user_id", "patronymic")))
    org_query = model("organizations.Organization").objects.filter(pk=organization.pk)
    if lock:
        org_query = org_query.select_for_update()
    protected["organization_policy"] = digest(
        list(org_query.values("id", "is_active", "status", "owner_id", "settings"))
    )
    if lock:
        offering, teacher, fresh_roster = prepare(organization=organization, lock=True)
        if fresh_roster != roster:
            raise RepairError("locked_roster_changed")
    return (
        offering,
        teacher,
        roster,
        {
            "protected": protected,
            "history_offerings": sorted(history),
            "roster": roster,
            "shares": records(share_model.objects.filter(offering_id__in=history), lock=lock),
            "share_students": records(through.objects.filter(journalshare__offering_id__in=history), lock=lock),
        },
    )


def created_share_state(data, share_id):
    return {
        "share": next(r for r in data["shares"] if str(r["id"]) == str(share_id)),
        "students": [r for r in data["share_students"] if str(r["journalshare_id"]) == str(share_id)],
    }
