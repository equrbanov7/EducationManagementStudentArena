"""Sahib 2026-11-08: Mexanika jurnalları — dərs növü (xanalar qalır) və səhv jurnala düşmüş dərslər (xanaları ilə).

Nəyi qoruyur
------------
* A: seminar → lab / mühazirə; xanalar (id, status, bal) dəyişmir; ballı dərs mühazirə olmur (``score_conflict``);
  lab qruplu jurnalda qrupsuz lab yaranmır; tapılmayan dərs ``missing``;
* B: dərs xanaları ilə hədəf jurnala, tələbənin HƏDƏF qeydiyyatına; müəllim hədəfinki; qayıb saatı hər iki tərəfdə;
  hədəfdə qeydiyyatı olmayan tələbə dərsi bloklayır; mənbədən yükdə olmayan müəllimin payı passiv olur;
* dry-run heç nə yazmır; ``--undo`` hər şeyi qaytarır, xanası sonradan dəyişən dərsi qaytarmır;
* repodakı plan yalnız id / tarix / saat / növdür; prod-data-ops-a qoşulub.
"""

from __future__ import annotations

import datetime
import io
import json
import tempfile

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from apps.audit.models import AuditLog
from apps.registrar import mexanika_lessons_fix_2026_11_08 as fix
from apps.registrar import services as registrar_services
from apps.registrar.models import Enrollment, JournalShare, Lesson, LessonKind, LessonMark, Subject
from apps.registrar.tests.journal_load_fixtures import seed_current_journal_load
from apps.registrar.tests.test_lab_groups_2026_11_06 import WORKFLOW, _LabWorld
from core.rls import bypass_rls

User = get_user_model()
T1010, T1335, T1515 = datetime.time(10, 10), datetime.time(13, 35), datetime.time(15, 15)


def _day(text):
    return datetime.date.fromisoformat(text)


