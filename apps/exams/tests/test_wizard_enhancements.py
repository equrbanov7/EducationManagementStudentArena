"""İmtahan sehrbazı təkmilləşdirmələri üçün testlər.

* Final/midterm imtahanlarında fənn (subject) məcburiliyi;
* hər tələbəyə fərdi PIN (ExamStudentPin) təmini + doğrulama;
* müəllimin verdiyi əlavə cəhd (StudentExamAttemptGrant) → attempts_left;
* sınaq (is_trial) cəhdi cəhd limitindən sayılmır.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.exams.forms import ExamForm
from apps.exams.models import Exam, ExamAttempt, ExamStudentPin, StudentExamAttemptGrant, StudentGroup
from apps.exams.services.student_pins import (
    provision_exam_student_pins,
    student_visible_pin,
    verify_student_pin,
)
from apps.exams.tests.test_exam_center_policy import _assign_user_to_org
from apps.organizations.models import Organization
from apps.registrar.models import Subject
from core.constants import OrganizationType

User = get_user_model()


class WizardEnhancementsTests(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user(
            username="wiz_teacher", email="wiz_teacher@example.com", password="StrongPass123!"
        )
        self.s1 = User.objects.create_user(username="wiz_s1", email="wiz_s1@example.com", password="x")
        self.s2 = User.objects.create_user(username="wiz_s2", email="wiz_s2@example.com", password="x")
        self.org = Organization.objects.create(
            name="Wizard Org",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.teacher, self.org, ProfileRole.TEACHER, "teacher")
        _assign_user_to_org(self.s1, self.org, ProfileRole.STUDENT, "student")
        _assign_user_to_org(self.s2, self.org, ProfileRole.STUDENT, "student")
        self.subject = Subject.objects.create(organization=self.org, code="MATH101", name="Calculus")

    # ── Subject required for final/midterm ────────────────────────────────
    def test_midterm_requires_subject(self):
        form = ExamForm(
            data={
                "title": "Midterm 1",
                "exam_type": "test",
                "exam_type_extended": "midterm",
                "random_question_count": "10",
            },
            organization=self.org,
            user=self.teacher,
        )
        self.assertFalse(form.is_valid())
        self.assertIn("subject", form.errors)

    def test_midterm_with_subject_is_valid(self):
        form = ExamForm(
            data={
                "title": "Midterm 1",
                "exam_type": "test",
                "exam_type_extended": "midterm",
                "subject": str(self.subject.pk),
                "random_question_count": "10",
            },
            organization=self.org,
            user=self.teacher,
        )
        self.assertTrue(form.is_valid(), form.errors.as_json())

    def test_quiz_does_not_require_subject(self):
        form = ExamForm(
            data={
                "title": "Quiz 1",
                "exam_type": "test",
                "exam_type_extended": "quiz",
                "random_question_count": "10",
            },
            organization=self.org,
            user=self.teacher,
        )
        self.assertTrue(form.is_valid(), form.errors.as_json())

    # ── Per-student PIN provisioning ──────────────────────────────────────
    def _make_secure_exam(self, category="midterm"):
        exam = Exam.objects.create(
            author=self.teacher,
            title="Secure Exam",
            organization=self.org,
            exam_type_extended=category,
            is_active=True,
            is_public=False,
        )
        exam.allowed_users.add(self.s1, self.s2)
        return exam

    def test_provision_creates_unique_pin_per_student(self):
        exam = self._make_secure_exam()
        provision_exam_student_pins(exam)
        self.assertEqual(ExamStudentPin.objects.filter(exam=exam).count(), 2)

        pin1 = student_visible_pin(exam, self.s1)
        pin2 = student_visible_pin(exam, self.s2)
        self.assertTrue(pin1 and pin2)
        self.assertNotEqual(pin1, pin2)
        # Doğru PIN qəbul olunur, yanlış PIN rədd edilir.
        self.assertTrue(verify_student_pin(exam, self.s1, pin1))
        self.assertFalse(verify_student_pin(exam, self.s1, pin2))

    def test_provision_is_idempotent_and_prunes_removed(self):
        exam = self._make_secure_exam()
        provision_exam_student_pins(exam)
        pin1_before = student_visible_pin(exam, self.s1)

        # Təkrar çağırış PIN-i dəyişmir.
        provision_exam_student_pins(exam)
        self.assertEqual(student_visible_pin(exam, self.s1), pin1_before)

        # Tələbə çıxarılsa PIN silinir.
        exam.allowed_users.remove(self.s2)
        provision_exam_student_pins(exam)
        self.assertFalse(ExamStudentPin.objects.filter(exam=exam, student=self.s2).exists())
        self.assertTrue(ExamStudentPin.objects.filter(exam=exam, student=self.s1).exists())

    def test_non_secure_exam_gets_no_pins(self):
        exam = self._make_secure_exam(category="quiz")
        provision_exam_student_pins(exam)
        self.assertEqual(ExamStudentPin.objects.filter(exam=exam).count(), 0)

    def test_group_student_added_after_exam_assignment_gets_pin(self):
        group = StudentGroup.objects.create(teacher=self.teacher, organization=self.org, name="G1")
        exam = Exam.objects.create(
            author=self.teacher,
            title="Group Final",
            organization=self.org,
            exam_type_extended="final",
            is_active=True,
            is_public=False,
        )
        exam.allowed_groups.add(group)
        self.assertEqual(ExamStudentPin.objects.filter(exam=exam).count(), 0)

        group.students.add(self.s1)
        self.assertTrue(ExamStudentPin.objects.filter(exam=exam, student=self.s1).exists())
        self.assertTrue(student_visible_pin(exam, self.s1))

        group.students.remove(self.s1)
        self.assertFalse(ExamStudentPin.objects.filter(exam=exam, student=self.s1).exists())

    def test_excluded_group_student_loses_access_and_pin(self):
        group = StudentGroup.objects.create(teacher=self.teacher, organization=self.org, name="G2")
        group.students.add(self.s1, self.s2)
        exam = Exam.objects.create(
            author=self.teacher,
            title="Excluded Group Final",
            organization=self.org,
            exam_type_extended="final",
            is_active=True,
            is_public=False,
        )
        exam.allowed_groups.add(group)
        self.assertTrue(ExamStudentPin.objects.filter(exam=exam, student=self.s2).exists())

        exam.excluded_users.add(self.s2)

        self.assertTrue(exam.can_user_see(self.s1))
        self.assertFalse(exam.can_user_see(self.s2))
        self.assertTrue(ExamStudentPin.objects.filter(exam=exam, student=self.s1).exists())
        self.assertFalse(ExamStudentPin.objects.filter(exam=exam, student=self.s2).exists())

    def test_user_lookup_returns_students_and_marks_group_members(self):
        group = StudentGroup.objects.create(teacher=self.teacher, organization=self.org, name="Lookup G")
        group.students.add(self.s1)
        client = Client()
        client.force_login(self.teacher)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()

        response = client.get(reverse("exams:user_search"), {"groups": str(group.id)})
        self.assertEqual(response.status_code, 200)
        results = response.json()["results"]
        by_id = {item["id"]: item for item in results}
        self.assertIn(str(self.s1.id), by_id)
        self.assertIn(str(self.s2.id), by_id)
        self.assertTrue(by_id[str(self.s1.id)]["group_member"])
        self.assertFalse(by_id[str(self.s2.id)]["group_member"])
        self.assertNotIn(str(self.teacher.id), by_id)

        count_response = client.get(
            reverse("exams:assigned_student_count"),
            {"groups": str(group.id), "excluded": str(self.s1.id)},
        )
        self.assertEqual(count_response.status_code, 200)
        self.assertEqual(count_response.json()["total"], 0)

    # ── Per-student attempt grant ─────────────────────────────────────────
    def test_grant_increases_attempts_left_for_single_student(self):
        exam = Exam.objects.create(
            author=self.teacher,
            title="Attempt Exam",
            organization=self.org,
            is_active=True,
            max_attempts_per_user=1,
        )
        ExamAttempt.objects.create(user=self.s1, exam=exam, attempt_number=1, status="submitted")
        self.assertEqual(exam.attempts_left_for(self.s1), 0)

        StudentExamAttemptGrant.objects.create(exam=exam, student=self.s1, extra_attempts=1, granted_by=self.teacher)
        self.assertEqual(exam.attempts_left_for(self.s1), 1)
        # Digər tələbəyə təsir etmir.
        self.assertEqual(exam.attempts_left_for(self.s2), 1)

    # ── Modal partial renders with the new hooks ──────────────────────────
    def test_create_modal_partial_renders_new_controls(self):
        from django.template.loader import render_to_string

        form = ExamForm(user=self.teacher, organization=self.org)
        html = render_to_string(
            "exams/teacher/partials/_create_exam_modal_form.html",
            {
                "form": form,
                "is_editing": False,
                "exam": None,
                "linked_course": None,
                "selected_allowed_groups": [],
                "selected_allowed_users": [],
                "selected_excluded_users": [],
                "supervision_config": None,
            },
        )
        # Subject axtarışlı select, lazy qrup/tələbə axtarış URL-ləri.
        self.assertIn("data-exam-subject-control", html)
        self.assertIn("lookups/groups", html)
        self.assertIn("lookups/users", html)
        # Qeyd: inline "yekun icmal" (data-ew-review) və canlı-tip (data-ew-live-tip)
        # dizayn qərarı ilə partialdan çıxarıldı — bax _create_exam_modal_form.html
        # (~sətir 494-495). İcmal artıq submit-dən əvvəl təsdiq modalında göstərilir;
        # exam_wizard.js::populateReview() element olmayanda təhlükəsiz no-op edir.
        self.assertIn("data-ew-qtime-group", html)
        # Ağır group_student_map JSON blob-u artıq render olunmur (lazy loading).
        self.assertNotIn("createExamGroupStudentMap", html)
        # Yeni imtahanda nəzarət default aktivdir.
        self.assertIn('name="supervision_enabled"', html)
        # İmtahan kodu (6 rəqəm) generatoru tamamilə silinib.
        self.assertNotIn("data-ew-gencode", html)
        self.assertNotIn("data-ew-access-code-group", html)
        # Lazy qrup/tələbə axtarış endpoint-ləri.
        self.assertIn("/lookups/groups/", html)
        self.assertIn("/lookups/users/", html)

    def test_trial_attempt_not_counted_against_limit(self):
        exam = Exam.objects.create(
            author=self.teacher,
            title="Trial Exam",
            organization=self.org,
            is_active=True,
            max_attempts_per_user=1,
        )
        ExamAttempt.objects.create(user=self.teacher, exam=exam, attempt_number=1, status="submitted", is_trial=True)
        # Sınaq cəhdi limiti tükətmir.
        self.assertEqual(exam.attempts_left_for(self.teacher), 1)
