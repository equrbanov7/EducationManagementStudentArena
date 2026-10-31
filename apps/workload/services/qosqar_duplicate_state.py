"""Fixed current duplicate scope; historical source868 journal stays immutable."""

import hashlib
import json

from django.apps import apps

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
FILLED = "4a94b82c-a6f9-4e29-9b07-cbbc4a56fb63"
EMPTY = "c6699552-e833-4c20-9cb0-78ae4be4352b"
KEEP_ROW = "29022155-8b7d-4efc-abb5-3dc7d3a686cf"
REMOVE_ROW = "b56648eb-fa8c-4e58-8054-e7f88bab9cff"
TASK = "663dbec7-6043-4b12-9f69-9d1278a1b7cb"
GROUP = "2700bd7b-2748-450e-a5e1-4b20f7feea21"
PERIOD = "a4f88744-8d49-4772-84ef-c28a96c3b372"
SUBJECT = "6d0dbff5-1140-4991-92d6-88518b704556"
DUPLICATE_SUBJECT = "57f0e160-8371-4974-811d-aa5b68dbacc8"
TEACHER = 7851
SOURCE_PROOF = "7d347cbf097f30864f184437f7146ada66f5e9a434d847640d3a98dbfeab8df1"
RESOURCE = "workload.qosqar_current_duplicate"


class DuplicateError(ValueError):
    pass


def model(label):
    return apps.get_model(label)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def records(query):
    return list(query.order_by("pk").values())


def graph():
    """Reverse academic graph, including grades/corrections and syllabus versions.

    Generic traversal includes newly introduced dependent academic records in the
    before/after invariant. It never follows a forward FK into an unrelated course.
    """
    pending = {"registrar.CourseOffering": {FILLED, EMPTY}}
    seen, result = {}, {}
    while pending:
        label, ids = pending.popitem()
        ids = set(map(str, ids)) - seen.get(label, set())
        if not ids:
            continue
        cls = model(label)
        query = cls._base_manager.filter(pk__in=ids)
        if any(f.name == "organization" for f in cls._meta.concrete_fields):
            query = query.filter(organization_id=ORG)
        values = records(query)
        seen.setdefault(label, set()).update(ids)
        result.setdefault(label, []).extend(values)
        if sum(len(v) for v in result.values()) > 20000:
            raise DuplicateError("academic_scope_exceeds_fixed_budget")
        for relation in cls._meta.get_fields(include_hidden=True):
            child = relation.related_model
            if not relation.auto_created or relation.concrete or not child:
                continue
            if child._meta.app_label not in ("registrar", "syllabus"):
                continue
            field = relation.field
            lookup = field.name if relation.many_to_many else field.attname
            child_ids = child._base_manager.filter(**{f"{lookup}__in": ids}).values_list("pk", flat=True)
            pending.setdefault(child._meta.label, set()).update(map(str, child_ids))
    return {key: sorted(value, key=lambda row: str(row["id"])) for key, value in sorted(result.items())}


def capture():
    rows = model("workload.TeachingTaskRow").objects.filter(pk__in=(KEEP_ROW, REMOVE_ROW), organization_id=ORG)
    return {
        "academic": graph(),
        "rows": records(rows),
        "groups": sorted(
            (str(row.pk), str(group)) for row in rows for group in row.groups.values_list("pk", flat=True)
        ),
        "assignments": records(model("workload.TeacherAssignment").objects.filter(row__in=rows)),
        "task": records(model("workload.TeachingTask").objects.filter(pk=TASK, organization_id=ORG)),
    }


def protected(value):
    result = dict(value["academic"])
    result["registrar.CourseOffering"] = [
        {k: v for k, v in row.items() if not (str(row["id"]) == EMPTY and k == "is_active")}
        for row in result["registrar.CourseOffering"]
    ]
    result["canonical_row"] = [row for row in value["rows"] if str(row["id"]) == KEEP_ROW]
    result["canonical_groups"] = [row for row in value["groups"] if row[0] == KEEP_ROW]
    result["canonical_assignments"] = [row for row in value["assignments"] if str(row["row_id"]) == KEEP_ROW]
    return result


def reject_row_history(row):
    allowed = {"workload.TeacherAssignment", row.groups.through._meta.label}
    for relation in row._meta.get_fields(include_hidden=True):
        child = relation.related_model
        if not relation.auto_created or relation.concrete or not child or child._meta.label in allowed:
            continue
        field = relation.field
        lookup = field.name if relation.many_to_many else field.attname
        if child._base_manager.filter(**{lookup: row.pk}).exists():
            raise DuplicateError("duplicate_row_has_history_" + child._meta.model_name)
    assignments = row.assignments.all()
    for relation in model("workload.TeacherAssignment")._meta.get_fields(include_hidden=True):
        child = relation.related_model
        if not relation.auto_created or relation.concrete or not child:
            continue
        field = relation.field
        lookup = field.name if relation.many_to_many else field.attname
        if child._base_manager.filter(**{f"{lookup}__in": assignments}).exists():
            raise DuplicateError("duplicate_assignment_has_history_" + child._meta.model_name)
    # Objection FK can point at an assignment even if row_id is null.
    if model("workload.LoadObjection").objects.filter(assignment__in=assignments).exists():
        raise DuplicateError("duplicate_assignment_has_objection")
    if model("workload.WorkloadAmendment").objects.filter(task_id=TASK, target_id=row.pk).exists():
        raise DuplicateError("duplicate_row_has_prior_amendment")


