"""Two sealed owner-present decisions; original legacy QB evidence remains immutable."""

import datetime as dt
import hashlib
import json
import re

from django.apps import apps
from django.db.models import Q

from core.reviewed_graph import require, rows

from . import reaudit_journal_structure_spec as spec
from .reaudit_cells.ledger import effective_maps
from .reaudit_cells.source_rows import minute
from .reaudit_cells.source_rows import rows as source_rows

OPERATION = "owner_present_conflict"
POLICY = "owner-present-for-exact-legacy-target-conflict-20261109"
PIN_FIELDS = {
    "id",
    "organization_id",
    "lesson_id",
    "enrollment_id",
    "status",
    "score",
    "entered_by_id",
    "created_at",
    "updated_at",
}


def authority(raw, manifest):
    require(
        isinstance(raw, bytes)
        and 0 < len(raw) <= spec.MAX_BYTES
        and hashlib.sha256(raw).hexdigest() == spec.CONFLICT_AUTHORITY_SHA == manifest["authority_sha256"],
        "structure_conflict_authority",
    )
    value = json.loads(raw)
    require(
        set(value)
        == {
            "format",
            "organization_id",
            "period_id",
            "source_system",
            "source_sha256",
            "decision_policy",
            "source",
            "cases",
        }
        and value["format"] == "reaudit-owner-present-conflict/1"
        and value["organization_id"] == spec.ORG
        and value["period_id"] == spec.PERIOD
        and value["source_system"] == "myedu_mariadb"
        and value["decision_policy"] == POLICY
        and isinstance(value["source_sha256"], str)
        and re.fullmatch(r"[a-f0-9]{64}", value["source_sha256"]),
        "structure_conflict_authority",
    )
    cases = value["cases"]
    require(
        isinstance(cases, list)
        and len(cases) == 2
        and all(
            set(c)
            == {
                "source_mark_id",
                "source_enrollment_id",
                "target_enrollment_id",
                "source_legacy_point_id",
                "target_legacy_point_id",
                "source_mark_pin",
                "target_counter_before",
                "target_counter_after",
            }
            for c in cases
        )
        and {c["source_mark_id"] for c in cases} == set(manifest["target_ids"])
        and len({c["source_enrollment_id"] for c in cases}) == 2
        and len({c["target_enrollment_id"] for c in cases}) == 2
        and all(set(c["source_mark_pin"]) == PIN_FIELDS for c in cases),
        "structure_conflict_authority",
    )
    require(
        all(
            type(c[k]) is int and 0 <= c[k] <= 100000
            for c in cases
            for k in ("target_counter_before", "target_counter_after")
        ),
        "structure_conflict_authority",
    )
    return value


def capture_maps(courses, family):
    """Complete base/version chains in both directions, including quarantined remaps."""
    targets = {str(r.student_id) for r in family}
    for c in courses:
        targets.update(str(x) for x in (c.subject_id, c.group_id, c.instructor_id) if x is not None)
    base = apps.get_model("legacy_import.LegacyEntityMap")
    versions = apps.get_model("legacy_import.LegacyEntityMapVersion")
    roots = versions.objects.filter(organization_id=spec.ORG, target_pk__in=targets).values("entity_map_id")
    maps = rows(
        base.objects.filter(organization_id=spec.ORG).filter(Q(target_pk__in=targets) | Q(pk__in=roots)), limit=1000
    )
    revisions = rows(
        versions.objects.filter(organization_id=spec.ORG, entity_map_id__in=[r["id"] for r in maps]), limit=1000
    )
    require(len(maps) + len(revisions) <= 1000, "structure_conflict_map_budget")
    typed = Q(pk__in=[])
    for course in courses:
        typed |= Q(subject_id=course.subject_id, group_id=course.group_id, instructor_id=course.instructor_id)
    candidates = rows(
        apps.get_model("registrar.CourseOffering").objects.filter(
            typed, organization_id=spec.ORG, period_id=spec.PERIOD
        ),
        limit=100,
    )
    return {"conflict_maps": maps, "conflict_map_versions": revisions, "conflict_typed_courses": candidates}


def _pin(row):
    result = {k: row[k] for k in PIN_FIELDS}
    # The reviewed bounded exporter uses Django's millisecond datetime codec.
    # The fresh locked baseline still binds full SQL columns and microseconds.
    for key in ("created_at", "updated_at"):
        result[key] = (
            dt.datetime.fromisoformat(str(result[key]).replace("Z", "+00:00"))
            .astimezone(dt.timezone.utc)
            .isoformat(timespec="milliseconds")
        )
    return result


