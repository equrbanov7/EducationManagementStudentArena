"""RİM 2026-10-27 düzəliş əmrləri: ``relocate_twin_enrollment``, ``merge_twin_offerings``, ``fix_legacy_lesson_kinds``,
``fix_slot_week_parity`` — defolt dry-run, ``--apply``, idempotent, stdout yalnız saylar, audit.
"""

from __future__ import annotations

import datetime
import json
import pathlib
import re
import tempfile
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.registrar.models import (
    CourseOffering,
    Enrollment,
    JournalCorrection,
    Lesson,
    LessonMark,
    ScheduleSlot,
    Subject,
    WeekType,
)
from apps.registrar.tests.subgroup_base import SubgroupFixture
from apps.syllabus.models import Syllabus, SyllabusVersion
from core.audit import log_action
from core.constants import AuditAction
from core.rls import bypass_rls

WORKFLOW = pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml"
D = datetime.date
T = datetime.time
TEN_TEN = datetime.time(10, 10)


def _counts(text: str, prefix: str) -> dict:
    out = {}
    for line in text.splitlines():
        if line.startswith(prefix + " ") and "mode=" not in line:
            out.update(pair.split("=", 1) for pair in line[len(prefix) + 1 :].split())
    return out


class RimFixBase(SubgroupFixture, TestCase):
    PREFIX = "rimfix"

    @classmethod
    def setUpTestData(cls):
        cls.build_world()
        with bypass_rls():
            cls.owner.is_superuser = True
            cls.owner.save(update_fields=["is_superuser"])

    def _call(self, command, plan=None, *extra):
        args = ["--org", self.org.slug, "--actor", self.owner.username]
        if plan is not None:
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as handle:
                json.dump(plan, handle)
            args += ["--file", handle.name]
        out = StringIO()
        call_command(command, *args, *extra, stdout=out)
        return out.getvalue()

    def _lesson(self, offering, day, start=TEN_TEN, kind="seminar", created_by=None):
        return Lesson.objects.create(
            organization=self.org, offering=offering, date=day, start_time=start, kind=kind, created_by=created_by
        )

    def _mark(self, lesson, enrollment, status="present", score=None):
        return LessonMark.objects.create(
            organization=self.org, lesson=lesson, enrollment=enrollment, status=status, score=score
        )


