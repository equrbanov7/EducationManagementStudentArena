"""DB invariantları: bir yekun/zəncir, bal aralığı, «0 yazılmır», cəm ≤ 10 trigger-i, append-only tarixçə."""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import DatabaseError, IntegrityError, connection, transaction

import pytest

from apps.subject_folder import constants, public
from apps.subject_folder.models import FolderAssignment, FolderTask, SimilarityMatch, Submission, SubmissionEvent

pytestmark = pytest.mark.django_db


def _row(ready, **overrides):
    values = {
        "organization": ready.org,
        "task": ready.slot1,
        "assignment": ready.assignment,
        "enrollment": ready.enrollments[0],
        "student": ready.students[0],
        "kind": "selfwork",
        "status": "submitted",
        "attempt_no": 1,
        "is_current": True,
    }
    values.update(overrides)
    return Submission(**values)


def _violates(obj_or_callable):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            obj_or_callable.save() if hasattr(obj_or_callable, "save") else obj_or_callable()


def test_policy_constant_matches_syllabus():
    from apps.syllabus.public import SELFWORK_TOTAL_SCORE

    assert constants.SELFWORK_TOTAL_CAP == SELFWORK_TOTAL_SCORE == 10


def test_one_current_attempt_and_unique_attempt_numbers(ready):
    _row(ready).save()
    _violates(_row(ready, attempt_no=2))  # ikinci CARİ cəhd
    _violates(_row(ready, is_current=False))  # eyni attempt_no


def test_one_final_row_per_chain(ready):
    _row(ready, status="accepted", points=Decimal("3"), points_max=Decimal("5"), is_current=False).save()
    _violates(_row(ready, attempt_no=2, status="rejected", feedback="x"))


@pytest.mark.parametrize(
    "overrides",
    [
        {"status": "returned", "points": Decimal("0.5"), "points_max": Decimal("5")},  # qaytarma bal yazmır
        {"status": "accepted", "points": Decimal("6"), "points_max": Decimal("5")},  # slot maksimumundan çox
        {"status": "accepted", "points": Decimal("0"), "points_max": Decimal("5")},  # 0 bal yoxdur
        {"status": "accepted", "points": None, "points_max": Decimal("5")},  # qəbul balsız ola bilməz
        {"status": "accepted", "kind": "homework", "points": Decimal("1"), "points_max": Decimal("5")},
        {"status": "checked"},  # «yoxlanıldı» yalnız ev tapşırığı
        {"status": "accepted", "points": Decimal("10"), "points_max": Decimal("11")},  # maksimum 10
    ],
)
def test_points_shape_constraints(ready, overrides):
    _violates(_row(ready, **overrides))


def test_total_cap_trigger_blocks_writes_outside_the_service(ready, folder):
    if connection.vendor != "postgresql":
        pytest.skip("trigger yalnız PostgreSQL-də")
    first = _row(ready, status="accepted", points=Decimal("5"), points_max=Decimal("5"))
    first.save()
    extra = FolderTask.objects.create(
        organization=ready.org,
        folder=folder,
        kind="selfwork",
        title="x",
        slot_index=7,
        max_points=Decimal("8"),
        is_archived=True,
    )
    _violates(_row(ready, task=extra, status="accepted", points=Decimal("6"), points_max=Decimal("8")))
    ok = _row(ready, task=extra, status="accepted", points=Decimal("5"), points_max=Decimal("8"))
    ok.save()
    _violates(lambda: Submission.objects.filter(pk=ok.pk).update(points=Decimal("5.5")))


def test_task_shape_and_single_active_slot(ready, folder):
    _violates(FolderTask(organization=ready.org, folder=folder, kind="selfwork", title="x", max_points=Decimal("5")))
    _violates(FolderTask(organization=ready.org, folder=folder, kind="homework", title="x", max_points=Decimal("1")))
    _violates(
        FolderTask(
            organization=ready.org, folder=folder, kind="selfwork", title="dup", slot_index=1, max_points=Decimal("5")
        )
    )
    FolderTask.objects.create(
        organization=ready.org,
        folder=folder,
        kind="selfwork",
        title="arxiv",
        slot_index=1,
        max_points=Decimal("5"),
        is_archived=True,
    )


def test_one_selfwork_grader_per_offering(ready):
    from . import factories as f

    other_teacher = f.make_teacher(ready.org)
    f.add_lesson(ready.offering, other_teacher)
    other_folder, _c, _s = public.create_folder(
        organization=ready.org, subject=ready.subject, owner=other_teacher, by_user=other_teacher, period=ready.period
    )
    result = public.assign_folder(other_folder, [ready.offering], by_user=other_teacher)
    assert result[0]["assignment"].grades_selfwork is False
    assert result[0]["warnings"][0]["code"] == "assignment.selfwork_elsewhere"
    _violates(lambda: FolderAssignment.objects.filter(pk=result[0]["assignment"].pk).update(grades_selfwork=True))


def test_events_are_append_only(ready):
    submission = public.submit(task=ready.slot1, assignment=ready.assignment, student=ready.students[0], text="mətn")
    event = submission.events.get()
    event.payload = {"forged": True}
    with pytest.raises(ValidationError):
        event.save()
    with pytest.raises(ValidationError):
        event.delete()
    if connection.vendor == "postgresql":
        with pytest.raises(DatabaseError, match="append-only"):
            with transaction.atomic():
                SubmissionEvent.objects.filter(pk=event.pk).update(kind="accepted")


def test_similarity_pair_is_canonical_and_unique(ready):
    one = public.submit(task=ready.slot1, assignment=ready.assignment, student=ready.students[0], text="a b c")
    two = public.submit(task=ready.slot1, assignment=ready.assignment, student=ready.students[1], text="a b c")
    low, high = sorted([one, two], key=lambda row: row.pk)
    _violates(
        SimilarityMatch(
            organization=ready.org, submission_a=high, submission_b=low, score=Decimal("0.9"), method="exact"
        )
    )
    SimilarityMatch.objects.create(
        organization=ready.org, submission_a=low, submission_b=high, score=Decimal("0.9"), method="exact"
    )
    _violates(
        SimilarityMatch(
            organization=ready.org, submission_a=low, submission_b=high, score=Decimal("0.5"), method="exact"
        )
    )


def test_deadline_range_constraint(ready):
    from django.utils import timezone

    from apps.subject_folder.models import TaskDeadline

    now = timezone.now()
    _violates(
        TaskDeadline(organization=ready.org, assignment=ready.assignment, task=ready.slot1, opens_at=now, due_at=now)
    )
