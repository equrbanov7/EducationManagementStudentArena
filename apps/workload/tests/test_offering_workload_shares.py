"""Cari növ təyinatı jurnal payına düşür; manual/legacy, təhvil və akademik tarixçə qorunur."""

import io
import re
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from apps.organizations.models import Membership
from apps.registrar.journal_shares import journal_scope, own_or_shared_q
from apps.registrar.models import CourseOffering, Enrollment, JournalShare, JournalShareSource, Lesson, TeachingHandover
from apps.workload.constants import Activity, TaskStatus
from apps.workload.models import TeacherAssignment
from apps.workload.services.journal_share_sync import run as run_backfill
from apps.workload.services.offering_sync import sync_task_offerings
from apps.workload.services.sbio235_state import RepairError

from .factories import TEACHER_PERMS, activate_member, make_org, make_row, make_structure, make_task

User = get_user_model()


class _WorkloadShareFixture:
    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("workload-kind-shares")
        cls.stack = make_structure(cls.org, code="WKS")
        cls.task = make_task(cls.org, cls.stack["chair"], status=TaskStatus.DISTRIBUTED)
        cls.row = make_row(cls.task, cls.stack, lecture_total=30, seminar_total=15, lab_total=15)
        cls.teachers = {}
        for kind, hours in ((Activity.LECTURE, 30), (Activity.SEMINAR, 15), (Activity.LAB, 15)):
            teacher = User.objects.create_user(f"wks-{kind}")
            activate_member(cls.org, teacher, "teacher", permissions=TEACHER_PERMS, scope_unit=cls.stack["chair"])
            TeacherAssignment.objects.create(
                organization=cls.org, row=cls.row, teacher=teacher, activity=kind, hours=hours
            )
            cls.teachers[kind] = teacher


