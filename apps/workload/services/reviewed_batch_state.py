"""Locked scope, live baseline and protected state for reviewed source batches."""

from django.db import connection
from django.db.models import Q, Sum

from apps.registrar.public import handover

from .owner_activity_state import workload_records
from .people import is_assignable_teacher
from .repair_fingerprints import academic_database_fingerprint
from .reviewed_batch_manifest import ACTIVITIES, ORG, YEAR
from .sbio235_state import RepairError, digest, model, records
from .scoping import ensure_can_distribute, ensure_can_manage
from .workflow import ensure_distribution_stage


def keys_q(plan):
    query = Q(pk__in=[])
    for subject, period, group in plan.keys:
        query |= Q(subject_id=subject, period_id=period, group_id=group)
    return query


def offerings(plan):
    return model("registrar.CourseOffering").objects.filter(organization_id=ORG).filter(keys_q(plan))


def task_rows(plan):
    return model("workload.TeachingTaskRow").objects.filter(organization_id=ORG, task_id__in=plan.task_ids)


def db_fingerprint(query):
    """All field values stay inside PostgreSQL; only count/hash leaves the DB."""
    if connection.vendor != "postgresql":
        raise RepairError("postgresql_required")
    sql, params = query.order_by().query.sql_with_params()
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT count(*), md5(coalesce(string_agg(md5(row_to_json(state)::text), '' ORDER BY id), '')) FROM ("
            + sql
            + ") state",
            params,
        )
        count, md5 = cursor.fetchone()
    return {"count": count, "md5": md5}


def outside(plan):
    ids = offerings(plan).values("pk")
    result = {}
    for label, path in (
        ("registrar.CourseOffering", "pk"),
        ("registrar.Lesson", "offering_id"),
        ("registrar.Enrollment", "offering_id"),
        ("registrar.LessonMark", "lesson__offering_id"),
        ("registrar.JournalShare", "offering_id"),
        ("registrar.TeachingHandover", "offering_id"),
    ):
        result[label] = db_fingerprint(model(label).objects.filter(organization_id=ORG).exclude(**{path + "__in": ids}))
    for label in (
        "organizations.Membership",
        "organizations.Role",
        "registrar.StudentAcademicRecord",
        "syllabus.Syllabus",
    ):
        result[label] = db_fingerprint(model(label).objects.filter(organization_id=ORG))
    for name, scope in (
        ("syllabus.SyllabusVersion", "syllabus__organization_id"),
        ("syllabus.SyllabusSection", "version__syllabus__organization_id"),
        ("syllabus.SyllabusReview", "version__syllabus__organization_id"),
    ):
        result[name] = db_fingerprint(model(name).objects.filter(**{scope: ORG}))
    for name, path in (
        ("SelfWorkTopic", "offering_id"),
        ("SelfWorkMark", "enrollment__offering_id"),
        ("ComponentScore", "enrollment__offering_id"),
        ("CriterionScore", "enrollment__offering_id"),
        ("CourseWork", "enrollment__offering_id"),
        ("FinalGrade", "enrollment__offering_id"),
        ("ResitRecord", "enrollment__offering_id"),
        ("AssessmentScheme", "offering_id"),
        ("AssessmentComponent", "offering_id"),
        ("ScheduleSlot", "offering_id"),
    ):
        result[name] = db_fingerprint(
            model("registrar." + name).objects.filter(organization_id=ORG).exclude(**{path + "__in": ids})
        )
    return result


