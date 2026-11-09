"""Existing rows may differ only by the reviewed restoration and absence projection."""

from .manifest import require


def assert_preserved(before, after, planned):
    restored = {row["before"]["id"] for row in planned["restorations"]}
    counters = {row["enrollment_id"] for row in planned["marks"] if row["status"] == "absent"}
    counters.update(
        row["before"]["enrollment_id"] for row in planned["restorations"] if row["before"]["status"] == "absent"
    )
    for table, rows in before.items():
        current = {row["id"]: row for row in after[table]}
        for row in rows:
            require(row["id"] in current, "protected_existing_row_removed")
            other = current[row["id"]]
            changed = {key for key in row if row[key] != other.get(key)}
            allowed = set()
            if table == "marks" and row["id"] in restored:
                allowed = {"score", "status", "updated_at"}
            if table == "enrollments" and row["id"] in counters:
                allowed = {"absence_hours", "updated_at"}
            require(changed <= allowed, "protected_existing_row_changed")
