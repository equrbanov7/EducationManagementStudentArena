"""Sahib 2026-10-25: «payızda vakantda olanlar olmamalıdır — köhnə sistemdən dəqiqləşdirməyə çalış, datadan ki
bunu kim keçir. Boş olmasın.»

``fill_vacant_from_journals``: vakant saat — həmin NÖVÜ jurnalda keçən müəllimə (yeni jurnalın müəllimli dərsləri,
yoxdursa köhnə jurnalın müəllimi + elan etdiyi növlər); çoxluq ≥ 75 %; ziddiyyət / sübutsuz → toxunulmur; dry-run
yazmır; idempotent; kənar müəllim kafedraya əlavə üzv + saathesabı; bildiriş yalnız yükü dəyişənə bir dəfə;
``--undo`` bölgünü, açılışın müəllimini və üzvlüyü əvvəlki halına qaytarır.
"""

from __future__ import annotations

import io
import json
import os
import stat
import tempfile
from datetime import date

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase

from apps.legacy_import.services.delta.journal_teachers import _kinds
from apps.notifications.models import InAppNotification
from apps.organizations.models import Membership
from apps.registrar.models import CourseOffering, Lesson
from apps.workload.constants import Activity, TaskStatus
from apps.workload.models import TeacherAssignment, WorkloadAmendment
from apps.workload.services.vacant_fill import LEGACY_FORMAT
from apps.workload.services.vacant_fill_apply import NOTE
from core.constants import RoleScopeType

from .factories import TEACHER_PERMS, YEAR, activate_member, make_org, make_row, make_structure, make_task

User = get_user_model()


class LegacyKindCodesTests(SimpleTestCase):
    def test_sem_muh_codes(self):
        self.assertEqual(_kinds('["0","1"]'), ["lecture", "seminar"])
        self.assertEqual(_kinds('["2"]'), ["lab"])
        self.assertEqual(_kinds('["3"]'), ["seminar"])
        self.assertEqual(_kinds("pozuq"), [])