def snapshot(plan, *, lock=False):
    task_state = records(
        model("workload.TeachingTask").objects.filter(organization_id=ORG, pk__in=plan.task_ids), lock=lock
    )
    row_state = workload_records(task_rows(plan), lock=lock)
    offering_state = records(offerings(plan), lock=lock)
    current = list(offerings(plan).order_by("pk"))
    selected_groups = plan.group_ids | {group["id"] for item in plan.items for group in item["source_groups"]}
    return {
        "selection": plan.selection_sha,
        "tasks": task_state,
        "rows": row_state,
        "offerings": offering_state,
        "groups": records(
            model("organizations.OrgUnit").objects.filter(organization_id=ORG, pk__in=selected_groups), lock=lock
        ),
        "periods": records(
            model("organizations.AcademicPeriod").objects.filter(
                organization_id=ORG, pk__in={item["period_id"] for item in plan.items}
            ),
            lock=lock,
        ),
        "programs": records(
            model("registrar.Program").objects.filter(
                organization_id=ORG,
                specialty_unit_id__in=model("organizations.OrgUnit")
                .objects.filter(organization_id=ORG, pk__in=selected_groups)
                .values("parent_id"),
            ),
            lock=lock,
        ),
        "subjects": records(
            model("registrar.Subject").objects.filter(
                organization_id=ORG, pk__in={item["subject_id"] for item in plan.items}
            ),
            lock=lock,
        ),
        "memberships": records(
            model("organizations.Membership").objects.filter(organization_id=ORG, user_id__in=plan.teacher_ids),
            lock=lock,
        ),
        "roles": records(model("organizations.Role").objects.filter(organization_id=ORG), lock=lock),
        "teachers": list(
            model("auth.User")
            .objects.filter(pk__in=plan.teacher_ids)
            .order_by("pk")
            .values("id", "first_name", "last_name", "is_active")
        ),
        "profiles": list(
            model("accounts.UserProfile")
            .objects.filter(organization_id=ORG, user_id__in=plan.teacher_ids)
            .order_by("user_id")
            .values("user_id", "patronymic")
        ),
        "academic": academic_database_fingerprint(organization_id=ORG, offerings=current),
    }


def baseline(value):
    return digest(value)


