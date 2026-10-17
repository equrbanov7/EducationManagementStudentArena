"""``dedupe_notifications`` — təkrar «Dərs yükü təyin edildi» bildirişlərini oxunmuş edir (sahib 2026-10-17)."""

from __future__ import annotations

from datetime import timedelta
from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase
from django.utils import timezone

from apps.notifications.models import InAppNotification, NotificationType
from apps.organizations.models import Organization

User = get_user_model()
TITLE = "Dərs yükü təyin edildi: Torpaq kadastrı — 60 saat"
BODY = "2026/2027 tədris ili üçün dərs yükünüz təsdiqləndi."
LINK = "/accounts/profile/?section=my-workload"


class DedupeNotificationsCommandTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("dd_owner", "dd_owner@x.test", "pw")
        self.org = Organization.objects.create(name="Dedupe Org", slug="dd-org", owner=self.owner)
        self.other_org = Organization.objects.create(name="Other Org", slug="dd-other", owner=self.owner)
        self.alice = User.objects.create_user("dd_alice", "dd_alice@x.test", "pw")
        self.bob = User.objects.create_user("dd_bob", "dd_bob@x.test", "pw")
        self.now = timezone.now()

    def _note(self, user, *, minutes_ago=0, title=TITLE, message=BODY, kind=NotificationType.ASSIGNMENT, **extra):
        note = InAppNotification.objects.create(
            recipient=user,
            organization=extra.pop("organization", self.org),
            title=title,
            message=message,
            link=LINK,
            notification_type=kind,
            metadata=extra.pop("metadata", {"event": "workload_assigned", "task_id": "t1"}),
            **extra,
        )
        InAppNotification.objects.filter(pk=note.pk).update(created_at=self.now - timedelta(minutes=minutes_ago))
        return note

    def _run(self, *extra):
        out = StringIO()
        since = (timezone.localdate() - timedelta(days=1)).isoformat()
        call_command(
            "dedupe_notifications", "--org", self.org.slug, "--type", "assignment", "--since", since, *extra, stdout=out
        )
        return out.getvalue()

    def _unread(self):
        return set(InAppNotification.objects.filter(is_read=False).values_list("pk", flat=True))

    def test_dry_run_writes_nothing(self):
        first, second = self._note(self.alice, minutes_ago=10), self._note(self.alice, minutes_ago=5)
        out = self._run()
        self.assertIn("DRY-RUN", out)
        self.assertIn("groups=1 · duplicates_marked_read=1 · users=1", out)
        self.assertEqual(self._unread(), {first.pk, second.pk})

    def test_apply_marks_only_duplicates_and_keeps_earliest(self):
        keep = self._note(self.alice, minutes_ago=30)
        dup = self._note(self.alice, minutes_ago=20)
        dup2 = self._note(self.alice, minutes_ago=1)
        bob_keep = self._note(self.bob, minutes_ago=30)
        bob_dup = self._note(self.bob, minutes_ago=29)
        other_body = self._note(self.alice, minutes_ago=15, message="Başqa mətn")
        other_title = self._note(self.alice, minutes_ago=15, title="Dərs yükü təyin edildi: Meşəçilik — 30 saat")
        other_type = self._note(self.alice, minutes_ago=15, kind=NotificationType.SYSTEM)
        other_task = self._note(self.alice, minutes_ago=15, metadata={"event": "workload_assigned", "task_id": "t2"})
        other_org = self._note(self.alice, minutes_ago=15, organization=self.other_org)
        old_read = self._note(self.bob, minutes_ago=40, is_read=True, read_at=self.now)
        far = self._note(self.bob, minutes_ago=30 + 24 * 60)  # pəncərədən kənar (dünən) — ayrı hadisə

        out = self._run("--apply")
        self.assertIn("APPLY", out)
        self.assertIn("groups=2 · duplicates_marked_read=3 · users=2", out)
        self.assertNotIn("dd_alice", out)
        unread = self._unread()
        self.assertTrue({dup.pk, dup2.pk, bob_dup.pk}.isdisjoint(unread))
        expected = {keep, bob_keep, other_body, other_title, other_type, other_task, other_org, far}
        self.assertTrue({note.pk for note in expected} <= unread)
        old_read.refresh_from_db()
        self.assertTrue(old_read.is_read)
        dup.refresh_from_db()
        self.assertIsNotNone(dup.read_at)
        self.assertIsNone(dup.deleted_at)
        self.assertEqual(InAppNotification.objects.count(), 12)  # heç nə silinmir

        self.assertIn("groups=0 · duplicates_marked_read=0 · users=0", self._run("--apply"))  # idempotent

    def test_window_and_until_bound_the_scan(self):
        self._note(self.alice, minutes_ago=200)
        self._note(self.alice, minutes_ago=10)
        self.assertIn("duplicates_marked_read=0", self._run("--window-minutes", "120"))
        self.assertIn("duplicates_marked_read=1", self._run("--window-minutes", "240"))
        until = (timezone.localdate() - timedelta(days=1)).isoformat()
        self.assertIn("duplicates_marked_read=0", self._run("--window-minutes", "240", "--until", until))

    def test_bad_arguments_raise(self):
        with self.assertRaises(CommandError):
            call_command("dedupe_notifications", "--org", "yoxdur", "--type", "assignment", "--since", "2026-10-17")
        with self.assertRaises(CommandError):
            self._run("--until", "2020-01-01")
        with self.assertRaises(CommandError):
            call_command("dedupe_notifications", "--org", self.org.slug, "--type", "assignment", "--since", "17.10")
