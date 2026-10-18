"""``merge_subjects`` / ``undo_subject_merge`` idarə əmrləri — default dry-run (2026-10-19)."""

from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError

from apps.audit.models import AuditLog
from apps.registrar.models import CourseOffering, Subject
from apps.registrar.subject_merge import AUDIT_RESOURCE, AUDIT_UNDO_RESOURCE
from core.rls import bypass_rls

from .subject_merge_fixture import REASON, SubjectMergeBase


class MergeCommandTest(SubjectMergeBase):
    def _run(self, name, *args):
        out = StringIO()
        call_command(name, *args, stdout=out)
        return out.getvalue()

    def test_dry_run_by_default_then_apply_then_undo(self):
        offering = self.offering(self.source, self.group1)
        output = self._run("merge_subjects", "--org", self.org.slug, "--target", "QA-SM-T", "--source", "QA-SM-S")
        self.assertIn("DRY-RUN", output)
        self.assertFalse(Subject.objects.get(pk=self.source.pk).is_archived)

        output = self._run(
            "merge_subjects",
            "--org",
            self.org.slug,
            "--target",
            "QA-SM-T",
            "--source",
            "QA-SM-S",
            "--apply",
            "--reason",
            REASON,
        )
        self.assertIn("Birləşdirildi", output)
        entry = AuditLog.objects.get(resource_type=AUDIT_RESOURCE)
        self.assertIsNone(entry.user_id)
        with bypass_rls():
            self.assertEqual(CourseOffering.objects.get(pk=offering.pk).subject_id, self.target.pk)

        output = self._run("undo_subject_merge", "--audit-id", str(entry.pk))
        self.assertIn("DRY-RUN", output)
        self.assertTrue(Subject.objects.get(pk=self.source.pk).is_archived)
        self._run("undo_subject_merge", "--audit-id", str(entry.pk), "--apply", "--reason", REASON)
        self.assertFalse(Subject.objects.get(pk=self.source.pk).is_archived)
        with bypass_rls():
            self.assertEqual(CourseOffering.objects.get(pk=offering.pk).subject_id, self.source.pk)
        self.assertTrue(AuditLog.objects.filter(resource_type=AUDIT_UNDO_RESOURCE, resource_id=str(entry.pk)).exists())
        with self.assertRaises(CommandError):
            self._run("undo_subject_merge", "--audit-id", str(entry.pk))

    def test_apply_requires_reason_and_conflicts_fail(self):
        with self.assertRaises(CommandError):
            self._run("merge_subjects", "--org", self.org.slug, "--target", "QA-SM-T", "--source", "QA-SM-S", "--apply")
        self.offering(self.source, self.group1)
        self.offering(self.target, self.group1)
        with self.assertRaises(CommandError):
            self._run("merge_subjects", "--org", self.org.slug, "--target", "QA-SM-T", "--source", "QA-SM-S")
        with self.assertRaises(CommandError):
            self._run("merge_subjects", "--org", self.org.slug, "--target", "QA-SM-T", "--source", "YOX-KOD")