def validate(plan, *, actor):
    tasks = {
        str(task.pk): task
        for task in model("workload.TeachingTask").objects.filter(
            organization_id=ORG, academic_year=YEAR, pk__in=plan.task_ids
        )
    }
    if set(tasks) != plan.task_ids:
        raise RepairError("reviewed_task_missing")
    rows, journals = {}, {(str(o.subject_id), str(o.period_id), str(o.group_id)): o for o in offerings(plan)}
    closed = handover.closed_offering_ids([o.pk for o in journals.values()])
    for item in plan.items:
        task = tasks[item["task_id"]]
        ensure_can_manage(actor, task.chair_id)
        ensure_can_distribute(actor, task.chair_id)
        ensure_distribution_stage(task)
        period = (
            model("organizations.AcademicPeriod")
            .objects.filter(organization_id=ORG, pk=item["period_id"], academic_year=YEAR, is_active=True)
            .first()
        )
        if period is None or period.locked_at:
            raise RepairError("source_period_missing_inactive_or_locked")
        season = "spring" if period.start_date.month in (2, 3, 4, 5, 6) else "fall"
        if item["season"] != season:
            raise RepairError("source_period_season_mismatch")
        subject = (
            model("registrar.Subject")
            .objects.filter(
                organization_id=ORG,
                pk=item["subject_id"],
                is_active=True,
                name=item["subject"]["name"],
                code=item["subject"]["code"],
            )
            .first()
        )
        if (
            subject is None
            or model("registrar.Subject")
            .objects.filter(organization_id=ORG, code__iexact=item["subject"]["code"])
            .count()
            != 1
        ):
            raise RepairError("current_subject_exact_code_title_org_guard")
        source_groups = {str(group["id"]): group for group in item["source_groups"]}
        expected_groups = {
            **source_groups,
            **{
                child["id"]: {**child, "parent_id": parent["parent_id"], "source_parent": parent["id"]}
                for parent in source_groups.values()
                for child in parent.get("children", [])
            },
        }
        for gid in item["group_ids"]:
            group = (
                model("organizations.OrgUnit")
                .objects.filter(organization_id=ORG, unit_type="group", pk=gid, is_active=True)
                .first()
            )
            expected = expected_groups.get(gid)
            if (
                group is None
                or expected is None
                or group.name != expected["name"]
                or str(group.parent_id) != expected["parent_id"]
            ):
                raise RepairError("source_physical_group_identity_changed")
            if (
                expected.get("source_parent")
                and str((group.settings or {}).get("parent_group")) != expected["source_parent"]
            ):
                raise RepairError("source_child_parent_relationship_changed")
        identity = {teacher["id"]: teacher for teacher in item["teacher_identity"]}
        for assignment in item["assignments"]:
            tid = assignment["teacher_id"]
            teacher = model("auth.User").objects.filter(pk=tid, is_active=True).first()
            profile = model("accounts.UserProfile").objects.filter(organization_id=ORG, user_id=tid).first()
            source = identity.get(tid)
            if (
                teacher is None
                or profile is None
                or source is None
                or (teacher.first_name, teacher.last_name, profile.patronymic)
                != (source["first_name"], source["last_name"], source["patronymic"])
            ):
                raise RepairError("source_teacher_full_identity_changed")
            if not is_assignable_teacher(task.organization, task.chair, teacher):
                raise RepairError("existing_scoped_teacher_membership_required_no_auto_join")
        matching = (
            model("workload.TeachingTaskRow")
            .objects.filter(
                organization_id=ORG,
                task__academic_year=YEAR,
                subject_id=item["subject_id"],
                period_id=item["period_id"],
                groups__pk__in=item["group_ids"],
            )
            .distinct()
        )
        if item["mode"] == "patch":
            if set(map(str, matching.values_list("pk", flat=True))) != {item["row_id"]}:
                raise RepairError("physical_course_has_unreviewed_workload_rows")
            row = matching.select_related("task").get(pk=item["row_id"], task_id=item["task_id"])
            expected = item["existing_rows"][0]
            actual = workload_records(matching)[0]
            for field in (
                "subject_id",
                "period_id",
                "task_id",
                "lecture_plan",
                "lecture_total",
                "seminar_plan",
                "seminar_total",
                "lab_plan",
                "lab_total",
                "union_count",
                "subgroup_count",
            ):
                if str(actual[field]) != str(expected[field]):
                    raise RepairError("reviewed_existing_row_changed:" + field)
            if sorted(str(group.pk) for group in row.groups.all()) != item["group_ids"]:
                raise RepairError("existing_group_set_changed")
            before_assignments = {a["id"]: a for a in expected["assignments"]}
            actual_assignments = list(row.assignments.all())
            if {str(a.pk) for a in actual_assignments} != set(before_assignments):
                raise RepairError("reviewed_assignment_set_changed")
            for assignment in actual_assignments:
                old = before_assignments[str(assignment.pk)]
                if (assignment.teacher_id, assignment.activity, assignment.hours, assignment.is_hourly_paid) != (
                    old["teacher_id"],
                    old["activity"],
                    old["hours"],
                    old["is_hourly_paid"],
                ):
                    raise RepairError("reviewed_assignment_changed")
            rows[item["line"]] = row
        elif matching.exists():
            raise RepairError("new_course_workload_already_exists")
        expected_offerings = {o["id"]: o for o in item["existing_journals"]}
        found = [
            journals[key]
            for key in plan.keys
            if key[0] == item["subject_id"]
            and key[1] == item["period_id"]
            and key[2] in item["group_ids"]
            and key in journals
        ]
        if {str(o.pk) for o in found} != set(expected_offerings):
            raise RepairError("reviewed_journal_allowlist_changed")
        if item["mode"] == "restore" and len(found) != len(item["group_ids"]):
            raise RepairError("existing_owner_journal_missing")
        if item["mode"] != "patch" and item["row_data"].get("degree_level") is None:
            parents = (
                model("organizations.OrgUnit")
                .objects.filter(organization_id=ORG, pk__in=item["group_ids"])
                .values("parent_id")
            )
            degrees = set(
                model("registrar.Program")
                .objects.filter(organization_id=ORG, specialty_unit_id__in=parents, is_active=True)
                .values_list("degree_level", flat=True)
            )
            if len(degrees) != 1 or not degrees <= {"bachelor", "master", "phd"}:
                raise RepairError("new_row_degree_program_context_not_unique")
            item["row_data"]["degree_level"] = next(iter(degrees))
        owner = item["assignments"][0]["teacher_id"]
        for offering in found:
            if not offering.is_active or offering.instructor_id != owner:
                raise RepairError("existing_owner_must_be_preserved")
            if offering.lesson_hours != expected_offerings[str(offering.pk)]["lesson_hours"]:
                raise RepairError("reviewed_journal_hours_changed")
            if offering.lesson_hours != item["contacts"] and offering.pk in closed:
                raise RepairError("journal_hours_locked_source_patch_requires_separate_review")
            taught = dict(offering.lessons.values("kind").annotate(hours=Sum("hours")).values_list("kind", "hours"))
            if any(int(taught.get(kind, 0) or 0) > item["plan"][kind] for kind in ACTIVITIES):
                raise RepairError("source_plan_below_recorded_teaching_hours")
    return tasks, rows