class VacantFillCommandTests(TestCase):
    def setUp(self):
        self.org = make_org("wl-vacant")
        self.stack = make_structure(self.org, code="VAC")
        self.other_stack = make_structure(self.org, code="VAO")
        self.admin = User.objects.create_user("vf_admin", "vf@x.test", "pw", is_superuser=True, is_staff=True)
        self.lecturer = User.objects.create_user("vf_l", "l@x.test", "pw", first_name="Natəvan", last_name="Test")
        self.seminarist = User.objects.create_user("vf_s", "s@x.test", "pw", first_name="Ləman", last_name="Test")
        self.outsider = User.objects.create_user("vf_o", "o@x.test", "pw", first_name="Şaban", last_name="Kənar")
        for user, chair in (
            (self.lecturer, self.stack["chair"]),
            (self.seminarist, self.stack["chair"]),
            (self.outsider, self.other_stack["chair"]),
        ):
            activate_member(
                self.org, user, "teacher", permissions=TEACHER_PERMS, scope_unit=chair, scope_type=RoleScopeType.COURSE
            )
        self.task = make_task(self.org, self.stack["chair"], status=TaskStatus.DISTRIBUTED)
        self.row = make_row(self.task, self.stack, lecture_total=30, seminar_total=15)
        for activity, hours in ((Activity.LECTURE, 30), (Activity.SEMINAR, 15)):
            TeacherAssignment.objects.create(
                organization=self.org, row=self.row, teacher=None, activity=activity, hours=hours
            )
        # Köhnə sistemdən köçmüş açılış: sahibi mühazirəçi, dərslərin müəllimi BOŞ.
        self.offering = CourseOffering.objects.create(
            organization=self.org,
            subject=self.stack["subject"],
            period=self.stack["period"],
            group=self.stack["group"],
            instructor=self.lecturer,
            lesson_hours=45,
        )
        for day, kind in ((1, "lecture"), (2, "seminar"), (8, "lecture"), (9, "seminar")):
            Lesson.objects.create(organization=self.org, offering=self.offering, date=date(2026, 9, day), kind=kind)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    # ── köməkçilər ────────────────────────────────────────────────────────
    def _legacy(self, *journals) -> str:
        path = os.path.join(self.tmp.name, "legacy.json")
        rows = [
            {
                "legacy_id": index,
                "subject_id": str(self.stack["subject"].pk),
                "group_ids": [str(self.stack["group"].pk)],
                "teacher_id": teacher.pk if teacher else None,
                "teacher_status": "ledger",
                "kinds": kinds,
                "dates": dates,
                "active": True,
            }
            for index, (teacher, kinds, dates) in enumerate(journals, 1)
        ]
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"format": LEGACY_FORMAT, "journals": rows}, handle)
        return path

    def _run(self, *extra, legacy="", report="", notify=False):
        out = io.StringIO()
        args = ["fill_vacant_from_journals", "--org", self.org.slug, "--year", YEAR, "--actor", "vf_admin"]
        args += ["--legacy-journals", legacy] if legacy else []
        args += ["--report", report] if report else []
        args += [] if notify else ["--no-notify"]
        call_command(*args, *extra, stdout=out)
        return out.getvalue()

    @staticmethod
    def _count(output: str, key: str) -> int:
        return int(output.split(f" {key}=")[1].split()[0])

    def _teacher(self, activity):
        return TeacherAssignment.objects.get(row=self.row, activity=activity).teacher

    # ── testlər ───────────────────────────────────────────────────────────
    def test_legacy_kinds_split_lecture_and_seminar_dry_run_apply_rerun_undo(self):
        legacy = self._legacy((self.lecturer, ["lecture"], 5), (self.seminarist, ["seminar"], 6))
        report = os.path.join(self.tmp.name, "vacant.md")

        dry = self._run(legacy=legacy, report=report)
        self.assertEqual(self._count(dry, "pairs_fill"), 2)
        self.assertIsNone(self._teacher(Activity.LECTURE))  # dry-run heç nə yazmır
        self.assertEqual(stat.S_IMODE(os.stat(report).st_mode), 0o600)
        with open(report, encoding="utf-8") as handle:
            self.assertIn("Ləman Test", handle.read())
        self.assertNotIn("Ləman", dry)  # stdout-a ad düşmür

        applied = self._run("--apply", legacy=legacy)
        self.assertEqual(self._count(applied, "pairs_filled"), 2)
        self.assertEqual(self._count(applied, "vacant_hours_after"), 0)
        self.assertEqual(self._teacher(Activity.LECTURE), self.lecturer)
        self.assertEqual(self._teacher(Activity.SEMINAR), self.seminarist)  # köhnə jurnal: seminar BAŞQASINDADIR
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.DISTRIBUTED)
        amendment = WorkloadAmendment.objects.get(target_id=self.row.pk)
        self.assertIn(NOTE, amendment.note)
        self.assertEqual(amendment.reason, "correction")
        self.offering.refresh_from_db()
        self.assertEqual(self.offering.instructor, self.lecturer)

        again = self._run("--apply", legacy=legacy)
        self.assertEqual(self._count(again, "pairs_filled"), 0)

        batch = applied.split("batch=")[1].split()[0]
        undone = self._run("--undo", batch, "--apply")
        self.assertIn("pairs_restored=2", undone)
        self.assertIsNone(self._teacher(Activity.LECTURE))
        self.assertIsNone(self._teacher(Activity.SEMINAR))
        self.offering.refresh_from_db()
        self.assertEqual(self.offering.instructor, self.lecturer)  # köhnə jurnaldan gələn sahib bərpa olunur
        self.assertIn("already_undone=1", self._run("--undo", batch, "--apply"))

    def test_lessons_without_instructor_are_not_evidence(self):
        output = self._run("--apply")
        self.assertEqual(self._count(output, "pairs_filled"), 0)
        self.assertEqual(self._count(output, "pairs_kind_missing"), 2)
        self.assertIsNone(self._teacher(Activity.LECTURE))

    def test_new_journal_lessons_with_instructor_majority_and_conflict(self):
        Lesson.objects.filter(offering=self.offering).delete()
        for day in (1, 2, 3, 4):
            Lesson.objects.create(
                organization=self.org, offering=self.offering, date=date(2026, 9, day), kind="lecture",
                instructor=self.lecturer,
            )  # fmt: skip
        Lesson.objects.create(
            organization=self.org, offering=self.offering, date=date(2026, 9, 5), kind="lecture",
            instructor=self.seminarist,
        )  # fmt: skip
        for day, who in ((6, self.lecturer), (7, self.seminarist)):
            Lesson.objects.create(
                organization=self.org, offering=self.offering, date=date(2026, 9, day), kind="seminar", instructor=who
            )
        # Köhnə jurnal başqa deyir — yeni sistemin müəllimli dərsi üstündür.
        legacy = self._legacy((self.seminarist, ["lecture", "seminar"], 9))
        output = self._run("--apply", legacy=legacy)
        self.assertEqual(self._count(output, "pairs_fill_lessons"), 1)
        self.assertEqual(self._count(output, "pairs_conflict"), 1)
        self.assertEqual(self._teacher(Activity.LECTURE), self.lecturer)  # 4/5 = 80 %
        self.assertIsNone(self._teacher(Activity.SEMINAR))  # 1/2 — ziddiyyət

    def test_outside_teacher_joins_chair_hourly_and_undo_deactivates(self):
        legacy = self._legacy((self.outsider, ["lecture", "seminar"], 7))
        # Jurnalın sahibi BAŞQA müəllimdir (köhnə sistemdən / təhvildən) — sahibə toxunulmur, yazı bloklanır.
        blocked = self._run("--apply", legacy=legacy)
        self.assertEqual(self._count(blocked, "pairs_blocked"), 2)
        self.assertIsNone(self._teacher(Activity.LECTURE))
        self.assertFalse(Membership.objects.filter(user=self.outsider, scope_unit=self.stack["chair"]).exists())

        CourseOffering.objects.filter(pk=self.offering.pk).update(instructor=None)
        applied = self._run("--apply", legacy=legacy)
        self.assertEqual(self._count(applied, "pairs_filled_outside_chair"), 2)
        self.assertEqual(self._count(applied, "memberships_added"), 1)
        assignment = TeacherAssignment.objects.get(row=self.row, activity=Activity.LECTURE)
        self.assertEqual(assignment.teacher, self.outsider)
        self.assertTrue(assignment.is_hourly_paid)
        joined = Membership.objects.get(organization=self.org, user=self.outsider, scope_unit=self.stack["chair"])
        self.assertTrue(joined.is_active)
        self.assertFalse(joined.is_primary)

        batch = applied.split("batch=")[1].split()[0]
        self._run("--undo", batch, "--apply")
        joined.refresh_from_db()
        self.assertFalse(joined.is_active)
        assignment.refresh_from_db()
        self.assertIsNone(assignment.teacher)
        self.assertFalse(assignment.is_hourly_paid)

    def test_blocked_and_ambiguous_evidence_untouched(self):
        self.seminarist.is_active = False
        self.seminarist.save(update_fields=["is_active"])
        legacy = self._legacy(
            (self.lecturer, ["lecture"], 3), (self.seminarist, ["lecture"], 3), (self.seminarist, ["seminar"], 4)
        )
        output = self._run("--apply", legacy=legacy)
        self.assertEqual(self._count(output, "pairs_conflict"), 1)  # mühazirə 3 : 3
        self.assertEqual(self._count(output, "pairs_teacher_blocked"), 1)
        self.assertEqual(self._count(output, "pairs_filled"), 0)

    def test_lab_from_practical_journal_when_row_has_no_seminar(self):
        lab_row = make_row(self.task, self.other_stack, lecture_total=0, seminar_total=0, lab_total=30)
        lab_row.subject = self.stack["subject"]
        lab_row.save(update_fields=["subject"])
        lab_row.groups.set([self.stack["group"]])
        TeacherAssignment.objects.create(organization=self.org, row=lab_row, teacher=None, activity="lab", hours=30)
        legacy = self._legacy((self.seminarist, ["seminar"], 4))
        self._run("--apply", legacy=legacy)
        self.assertEqual(TeacherAssignment.objects.get(row=lab_row, activity="lab").teacher, self.seminarist)

    def test_notification_once_per_changed_teacher(self):
        legacy = self._legacy((self.lecturer, ["lecture"], 5), (self.seminarist, ["seminar"], 6))
        before = {u.pk: _notified(u) for u in (self.lecturer, self.seminarist, self.outsider)}
        self._run("--apply", legacy=legacy, notify=True)
        self.assertEqual(_notified(self.lecturer) - before[self.lecturer.pk], 1)
        self.assertEqual(_notified(self.seminarist) - before[self.seminarist.pk], 1)
        self.assertEqual(_notified(self.outsider), before[self.outsider.pk])

    def test_bad_legacy_file_fails_closed(self):
        path = os.path.join(self.tmp.name, "bad.json")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"format": "nope"}, handle)
        with self.assertRaises(CommandError):
            self._run(legacy=path)