class RelocateTwinEnrollmentTest(RimFixBase):
    """Uzaq qrupun tələbəsi delta ilə G1 Tarix jurnalına (W) düşüb; əsl jurnalı G2 Tarix (T)."""

    def setUp(self):
        with bypass_rls():
            self.wrong = Enrollment.objects.create(
                organization=self.org, student=self.far_student, offering=self.history_g1
            )
            self.real = self._lesson(self.own_history, D(2025, 10, 7))
            self.real_absent = self._lesson(self.own_history, D(2025, 10, 14))
            self.phantom = self._lesson(self.history_g1, D(2025, 10, 7))
            self.moved = self._mark(self.phantom, self.wrong, score=7)
            self.local = self._lesson(self.history_g1, D(2025, 10, 9), start=T(13, 35))
            self._mark(self.local, self.wrong, status="absent")
            self._mark(self.local, Enrollment.objects.get(student=self.host, offering=self.history_g1))
            self.old_created = self.moved.created_at - datetime.timedelta(days=10)
            LessonMark.objects.filter(pk=self.moved.pk).update(created_at=self.old_created)
        self.plan = {
            "format": "twin-relocate/1",
            "items": [
                {
                    "student": self.far_student.pk,
                    "source": str(self.wrong.pk),
                    "target_offering": str(self.own_history.pk),
                    "moves": [{"mark": str(self.moved.pk), "lesson": str(self.real.pk)}],
                    "restore": [{"lesson": str(self.real_absent.pk), "status": "absent"}],
                    "drop_source": True,
                }
            ],
        }

    def test_dry_run_apply_and_idempotent(self):
        dry = _counts(self._call("relocate_twin_enrollment", self.plan), "twin_relocate:")
        self.assertEqual((dry["marks_moved"], dry["lessons_deleted"], dry["sources_dropped"]), ("1", "1", "1"))
        with bypass_rls():
            self.assertTrue(LessonMark.objects.filter(pk=self.moved.pk).exists(), "dry-run yazmır")
        text = self._call("relocate_twin_enrollment", self.plan, "--apply")
        self.assertNotIn(self.far_student.username, text)
        with bypass_rls():
            target = Enrollment.objects.get(student=self.far_student, offering=self.own_history)
            mark = LessonMark.objects.get(enrollment=target, lesson=self.real)
            self.assertEqual((mark.status, mark.score), ("present", 7))
            self.assertEqual(mark.created_at, self.old_created, "redaktə pəncərəsi yenidən açılmır")
            self.assertTrue(
                LessonMark.objects.filter(enrollment=target, lesson=self.real_absent, status="absent").exists()
            )
            self.assertFalse(Lesson.objects.filter(pk=self.phantom.pk).exists(), "boşalan fantom dərs silinir")
            self.assertTrue(Lesson.objects.filter(pk=self.local.pk).exists())
            self.wrong.refresh_from_db()
            self.assertEqual((self.wrong.status, self.wrong.superseded_by_id), ("dropped", None))
            self.assertEqual(target.source_group_id, self.far_group.pk)
            # W-də qalan «qb» T-yə DAŞINMIR: yalnız bərpa olunan əsl qayıb (2 saat).
            self.assertEqual(target.absence_hours, 2)
            self.assertTrue(AuditLog.objects.filter(object_id=str(self.wrong.pk)).exists())
        again = _counts(self._call("relocate_twin_enrollment", self.plan, "--apply"), "twin_relocate:")
        self.assertEqual(again.get("marks_moved", "0"), "0")
        self.assertEqual(again.get("absences_restored", "0"), "0")
        self.assertNotIn("sources_dropped", again)

    def test_corrected_cell_and_closed_or_registry_source_are_kept(self):
        with bypass_rls():
            JournalCorrection.objects.bulk_create(
                [
                    JournalCorrection(
                        organization=self.org,
                        lesson_mark=self.moved,
                        lesson_mark_ref=self.moved.pk,
                        lesson_ref=self.phantom.pk,
                        enrollment_ref=self.wrong.pk,
                        field="score",
                        reason="other",
                        note="test",
                        document="x.pdf",
                        corrected_by_name="x",
                    )
                ]
            )
        counts = _counts(self._call("relocate_twin_enrollment", self.plan, "--apply"), "twin_relocate:")
        self.assertEqual(counts["mark_corrected_kept"], "1")
        with bypass_rls():
            self.assertTrue(LessonMark.objects.filter(pk=self.moved.pk).exists())
        # Tələbənin reyestr qrupunun (G2) jurnalı mənbədirsə — yeni sistemin qərarıdır, toxunulmur.
        with bypass_rls():
            own = Enrollment.objects.get(student=self.student, offering=self.own_history)
        item = dict(self.plan["items"][0], student=self.student.pk, source=str(own.pk))
        item["target_offering"] = str(self.history_g1.pk)
        counts = _counts(self._call("relocate_twin_enrollment", dict(self.plan, items=[item])), "twin_relocate:")
        self.assertEqual(counts["registry_group_is_source"], "1")


