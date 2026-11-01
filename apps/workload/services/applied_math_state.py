"""One AppliedMath A/B identity swap: complete bounded snapshots, no grade relocation."""

import sys
from decimal import Decimal

from . import applied_math_history as history
from . import qosqar_duplicate_state as common

ORG = common.ORG
EMPTY = "892571e3-7270-4ee3-b580-831731901e9c"
FILLED = "1911c5cc-dae5-4e13-ba7d-9784fcc28dd0"
KEEP_ROW = "eee93b6e-5bfa-4436-8166-a08438f74efe"
REMOVE_ROW = "eb41b840-05b1-4637-8c2c-03fb8b36c0c3"
TASK = "743c143e-254a-4ef1-bf73-c368a477cc2f"
GROUP = "bb710525-2453-4ca0-85bc-71da98736988"
PERIOD = "a4f88744-8d49-4772-84ef-c28a96c3b372"
NEW = "2b42409c-2945-437e-96ab-fe249fce79b4"
OLD = "e3e63883-9808-4de7-8aad-0b0b6d4f1638"
TEACHER = 7753
RESOURCE = "workload.applied_math_journal_repair"
DuplicateError = common.DuplicateError
model, digest, records = common.model, common.digest, common.records
GROUPS = {GROUP, "4fd2387d-56fa-42b1-8dbf-98adf1a4127b", "fe5e7469-ad5c-4a4b-91de-5a572cbea53e"}


def graph():
    """Every reverse model, including unknown apps and hidden through rows, is protected."""
    pending, seen, result = {"registrar.CourseOffering": {EMPTY, FILLED}}, {}, {}
    while pending:
        label, ids = pending.popitem()
        ids = set(map(str, ids)) - seen.get(label, set())
        if not ids:
            continue
        cls = model(label)
        rows = records(cls._base_manager.select_for_update().filter(pk__in=ids))
        if any(str(r.get("organization_id", ORG)) != ORG for r in rows):
            raise DuplicateError("reverse_graph_tenant_changed")
        seen.setdefault(label, set()).update(ids)
        result.setdefault(label, []).extend(rows)
        if sum(map(len, result.values())) > 20000:
            raise DuplicateError("fixed_reverse_graph_budget")
        for rel in cls._meta.get_fields(include_hidden=True):
            child = rel.related_model
            if not rel.auto_created or rel.concrete or not child:
                continue
            field = rel.field
            lookup = field.name if rel.many_to_many else field.attname
            children = child._base_manager.filter(**{lookup + "__in": ids}).values_list("pk", flat=True)
            pending.setdefault(child._meta.label, set()).update(map(str, children))
    return {k: sorted(v, key=lambda r: str(r[model(k)._meta.pk.attname])) for k, v in sorted(result.items()) if v}


def capture():
    rows = model("workload.TeachingTaskRow").objects.filter(pk__in=(KEEP_ROW, REMOVE_ROW), organization_id=ORG)
    return {
        "academic": graph(),
        "history": history.capture(sys.modules[__name__]),
        "rows": records(rows),
        "group_links": records(
            model("workload.TeachingTaskRow").groups.through.objects.filter(
                teachingtaskrow_id__in=(KEEP_ROW, REMOVE_ROW)
            )
        ),
        "groups": sorted((str(r.pk), str(g)) for r in rows for g in r.groups.values_list("pk", flat=True)),
        "assignments": records(model("workload.TeacherAssignment").objects.filter(row__in=rows)),
        "task": records(model("workload.TeachingTask").objects.filter(pk=TASK, organization_id=ORG)),
        "subjects": records(model("registrar.Subject").objects.filter(pk__in=(OLD, NEW), organization_id=ORG)),
    }


def protected(value):
    graph = {
        k: v for k, v in value["academic"].items() if not k.startswith("syllabus.") and k != "registrar.ScheduleSlot"
    }
    graph["registrar.CourseOffering"] = [
        {k: v for k, v in row.items() if k != "subject_id" and not (str(row["id"]) == EMPTY and k == "is_active")}
        for row in graph["registrar.CourseOffering"]
    ]
    return {
        "academic": graph,
        "history": history.protected(value["history"]),
        "subjects": value["subjects"],
        "task": [{k: v for k, v in r.items() if k not in ("status", "updated_at")} for r in value["task"]],
        "rows": [r for r in value["rows"] if str(r["id"]) == KEEP_ROW],
        "groups": [r for r in value["groups"] if r[0] == KEEP_ROW],
        "group_links": [r for r in value["group_links"] if str(r["teachingtaskrow_id"]) == KEEP_ROW],
        "assignments": [r for r in value["assignments"] if str(r["row_id"]) == KEEP_ROW],
    }


