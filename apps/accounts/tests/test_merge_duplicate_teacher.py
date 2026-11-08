"""``merge_duplicate_teacher`` (sahib 2026-11-08): müəllimin dublikat hesabı → əsas hesab, heç nə itmir."""

from __future__ import annotations

import datetime
import io
import re

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase
from django.utils import timezone

from apps.accounts.services.teacher_merge import policy
from apps.audit.models import AuditLog
from apps.notifications.models import InAppNotification
from apps.organizations.models import Membership
from apps.registrar.models import CourseOffering, JournalShare, Lesson, LessonMark
from apps.registrar.tests.journal_load_fixtures import seed_current_journal_load
from apps.registrar.tests.test_journal_shares_2026_10_26 import User, _add_teacher, _ShareBase
from apps.syllabus.models import Syllabus, SyllabusVersion
from apps.workload.models import TeacherAssignment, TeacherWorkloadProfile
from core.rls import bypass_rls

LINE_RE = re.compile(r"^teacher_merge: [a-z_]+=[0-9a-z_-]+( [a-z_]+=[0-9a-z_-]+)*$")


class TeacherMergePolicyTest(SimpleTestCase):
    def test_every_user_relation_is_classified_and_no_stale_entries(self):
        self.assertEqual(policy.unclassified(), [])
        self.assertEqual(policy.stale(), [])


