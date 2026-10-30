"""A second level contribution preserves the owner's journal and restricted roster."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.organizations.models import Membership, OrgUnit
from apps.registrar.models import CourseOffering, Enrollment, JournalShare, Lesson, LessonMark
from apps.workload.models import TeacherAssignment, TeachingTaskRow
from apps.workload.services import reviewed_language_level_load as repair
from apps.workload.services.sbio235_state import RepairError
from core.rls import apply_rls_request_context, reset_rls_context


@override_settings(RLS_TRANSACTION_SCOPED=True)
class LanguageLevelLoadTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from .test_cavid_source_batch import CavidSourceBatchTests

        CavidSourceBatchTests.setUpTestData.__func__(cls)

    def setUp(self):
        apply_rls_request_context(user_id=self.admin.pk, org_id=self.org.pk, bypass=False)
        self.ga = OrgUnit.objects.create(
            organization=self.org, parent=self.ga.parent, unit_type="group", name="LevelGroup", slug="levelgroup"
        )
        self.row = TeachingTaskRow.objects.create(
            organization=self.org,
            task=self.ta,
            subject=self.sa,
            period=self.period,
            season="fall",
            degree_level="bachelor",
            education_form="eyani",
            seminar_plan=75,
            seminar_total=75,
            total_hours=75,
            union_count=1,
            subgroup_count=1,
        )
        self.row.groups.set([self.ga])
        self.assignment = TeacherAssignment.objects.create(
            organization=self.org, row=self.row, teacher=self.previous, activity="seminar", hours=75
        )
        self.offering = CourseOffering.objects.create(
            organization=self.org,
            group=self.ga,
            subject=self.sa,
            period=self.period,
            instructor=self.previous,
            lesson_hours=75,
        )
        self.share = JournalShare.objects.create(
            organization=self.org, offering=self.offering, teacher=self.teacher, kinds=["seminar"], source="legacy"
        )
        for i in range(13):
            student = get_user_model().objects.create_user(username=f"level_student{i}")
            Membership.objects.create(
                organization=self.org,
                user=student,
                role=self.org.roles.get(name="student"),
                scope_unit=self.ga,
                is_active=True,
            )
            enrollment = Enrollment.objects.create(organization=self.org, offering=self.offering, student=student)
            self.share.enrollments.add(enrollment)
        lesson = Lesson.objects.create(
            organization=self.org,
            offering=self.offering,
            date="2026-10-20",
            kind="seminar",
            hours=2,
            instructor=self.teacher,
            created_by=self.admin,
        )
        LessonMark.objects.create(
            organization=self.org, lesson=lesson, enrollment=enrollment, score=9, status="present"
        )
        self.patcher = patch.multiple(
            repair,
            ROW=str(self.row.pk),
            JOURNAL=str(self.offering.pk),
            GROUP=str(self.ga.pk),
            SUBJECT=str(self.sa.pk),
            PERIOD=str(self.period.pk),
            TASK=str(self.ta.pk),
            CHAIR=str(self.finance.pk),
            TEACHER=self.teacher.pk,
            OWNER=self.previous.pk,
        )
        self.patcher.start()
        self.manifest = {"format": repair.FORMAT, "organization_id": repair.ORG, "source": dict(repair.SOURCE)}

    def tearDown(self):
        self.patcher.stop()
        reset_rls_context()

    def execute(self, **kw):
        return repair.run(
            manifest=self.manifest, manifest_sha="d" * 64, lines=[14383], organization=self.org, user=self.admin, **kw
        )

    def test_apply_keeps_owner_roster_marks_and_repeat_is_noop(self):
        before = repair._state(self.row, self.offering)
        dry = self.execute()
        self.assertEqual(before, repair._state(self.row, self.offering))
        self.execute(apply=True, expected_baseline=dry["baseline"])
        self.row.refresh_from_db()
        self.assertEqual(self.row.seminar_total, 150)
        self.assertEqual(self.row.assignments.count(), 2)
        self.assertEqual(self.row.assignments.get(teacher=self.teacher).hours, 75)
        repair._protected(before, repair._state(self.row, self.offering))
        self.assertEqual(self.execute()["already_done"], 1)

    def test_undo_removes_only_secondary_contribution(self):
        before = repair._state(self.row, self.offering)
        dry = self.execute()
        applied = self.execute(apply=True, expected_baseline=dry["baseline"])
        preview = self.execute(undo=applied["batch"])
        self.execute(undo=applied["batch"], apply=True, expected_baseline=preview["baseline"])
        self.row.refresh_from_db()
        self.assertEqual(self.row.seminar_total, 75)
        self.assertEqual(self.row.assignments.count(), 1)
        self.assertEqual(self.row.assignments.first().pk, self.assignment.pk)
        repair._protected(before, repair._state(self.row, self.offering))

    def test_missing_restricted_roster_or_changed_source_rejected(self):
        self.share.enrollments.clear()
        with self.assertRaisesMessage(RepairError, "existing_restricted_share_required"):
            self.execute()

    def test_source_and_concurrent_journal_change_rejected(self):
        self.manifest["source"]["hours"] = 76
        with self.assertRaisesMessage(RepairError, "language_level_exact_source_required"):
            self.execute()
        self.manifest["source"]["hours"] = 75
        dry = self.execute()
        Lesson.objects.create(
            organization=self.org,
            offering=self.offering,
            date="2026-10-21",
            kind="seminar",
            hours=2,
            instructor=self.teacher,
            created_by=self.admin,
        )
        with self.assertRaisesMessage(RepairError, "baseline_conflict"):
            self.execute(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(self.row.assignments.count(), 1)
