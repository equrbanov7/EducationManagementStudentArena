"""235 SBİO üçün sabit əhatə və tam məzmun fingerprintləri; heç bir bypass yoxdur."""

import hashlib
import json

from django.apps import apps

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
YEAR = "2026/2027"
TASK = "663dbec7-6043-4b12-9f69-9d1278a1b7cb"
ANCHOR = "6f7f012e-cd90-4fec-9413-cd8bb48a39e5"
DUPLICATE = "2a2e24e6-c4fa-4f8c-96ee-ac73f8987fa7"
SUBJECT = "bf274759-1680-4a92-8ad7-ab1de3ae65c4"
PERIOD = "a4f88744-8d49-4772-84ef-c28a96c3b372"
PARENT = "bc10eead-aa10-4e07-8ca5-319b83018b57"
CHILDREN = ("e6f9fba6-57dc-4786-bb38-3f10470500ca", "6dd9a058-83ac-45f2-80a2-20327f6ca44a")
OFFERINGS = ("67675fe9-83c7-4ce0-aba7-95212d79fee0", "ddd16646-ea17-4dc1-aa14-eefd3dba03fe")
TEACHER = 7721
SOURCE_SHA = "7630be3cbe9bfe7050e2f308fae8c4959c35bd298967f5e3f2b77a0ab4a9cb09"
RESOURCE = "workload.sbio235_repair"


class RepairError(Exception):
    pass


def model(name):
    return apps.get_model(name)


def digest(value):
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def records(qs, *, lock=False):
    if lock:
        qs = qs.select_for_update()
    return json.loads(json.dumps(list(qs.order_by("pk").values()), default=str))


def workload_state(*, only_targets=False, exclude_targets=False, lock=False):
    rows = model("workload.TeachingTaskRow").objects.filter(organization_id=ORG, task_id=TASK, task__academic_year=YEAR)
    if only_targets:
        rows = rows.filter(pk__in=(ANCHOR, DUPLICATE))
    if exclude_targets:
        rows = rows.exclude(pk__in=(ANCHOR, DUPLICATE))
    result = []
    for data in records(rows, lock=lock):
        row = rows.get(pk=data["id"])
        data["groups"] = sorted(str(pk) for pk in row.groups.values_list("pk", flat=True))
        data["assignments"] = records(row.assignments.filter(organization_id=ORG), lock=lock)
        result.append(data)
    return result


def footprint(*, lock=False):
    """Hər bütün-sahə məzmununun yalnız count+SHA-sı auditə gedir."""
    queries = {
        "offering": model("registrar.CourseOffering").objects.filter(organization_id=ORG, pk__in=OFFERINGS),
        "lesson": model("registrar.Lesson").objects.filter(organization_id=ORG, offering_id__in=OFFERINGS),
        "enrollment": model("registrar.Enrollment").objects.filter(organization_id=ORG, offering_id__in=OFFERINGS),
        "syllabus": model("syllabus.Syllabus").objects.filter(
            organization_id=ORG, subject_id=SUBJECT, period_id=PERIOD
        ),
        "journal_share": model("registrar.JournalShare").objects.filter(organization_id=ORG, offering_id__in=OFFERINGS),
        "handover": model("registrar.TeachingHandover").objects.filter(organization_id=ORG, offering_id__in=OFFERINGS),
    }
    lesson_ids = queries["lesson"].values("pk")
    enrollment_ids = queries["enrollment"].values("pk")
    queries["mark"] = model("registrar.LessonMark").objects.filter(organization_id=ORG, lesson_id__in=lesson_ids)
    queries["selfwork_topic"] = model("registrar.SelfWorkTopic").objects.filter(
        organization_id=ORG, offering_id__in=OFFERINGS
    )
    queries["selfwork"] = model("registrar.SelfWorkMark").objects.filter(
        organization_id=ORG, enrollment_id__in=enrollment_ids
    )
    for name in ("ComponentScore", "CriterionScore", "CourseWork", "FinalGrade", "ResitRecord"):
        queries[name.lower()] = model("registrar." + name).objects.filter(
            organization_id=ORG, enrollment_id__in=enrollment_ids
        )
    for name in ("AssessmentScheme", "AssessmentComponent", "ScheduleSlot"):
        queries[name.lower()] = model("registrar." + name).objects.filter(
            organization_id=ORG, offering_id__in=OFFERINGS
        )
    syllabus_ids = queries["syllabus"].values("pk")
    queries["syllabus_share"] = model("syllabus.SyllabusShare").objects.filter(
        organization_id=ORG, syllabus_id__in=syllabus_ids
    )
    queries["version"] = model("syllabus.SyllabusVersion").objects.filter(syllabus_id__in=syllabus_ids)
    queries["section"] = model("syllabus.SyllabusSection").objects.filter(
        version_id__in=queries["version"].values("pk")
    )
    queries["review"] = model("syllabus.SyllabusReview").objects.filter(version_id__in=queries["version"].values("pk"))
    result = {}
    for key, qs in queries.items():
        data = records(qs, lock=lock)
        result[key] = {"count": len(data), "sha256": digest(data)}
    return result