class MexanikaLessonsFixTest(_LabWorld, TestCase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            cls.owner.is_superuser = True
            cls.owner.save(update_fields=["is_superuser"])
            cls.hamidova = User.objects.create_user("mx_robot", "mx_robot@x.test", "pw")
            cls.leman = User.objects.create_user("mx_seminar", "mx_seminar@x.test", "pw")
            for user in (cls.hamidova, cls.leman):
                cls._member(user, "teacher", ["grade.input"])
            cls.fiz, cls.riy, cls.cih, cls.rob = (
                registrar_services.get_or_create_offering(
                    organization=cls.org,
                    subject=Subject.objects.create(organization=cls.org, code=code, name=code),
                    period=cls.period,
                    group=cls.group,
                )
                for code in ("MXFIZ", "MXRIY", "MXCIH", "MXROB")
            )
            for offering, teacher in ((cls.fiz, cls.teacher), (cls.riy, cls.teacher), (cls.cih, cls.teacher)):
                offering.instructor = teacher
                offering.save(update_fields=["instructor"])
            cls.rob.instructor = cls.hamidova
            cls.rob.save(update_fields=["instructor"])
            # Köçürmə Həmidovanı «Sənaye cihazları»na da pay kimi yazıb; yükdə L — sahib, S — Ləman.
            JournalShare.objects.create(organization=cls.org, offering=cls.cih, teacher=cls.hamidova, source="legacy")
            JournalShare.objects.create(
                organization=cls.org, offering=cls.cih, teacher=cls.leman, kinds=["seminar"], source="legacy"
            )
            seed_current_journal_load(cls.cih, teacher=cls.teacher, kinds=("lecture",))
            seed_current_journal_load(cls.cih, teacher=cls.leman, kinds=("seminar",))
            cls.enr = {
                offering.pk: [
                    Enrollment.objects.create(organization=cls.org, student=student, offering=offering)
                    for student in cls.students
                ]
                for offering in (cls.fiz, cls.riy, cls.cih, cls.rob)
            }

    def setUp(self):
        with bypass_rls():
            self.fiz_lessons = [
                self._make(self.fiz, day, T1010, LessonKind.SEMINAR, [("present", 8), ("absent", None)])
                for day in ("2026-09-18", "2026-09-25", "2026-10-02")
            ]
            self.riy_ok = self._make(self.riy, "2026-09-15", T1010, LessonKind.SEMINAR, [("present", None)] * 3)
            self.riy_scored = self._make(self.riy, "2026-09-22", T1010, LessonKind.SEMINAR, [("present", 7)])
            self.split_lab = self._make(self.offering, "2026-09-16", T1010, LessonKind.SEMINAR, [])
            self.cih_lecture = self._make(
                self.cih, "2026-09-25", T1335, LessonKind.LECTURE, [("absent", None), ("present", None)]
            )
            self.cih_seminar = self._make(
                self.cih, "2026-09-25", T1515, LessonKind.SEMINAR, [("present", 9), ("present", 6), ("absent", None)]
            )
            self.cih_own = self._make(self.cih, "2026-09-26", T1335, LessonKind.LECTURE, [("absent", None)])
            Lesson.objects.filter(pk=self.cih_own.pk).update(instructor=self.teacher)
        self.plan = self._plan()

    def _make(self, offering, day, start, kind, cells):
        lesson = Lesson.objects.create(
            organization=self.org, offering=offering, date=_day(day), start_time=start, kind=kind, hours=2, topic=""
        )
        for enrollment, (status, score) in zip(self.enr.get(offering.pk, []), cells):
            LessonMark.objects.create(
                organization=self.org, lesson=lesson, enrollment=enrollment, status=status, score=score
            )
        return lesson

    def _plan(self, *, kinds=None, moves=None):
        kinds = kinds or [
            *(
                {"offering": str(self.fiz.pk), "date": day, "start_time": "10:10", "from": "seminar", "to": "lab"}
                for day in ("2026-09-18", "2026-09-25", "2026-10-02", "2026-10-09")
            ),
            {
                "offering": str(self.riy.pk),
                "date": "2026-09-15",
                "start_time": "10:10",
                "from": "seminar",
                "to": "lecture",
            },
            {
                "offering": str(self.riy.pk),
                "date": "2026-09-22",
                "start_time": "10:10",
                "from": "seminar",
                "to": "lecture",
            },
            {
                "offering": str(self.offering.pk),
                "date": "2026-09-16",
                "start_time": "10:10",
                "from": "seminar",
                "to": "lab",
            },
        ]
        moves = moves or [
            {
                "source": str(self.cih.pk),
                "target": str(self.rob.pk),
                "remove_source_instructor": True,
                "lessons": [
                    {"date": "2026-09-25", "start_time": "13:35", "kind": "lecture"},
                    {"date": "2026-09-25", "start_time": "15:15", "kind": "seminar"},
                ],
            }
        ]
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
            json.dump({"format": fix.FORMAT, "kind_changes": kinds, "moves": moves}, handle)
        return handle.name

    def _call(self, *extra):
        out = io.StringIO()
        call_command(
            "fix_mexanika_lessons_20261108", "--org", self.org.slug, "--actor", self.owner.username, *extra, stdout=out
        )
        counts = {}
        for line in out.getvalue().splitlines():
            self.assertRegex(line, r"^mexanika_lessons: [a-z_]+=[0-9a-z_-]+( [a-z_]+=[0-9a-z_-]+)*$")
            if "mode=" not in line:
                counts.update(pair.split("=", 1) for pair in line[len("mexanika_lessons: ") :].split())
        return counts

    def _state(self):
        with bypass_rls():
            return (
                sorted(
                    Lesson.objects.values_list("offering_id", "date", "start_time", "kind", "instructor_id"), key=str
                ),
                sorted(LessonMark.objects.values_list("enrollment_id", "lesson__date", "status", "score"), key=str),
                sorted(JournalShare.objects.values_list("teacher_id", "is_active"), key=str),
            )

    # ── A ──────────────────────────────────────────────────────────────────
    def test_kind_changes_keep_marks_and_block_conflicts(self):
        with bypass_rls():
            before = fix.marks_state(self.fiz_lessons[0].pk)
        counts = self._call("--file", self.plan, "--apply")
        self.assertEqual(counts["kind_changed_to_lab"], "3")
        self.assertEqual(counts["kind_changed_to_lecture"], "1")
        self.assertEqual(counts["kind_missing"], "1")  # 10-09 dərsi yoxdur — təxmin yox
        self.assertEqual(counts["score_conflict"], "1")
        self.assertEqual(counts["kind_lab_split_offering"], "1")
        with bypass_rls():
            self.assertEqual({row.kind for row in Lesson.objects.filter(offering=self.fiz)}, {"lab"})
            self.assertEqual(fix.marks_state(self.fiz_lessons[0].pk), before)
            self.assertIsNone(Lesson.objects.get(pk=self.fiz_lessons[0].pk).lab_group)
            self.assertEqual(Lesson.objects.get(pk=self.riy_ok.pk).kind, "lecture")
            self.assertEqual(LessonMark.objects.filter(lesson=self.riy_ok).count(), 3)
            self.assertEqual(Lesson.objects.get(pk=self.riy_scored.pk).kind, "seminar")
            self.assertEqual(Lesson.objects.get(pk=self.split_lab.pk).kind, "seminar")
        self.assertEqual(self._call("--file", self.plan, "--apply")["kind_already_done"], "4")

    # ── B ──────────────────────────────────────────────────────────────────
    def test_move_dry_run_apply_and_undo(self):
        before = self._state()
        counts = self._call("--file", self.plan)
        self.assertEqual((counts["moved_lessons"], counts["moved_marks"]), ("2", "5"))
        self.assertEqual(self._state(), before)  # dry-run
        counts = self._call("--file", self.plan, "--apply")
        self.assertEqual((counts["moved_lessons"], counts["instructor_removed"]), ("2", "1"))
        cih, rob = self.enr[self.cih.pk], self.enr[self.rob.pk]
        with bypass_rls():
            moved = Lesson.objects.filter(offering=self.rob).order_by("start_time")
            self.assertEqual(
                [(row.kind, row.instructor_id) for row in moved],
                [("lecture", self.hamidova.pk), ("seminar", self.hamidova.pk)],
            )
            self.assertEqual(
                list(Lesson.objects.filter(offering=self.cih).values_list("pk", flat=True)), [self.cih_own.pk]
            )
            seminar = moved.get(kind="seminar")
            self.assertEqual(
                sorted(LessonMark.objects.filter(lesson=seminar).values_list("enrollment_id", "score"), key=str),
                sorted([(rob[0].pk, 9), (rob[1].pk, 6), (rob[2].pk, None)], key=str),
            )
            self.assertEqual(Enrollment.objects.get(pk=rob[0].pk).absence_hours, 2)
            self.assertEqual(Enrollment.objects.get(pk=cih[0].pk).absence_hours, 2)  # öz 26.09 qayıbı qalır
            self.assertEqual(Enrollment.objects.get(pk=rob[2].pk).absence_hours, 2)
            self.assertEqual(Enrollment.objects.get(pk=cih[2].pk).absence_hours, 0)
            self.assertFalse(JournalShare.objects.get(offering=self.cih, teacher=self.hamidova).is_active)
            self.assertTrue(JournalShare.objects.get(offering=self.cih, teacher=self.leman).is_active)
            self.assertEqual(AuditLog.objects.filter(resource_type=fix.RESOURCE, reason=fix.REASON).count(), 1)
        self.assertEqual(self._call("--file", self.plan, "--apply")["move_already_done"], "2")
        counts = self._call("--apply", "--undo")
        self.assertEqual((counts["undo_lessons_moved_back"], counts["undo_marks_moved_back"]), ("2", "5"))
        self.assertEqual(counts["undo_instructor_restored"], "1")
        self.assertEqual(self._state(), before)  # növ dəyişmələri, dərs müəllimi, xanalar, pay — hamısı geri
        with bypass_rls():
            self.assertEqual(Enrollment.objects.get(pk=rob[0].pk).absence_hours, 0)
            self.assertEqual(Enrollment.objects.get(pk=cih[0].pk).absence_hours, 4)
        self.assertEqual(self._call("--apply", "--undo")["undo_already"], "7")

    def test_undo_blocked_when_marks_changed_after_fix(self):
        self._call("--file", self.plan, "--apply")
        with bypass_rls():
            lesson = Lesson.objects.get(offering=self.rob, kind="lecture")
            LessonMark.objects.filter(lesson=lesson, status="absent").update(status="present")
            fiz = Lesson.objects.get(pk=self.fiz_lessons[0].pk)
            LessonMark.objects.create(
                organization=self.org, lesson=fiz, enrollment=self.enr[self.fiz.pk][2], status="present"
            )
        counts = self._call("--apply", "--undo")
        self.assertEqual(counts["undo_marks_changed_blocked"], "2")
        with bypass_rls():
            self.assertTrue(Lesson.objects.filter(pk=lesson.pk).exists())
            self.assertEqual(Lesson.objects.get(pk=fiz.pk).kind, "lab")

    def test_missing_target_enrollment_blocks_lesson_and_keeps_instructor(self):
        with bypass_rls():
            Enrollment.objects.filter(pk=self.enr[self.rob.pk][2].pk).update(status="dropped")
        counts = self._call("--file", self.plan, "--apply")
        self.assertEqual(counts["move_student_not_enrolled"], "1")  # yalnız seminarın 3-cü xanası
        self.assertEqual((counts["moved_lessons"], counts["move_lessons_blocked"]), ("1", "1"))
        self.assertEqual(counts["instructor_kept_moves_pending"], "1")
        with bypass_rls():
            self.assertTrue(Lesson.objects.filter(pk=self.cih_seminar.pk).exists())
            self.assertTrue(JournalShare.objects.get(offering=self.cih, teacher=self.hamidova).is_active)

    def test_closed_offering_blocks(self):
        with bypass_rls():
            type(self.rob).objects.filter(pk=self.rob.pk).update(is_active=False)
        counts = self._call("--file", self.plan, "--apply")
        self.assertEqual(counts["move_offering_closed"], "1")
        self.assertNotIn("moved_lessons", counts)

    # ── repo planı + qoşulma ────────────────────────────────────────────────
    def test_repo_plan_is_ids_only_and_reports_missing(self):
        data = fix.load_plan(fix.__file__.replace(".py", ".json"))
        allowed = {"legacy_journal", "offering", "date", "start_time", "from", "to", "source", "target"}
        allowed |= {"remove_source_instructor", "lessons", "kind"}
        keys = {key for row in data["kind_changes"] for key in row}
        keys |= {key for row in data["moves"] for key in row} | {
            k for row in data["moves"] for r in row["lessons"] for k in r
        }
        self.assertLessEqual(keys, allowed)
        self.assertEqual((len(data["kind_changes"]), len(data["moves"][0]["lessons"])), (5, 6))
        counts = self._call()
        self.assertEqual((counts["missing"], counts["kind_offering_missing"]), ("6", "5"))

    def test_workflow_wiring(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - fix_mexanika_lessons_20261108\n", text)
        self.assertIn('[ "$COMMAND" = "fix_mexanika_lessons_20261108" ]', text)
        self.assertIn("|merge_subgroup_journals_20261108|fix_mexanika_lessons_20261108)", text)
        self.assertIn("|mexanika_lessons|", text)
