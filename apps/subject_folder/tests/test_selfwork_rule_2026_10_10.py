"""Sahib 2026-10-10: sərbəst iş ləğv olunan dövrdə (2026/2027+, RİM tənzimləməsi söndürülü — defolt)
fənn qovluğunda sərbəst iş YOXDUR: slot yaradılmır, mövcud slotlar heç kimə göstərilmir, dərc/göndəriş/
qəbul edilmir, «Yeni sərbəst iş» bildirişi getmir, jurnal sinxronu onları götürmür. Data toxunulmur —
tənzimləmə yandırılanda hamısı geri qayıdır; köhnə (2025/2026) semestr əvvəlki kimidir.
"""

from __future__ import annotations

import pytest

from apps.notifications.models import InAppNotification
from apps.subject_folder import public
from apps.subject_folder.errors import FolderError
from apps.subject_folder.services import journal, notify

from . import factories as f

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def selfwork_rule(settings):
    """``conftest``-dəki eyni adlı fixture-u əvəzləyir: burada DEFOLT (yeni) qayda — sərbəst iş söndürülüb."""
    settings.ACADEMIC_SELFWORK_ENABLED = False


def _selfwork(folder):
    return list(folder.tasks.filter(kind="selfwork").order_by("slot_index"))


def _announced(students) -> int:
    return InAppNotification.objects.filter(recipient__in=students, title__startswith="Yeni sərbəst iş").count()


def _create(world):
    folder, created, summary = public.create_folder(
        organization=world.org, subject=world.subject, owner=world.teacher, by_user=world.teacher, period=world.period
    )
    assert created
    return folder, summary


@pytest.fixture
def legacy_ready(world, settings, django_capture_on_commit_callbacks):
    """Tənzimləmə YANILI ikən qurulmuş qovluq (slotlar dərc olunub) — sonra RİM onu söndürür."""
    settings.ACADEMIC_SELFWORK_ENABLED = True
    folder, _summary = _create(world)
    with django_capture_on_commit_callbacks(execute=True):
        assignment = public.assign_folder(folder, [world.offering], by_user=world.teacher)[0]["assignment"]
        for task in _selfwork(folder):
            public.set_task_published(task, by_user=world.teacher, published=True)
        homework = public.create_homework(folder, by_user=world.teacher, title="Ev tapşırığı 1", is_published=True)
    settings.ACADEMIC_SELFWORK_ENABLED = False
    folder.refresh_from_db()
    return folder, assignment, homework


def test_new_period_folder_gets_topics_but_no_selfwork_slots(world):
    folder, summary = _create(world)
    assert _selfwork(folder) == []
    assert summary["selfwork"]["disabled"] is True
    assert folder.topics.count() == len(f.WEEK_TITLES)  # mövzular sillabusdan gəlir


def test_resync_after_the_toggle_brings_the_slots_back(world, settings):
    folder, _summary = _create(world)
    settings.ACADEMIC_SELFWORK_ENABLED = True
    summary = public.resync_folder(folder, by_user=world.teacher)
    assert [task.slot_index for task in _selfwork(folder)] == [1, 2]
    assert len(summary["selfwork"]["created"]) == 2


def test_legacy_period_keeps_selfwork_slots():
    org = f.make_org()
    teacher = f.make_teacher(org)
    period = f.make_period(org, year="2025/2026", start="2025-09-01", end="2026-01-31")
    offering = f.make_offering(org, subject=f.make_subject(org), period=period, instructor=teacher)
    f.approve_syllabus(offering, teacher, option="2x5")
    folder, created, summary = public.create_folder(
        organization=org, subject=offering.subject, owner=teacher, by_user=teacher, period=period
    )
    assert created and not summary["selfwork"].get("disabled")
    assert [task.slot_index for task in _selfwork(folder)] == [1, 2]


def test_existing_slots_are_hidden_not_deleted(world, legacy_ready):
    folder, _assignment, homework = legacy_ready
    slots = _selfwork(folder)
    assert len(slots) == 2 and all(task.is_published for task in slots)  # data yerindədir
    (entry,) = public.student_folders(organization=world.org, student=world.students[0])
    assert entry["selfwork_active"] is False
    assert [row["task"].pk for row in entry["tasks"]] == [homework.pk]
    contents = public.folder_contents(folder, actor=world.teacher)
    assert contents["selfwork_active"] is False
    shown = [task.kind for task in contents["general"]["tasks"]]
    shown += [task.kind for row in contents["topics"] for task in row["tasks"]]
    assert "selfwork" not in shown and "homework" in shown


def test_hidden_slot_cannot_be_published_submitted_or_announced(
    world, legacy_ready, django_capture_on_commit_callbacks
):
    folder, assignment, homework = legacy_ready
    slot = _selfwork(folder)[0]
    before = _announced(world.students)
    with pytest.raises(FolderError) as excinfo:
        public.submit(task=slot, assignment=assignment, student=world.students[0], text="iş")
    assert excinfo.value.code == "selfwork.disabled"
    public.set_task_published(slot, by_user=world.teacher, published=False)
    with pytest.raises(FolderError) as excinfo:
        public.set_task_published(slot, by_user=world.teacher, published=True)
    assert excinfo.value.code == "selfwork.disabled"
    with django_capture_on_commit_callbacks(execute=True):
        notify.task_published(slot)  # birbaşa çağırış da «Yeni sərbəst iş» göndərmir
    assert _announced(world.students) == before
    public.submit(task=homework, assignment=assignment, student=world.students[0], text="ev işi")  # ev işi qalır


def test_accepted_selfwork_of_an_inactive_period_is_not_synced(world, legacy_ready, settings):
    folder, assignment, _homework = legacy_ready
    slot = _selfwork(folder)[0]
    settings.ACADEMIC_SELFWORK_ENABLED = True
    submission = public.submit(task=slot, assignment=assignment, student=world.students[0], text="iş")
    submission = public.accept(submission, by_user=world.teacher, points="5")
    assert journal.is_syncable(submission)
    assert journal.retry_pending(organization_id=world.org.pk, apply=False)["candidates"] == 1
    settings.ACADEMIC_SELFWORK_ENABLED = False
    assert not journal.is_syncable(submission)
    assert journal.retry_pending(organization_id=world.org.pk, apply=False)["candidates"] == 0
    submission.refresh_from_db()
    assert submission.points == 5 and submission.status == "accepted"  # bal və status toxunulmur
