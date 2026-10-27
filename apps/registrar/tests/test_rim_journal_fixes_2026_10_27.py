"""RİM müraciətləri 2026-10-27: sahibin növləri (MR-000010), pay faylının növ yeniləməsi / söndürmə / geri qaytarma,
``relocate_superseded_marks`` (MR-000010 / MR-000030.1)."""

from __future__ import annotations

import datetime
import io
import json
import os
import re
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.test import SimpleTestCase

from apps.audit.models import AuditLog
from apps.organizations.models import OrgUnit, OrgUnitType
from apps.registrar.models import (
    CourseOffering,
    Enrollment,
    JournalShare,
    JournalShareSource,
    Lesson,
    LessonKind,
    LessonMark,
)
from apps.registrar.superseded_marks import BATCH_RESOURCE
from apps.registrar.tests.test_journal_shares_2026_10_26 import User, _add_teacher, _ShareBase
from core.rls import bypass_rls

COUNTS_RE = re.compile(r"^[a-z_]+: [a-z_]+=[0-9a-z_-]+( [a-z_]+=[0-9a-z_-]+)*$")


def _counts(out: str) -> dict:
    counts = {}
    for line in out.splitlines():
        assert COUNTS_RE.match(line), line  # stdout-a YALNIZ saylar
        for pair in line.split(" ")[1:]:
            key, value = pair.split("=")
            counts[key] = value
    return counts


class OwnerKindsTest(_ShareBase):
    """Sahibin növləri yalnız BÜTÜN siyahını örtən paylarla daralır."""

    def test_guest_share_does_not_hide_owner_kinds(self):
        guest = _add_teacher(self, "jsh_guest")
        self._share(self.teacher, kinds=["lecture"])
        self._share(guest, kinds=[], enrollments=[self.e2])  # qonaq tələbə, bütün növlər
        scope = self._scope(self.teacher)
        self.assertIsNone(scope.kinds)  # MR-000010: sahib seminar/lab sütunlarını da görür
        self.assertTrue(scope.allows_kind(LessonKind.SEMINAR))

    def test_whole_roster_seminar_share_still_claims_seminar(self):
        self._share(self.teacher, kinds=["lecture"])
        self._share(self.seminarist, kinds=["seminar"])  # bütün tələbələr
        scope = self._scope(self.teacher)
        self.assertEqual(scope.kinds, frozenset({"lecture", "lab"}))
        self.assertFalse(scope.allows_kind(LessonKind.SEMINAR))

    def test_seminar_shares_covering_roster_together_claim_seminar(self):
        other = _add_teacher(self, "jsh_seminar2")
        self._share(self.teacher, kinds=["lecture"])
        self._share(self.seminarist, kinds=["seminar"], enrollments=[self.e1])
        self._share(other, kinds=["seminar"], enrollments=[self.e2])
        self.assertEqual(self._scope(self.teacher).kinds, frozenset({"lecture", "lab"}))


class ShareFileUpdateTest(_ShareBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            cls.admin = User.objects.create_superuser("jsh27_admin", "jsh27_admin@qku.edu.az", "pw")

    def _file(self, shares):
        payload = {"format": "journal-shares/1", "period": str(self.period.pk), "shares": shares}
        handle, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream)
        self.addCleanup(os.unlink, path)
        return path

    def _run(self, *args):
        out = io.StringIO()
        call_command("apply_journal_shares", "--org", self.org.slug, "--actor", self.admin.username, *args, stdout=out)
        return _counts(out.getvalue())

    def _row(self, teacher, kinds, **extra):
        return {"offering": str(self.offering.pk), "teacher": teacher.pk, "kinds": kinds, "enrollments": [], **extra}

    def test_kinds_update_and_undo_restores_previous_state(self):
        share = self._share(
            self.seminarist, kinds=["seminar"], enrollments=[self.e2], batch="shares-20261026-000000-aaaa"
        )
        counts = self._run(
            "--file",
            self._file([self._row(self.seminarist, ["lecture", "seminar"], enrollments=[str(self.e2.pk)])]),
            "--apply",
        )
        self.assertEqual(counts["shares_updated"], "1")
        with bypass_rls():
            share.refresh_from_db()
            self.assertEqual(share.kinds, [])  # dərslərdəki bütün növlər → hamısı
            self.assertTrue(AuditLog.objects.filter(resource_id=counts["batch"]).exists())
        undo = self._run("--undo", counts["batch"], "--apply")
        self.assertEqual(undo["shares_restored"], "1")
        with bypass_rls():
            share.refresh_from_db()
            self.assertTrue(share.is_active)
            self.assertEqual((share.kinds, share.batch), (["seminar"], "shares-20261026-000000-aaaa"))
            self.assertEqual(list(share.enrollments.values_list("pk", flat=True)), [self.e2.pk])

    def test_active_false_deactivates_single_share_and_undo_reactivates(self):
        share = self._share(self.seminarist, kinds=["seminar"])
        manual = self._share(self.stranger, kinds=["seminar"], source=JournalShareSource.MANUAL)
        rows = [
            {"offering": str(self.offering.pk), "teacher": self.seminarist.pk, "active": False},
            {"offering": str(self.offering.pk), "teacher": self.stranger.pk, "active": False},
            {"offering": str(self.offering.pk), "teacher": self.teacher.pk, "active": False},
        ]
        dry = self._run("--file", self._file(rows))
        self.assertEqual((dry["shares_deactivated"], dry["manual_kept"], dry["deactivate_missing"]), ("1", "1", "1"))
        counts = self._run("--file", self._file(rows), "--apply")
        with bypass_rls():
            self.assertFalse(JournalShare.objects.get(pk=share.pk).is_active)
            self.assertTrue(JournalShare.objects.get(pk=manual.pk).is_active)  # əl ilə pay toxunulmur
        undo = self._run("--undo", counts["batch"], "--apply")
        self.assertEqual(undo["shares_reactivated"], "1")
        with bypass_rls():
            self.assertTrue(JournalShare.objects.get(pk=share.pk).is_active)