def _notified(user) -> int:
    return InAppNotification.objects.filter(recipient=user, metadata__event="workload_assigned").count()


class VacantFillWorkflowTests(SimpleTestCase):
    def test_prod_data_ops_whitelists_command_with_counts_only_log(self):
        import pathlib
        import re

        text = (pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows" / "prod-data-ops.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("          - fill_vacant_from_journals\n", text)
        block = text.split("            fill_vacant_from_journals)\n              # Sahib")[1].split(";;")[0]
        self.assertIn('--report "/tmp/vacant_fill_report_${GITHUB_RUN_ID}.md"', block)
        self.assertIn("--legacy-journals", block)
        self.assertIn("--undo", block)
        self.assertIn("--no-notify", block)
        self.assertIn("^legacy-journals-[0-9a-z-]+$", text)
        pattern = re.compile(r"^vacantfill: [a-z_]+=[0-9a-z_-]+( [a-z_]+=[0-9a-z_-]+)*$")
        self.assertIn(pattern.pattern, text.replace("'", ""))
        for line in (
            "vacantfill: mode=apply pairs_fill=167 hours_filled=4800 vacant_hours_after=3575",
            "vacantfill: batch=vacantfill-20261025-193513-b6ce",
        ):
            self.assertRegex(line, pattern)
        self.assertNotRegex("vacantfill: teacher=Ləman Orucova", pattern)
