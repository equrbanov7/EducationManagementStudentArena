"""Əkiz fənn kartları + əkiz jurnallar (sahib 2026-11-04): K1 (boş əkiz → datalı jurnal), K2 (ləğv olunmuş boş əkiz
silinir), K3 (qiymətsiz təkrar qeydiyyat bağlanır), K4 (``undo_subject_merge`` prod-data-ops-da), imtahan bağı.

VoIP forması: iki qrup; saxlanılan jurnallar A kartında (dərs + xana), boş əkizlər B kartında (eyni tələbələr, slot,
imtahan bağı) → ``merge_twin_offerings`` → ``merge_subjects`` → ``undo_subject_merge``.
"""

from __future__ import annotations

import datetime
import json
import os
import pathlib
import re
import subprocess
import tempfile
from decimal import Decimal
from io import StringIO

from django.apps import apps as django_apps
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.audit.models import AuditLog
from apps.registrar import subject_merge, subject_merge_apply, subject_merge_undo
from apps.registrar.models import CourseOffering, Enrollment, Lesson, LessonMark, ScheduleSlot, Subject
from apps.registrar.models.journal_share import JournalShare
from apps.registrar.twin_inert import attendance_only, enrollment_data, offering_blockers
from core.rls import bypass_rls

from .subject_merge_fixture import REASON, SubjectMergeBase

WORKFLOW = pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml"
T = datetime.time
DAY = datetime.date(2026, 10, 5)


