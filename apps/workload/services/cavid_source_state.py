"""Cavid35/36: sabit tenant, sətir, müəllif və məzmun sərhədləri."""

from django.db import connection

from . import cavid_source_spec as spec
from .owner_activity_state import workload_records
from .repair_fingerprints import academic_fingerprint
from .sbio235_state import RepairError, digest, model, records

ACTIVITIES = ("lecture", "seminar", "lab")


def offerings():
    return model("registrar.CourseOffering").objects.filter(
        organization_id=spec.ORG, pk__in=(spec.OFFERING_A, spec.OFFERING_B)
    )


def target_membership():
    return model("organizations.Membership").objects.filter(
        organization_id=spec.ORG,
        user_id=spec.TEACHER,
        scope_unit_id=spec.NATURE,
        role__name="teacher",
        role__organization_id=spec.ORG,
    )


def snapshot(*, lock=False):
    tasks = model("workload.TeachingTask").objects.filter(
        organization_id=spec.ORG, pk__in=(spec.TASK_A, spec.TASK_B), academic_year=spec.YEAR
    )
    task_rows = model("workload.TeachingTaskRow").objects.filter(
        organization_id=spec.ORG, task_id__in=(spec.TASK_A, spec.TASK_B)
    )
    values = {
        "tasks": records(tasks, lock=lock),
        "rows": workload_records(task_rows, lock=lock),
        "offerings": records(offerings(), lock=lock),
        "handovers": records(
            model("registrar.TeachingHandover").objects.filter(
                organization_id=spec.ORG, offering_id__in=(spec.OFFERING_A, spec.OFFERING_B)
            ),
            lock=lock,
        ),
        "memberships": records(
            model("organizations.Membership").objects.filter(
                organization_id=spec.ORG, user_id__in=(spec.TEACHER, spec.PREVIOUS)
            ),
            lock=lock,
        ),
        "groups": records(
            model("organizations.OrgUnit").objects.filter(
                organization_id=spec.ORG,
                pk__in=(spec.GROUP_A, spec.GROUP_B, spec.SPECIALTY_A, spec.FINANCE, spec.NATURE),
            ),
            lock=lock,
        ),
        "period": records(
            model("organizations.AcademicPeriod").objects.filter(organization_id=spec.ORG, pk=spec.PERIOD),
            lock=lock,
        ),
        "subjects": records(
            model("registrar.Subject").objects.filter(
                organization_id=spec.ORG, pk__in=(spec.SUBJECT_A, spec.SUBJECT_B)
            ),
            lock=lock,
        ),
        "roles": records(model("organizations.Role").objects.filter(organization_id=spec.ORG), lock=lock),
        # Never select password hashes or private profile/identity fields.
        "teachers": list(
            model("auth.User")
            .objects.filter(pk__in=(spec.TEACHER, spec.PREVIOUS))
            .order_by("pk")
            .values("id", "username", "first_name", "last_name", "is_active")
        ),
        "profiles": [
            {**p, "organization_id": str(p["organization_id"])}
            for p in (
                model("accounts.UserProfile")
                .objects.filter(organization_id=spec.ORG, user_id__in=(spec.TEACHER, spec.PREVIOUS))
                .order_by("user_id")
                .values("user_id", "organization_id", "patronymic", "role")
            )
        ],
        "history": {
            name: records(model("workload." + name).objects.filter(organization_id=spec.ORG, **where))
            for name, where in {
                "WorkloadAmendment": {"task_id__in": (spec.TASK_A, spec.TASK_B)},
                "TaskFacultySlice": {"task_id__in": (spec.TASK_A, spec.TASK_B)},
                "TaskRowReview": {"row__task_id__in": (spec.TASK_A, spec.TASK_B)},
                "LoadObjection": {"row__task_id__in": (spec.TASK_A, spec.TASK_B)},
            }.items()
        },
    }
    values["academic"] = academic_fingerprint(organization_id=spec.ORG, offerings=list(offerings()), lock=lock)
    return values


