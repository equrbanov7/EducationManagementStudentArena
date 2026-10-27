"""``merge_level_journals`` (sahib 2026-10-27) — bölünmüş səviyyə jurnalının tələbəsi müəllimin ev jurnalına qonaq kimi:
defolt dry-run, ``--apply``, idempotent, münaqişə saxlanılır, paylar, ``--undo``, stdout yalnız saylar, workflow.
"""

from __future__ import annotations

import json
import pathlib
import re
import tempfile
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.audit.models import AuditLog
from apps.registrar.level_merge import BATCH_RESOURCE
from apps.registrar.models import Enrollment, JournalShare, JournalShareSource, LessonMark
from apps.registrar.tests.level_fixture import D, LevelFixture
from core.rls import bypass_rls

WORKFLOW = pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml"
LINE_RE = re.compile(r"^level_merge: [a-z_]+=[0-9a-z_-]+( [a-z_]+=[0-9a-z_-]+)*$")


def _counts(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        if line.startswith("level_merge: ") and not line.startswith(("level_merge: mode=", "level_merge: batch=")):
            out.update(pair.split("=", 1) for pair in line[len("level_merge: ") :].split())
    return out


class LevelMergeTest(LevelFixture, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.build_levels()

    def setUp(self):
        with bypass_rls():
            self.a1 = self.lesson(self.lvl_a, D(2025, 10, 7))
            self.a2 = self.lesson(self.lvl_a, D(2025, 10, 14))
            self.b1 = self.lesson(self.lvl_b, D(2025, 10, 7))
            self.b2 = self.lesson(self.lvl_b, D(2025, 10, 14))
            self.scored = self.mark(self.b1, self.e_student, score=Decimal("8"))
            self.absent = self.mark(self.b2, self.e_student, status="absent")
            self.mark(self.b1, self.e_s3, score=Decimal("6"))
            self.t_share_a = self._share(self.lvl_a, self.t, [self.e_host])
            self.t_share_b = self._share(self.lvl_b, self.t, [self.e_student])
            self.z_share_b = self._share(self.lvl_b, self.z, [self.e_s3])
        self.plan = {
            "format": "level-merge/1",
            "period": str(self.period.pk),
            "journals": [
                {
                    "legacy_journal": 15345,
                    "teacher": self.t.pk,
                    "host": str(self.lvl_a.pk),
                    "via": "owner",
                    "moves": [{"enrollment": str(self.e_student.pk), "student": self.student.pk}],
                }
            ],
        }

    def _share(self, offering, teacher, rows):
        share = JournalShare.objects.create(
            organization=self.org, offering=offering, teacher=teacher, source=JournalShareSource.LEGACY, batch="x"
        )
        share.enrollments.set(rows)
        return share

    def _call(self, *extra, plan=None):
        args = ["--org", self.org.slug, "--actor", self.owner.username]
        if "--undo" not in extra:
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
                json.dump(plan or self.plan, handle)
            args += ["--file", handle.name]
        out = StringIO()
        call_command("merge_level_journals", *args, *extra, stdout=out)
        return out.getvalue()

    def test_dry_run_apply_idempotent_and_undo(self):
        dry = _counts(self._call())
        self.assertEqual((dry["students_moved"], dry["marks_moved"], dry["journals_merged"]), ("1", "2", "1"))
        with bypass_rls():
            self.assertFalse(Enrollment.objects.filter(student=self.student, offering=self.lvl_a).exists())
        text = self._call("--apply")
        for line in text.splitlines():
            self.assertRegex(line, LINE_RE)
        self.assertNotIn(self.student.username, text)
        batch = re.search(r"batch=(lvlmerge-\S+)", text).group(1)
        with bypass_rls():
            guest = Enrollment.objects.get(student=self.student, offering=self.lvl_a)
            self.assertEqual((guest.status, guest.source_group_id), ("enrolled", self.group2.pk))
            moved = LessonMark.objects.get(enrollment=guest, lesson=self.a1)
            self.assertEqual(moved.score, Decimal("8"))
            self.assertEqual(moved.created_at, self.scored.created_at, "redaktə pəncərəsi yenidən açılmır")
            self.assertTrue(LessonMark.objects.filter(enrollment=guest, lesson=self.a2, status="absent").exists())
            self.assertEqual(guest.absence_hours, 2)
            self.e_student.refresh_from_db()
            self.assertEqual((self.e_student.status, self.e_student.superseded_by_id), ("dropped", guest.pk))
            self.assertFalse(LessonMark.objects.filter(enrollment=self.e_student).exists())
            self.assertEqual(LessonMark.objects.filter(lesson=self.b1).count(), 1, "Z-nin tələbəsi yerində")
            # Paylar: ev sahibinin payına əlavə; mənbədə (sahibi deyil) boşalan pay söndürülür; Z-nin payı qalır.
            self.assertIn(guest.pk, set(self.t_share_a.enrollments.values_list("pk", flat=True)))
            self.t_share_b.refresh_from_db()
            self.z_share_b.refresh_from_db()
            self.assertEqual((self.t_share_b.is_active, self.z_share_b.is_active), (False, True))
            self.assertEqual(AuditLog.objects.filter(resource_type=BATCH_RESOURCE).count(), 1)
        again = _counts(self._call("--apply"))
        self.assertEqual((again["already_moved"], again.get("students_moved", "0")), ("1", "0"))
        undo = _counts(self._call("--undo", batch, "--apply"))
        self.assertEqual((undo["marks_returned"], undo["sources_restored"], undo["host_rows_deleted"]), ("2", "1", "1"))
        with bypass_rls():
            self.e_student.refresh_from_db()
            self.assertEqual((self.e_student.status, self.e_student.superseded_by_id), ("enrolled", None))
            self.assertFalse(Enrollment.objects.filter(student=self.student, offering=self.lvl_a).exists())
            back = LessonMark.objects.get(enrollment=self.e_student, lesson=self.b1)
            self.assertEqual((back.score, back.created_at), (Decimal("8"), self.scored.created_at))
            self.t_share_b.refresh_from_db()
            self.assertTrue(self.t_share_b.is_active)
            self.assertEqual(set(self.t_share_a.enrollments.values_list("pk", flat=True)), {self.e_host.pk})

    def test_unmatched_lesson_keeps_student_and_counts(self):
        with bypass_rls():
            extra = self.lesson(self.lvl_b, D(2025, 10, 21))
            self.mark(extra, self.e_student, score=Decimal("5"))
        counts = _counts(self._call("--apply"))
        self.assertEqual((counts["kept_no_host_lesson"], counts["kept_marks_no_host_lesson"]), ("1", "1"))
        self.assertNotIn("students_moved", counts)
        with bypass_rls():
            self.e_student.refresh_from_db()
            self.assertEqual(self.e_student.status, "enrolled")
            self.assertEqual(LessonMark.objects.filter(enrollment=self.e_student).count(), 3, "heç nə silinmir")

    def test_owner_share_on_source_is_not_retired(self):
        """Sahibin boşalan payı söndürülsəydi, paysız sahib başqa müəllimlərin tələbələrini görərdi."""
        with bypass_rls():
            self.lvl_b.instructor = self.t
            self.lvl_b.save(update_fields=["instructor"])
        plan = dict(self.plan)
        self._call("--apply", plan=plan)
        with bypass_rls():
            self.t_share_b.refresh_from_db()
            self.assertTrue(self.t_share_b.is_active)

    def test_host_owner_changed_or_share_missing_is_skipped(self):
        with bypass_rls():
            self.lvl_a.instructor = self.z
            self.lvl_a.save(update_fields=["instructor"])
        counts = _counts(self._call())
        self.assertEqual(counts["host_owner_changed"], "1")
        item = dict(self.plan["journals"][0], via="share", teacher=self.s3.pk)
        counts = _counts(self._call(plan=dict(self.plan, journals=[item])))
        self.assertEqual(counts["host_teacher_no_share"], "1")

    def test_bad_inputs(self):
        with self.assertRaisesMessage(CommandError, "bad_batch"):
            self._call("--undo", "x")
        with self.assertRaisesMessage(CommandError, "level_merge_format_unknown"):
            self._call(plan={"format": "other"})
        with bypass_rls():
            self.period.is_current = False
            self.period.save(update_fields=["is_current"])
        with self.assertRaisesMessage(CommandError, "period_not_current"):
            self._call()


class LevelMergeWorkflowTest(TestCase):
    def test_workflow_whitelists_command_with_plan_and_undo(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - merge_level_journals\n", text)
        self.assertIn("'^level-merge-[0-9a-z-]+$'", text)
        self.assertIn("asset=levelmerge.json.enc", text)
        self.assertIn("'^lvlmerge-[0-9]{8}-[0-9]{6}-[0-9a-f]{4}$'", text)
        self.assertIn("'^level_merge: [a-z_]+=[0-9a-z_-]+( [a-z_]+=[0-9a-z_-]+)*$'", text)
        self.assertIn("/tmp/level_merge_*.json", text)
