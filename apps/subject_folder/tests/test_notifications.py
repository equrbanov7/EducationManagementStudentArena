"""Bildirişlər TOPLU gedir: təyinat/dərc — bir bulk insert; baxış nəticələri qrup üzrə; müəllimə xülasə (digest)."""

from __future__ import annotations

import pytest

from apps.notifications.models import InAppNotification
from apps.subject_folder import public

from . import factories as f

pytestmark = pytest.mark.django_db


@pytest.fixture
def spy(monkeypatch):
    import apps.notifications.public as notifications_public

    calls = []
    original = notifications_public.create_notification_for_users

    def _spy(**kwargs):
        calls.append(kwargs)
        return original(**kwargs)

    monkeypatch.setattr(notifications_public, "create_notification_for_users", _spy)
    return calls


def test_assignment_notifies_audience_in_one_bulk(world, folder, spy, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        public.assign_folder(folder, [world.offering], by_user=world.teacher)
    (call,) = spy
    assert sorted(user.pk for user in call["recipients"]) == sorted(user.pk for user in world.students)
    assert call["metadata"]["event"] == "subject_folder.assigned"
    assert "section=my-subject-folders" in call["link"] and f"sf_folder={folder.pk}" in call["link"]
    assert InAppNotification.objects.filter(recipient__in=world.students).count() == 3


def test_publishing_task_notifies_once_and_draft_folder_is_silent(ready, spy, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        homework = public.create_homework(ready.folder, by_user=ready.teacher, title="Yeni ev işi", is_published=True)
    (call,) = spy
    assert len(call["recipients"]) == 3 and call["title"].endswith("Yeni ev işi")
    spy.clear()
    public.set_folder_status(ready.folder, by_user=ready.teacher, status="draft")
    with django_capture_on_commit_callbacks(execute=True):
        public.set_task_published(homework, by_user=ready.teacher, published=False)
        public.set_task_published(homework, by_user=ready.teacher, published=True)
    assert spy == []


def test_review_outcomes_are_grouped(ready, spy, django_capture_on_commit_callbacks):
    rows = [
        public.submit(task=ready.slot1, assignment=ready.assignment, student=student, text="iş")
        for student in ready.students
    ]
    spy.clear()
    with django_capture_on_commit_callbacks(execute=True):
        public.bulk_review(
            rows,
            by_user=ready.teacher,
            action="accept",
            points={str(rows[0].pk): "5", str(rows[1].pk): "5", str(rows[2].pk): "3"},
        )
    grouped = [call for call in spy if call["metadata"]["event"] == "subject_folder.accepted"]
    assert sorted(len(call["recipients"]) for call in grouped) == [1, 2]
    assert any("Bal: 5 / 5" in call["message"] for call in grouped)
    spy.clear()
    other = public.submit(task=ready.homework, assignment=ready.assignment, student=ready.students[0], text="ev")
    with django_capture_on_commit_callbacks(execute=True):
        public.return_for_revision(other, by_user=ready.teacher, feedback="Daha ətraflı yazın")
    returned = [call for call in spy if call["metadata"]["event"] == "subject_folder.returned"]
    assert len(returned) == 1 and returned[0]["recipients"] == [ready.students[0]]


def test_teacher_gets_a_digest_not_one_message_per_submission(ready, django_capture_on_commit_callbacks):
    first, *others = ready.students
    with django_capture_on_commit_callbacks(execute=True):
        public.submit(task=ready.slot1, assignment=ready.assignment, student=first, text="iş")
    digests = InAppNotification.objects.filter(recipient=ready.teacher, metadata__event="subject_folder.digest")
    assert digests.count() == 1  # ilk göndəriş dərhal xəbər verilir
    for student in others:
        with django_capture_on_commit_callbacks(execute=True):
            public.submit(task=ready.slot1, assignment=ready.assignment, student=student, text="iş")
    assert digests.count() == 1  # interval daxilində yeni bildiriş YOX — gözləyənlər toplanır
    from apps.subject_folder.services.notify import send_submission_digests

    with django_capture_on_commit_callbacks(execute=True):
        assert send_submission_digests(force=True) == 1
    latest = digests.order_by("-id").first()
    assert digests.count() == 2 and latest.title.endswith(": 2")
    with django_capture_on_commit_callbacks(execute=True):
        assert send_submission_digests(force=True) == 0  # hamısı artıq xəbərdar edilib


def test_digest_goes_to_the_current_instructor(ready, django_capture_on_commit_callbacks):
    successor = f.make_teacher(ready.org)
    ready.offering.instructor = successor
    ready.offering.save(update_fields=["instructor"])
    with django_capture_on_commit_callbacks(execute=True):
        public.submit(task=ready.slot1, assignment=ready.assignment, student=ready.students[0], text="iş")
    assert InAppNotification.objects.filter(recipient=successor, metadata__event="subject_folder.digest").exists()
    assert not InAppNotification.objects.filter(
        recipient=ready.teacher, metadata__event="subject_folder.digest"
    ).exists()
