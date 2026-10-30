"""Reviewed official names opt in to exact choices without weakening ordinary sync."""

import copy
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import connections, transaction
from django.test import TestCase, TransactionTestCase, override_settings

from apps.registrar.models import Curriculum, CurriculumSubject, GroupElectiveChoice, Program, Subject
from apps.registrar.public import services as registrar_services
from apps.workload.services import reviewed_batch as repair
from apps.workload.services import reviewed_batch_state as state
from apps.workload.services.reviewed_batch_manifest import ORG, YEAR, select_manifest
from apps.workload.services.sbio235_state import RepairError, records
from core.rls import apply_rls_request_context, reset_rls_context

from .test_reviewed_source_batch import source_entry


@override_settings(RLS_TRANSACTION_SCOPED=True)
class ReviewedElectiveChoicesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        from .test_cavid_source_batch import CavidSourceBatchTests

        CavidSourceBatchTests.setUpTestData.__func__(cls)
        cls.subject = Subject.objects.create(organization=cls.org, code="REV-ELECTIVE", name="Rəsmi maliyyə uçotu")
        cls.other = Subject.objects.create(organization=cls.org, code="REV-OTHER", name="Digər maliyyə uçotu")
        cls.program = Program.objects.create(
            organization=cls.org, code="REV-P", name="P", specialty_unit=cls.specialty, degree_level="bachelor"
        )
        cls.curriculum = Curriculum.objects.create(
            organization=cls.org, program=cls.program, admission_year=2026, status="approved"
        )
        cls.option = CurriculumSubject.objects.create(
            organization=cls.org,
            curriculum=cls.curriculum,
            subject=cls.subject,
            semester_number=1,
            is_elective=True,
            elective_group="4.07",
        )
        CurriculumSubject.objects.create(
            organization=cls.org,
            curriculum=cls.curriculum,
            subject=cls.other,
            semester_number=1,
            is_elective=True,
            elective_group="4.07",
        )

    def setUp(self):
        apply_rls_request_context(user_id=self.admin.pk, org_id=self.org.pk, bypass=False)
        entry = source_entry(
            line=7,
            subject=self.subject,
            group=self.ga,
            task=self.ta,
            teacher=self.teacher,
            hours={"lecture": 30, "seminar": 15},
            mode="literal_or_spelling_unique_existing_membership_newrow",
            offering=self.a,
        )
        entry["existing_journals"] = []
        entry["source_reference"]["values"]["subject"] = self.subject.name
        entry["reviewed_policy"] = {
            "elective_choices": [
                {
                    "source_sha": "a" * 64,
                    "source_line": 7,
                    "source_subject": self.subject.name,
                    "subject_id": str(self.subject.pk),
                    "group_id": str(self.ga.pk),
                    "period_id": str(self.period.pk),
                    "option_id": str(self.option.pk),
                    "curriculum_id": str(self.curriculum.pk),
                    "elective_group": "4.07",
                }
            ]
        }
        self.entry = entry
        self.manifest = {
            "format": "reviewed-workload-source/2",
            "organization_id": ORG,
            "academic_year": YEAR,
            "chair_id": str(self.finance.pk),
            "source_entries": [entry],
        }

    def tearDown(self):
        reset_rls_context()

    def plan(self):
        return select_manifest(self.manifest, sha256="e" * 64, lines=[7])

    def execute(self, **kwargs):
        return repair.run(plan=self.plan(), organization=self.org, user=self.admin, **kwargs)

    def apply(self):
        preview = self.execute()
        return self.execute(apply=True, expected_baseline=preview["baseline"])

    def choice(self, subject=None):
        return GroupElectiveChoice.objects.create(
            organization=self.org,
            group=self.ga,
            period=self.period,
            elective_group="4.07",
            chosen_subject=subject or self.subject,
            decided_by=self.admin,
        )

    def test_missing_choice_dry_apply_and_undo_preserve_existing_academics(self):
        before = state.snapshot(self.plan())
        marks = records(self.a.lessons.all())
        self.execute()
        self.assertEqual(state.snapshot(self.plan()), before)
        self.assertFalse(GroupElectiveChoice.objects.exists())
        applied = self.apply()
        self.assertEqual(GroupElectiveChoice.objects.get().chosen_subject_id, self.subject.pk)
        self.assertEqual(records(self.a.lessons.all()), marks)
        self.assertEqual(self.execute()["already_done"], 1)
        undone = self.execute(undo=applied["batch"])
        self.execute(undo=applied["batch"], expected_baseline=undone["baseline"], apply=True)
        self.assertFalse(GroupElectiveChoice.objects.exists())
        self.assertFalse(self.subject.offerings.exists())

    def test_existing_same_choice_is_unchanged_including_actor_timestamps(self):
        choice = self.choice()
        before = records(GroupElectiveChoice.objects.filter(pk=choice.pk))
        self.apply()
        self.assertEqual(records(GroupElectiveChoice.objects.filter(pk=choice.pk)), before)

    def test_existing_other_choice_rejects_entire_batch(self):
        choice = self.choice(self.other)
        before = state.snapshot(self.plan())
        with self.assertRaisesMessage(RepairError, "bounded_sync_rejected"):
            self.execute()
        self.assertEqual(state.snapshot(self.plan()), before)
        choice.refresh_from_db()
        self.assertEqual(choice.chosen_subject_id, self.other.pk)
        self.assertFalse(self.subject.offerings.exists())

    def test_default_named_row_still_waits_for_choice(self):
        self.entry.pop("reviewed_policy")
        with self.assertRaisesMessage(RepairError, "bounded_sync_rejected"):
            self.execute()
        self.assertFalse(GroupElectiveChoice.objects.exists())

    def test_late_error_rolls_back_choice_load_and_journal(self):
        before = state.snapshot(self.plan())
        with patch("apps.workload.services.reviewed_batch.guards.verify_after", side_effect=RepairError("late")):
            with self.assertRaisesMessage(RepairError, "late"):
                self.execute()
        self.assertEqual(state.snapshot(self.plan()), before)
        self.assertFalse(GroupElectiveChoice.objects.exists())

    def test_multiple_approved_options_without_actual_curriculum_are_rejected(self):
        other_plan = Curriculum.objects.create(
            organization=self.org, program=self.program, admission_year=2025, status="approved"
        )
        CurriculumSubject.objects.create(
            organization=self.org,
            curriculum=other_plan,
            subject=self.subject,
            semester_number=3,
            is_elective=True,
            elective_group="4.07",
        )
        with self.assertRaisesMessage(ValidationError, "ambiguous"):
            self.execute()
        self.assertFalse(self.subject.offerings.exists())

    def test_actual_unique_sar_curriculum_resolves_multiple_approved_options(self):
        from apps.registrar.models import StudentAcademicRecord

        other_plan = Curriculum.objects.create(
            organization=self.org, program=self.program, admission_year=2025, status="approved"
        )
        CurriculumSubject.objects.create(
            organization=self.org,
            curriculum=other_plan,
            subject=self.subject,
            semester_number=3,
            is_elective=True,
            elective_group="4.07",
        )
        student = self.a.enrollments.first().student
        StudentAcademicRecord.objects.create(
            organization=self.org,
            student=student,
            program=self.program,
            curriculum=self.curriculum,
            group=self.ga,
            admission_year=2026,
        )
        self.apply()
        self.assertEqual(GroupElectiveChoice.objects.get().chosen_subject_id, self.subject.pk)

    def test_single_approved_option_preserves_an_older_sar_curriculum(self):
        from apps.registrar.models import StudentAcademicRecord

        older = Curriculum.objects.create(
            organization=self.org, program=self.program, admission_year=2025, status="approved"
        )
        student = self.a.enrollments.first().student
        record = StudentAcademicRecord.objects.create(
            organization=self.org,
            student=student,
            program=self.program,
            curriculum=older,
            group=self.ga,
            admission_year=2025,
        )
        before = records(StudentAcademicRecord.objects.filter(pk=record.pk))
        self.apply()
        self.assertEqual(records(StudentAcademicRecord.objects.filter(pk=record.pk)), before)
        self.assertTrue(self.subject.offerings.get().enrollments.filter(student=student).exists())

    def test_frozen_option_and_source_scope_cannot_be_retargeted(self):
        for field, value in (
            ("source_sha", "f" * 64),
            ("source_line", 8),
            ("group_id", str(self.gb.pk)),
            ("subject_id", str(self.other.pk)),
            ("period_id", str(self.gb.pk)),
        ):
            original = copy.deepcopy(self.entry["reviewed_policy"])
            self.entry["reviewed_policy"]["elective_choices"][0][field] = value
            with self.subTest(field=field), self.assertRaises(RepairError):
                self.plan()
            self.entry["reviewed_policy"] = original

    def test_option_pk_or_block_changed_is_rejected_live(self):
        self.entry["reviewed_policy"]["elective_choices"][0]["elective_group"] = "wrong"
        with self.assertRaisesMessage(ValidationError, "frozen"):
            self.execute()
        self.assertFalse(GroupElectiveChoice.objects.exists())

    def test_fresh_strict_choice_rejects_stale_cache_other_choice(self):
        from apps.workload.services.offering_elective_flow import record_group_choice

        original = record_group_choice

        def concurrent_choice(**kwargs):
            self.choice(self.other)
            return original(**kwargs)

        with patch("apps.workload.services.offering_elective_flow.record_group_choice", side_effect=concurrent_choice):
            with self.assertRaisesMessage(RepairError, "bounded_sync_rejected"):
                self.execute()
        self.assertFalse(self.subject.offerings.exists())
        self.assertFalse(GroupElectiveChoice.objects.exists())

    def test_canonical_strict_api_never_replaces_choice_and_default_still_can(self):
        choice = self.choice(self.other)
        kwargs = dict(
            organization=self.org,
            group=self.ga,
            curriculum=self.curriculum,
            period=self.period,
            elective_group="4.07",
            subject=self.subject,
            decided_by=self.admin,
            enforce_window=False,
        )
        with self.assertRaises(ValidationError):
            registrar_services.choose_group_elective(**kwargs, preserve_existing=True)
        choice.refresh_from_db()
        self.assertEqual(choice.chosen_subject_id, self.other.pk)
        registrar_services.choose_group_elective(**kwargs)
        choice.refresh_from_db()
        self.assertEqual(choice.chosen_subject_id, self.subject.pk)

    def test_other_group_choice_is_preserved(self):
        other = GroupElectiveChoice.objects.create(
            organization=self.org, group=self.gb, period=self.period, elective_group="4.07", chosen_subject=self.other
        )
        before = records(GroupElectiveChoice.objects.filter(pk=other.pk))
        self.apply()
        self.assertEqual(records(GroupElectiveChoice.objects.filter(pk=other.pk)), before)

    def test_cross_tenant_option_cannot_be_used(self):
        self.entry["reviewed_policy"]["elective_choices"][0]["option_id"] = str(self.ga.pk)
        with self.assertRaisesMessage(ValidationError, "frozen"):
            self.execute()
        self.assertFalse(self.subject.offerings.exists())


