"""Prefetch edilmiş yük təyinatlarından exact qrup üzrə növ payları (əlavə assignment SELECT yoxdur)."""

import re
from collections import defaultdict

from apps.registrar.public import sync_workload_journal_shares

from .offering_rules import owner_for_rows, plan_reached_chair

KINDS = {"lecture", "seminar", "lab"}
SHARE_COUNTER_KEYS = tuple(
    f"shares_{key}" for key in ("created", "updated", "deactivated", "preserved", "skipped", "ambiguous")
)


def _assignment_group(assignment, row, group):
    """True/False=exact fiziki qrup qeydi; None=strukturlaşdırılmamış yarımqrup mətni."""
    note = (assignment.groups_note or "").strip()
    if not note:
        return True

    def normalize(value):
        return re.sub(r"\s+", "", str(value or "")).casefold()

    known = {}
    for candidate in row.groups.all():
        for label in (candidate.name, candidate.code):
            if label:
                known.setdefault(normalize(label), set()).add(candidate.pk)
    parts = [normalize(part) for part in re.split(r"[,;+\n]+", note) if part.strip()]
    if not parts or any(part not in known or len(known[part]) != 1 for part in parts):
        return None
    return any(group.pk in known[part] for part in parts)


def plan_for_rows(rows, *, group, owner_rows=None):
    teachers, activity_owners = defaultdict(set), defaultdict(set)
    unclear_group = False
    for row in rows:
        if not plan_reached_chair(row.task):
            continue
        for assignment in row.assignments.all():
            if assignment.teacher_id and assignment.activity in KINDS and assignment.hours > 0:
                applies = _assignment_group(assignment, row, group)
                unclear_group |= applies is None
                if applies is not True:
                    continue
                teachers[assignment.teacher_id].add(assignment.activity)
                activity_owners[assignment.activity].add(assignment.teacher_id)
    return {
        "owner_id": getattr(owner_for_rows(rows if owner_rows is None else owner_rows), "pk", None),
        "teachers": teachers,
        "ambiguous": unclear_group or any(len(owners) > 1 for owners in activity_owners.values()),
    }


def sync_target_shares(*, organization_id, targets, foreign_rows, offering_ids, by_user, request, counters):
    plans = {}
    for key, entry in targets.items():
        plans[key] = plan_for_rows(
            entry["rows"] + foreign_rows.get(key, []), group=entry["group"], owner_rows=entry["rows"]
        )
    report = sync_workload_journal_shares(
        organization_id=organization_id, offering_ids=offering_ids, plans=plans, by_user=by_user, request=request
    )
    counters.update({f"shares_{key}": value for key, value in report.items()})
