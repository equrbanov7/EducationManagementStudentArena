"""Contact access export stays read-only, typed and scoped in both RLS modes."""

import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.registrar.models import CourseOffering, Enrollment, JournalShare, TeachingHandover
from apps.workload.services.scoped_snapshot import capture
from apps.workload.services.scoped_snapshot import repair_contact_rights as probe
from apps.workload.tests import test_scoped_snapshot as fixtures
from apps.workload.tests.factories import TEACHER_PERMS, activate_member


class ContactRightsSnapshotTests(TransactionTestCase):
    setUp = fixtures.ScopedSnapshotTests.setUp

    def prepare(self):
        self.seminar = get_user_model().objects.create_user("PRIVATE_SEMINAR_NAME")
        activate_member(self.org, self.seminar, "contact_teacher", permissions=TEACHER_PERMS)
        self.seminar.profile.organization = self.org
        self.seminar.profile.save()
        self.offering = CourseOffering.objects.create(
            organization=self.org,
            subject=self.stack["subject"],
            period=self.stack["period"],
            group=self.stack["group"],
            instructor=self.teacher,
            lesson_hours=150,
        )
        self.other = CourseOffering.objects.create(
            organization=self.org,
            subject=self.stack["subject"],
            period=self.stack["period"],
            instructor=self.teacher,
            lesson_hours=90,
        )
        student = get_user_model().objects.create_user("PRIVATE_STUDENT_NAME")
        activate_member(self.org, student, "contact_student", permissions=["grade.view"])
        student.profile.organization = self.org
        student.profile.save()
        self.enrollment = Enrollment.objects.create(organization=self.org, offering=self.offering, student=student)
        self.other_enrollment = Enrollment.objects.create(organization=self.org, offering=self.other, student=student)
        self.batch = "shares-20261027-120000-abcd"
        self.legacy = JournalShare.objects.create(
            organization=self.org,
            offering=self.offering,
            teacher=self.seminar,
            source="legacy",
            kinds=["seminar"],
            batch=self.batch,
            created_by=self.actor,
        )
        self.legacy.enrollments.add(self.enrollment)
        self.manual = JournalShare.objects.create(
            organization=self.org,
            offering=self.offering,
            teacher=self.teacher,
            source="manual",
            kinds=["lecture"],
            batch="PRIVATE_MANUAL_BATCH",
            created_by=self.actor,
        )
        self.unrelated = JournalShare.objects.create(
            organization=self.org,
            offering=self.other,
            teacher=self.seminar,
            source="legacy",
            batch=self.batch,
        )
        self.handover = TeachingHandover.objects.create(
            organization=self.org,
            offering=self.offering,
            from_instructor=self.teacher,
            to_instructor=self.seminar,
            from_instructor_name="PRIVATE_OLD_NAME",
            to_instructor_name="PRIVATE_NEW_NAME",
            reason="PRIVATE_HANDOVER_NOTE",
            performed_by=self.actor,
            reverted_at=timezone.now(),
            reverted_by=self.actor,
            revert_reason="PRIVATE_REVERT_NOTE",
        )
        self.audit = AuditLog.objects.create(
            organization=self.org,
            user=self.actor,
            action="UPDATE",
            resource_type="registrar.journal_shares_batch",
            resource_id=self.batch,
            reason="PRIVATE_AUDIT_NOTE",
            ip_address="192.0.2.123",
            user_agent="PRIVATE_CONTACT",
            new_values={
                "created": [str(self.legacy.pk), str(self.unrelated.pk)],
                "source_sha256": "a" * 64,
                "contact": "PRIVATE_JSON",
            },
        )
        self.teachers = (self.teacher.pk, self.seminar.pk)
        patcher = patch.multiple(
            probe,
            SOURCES={
                str(self.offering.pk): {
                    "case_code": "tarix_region",
                    "teacher_ids": list(self.teachers),
                    "official_source_sha256": "a" * 64,
                }
            },
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_typed_rights_sources_restrictions_provenance_and_no_writes_both_rls_modes(self):
        self.prepare()
        before = list(JournalShare.objects.order_by("pk").values())
        before_links = list(JournalShare.enrollments.through.objects.order_by("pk").values())

        def readonly(execute, sql, params, many, context):
            self.assertFalse(sql.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "ALTER", "CREATE")))
            return execute(sql, params, many, context)

        for mode in (False, True):
            with (
                self.subTest(mode=mode),
                override_settings(RLS_TRANSACTION_SCOPED=mode),
                connection.execute_wrapper(readonly),
            ):
                payload = capture(self.actor.username)
            exported = {key: value for key, value in payload["data"].items() if key.startswith("repair_contact_")}
            encoded = json.dumps(exported, cls=DjangoJSONEncoder)
            self.assertNotIn("PRIVATE", encoded)
            self.assertNotIn("192.0.2.123", encoded)
            self.assertNotIn(str(self.unrelated.pk), encoded)
            shares = {row["id"]: row for row in exported["repair_contact_shares"]}
            self.assertEqual(set(shares), {self.legacy.pk, self.manual.pk})
            self.assertEqual(shares[self.legacy.pk]["source"], "legacy")
            self.assertEqual(shares[self.manual.pk]["source"], "manual")
            self.assertEqual(shares[self.legacy.pk]["kinds"], ["seminar"])
            self.assertEqual(shares[self.legacy.pk]["enrollment_ids"], [str(self.enrollment.pk)])
            self.assertTrue(shares[self.legacy.pk]["enrollments_restricted"])
            self.assertFalse(shares[self.manual.pk]["enrollments_restricted"])
            self.assertEqual(shares[self.legacy.pk]["batch_code"], self.batch)
            self.assertIsNone(shares[self.manual.pk]["batch_code"])
            self.assertEqual(shares[self.legacy.pk]["created_by_id"], self.actor.pk)
            audit = exported["repair_contact_share_audits"][0]
            self.assertEqual(audit["created_share_ids"], [str(self.legacy.pk)])
            self.assertEqual(audit["source_sha256s"], ["a" * 64])
            self.assertEqual(audit["new_values_sha256"], probe.sha(self.audit.new_values))
            self.assertTrue(exported["repair_contact_handovers"][0]["reason_present"])
            self.assertFalse(exported["repair_contact_rights_scope"][0]["automatic_apply_authority"])
            path = Path(__file__).resolve().parents[3] / "scripts/ops/workload_contact_rights_scope.py"
            spec = importlib.util.spec_from_file_location("contact_scope", path)
            validator = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(validator)
            with patch.multiple(validator, SOURCES=probe.SOURCES):
                validator.validate(json.loads(json.dumps(payload, cls=DjangoJSONEncoder)))
        self.assertEqual(list(JournalShare.objects.order_by("pk").values()), before)
        self.assertEqual(list(JournalShare.enrollments.through.objects.order_by("pk").values()), before_links)

    def test_foreign_offering_restriction_and_budget_fail_closed(self):
        self.prepare()
        self.legacy.enrollments.add(self.other_enrollment)
        with self.assertRaisesRegex(ValueError, "foreign_enrollment"):
            capture(self.actor.username)
        self.legacy.enrollments.remove(self.other_enrollment)
        with patch.object(probe, "MAX_ROWS", 1), self.assertRaisesRegex(ValueError, "scope_budget_exceeded"):
            capture(self.actor.username)

    def test_missing_root_is_explicit_and_not_a_permission_or_absence_decision(self):
        payload = capture(self.actor.username)
        scope = payload["data"]["repair_contact_rights_scope"][0]
        self.assertEqual(scope["root_offering_ids"], [])
        self.assertFalse(scope["automatic_apply_authority"])
        self.assertEqual(payload["data"]["repair_contact_shares"], [])

    def test_multiple_selected_journals_keep_separate_restrictions_and_one_shared_batch(self):
        self.prepare()
        self.unrelated.enrollments.add(self.other_enrollment)
        sources = {**probe.SOURCES, str(self.other.pk): next(iter(probe.SOURCES.values()))}
        with patch.object(probe, "SOURCES", sources):
            payload = capture(self.actor.username)["data"]
        shares = {row["id"]: row for row in payload["repair_contact_shares"]}
        self.assertEqual(shares[self.legacy.pk]["enrollment_ids"], [str(self.enrollment.pk)])
        self.assertEqual(shares[self.unrelated.pk]["enrollment_ids"], [str(self.other_enrollment.pk)])
        self.assertEqual(len(payload["repair_contact_offerings"]), 2)
        self.assertEqual(len(payload["repair_contact_share_audits"]), 1)
        self.assertEqual(
            payload["repair_contact_share_audits"][0]["created_share_ids"],
            sorted([str(self.legacy.pk), str(self.unrelated.pk)]),
        )

    def test_missing_import_source_hash_is_not_invented_from_official_workbook_hash(self):
        self.prepare()
        record = AuditLog.objects.create(
            organization=self.org,
            user=self.actor,
            action="UPDATE",
            resource_type="registrar.JournalShare",
            resource_id=str(self.legacy.pk),
            new_values={"kinds": ["seminar"]},
        )
        payload = capture(self.actor.username)["data"]
        audit = next(row for row in payload["repair_contact_share_audits"] if row["id"] == record.pk)
        self.assertEqual(audit["source_sha256s"], [])
        self.assertEqual(audit["target_object_ids"], [str(self.legacy.pk)])