class MergeTwinOfferingsTest(RimFixBase):
    """Fizika (W, köhnə sistemin datası yanlış adla) → eyni qrupun boş «Kimya» açılışı (T: cədvəl slotu var)."""

    def setUp(self):
        with bypass_rls():
            self.chemistry = Subject.objects.create(organization=self.org, code="RIMKIM", name="Kimya", ects=5)
            self.target = CourseOffering.objects.create(
                organization=self.org, subject=self.chemistry, period=self.period, group=self.group1
            )
            ScheduleSlot.objects.create(
                organization=self.org, offering=self.target, weekday=2, start_time=T(10, 10), end_time=T(11, 40)
            )
            self.wrong_slot = ScheduleSlot.objects.create(
                organization=self.org, offering=self.physics_g1, weekday=4, start_time=T(8, 30), end_time=T(10, 0)
            )
            self.lesson = self._lesson(self.physics_g1, D(2025, 10, 7))
            source = Enrollment.objects.get(student=self.host, offering=self.physics_g1)
            self._mark(self.lesson, source, score=8)
            self.syllabus = Syllabus.objects.create(
                organization=self.org, subject=self.physics, period=self.period, offering=self.physics_g1
            )
        self.plan = {
            "format": "twin-merge/1",
            "pairs": [{"source": str(self.physics_g1.pk), "target": str(self.target.pk)}],
        }

    def test_merge_moves_everything_and_cancels_the_twin(self):
        dry = _counts(self._call("merge_twin_offerings", self.plan), "twin_merge:")
        self.assertEqual(dry["pairs_merged"], "1")
        with bypass_rls():
            self.assertTrue(CourseOffering.objects.get(pk=self.physics_g1.pk).is_active)
        self._call("merge_twin_offerings", self.plan, "--apply")
        with bypass_rls():
            self.physics_g1.refresh_from_db()
            self.assertFalse(self.physics_g1.is_active)
            lesson = Lesson.objects.get(offering=self.target)
            self.assertEqual((lesson.date, lesson.kind), (D(2025, 10, 7), "seminar"))
            mark = LessonMark.objects.get(lesson=lesson)
            self.assertEqual((mark.enrollment.student_id, mark.score), (self.host.pk, 8))
            self.assertFalse(Lesson.objects.filter(offering=self.physics_g1).exists())
            self.assertEqual(
                set(Enrollment.objects.filter(offering=self.physics_g1).values_list("status", flat=True)), {"dropped"}
            )
            self.syllabus.refresh_from_db()
            self.assertEqual((self.syllabus.offering_id, self.syllabus.subject_id), (self.target.pk, self.chemistry.pk))
            self.assertTrue(ScheduleSlot.all_objects.get(pk=self.wrong_slot.pk).is_deleted)
            self.assertEqual(ScheduleSlot.objects.filter(offering=self.target).count(), 1, "T-nin cədvəli qalır")
        again = _counts(self._call("merge_twin_offerings", self.plan, "--apply"), "twin_merge:")
        self.assertEqual(again, {"already_merged": "1", "pairs_in_file": "1"})

    def test_both_sides_with_marks_are_reported_not_merged(self):
        with bypass_rls():
            enrollment = Enrollment.objects.create(organization=self.org, student=self.host, offering=self.target)
            self._mark(self._lesson(self.target, D(2025, 10, 8)), enrollment)
        counts = _counts(self._call("merge_twin_offerings", self.plan, "--apply"), "twin_merge:")
        self.assertEqual(counts["both_have_marks"], "1")
        with bypass_rls():
            self.assertTrue(CourseOffering.objects.get(pk=self.physics_g1.pk).is_active)


class FixLegacyLessonKindsTest(RimFixBase):
    def _approved(self, plan_hours):
        now = timezone.now()
        syllabus = Syllabus.objects.create(
            organization=self.org, subject=self.physics, period=self.period, offering=self.physics_g1
        )
        version = SyllabusVersion.objects.create(
            organization=self.org,
            syllabus=syllabus,
            status="approved",
            locked_at=now,
            approved_at=now,
            approved_by=self.owner,
            plan_hours=plan_hours,
        )
        syllabus.approved_version = version
        syllabus.save(update_fields=["approved_version", "updated_at"])

    def setUp(self):
        with bypass_rls():
            self.lesson = self._lesson(self.physics_g1, D(2025, 10, 7))
            self.teacher_lesson = self._lesson(self.physics_g1, D(2025, 10, 14), created_by=self.teacher)
            self.slot = ScheduleSlot.objects.create(
                organization=self.org,
                offering=self.physics_g1,
                weekday=2,
                start_time=T(10, 10),
                end_time=T(11, 40),
                kind="seminar",
            )
        self.plan = {"format": "legacy-lesson-kinds/1", "lessons": [str(self.lesson.pk), str(self.teacher_lesson.pk)]}

    def test_lab_only_plan_switches_lessons_and_slots(self):
        with bypass_rls():
            self._approved({"lecture": 30, "lab": 30})
        self._call("fix_legacy_lesson_kinds", self.plan)
        with bypass_rls():
            self.assertEqual(Lesson.objects.get(pk=self.lesson.pk).kind, "seminar")
        counts = _counts(self._call("fix_legacy_lesson_kinds", self.plan, "--apply"), "lesson_kinds:")
        self.assertEqual((counts["lessons_set_lab"], counts["slots_set_lab"]), ("1", "1"))
        with bypass_rls():
            self.assertEqual(Lesson.objects.get(pk=self.lesson.pk).kind, "lab")
            self.assertEqual(Lesson.objects.get(pk=self.teacher_lesson.pk).kind, "seminar", "müəllimin dərsi qalır")
            self.assertEqual(ScheduleSlot.objects.get(pk=self.slot.pk).kind, "lab")
        again = _counts(self._call("fix_legacy_lesson_kinds", self.plan, "--apply"), "lesson_kinds:")
        self.assertNotIn("lessons_set_lab", again)

    def test_mixed_plan_needs_flag_and_keeps_slots(self):
        with bypass_rls():
            self._approved({"lecture": 30, "seminar": 15, "lab": 15})
        counts = _counts(self._call("fix_legacy_lesson_kinds", self.plan, "--apply"), "lesson_kinds:")
        self.assertEqual(counts["offering_mixed_plan_skipped"], "1")
        self._call("fix_legacy_lesson_kinds", self.plan, "--apply", "--include-mixed")
        with bypass_rls():
            self.assertEqual(Lesson.objects.get(pk=self.lesson.pk).kind, "lab")
            self.assertEqual(ScheduleSlot.objects.get(pk=self.slot.pk).kind, "seminar")