def other_offerings():
    qs = (
        model("registrar.CourseOffering")
        .objects.filter(organization_id=ORG, period__academic_year=YEAR)
        .exclude(pk__in=OFFERINGS)
    )
    return digest(records(qs))


def validate_scope(task, *, after=False):
    allowed_statuses = ("amended",) if after else ("distributed", "amended")
    if task.status not in allowed_statuses:
        raise RepairError("task_status_mismatch")
    if str(task.pk) != TASK or str(task.organization_id) != ORG or task.academic_year != YEAR:
        raise RepairError("scope_mismatch")
    period = model("organizations.AcademicPeriod").objects.get(pk=PERIOD, organization_id=ORG)
    if period.academic_year != YEAR:
        raise RepairError("period_mismatch")
    groups = model("organizations.OrgUnit").objects.filter(organization_id=ORG, pk__in=(PARENT, *CHILDREN))
    if groups.count() != 3:
        raise RepairError("group_missing")
    for group in groups:
        if not group.is_active or (str(group.pk) != PARENT and str(group.settings.get("parent_group")) != PARENT):
            raise RepairError("group_parent_mismatch")
    teacher = model("auth.User").objects.filter(pk=TEACHER, is_active=True).first()
    if teacher is None:
        raise RepairError("teacher_inactive")
    offerings = (
        model("registrar.CourseOffering")
        .objects.select_for_update()
        .filter(
            organization_id=ORG,
            pk__in=OFFERINGS,
            subject_id=SUBJECT,
            period_id=PERIOD,
            instructor_id=TEACHER,
            lesson_hours=45,
            is_active=True,
        )
    )
    if offerings.count() != 2 or {str(o.group_id) for o in offerings} != set(CHILDREN):
        raise RepairError("offering_mismatch")
    rows = task.rows.filter(organization_id=ORG, pk__in=(ANCHOR, DUPLICATE))
    if rows.count() != (1 if after else 2):
        raise RepairError("row_count_mismatch")
    wanted = {ANCHOR: (30, 30, 15, 30, 2), DUPLICATE: (33, 33, 12, 12, 1)}
    for row in rows:
        if str(row.subject_id) != SUBJECT or str(row.period_id) != PERIOD or row.season != "fall":
            raise RepairError("row_scope_mismatch")
        shape = (row.lecture_plan, row.lecture_total, row.seminar_plan, row.seminar_total, row.subgroup_count)
        if shape != wanted[str(row.pk)] or row.union_count != 1 or row.lab_total or row.lab_plan:
            raise RepairError("row_shape_mismatch")
        expected_groups = set(CHILDREN) if after else {CHILDREN[int(str(row.pk) == DUPLICATE)]}
        if {str(pk) for pk in row.groups.values_list("pk", flat=True)} != expected_groups:
            raise RepairError("row_group_mismatch")
        assignments = list(row.assignments.values_list("teacher_id", "activity", "hours"))
        if sorted(assignments) != sorted(
            [(TEACHER, "lecture", row.lecture_total), (TEACHER, "seminar", row.seminar_total)]
        ):
            raise RepairError("assignment_mismatch")
        if row.reviews.exists() or row.objections.exists():
            raise RepairError("row_history_in_use")
    return rows


def task_header(*, after=False):
    qs = model("workload.TeachingTask").objects.filter(pk=TASK, organization_id=ORG, academic_year=YEAR)
    data = records(qs)[0]
    if after and data["status"] != "amended":
        raise RepairError("task_status_mismatch")
    data.pop("updated_at")  # canonical amendment opens update this routine timestamp only.
    # A confirmed task enters the canonical amendment flow; all other header
    # fields (including distributed actor/date and revision) must remain exact.
    if data["status"] == "distributed":
        data["status"] = "amended"
    return digest(data)


def workflow_history():
    scopes = {
        "WorkloadAmendment": {"task_id": TASK},
        "TaskFacultySlice": {"task_id": TASK},
        "TaskRowReview": {"row__task_id": TASK},
        "LoadObjection": {"row__task_id": TASK},
    }
    return {
        name: records(model("workload." + name).objects.filter(organization_id=ORG, **scope))
        for name, scope in scopes.items()
    }


def check_workflow_history(before):
    after = workflow_history()
    for name, rows in before.items():
        ids = {row["id"] for row in rows}
        existing = [row for row in after[name] if row["id"] in ids]
        if digest(existing) != digest(rows):
            raise RepairError("workflow_history_changed")
        additions = [row for row in after[name] if row["id"] not in ids]
        if name != "WorkloadAmendment" and additions:
            raise RepairError("workflow_history_changed")
        if name == "WorkloadAmendment" and any(str(row["target_id"]) not in (ANCHOR, DUPLICATE) for row in additions):
            raise RepairError("outside_amendment_created")
