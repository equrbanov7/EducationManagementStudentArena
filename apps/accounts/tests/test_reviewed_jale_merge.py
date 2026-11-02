"""PostgreSQL merge: conservative holds, atomic preservation, recoverable alias."""

from contextlib import ExitStack
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.accounts.services import reviewed_jale_merge as service
from apps.workload.tests.factories import TEACHER_PERMS, activate_member, make_org, make_structure


class ReviewedJaleMergeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("jale-merge")
        cls.actor = cls.org.owner
        cls.actor.is_superuser = True
        cls.actor.save(update_fields=["is_superuser"])
        apps.get_model("accounts.UserProfile").objects.filter(user=cls.actor).update(organization=cls.org)
        cls.alias = get_user_model().objects.create_user("jale-alias", first_name="Jalə", last_name="Qəniyeva")
        cls.main = get_user_model().objects.create_user("jale-main", first_name="Jalə", last_name="Qəniyeva")
        for user in (cls.alias, cls.main):
            activate_member(cls.org, user, "teacher", permissions=TEACHER_PERMS)
            apps.get_model("accounts.UserProfile").objects.filter(user=user).update(organization=cls.org)
        structure = make_structure(cls.org, code="JM")
        cls.course = apps.get_model("registrar.CourseOffering").objects.create(
            organization=cls.org,
            instructor=cls.main,
            subject=structure["subject"],
            group=structure["group"],
            period=structure["period"],
        )
        cls.share = apps.get_model("registrar.JournalShare").objects.create(
            organization=cls.org, offering=cls.course, teacher=cls.alias, source="legacy"
        )
        run = apps.get_model("legacy_import.LegacyMigrationRun").objects.create(
            organization=cls.org,
            source_system="myedu_mariadb",
            snapshot_sha256="a" * 64,
            snapshot_size_bytes=1,
            schema_version="v1",
            transform_version="v1",
            mode="profile",
        )
        run.status = "running"
        from django.utils import timezone

        run.started_at = timezone.now()
        run.save(update_fields=["status", "started_at", "updated_at"])
        cls.bridge = apps.get_model("legacy_import.LegacyEntityMap").objects.create(
            organization=cls.org,
            source_system="myedu_mariadb",
            entity_type="worker",
            legacy_pk="949",
            source_row_hash="b" * 64,
            transform_version="v1",
            target_model_label="auth.user",
            target_pk=str(cls.alias.pk),
            created_run=run,
            state="migrated",
        )

    def setUp(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        for key, value in {
            "ORG": str(self.org.pk),
            "CANONICAL": self.main.pk,
            "ALIAS": self.alias.pk,
            "ACTOR": self.actor.pk,
        }.items():
            stack.enter_context(patch.object(service, key, value))

    def test_merge_moves_exact_share_retains_bridge_soft_deletes(self):
        before = service.snapshot(self.org, self.actor)
        self.assertEqual(before["holds"], [])
        result = service.execute(self.org, self.actor, before["baseline_sha256"], "Reviewed exact same person alias")
        self.assertEqual(result["soft_deleted_alias"], self.alias.pk)
        self.share.refresh_from_db()
        self.assertEqual(self.share.teacher_id, self.main.pk)
        self.assertEqual(self.share.source, "legacy")
        self.bridge.refresh_from_db()
        self.assertEqual(self.bridge.target_pk, str(self.alias.pk))
        self.alias.refresh_from_db()
        self.assertFalse(self.alias.is_active)
        self.assertTrue(self.alias.profile.is_deleted)
        self.assertEqual(self.course.instructor_id, self.main.pk)

    def test_stale_baseline_and_collision_are_atomic_holds(self):
        state = service.snapshot(self.org, self.actor)
        with self.assertRaisesRegex(service.MergeError, "stale_baseline"):
            service.execute(self.org, self.actor, "0" * 64, "Reviewed exact same person alias")
        apps.get_model("registrar.JournalShare").objects.create(
            organization=self.org, offering=self.course, teacher=self.main
        )
        state = service.snapshot(self.org, self.actor)
        self.assertTrue(any(row["reason"] == "canonical_collision" for row in state["holds"]))
        with self.assertRaisesRegex(service.MergeError, "unreviewed_reference"):
            service.execute(self.org, self.actor, state["baseline_sha256"], "Reviewed exact same person alias")
        self.share.refresh_from_db()
        self.assertEqual(self.share.teacher_id, self.alias.pk)
        self.alias.refresh_from_db()
        self.assertTrue(self.alias.is_active)

    def test_other_tenant_reference_blocks_and_notification_not_lost(self):
        other = make_org("jale-unrelated")
        notice = apps.get_model("notifications.InAppNotification").objects.create(
            organization=other, recipient=self.alias, title="Private unrelated tenant"
        )
        state = service.snapshot(self.org, self.actor)
        self.assertTrue(any(row["reason"] == "other_tenant" for row in state["holds"]))
        with self.assertRaisesRegex(service.MergeError, "unreviewed_reference"):
            service.execute(self.org, self.actor, state["baseline_sha256"], "Reviewed exact same person alias")
        notice.refresh_from_db()
        self.assertIsNone(notice.deleted_at)
        self.assertEqual(notice.recipient_id, self.alias.pk)

    def test_historical_authorship_preserved_notifications_moved(self):
        import datetime

        lesson = apps.get_model("registrar.Lesson").objects.create(
            organization=self.org,
            offering=self.course,
            instructor=self.alias,
            created_by=self.alias,
            date=datetime.date(2026, 10, 1),
            kind="seminar",
            hours=2,
            topic="Exact historical language lesson",
        )
        notice = apps.get_model("notifications.InAppNotification").objects.create(
            organization=self.org, recipient=self.alias, title="Keep existing notification"
        )
        before_lesson = list(type(lesson).objects.filter(pk=lesson.pk).values())
        state = service.snapshot(self.org, self.actor)
        self.assertEqual(state["holds"], [])
        service.execute(self.org, self.actor, state["baseline_sha256"], "Reviewed exact same person alias")
        self.assertEqual(list(type(lesson).objects.filter(pk=lesson.pk).values()), before_lesson)
        notice.refresh_from_db()
        self.assertEqual(notice.recipient_id, self.main.pk)
        self.assertIsNone(notice.deleted_at)

    def test_unapproved_auth_group_is_hold_not_transferred(self):
        group = apps.get_model("auth.Group").objects.create(name="Do not guess global privilege")
        self.alias.groups.add(group)
        state = service.snapshot(self.org, self.actor)
        self.assertTrue(any(row["reason"] == "unscoped_reference" for row in state["holds"]))
        with self.assertRaisesRegex(service.MergeError, "unreviewed_reference"):
            service.execute(self.org, self.actor, state["baseline_sha256"], "Reviewed exact same person alias")
        self.assertFalse(self.main.groups.exists())
        self.alias.refresh_from_db()
        self.assertTrue(self.alias.is_active)