class FixSlotWeekParityTest(RimFixBase):
    def setUp(self):
        with bypass_rls():
            self.weekly = ScheduleSlot.objects.create(
                organization=self.org,
                offering=self.physics_g1,
                weekday=2,
                start_time=T(10, 10),
                end_time=T(11, 40),
                kind="seminar",
                week_type=WeekType.EVEN,
            )
            self.alternate = ScheduleSlot.objects.create(
                organization=self.org,
                offering=self.physics_g1,
                weekday=4,
                start_time=T(10, 10),
                end_time=T(11, 40),
                kind="seminar",
                week_type=WeekType.ODD,
            )
            self.official = ScheduleSlot.objects.create(
                organization=self.org,
                offering=self.history_g1,
                weekday=5,
                start_time=T(10, 10),
                end_time=T(11, 40),
                kind="seminar",
                week_type=WeekType.EVEN,
            )
            log_action(
                action=AuditAction.UPDATE,
                organization=self.org,
                new_values={"created_ids": [str(self.weekly.pk), str(self.alternate.pk)]},
                resource_type="registrar.ScheduleSlot",
                resource_id="infer_timetable_from_lessons",
            )
            # Ç.a. 10:10 — 2, 3, 4, 6-cı həftələr (bir həftə buraxılıb) → hər həftə; C.a. — 1, 3, 5 → üst qalır.
            for day in (D(2025, 9, 9), D(2025, 9, 16), D(2025, 9, 23), D(2025, 10, 7)):
                self._lesson(self.physics_g1, day)
            for day in (D(2025, 9, 4), D(2025, 9, 18), D(2025, 10, 2)):
                self._lesson(self.physics_g1, day)
            for day in (D(2025, 9, 5), D(2025, 9, 12), D(2025, 9, 19)):
                self._lesson(self.history_g1, day)

    def test_only_inferred_slots_with_consecutive_weeks_become_weekly(self):
        args = ("--period", str(self.period.pk))
        dry = _counts(self._call("fix_slot_week_parity", None, *args), "slot_parity:")
        self.assertEqual((dry["slots_set_weekly"], dry["alternate_confirmed"]), ("1", "1"))
        self._call("fix_slot_week_parity", None, *args, "--apply")
        with bypass_rls():
            self.assertEqual(ScheduleSlot.objects.get(pk=self.weekly.pk).week_type, WeekType.ALL)
            self.assertEqual(ScheduleSlot.objects.get(pk=self.alternate.pk).week_type, WeekType.ODD)
            self.assertEqual(ScheduleSlot.objects.get(pk=self.official.pk).week_type, WeekType.EVEN, "rəsmi slot")
            self.assertTrue(AuditLog.objects.filter(resource_id="fix_slot_week_parity").exists())
        again = _counts(self._call("fix_slot_week_parity", None, *args, "--apply"), "slot_parity:")
        self.assertEqual(again["slots_set_weekly"], "0")