def validate(offerings, *, retired=False):
    if set(offerings) != {FILLED, EMPTY}:
        raise DuplicateError("fixed_offerings_missing")
    for oid, subject, code in ((FILLED, SUBJECT, "QKU-868"), (EMPTY, DUPLICATE_SUBJECT, "QKU-1487")):
        o = offerings[oid]
        if (str(o.subject_id), str(o.group_id), str(o.period_id), o.instructor_id, o.lesson_hours, o.subject.code) != (
            subject,
            GROUP,
            PERIOD,
            TEACHER,
            90,
            code,
        ) or o.is_active != (oid != EMPTY or not retired):
            raise DuplicateError("fixed_offering_identity_or_activity_changed")
    for label in ("registrar.Lesson", "syllabus.Syllabus", "syllabus.SyllabusShare", "registrar.ScheduleSlot"):
        if model(label).objects.filter(offering_id=EMPTY).exists():
            raise DuplicateError("empty_offering_has_content_or_schedule_" + label.lower().replace(".", "_"))
    metadata = {
        "registrar.Enrollment",
        "registrar.AssessmentScheme",
        "registrar.AssessmentComponent",
        "registrar.JournalShare",
    }
    for relation in model("registrar.CourseOffering")._meta.get_fields(include_hidden=True):
        child = relation.related_model
        if not relation.auto_created or relation.concrete or not child or child._meta.label in metadata:
            continue
        field = relation.field
        lookup = field.name if relation.many_to_many else field.attname
        if child._base_manager.filter(**{lookup: EMPTY}).exists():
            raise DuplicateError("empty_offering_has_dependent_history_" + child._meta.model_name)
    # Any non-configuration descendants under source enrollments prevent retirement.
    enrollments = model("registrar.Enrollment").objects.filter(offering_id=EMPTY)
    for relation in model("registrar.Enrollment")._meta.get_fields(include_hidden=True):
        child = relation.related_model
        if not relation.auto_created or relation.concrete or not child:
            continue
        field = relation.field
        lookup = field.name if relation.many_to_many else field.attname
        if child._base_manager.filter(**{f"{lookup}__in": enrollments}).exists():
            raise DuplicateError("empty_enrollment_has_history_" + child._meta.model_name)
    if not model("registrar.Lesson").objects.filter(offering_id=FILLED).exists():
        raise DuplicateError("canonical_historical_journal_missing")
    if (
        model("workload.TeachingTaskRow")
        .objects.filter(
            organization_id=ORG, period_id=PERIOD, subject_id__in=(SUBJECT, DUPLICATE_SUBJECT), groups__pk=GROUP
        )
        .exclude(pk__in=(KEEP_ROW, REMOVE_ROW))
        .exists()
    ):
        raise DuplicateError("alternate_workload_requires_review")
    rows = list(model("workload.TeachingTaskRow").objects.filter(pk__in=(KEEP_ROW, REMOVE_ROW), organization_id=ORG))
    if {str(row.pk) for row in rows} != ({KEEP_ROW} if retired else {KEEP_ROW, REMOVE_ROW}):
        raise DuplicateError("fixed_workload_row_set_changed")
    for row in rows:
        subject = SUBJECT if str(row.pk) == KEEP_ROW else DUPLICATE_SUBJECT
        if (
            str(row.task_id),
            str(row.subject_id),
            str(row.period_id),
            row.row_kind,
            row.lecture_total,
            row.seminar_total,
            row.lab_total,
            row.lecture_plan,
            row.seminar_plan,
            row.lab_plan,
            row.total_hours,
        ) != (TASK, subject, PERIOD, "teaching", 45, 45, 0, 45, 45, 0, 90) or set(
            map(str, row.groups.values_list("pk", flat=True))
        ) != {
            GROUP
        }:
            raise DuplicateError("fixed_workload_identity_or_hours_changed")
        if sorted(row.assignments.values_list("teacher_id", "activity", "hours")) != [
            (TEACHER, "lecture", 45),
            (TEACHER, "seminar", 45),
        ]:
            raise DuplicateError("fixed_assignment_changed")
        if str(row.pk) == REMOVE_ROW:
            reject_row_history(row)
    return {str(row.pk): row for row in rows}
