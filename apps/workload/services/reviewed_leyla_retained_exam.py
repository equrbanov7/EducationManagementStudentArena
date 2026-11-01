"""One retained Exam92 association, never an exam relink or score projection.

The caller locks the complete graph and its existing before/after/undo protected
hashes cover every retained exam, attempt, answer and association. Only these two
source-pinned through rows may coexist with a workload-only catalog correction.
"""

from . import reviewed_leyla_catalog_spec as spec
from .reviewed_leyla_catalog_graph import require

PIN = {
    "exam_id": 92,
    "organization_id": "526cfa63-4f80-4bba-a7a7-61c8fbb3d918",
    "author_id": 8302,
    "subject_id": "b7e2b8b9-6de9-459b-b505-97cee35a9461",
    "links": {64: "670324f8-13e4-4011-854a-0f873e30bf38", 65: "bad814fd-a7a5-4e24-8722-6e0d33e9ee13"},
    "pairs": {
        "670324f8-13e4-4011-854a-0f873e30bf38": "07cbecc2-6f7e-4207-adb6-53932d960d57",
        "bad814fd-a7a5-4e24-8722-6e0d33e9ee13": "c52bc071-f4de-468a-8fd4-56e51d55dde0",
    },
}
LABEL = "exams.Exam_journal_offerings"


def allowed_reference(label, row, graph):
    if label != LABEL or row.get("id") not in PIN["links"]:
        return False
    expected = [
        {"id": pk, "exam_id": PIN["exam_id"], "courseoffering_id": offering}
        for pk, offering in sorted(PIN["links"].items())
    ]
    require(row in expected, "leyla_retained_exam_reference_changed")
    linked = [r for r in graph.get(LABEL, []) if r["exam_id"] == PIN["exam_id"]]
    require(sorted(linked, key=lambda r: r["id"]) == expected, "leyla_retained_exam_exact_links_required")
    exams = [r for r in graph.get("exams.Exam", []) if r["id"] == PIN["exam_id"]]
    require(
        len(exams) == 1
        and all(exams[0][key] == PIN[key] for key in ("organization_id", "author_id", "subject_id"))
        and spec.ORG == PIN["organization_id"]
        and spec.TEACHER == PIN["author_id"],
        "leyla_retained_exam_identity_changed",
    )
    offerings = {r["id"]: r for r in graph.get("registrar.CourseOffering", [])}
    enrollments = graph.get("registrar.Enrollment", [])
    candidates = {}
    for named, canonical in PIN["pairs"].items():
        require(spec.PAIRS.get(named) == canonical, "leyla_retained_exam_catalog_pair_changed")
        a, b = offerings[named], offerings[canonical]
        require(
            a["organization_id"] == b["organization_id"] == spec.ORG
            and a["group_id"] == b["group_id"]
            and a["period_id"] == b["period_id"] == spec.PERIOD
            and a["instructor_id"] == b["instructor_id"] == spec.TEACHER
            and a["subject_id"] == PIN["subject_id"] != b["subject_id"],
            "leyla_retained_exam_course_identity_changed",
        )
        active = {}
        for oid in (named, canonical):
            rows = [r for r in enrollments if r["offering_id"] == oid and r["status"] == "enrolled"]
            require(
                all(r["organization_id"] == spec.ORG and r["superseded_by_id"] is None for r in rows)
                and len({r["student_id"] for r in rows}) == len(rows),
                "leyla_retained_exam_roster_identity_changed",
            )
            active[oid] = {r["student_id"] for r in rows}
        require(active[named] == active[canonical], "leyla_retained_exam_pair_students_changed")
        for uid in active[canonical]:
            require(uid not in candidates, "leyla_retained_exam_student_target_ambiguous")
            candidates[uid] = canonical
    real = [
        r
        for r in graph.get("exams.ExamAttempt", [])
        if r["exam_id"] == PIN["exam_id"] and not r["is_trial"] and r["status"] in ("submitted", "expired")
    ]
    require(real and all(r["user_id"] in candidates for r in real), "leyla_retained_exam_attempt_student_unmatched")
    return True
