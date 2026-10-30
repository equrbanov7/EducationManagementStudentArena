"""Source35/36: two real repairs, atomic rollback, exact identities and bounded undo."""

import os
import subprocess
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar.models import (
    CourseOffering,
    Enrollment,
    JournalShare,
    Lesson,
    LessonMark,
    Subject,
    TeachingHandover,
)
from apps.registrar.public import handover, handover_actions
from apps.syllabus.models import Syllabus, SyllabusSection, SyllabusVersion
from apps.workload.models import TeacherAssignment, TeachingTask, TeachingTaskRow
from apps.workload.services import cavid_source_batch as repair
from apps.workload.services import cavid_source_spec as spec
from apps.workload.services import cavid_source_state as state
from core.rls import apply_rls_request_context, reset_rls_context

User = get_user_model()


@override_settings(RLS_TRANSACTION_SCOPED=True)
class CavidSourceBatchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser("cavid_admin", "admin@x.test", "pw")
        cls.org = Organization.objects.create(
            pk=spec.ORG,
            name="QKU",
            slug="qku",
            owner=cls.admin,
            org_type="university",
            status="active",
            is_active=True,
        )
        faculty = OrgUnit.objects.create(organization=cls.org, name="Faculty", slug="cv-fac", unit_type="faculty")
        cls.finance = OrgUnit.objects.create(
            pk=spec.FINANCE, organization=cls.org, name="Maliyyə", slug="cv-fin", unit_type="chair", parent=faculty
        )
        cls.nature = OrgUnit.objects.create(
            pk=spec.NATURE, organization=cls.org, name="Təbiət", slug="cv-nat", unit_type="chair", parent=faculty
        )
        cls.specialty = OrgUnit.objects.create(
            pk=spec.SPECIALTY_A,
            organization=cls.org,
            name="Mühasibat",
            slug="cv-spec",
            unit_type="specialty",
            parent=faculty,
        )
        cls.ga = OrgUnit.objects.create(
            pk=spec.GROUP_A, organization=cls.org, name="533MU", slug="cv-ga", unit_type="group", parent=cls.specialty
        )
        cls.gb = OrgUnit.objects.create(
            pk=spec.GROUP_B, organization=cls.org, name="403/5MN", slug="cv-gb", unit_type="group", parent=cls.specialty
        )
        cls.period = AcademicPeriod.objects.create(
            pk=spec.PERIOD,
            organization=cls.org,
            name="Payız",
            academic_year=spec.YEAR,
            period_type="semester",
            start_date="2026-09-01",
            end_date="2027-01-31",
            is_current=True,
        )
        cls.teacher = User.objects.create_user(
            pk=spec.TEACHER, username="cavid.xelilov2", first_name="Cavid", last_name="Xəlilov"
        )
        cls.previous = User.objects.create_user(
            pk=spec.PREVIOUS, username="cavid.xelilov", first_name="Cavid", last_name="Xəlilov"
        )
        role = cls.org.roles.get(name="teacher")
        cls.primary = Membership.objects.create(
            organization=cls.org, user=cls.teacher, role=role, scope_unit=cls.finance, is_active=True, is_primary=True
        )
        Membership.objects.create(
            organization=cls.org, user=cls.previous, role=role, scope_unit=cls.nature, is_active=True, is_primary=True
        )
        for user, father in ((cls.teacher, "Murad"), (cls.previous, "Bəxtiyar")):
            profile = user.profile
            profile.organization, profile.patronymic, profile.role = cls.org, father, "teacher"
            profile.save(update_fields=["organization", "patronymic", "role"])
        cls.sa = Subject.objects.create(
            pk=spec.SUBJECT_A, organization=cls.org, code="QKU1410", name="Vergitutmanın auditi", chair_unit=cls.finance
        )
        cls.sb = Subject.objects.create(
            pk=spec.SUBJECT_B, organization=cls.org, code="QKU2679", name="Tədqiqat analitikası", chair_unit=cls.nature
        )
        cls.ta = TeachingTask.objects.create(
            pk=spec.TASK_A, organization=cls.org, chair=cls.finance, academic_year=spec.YEAR, status="distributed"
        )
        cls.tb = TeachingTask.objects.create(
            pk=spec.TASK_B, organization=cls.org, chair=cls.nature, academic_year=spec.YEAR, status="distributed"
        )
        cls.rb = TeachingTaskRow.objects.create(
            pk=spec.ROW_B,
            organization=cls.org,
            task=cls.tb,
            subject=cls.sb,
            period=cls.period,
            season="fall",
            lecture_plan=45,
            lecture_total=45,
            total_hours=45,
            union_count=1,
            subgroup_count=1,
            note="B metadata must remain",
        )
        cls.rb.groups.set([cls.gb])
        cls.lecture = TeacherAssignment.objects.create(
            pk=spec.LECTURE_B,
            organization=cls.org,
            row=cls.rb,
            teacher=cls.previous,
            activity="lecture",
            hours=45,
            groups_note="retain original note",
            note="retain source provenance",
        )
        cls.a = CourseOffering.objects.create(
            pk=spec.OFFERING_A,
            organization=cls.org,
            subject=cls.sa,
            period=cls.period,
            group=cls.ga,
            instructor=cls.teacher,
            lesson_hours=60,
        )
        cls.b = CourseOffering.objects.create(
            pk=spec.OFFERING_B,
            organization=cls.org,
            subject=cls.sb,
            period=cls.period,
            group=cls.gb,
            instructor=cls.previous,
            lesson_hours=45,
        )
        enrollments = []
        for i in range(7):
            student = User.objects.create_user(f"cv_student_{i}")
            Membership.objects.create(
                organization=cls.org,
                user=student,
                role=cls.org.roles.get(name="student"),
                scope_unit=cls.ga,
                is_active=True,
                is_primary=True,
            )
            enrollments.append(Enrollment.objects.create(organization=cls.org, offering=cls.a, student=student))
            if i < 2:
                Enrollment.objects.create(organization=cls.org, offering=cls.b, student=student)
        cls.marks = []
        for day in range(1, 13):
            lesson = Lesson.objects.create(
                organization=cls.org,
                offering=cls.a,
                date=f"2026-10-{day:02}",
                kind="seminar",
                hours=2,
                instructor=cls.teacher,
                created_by=cls.admin,
            )
            for en in enrollments:
                cls.marks.append(
                    LessonMark.objects.create(
                        organization=cls.org,
                        lesson=lesson,
                        enrollment=en,
                        score=9,
                        status="present",
                        entered_by=cls.teacher,
                    )
                )
        syllabus = Syllabus.objects.create(
            organization=cls.org, subject=cls.sa, offering=cls.a, period=cls.period, author=cls.teacher
        )
        version = SyllabusVersion.objects.create(
            organization=cls.org,
            syllabus=syllabus,
            major=1,
            status="approved",
            approved_at=timezone.now(),
            approved_by=cls.admin,
            locked_at=timezone.now(),
            plan_hours={"lecture": 30, "seminar": 30},
        )
        SyllabusSection.objects.create(
            organization=cls.org, version=version, section_id="week", data={"rows": [{"topic": "keep all"}]}
        )
        syllabus.current_version = syllabus.approved_version = version
        syllabus.save(update_fields=["current_version", "approved_version"])
        cls.other_row = TeachingTaskRow.objects.create(
            organization=cls.org,
            task=cls.ta,
            subject=cls.sb,
            period=cls.period,
            lecture_plan=7,
            lecture_total=7,
            total_hours=7,
        )

    def setUp(self):
        apply_rls_request_context(user_id=self.admin.pk, org_id=self.org.pk, bypass=False)

    def tearDown(self):
        reset_rls_context()

    def run_repair(self, **kwargs):
        return repair.run(organization=self.org, user=self.admin, source_sha256=spec.SOURCE_SHA, **kwargs)

    def apply(self):
        return self.run_repair(apply=True, expected_baseline=state.baseline(state.snapshot()))

    def receipt(self, batch):
        return (
            AuditLog.objects.filter(organization=self.org, resource_type=spec.RESOURCE, resource_id=batch)
            .latest("created_at")
            .new_values
        )

    def test_dry_run_rolls_back_both_repairs_and_notifications(self):
        before = state.snapshot()
        outside = state.outside_fingerprint()
        result = self.run_repair()
        self.assertEqual(result["restored_load_rows"], 1)
        self.assertEqual(state.snapshot(), before)
        self.assertEqual(state.outside_fingerprint(), outside)
        self.assertFalse(state.target_membership().exists())
        self.assertFalse(TeachingHandover.objects.filter(offering=self.b).exists())
        self.assertFalse(AuditLog.objects.filter(resource_type=spec.RESOURCE).exists())

    def test_apply_preserves_academics_and_original_assignment_identity(self):
        before = state.snapshot()
        result = self.apply()
        values = self.receipt(result["batch"])
        state.validate(after=True, receipt=values)
        self.a.refresh_from_db()
        self.b.refresh_from_db()
        self.primary.refresh_from_db()
        self.lecture.refresh_from_db()
        self.assertEqual((self.a.instructor_id, self.b.instructor_id), (spec.TEACHER, spec.TEACHER))
        self.assertEqual(
            (
                self.a.enrollments.count(),
                self.a.lessons.count(),
                LessonMark.objects.filter(lesson__offering=self.a).count(),
            ),
            (7, 12, 84),
        )
        self.assertEqual(
            (self.lecture.pk, self.lecture.teacher_id, self.lecture.hours, self.lecture.note),
            (
                state.model("workload.TeacherAssignment").objects.get(pk=spec.LECTURE_B).pk,
                spec.TEACHER,
                30,
                "retain source provenance",
            ),
        )
        self.assertTrue(self.primary.is_primary)
        self.assertEqual(str(self.primary.scope_unit_id), spec.FINANCE)
        self.assertFalse(state.target_membership().get().is_primary)
        self.assertTrue(handover.is_handover_observer(self.previous, self.b))
        state.assert_protected(
            before, state.snapshot(), row_a_id=values["created_row_id"], membership_id=values["membership_id"]
        )

    def test_retry_is_idempotent_and_does_not_duplicate_handover(self):
        result = self.apply()
        again = self.run_repair(apply=True, expected_baseline=result["baseline"])
        self.assertEqual(again["already_done"], 1)
        self.assertEqual(TeachingHandover.objects.filter(offering=self.b).count(), 1)

    def test_wrong_source_and_stale_academic_baseline_fail_without_writes(self):
        with self.assertRaises(state.RepairError):
            repair.run(organization=self.org, user=self.admin, source_sha256="f" * 64)
        baseline = state.baseline(state.snapshot())
        LessonMark.objects.filter(pk=self.marks[0].pk).update(score=8)
        with self.assertRaisesMessage(state.RepairError, "baseline_conflict"):
            self.run_repair(apply=True, expected_baseline=baseline)
        self.assertFalse(state.target_membership().exists())

    def test_second_operation_failure_rolls_back_first_and_secondary_access(self):
        before = state.snapshot()
        with patch.object(handover_actions, "reassign", side_effect=state.RepairError("forced second-case failure")):
            with self.assertRaises(state.RepairError):
                self.apply()
        self.assertEqual(state.snapshot(), before)

    def test_wrong_father_is_not_merged_or_silently_assigned(self):
        self.teacher.profile.patronymic = "Different"
        self.teacher.profile.save(update_fields=["patronymic"])
        with self.assertRaisesMessage(state.RepairError, "canonical_teacher_identity_mismatch"):
            self.apply()
        self.assertEqual(User.objects.filter(pk__in=(spec.TEACHER, spec.PREVIOUS)).count(), 2)

    def test_new_b_lesson_blocks_the_whole_batch(self):
        Lesson.objects.create(
            organization=self.org, offering=self.b, date="2026-10-20", kind="lecture", hours=2, instructor=self.previous
        )
        with self.assertRaisesMessage(state.RepairError, "b_journal_no_longer_empty"):
            self.apply()
        self.assertFalse(state.target_membership().exists())

    def test_manual_share_blocks_without_removing_it(self):
        share = JournalShare.objects.create(
            organization=self.org, offering=self.b, teacher=self.teacher, is_active=True
        )
        with self.assertRaisesMessage(state.RepairError, "manual_b_share_requires_review"):
            self.apply()
        share.refresh_from_db()
        self.assertTrue(share.is_active)

    def test_foreign_teacher_or_actor_cannot_run_fixed_repair(self):
        with self.assertRaises(state.RepairError):
            repair.run(organization=self.org, user=self.teacher, source_sha256=spec.SOURCE_SHA)
        with self.assertRaises(state.RepairError):
            self.run_repair(apply=True)

    def test_undo_and_undo_retry_preserve_history_and_primary_membership(self):
        result = self.apply()
        values = self.receipt(result["batch"])
        preview = self.run_repair(undo=result["batch"])
        self.assertTrue(TeachingTaskRow.objects.filter(pk=values["created_row_id"]).exists())
        self.run_repair(undo=result["batch"], apply=True, expected_baseline=preview["baseline"])
        self.b.refresh_from_db()
        self.lecture.refresh_from_db()
        self.primary.refresh_from_db()
        self.assertEqual(
            (self.b.instructor_id, self.lecture.teacher_id, self.lecture.hours), (spec.PREVIOUS, spec.PREVIOUS, 45)
        )
        self.assertFalse(TeachingTaskRow.objects.filter(pk=values["created_row_id"]).exists())
        self.assertFalse(state.target_membership().get().is_active)
        self.assertTrue(self.primary.is_active and self.primary.is_primary)
        self.assertIsNotNone(TeachingHandover.objects.get(pk=values["handover_id"]).reverted_at)
        self.assertEqual(self.run_repair(undo=result["batch"])["already_done"], 1)

    def test_undo_keeps_later_a_grades_and_refuses_workload_changes(self):
        result = self.apply()
        LessonMark.objects.filter(pk=self.marks[0].pk).update(score=10)
        current = state.baseline(state.snapshot())
        self.run_repair(undo=result["batch"], apply=True, expected_baseline=current)
        self.marks[0].refresh_from_db()
        self.assertEqual(self.marks[0].score, 10)

    def test_undo_rejects_later_manual_scope_change(self):
        result = self.apply()
        state.target_membership().update(is_primary=True)
        with self.assertRaisesMessage(state.RepairError, "undo_workload_or_access_changed"):
            self.run_repair(undo=result["batch"])

    def test_inactive_secondary_membership_is_reused_and_restored(self):
        membership = Membership.objects.create(
            organization=self.org,
            user=self.teacher,
            role=self.primary.role,
            scope_unit=self.nature,
            is_active=False,
            is_primary=False,
            assigned_by=self.previous,
        )
        result = self.apply()
        self.assertEqual(state.target_membership().get().pk, membership.pk)
        self.run_repair(undo=result["batch"], apply=True, expected_baseline=state.baseline(state.snapshot()))
        membership.refresh_from_db()
        self.assertEqual(
            (membership.is_active, membership.is_primary, membership.assigned_by_id), (False, False, spec.PREVIOUS)
        )

    def test_an_unrelated_row_mutation_rolls_back_the_batch(self):
        original = handover_actions.reassign

        def bad(**kwargs):
            result = original(**kwargs)
            TeachingTaskRow.objects.filter(pk=self.other_row.pk).update(note="unauthorized mutation")
            return result

        with patch.object(handover_actions, "reassign", side_effect=bad):
            with self.assertRaisesMessage(state.RepairError, "outside_target_row_changed"):
                self.apply()
        self.other_row.refresh_from_db()
        self.assertEqual(self.other_row.note, "")

    def test_an_unrelated_journal_mark_is_protected_by_full_tenant_fingerprint(self):
        other = CourseOffering.objects.create(
            organization=self.org,
            subject=self.sa,
            period=self.period,
            group=self.gb,
            instructor=self.previous,
        )
        student = self.a.enrollments.first().student
        enrollment = Enrollment.objects.create(organization=self.org, offering=other, student=student)
        lesson = Lesson.objects.create(organization=self.org, offering=other, date="2026-10-20", kind="seminar")
        mark = LessonMark.objects.create(
            organization=self.org, lesson=lesson, enrollment=enrollment, score=8, status="present"
        )
        original = handover_actions.reassign

        def bad(**kwargs):
            result = original(**kwargs)
            LessonMark.objects.filter(pk=mark.pk).update(score=1)
            return result

        with patch.object(handover_actions, "reassign", side_effect=bad):
            with self.assertRaisesMessage(state.RepairError, "outside_academics_or_manual_access_changed"):
                self.apply()
        mark.refresh_from_db()
        self.assertEqual(mark.score, 8)

    def test_outside_academic_mutation_is_caught_and_rolled_back(self):
        original = handover_actions.reassign

        def bad(**kwargs):
            result = original(**kwargs)
            # A real academic field, outside the permitted owner/handover delta.
            LessonMark.objects.filter(pk=self.marks[0].pk).update(score=1)
            return result

        with patch.object(handover_actions, "reassign", side_effect=bad):
            with self.assertRaises(state.RepairError):
                self.apply()
        self.marks[0].refresh_from_db()
        self.assertEqual(self.marks[0].score, 9)
        self.assertFalse(state.target_membership().exists())