def _array(value):
    value = json.loads(value) if isinstance(value, str) else value
    require(isinstance(value, list) and all(str(v).isdigit() for v in value), "structure_conflict_source")
    return {str(v) for v in value}


def validate(snapshot, manifest, proof, actor, organization):
    """All checks run after authoritative full graph locks; no source/grade writer."""
    from apps.organizations.public import guard_self_conflict

    data = snapshot["graph"]
    courses = {r["id"]: r for r in data["registrar.CourseOffering"]}
    enrollments = {r["id"]: r for r in data["registrar.Enrollment"]}
    lessons = {r["id"]: r for r in data["registrar.Lesson"]}
    marks = {r["id"]: r for r in data["registrar.LessonMark"]}
    period = snapshot["extra"]["period"][0]
    preview = {r["enrollment_id"]: r for r in snapshot["preview"]}
    source = proof["source"]
    require(set(source) == {"journals", "points", "excuse_windows"}, "structure_conflict_source")
    normalized = {r["id"]: r for r in source_rows(source)}
    require(
        len(normalized) == 4 and len(source["points"]) == 4 and len(source["journals"]) == 2,
        "structure_conflict_source",
    )
    headers = {r["uniqid"]: r for r in source["journals"]}
    require(len(headers) == 2, "structure_conflict_source")
    mapping = {}
    for r in effective_maps(snapshot["extra"]["conflict_maps"], snapshot["extra"]["conflict_map_versions"]):
        if r["source_system"] == proof["source_system"]:
            mapping.setdefault((r["entity_type"], r["target_model_label"], str(r["legacy_pk"])), set()).add(
                str(r["target_pk"])
            )

    def mapped(entity, label, key, expected):
        require(mapping.get((entity, label, str(key))) == {str(expected)}, "structure_conflict_mapping")

    for case in proof["cases"]:
        mark = marks.get(case["source_mark_id"])
        before = case["source_mark_pin"]
        require(mark is not None and _pin(mark) == _pin(before), "structure_conflict_mark_changed")
        require(mark["score"] is None and mark["status"] == "absent", "structure_conflict_grade_or_attendance")
        old = enrollments.get(case["source_enrollment_id"])
        target = enrollments.get(case["target_enrollment_id"])
        require(
            old is not None and target is not None and mark["enrollment_id"] == old["id"], "structure_conflict_scope"
        )
        original, current = courses[old["offering_id"]], courses[target["offering_id"]]
        require(
            old["status"] == "dropped"
            and old["superseded_by_id"] == target["id"]
            and not original["is_active"]
            and target["status"] == "enrolled"
            and target["superseded_by_id"] is None
            and current["is_active"]
            and old["student_id"] == target["student_id"]
            and original["subject_id"] == current["subject_id"]
            and original["period_id"] == current["period_id"] == spec.PERIOD,
            "structure_conflict_scope",
        )
        forecast = preview[target["id"]]
        require(
            forecast["cached"] == case["target_counter_before"]
            and forecast["canonical_after"] == case["target_counter_after"],
            "structure_conflict_counter_forecast",
        )
        lesson = lessons[mark["lesson_id"]]
        require(lesson["offering_id"] == original["id"], "structure_conflict_scope")
        events = [normalized.get(str(case[k])) for k in ("source_legacy_point_id", "target_legacy_point_id")]
        require(
            all(events) and events[0].get("status") == "absent" and events[1].get("status") == "present",
            "structure_conflict_source",
        )
        for event, course in zip(events, (original, current)):
            require(
                sum(
                    all(r[k] == course[k] for k in ("subject_id", "group_id", "instructor_id", "period_id"))
                    for r in snapshot["extra"]["conflict_typed_courses"]
                )
                == 1,
                "structure_conflict_mapping",
            )
            require(
                event["kind"] == "attendance"
                and event["score"] is None
                and event["certain"]
                and (event["source_date"], event["source_time"], event["source_kind"])
                == (lesson["date"], minute(lesson["start_time"]), lesson["kind"])
                and period["start_date"] <= event["source_date"] <= period["end_date"],
                "structure_conflict_source",
            )
            header = headers.get(event["legacy_journal_uniqid"])
            require(
                header is not None
                and header["active"] == 1
                and not header["fake"]
                and not header["sonra_sil"]
                and header["semestr"] == 14,
                "structure_conflict_source",
            )
            require(event["legacy_student_id"] in _array(header["students_id"]), "structure_conflict_source")
            mapped("student", "auth.user", event["legacy_student_id"], old["student_id"])
            mapped("worker", "auth.user", header["teacher_id"], course["instructor_id"])
            mapped("lesson_subject", "registrar.subject", header["lesson_id"], course["subject_id"])
            require(
                any(
                    mapping.get(("group_unit", "organizations.orgunit", gid)) == {course["group_id"]}
                    for gid in _array(header["groups_id"])
                ),
                "structure_conflict_mapping",
            )
            guard_self_conflict(
                actor,
                organization,
                action="registrar.journal_correction",
                offering_id=course["id"],
                group_id=course["group_id"],
                student_id=old["student_id"],
            )
        matches = [
            r
            for r in lessons.values()
            if r["offering_id"] == current["id"]
            and (r["date"], minute(r["start_time"]), r["kind"])
            == (lesson["date"], minute(lesson["start_time"]), lesson["kind"])
        ]
        require(len(matches) <= 1, "structure_conflict_target_changed")
        for m in marks.values():
            if matches and m["enrollment_id"] == target["id"] and m["lesson_id"] == matches[0]["id"]:
                require(m["status"] == "present" and m["score"] is None, "structure_conflict_target_changed")
        require(
            not any(
                r.get("lesson_mark_ref") == mark["id"] or r.get("lesson_mark_id") == mark["id"]
                for r in data.get("registrar.JournalCorrection", [])
            ),
            "structure_conflict_formal_history",
        )