def baseline(value):
    return digest({"manifest": spec.PLAN, "state": value})


def workload_baseline(value):
    return baseline({k: v for k, v in value.items() if k != "academic"})


def outside_fingerprint():
    """DB-side full-row fingerprints; no grades/student values leave PostgreSQL."""
    if connection.vendor != "postgresql":
        raise RepairError("postgresql_required")
    labels = [
        "registrar.CourseOffering",
        "registrar.Enrollment",
        "registrar.Lesson",
        "registrar.LessonMark",
        "registrar.SelfWorkTopic",
        "registrar.SelfWorkMark",
        "registrar.ComponentScore",
        "registrar.CriterionScore",
        "registrar.CourseWork",
        "registrar.FinalGrade",
        "registrar.ResitRecord",
        "registrar.AssessmentScheme",
        "registrar.AssessmentComponent",
        "registrar.ScheduleSlot",
        "registrar.JournalShare",
        "registrar.TeachingHandover",
        "syllabus.Syllabus",
        "syllabus.SyllabusVersion",
        "syllabus.SyllabusSection",
        "syllabus.SyllabusReview",
        "syllabus.SyllabusShare",
        "organizations.OrgUnit",
        "organizations.Role",
        "organizations.Membership",
    ]
    result = {}
    quote = connection.ops.quote_name
    with connection.cursor() as cursor:
        for label in labels:
            cls = model(label)
            fields = {f.name for f in cls._meta.fields}
            table = quote(cls._meta.db_table)
            condition, params = "t.organization_id=%s", [spec.ORG]
            if "organization" not in fields:
                version_table = quote(model("syllabus.SyllabusVersion")._meta.db_table)
                condition = f"t.version_id IN (SELECT id FROM {version_table} WHERE organization_id=%s)"
            if label == "registrar.CourseOffering":
                condition += " AND t.id<>%s"
                params.append(spec.OFFERING_B)
            elif label == "registrar.TeachingHandover":
                condition += " AND t.offering_id<>%s"
                params.append(spec.OFFERING_B)
            elif label == "organizations.Membership":
                role_table = quote(model("organizations.Role")._meta.db_table)
                condition += f" AND NOT (t.user_id=%s AND t.scope_unit_id IS NOT DISTINCT FROM %s AND t.role_id IN (SELECT id FROM {role_table} WHERE organization_id=%s AND name='teacher'))"
                params += [spec.TEACHER, spec.NATURE, spec.ORG]
            cursor.execute(
                f"SELECT count(*), md5(coalesce(string_agg(md5(row_to_json(t)::text), '' ORDER BY t.id), '')) FROM {table} t WHERE {condition}",
                params,
            )
            count, fingerprint = cursor.fetchone()
            result[label] = {"count": count, "md5": fingerprint}
    return result


def _assignment_shape(row):
    return sorted((str(a.pk), a.teacher_id, a.activity, a.hours, a.is_hourly_paid) for a in row.assignments.all())


