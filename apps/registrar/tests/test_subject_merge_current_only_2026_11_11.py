"""Fənn birləşdirməsi — «yalnız cari və gələcək» rejimi (sahib 2026-11-11).

«Köhnə illərin jurnalını ciddiyə alma, boşver — əsas indi və bundan sonra olandır.» Keçmiş dövrün toqquşması bloklamır,
keçmiş açılışlar (və onların sillabusu, keçmiş imtahan) arxivlənən mənbə kartda olduğu kimi qalır; cari toqquşma yenə
bloklayır; geri qaytarma yalnız köçən sətirləri qaytarır.
"""

from __future__ import annotations

import datetime
from io import StringIO

from django.apps import apps as django_apps
from django.core.management import call_command
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.organizations.models import AcademicPeriod
from apps.registrar import subject_merge, subject_merge_apply, subject_merge_undo
from apps.registrar.models import CourseOffering, Subject
from core.constants import AcademicPeriodType
from core.rls import bypass_rls

from .subject_merge_fixture import REASON, SubjectMergeBase

OFFERING_KEY = "registrar.CourseOffering.subject"
EXAM_KEY = "exams.Exam.subject"


class CurrentOnlyMergeTest(SubjectMergeBase):
    def setUp(self):
        super().setUp()
        with bypass_rls():
            self.past = AcademicPeriod.objects.create(
                organization=self.org,
                name="2022/2023 Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2022/2023",
                start_date=datetime.date(2022, 9, 15),
                end_date=datetime.date(2023, 1, 25),
            )

    def _preview(self, **extra):
        with bypass_rls():
            return subject_merge.preview(self.org, str(self.target.pk), [str(self.source.pk)], **extra)

    def _merge(self, **extra):
        payload = self._preview(**extra)
        with bypass_rls():
            result = subject_merge_apply.apply(
                organization=self.org,
                actor=self.office,
                target_ref=str(self.target.pk),
                source_refs=[str(self.source.pk)],
                reason=REASON,
                expected_digest=payload["digest"],
                **extra,
            )
        return payload, result

    def _past_conflict(self):
        """«2022/2023 Payız · 234 K: hər iki fənn üzrə açılış var» — datalı iki köhnə jurnal."""
        past_source = self.offering(self.source, self.group1, period=self.past)
        past_target = self.offering(self.target, self.group1, period=self.past)
        self.enroll(past_source, grade="71")
        self.enroll(past_target, student=self.other_student, grade="64")
        return past_source, past_target

    def _exam(self, subject, start):
        Exam = django_apps.get_model("exams", "Exam")
        with bypass_rls():
            return Exam.objects.create(
                author=self.teacher, title="Midterm", organization=self.org, subject=subject, start_datetime=start
            )

    # (a) keçmiş toqquşma bloklamır, keçmiş açılış mənbədə qalır
    def test_past_only_conflict_blocks_normal_merge_but_not_current_only(self):
        past_source, past_target = self._past_conflict()
        current = self.offering(self.source, self.group2)
        self.enroll(current)
        normal = self._preview()
        self.assertEqual([item["code"] for item in normal["blocking"]], ["offering"])

        payload, result = self._merge(current_only=True)
        self.assertEqual(payload["blocking_total"], 0)
        self.assertTrue(payload["current_only"])
        self.assertEqual(payload["left_past"][OFFERING_KEY], 1)
        self.assertEqual(result["counts"][OFFERING_KEY], 1)
        self.assertEqual(result["counts"][f"{OFFERING_KEY}:left_past"], 1)
        with bypass_rls():
            self.assertEqual(CourseOffering.objects.get(pk=current.pk).subject_id, self.target.pk)
            self.assertEqual(CourseOffering.objects.get(pk=past_source.pk).subject_id, self.source.pk)
            self.assertEqual(CourseOffering.objects.get(pk=past_target.pk).subject_id, self.target.pk)
            source = Subject.objects.get(pk=self.source.pk)
        self.assertTrue(source.is_archived)
        self.assertFalse(source.is_active)
        changes = AuditLog.objects.get(pk=result["audit_id"]).changes
        self.assertTrue(changes["current_only"])
        self.assertEqual(changes["left_past"][OFFERING_KEY], [str(past_source.pk)])

    def test_past_syllabus_and_past_exam_stay_current_ones_move(self):
        past_source, _past_target = self._past_conflict()
        past_syllabus = self.syllabus(self.source, offering=past_source, author=self.teacher)
        current_syllabus = self.syllabus(self.source, period=self.period, author=self.teacher)
        tz = timezone.get_current_timezone()
        old_exam = self._exam(self.source, datetime.datetime(2022, 11, 1, 10, tzinfo=tz))
        new_exam = self._exam(self.source, datetime.datetime(2026, 11, 1, 10, tzinfo=tz))
        _payload, result = self._merge(current_only=True)
        Syllabus = django_apps.get_model("syllabus", "Syllabus")
        Exam = django_apps.get_model("exams", "Exam")
        with bypass_rls():
            self.assertEqual(Syllabus.objects.get(pk=past_syllabus.pk).subject_id, self.source.pk)
            self.assertEqual(Syllabus.objects.get(pk=current_syllabus.pk).subject_id, self.target.pk)
            self.assertEqual(Exam.objects.get(pk=old_exam.pk).subject_id, self.source.pk)
            self.assertEqual(Exam.objects.get(pk=new_exam.pk).subject_id, self.target.pk)
        self.assertEqual(result["counts"][EXAM_KEY], 1)
        self.assertEqual(result["counts"][f"{EXAM_KEY}:left_past"], 1)

    def test_current_conflict_still_blocks(self):
        self._past_conflict()
        self.enroll(self.offering(self.source, self.group1))
        self.enroll(self.offering(self.target, self.group1), student=self.other_student)
        payload = self._preview(current_only=True)
        self.assertEqual([item["code"] for item in payload["blocking"]], ["offering"])
        self.assertIn("Payız", payload["blocking"][0]["message"])
        self.assertNotIn("2022/2023", payload["blocking"][0]["message"])

    def test_past_graded_credit_difference_does_not_block_current_only(self):
        Subject.objects.filter(pk=self.source.pk).update(ects=4)
        self.source.refresh_from_db()
        self.enroll(self.offering(self.source, self.group1, period=self.past), grade="80")
        self.offering(self.source, self.group2)
        self.assertEqual([item["code"] for item in self._preview()["blocking"]], ["credit_mismatch"])
        self.assertEqual(self._preview(current_only=True)["blocking_total"], 0)

    def test_digest_carries_the_mode(self):
        self._past_conflict()
        self.offering(self.source, self.group2)
        normal = self._preview()
        current = self._preview(current_only=True)
        self.assertNotEqual(normal["digest"], current["digest"])
        with bypass_rls(), self.assertRaises(subject_merge.MergeError) as caught:
            subject_merge_apply.apply(
                organization=self.org,
                actor=self.office,
                target_ref=str(self.target.pk),
                source_refs=[str(self.source.pk)],
                reason=REASON,
                expected_digest=normal["digest"],
                current_only=True,
            )
        self.assertEqual(caught.exception.code, "drift")

    # (d) geri qaytarma
    def test_undo_returns_moved_rows_and_leaves_past_rows_alone(self):
        past_source, past_target = self._past_conflict()
        current = self.offering(self.source, self.group2)
        _payload, result = self._merge(current_only=True)
        with bypass_rls():
            dry = subject_merge_undo.undo(audit_id=result["audit_id"])
            self.assertEqual(dry["issues"], [])
            report = subject_merge_undo.undo(audit_id=result["audit_id"], apply=True, reason=REASON)
        self.assertTrue(report["applied"], report["issues"])
        with bypass_rls():
            self.assertEqual(CourseOffering.objects.get(pk=current.pk).subject_id, self.source.pk)
            self.assertEqual(CourseOffering.objects.get(pk=past_source.pk).subject_id, self.source.pk)
            self.assertEqual(CourseOffering.objects.get(pk=past_target.pk).subject_id, self.target.pk)
            source = Subject.objects.get(pk=self.source.pk)
        self.assertFalse(source.is_archived)
        self.assertTrue(source.is_active)

    def test_command_flag_and_report(self):
        self._past_conflict()
        self.offering(self.source, self.group2)
        base = ["merge_subjects", "--org", self.org.slug, "--target", "QA-SM-T", "--source", "QA-SM-S"]
        out = StringIO()
        call_command(*base, "--current-only", stdout=out)
        text = out.getvalue()
        self.assertIn("offerings_moved=1 offerings_left_past=1", text)
        self.assertIn("DRY-RUN", text)
        self.assertFalse(Subject.objects.get(pk=self.source.pk).is_archived)
        out = StringIO()
        call_command(*base, "--current-only", "--apply", "--reason", REASON, stdout=out)
        self.assertIn("Audit id:", out.getvalue())
        self.assertTrue(Subject.objects.get(pk=self.source.pk).is_archived)

    def test_plan_mode_passes_the_flag(self):
        self._past_conflict()
        self.offering(self.source, self.group2)
        Subject.objects.filter(pk=self.target.pk).update(code="QKU-9001")
        Subject.objects.filter(pk=self.source.pk).update(code="QKU-9002")
        out = StringIO()
        call_command(
            "merge_subjects", "--org", self.org.slug, "--plan", "QKU-9001:QKU-9002", "--current-only", stdout=out
        )
        text = out.getvalue()
        self.assertIn("merge_plan: mode=dry_run current_only=1 pairs=1 ok=1 conflict=0 error=0", text)
        self.assertIn(f"{OFFERING_KEY}:left_past=1", text)
