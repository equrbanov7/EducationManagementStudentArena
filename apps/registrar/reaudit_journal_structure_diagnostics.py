"""Read-only six reviewed duplicate-QB candidates; never infer which event to erase."""

import copy
from types import SimpleNamespace

from django.apps import apps
from django.db import transaction

from core.reviewed_graph import require, rows

from . import reaudit_journal_structure_spec as spec
from . import reaudit_journal_structure_state as state
from .absence_credit_read import credit_hours_map
from .lab_groups import applies


def candidate_pairs():
    registry = spec.scope()["duplicate_candidates"]
    result = [
        {
            "kind": "exact_carry",
            "mark_ids": [row["source_mark_id"], row["target_mark_id"]],
            "enrollment_ids": [row["source_enrollment_id"], row["target_enrollment_id"]],
        }
        for row in registry["carry_pairs"]
    ]
    result.extend(
        {
            "kind": "cross_offering",
            "mark_ids": [event["mark_id"] for event in row["events"]],
            "enrollment_ids": [event["enrollment_id"] for event in row["events"]],
        }
        for row in registry["cross_offering"]
    )
    return result


@transaction.atomic
def inspect(*, organization, actor):
    pairs = candidate_pairs()
    manifest = {
        "operation": "duplicate_qb",
        "target_ids": sorted({pk for pair in pairs for pk in pair["enrollment_ids"]}),
    }
    snapshot = state.capture(organization, actor, manifest)
    data = snapshot["graph"]
    enrollments = {row["id"]: row for row in data["registrar.Enrollment"]}
    lessons = {row["id"]: row for row in data["registrar.Lesson"]}
    all_marks = data["registrar.LessonMark"]
    by_id = {row["id"]: row for row in all_marks}
    credits = {str(pk): value for pk, value in credit_hours_map(list(enrollments)).items()}
    output = []
    for pair in pairs:
        marks = [by_id.get(pk) for pk in pair["mark_ids"]]
        require(all(marks), "structure_duplicate_candidate_changed")
        require(
            [row["enrollment_id"] for row in marks] == pair["enrollment_ids"], "structure_duplicate_reference_changed"
        )
        lesson_rows = [lessons[row["lesson_id"]] for row in marks]
        facts = []
        for mark, lesson in zip(marks, lesson_rows):
            enrollment = enrollments[mark["enrollment_id"]]
            changed = copy.deepcopy(all_marks)
            for candidate in changed:
                if candidate["id"] == mark["id"]:
                    candidate["status"] = "present"
            hypothetical = state.counters(enrollments, changed, lessons, credits, manifest)
            current = {row["enrollment_id"]: row["canonical_before"] for row in snapshot["preview"]}
            delta = {
                row["enrollment_id"]: row["canonical_before"]
                - current.get(row["enrollment_id"], row["canonical_before"])
                for row in hypothetical
                if row["enrollment_id"] in pair["enrollment_ids"]
            }
            facts.append(
                {
                    "mark_id": mark["id"],
                    "lesson_id": lesson["id"],
                    "enrollment_id": enrollment["id"],
                    "status": mark["status"],
                    "numeric_value_present": mark["score"] is not None,
                    "lesson_applies_to_enrollment_mask": applies(
                        SimpleNamespace(**lesson), SimpleNamespace(**enrollment)
                    ),
                    "lab_group": lesson["lab_group"],
                    "seminar_group": lesson["seminar_group"],
                    "enrollment_lab_group": enrollment["lab_group"],
                    "enrollment_seminar_group": enrollment["seminar_group"],
                    "target_credit_hours": credits.get(enrollment["id"], 0),
                    "hypothetical_effect_if_this_mark_not_absent": delta,
                }
            )
        bridge = rows(
            apps.get_model("legacy_import.LegacyEntityMap").objects.filter(
                organization=organization, target_pk__in=pair["mark_ids"], target_model_label="registrar.lessonmark"
            )
        )
        output.append(
            {
                **pair,
                "event_equal_fields": [
                    key
                    for key in ("date", "start_time", "end_time", "kind", "hours", "instructor_id", "room_id")
                    if len({row[key] for row in lesson_rows}) == 1
                ],
                "facts": facts,
                "source_ledger_count": len(bridge),
                "authority": "distinct_event_and_teacher_source_review_required",
                "eligible_for_apply": False,
            }
        )
    return {"status": "read_only", "candidates": output, "changed": 0, "baseline": state.digest(snapshot)}
