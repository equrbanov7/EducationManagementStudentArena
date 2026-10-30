"""Official source courses enroll current students without inventing block choices."""

import copy
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from apps.registrar.models import Curriculum, CurriculumSubject, GroupElectiveChoice, LessonMark, StudentAcademicRecord
from apps.workload.services import reviewed_batch_state as state
from apps.workload.services.sbio235_state import RepairError, records

from . import test_reviewed_elective_choices as fixtures


@override_settings(RLS_TRANSACTION_SCOPED=True)
class ReviewedDirectCourseTests(TestCase):
    setUpTestData = fixtures.ReviewedElectiveChoicesTests.__dict__["setUpTestData"]
    plan = fixtures.ReviewedElectiveChoicesTests.plan
    execute = fixtures.ReviewedElectiveChoicesTests.execute
    apply = fixtures.ReviewedElectiveChoicesTests.apply
    tearDown = fixtures.ReviewedElectiveChoicesTests.tearDown

    def setUp(self):
        fixtures.ReviewedElectiveChoicesTests.setUp(self)
        self.other_plan = Curriculum.objects.create(
            organization=self.org, program=self.program, admission_year=2025, status="approved"
        )
        self.second_option = CurriculumSubject.objects.create(
            organization=self.org,
            curriculum=self.other_plan,
            subject=self.subject,
            semester_number=3,
            is_elective=True,
            elective_group="4.08",
        )
        value = self.entry["reviewed_policy"]["elective_choices"][0]
        self.entry["reviewed_policy"] = {
            "direct_elective_courses": [
                {
                    **{k: v for k, v in value.items() if k not in ("option_id", "curriculum_id", "elective_group")},
                    "options": [
                        {
                            "option_id": str(op.pk),
                            "curriculum_id": str(op.curriculum_id),
                            "elective_group": op.elective_group,
                        }
                        for op in (self.option, self.second_option)
                    ],
                }
            ]
        }
        students = [en.student for en in self.a.enrollments.order_by("student_id")[:4]]
        self.current = students[:2]
        self.graduated, self.on_leave = students[2:]
        for student, plan, status in (
            (students[0], self.curriculum, "enrolled"),
            (students[1], self.other_plan, "enrolled"),
            (students[2], self.curriculum, "graduated"),
            (students[3], self.curriculum, "academic_leave"),
        ):
            StudentAcademicRecord.objects.create(
                organization=self.org,
                student=student,
                program=self.program,
                curriculum=plan,
                group=self.ga,
                admission_year=2025,
                status=status,
            )

    def test_source_course_enrolls_only_current_group_students_as_elective(self):
        before_records = records(StudentAcademicRecord.objects.all())
        before_marks = records(LessonMark.objects.all())
        self.apply()
        offering = self.subject.offerings.get()
        self.assertEqual(offering.instructor_id, self.teacher.pk)
        self.assertEqual(offering.lesson_hours, 45)
        self.assertCountEqual(
            list(offering.enrollments.values_list("student_id", flat=True)), [u.pk for u in self.current]
        )
        self.assertEqual(set(offering.enrollments.values_list("kind", flat=True)), {"elective"})
        self.assertFalse(GroupElectiveChoice.objects.exists())
        self.assertEqual(records(StudentAcademicRecord.objects.all()), before_records)
        self.assertEqual(records(LessonMark.objects.all()), before_marks)
        self.assertEqual(self.execute()["already_done"], 1)

    def test_dry_run_and_undo_preserve_all_prior_data(self):
        before = state.snapshot(self.plan())
        self.execute()
        self.assertEqual(state.snapshot(self.plan()), before)
        applied = self.apply()
        preview = self.execute(undo=applied["batch"])
        self.execute(undo=applied["batch"], apply=True, expected_baseline=preview["baseline"])
        self.assertFalse(self.subject.offerings.exists())
        self.assertFalse(GroupElectiveChoice.objects.exists())

    def test_different_matching_block_choice_rejects_without_roster_or_load(self):
        choice = GroupElectiveChoice.objects.create(
            organization=self.org,
            group=self.ga,
            period=self.period,
            elective_group="4.08",
            chosen_subject=self.other,
        )
        before = state.snapshot(self.plan())
        with self.assertRaisesMessage(ValidationError, "conflicts"):
            self.execute()
        self.assertEqual(state.snapshot(self.plan()), before)
        choice.refresh_from_db()
        self.assertEqual(choice.chosen_subject_id, self.other.pk)

    def test_same_existing_choice_is_preserved_without_reinterpretation(self):
        choice = GroupElectiveChoice.objects.create(
            organization=self.org,
            group=self.ga,
            period=self.period,
            elective_group="4.07",
            chosen_subject=self.subject,
            decided_by=self.admin,
        )
        before = records(GroupElectiveChoice.objects.filter(pk=choice.pk))
        self.apply()
        self.assertEqual(records(GroupElectiveChoice.objects.filter(pk=choice.pk)), before)

    def test_unrelated_block_choice_is_unchanged(self):
        choice = GroupElectiveChoice.objects.create(
            organization=self.org,
            group=self.ga,
            period=self.period,
            elective_group="unrelated",
            chosen_subject=self.other,
        )
        before = records(GroupElectiveChoice.objects.filter(pk=choice.pk))
        self.apply()
        self.assertEqual(records(GroupElectiveChoice.objects.filter(pk=choice.pk)), before)

    def test_changed_option_set_fails_closed(self):
        self.entry["reviewed_policy"]["direct_elective_courses"][0]["options"][1]["elective_group"] = "forged"
        with self.assertRaisesMessage(ValidationError, "option set"):
            self.execute()
        self.assertFalse(self.subject.offerings.exists())

    def test_source_and_group_scope_are_not_optional(self):
        original = copy.deepcopy(self.entry["reviewed_policy"])
        for field, value in (("source_line", 8), ("source_sha", "f" * 64), ("group_id", str(self.gb.pk))):
            self.entry["reviewed_policy"] = copy.deepcopy(original)
            self.entry["reviewed_policy"]["direct_elective_courses"][0][field] = value
            with self.subTest(field=field), self.assertRaises(RepairError):
                self.plan()

    def test_late_error_rolls_back_new_roster_and_journal(self):
        before = state.snapshot(self.plan())
        with patch("apps.workload.services.reviewed_batch.guards.verify_after", side_effect=RepairError("late")):
            with self.assertRaisesMessage(RepairError, "late"):
                self.execute()
        self.assertEqual(state.snapshot(self.plan()), before)