def apply(organization, actor, manifest, proof):
    from .correction_target_locks import lock_grade_for_apply
    from .corrections import apply_correction
    from .models import LessonMark

    result = []
    for case in sorted(proof["cases"], key=lambda r: r["source_mark_id"]):
        mark = LessonMark.objects.get(organization=organization, pk=case["source_mark_id"])
        mark, _lesson, _enrollment = lock_grade_for_apply(mark, expected_empty=False)
        require(mark.score is None and mark.status == "absent", "structure_conflict_grade_or_attendance")
        correction = apply_correction(
            mark=mark,
            field="attendance",
            new_status="present",
            reason="technical",
            document=None,
            by_user=actor,
            note="Sahibin dəqiq hadisə üzrə iştirak qərarı; hədəf legacy jurnalında PRESENT sübutu. Authority SHA256 "
            + manifest["authority_sha256"]
            + "; dəyişməz original legacy mənbə SHA256 "
            + proof["source_sha256"],
            audit_reason="reviewed_owner_present_conflict",
        )
        result.append(str(correction.pk))
    return result


def postcheck(before, after, manifest, correction_ids, reversal_ids, actor, *, undo):
    require(len(correction_ids) == len(set(correction_ids)) == 2, "structure_conflict_postcondition")
    marks = {r["id"]: r for r in after["graph"]["registrar.LessonMark"]}
    require(
        all(
            marks[pk]["status"] == ("absent" if undo else "present") and marks[pk]["score"] is None
            for pk in manifest["target_ids"]
        ),
        "structure_conflict_postcondition",
    )
    require(
        all(
            r["cached"] == r["canonical_before"]
            for r in after["preview"]
            if r["enrollment_id"] in after["affected_ids"]
        ),
        "structure_conflict_postcondition",
    )
    corrections = {
        r["id"]: r for r in after["graph"].get("registrar.JournalCorrection", []) if r["id"] in correction_ids
    }
    require(
        set(corrections) == set(correction_ids)
        and {r["lesson_mark_id"] for r in corrections.values()} == set(manifest["target_ids"])
        and all(
            r["field"] == "attendance"
            and r["old_status"] == "absent"
            and r["new_status"] == "present"
            and r["old_score"] is None
            and r["new_score"] is None
            for r in corrections.values()
        ),
        "structure_conflict_postcondition",
    )
    if undo:
        original = {
            r["id"]: r for r in before["graph"].get("registrar.JournalCorrection", []) if r["id"] in correction_ids
        }
        require(original == corrections, "structure_conflict_postcondition")
        reversed_rows = [r for r in after["graph"].get("registrar.CorrectionReversal", []) if r["id"] in reversal_ids]
        require(
            len(reversed_rows) == 2 and {r["journal_correction_id"] for r in reversed_rows} == set(correction_ids),
            "structure_conflict_postcondition",
        )
    else:
        require(
            all(r["corrected_by_id"] == actor.pk for r in corrections.values()) and not reversal_ids,
            "structure_conflict_postcondition",
        )