@override_settings(RLS_TRANSACTION_SCOPED=True)
class ConcurrentStrictChoiceTests(TransactionTestCase):
    def test_two_concurrent_different_choices_preserve_the_first_decision(self):
        ReviewedElectiveChoicesTests.setUpTestData.__func__(type(self))
        self.org.refresh_from_db()
        self.ga.refresh_from_db()
        self.period.refresh_from_db()
        self.subject.refresh_from_db()
        self.other.refresh_from_db()
        barrier = Barrier(2)
        curriculum = Curriculum.objects.select_related("program").get(pk=self.curriculum.pk)

        def choose(subject):
            try:
                with transaction.atomic():
                    apply_rls_request_context(user_id=self.admin.pk, org_id=self.org.pk, bypass=False)
                    barrier.wait(timeout=10)
                    registrar_services.choose_group_elective(
                        organization=self.org,
                        group=self.ga,
                        curriculum=curriculum,
                        period=self.period,
                        elective_group="4.07",
                        subject=subject,
                        decided_by=self.admin,
                        enforce_window=False,
                        preserve_existing=True,
                    )
                return "created"
            except ValidationError as exc:
                if "mövcud seçimi" not in str(exc):
                    raise
                return "preserved_other"
            finally:
                reset_rls_context()
                connections["default"].close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(choose, (self.subject, self.other)))
        self.assertCountEqual(results, ["created", "preserved_other"])
        self.assertEqual(GroupElectiveChoice.objects.count(), 1)
        self.assertEqual(self.subject.offerings.count() + self.other.offerings.count(), 1)