def validate(*, after=False, receipt=None, undo=False):
    receipt = receipt or {}
    task_list = list(
        model("workload.TeachingTask").objects.filter(organization_id=spec.ORG, pk__in=(spec.TASK_A, spec.TASK_B))
    )
    if len(task_list) != 2:
        raise RepairError("fixed_tasks_missing")
    tasks = {str(t.pk): t for t in task_list}
    for tid, chair in ((spec.TASK_A, spec.FINANCE), (spec.TASK_B, spec.NATURE)):
        task = tasks[tid]
        if (
            task.academic_year != spec.YEAR
            or str(task.chair_id) != chair
            or task.status not in ("distributed", "amended")
        ):
            raise RepairError("task_scope_or_stage_mismatch")
    period = model("organizations.AcademicPeriod").objects.get(organization_id=spec.ORG, pk=spec.PERIOD)
    if period.academic_year != spec.YEAR or not period.is_active or period.is_locked:
        raise RepairError("period_unavailable")
    for key in ("teacher", "previous"):
        expected = spec.PLAN[key]
        user = model("auth.User").objects.filter(pk=expected["id"], is_active=True).first()
        profile = model("accounts.UserProfile").objects.filter(user_id=expected["id"], organization_id=spec.ORG).first()
        if (
            not user
            or not profile
            or (user.username, user.first_name, user.last_name, profile.patronymic)
            != (expected["username"], "Cavid", "Xəlilov", expected["patronymic"])
        ):
            raise RepairError("canonical_teacher_identity_mismatch")
    finance_members = model("organizations.Membership").objects.filter(
        organization_id=spec.ORG,
        user_id=spec.TEACHER,
        scope_unit_id=spec.FINANCE,
        role__name="teacher",
        role__is_active=True,
        role__organization_id=spec.ORG,
        is_active=True,
        is_primary=True,
    )
    if finance_members.count() != 1:
        raise RepairError("primary_finance_membership_required")
    target = list(target_membership())
    if len(target) > 1 or any(m.is_primary for m in target):
        raise RepairError("unexpected_target_membership")
    if after:
        if len(target) != 1 or not target[0].is_active or not target[0].role.is_active:
            raise RepairError("secondary_nature_membership_required")
    elif any(m.is_active for m in target):
        raise RepairError("preexisting_active_nature_access")
    journal_list = list(offerings())
    if len(journal_list) != 2:
        raise RepairError("fixed_journals_missing")
    journals = {str(o.pk): o for o in journal_list}
    for oid, sid, gid, teacher, hours in (
        (spec.OFFERING_A, spec.SUBJECT_A, spec.GROUP_A, spec.TEACHER, 60),
        (spec.OFFERING_B, spec.SUBJECT_B, spec.GROUP_B, spec.TEACHER if after else spec.PREVIOUS, 45),
    ):
        o = journals[oid]
        if not o.is_active or (
            str(o.subject_id),
            str(o.period_id),
            str(o.group_id),
            o.instructor_id,
            o.lesson_hours,
        ) != (sid, spec.PERIOD, gid, teacher, hours):
            raise RepairError("journal_identity_owner_or_hours_mismatch")
        if not o.group.is_active or o.group.unit_type != "group" or not o.subject.is_active:
            raise RepairError("subject_or_physical_group_inactive")
        if (
            model("registrar.CourseOffering")
            .objects.filter(organization_id=spec.ORG, subject_id=sid, period_id=spec.PERIOD, group_id=gid)
            .count()
            != 1
        ):
            raise RepairError("duplicate_physical_journal")
    a, b = journals[spec.OFFERING_A], journals[spec.OFFERING_B]
    if str(a.group.parent_id) != spec.SPECIALTY_A:
        raise RepairError("a_specialty_changed")
    if a.enrollments.count() != 7:
        raise RepairError("a_existing_roster_changed")
    if (
        a.lessons.count() < 12
        or model("registrar.LessonMark").objects.filter(organization_id=spec.ORG, lesson__offering=a).count() < 84
    ):
        raise RepairError("existing_a_content_missing")
    if (
        b.lessons.exists()
        or model("registrar.LessonMark").objects.filter(organization_id=spec.ORG, lesson__offering=b).exists()
    ):
        raise RepairError("b_journal_no_longer_empty")
    if (
        b.enrollments.count() != 2
        or model("syllabus.Syllabus").objects.filter(organization_id=spec.ORG, offering=b).exists()
    ):
        raise RepairError("b_roster_or_syllabus_changed")
    if model("registrar.JournalShare").objects.filter(organization_id=spec.ORG, offering=b, is_active=True).exists():
        raise RepairError("manual_b_share_requires_review")
    source_a_rows = (
        model("workload.TeachingTaskRow")
        .objects.filter(
            organization_id=spec.ORG, subject_id=spec.SUBJECT_A, period_id=spec.PERIOD, groups__pk=spec.GROUP_A
        )
        .distinct()
    )
    arows = list(source_a_rows)
    if len(arows) != int(after):
        raise RepairError("a_workload_already_exists_or_missing")
    row_a = arows[0] if after else None
    if row_a:
        if str(row_a.pk) != receipt.get("created_row_id") or str(row_a.task_id) != spec.TASK_A:
            raise RepairError("a_created_row_identity_mismatch")
        if {str(g) for g in row_a.groups.values_list("pk", flat=True)} != {spec.GROUP_A}:
            raise RepairError("a_group_set_changed")
        if (row_a.union_count, row_a.subgroup_count, row_a.total_hours, row_a.student_count, row_a.credits) != (
            1,
            1,
            60,
            6,
            "5",
        ) or any(
            getattr(row_a, a + s) != {"lecture": 30, "seminar": 30}.get(a, 0)
            for a in ACTIVITIES
            for s in ("_plan", "_total")
        ):
            raise RepairError("a_official_source_plan_mismatch")
        if sorted((a.teacher_id, a.activity, a.hours, a.is_hourly_paid) for a in row_a.assignments.all()) != [
            (spec.TEACHER, "lecture", 30, False),
            (spec.TEACHER, "seminar", 30, False),
        ]:
            raise RepairError("a_source_assignments_mismatch")
        if row_a.reviews.exists() or row_a.objections.exists():
            raise RepairError("a_new_workflow_history")
    row_b = tasks[spec.TASK_B].rows.get(pk=spec.ROW_B, organization_id=spec.ORG)
    if (
        str(row_b.subject_id),
        str(row_b.period_id),
        row_b.season,
        row_b.union_count,
        row_b.subgroup_count,
        row_b.total_hours,
    ) != (spec.SUBJECT_B, spec.PERIOD, "fall", 1, 1, 45):
        raise RepairError("b_row_identity_or_sections_mismatch")
    if {str(g) for g in row_b.groups.values_list("pk", flat=True)} != {spec.GROUP_B}:
        raise RepairError("b_fixed_group_changed")
    expected = {"lecture": 30, "seminar": 15} if after else {"lecture": 45}
    if any(getattr(row_b, a + s) != expected.get(a, 0) for a in ACTIVITIES for s in ("_plan", "_total")):
        raise RepairError("b_source_activity_shape_mismatch")
    actual = _assignment_shape(row_b)
    wanted = [(spec.LECTURE_B, spec.TEACHER if after else spec.PREVIOUS, "lecture", expected["lecture"], False)]
    if after:
        wanted.append((receipt.get("created_seminar_id"), spec.TEACHER, "seminar", 15, False))
    if actual != sorted(wanted) or row_b.reviews.exists() or row_b.objections.exists():
        raise RepairError("b_assignments_or_history_mismatch")
    return tasks, row_a, row_b, journals


