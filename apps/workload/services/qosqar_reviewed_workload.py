"""One preserved zero-load choice block; no generic alternate-row exemption."""

from . import qosqar_duplicate_state as common

ZERO_CHOICE_ROW = "e2ed0137-c68e-4c8f-ba1c-437565990724"
RETIRING_ASSIGNMENTS = {"005e01da-7983-48c1-9c5f-3cdae4682055", "bd83bf34-d06f-4e97-b748-4816a84f3a08"}


def validate_retiring_assignments(row):
    if set(map(str, row.assignments.values_list("pk", flat=True))) != RETIRING_ASSIGNMENTS:
        raise common.DuplicateError("reviewed_retiring_assignment_ids_changed")


def validate_alternates(query, *, group):
    rows = list(query.select_for_update())
    if not rows:
        return
    if len(rows) != 1 or str(rows[0].pk) != ZERO_CHOICE_ROW:
        raise common.DuplicateError("alternate_workload_requires_review")
    row = rows[0]
    expected = {
        "organization_id": common.ORG,
        "task_id": common.TASK,
        "period_id": common.PERIOD,
        "subject_id": common.DUPLICATE_SUBJECT,
        "subject_text": "ATMF XII blok: \n1.Kompüterlərdə modelləşdirmə\n2. Avtomatlar nəzəriyyəsi",
        "groups_text": "233 İT",
        "row_kind": "teaching",
        "season": "fall",
        "degree_level": "bachelor",
        "education_form": "eyani",
        "credits": "7",
        "student_count": 17,
        "lecture_plan": 45,
        "seminar_plan": 45,
        "lab_plan": 0,
        "union_count": 0,
        "subgroup_count": 0,
    }
    zero = (
        "lecture_total seminar_total lab_total total_hours consult_hours exam_hours "
        "postgrad_hours practice_production_hours practice_research_hours thesis_hours"
    ).split()
    if (
        any(str(getattr(row, key)) != str(value) for key, value in expected.items())
        or any(getattr(row, key) != 0 for key in zero)
        or set(map(str, row.groups.values_list("pk", flat=True))) != {group}
        or row.assignments.exists()
    ):
        raise common.DuplicateError("reviewed_zero_choice_workload_changed")