def _counts(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        if line.startswith("twin_merge: ") and "mode=" not in line:
            out.update(pair.split("=", 1) for pair in line[len("twin_merge: ") :].split())
    return out


class TwinBase(SubjectMergeBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            cls.owner.is_superuser = True
            cls.owner.save(update_fields=["is_superuser"])
            cls.third = cls._student("sm_student3")

    # ── köməkçilər ──
    def twin_merge(self, pairs, *extra):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump({"format": "twin-merge/1", "pairs": pairs}, handle)
        out = StringIO()
        call_command(
            "merge_twin_offerings",
            "--org",
            self.org.slug,
            "--actor",
            self.owner.username,
            "--file",
            handle.name,
            *extra,
            stdout=out,
        )
        os.unlink(handle.name)
        return out.getvalue()

    def lesson(self, offering, *, kind="seminar", day=DAY):
        with bypass_rls():
            return Lesson.objects.create(
                organization=self.org, offering=offering, date=day, start_time=T(10, 10), kind=kind
            )

    def mark(self, lesson, enrollment, status="present", score=None):
        with bypass_rls():
            return LessonMark.objects.create(
                organization=self.org, lesson=lesson, enrollment=enrollment, status=status, score=score
            )

    def slot(self, offering, weekday, start, end, *, kind="lecture", week_type="all", parked=False):
        with bypass_rls():
            return ScheduleSlot.objects.create(
                organization=self.org,
                offering=offering,
                weekday=weekday,
                start_time=start,
                end_time=end,
                kind=kind,
                week_type=week_type,
                is_parked=parked,
            )

    def exam(self, subject, *offerings):
        Exam = django_apps.get_model("exams", "Exam")
        with bypass_rls():
            exam = Exam.objects.create(author=self.teacher, title="Midterm", organization=self.org, subject=subject)
            exam.journal_offerings.add(*offerings)
        return exam

    def merge_subjects(self, *, drop_attendance_only=False):
        with bypass_rls():
            payload = subject_merge.preview(
                self.org, str(self.target.pk), [str(self.source.pk)], drop_attendance_only=drop_attendance_only
            )
            if payload["blocking"]:
                return payload, None
            result = subject_merge_apply.apply(
                organization=self.org,
                actor=self.office,
                target_ref=str(self.target.pk),
                source_refs=[str(self.source.pk)],
                reason=REASON,
                expected_digest=payload["digest"],
                drop_attendance_only=drop_attendance_only,
            )
        return payload, result


class VoipShapeTest(TwinBase):
    """A = ``self.target`` (saxlanılan kart), B = ``self.source`` (dublikat). G1, G2 — hər birində iki jurnal."""

    def setUp(self):
        with bypass_rls():
            self.keep1 = self.offering(self.target, self.group1)
            self.keep2 = self.offering(self.target, self.group2)
            self.twin1 = self.offering(self.source, self.group1)
            self.twin2 = self.offering(self.source, self.group2)
            for offering in (self.keep1, self.twin1):
                self.enroll(offering, self.student)
                self.enroll(offering, self.other_student)
            for offering in (self.keep2, self.twin2):
                self.enroll(offering, self.third)
            self.enroll(self.twin2, self.other_student)  # keep2-də YOXDUR → yaradılmalı
            for keep in (self.keep1, self.keep2):
                lesson = self.lesson(keep)
                for row in Enrollment.objects.filter(offering=keep):
                    self.mark(lesson, row, score=Decimal("8"))
            self.slot(self.keep1, 1, T(15, 15), T(16, 45))
            self.equiv = self.slot(self.twin1, 1, T(15, 15), T(16, 45), parked=True)  # eyni slot, park olunub
            self.slot(self.keep2, 4, T(11, 50), T(13, 20))  # Cümə axşamı
            self.wed_lecture = self.slot(self.twin2, 3, T(11, 50), T(13, 20))  # Çərşənbə — T-də yoxdur
            self.wed_seminar = self.slot(self.twin2, 3, T(13, 35), T(15, 5), kind="seminar", week_type="odd")
            self.exam_row = self.exam(self.source, self.twin2)
        self.pairs = [
            {"source": str(self.twin1.pk), "target": str(self.keep1.pk)},
            {"source": str(self.twin2.pk), "target": str(self.keep2.pk)},
        ]

    def test_full_chain_k1_then_merge_subjects_then_undo(self):
        with bypass_rls():
            self.assertEqual(offering_blockers(self.twin1), [])
        dry = _counts(self.twin_merge(self.pairs))
        self.assertEqual(dry["pairs_merged"], "2")
        self.assertEqual(dry["pairs_merged_empty_source"], "2")
        self.assertEqual(dry["enrollments_created"], "1")
        self.assertEqual(dry["source_enrollments_dropped"], "4")
        self.assertEqual((dry["slots_moved"], dry["slots_dropped_equivalent"]), ("2", "1"))
        self.assertEqual(dry["exam_links_repointed"], "1")
        self.assertNotIn("both_have_marks", dry)
        with bypass_rls():
            self.assertTrue(CourseOffering.objects.get(pk=self.twin1.pk).is_active, "dry-run yazmır")

        text = self.twin_merge(self.pairs, "--apply")
        self.assertNotIn(self.student.username, text)
        with bypass_rls():
            for twin in (self.twin1, self.twin2):
                twin.refresh_from_db()
                self.assertFalse(twin.is_active)
                self.assertEqual(set(twin.enrollments.values_list("status", flat=True)), {"dropped"})
            self.assertTrue(Enrollment.objects.filter(offering=self.keep2, student=self.other_student).exists())
            self.assertEqual(LessonMark.objects.filter(lesson__offering=self.keep1).count(), 2, "xanalar qalır")
            self.assertTrue(ScheduleSlot.all_objects.get(pk=self.equiv.pk).is_deleted)
            moved = ScheduleSlot.objects.filter(offering=self.keep2).order_by("weekday", "start_time")
            self.assertEqual(
                [(row.weekday, row.start_time, row.kind, row.week_type) for row in moved],
                [(3, T(11, 50), "lecture", "all"), (3, T(13, 35), "seminar", "odd"), (4, T(11, 50), "lecture", "all")],
            )
            self.assertEqual(list(self.exam_row.journal_offerings.values_list("pk", flat=True)), [self.keep2.pk])
            entry = (
                AuditLog.objects.filter(object_id=str(self.twin2.pk))
                .filter(changes__kind="twin_merge_empty")
                .latest("created_at")
            )
            self.assertEqual(entry.changes["kind"], "twin_merge_empty")
            self.assertEqual(len(entry.changes["manifest"]["slots"]), 2)
        again = _counts(self.twin_merge(self.pairs, "--apply"))
        self.assertEqual(again, {"already_merged": "2", "pairs_in_file": "2"})

        payload, result = self.merge_subjects()
        self.assertEqual(payload["blocking"], [])
        self.assertEqual(sum(1 for item in payload["resolvable"] if item["code"] == "offering_twin"), 2)
        with bypass_rls():
            self.assertFalse(CourseOffering._base_manager.filter(pk__in=[self.twin1.pk, self.twin2.pk]).exists())
            self.assertEqual(CourseOffering.objects.filter(subject=self.target).count(), 2)
            self.exam_row.refresh_from_db()
            self.assertEqual(self.exam_row.subject_id, self.target.pk)
            self.assertEqual(list(self.exam_row.journal_offerings.values_list("pk", flat=True)), [self.keep2.pk])
        changes = AuditLog.objects.get(pk=result["audit_id"]).changes
        self.assertEqual(changes["counts"]["registrar.CourseOffering:deleted_empty_twins"], 2)
        self.assertEqual(
            {item["offering"]["id"] for item in changes["deleted_offerings"]}, {str(self.twin1.pk), str(self.twin2.pk)}
        )

        with bypass_rls():
            report = subject_merge_undo.undo(audit_id=result["audit_id"])
            self.assertEqual(report["issues"], [])
            self.assertFalse(CourseOffering._base_manager.filter(pk=self.twin1.pk).exists(), "dry-run saxlamır")
            report = subject_merge_undo.undo(audit_id=result["audit_id"], apply=True, reason=REASON)
            self.assertTrue(report["applied"], report["issues"])
            twin2 = CourseOffering._base_manager.get(pk=self.twin2.pk)
            self.assertEqual((twin2.subject_id, twin2.is_active), (self.source.pk, False))
            self.assertEqual(Enrollment.objects.filter(offering=twin2).count(), 2)
            self.assertEqual(ScheduleSlot.all_objects.filter(offering=twin2, is_deleted=True).count(), 2)
            # İmtahan bağını K1 köçürüb (öz manifestində) — fənn birləşməsinin geri qaytarılması ona toxunmur.
            self.assertEqual(list(self.exam_row.journal_offerings.values_list("pk", flat=True)), [self.keep2.pk])
            self.exam_row.refresh_from_db()
            self.assertEqual(self.exam_row.subject_id, self.source.pk)
            self.assertFalse(Subject.objects.get(pk=self.source.pk).is_archived)

    def test_merge_subjects_still_blocks_while_twins_are_active(self):
        payload, result = self.merge_subjects()
        self.assertIsNone(result)
        self.assertEqual(sum(1 for item in payload["blocking"] if item["code"] == "offering"), 2)


class EmptyTwinRefusalTest(TwinBase):
    def setUp(self):
        with bypass_rls():
            self.keep = self.offering(self.target, self.group1)
            self.twin = self.offering(self.source, self.group1)
            self.keep_row = self.enroll(self.keep, self.student)
            self.twin_row = self.enroll(self.twin, self.student)
            self.mark(self.lesson(self.keep), self.keep_row, score=Decimal("7"))
        self.pairs = [{"source": str(self.twin.pk), "target": str(self.keep.pk)}]

    def _assert_not_merged(self, key):
        counts = _counts(self.twin_merge(self.pairs, "--apply"))
        self.assertEqual(counts.get(key), "1", counts)
        with bypass_rls():
            self.assertTrue(CourseOffering.objects.get(pk=self.twin.pk).is_active)
            self.assertEqual(Enrollment.objects.get(pk=self.twin_row.pk).status, "enrolled")

    def test_graded_twin_is_refused(self):
        with bypass_rls():
            django_apps.get_model("registrar", "FinalGrade").objects.create(
                organization=self.org, enrollment=self.twin_row, exam_score=Decimal("30")
            )
            self.assertIn("enrollment_data", offering_blockers(self.twin))
        self._assert_not_merged("both_have_marks")

    def test_twin_with_lesson_or_syllabus_is_refused(self):
        self.syllabus(self.source, offering=self.twin, author=self.teacher)
        with bypass_rls():
            self.assertIn("syllabus.Syllabus.offering", offering_blockers(self.twin))
        self._assert_not_merged("both_have_marks")
        with bypass_rls():
            django_apps.get_model("syllabus", "Syllabus").objects.filter(offering=self.twin).delete()
        self.lesson(self.twin)
        self._assert_not_merged("both_have_marks")

    def test_inactive_keeper_enrollment_stops_the_pair(self):
        with bypass_rls():
            Enrollment.objects.filter(pk=self.keep_row.pk).update(status="dropped")
        self._assert_not_merged("target_enrollment_inactive")

    def test_shares_stay_by_default_and_move_on_request(self):
        with bypass_rls():
            share = JournalShare.objects.create(organization=self.org, offering=self.twin, teacher=self.other_student)
            share.enrollments.add(self.twin_row)
        counts = _counts(self.twin_merge(self.pairs))
        self.assertEqual(counts["shares_left_on_source"], "1")
        self.pairs[0]["move_shares"] = True
        counts = _counts(self.twin_merge(self.pairs, "--apply"))
        self.assertEqual(counts["shares_moved"], "1")
        with bypass_rls():
            share.refresh_from_db()
            self.assertEqual(share.offering_id, self.keep.pk)
            self.assertEqual(list(share.enrollments.values_list("pk", flat=True)), [self.keep_row.pk])


class CancelledTwinCollisionTest(TwinBase):
    """K2 sərhədləri: aktiv əkiz və ya datalı ləğv olunmuş əkiz → yenə blok."""

    def setUp(self):
        self.keep = self.offering(self.target, self.group1)
        self.twin = self.offering(self.source, self.group1)
        self.enroll(self.twin, self.student)

    def test_cancelled_twin_with_data_still_blocks(self):
        with bypass_rls():
            CourseOffering.objects.filter(pk=self.twin.pk).update(is_active=False)
        self.lesson(self.twin)
        payload, result = self.merge_subjects()
        self.assertIsNone(result)
        self.assertTrue(any(item["code"] == "offering" for item in payload["blocking"]))

    def test_inert_cancelled_twin_on_target_card_is_deleted_and_restored(self):
        """Coğrafi forma: boş əkiz HƏDƏF kartdadır, datalı jurnal mənbə kartında — mənbə hədəfə köçür."""
        with bypass_rls():  # setUp-ın G1 cütü bu testdə lazım deyil — boş əkiz kimi ləğv olunur
            CourseOffering.objects.filter(pk=self.twin.pk).update(is_active=False)
        self.keep = self.offering(self.source, self.group2)
        self.twin = self.offering(self.target, self.group2)
        self.enroll(self.keep, self.other_student, grade="30")
        self.enroll(self.twin, self.other_student)
        with bypass_rls():
            CourseOffering.objects.filter(pk=self.twin.pk).update(is_active=False)
            self.slot(self.twin, 2, T(8, 30), T(10, 0))
        exam = self.exam(self.target, self.twin)
        payload, result = self.merge_subjects()
        self.assertEqual(payload["blocking"], [])
        with bypass_rls():
            self.assertEqual(CourseOffering.objects.get(pk=self.keep.pk).subject_id, self.target.pk)
            self.assertFalse(CourseOffering._base_manager.filter(pk=self.twin.pk).exists())
            self.assertEqual(list(exam.journal_offerings.values_list("pk", flat=True)), [self.keep.pk])
            report = subject_merge_undo.undo(audit_id=result["audit_id"], apply=True, reason=REASON)
            self.assertTrue(report["applied"], report["issues"])
            self.assertEqual(CourseOffering.objects.get(pk=self.keep.pk).subject_id, self.source.pk)
            restored = CourseOffering._base_manager.get(pk=self.twin.pk)
            self.assertEqual((restored.subject_id, restored.is_active), (self.target.pk, False))
            self.assertEqual(ScheduleSlot.objects.filter(offering=restored).count(), 1)
            self.assertEqual(Enrollment.objects.get(offering=restored).student_id, self.other_student.pk)
            self.assertEqual(list(exam.journal_offerings.values_list("pk", flat=True)), [self.twin.pk])


class UngradedDuplicateEnrollmentTest(TwinBase):
    """K3: tələbənin eyni dövrdə iki kart üzrə qeydiyyatı (fərqli qruplar, toqquşan açılış yoxdur)."""

    def setUp(self):
        self.graded_offering = self.offering(self.target, self.group1)
        self.other_offering = self.offering(self.source, self.group2)
        self.graded = self.enroll(self.graded_offering, self.student, grade="40")
        self.bare = self.enroll(self.other_offering, self.student)

    def test_bare_enrollment_is_dropped_and_undo_restores_it(self):
        payload, result = self.merge_subjects()
        self.assertEqual(payload["blocking"], [])
        self.assertEqual([item["drop"] for item in payload["resolvable"]], [[str(self.bare.pk)]])
        with bypass_rls():
            self.assertEqual(Enrollment.objects.get(pk=self.bare.pk).status, "dropped")
            self.assertEqual(Enrollment.objects.get(pk=self.graded.pk).status, "enrolled")
            subject_merge_undo.undo(audit_id=result["audit_id"], apply=True, reason=REASON)
            self.assertEqual(Enrollment.objects.get(pk=self.bare.pk).status, "enrolled")

    def test_both_graded_still_blocks(self):
        with bypass_rls():
            django_apps.get_model("registrar", "FinalGrade").objects.create(
                organization=self.org, enrollment=self.bare, exam_score=Decimal("20")
            )
        payload, result = self.merge_subjects()
        self.assertIsNone(result)
        self.assertTrue(any(item["code"] == "enrollment" for item in payload["blocking"]))

    def test_attendance_only_counts_as_data_unless_flag(self):
        lesson = self.lesson(self.other_offering)
        self.mark(lesson, self.bare, status="absent")
        with bypass_rls():
            data = enrollment_data([self.bare.pk])
            self.assertEqual(attendance_only([self.bare.pk], data), {str(self.bare.pk)})
        payload, result = self.merge_subjects()
        self.assertIsNone(result, "yalnız davamiyyət DATADIR — defolt blok")
        payload, result = self.merge_subjects(drop_attendance_only=True)
        self.assertEqual(payload["blocking"], [])
        with bypass_rls():
            self.assertEqual(Enrollment.objects.get(pk=self.bare.pk).status, "dropped")
            self.assertEqual(LessonMark.objects.filter(enrollment=self.bare).count(), 1, "xana silinmir")

    def test_attendance_only_flag_needs_final_grade_on_kept_side(self):
        with bypass_rls():
            django_apps.get_model("registrar", "FinalGrade").objects.filter(enrollment=self.graded).delete()
        self.mark(self.lesson(self.graded_offering), self.graded, score=Decimal("9"))
        self.mark(self.lesson(self.other_offering), self.bare, status="present")
        payload, result = self.merge_subjects(drop_attendance_only=True)
        self.assertIsNone(result)

    def test_command_flag(self):
        self.mark(self.lesson(self.other_offering), self.bare, status="absent")
        args = ["merge_subjects", "--org", self.org.slug, "--target", "QA-SM-T", "--source", "QA-SM-S"]
        with self.assertRaises(CommandError):
            call_command(*args, stdout=StringIO())
        out = StringIO()
        call_command(*args, "--drop-attendance-only", stdout=out)
        self.assertIn("Həll olunur", out.getvalue())
        self.assertIn("DRY-RUN", out.getvalue())


class UndoWorkflowTest(TestCase):
    """K4: ``undo_subject_merge`` ağ siyahıdadır; ``batch`` = audit id (UUID), apply yalnız apply ilə."""

    def _block(self, name):
        text = WORKFLOW.read_text(encoding="utf-8")
        return re.findall(rf"            {name}\)\n(.*?)\n              ;;\n", text, re.S)[0]

    def _run(self, name, **env):
        script = (
            "set -euo pipefail\n"
            "match() { case \"$1\" in (*$'\\n'*|*$'\\r'*) return 1 ;; esac; "
            'printf \'%s\' "$1" | grep -Eq -- "$2"; }\n' + self._block(name) + '\nprintf "ARG:%s\\n" "${args[@]}"\n'
        )
        base = {"ORG": "qku", "APPLY": "false", "BATCH": "", "TEACHER": "", "CREATE_MISSING": "false"}
        return subprocess.run(
            ["bash", "-c", script], env={**os.environ, **base, **env}, capture_output=True, text=True, check=False
        )

    def test_whitelist_and_arguments(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - undo_subject_merge\n", text)
        audit_id = "0f1e2d3c-4b5a-4968-8776-655443322110"
        dry = self._run("undo_subject_merge", BATCH=audit_id)
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertIn(f"ARG:--audit-id={audit_id}", dry.stdout)
        self.assertNotIn("ARG:--apply", dry.stdout)
        applied = self._run("undo_subject_merge", BATCH=audit_id, APPLY="true")
        self.assertIn("ARG:--apply", applied.stdout)
        self.assertIn("ARG:--reason", applied.stdout)
        for bad in ("", "QKU-2693", audit_id + "\ninjected", audit_id.upper()):
            self.assertNotEqual(self._run("undo_subject_merge", BATCH=bad).returncode, 0, bad)

    def test_merge_subjects_attendance_flag_is_opt_in(self):
        plain = self._run("merge_subjects", TEACHER="QKU-452", BATCH="QKU-2436")
        self.assertEqual(plain.returncode, 0, plain.stderr)
        self.assertNotIn("--drop-attendance-only", plain.stdout)
        flagged = self._run("merge_subjects", TEACHER="QKU-452", BATCH="QKU-2436", CREATE_MISSING="true")
        self.assertIn("ARG:--drop-attendance-only", flagged.stdout)
