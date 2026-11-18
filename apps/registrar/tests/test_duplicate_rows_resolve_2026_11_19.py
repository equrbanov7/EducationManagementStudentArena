"""Sahib 2026-11-19: ``resolve_duplicate_rows_20261119`` — birləşdirilmiş dublikatın jurnaldakı ikinci sətri."""

from __future__ import annotations

import datetime
import pathlib
from decimal import Decimal
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase

from apps.audit.models import AuditLog
from apps.organizations.models import Membership
from apps.registrar import duplicate_rows_resolve_2026_11_19 as resolver
from apps.registrar.models import AssessmentComponent, ComponentScore, Enrollment, Lesson, LessonKind, LessonMark
from apps.registrar.tests.test_journal_shares_2026_10_26 import User, _add_student, _ShareBase
from core.rls import bypass_rls

WORKFLOW = pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml"
PREFIX = "dup_rows: "


def _parse(text: str) -> tuple[dict, str]:
    counts, batch = {}, ""
    for line in text.splitlines():
        if not line.startswith(PREFIX) or "mode=" in line:
            continue
        body = line[len(PREFIX) :]
        if body.startswith("batch="):
            batch = body.split("=", 1)[1]
            continue
        counts.update(pair.split("=", 1) for pair in body.split())
    return counts, batch