class CavidWorkflowArgsTests(SimpleTestCase):
    def shell(self, batch="", apply="false", tag=""):
        helper = Path(__file__).resolve().parents[3] / "scripts/ops/cavid_source_batch_args.sh"
        code = 'source "$1"; cavid_source_batch_args qku actor "$2" "$3" "$4" || exit $?; printf "%s\\0" "${args[@]}"'
        return subprocess.run(
            ["bash", "-c", code, "test", str(helper), batch, apply, tag],
            check=False,
            capture_output=True,
            env=os.environ,
        )

    def test_dry_and_apply_and_undo_argv_are_exact(self):
        dry = self.shell()
        self.assertEqual(dry.returncode, 0)
        self.assertIn(spec.SOURCE_SHA.encode(), dry.stdout)
        self.assertNotIn(b"--apply", dry.stdout)
        self.assertIn(b"--expected-baseline\0" + b"a" * 64, self.shell("a" * 64, "true").stdout)
        undo = "cavid3536-20261030-020304-abcd"
        self.assertEqual(self.shell(undo).returncode, 0)
        self.assertEqual(self.shell(undo + ":" + "b" * 64, "true").returncode, 0)

    def test_missing_or_malicious_baseline_and_wrong_release_are_rejected(self):
        for batch, apply, tag in [
            ("", "true", ""),
            ("oops", "false", ""),
            ("a" * 64, "false", "unexpected"),
            ("cavid3536-20261030-020304-abcd", "true", ""),
            ("$(touch /tmp/never-execute)", "true", ""),
        ]:
            with self.subTest(batch=batch):
                self.assertNotEqual(self.shell(batch, apply, tag).returncode, 0)
