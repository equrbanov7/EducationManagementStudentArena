"""Source-cell audit: exact slots and existing enrollments; no writes or guessing."""

import datetime
import re
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .delta.lessons import CALENDAR, mark_value, winning_cells
from .delta.resolve import lesson_date
from .rehearsal_journal_lesson_kinds import cell_kind
from .reviewed_content_spec import ORG
from .reviewed_content_state import model


@dataclass
class Decision:
    counts: Counter = field(default_factory=Counter)
    lessons: dict = field(default_factory=dict)
    marks: list = field(default_factory=list)
    touched: dict = field(default_factory=dict)
    provenance: list = field(default_factory=list)


def _time(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d{2}:\d{2}(?::00(?:\.0{1,6})?)?", value):
        return None
    try:
        parsed = datetime.time.fromisoformat(value)
    except ValueError:
        return None
    if parsed.second or parsed.microsecond or parsed.tzinfo is not None:
        return None
    return parsed


def _rank(row):
    return row["update_counter"], row["updated_at"], row["id"]


def _enrollment(state, uid, family, student):
    candidates = [
        row
        for row in state.by_user[uid]
        if str(row.offering_id) in family and row.status == "enrolled" and row.superseded_by_id is None
    ]
    if len(candidates) == 1:
        return candidates[0]
    for groups in (state.active_groups[uid], state.group_maps.get(str((student or {}).get("group_id")), set())):
        exact = [row for row in candidates if state.group_of_offering[str(row.offering_id)] in groups]
        if len(exact) == 1:
            return exact[0]
    return None


def build(state):
    data, decision = state.data, Decision()
    counts = decision.counts
    selected_journals = {value["journal_uniqid"] for value in state.selected.values()}
    source_points = [row for row in data["points"] if row["journal_uniqid"] in selected_journals]
    winners = winning_cells(source_points)
    counts["source_cells"] = len(source_points)
    counts["duplicate_source_cells"] = len(source_points) - len(winners)
    special = {value["journal_uniqid"] for value in state.selected.values() if value["special"]}
    special.update(row["journal_uniqid"] for row in winners if str(row["sem_muh"]) == "3")
    counts["special_deferred_targets"] = sum(spec["journal_uniqid"] in special for spec in state.selected.values())
    journals = {row["uniqid"]: row for row in data["journals"]}
    periods = {spec["journal_uniqid"]: state.selected_offerings[pk].period for pk, spec in state.selected.items()}
    dated = set()
    for row in data["dates"]:
        uniqid = next((u for u, j in journals.items() if j["id"] == row["journal_id"]), None)
        period = periods.get(uniqid)
        if period:
            day = lesson_date(period, int(row["month"]), int(row["day"]))
            start = _time(row["time"])
            if day and start:
                dated.add((uniqid, day, start))
    natural, kinds = {}, defaultdict(set)
    for row in winners:
        uniqid = row["journal_uniqid"]
        if uniqid in special:
            counts["special_policy_deferred_cells"] += 1
            continue
        if str(row["month_id"]) not in CALENDAR:
            counts["noncalendar_cells_skipped"] += 1
            continue
        period = periods[uniqid]
        day = lesson_date(period, int(row["month_id"]), int(row["day_number"]))
        start = _time(row["time"])
        if start is None:
            counts["invalid_time_cells"] += 1
            continue
        if day is None or not period.start_date <= day <= period.end_date:
            counts["invalid_or_outside_period_cells"] += 1
            continue
        if day > data["until_date"]:
            counts["future_cells_skipped"] += 1
            continue
        kind = cell_kind(lab=int(row["lab"]), sem_muh=int(row["sem_muh"]))
        slot = (uniqid, day, start)
        kinds[slot].add(kind)
        key = slot + (row["student_id"],)
        if key not in natural or _rank(row) > _rank(natural[key]):
            natural[key] = row
        else:
            counts["normalized_duplicate_source_cells"] += 1
    windows = defaultdict(list)
    for row in data.get("excuse_windows", []):
        windows[row["student_id"]].append(
            (
                datetime.date.fromisoformat(row["allowed_date_start"]),
                datetime.date.fromisoformat(row["allowed_date_end"]),
            )
        )
    proposed = set()
    for (uniqid, day, start, sid), row in sorted(natural.items(), key=lambda value: tuple(map(str, value[0]))):
        slot = (uniqid, day, start)
        if len(kinds[slot]) != 1:
            counts["source_slot_kind_conflicts"] += 1
            continue
        kind = next(iter(kinds[slot]))
        status, score, outcome = mark_value(row["point"])
        if not status:
            counts["source_" + outcome] += 1
            continue
        if kind == "lecture" and score is not None:
            counts["scored_lecture_source_conflicts"] += 1
            continue
        if status == "absent":
            if int(row["excusable"]) == 1 or any(start <= day <= end for start, end in windows.get(sid, [])):
                status = "excused"
            elif "excuse_windows" not in data:
                counts["absence_source_policy_unattested"] += 1
                continue
        mapped = state.student_maps.get(str(sid), set())
        if len(mapped) != 1 or not next(iter(mapped)).isdigit():
            counts["student_identity_unresolved"] += 1
            continue
        uid = int(next(iter(mapped)))
        if uid not in state.tenant_students:
            counts["student_foreign_profile_rejected"] += 1
            continue
        family = state.families[uniqid]
        existing = [mark for oid in family for mark in state.marks.get((oid, day, start, uid), [])]
        if existing:
            same = all(mark.lesson.kind == kind and mark.status == status and mark.score == score for mark in existing)
            counts["existing_identical_cells" if same else "existing_conflicting_cells_kept"] += 1
            continue
        student = next((s for s in data["students"] if s["id"] == sid), None)
        enrollment = _enrollment(state, uid, family, student)
        if enrollment is None:
            candidates = [e for e in state.by_user[uid] if str(e.offering_id) in family and e.status == "enrolled"]
            counts["ambiguous_enrollment_slice" if candidates else "no_existing_target_enrollment"] += 1
            continue
        oid = str(enrollment.offering_id)
        if oid not in state.selected:
            counts["source_cell_belongs_to_unselected_family_slice"] += 1
            continue
        offering = state.selected_offerings[oid]
        if oid in state.closed or offering.period.locked_at:
            counts["locked_target_cells_skipped"] += 1
            continue
        lessons = state.lessons.get((oid, day, start), [])
        if len(lessons) > 1:
            counts["ambiguous_existing_lesson_slot"] += 1
            continue
        lesson = lessons[0] if lessons else None
        if lesson and lesson.kind != kind:
            counts["existing_lesson_kind_conflicts_kept"] += 1
            continue
        key = (oid, day, start)
        if lesson is None:
            lesson = decision.lessons.get(key)
            if lesson is None:
                pk = uuid.uuid5(uuid.UUID(ORG), f"reviewed-source:{uniqid}:{oid}:{day}:{start}:{kind}")
                lesson = model("registrar.Lesson")(
                    pk=pk,
                    organization_id=ORG,
                    offering_id=oid,
                    date=day,
                    start_time=start,
                    kind=kind,
                    hours=2,
                    instructor_id=None,
                    created_by_id=None,
                    topic="",
                    is_legacy_synthesised=slot not in dated,
                )
                decision.lessons[key] = lesson
        markkey = (lesson.pk, enrollment.pk)
        if markkey in proposed:
            counts["source_cell_collision_after_identity_mapping"] += 1
            continue
        proposed.add(markkey)
        mark = model("registrar.LessonMark")(
            pk=uuid.uuid5(uuid.UUID(ORG), f"reviewed-source-mark:{lesson.pk}:{enrollment.pk}"),
            organization_id=ORG,
            lesson=lesson,
            enrollment=enrollment,
            status=status,
            score=score,
            entered_by_id=None,
        )
        decision.marks.append(mark)
        decision.touched[str(enrollment.pk)] = enrollment
        decision.provenance.append(
            {
                "mark_id": str(mark.pk),
                "source_point_id": row["id"],
                "source_journal_id": journals[uniqid]["id"],
                "source_worker_id": journals[uniqid]["teacher_id"],
                "source_owner_current_user_id": state.selected[oid]["teacher_id"],
                "authorship": "unknown_in_source; existing_NULL_and_named_authors_unchanged",
            }
        )
    real_lesson_ids = {mark.lesson_id for mark in decision.marks if mark.status != "absent"}
    dropped = {lesson.pk for lesson in decision.lessons.values()} - real_lesson_ids
    if dropped:
        counts["new_absence_only_cells_skipped"] = sum(mark.lesson_id in dropped for mark in decision.marks)
        decision.marks = [mark for mark in decision.marks if mark.lesson_id not in dropped]
        decision.lessons = {key: lesson for key, lesson in decision.lessons.items() if lesson.pk not in dropped}
        kept = {str(mark.pk) for mark in decision.marks}
        decision.provenance = [row for row in decision.provenance if row["mark_id"] in kept]
        touched = {str(mark.enrollment_id) for mark in decision.marks}
        decision.touched = {pk: value for pk, value in decision.touched.items() if pk in touched}
    counts["missing_lessons"] = len(decision.lessons)
    counts["missing_marks"] = len(decision.marks)
    counts["ordinary_targets"] = sum(not spec["special"] for spec in state.selected.values())
    return decision