class RelocateSupersededMarksTest(_ShareBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            cls.admin = User.objects.create_superuser("jsh27_root", "jsh27_root@qku.edu.az", "pw")
            group2 = OrgUnit.objects.create(
                organization=cls.org,
                name="JR-102",
                slug="jsh-jr102",
                unit_type=OrgUnitType.GROUP,
                parent=cls.group.parent,
            )
            cls.target_offering = CourseOffering.objects.create(
                organization=cls.org, subject=cls.subject, period=cls.period, group=group2, instructor=cls.stranger
            )
            cls.successor = Enrollment.objects.create(
                organization=cls.org,
                student=cls.student,
                offering=cls.target_offering,
                kind="mandatory",
                status="enrolled",
            )
            Enrollment.objects.filter(pk=cls.e1.pk).update(status="dropped", superseded_by=cls.successor)
            day = datetime.date(2026, 10, 15)
            cls.phantom = Lesson.objects.create(
                organization=cls.org, offering=cls.offering, date=day, kind=LessonKind.LECTURE, hours=2,
                start_time=datetime.time(10, 10), topic="",
            )  # fmt: skip
            cls.phantom2 = Lesson.objects.create(
                organization=cls.org, offering=cls.offering, date=day, kind=LessonKind.SEMINAR, hours=2,
                start_time=datetime.time(13, 35), topic="",
            )  # fmt: skip
            cls.target = Lesson.objects.create(
                organization=cls.org, offering=cls.target_offering, date=day, kind=LessonKind.LECTURE, hours=2,
                start_time=datetime.time(10, 10), topic="",
            )  # fmt: skip
            cls.target2 = Lesson.objects.create(
                organization=cls.org, offering=cls.target_offering, date=day, kind=LessonKind.SEMINAR, hours=2,
                start_time=datetime.time(13, 35), topic="",
            )  # fmt: skip
            cls.moving = LessonMark.objects.create(
                organization=cls.org, lesson=cls.phantom, enrollment=cls.e1, status="absent"
            )
            cls.conflicting = LessonMark.objects.create(
                organization=cls.org, lesson=cls.phantom2, enrollment=cls.e1, status="present", score=7
            )
            LessonMark.objects.create(
                organization=cls.org, lesson=cls.target2, enrollment=cls.successor, status="present", score=5
            )

    def _run(self, *args):
        out = io.StringIO()
        call_command(
            "relocate_superseded_marks", "--org", self.org.slug, "--actor", self.admin.username, *args, stdout=out
        )
        return _counts(out.getvalue())

    def test_dry_run_apply_idempotent_and_undo(self):
        dry = self._run()
        self.assertEqual((dry["mode"], dry["moved"], dry["conflict_kept"]), ("dry_run", "1", "1"))
        with bypass_rls():
            self.assertEqual(LessonMark.objects.get(pk=self.moving.pk).lesson_id, self.phantom.pk)
        counts = self._run("--apply")
        self.assertEqual((counts["moved"], counts["lessons_emptied"], counts["lessons_deleted"]), ("1", "1", "1"))
        with bypass_rls():
            # Boşalan fantom sütun eyni paketdə silinir (MR-000010); xanası qalan sütun yerindədir.
            self.assertFalse(Lesson.objects.filter(pk=self.phantom.pk).exists())
            self.assertTrue(Lesson.objects.filter(pk=self.phantom2.pk).exists())
            moved = LessonMark.objects.get(pk=self.moving.pk)  # eyni id
            self.assertEqual(
                (moved.lesson_id, moved.enrollment_id, moved.status), (self.target.pk, self.successor.pk, "absent")
            )
            self.assertEqual(moved.created_at, self.moving.created_at)
            self.assertEqual(Enrollment.objects.get(pk=self.successor.pk).absence_hours, 2)
            # Hədəf xana doludur → mənbə toxunulmur (heç vaxt üzərinə yazılmır).
            self.assertEqual(LessonMark.objects.get(pk=self.conflicting.pk).lesson_id, self.phantom2.pk)
            self.assertEqual(str(LessonMark.objects.get(lesson=self.target2).score), "5.00")
            self.assertTrue(AuditLog.objects.filter(resource_type=BATCH_RESOURCE, resource_id=counts["batch"]).exists())
        self.assertEqual(self._run("--apply")["moved"], "0")
        undo = self._run("--undo", counts["batch"], "--apply")
        self.assertEqual((undo["undo_restored"], undo["undo_lessons_restored"]), ("1", "1"))
        with bypass_rls():
            restored = Lesson.objects.get(pk=self.phantom.pk)  # eyni id, eyni sahələr
            self.assertEqual(
                (restored.offering_id, restored.date, restored.start_time, restored.kind),
                (self.offering.pk, self.phantom.date, self.phantom.start_time, LessonKind.LECTURE),
            )
            back = LessonMark.objects.get(pk=self.moving.pk)
            self.assertEqual((back.lesson_id, back.enrollment_id), (self.phantom.pk, self.e1.pk))

    def test_plan_round_trip_and_mismatch(self):
        handle, path = tempfile.mkstemp(suffix=".json")
        os.close(handle)
        self.addCleanup(os.unlink, path)
        self.assertEqual(self._run("--plan-out", path)["plan_rows"], "1")
        with open(path, encoding="utf-8") as stream:
            plan = json.load(stream)
        self.assertEqual(plan["moves"][0]["mark"], str(self.moving.pk))
        plan["moves"][0]["lesson"] = str(self.target2.pk)
        with open(path, "w", encoding="utf-8") as stream:
            json.dump(plan, stream)
        counts = self._run("--file", path, "--apply")
        self.assertEqual((counts["plan_mismatch"], counts["moved"]), ("1", "0"))


class LegacyDeltaSinceTest(SimpleTestCase):
    def test_since_filter_drops_older_and_undated_rows(self):
        from unittest import mock

        from apps.legacy_import.services.delta import since

        period = mock.Mock(start_date=datetime.date(2026, 9, 15), end_date=datetime.date(2027, 1, 31))
        bundle = {
            "periods": [{"id": 14}],
            "journals": [{"id": 1, "uniqid": "J1", "semestr": 14}],
            "points": [
                {"journal_uniqid": "J1", "month_id": "10", "day_number": "20", "id": 1},
                {"journal_uniqid": "J1", "month_id": "10", "day_number": "22", "id": 2},
                {"journal_uniqid": "J1", "month_id": "im2", "day_number": "im2", "id": 3},
            ],
            "lesson_dates": [{"journal_id": 1, "month": 10, "day": 23}, {"journal_id": 1, "month": 9, "day": 30}],
            "lesson_topics": [{"journal_uniqid": "J1", "month": 10.0, "day": 21.0}],
        }
        with mock.patch.object(since, "Catalog") as catalog:
            catalog.return_value.period_for.return_value = period
            restricted, counts = since.restrict_to_since(bundle, object(), datetime.date(2026, 10, 21))
        self.assertEqual([row["id"] for row in restricted["points"]], [2])
        self.assertEqual(len(restricted["lesson_dates"]), 1)
        self.assertEqual(len(restricted["lesson_topics"]), 1)
        self.assertEqual(counts["since.points_undated_dropped"], 1)
        self.assertEqual(len(bundle["points"]), 3)  # paketin özü dəyişmir


class ProdDataOpsCasesTest(SimpleTestCase):
    def test_new_commands_are_whitelisted(self):
        text = (Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml").read_text(
            encoding="utf-8"
        )
        for command in ("relocate_superseded_marks", "merge_duplicate_student"):
            self.assertIn(f"          - {command}\n", text)
            self.assertIn(f"            {command})\n", text)
        self.assertIn("^superseded-marks-[0-9a-z-]+$", text)
        self.assertIn("^student-merge-[0-9a-z-]+$", text)
        self.assertIn("^(superseded_marks|student_merge): [a-z_]+=[0-9a-z_-]+( [a-z_]+=[0-9a-z_-]+)*$", text)
        self.assertIn('args+=(--lessons-since "$DATE_FROM")', text)
