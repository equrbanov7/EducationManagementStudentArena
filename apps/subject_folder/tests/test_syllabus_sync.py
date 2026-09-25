"""Sillabus → qovluq strukturu: mövzular + sərbəst iş slotları (1x10 / 2x5 / 10x1), idempotent sinxron."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.subject_folder import public
from apps.subject_folder.models import FolderMaterial, FolderTask, Submission

from . import factories as f

pytestmark = pytest.mark.django_db


def _slots(folder):
    return list(folder.tasks.filter(kind="selfwork", is_archived=False).order_by("slot_index"))


@pytest.mark.parametrize(
    ("option", "count", "per_score"),
    [("1x10", 1, Decimal("10")), ("2x5", 2, Decimal("5")), ("10x1", 10, Decimal("1"))],
)
def test_selfwork_slots_follow_syllabus_option(option, count, per_score):
    org = f.make_org()
    teacher = f.make_teacher(org)
    offering = f.make_offering(org, subject=f.make_subject(org), period=f.make_period(org), instructor=teacher)
    f.approve_syllabus(offering, teacher, option=option)
    folder, created, summary = public.create_folder(
        organization=org, subject=offering.subject, owner=teacher, by_user=teacher, period=offering.period
    )
    slots = _slots(folder)
    assert created and summary["has_syllabus"]
    assert summary["selfwork"]["option"] == option
    assert [task.slot_index for task in slots] == list(range(1, count + 1))
    assert {task.max_points for task in slots} == {per_score}
    assert sum(task.max_points for task in slots) == Decimal("10")
    assert all(not task.is_published for task in slots)  # müəllim doldurub dərc edir
    assert folder.selfwork_option == option


def test_topics_come_from_approved_week_plan(world, folder):
    topics = list(folder.topics.order_by("order"))
    assert [topic.title for topic in topics] == f.WEEK_TITLES
    assert [topic.week_no for topic in topics] == [1, 2, 3, 4]
    assert all(topic.source == "syllabus" and topic.syllabus_uid for topic in topics)
    assert folder.syllabus_ref == world.version.pk
    assert [task.title for task in _slots(folder)] == ["Sərbəst iş mövzusu 1", "Sərbəst iş mövzusu 2"]


def test_resync_is_idempotent(world, folder):
    summary = public.resync_folder(folder, by_user=world.teacher)
    assert summary["topics"]["created"] == 0 and summary["selfwork"]["created"] == []
    assert folder.topics.count() == 4
    assert folder.tasks.filter(kind="selfwork").count() == 2


def test_draft_syllabus_is_never_used():
    org = f.make_org()
    teacher = f.make_teacher(org)
    offering = f.make_offering(org, subject=f.make_subject(org), period=f.make_period(org), instructor=teacher)
    f.approve_syllabus(offering, teacher, option="2x5", status="draft")
    folder, _created, summary = public.create_folder(
        organization=org, subject=offering.subject, owner=teacher, by_user=teacher, period=offering.period
    )
    assert summary["has_syllabus"] is False
    assert folder.topics.count() == 0 and folder.tasks.count() == 0


def test_teacher_renamed_title_survives_resync(world, folder):
    topic = folder.topics.order_by("order").first()
    public.update_topic(topic, by_user=world.teacher, title="Mənim adım")
    slot = _slots(folder)[0]
    public.update_task(slot, by_user=world.teacher, title="Sərbəst iş: öz başlığım", instructions="Təlimat")
    f.approve_syllabus(world.offering, world.teacher, option="2x5", self_titles=["Yeni ad 1", "Yeni ad 2"])
    public.resync_folder(folder, by_user=world.teacher)
    topic.refresh_from_db()
    slot.refresh_from_db()
    assert topic.title == "Mənim adım"
    assert slot.title == "Sərbəst iş: öz başlığım" and slot.syllabus_title == "Yeni ad 1"
    assert _slots(folder)[1].title == "Yeni ad 2"  # dəyişdirilməmiş slot sillabusu izləyir


def test_typo_fix_in_syllabus_keeps_topic_and_materials(world, folder):
    topic = folder.topics.get(title="Rekursiya")
    material = public.create_material(
        folder, by_user=world.teacher, kind="link", title="Video", url="https://example.com/v", topic=topic
    )
    titles = list(f.WEEK_TITLES)
    titles[2] = "Rekursiyaa"  # yazı səhvi düzəlişi / kiçik dəyişiklik
    f.approve_syllabus(world.offering, world.teacher, option="2x5", week_titles=titles)
    summary = public.resync_folder(folder, by_user=world.teacher)
    material.refresh_from_db()
    assert summary["topics"]["created"] == 0
    assert material.topic_id == topic.pk
    topic.refresh_from_db()
    assert topic.title == "Rekursiyaa" and not topic.is_archived


def test_removed_topic_with_material_is_archived_empty_one_deleted(world, folder):
    keep = folder.topics.get(title="Rekursiya")
    FolderMaterial.objects.create(
        organization=world.org, folder=folder, topic=keep, kind="note", title="Qeyd", description="mətn"
    )
    f.approve_syllabus(world.offering, world.teacher, option="2x5", week_titles=f.WEEK_TITLES[:2])
    summary = public.resync_folder(folder, by_user=world.teacher)
    keep.refresh_from_db()
    assert keep.is_archived
    assert summary["topics"] == {"created": 0, "updated": 2, "restored": 0, "archived": 1, "deleted": 1}
    # Mövzu sillabusa qayıdanda eyni sətir bərpa olunur.
    f.approve_syllabus(world.offering, world.teacher, option="2x5", week_titles=f.WEEK_TITLES)
    summary = public.resync_folder(folder, by_user=world.teacher)
    keep.refresh_from_db()
    assert not keep.is_archived and summary["topics"]["restored"] == 1


def test_option_change_archives_slots_with_submissions_and_never_deletes_them(world, folder, ready):
    slot2 = ready.slots[1]
    public.submit(task=slot2, assignment=ready.assignment, student=world.students[0], text="cavab mətni")
    f.approve_syllabus(world.offering, world.teacher, option="1x10")
    summary = public.resync_folder(folder, by_user=world.teacher)
    assert summary["selfwork"]["option"] == "1x10"
    assert summary["selfwork"]["archived"] == [2]
    slot2.refresh_from_db()
    assert slot2.is_archived and not slot2.is_published
    assert Submission.objects.filter(task=slot2).count() == 1  # data qalır
    slots = _slots(folder)
    assert [(task.slot_index, task.max_points) for task in slots] == [(1, Decimal("10"))]


def test_changed_max_points_with_submissions_creates_replacement_keeping_lineage(world, folder, ready):
    slot1 = ready.slot1
    public.submit(task=slot1, assignment=ready.assignment, student=world.students[0], text="cavab")
    f.approve_syllabus(world.offering, world.teacher, option="1x10")
    public.resync_folder(folder, by_user=world.teacher)
    slot1.refresh_from_db()
    replacement = _slots(folder)[0]
    assert slot1.is_archived and replacement.pk != slot1.pk
    assert replacement.lineage_key == slot1.lineage_key and replacement.max_points == Decimal("10")


def test_selfwork_cannot_be_created_manually(world, folder):
    with pytest.raises(public.FolderError) as exc:
        public.create_task(folder, by_user=world.teacher, kind="selfwork", title="Əlavə sərbəst iş")
    assert exc.value.code == "task.selfwork_slots_fixed"
    homework = public.create_task(folder, by_user=world.teacher, kind="homework", title="Ev")
    assert homework.kind == "homework" and homework.slot_index is None and homework.max_points is None
    assert FolderTask.objects.filter(folder=folder, kind="homework").count() == 1


def test_create_folder_is_idempotent_and_requires_teaching(world, folder):
    again, created, _summary = public.create_folder(
        organization=world.org, subject=world.subject, owner=world.teacher, by_user=world.teacher, period=world.period
    )
    assert again.pk == folder.pk and created is False
    stranger = f.make_teacher(world.org)
    with pytest.raises(public.FolderError) as exc:
        public.create_folder(
            organization=world.org, subject=world.subject, owner=stranger, by_user=stranger, period=world.period
        )
    assert exc.value.code == "folder.not_teaching_subject"
    with pytest.raises(public.FolderError) as exc:
        public.create_folder(
            organization=world.org, subject=world.subject, owner=stranger, by_user=world.teacher, period=world.period
        )
    assert exc.value.code == "permission.denied"


def test_clone_to_next_period_copies_content_not_submissions(world, folder, ready):
    material = public.create_material(
        folder,
        by_user=world.teacher,
        kind="file",
        title="Slayd",
        file=__import__("apps.subject_folder.tests.conftest", fromlist=["upload"]).upload(
            "slayd.pdf", b"%PDF-1.4 slayd", "application/pdf"
        ),
        is_published=True,
    )
    public.update_task(ready.slot1, by_user=world.teacher, instructions="Esse yazın")
    next_period = f.make_period(world.org, year="2027/2028", start="2027-09-01", end="2028-01-31", current=False)
    target, info = public.clone_folder(folder, by_user=world.teacher, period=next_period)
    assert info["created"] and info["materials"] == 1 and info["homework"] == 1
    copied = target.materials.get()
    assert copied.file.name != material.file.name and copied.sha256 == material.sha256
    assert target.tasks.filter(kind="selfwork", instructions="Esse yazın").exists()
    assert not Submission.objects.filter(task__folder=target).exists()
    assert target.assignments.count() == 0 and target.source_folder_id == folder.pk