@override_settings(RLS_TRANSACTION_SCOPED=True)
class EmptyReviewedJournalTests(TestCase):
    setUpTestData = ReviewedElectiveChoicesTests.__dict__["setUpTestData"]
    plan = ReviewedElectiveChoicesTests.plan
    execute = ReviewedElectiveChoicesTests.execute
    apply = ReviewedElectiveChoicesTests.apply
    tearDown = ReviewedElectiveChoicesTests.tearDown

    def setUp(self):
        from apps.organizations.models import OrgUnit

        ReviewedElectiveChoicesTests.setUp(self)
        self.empty_group = OrgUnit.objects.create(
            organization=self.org, name="2532i", slug="empty-review", unit_type="group", parent=self.specialty
        )
        self.entry["desired_row"]["group_ids"] = [str(self.empty_group.pk)]
        self.entry["desired_row"]["groups_text"] = self.empty_group.name
        self.entry["physical_source_groups"] = [
            {
                "id": str(self.empty_group.pk),
                "name": self.empty_group.name,
                "parent_id": str(self.specialty.pk),
                "children": [],
            }
        ]
        value = self.entry["reviewed_policy"]["elective_choices"][0]
        self.entry["reviewed_policy"] = {
            "empty_group_journals": [
                {
                    k: (str(self.empty_group.pk) if k == "group_id" else v)
                    for k, v in value.items()
                    if k not in ("option_id", "curriculum_id", "elective_group")
                }
            ]
        }

    def record(self, status="enrolled", *, active=True):
        from apps.registrar.models import StudentAcademicRecord

        return StudentAcademicRecord.objects.create(
            organization=self.org,
            student=self.a.enrollments.first().student,
            program=self.program,
            curriculum=self.curriculum,
            group=self.empty_group,
            admission_year=2025,
            status=status,
            is_active=active,
        )

    def test_empty_course_creates_teacher_journal_without_roster_choice_or_plan(self):
        graduated = self.record("graduated")
        before = records(type(graduated).objects.filter(pk=graduated.pk))
        result = self.apply()
        offering = self.subject.offerings.get()
        self.assertEqual(result["created_journals"], 1)
        self.assertEqual(offering.group_id, self.empty_group.pk)
        self.assertEqual(offering.instructor_id, self.teacher.pk)
        self.assertEqual(offering.lesson_hours, 45)
        self.assertFalse(offering.enrollments.exists())
        self.assertFalse(GroupElectiveChoice.objects.exists())
        self.assertEqual(records(type(graduated).objects.filter(pk=graduated.pk)), before)

    def test_one_enrolled_student_blocks_empty_exception(self):
        self.record()
        with self.assertRaisesMessage(ValidationError, "empty group"):
            self.execute()
        self.assertFalse(self.subject.offerings.exists())

    def test_one_active_leave_record_blocks_empty_exception(self):
        self.record("academic_leave")
        with self.assertRaisesMessage(ValidationError, "empty group"):
            self.execute()

    def test_existing_other_subject_enrollment_blocks_empty_exception(self):
        from apps.registrar.models import CourseOffering, Enrollment

        offering = CourseOffering.objects.create(
            organization=self.org,
            subject=self.other,
            group=self.empty_group,
            period=self.period,
            instructor=self.teacher,
        )
        Enrollment.objects.create(organization=self.org, offering=offering, student=self.a.enrollments.first().student)
        with self.assertRaisesMessage(ValidationError, "empty group"):
            self.execute()
        self.assertEqual(offering.enrollments.count(), 1)

    def test_existing_other_choice_is_never_changed(self):
        other = GroupElectiveChoice.objects.create(
            organization=self.org,
            group=self.empty_group,
            period=self.period,
            elective_group="other-block",
            chosen_subject=self.other,
        )
        before = records(GroupElectiveChoice.objects.filter(pk=other.pk))
        with self.assertRaisesMessage(ValidationError, "empty group"):
            self.execute()
        self.assertEqual(records(GroupElectiveChoice.objects.filter(pk=other.pk)), before)

    def test_empty_exception_cannot_target_other_group(self):
        self.entry["reviewed_policy"]["empty_group_journals"][0]["group_id"] = str(self.ga.pk)
        with self.assertRaisesMessage(RepairError, "source_key_mismatch"):
            self.plan()

    def test_late_failure_rolls_back_empty_journal_and_workload(self):
        before = state.snapshot(self.plan())
        with patch("apps.workload.services.reviewed_batch.guards.verify_after", side_effect=RepairError("late")):
            with self.assertRaisesMessage(RepairError, "late"):
                self.execute()
        self.assertEqual(state.snapshot(self.plan()), before)

    def test_foreign_tenant_group_is_rejected_by_canonical_choice(self):
        import uuid

        group = copy.copy(self.empty_group)
        group.organization_id = uuid.uuid4()
        with self.assertRaises(ValidationError):
            registrar_services.choose_group_elective(
                organization=self.org,
                group=group,
                curriculum=self.curriculum,
                period=self.period,
                elective_group="4.07",
                subject=self.subject,
                decided_by=self.admin,
                enforce_window=False,
                preserve_existing=True,
            )
        self.assertFalse(GroupElectiveChoice.objects.exists())