class MergeDuplicateTeacherTest(_ShareBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            cls.admin = User.objects.create_superuser("tmg_admin", "tmg_admin@qku.edu.az", "pw")
            cls.source = cls.teacher  # köhnə sistemin hesabı — jurnalın müəllimi
            cls.target = cls.seminarist  # əsas hesab — dərs yükündədir
            cls.extra_role = cls.org.roles.exclude(name__in=["teacher", "student"]).filter(is_active=True).first()
            cls.extra = Membership.objects.create(
                user=cls.source, organization=cls.org, role=cls.extra_role, is_active=True
            )
            Lesson.objects.filter(pk=cls.lecture.pk).update(instructor=cls.source, created_by=cls.source)
            cls.mark = LessonMark.objects.create(
                organization=cls.org, lesson=cls.lecture, enrollment=cls.e1, status="present", entered_by=cls.source
            )
            # 2 saatlıq jurnal qoruyucusu: köhnə xana — müəllif sahəsi yalnız journal_unlock ilə dəyişir.
            LessonMark.objects.filter(pk=cls.mark.pk).update(created_at=timezone.now() - datetime.timedelta(hours=5))
            cls.syllabus = Syllabus.objects.create(
                organization=cls.org, subject=cls.subject, offering=cls.offering, author=cls.source
            )
            cls.version = SyllabusVersion.objects.create(
                organization=cls.org, syllabus=cls.syllabus, major=1, minor=0, created_by=cls.source
            )
            cls.base_source = Syllabus.objects.create(organization=cls.org, subject=cls.subject, author=cls.source)
            cls.base_target = Syllabus.objects.create(organization=cls.org, subject=cls.subject, author=cls.target)
            cls.row = seed_current_journal_load(cls.offering, teacher=cls.source, kinds=("lecture",))
            seed_current_journal_load(cls.offering, teacher=cls.target, kinds=("seminar",))
            cls.profile_old = TeacherWorkloadProfile.objects.create(
                organization=cls.org, teacher=cls.source, academic_year="2025/2026"
            )
            cls.profile_clash = TeacherWorkloadProfile.objects.create(
                organization=cls.org, teacher=cls.source, academic_year="2026/2027"
            )
            TeacherWorkloadProfile.objects.create(organization=cls.org, teacher=cls.target, academic_year="2026/2027")
            cls.note = InAppNotification.objects.create(recipient=cls.source, organization=cls.org, title="x")
            # Eyni jurnalda hər iki hesab: mənbə payısız sahib (TAM), hədəfin seminar payı.
            cls.target_share = JournalShare.objects.create(
                organization=cls.org, offering=cls.offering, teacher=cls.target, kinds=["seminar"]
            )
            cls.target_share.enrollments.set([cls.e2])
            AuditLog.objects.create(organization=cls.org, user=cls.source, action="update", resource_type="x")

    def _run(self, *args):
        out = io.StringIO()
        call_command("merge_duplicate_teacher", "--org", self.org.slug, "--actor", self.admin.username, *args,
                     stdout=out)  # fmt: skip
        counts = {}
        for line in out.getvalue().splitlines():
            self.assertRegex(line, LINE_RE)  # stdout-a YALNIZ saylar
            for pair in line.split(" ")[1:]:
                key, value = pair.split("=")
                counts[key] = value
        return counts

    def _pair(self):
        return ("--source", str(self.source.pk), "--target", str(self.target.pk))

    def _snapshot(self):
        with bypass_rls():
            return {
                "offering": CourseOffering.objects.get(pk=self.offering.pk).instructor_id,
                "lesson": Lesson.objects.values_list("instructor_id", "created_by_id").get(pk=self.lecture.pk),
                "mark": LessonMark.objects.get(pk=self.mark.pk).entered_by_id,
                "syllabus": Syllabus.objects.get(pk=self.syllabus.pk).author_id,
                "version": SyllabusVersion.objects.get(pk=self.version.pk).created_by_id,
                "assignments": sorted(
                    TeacherAssignment.objects.filter(row=self.row).values_list("teacher_id", flat=True)
                ),
                "note": InAppNotification.objects.get(pk=self.note.pk).recipient_id,
                "share": JournalShare.objects.values_list("teacher_id", "is_active").get(pk=self.target_share.pk),
                "source_active": User.objects.get(pk=self.source.pk).is_active,
                "memberships": sorted(
                    Membership.objects.filter(user__in=[self.source, self.target]).values_list(
                        "user_id", "role__name", "is_active"
                    )
                ),
            }

    def test_dry_run_writes_nothing_and_reports_same_counts(self):
        before = self._snapshot()
        dry = self._run(*self._pair())
        self.assertEqual((dry["mode"], dry["merged"]), ("dry_run", "1"))
        self.assertEqual(self._snapshot(), before)
        with bypass_rls():
            self.assertFalse(AuditLog.objects.filter(resource_type="accounts.teacher_merge_batch").exists())
        applied = self._run(*self._pair(), "--apply")
        applied.pop("batch")
        self.assertEqual({**dry, "mode": "apply"}, applied)

    def test_apply_moves_everything_then_undo_restores(self):
        before = self._snapshot()
        counts = self._run(*self._pair(), "--apply")
        self.assertEqual(counts["moved_registrar_courseoffering_instructor"], "1")
        self.assertEqual(counts["moved_registrar_lessonmark_entered_by"], "1")
        self.assertEqual(counts["collision_syllabus_syllabus_author"], "1")  # baza sillabus — qalır, sayılır
        self.assertEqual(counts["collision_workload_teacherworkloadprofile_teacher"], "1")
        self.assertEqual(counts["moved_workload_teacherworkloadprofile_teacher"], "1")
        self.assertEqual(counts["shares_owner_full_deactivated"], "1")
        self.assertEqual((counts["source_blocked"], counts["memberships_created"]), ("1", "1"))
        self.assertEqual(counts["kept_audit_auditlog_user"], "1")
        self.assertEqual(counts.get("rows_blocked_kept"), "0")
        with bypass_rls():
            self.assertEqual(CourseOffering.objects.get(pk=self.offering.pk).instructor_id, self.target.pk)
            lesson = Lesson.objects.get(pk=self.lecture.pk)
            self.assertEqual((lesson.instructor_id, lesson.created_by_id), (self.target.pk, self.target.pk))
            mark = LessonMark.objects.get(pk=self.mark.pk)
            self.assertEqual((mark.entered_by_id, mark.status), (self.target.pk, "present"))  # bal dəyişmir
            self.assertEqual(Syllabus.objects.get(pk=self.syllabus.pk).author_id, self.target.pk)
            self.assertEqual(SyllabusVersion.objects.get(pk=self.version.pk).created_by_id, self.target.pk)
            self.assertEqual(Syllabus.objects.get(pk=self.base_source.pk).author_id, self.source.pk)  # silinmir
            self.assertEqual(TeacherWorkloadProfile.objects.get(pk=self.profile_old.pk).teacher_id, self.target.pk)
            self.assertEqual(TeacherWorkloadProfile.objects.get(pk=self.profile_clash.pk).teacher_id, self.source.pk)
            self.assertEqual(
                set(TeacherAssignment.objects.filter(row=self.row).values_list("teacher_id", flat=True)),
                {self.target.pk},
            )
            self.assertEqual(InAppNotification.objects.get(pk=self.note.pk).recipient_id, self.target.pk)
            self.assertFalse(JournalShare.objects.get(pk=self.target_share.pk).is_active)  # sahib → TAM
            self.assertTrue(Membership.objects.filter(user=self.target, role=self.extra_role, is_active=True).exists())
            self.assertFalse(Membership.objects.filter(user=self.source, is_active=True).exists())
            source = User.objects.get(pk=self.source.pk)
            self.assertFalse(source.is_active)  # bloklanır, silinmir
        again = self._run(*self._pair(), "--apply")
        self.assertEqual((again["merged"], again["rows_moved"]), ("0", "0"))
        undo = self._run("--undo", counts["batch"], "--apply")
        self.assertEqual(undo["undo_unblocked"], "1")
        self.assertEqual(undo.get("undo_rows_blocked", "0"), "0")
        self.assertEqual(self._snapshot(), before)
        with self.assertRaises(CommandError):
            self._run("--undo", counts["batch"], "--apply")

    def test_both_accounts_share_one_journal_collapse_keeps_both_roles(self):
        with bypass_rls():
            stranger = self.stranger
            CourseOffering.objects.filter(pk=self.offering.pk).update(instructor=stranger)
            source_share = JournalShare.objects.create(
                organization=self.org, offering=self.offering, teacher=self.source, kinds=["lecture"]
            )
            source_share.enrollments.set([self.e1])
        counts = self._run(*self._pair(), "--apply")
        self.assertEqual(counts["shares_collapsed"], "1")
        with bypass_rls():
            merged = JournalShare.objects.get(pk=self.target_share.pk)
            self.assertTrue(merged.is_active)
            self.assertEqual(sorted(merged.kinds), ["lecture", "seminar"])  # mühazirə + seminar
            self.assertEqual(set(merged.enrollments.values_list("pk", flat=True)), {self.e1.pk, self.e2.pk})
            self.assertFalse(JournalShare.objects.get(pk=source_share.pk).is_active)
            self.assertEqual(
                JournalShare.objects.filter(offering=self.offering, teacher=self.target, is_active=True).count(), 1
            )
        self._run("--undo", counts["batch"], "--apply")
        with bypass_rls():
            self.assertEqual(JournalShare.objects.get(pk=self.target_share.pk).kinds, ["seminar"])
            self.assertEqual(
                set(JournalShare.objects.get(pk=self.target_share.pk).enrollments.values_list("pk", flat=True)),
                {self.e2.pk},
            )
            self.assertTrue(JournalShare.objects.get(pk=source_share.pk).is_active)

    def test_guards_refuse(self):
        with self.assertRaisesMessage(CommandError, "same_user"):
            self._run("--source", str(self.target.pk), "--target", str(self.target.pk))
        with self.assertRaisesMessage(CommandError, "source_is_student"):
            self._run("--source", str(self.student.pk), "--target", str(self.target.pk))
        with self.assertRaisesMessage(CommandError, "target_is_student"):
            self._run("--source", str(self.source.pk), "--target", str(self.student.pk))
        with bypass_rls():
            inactive = _add_teacher(self, "tmg_inactive")
            User.objects.filter(pk=inactive.pk).update(is_active=False)
        with self.assertRaisesMessage(CommandError, "target_inactive"):
            self._run("--source", str(self.source.pk), "--target", str(inactive.pk))
        with self.assertRaisesMessage(CommandError, "source_and_target_required"):
            self._run()
        with self.assertRaisesMessage(CommandError, "bad_batch"):
            self._run("--undo", "nope")
