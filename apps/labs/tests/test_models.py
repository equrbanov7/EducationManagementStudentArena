"""
Model tests for labs app.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.courses.models import Course
from apps.labs.models import Lab, LabAssignment, LabBlock, LabQuestion, LabSubmission

User = get_user_model()


class LabAssignmentReassignmentTest(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("lab_teacher_m", "lab_teacher_m@example.com", "StrongPass123!")
        self.student = User.objects.create_user("lab_student_m", "lab_student_m@example.com", "StrongPass123!")
        self.course = Course.objects.create(owner=self.teacher, title="Lab Course M", status="published")
        self.lab = Lab.objects.create(
            course=self.course,
            title="Lab Reassign",
            description="Lab reassign test",
            start_datetime=timezone.now() - timedelta(hours=1),
            end_datetime=timezone.now() + timedelta(days=1),
            max_score=100,
            max_attempts=1,
            status="published",
            created_by=self.teacher,
            questions_per_student=0,
        )

    def test_get_or_create_refreshes_assignment_when_question_pool_changes(self):
        block = LabBlock.objects.create(lab=self.lab, title="First", order=1)
        q1 = LabQuestion.objects.create(block=block, question_number=1, question_text="Q1")

        assignment = LabAssignment.get_or_create_for_student(self.lab, self.student)
        self.assertEqual(set(assignment.assigned_questions.values_list("id", flat=True)), {q1.id})

        q2 = LabQuestion.objects.create(block=block, question_number=2, question_text="Q2")
        assignment = LabAssignment.get_or_create_for_student(self.lab, self.student)

        self.assertEqual(set(assignment.assigned_questions.values_list("id", flat=True)), {q1.id, q2.id})

    def test_get_or_create_refreshes_assignment_even_when_submission_exists(self):
        block = LabBlock.objects.create(lab=self.lab, title="First", order=1)
        q1 = LabQuestion.objects.create(block=block, question_number=1, question_text="Q1")

        assignment = LabAssignment.get_or_create_for_student(self.lab, self.student)
        LabSubmission.objects.create(assignment=assignment, status="submitted", attempt_number=1)

        q2 = LabQuestion.objects.create(block=block, question_number=2, question_text="Q2")
        assignment = LabAssignment.get_or_create_for_student(self.lab, self.student)

        self.assertEqual(set(assignment.assigned_questions.values_list("id", flat=True)), {q1.id, q2.id})
