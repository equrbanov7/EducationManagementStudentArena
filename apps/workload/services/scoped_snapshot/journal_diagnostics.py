"""Derive exact assignment/owner/share slots, not guessed student/group aliases."""

from collections import defaultdict

from django.apps import apps

from apps.registrar.public import journal_access_diagnostics

from .data import ORG


def collect_journal_diagnostics(data):
    group_links = defaultdict(set)
    for row in data["row_groups"]:
        group_links[row["id"]].add(row["groups__id"])
    assignments = defaultdict(set)
    for row in data["assignments"]:
        if row["teacher_id"]:
            assignments[row["row_id"]].add(row["teacher_id"])
    slots = defaultdict(set)
    for row in data["rows"]:
        for group in group_links[row["id"]]:
            slots[(row["subject_id"], row["period_id"], group)].update(assignments[row["id"]])
    ids = [o["id"] for o in data["offerings"]]
    shares = defaultdict(set)
    for offering, teacher in (
        apps.get_model("registrar.JournalShare")
        .objects.filter(organization_id=ORG, offering_id__in=ids, is_active=True)
        .values_list("offering_id", "teacher_id")
    ):
        shares[offering].add(teacher)
    result = []
    offerings = (
        apps.get_model("registrar.CourseOffering")
        .objects.filter(organization_id=ORG, pk__in=ids)
        .select_related("organization", "period")
        .order_by("pk")
    )
    for offering in offerings:
        teachers = set(slots[(offering.subject_id, offering.period_id, offering.group_id)]) | shares[offering.pk]
        if offering.instructor_id:
            teachers.add(offering.instructor_id)
        result.extend(journal_access_diagnostics(offering=offering, teacher_ids=teachers))
    return result
