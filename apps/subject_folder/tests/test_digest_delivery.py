"""Tenant-scoped inbox and submission-marker commits under retries and concurrent workers."""

from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from threading import Barrier
from unittest.mock import patch

from django.core.management import call_command
from django.db import connections, transaction
from django.urls import reverse

import pytest

from apps.notifications.models import InAppNotification
from apps.subject_folder import public
from apps.subject_folder.services import notify
from apps.subject_folder.tasks import send_submission_digests
from core.rls import apply_rls_request_context

from . import factories as f


def _submit(ready):
    return public.submit(task=ready.homework, assignment=ready.assignment, student=ready.students[0], text="İş")


def _digests(teacher):
    return InAppNotification.objects.filter(recipient=teacher, metadata__event="subject_folder.digest")


@pytest.mark.django_db(transaction=True)
def test_failed_inbox_insert_rolls_back_and_next_worker_delivers_once(ready):
    from apps.notifications.public import create_notification_for_users

    def fail_after_insert(**kwargs):
        create_notification_for_users(**kwargs)
        raise RuntimeError("synthetic inbox interruption")

    with patch("apps.notifications.public.create_notification_for_users", side_effect=fail_after_insert):
        submission = _submit(ready)
    submission.refresh_from_db()
    assert submission.teacher_notified_at is None and not _digests(ready.teacher).exists()
    assert send_submission_digests.run() == 1
    assert send_submission_digests.run() == 0
    submission.refresh_from_db()
    assert submission.teacher_notified_at is not None and _digests(ready.teacher).count() == 1


@pytest.mark.django_db(transaction=True)
def test_two_workers_commit_one_digest_for_one_teacher(ready):
    with patch.object(notify, "submission_received"):
        row = _submit(ready)
    barrier = Barrier(2)

    def deliver():
        try:
            barrier.wait(timeout=10)
            return notify.deliver_pending_digest(ready.org.pk, ready.teacher.pk)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = [executor.submit(deliver) for _ in range(2)]
        assert sorted(result.result(timeout=15) for result in results) == [False, True]
    row.refresh_from_db()
    assert row.teacher_notified_at and _digests(ready.teacher).count() == 1


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("defer_first", [False, True])
def test_worker_keeps_shared_teachers_titles_and_cooldowns_separate(ready, defer_first):
    other = f.make_org()
    teacher = ready.teacher
    f.activate_member(other, teacher, "teacher", permissions=["grade.input"], level=60)
    period, subject = f.make_period(other), f.make_subject(other)
    offering = f.make_offering(other, subject=subject, period=period, instructor=teacher)
    student = f.make_student(other)
    f.enroll(offering, student)
    f.approve_syllabus(offering, teacher)
    folder, _, _ = public.create_folder(
        organization=other, subject=subject, owner=teacher, by_user=teacher, period=period, auto_assign=False
    )
    assignment = public.assign_folder(folder, [offering], by_user=teacher)[0]["assignment"]
    homework = public.create_homework(folder, by_user=teacher, title="İkinci qrupun işi", is_published=True)
    with patch.object(notify, "submission_received"):
        first = _submit(ready)
        second = public.submit(task=homework, assignment=assignment, student=student, text="İş")
    if defer_first:
        original = notify.deliver_pending_digest
        affected = min([ready.org.pk, other.pk])

        def defer_one(org, recipient, *, force=False):
            if org == affected:
                raise RuntimeError("temporary synthetic inbox outage")
            return original(org, recipient, force=force)

        with patch.object(notify, "deliver_pending_digest", side_effect=defer_one), pytest.raises(RuntimeError):
            send_submission_digests.run()
        assert _digests(teacher).count() == 1 and not _digests(teacher).filter(organization_id=affected).exists()
        assert send_submission_digests.run() == 1
    else:
        assert send_submission_digests.run() == 2
    for org, expected, row in [(ready.org, ready.homework.title, first), (other, homework.title, second)]:
        with transaction.atomic():
            apply_rls_request_context(user_id=teacher.pk, org_id=org.pk, local=True)
            digest = _digests(teacher).get(organization_id=org.pk)
            assert digest.message == f"{expected} — 1"
            assert digest.link.startswith(reverse("organizations:switch", kwargs={"slug": org.slug}) + "?")
            row.refresh_from_db()
            assert row.teacher_notified_at
    assert send_submission_digests.run() == 0


@pytest.mark.django_db(transaction=True)
def test_digest_management_command_counts_and_forces_scoped_work(ready):
    _submit(ready)
    with patch.object(notify, "submission_received"):
        row = public.submit(
            task=ready.homework, assignment=ready.assignment, student=ready.students[1], text="İkinci təqdimat"
        )
    for options, expected in [([], 0), (["--apply"], 0), (["--apply", "--force"], 1)]:
        output = StringIO()
        call_command("subject_folder_digest", *options, stdout=output)
        assert output.getvalue().strip().endswith(f"göndərilən xülasə: {expected}")
    row.refresh_from_db()
    assert row.teacher_notified_at and _digests(ready.teacher).count() == 2