class RimFixWorkflowTest(TestCase):
    def test_workflow_whitelists_commands_and_filters_counts(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        for command in (
            "relocate_twin_enrollment",
            "merge_twin_offerings",
            "fix_legacy_lesson_kinds",
            "fix_slot_week_parity",
        ):
            self.assertIn(f"          - {command}\n", text)
        pattern = re.search(r"grep -E '(\^\(twin_relocate[^']+)'", text).group(1)
        for line in (
            "twin_relocate: mode=apply",
            "twin_merge: pairs_merged=23 both_have_marks=2",
            "lesson_kinds: lessons_set_lab=65",
            "slot_parity: slots_set_weekly=46 conflict_kept=13",
        ):
            self.assertRegex(line, pattern)
        self.assertNotRegex("twin_relocate: name=Əli Vəli", pattern)

    def test_mr27_workflow_builds_sealed_plan_and_explicit_undo_arguments(self):
        import os
        import subprocess

        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("          - recover_mr27_journal\n", text)
        self.assertIn("asset=mr27-recovery.json.enc", text)
        self.assertIn("'^mr27-recovery-[0-9a-z-]+$'", text)
        self.assertIn("!startsWith(github.event.inputs.batch, 'mr27-')", text)
        self.assertIn("/tmp/mr27_recovery_*.json", text)
        block = re.findall(
            r"            recover_mr27_journal\)\n(              actor=.*?)              ;;", text, re.S
        )[0]
        script = (
            "set -euo pipefail\n"
            "match() { case \"$1\" in (*$'\\n'*|*$'\\r'*) return 1 ;; esac; "
            'printf \'%s\' "$1" | grep -Eq -- "$2"; }\n'
            "superadmin_actor() { printf 'fixture-actor'; }\n" + block + '\nprintf "ARG:%s\\n" "${args[@]}"\n'
        )

        def run(batch, apply="false", tag="", teacher_assertion="false"):
            return subprocess.run(
                ["bash", "-c", script],
                env={
                    **os.environ,
                    "BATCH": batch,
                    "APPLY": apply,
                    "ROSTER_TAG": tag,
                    "CREATE_MISSING": teacher_assertion,
                    "ORG": "qku",
                    "GITHUB_RUN_ID": "123",
                },
                capture_output=True,
                text=True,
                check=False,
            )

        plan = run("a" * 64, tag="mr27-recovery-fixture")
        self.assertEqual(plan.returncode, 0, plan.stderr)
        self.assertIn("ARG:--file\nARG:/tmp/mr27_recovery_123.json\nARG:--sha256\nARG:" + "a" * 64, plan.stdout)
        self.assertNotIn("ARG:--apply", plan.stdout, "dry-run is the default")
        self.assertNotIn("ARG:--include-teacher-assertion", plan.stdout)
        teacher_plan = run("a" * 64, tag="mr27-recovery-fixture", teacher_assertion="true")
        self.assertEqual(teacher_plan.returncode, 0, teacher_plan.stderr)
        self.assertIn("ARG:--include-teacher-assertion", teacher_plan.stdout)
        undo = run("mr27-20261028-235959-abcd", "true")
        self.assertEqual(undo.returncode, 0, undo.stderr)
        self.assertIn("ARG:--undo\nARG:mr27-20261028-235959-abcd", undo.stdout)
        self.assertNotIn("ARG:--file", undo.stdout)
        undo_with_toggle = run("mr27-20261028-235959-abcd", "true", teacher_assertion="true")
        self.assertNotIn("ARG:--include-teacher-assertion", undo_with_toggle.stdout)
        for batch, apply, tag in [
            ("", "false", ""),
            ("a" * 64 + "\ninjected", "false", ""),
            ("mr27-20261028-235959-abcd", "false", ""),
            ("mr27-20261028-235959-abcd", "true", "mr27-recovery-fixture"),
            ("mr27-invalid", "true", ""),
        ]:
            self.assertNotEqual(run(batch, apply, tag).returncode, 0)

    def test_mr27_workflow_filters_private_output(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        pattern = re.search(r"grep -E '(\^mr27_recovery:[^']+)'", text).group(1)
        self.assertRegex(
            "mr27_recovery: mode=apply students_created=2 marks_created=15 batch=mr27-20261028-235959-abcd", pattern
        )
        self.assertNotRegex("mr27_recovery: username=private.name password=Secret!", pattern)
        self.assertNotRegex("mr27_recovery: name=Real Person", pattern)
