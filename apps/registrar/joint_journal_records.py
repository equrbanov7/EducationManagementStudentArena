"""Read-only common session counts, with authorship and physical history separate.

Exactly one full matching session per member forms a common recorded session.
NULL authors remain unknown; matching headers never create teacher attribution.
"""

from collections import defaultdict

from django.db.models import Q
from django.utils import timezone

from .models import Lesson

FIELDS = ("date", "start_time", "end_time", "kind", "topic", "hours", "instructor_id", "room_id")


def summaries(joints, user):
    joints = list(joints)
    if not joints:
        return {}
    ids = set().union(*(joint.offering_ids for joint in joints))
    organizations = {offering.organization_id for joint in joints for offering in joint.offerings}
    lessons = defaultdict(list)
    for row in (
        Lesson.objects.filter(organization_id__in=organizations, offering_id__in=ids, date__lte=timezone.localdate())
        .filter(Q(instructor=user) | Q(instructor__isnull=True))
        .values("id", "offering_id", *FIELDS)
    ):
        lessons[row["offering_id"], row["kind"]].append(row)
    result = {}
    for joint in joints:
        sessions = defaultdict(lambda: defaultdict(list))
        for offering in joint.offerings:
            for row in lessons[offering.pk, joint.kind]:
                signature = tuple(row[field] for field in FIELDS)
                sessions[signature][offering.pk].append(row)
        common = {
            signature: rows
            for signature, rows in sessions.items()
            if set(rows) == joint.offering_ids and all(len(values) == 1 for values in rows.values())
        }
        matched = {row["id"] for rows in common.values() for values in rows.values() for row in values}
        owned = {
            signature: rows for signature, rows in common.items() if signature[FIELDS.index("instructor_id")] == user.pk
        }
        history = []
        for offering in joint.offerings:
            unmatched = [
                row
                for row in lessons[offering.pk, joint.kind]
                if row["instructor_id"] == user.pk and row["id"] not in matched
            ]
            anonymous = [
                row
                for row in lessons[offering.pk, joint.kind]
                if row["instructor_id"] is None and row["id"] not in matched
            ]
            history.append(
                {
                    "group": offering.group,
                    "anonymous_lessons": len(anonymous),
                    "anonymous_hours": sum(row["hours"] for row in anonymous),
                    "separate_own_lessons": len(unmatched),
                    "separate_own_hours": sum(row["hours"] for row in unmatched),
                }
            )
        result[joint.source_row_id, joint.kind] = {
            "common_lessons": len(common),
            "common_hours": sum(signature[FIELDS.index("hours")] for signature in common),
            "own_lessons": len(owned),
            "own_hours": sum(signature[FIELDS.index("hours")] for signature in owned),
            "history": [row for row in history if row["anonymous_lessons"] or row["separate_own_lessons"]],
        }
    return result


def attach(entries, user):
    grouped = defaultdict(list)
    for entry in entries:
        if getattr(entry, "joint_selection", None):
            grouped[getattr(entry, "joint_observed_teacher", None) or user].append(entry)
    records = {
        teacher: summaries([entry.joint_selection for entry in rows], teacher) for teacher, rows in grouped.items()
    }
    for entry in entries:
        joint = getattr(entry, "joint_selection", None)
        if joint:
            teacher = getattr(entry, "joint_observed_teacher", None) or user
            record = records[teacher][joint.source_row_id, joint.kind]
            entry.journal_common_lessons = record["common_lessons"]
            entry.journal_common_hours = record["common_hours"]
            entry.journal_own_lessons = record["own_lessons"]
            entry.journal_own_hours = record["own_hours"]
            entry.joint_history_records = record["history"]