class WorkloadJournalSharesTest(_WorkloadShareFixture, TestCase):

    def _sync(self):
        report = sync_task_offerings(self.task)
        offering = CourseOffering.objects.get(
            organization=self.org, subject=self.stack["subject"], group=self.stack["group"], period=self.stack["period"]
        )
        return offering, report

    def test_three_assigned_teachers_get_only_their_kind_and_one_journal(self):
        offering, report = self._sync()
        self.assertEqual(report["created"], 1)
        self.assertEqual(report["shares_created"], 3)
        self.assertEqual(offering.instructor_id, self.teachers[Activity.LECTURE].pk)
        self.assertEqual(JournalShare.objects.filter(offering=offering, source=JournalShareSource.WORKLOAD).count(), 3)
        for kind, teacher in self.teachers.items():
            scope = journal_scope(teacher, offering)
            self.assertEqual(scope.kinds, {kind})
            self.assertTrue(CourseOffering.objects.filter(pk=offering.pk).filter(own_or_shared_q(teacher)).exists())
        self.assertEqual(offering.lesson_hours, 60)
        self.assertEqual(Lesson.objects.filter(offering=offering).count(), 0)
        again, repeated = self._sync()
        self.assertEqual((repeated["created"], repeated["updated"]), (0, 0))
        self.assertEqual(JournalShare.objects.filter(offering=again).count(), 3)

    def test_removing_a_teacher_revokes_only_automatic_share_and_preserves_lessons(self):
        offering, _ = self._sync()
        Lesson.objects.create(
            organization=self.org,
            offering=offering,
            instructor=self.teachers[Activity.SEMINAR],
            date=timezone.localdate(),
            kind="seminar",
            topic="Keçilmiş dərs",
            hours=2,
        )
        TeacherAssignment.objects.filter(row=self.row, activity=Activity.SEMINAR).update(teacher=None)
        self._sync()
        former = JournalShare.objects.get(offering=offering, teacher=self.teachers[Activity.SEMINAR])
        self.assertFalse(former.is_active)
        self.assertTrue(Lesson.objects.filter(offering=offering, topic="Keçilmiş dərs").exists())
        self.assertTrue(JournalShare.objects.get(offering=offering, teacher=self.teachers[Activity.LAB]).is_active)

    def test_manual_and_legacy_scope_are_never_widened_or_rewritten(self):
        offering, _ = self._sync()
        share = JournalShare.objects.get(offering=offering, teacher=self.teachers[Activity.SEMINAR])
        for source in (JournalShareSource.MANUAL, JournalShareSource.LEGACY):
            share.source = source
            share.kinds = ["lab"]
            share.save(update_fields=["source", "kinds"])
            self._sync()
            share.refresh_from_db()
            self.assertEqual((share.source, share.kinds, share.is_active), (source, ["lab"], True))

    def test_inactive_teacher_does_not_get_access(self):
        Membership.objects.filter(organization=self.org, user=self.teachers[Activity.SEMINAR]).update(is_active=False)
        offering, _ = self._sync()
        self.assertFalse(
            JournalShare.objects.filter(offering=offering, teacher=self.teachers[Activity.SEMINAR]).exists()
        )

    def test_single_owner_needs_no_share_and_revokes_stale_automatic_shares(self):
        offering, _ = self._sync()
        TeacherAssignment.objects.filter(row=self.row).update(teacher=self.teachers[Activity.LECTURE])
        self._sync()
        self.assertFalse(JournalShare.objects.filter(offering=offering, is_active=True).exists())

    def test_teacher_from_another_tenant_does_not_get_access(self):
        foreign_org = make_org("workload-kind-foreign")
        foreign_teacher = User.objects.create_user("wks-foreign-teacher")
        activate_member(foreign_org, foreign_teacher, "teacher", permissions=TEACHER_PERMS)
        TeacherAssignment.objects.filter(row=self.row, activity=Activity.SEMINAR).update(teacher=foreign_teacher)
        offering, _ = self._sync()
        self.assertFalse(JournalShare.objects.filter(offering=offering, teacher=foreign_teacher).exists())

    def test_draft_assignment_does_not_grant_new_access(self):
        self.task.status = TaskStatus.DRAFT
        self.task.save(update_fields=["status"])
        offering, _ = self._sync()
        self.assertFalse(JournalShare.objects.filter(offering=offering).exists())

    def test_ambiguous_same_kind_sections_do_not_grant_whole_roster(self):
        other_teacher = User.objects.create_user("wks-other-section")
        activate_member(self.org, other_teacher, "teacher", permissions=TEACHER_PERMS)
        TeacherAssignment.objects.filter(row=self.row, activity=Activity.SEMINAR).update(hours=7)
        TeacherAssignment.objects.create(
            organization=self.org,
            row=self.row,
            activity=Activity.SEMINAR,
            teacher=other_teacher,
            hours=8,
        )
        offering, report = self._sync()
        self.assertEqual(report["shares_ambiguous"], 1)
        self.assertFalse(JournalShare.objects.filter(offering=offering).exists())

    def test_explicit_physical_group_notes_keep_seminar_teachers_separate(self):
        second = make_structure(self.org, code="WKS2")
        self.row.groups.add(second["group"])
        self.row.seminar_plan = self.row.lab_plan = 15
        self.row.seminar_total = self.row.lab_total = 30
        self.row.subgroup_count = 2
        self.row.total_hours = 90
        self.row.save()
        TeacherAssignment.objects.filter(row=self.row, activity=Activity.LAB).update(hours=30)
        TeacherAssignment.objects.filter(row=self.row, activity=Activity.SEMINAR).update(
            groups_note=self.stack["group"].name
        )
        other_teacher = User.objects.create_user("wks-other-physical-group")
        activate_member(self.org, other_teacher, "teacher", permissions=TEACHER_PERMS)
        TeacherAssignment.objects.create(
            organization=self.org,
            row=self.row,
            activity=Activity.SEMINAR,
            teacher=other_teacher,
            hours=15,
            groups_note=second["group"].name,
        )
        offering, report = self._sync()
        self.assertEqual(report["shares_ambiguous"], 0)
        other_offering = CourseOffering.objects.get(
            organization=self.org, subject=self.stack["subject"], period=self.stack["period"], group=second["group"]
        )
        self.assertFalse(JournalShare.objects.filter(offering=offering, teacher=other_teacher, is_active=True).exists())
        self.assertTrue(
            JournalShare.objects.filter(
                offering=offering, teacher=self.teachers[Activity.SEMINAR], is_active=True
            ).exists()
        )
        self.assertFalse(
            JournalShare.objects.filter(
                offering=other_offering, teacher=self.teachers[Activity.SEMINAR], is_active=True
            ).exists()
        )
        self.assertTrue(
            JournalShare.objects.filter(offering=other_offering, teacher=other_teacher, is_active=True).exists()
        )

    def test_limited_automatic_scope_is_not_widened_but_is_revoked_on_unassignment(self):
        offering, _ = self._sync()
        student = User.objects.create_user("wks-student")
        activate_member(self.org, student, "student", permissions=["course.view"])
        enrollment = Enrollment.objects.create(organization=self.org, offering=offering, student=student)
        share = JournalShare.objects.get(offering=offering, teacher=self.teachers[Activity.SEMINAR])
        share.enrollments.add(enrollment)
        share.kinds = ["lab"]
        share.save(update_fields=["kinds"])
        self._sync()
        share.refresh_from_db()
        self.assertEqual(share.kinds, ["lab"])
        self.assertEqual(list(share.enrollments.all()), [enrollment])
        TeacherAssignment.objects.filter(row=self.row, activity=Activity.SEMINAR).update(teacher=None)
        self._sync()
        share.refresh_from_db()
        self.assertFalse(share.is_active)

    def test_handover_is_not_undone_by_old_load_assignments(self):
        offering, _ = self._sync()
        new_teacher = User.objects.create_user("wks-handover")
        activate_member(self.org, new_teacher, "teacher", permissions=TEACHER_PERMS)
        TeachingHandover.objects.create(
            organization=self.org,
            offering=offering,
            from_instructor=offering.instructor,
            to_instructor=new_teacher,
            performed_by=self.org.owner,
            reason="Test təhvili",
        )
        JournalShare.objects.filter(offering=offering).update(is_active=False)
        offering.instructor = new_teacher
        offering.save(update_fields=["instructor"])
        self._sync()
        self.assertFalse(JournalShare.objects.filter(offering=offering, is_active=True).exists())
        offering.refresh_from_db()
        self.assertEqual(offering.instructor_id, new_teacher.pk)

    def test_foreign_and_locked_offerings_are_not_given_new_shares(self):
        offering, _ = self._sync()
        JournalShare.objects.filter(offering=offering).update(is_active=False)
        self.stack["period"].locked_at = timezone.now()
        self.stack["period"].save(update_fields=["locked_at"])
        self._sync()
        self.assertFalse(JournalShare.objects.filter(offering=offering, is_active=True).exists())


