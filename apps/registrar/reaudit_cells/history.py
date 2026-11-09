"""Visible journal audit entries; failure rolls the repair back with its receipt."""

from collections import defaultdict

from ..grade_audit import log_grade_changes
from .snapshot import model


def record(*, organization, actor, created, restored_before, restored_after, undo=False):
    rows = defaultdict(list)
    before = {row["id"]: row for row in restored_before}
    enrollment_ids = {row["enrollment_id"] for row in created["marks"] + created["components"] + restored_after}
    enrollments = {
        str(row.pk): row
        for row in model("Enrollment")
        .objects.filter(organization=organization, pk__in=enrollment_ids)
        .select_related("offering__subject", "offering__organization")
    }
    for key, kind, item in (("marks", "mark", "lesson_id"), ("components", "component", "component_id")):
        for row in created[key]:
            old = "—"
            new = str(row["score"]) if row.get("score") is not None else row.get("status", "—")
            if undo:
                old, new = new, old
            enrollment = enrollments[row["enrollment_id"]]
            rows[(enrollment.offering_id, kind)].append(
                {
                    "student": str(enrollment.student_id),
                    "enrollment_id": row["enrollment_id"],
                    "item": row[item],
                    "old": old,
                    "new": new,
                }
            )
    for row in restored_after:
        old = before[row["id"]]["status"]
        new = str(row["score"]) if row["score"] is not None else row["status"]
        if undo:
            old, new = new, old
        enrollment = enrollments[row["enrollment_id"]]
        rows[(enrollment.offering_id, "mark")].append(
            {
                "student": str(enrollment.student_id),
                "enrollment_id": row["enrollment_id"],
                "item": row["lesson_id"],
                "old": old,
                "new": new,
            }
        )
    offerings = {row.offering_id: row.offering for row in enrollments.values()}
    for (offering_id, kind), changes in rows.items():
        log_grade_changes(
            offering=offerings[offering_id],
            by_user=actor,
            kind=kind,
            changes=changes,
            fail_closed=True,
            reason="2026-11-09 mənbə bərpası" + (" — dəqiq receipt ilə geri qaytarıldı" if undo else ""),
        )