def validate(*, corrected=False):
    offerings = {
        str(o.pk): o
        for o in model("registrar.CourseOffering")
        .objects.select_for_update()
        .filter(pk__in=(EMPTY, FILLED), organization_id=ORG)
    }
    if set(offerings) != {EMPTY, FILLED}:
        raise DuplicateError("fixed_offerings_missing")
    for oid, subject, active in (
        (EMPTY, OLD if corrected else NEW, not corrected),
        (FILLED, NEW if corrected else OLD, True),
    ):
        o = offerings[oid]
        if (
            str(o.subject_id),
            str(o.group_id),
            str(o.period_id),
            o.instructor_id,
            o.lesson_hours,
            o.is_active,
            o.is_intensive,
        ) != (subject, GROUP, PERIOD, TEACHER, 45, active, False):
            raise DuplicateError("fixed_offering_identity_changed")
    if (
        model("registrar.CourseOffering")
        .objects.filter(organization_id=ORG, group_id=GROUP, period_id=PERIOD, subject_id__in=(OLD, NEW))
        .exclude(pk__in=(EMPTY, FILLED))
        .exists()
    ):
        raise DuplicateError("third_offering_collision")
    if dict(
        model("registrar.Subject").objects.filter(organization_id=ORG, pk__in=(OLD, NEW)).values_list("id", "code")
    ) != {
        offerings[EMPTY].subject_id: "QKU-1797" if corrected else "QKU-45",
        offerings[FILLED].subject_id: "QKU-45" if corrected else "QKU-1797",
    }:
        raise DuplicateError("fixed_subject_codes_changed")
    rows = {
        str(r.pk): r
        for r in model("workload.TeachingTaskRow")
        .objects.select_for_update()
        .filter(organization_id=ORG, pk__in=(KEEP_ROW, REMOVE_ROW))
    }
    if set(rows) != ({KEEP_ROW} if corrected else {KEEP_ROW, REMOVE_ROW}):
        raise DuplicateError("fixed_workload_row_set_changed")
    if (
        model("workload.TeachingTaskRow")
        .objects.filter(organization_id=ORG, period_id=PERIOD, subject_id__in=(OLD, NEW), groups__pk=GROUP)
        .exclude(pk__in=(KEEP_ROW, REMOVE_ROW))
        .exists()
    ):
        raise DuplicateError("third_workload_row_requires_review")
    for rid, row in rows.items():
        keep = rid == KEEP_ROW
        if (
            str(row.task_id),
            str(row.subject_id),
            str(row.period_id),
            row.season,
            row.row_kind,
            row.lecture_plan,
            row.seminar_plan,
            row.lab_plan,
            row.lecture_total,
            row.seminar_total,
            row.lab_total,
            row.total_hours,
            row.union_count,
            row.subgroup_count,
            str(row.credits),
        ) != (
            TASK,
            NEW if keep else OLD,
            PERIOD,
            "fall",
            "teaching",
            30,
            15,
            0,
            30,
            30 if keep else 15,
            0,
            60 if keep else 45,
            1,
            2 if keep else 1,
            "4",
        ):
            raise DuplicateError("fixed_official_hours_changed")
        if any(
            getattr(row, k)
            for k in (
                "consult_hours",
                "exam_hours",
                "postgrad_hours",
                "practice_production_hours",
                "practice_research_hours",
                "thesis_hours",
            )
        ):
            raise DuplicateError("unrelated_official_hours_changed")
        if set(map(str, row.groups.values_list("pk", flat=True))) != (GROUPS if keep else {GROUP}):
            raise DuplicateError("fixed_workload_groups_changed")
        if sorted(row.assignments.values_list("teacher_id", "activity", "hours", "is_hourly_paid")) != [
            (TEACHER, "lecture", 30, False),
            (TEACHER, "seminar", 30 if keep else 15, False),
        ]:
            raise DuplicateError("fixed_allocations_changed")
    if not corrected:
        common.reject_row_history(rows[REMOVE_ROW])
        history.validate_before(sys.modules[__name__])
    return offerings, rows


def cells():
    lessons = list(model("registrar.Lesson").objects.filter(offering_id=FILLED, organization_id=ORG))
    if len(lessons) != 7 or len({(lesson.date, lesson.start_time, lesson.kind) for lesson in lessons}) != 7:
        raise DuplicateError("source_seven_exact_lessons_required")
    marks = list(
        model("registrar.LessonMark")
        .objects.filter(lesson__in=lessons, organization_id=ORG)
        .select_related("lesson", "enrollment")
    )
    if len(marks) != 81 or any(str(m.enrollment.offering_id) != FILLED for m in marks):
        raise DuplicateError("source_81_exact_marks_required")
    result = [
        (
            m.lesson.date.isoformat(),
            str(m.lesson.start_time),
            m.lesson.kind,
            str(m.enrollment.student_id),
            m.status,
            str(Decimal(str(m.score)).normalize()) if m.score is not None else None,
        )
        for m in marks
    ]
    if len(set(r[:4] for r in result)) != 81:
        raise DuplicateError("ambiguous_source_mark_cells")
    return sorted(result, key=str)
