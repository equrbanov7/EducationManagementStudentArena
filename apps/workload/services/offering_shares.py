"""Prefetch edilmiş yük təyinatlarından exact qrup üzrə növ payları (əlavə assignment SELECT yoxdur)."""

import re
from collections import defaultdict

from apps.registrar.public import sync_workload_journal_shares

from .offering_rules import owner_for_rows, plan_reached_chair

KINDS = {"lecture", "seminar", "lab"}
SHARE_COUNTER_KEYS = tuple(
    f"shares_{key}" for key in ("created", "updated", "deactivated", "preserved", "skipped", "ambiguous")
)


def _assignment_group(assignment, row, group, *, known_groups=None):
    """True/False=exact fiziki qrup qeydi; None=strukturlaşdırılmamış yarımqrup mətni.

    Sahib 2026-11-09: struktur bağ (``TeacherAssignment.group``) qeyddən ÜSTÜNDÜR — varsa qrup məhz odur.
    """
    group_id = getattr(assignment, "group_id", None)
    if group_id is not None:
        return group.pk == group_id
    note = (assignment.groups_note or "").strip()
    if not note:
        return True

    def normalize(value):
        return re.sub(r"\s+", "", str(value or "")).casefold()

    known = {}
    for candidate in row.groups.all() if known_groups is None else known_groups:
        for label in (candidate.name, candidate.code):
            if label:
                known.setdefault(normalize(label), set()).add(candidate.pk)
    parts = [normalize(part) for part in re.split(r"[,;+\n]+", note) if part.strip()]
    if not parts or any(part not in known or len(known[part]) != 1 for part in parts):
        return None
    return any(group.pk in known[part] for part in parts)


def plan_for_rows(rows, *, group, owner_rows=None):
    """Açılışın (qrupun) növ payları: ``teachers`` (müəllim → növlər), ``sections`` (müəllim → növ → alt qrup
    nömrələri — sahib 2026-11-09, bir jurnalda iki lab müəllimi), ``ambiguous``.

    Eyni növ iki müəllimdədirsə pay yalnız hər ikisinin AYRI alt qrupu olanda yazılır; əks halda (bölməsiz
    bölgü, tanınmayan qeyd) əvvəlki kimi «qeyri-müəyyən» — heç kimə bütün-roster girişi açılmır.
    """
    teachers, activity_owners = defaultdict(set), defaultdict(set)
    sections: dict = defaultdict(lambda: defaultdict(set))
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
                number = getattr(assignment, "sub_number", None)
                if number:
                    sections[assignment.teacher_id][assignment.activity].add(int(number))
    ambiguous = unclear_group
    for activity, owners in activity_owners.items():
        if len(owners) < 2:
            continue
        taken: set = set()
        for teacher_id in owners:
            numbers = sections[teacher_id].get(activity) or set()
            if not numbers or taken & numbers:
                ambiguous = True
                break
            taken |= numbers
    return {
        "owner_id": getattr(owner_for_rows(rows if owner_rows is None else owner_rows), "pk", None),
        "teachers": teachers,
        "sections": {
            teacher_id: {activity: sorted(numbers) for activity, numbers in kinds.items() if numbers}
            for teacher_id, kinds in sections.items()
            if any(kinds.values())
        },
        "ambiguous": ambiguous,
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