def assert_protected(before, after, *, row_a_id, membership_id, undo=False):
    for key in ("groups", "period", "subjects", "roles", "teachers", "profiles"):
        if before[key] != after[key]:
            raise RepairError(key + "_changed")
    for old, new in zip(before["tasks"], after["tasks"]):
        if {k: v for k, v in old.items() if k not in ("updated_at", "status")} != {
            k: v for k, v in new.items() if k not in ("updated_at", "status")
        } or new["status"] != "amended":
            raise RepairError("task_header_changed")
    rows_before = {r["id"]: r for r in before["rows"]}
    rows_after = {r["id"]: r for r in after["rows"]}
    if set(rows_after) != (set(rows_before) - {row_a_id} if undo else set(rows_before) | {row_a_id}):
        raise RepairError("workload_row_set_changed")
    ignore = {"assignments", "updated_at", "lecture_plan", "lecture_total", "seminar_plan", "seminar_total"}
    for rid in set(rows_before) & set(rows_after):
        old, new = rows_before[rid], rows_after[rid]
        if rid != spec.ROW_B:
            if old != new:
                raise RepairError("outside_target_row_changed")
        elif {k: v for k, v in old.items() if k not in ignore} != {k: v for k, v in new.items() if k not in ignore}:
            raise RepairError("b_non_activity_metadata_changed")
        elif rid == spec.ROW_B:
            old_lecture = next(a for a in old["assignments"] if a["id"] == spec.LECTURE_B)
            new_lecture = next(a for a in new["assignments"] if a["id"] == spec.LECTURE_B)
            allowed_assignment_fields = {"teacher_id", "hours", "updated_at", "assigned_by_id"}
            if {k: v for k, v in old_lecture.items() if k not in allowed_assignment_fields} != {
                k: v for k, v in new_lecture.items() if k not in allowed_assignment_fields
            }:
                raise RepairError("original_lecture_assignment_metadata_changed")
    for oid in (spec.OFFERING_A, spec.OFFERING_B):
        old = next(o for o in before["offerings"] if o["id"] == oid)
        new = next(o for o in after["offerings"] if o["id"] == oid)
        ignored = {"instructor_id"} if oid == spec.OFFERING_B else set()
        if {k: v for k, v in old.items() if k not in ignored} != {k: v for k, v in new.items() if k not in ignored}:
            raise RepairError("journal_metadata_changed")
    excluded = {"offering", "handover"}
    if {k: v for k, v in before["academic"].items() if k not in excluded} != {
        k: v for k, v in after["academic"].items() if k not in excluded
    }:
        raise RepairError("academic_content_or_shares_changed")
    old_members = {m["id"]: m for m in before["memberships"]}
    new_members = {m["id"]: m for m in after["memberships"]}
    if set(old_members) - set(new_members) or set(new_members) - set(old_members) - {membership_id}:
        raise RepairError("unexpected_membership_identity_change")
    if any(old_members[mid] != new_members[mid] for mid in set(old_members) & set(new_members) if mid != membership_id):
        raise RepairError("existing_access_changed")
    if membership_id in old_members:
        allowed = {"is_active", "is_primary", "assigned_by_id", "updated_at"}
        if {k: v for k, v in old_members[membership_id].items() if k not in allowed} != {
            k: v for k, v in new_members[membership_id].items() if k not in allowed
        }:
            raise RepairError("secondary_membership_metadata_changed")
    old_handovers = {h["id"]: h for h in before["handovers"]}
    new_handovers = {h["id"]: h for h in after["handovers"]}
    if set(old_handovers) - set(new_handovers):
        raise RepairError("handover_history_removed")
    if not undo:
        if len(set(new_handovers) - set(old_handovers)) != 1 or any(
            new_handovers[hid] != old for hid, old in old_handovers.items()
        ):
            raise RepairError("unexpected_handover_history_change")
    else:
        changed = [hid for hid, old in old_handovers.items() if old != new_handovers[hid]]
        allowed = {"reverted_at", "reverted_by_id", "revert_reason", "updated_at"}
        if set(new_handovers) != set(old_handovers) or len(changed) != 1:
            raise RepairError("unexpected_handover_revert")
        hid = changed[0]
        if {k: v for k, v in old_handovers[hid].items() if k not in allowed} != {
            k: v for k, v in new_handovers[hid].items() if k not in allowed
        }:
            raise RepairError("handover_original_metadata_changed")
    for name, old in before["history"].items():
        ids = {x["id"] for x in old}
        new = after["history"][name]
        if [x for x in new if x["id"] in ids] != old:
            raise RepairError("workflow_history_changed")
        added = [x for x in new if x["id"] not in ids]
        if added and (
            name != "WorkloadAmendment" or any(str(x["target_id"]) not in (row_a_id, spec.ROW_B) for x in added)
        ):
            raise RepairError("outside_amendment_created")
