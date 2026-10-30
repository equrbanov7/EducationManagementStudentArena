"""Explicit current-load evidence for journal presentation fixtures (no sync side effects)."""

from apps.organizations.models import OrgUnit
from apps.workload.constants import TaskStatus
from apps.workload.models import TeacherAssignment, TeachingTask, TeachingTaskRow


def seed_current_journal_load(offering, *, teacher=None, kinds=("lecture",)):
    """Give a fixture's already-authorized instructor/share holder a real positive load.

    This does not assign owners, grant shares, alter the subject's chair, create
    lessons, or change the roster: those remain the responsibility of each test.
    """
    teacher = teacher or offering.instructor
    if teacher is None or offering.group_id is None:
        raise ValueError("Use an explicit physical-group offering and assigned teacher")
    chair, _ = OrgUnit.objects.get_or_create(
        organization=offering.organization,
        slug="journal-presentation-fixture-chair",
        defaults={"name": "Journal presentation fixture chair", "unit_type": "chair"},
    )
    task, _ = TeachingTask.objects.get_or_create(
        organization=offering.organization,
        chair=chair,
        academic_year=offering.period.academic_year,
        defaults={"status": TaskStatus.AMENDED},
    )
    row = TeachingTaskRow.objects.filter(
        task=task, period=offering.period, subject=offering.subject, groups=offering.group
    ).first()
    if row is None:
        row = TeachingTaskRow.objects.create(
            organization=offering.organization,
            task=task,
            period=offering.period,
            subject=offering.subject,
        )
        row.groups.add(offering.group)
    for kind in kinds:
        setattr(row, f"{kind}_plan", 30)
        setattr(row, f"{kind}_total", 30)
    row.total_hours = row.computed_total_hours
    row.save()
    for kind in kinds:
        TeacherAssignment.objects.get_or_create(
            organization=offering.organization,
            row=row,
            teacher=teacher,
            activity=kind,
            defaults={"hours": 30},
        )
    return row