class WorkloadShareBackfillTest(_WorkloadShareFixture, TestCase):
    def setUp(self):
        self.org.owner.is_superuser = True
        self.org.owner.save(update_fields=["is_superuser"])
        self.offering = CourseOffering.objects.create(
            organization=self.org,
            subject=self.stack["subject"],
            group=self.stack["group"],
            period=self.stack["period"],
            instructor=self.teachers[Activity.LECTURE],
            lesson_hours=60,
        )

    def _run(self, **kwargs):
        return run_backfill(organization=self.org, year="2026/2027", user=self.org.owner, **kwargs)

    def test_dry_apply_repeat_and_no_academic_or_workload_changes(self):
        before = list(TeacherAssignment.objects.filter(row=self.row).values("id", "activity", "hours", "teacher_id"))
        dry = self._run()
        self.assertEqual(dry["created"], 3)
        self.assertEqual(JournalShare.objects.filter(offering=self.offering).count(), 0)
        actual = self._run(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(actual["created"], 3)
        self.assertEqual(JournalShare.objects.filter(offering=self.offering, is_active=True).count(), 3)
        repeat = self._run()
        self.assertEqual((repeat["created"], repeat["updated"], repeat["deactivated"]), (0, 0, 0))
        self.assertEqual(
            before, list(TeacherAssignment.objects.filter(row=self.row).values("id", "activity", "hours", "teacher_id"))
        )
        self.offering.refresh_from_db()
        self.assertEqual(
            (self.offering.lesson_hours, self.offering.instructor_id), (60, self.teachers[Activity.LECTURE].pk)
        )
        self.assertFalse(Lesson.objects.filter(offering=self.offering).exists())

    def test_stale_baseline_refuses_apply_without_shares(self):
        baseline = self._run()["baseline"]
        TeacherAssignment.objects.filter(row=self.row, activity=Activity.SEMINAR).update(teacher=None)
        with self.assertRaisesRegex(RepairError, "baseline_changed"):
            self._run(apply=True, expected_baseline=baseline)
        self.assertFalse(JournalShare.objects.filter(offering=self.offering).exists())

    def test_accidental_academic_write_rolls_back_whole_batch(self):
        from apps.workload.services import journal_share_sync

        canonical = journal_share_sync.sync_workload_journal_shares
        baseline = self._run()["baseline"]

        def corrupt(**kwargs):
            result = canonical(**kwargs)
            CourseOffering.objects.filter(pk=self.offering.pk).update(lesson_hours=999)
            return result

        with patch.object(journal_share_sync, "sync_workload_journal_shares", side_effect=corrupt):
            with self.assertRaisesRegex(RepairError, "protected_workload_or_access_changed"):
                self._run(apply=True, expected_baseline=baseline)
        self.assertFalse(JournalShare.objects.filter(offering=self.offering).exists())
        self.offering.refresh_from_db()
        self.assertEqual(self.offering.lesson_hours, 60)

    def test_command_outputs_only_counts_and_hash_and_requires_superadmin(self):
        output = io.StringIO()
        call_command(
            "sync_workload_journal_shares",
            org=self.org.slug,
            year="2026/2027",
            actor=self.org.owner.username,
            stdout=output,
        )
        self.assertRegex(
            output.getvalue().strip(),
            r"^workload_shares: mode=dry_run (?:baseline=[a-f0-9]{64}|[a-z_]+=[0-9]+)(?: (?:baseline=[a-f0-9]{64}|[a-z_]+=[0-9]+))*$",
        )
        self.assertFalse(JournalShare.objects.filter(offering=self.offering).exists())
        self.assertNotIn(self.org.owner.username, output.getvalue())
        self.assertFalse(re.search(r"wks-", output.getvalue()))
        with self.assertRaisesRegex(CommandError, "active_superadmin_org_and_year_required"):
            call_command(
                "sync_workload_journal_shares",
                org=self.org.slug,
                year="2026/2027",
                actor=self.teachers[Activity.LECTURE].username,
                stdout=io.StringIO(),
            )