class SpecTest(SimpleTestCase):
    def test_workflow_runs_the_command_and_keeps_its_summary(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - resolve_duplicate_rows_20261119\n", text)
        self.assertIn('[ "$COMMAND" = "resolve_duplicate_rows_20261119" ]', text)
        self.assertIn("|dup_rows|", text)
        self.assertIn("^dupres-[0-9]{8}-[0-9]{6}-[0-9a-f]{4}$", text)

    def test_unconfirmed_namesake_is_excluded(self):
        self.assertIn(11740, resolver.EXCLUDED_DUPLICATES)


def _block(user):
    User.objects.filter(pk=user.pk).update(is_active=False)
    Membership.objects.filter(user=user).update(is_active=False)


class ResolveDuplicateRowsTest(_ShareBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            cls.admin = User.objects.create_superuser("dupres_admin", "dupres_admin@qku.edu.az", "pw")
            cls.keep = cls.e1
            cls.dup = _add_student(cls, "dupres_dup")
            cls.other = _add_student(cls, "dupres_other")  # təsdiqlənməmiş adaş — istisna
            day = datetime.date(2026, 10, 1)
            lesson = Lesson.objects.create
            cls.only_dup = lesson(organization=cls.org, offering=cls.offering, date=day, kind=LessonKind.SEMINAR,
                                  hours=2, start_time=datetime.time(13, 35), topic="")  # fmt: skip
            cls.both_scored = lesson(organization=cls.org, offering=cls.offering, date=day, kind=LessonKind.SEMINAR,
                                     hours=2, start_time=datetime.time(15, 15), topic="")  # fmt: skip
            mark = LessonMark.objects.create
            # mühazirə: əsas iə, dublikat qb → əsasın davamiyyəti qalır
            mark(organization=cls.org, lesson=cls.lecture, enrollment=cls.keep, status="present")
            mark(organization=cls.org, lesson=cls.lecture, enrollment=cls.dup, status="absent")
            # seminar: əsas iə balsız, dublikat iə 10 → bal əsasın xanasına
            cls.keep_seminar = mark(organization=cls.org, lesson=cls.seminar, enrollment=cls.keep, status="present")
            mark(organization=cls.org, lesson=cls.seminar, enrollment=cls.dup, status="present", score=10)
            # yalnız dublikatda: iə 7 → əsasa yeni xana
            cls.dup_only_mark = mark(
                organization=cls.org, lesson=cls.only_dup, enrollment=cls.dup, status="present", score=7
            )
            # hər ikisində bal: əsasın 5-i qalır
            mark(organization=cls.org, lesson=cls.both_scored, enrollment=cls.keep, status="present", score=5)
            mark(organization=cls.org, lesson=cls.both_scored, enrollment=cls.dup, status="present", score=9)
            # istisna edilmiş dublikatın xanası
            mark(organization=cls.org, lesson=cls.only_dup, enrollment=cls.other, status="present", score=6)
            component = AssessmentComponent.objects.create
            cls.midterm = component(organization=cls.org, offering=cls.offering, name="Midterm", max_score=30)
            cls.colloq = component(organization=cls.org, offering=cls.offering, name="Kollokvium", max_score=10)
            score = ComponentScore.objects.create
            score(organization=cls.org, component=cls.midterm, enrollment=cls.dup, score=Decimal("21"))
            score(organization=cls.org, component=cls.colloq, enrollment=cls.keep, score=Decimal("4"))
            score(organization=cls.org, component=cls.colloq, enrollment=cls.dup, score=Decimal("8"))
            _block(cls.dup.student)
            _block(cls.other.student)
            AuditLog.objects.create(
                organization=cls.org,
                action="update",
                resource_type=resolver.MERGE_RESOURCE,
                resource_id="stmerge-20261118-221823-994c",
                new_values={
                    "pairs": [
                        {"duplicate": cls.dup.student_id, "keep": cls.keep.student_id},
                        {"duplicate": cls.other.student_id, "keep": cls.keep.student_id},
                    ]
                },
            )
            # başqa (siyahıda olmayan) paket oxunmur
            AuditLog.objects.create(
                organization=cls.org,
                action="update",
                resource_type=resolver.MERGE_RESOURCE,
                resource_id="stmerge-20261027-101010-abcd",
                new_values={"pairs": [{"duplicate": cls.e2.student_id, "keep": cls.keep.student_id}]},
            )

    def setUp(self):
        patch = mock.patch.object(resolver, "EXCLUDED_DUPLICATES", frozenset({11740, self.other.student_id}))
        patch.start()
        self.addCleanup(patch.stop)

    def _call(self, *extra):
        out = StringIO()
        call_command(
            "resolve_duplicate_rows_20261119",
            "--org",
            self.org.slug,
            "--actor",
            self.admin.username,
            *extra,
            stdout=out,
        )
        return _parse(out.getvalue())

    def _keep_cells(self):
        with bypass_rls():
            marks = {
                mark.lesson_id: (mark.status, mark.score) for mark in LessonMark.objects.filter(enrollment=self.keep)
            }
            scores = {row.component_id: row.score for row in ComponentScore.objects.filter(enrollment=self.keep)}
        return marks, scores

    def _status(self, enrollment):
        with bypass_rls():
            return Enrollment.objects.get(pk=enrollment.pk).status

    def test_dry_run_apply_idempotent_and_undo(self):
        before = self._keep_cells()
        dry, batch = self._call()
        self.assertEqual((dry["rows_found"], dry["rows_resolved"], dry["merge_batches_read"]), ("1", "1", "1"))
        self.assertEqual(batch, "")
        self.assertEqual(self._keep_cells(), before)
        self.assertEqual(self._status(self.dup), "enrolled")

        applied, batch = self._call("--apply")
        self.assertRegex(batch, r"^dupres-\d{8}-\d{6}-[0-9a-f]{4}$")
        self.assertEqual(
            (
                applied["marks_copied"],
                applied["scores_copied_onto_kept_mark"],
                applied["marks_attendance_kept"],
                applied["marks_kept_value_wins"],
                applied["component_scores_copied"],
                applied["components_kept_value_wins"],
                applied["pairs_excluded"],
            ),
            ("1", "1", "1", "1", "1", "1", "1"),
        )
        marks, scores = self._keep_cells()
        self.assertEqual(marks[self.lecture.pk], ("present", None))  # əsasın davamiyyəti qalır
        self.assertEqual(marks[self.seminar.pk], ("present", Decimal("10.00")))  # yalnız dublikatın balı
        self.assertEqual(marks[self.only_dup.pk], ("present", Decimal("7.00")))  # yalnız dublikatın xanası
        self.assertEqual(marks[self.both_scored.pk], ("present", Decimal("5.00")))  # əsasın dəyəri üstündür
        self.assertEqual(scores, {self.midterm.pk: Decimal("21.00"), self.colloq.pk: Decimal("4.00")})
        with bypass_rls():
            copied = LessonMark.objects.get(enrollment=self.keep, lesson=self.only_dup)
            self.assertEqual(copied.created_at, LessonMark.objects.get(pk=self.dup_only_mark.pk).created_at)
            self.assertEqual(LessonMark.objects.filter(enrollment=self.dup).count(), 4)  # dublikatın xanaları qalır
        self.assertEqual(self._status(self.dup), "dropped")
        self.assertEqual(self._status(self.other), "enrolled")  # istisna toxunulmur
        self.assertEqual(self._status(self.e2), "enrolled")  # siyahıda olmayan paket

        again, second = self._call("--apply")
        self.assertEqual((again.get("rows_found"), again["nothing_to_resolve"], second), (None, "1", ""))

        undone, _ = self._call("--apply", "--undo", "--batch", batch)
        self.assertEqual(
            (
                undone["undo_marks_deleted"],
                undone["undo_marks_restored"],
                undone["undo_scores_deleted"],
                undone["undo_rows_reenrolled"],
            ),
            ("1", "1", "1", "1"),
        )
        self.assertEqual(self._keep_cells(), before)
        self.assertEqual(self._status(self.dup), "enrolled")

    def test_closed_journal_and_unblocked_duplicate_are_skipped(self):
        with bypass_rls():
            User.objects.filter(pk=self.dup.student_id).update(is_active=True)
        counts, _ = self._call("--apply")
        self.assertEqual((counts["pairs_duplicate_not_blocked"], counts.get("rows_found")), ("1", None))
        with bypass_rls():
            User.objects.filter(pk=self.dup.student_id).update(is_active=False)
        with mock.patch.object(resolver, "closed", return_value={str(self.offering.pk)}):
            counts, _ = self._call("--apply")
        self.assertEqual((counts["rows_skipped_closed_or_inactive"], counts.get("rows_resolved")), ("1", None))
        self.assertEqual(self._status(self.dup), "enrolled")

    def test_undo_keeps_cell_changed_after_apply(self):
        _, batch = self._call("--apply")
        with bypass_rls():
            LessonMark.objects.filter(enrollment=self.keep, lesson=self.only_dup).update(score=Decimal("3"))
        undone, _ = self._call("--apply", "--undo", "--batch", batch)
        self.assertEqual(undone["undo_mark_changed_kept"], "1")
        marks, _ = self._keep_cells()
        self.assertEqual(marks[self.only_dup.pk], ("present", Decimal("3.00")))
