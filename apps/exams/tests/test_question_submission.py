"""
Müəllim → İmtahan mərkəzi sual göndərişi axını testləri.

* Göndərmə: snapshot + xəbərdarlıq sayları, mərkəzə bildiriş.
* Preview: müəllim xəbərdarlıqları görür.
* Qəbul: suallar banka yazılır (yeni/mövcud), müəllimə bildiriş.
* Rədd + düzəliş + yenidən göndərmə dövrü.
* İcazələr: qutu/baxış yalnız imtahan mərkəzi; müəllim yalnız öz göndərişini görür.
"""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.exams.models import BankQuestion, QuestionBank, QuestionSubmission
from apps.exams.services.question_submission import (
    accept_submission,
    reject_submission,
    resubmit_question_set,
    submit_question_set,
)
from apps.exams.tests.test_exam_center_policy import PASSWORD, _assign_user_to_org
from apps.notifications.models import InAppNotification
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()

VALID_TEXT = (
    "1. Azərbaycanın paytaxtı hansıdır?\n"
    "*A) Bakı\n"
    "B) Gəncə\n"
    "C) Sumqayıt\n"
    "D) Şəki\n"
    "E) Lənkəran\n"
    "2. 2 + 2 neçə edir?\n"
    "A) 3\n"
    "*B) 4\n"
    "C) 5\n"
    "D) 6\n"
    "E) 7\n"
)

# Düzgün cavab işarələnməyib → correct_defaulted ERROR xəbərdarlığı çıxmalıdır.
TEXT_WITH_PROBLEM = (
    "1. Problemli sual hansıdır?\n" "A) Birinci\n" "B) İkinci\n" "C) Üçüncü\n" "D) Dördüncü\n" "E) Beşinci\n"
)


class _Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("qs_owner", "qs_owner@test.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="QS University",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        cls.teacher = User.objects.create_user("qs_teacher", "qs_teacher@test.az", PASSWORD)
        _assign_user_to_org(cls.teacher, cls.org, ProfileRole.TEACHER, "teacher")

        cls.exam_center = User.objects.create_user("qs_center", "qs_center@test.az", PASSWORD)
        _assign_user_to_org(cls.exam_center, cls.org, ProfileRole.MEMBER, "exam_center")

    def _client_for(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _submission(self, raw_text=VALID_TEXT, title="İnformatika finalı", **overrides):
        kwargs = {
            "teacher": self.teacher,
            "organization": self.org,
            "title": title,
            "subject": "İnformatika",
            "group_label": "875i",
            "language": "az",
            "raw_text": raw_text,
        }
        kwargs.update(overrides)
        return submit_question_set(**kwargs)


class SubmissionServiceTests(_Base):
    def test_submit_builds_snapshot_and_counts(self):
        submission = self._submission()
        self.assertEqual(submission.status, QuestionSubmission.STATUS_PENDING)
        self.assertEqual(submission.question_count, 2)
        self.assertEqual(submission.error_count, 0)
        self.assertEqual(len(submission.parsed_snapshot), 2)
        self.assertEqual(submission.parsed_snapshot[0]["correct"], ["A"])

    def test_submit_records_warnings_for_problem_text(self):
        submission = self._submission(raw_text=TEXT_WITH_PROBLEM, title="Problemli toplu")
        self.assertGreaterEqual(submission.error_count, 1)
        warning_types = {w["type"] for q in submission.parsed_snapshot for w in q.get("warnings", [])}
        self.assertIn("correct_defaulted", warning_types)

    def test_submit_notifies_exam_center_members(self):
        self._submission()
        self.assertTrue(InAppNotification.objects.filter(recipient=self.exam_center).exists())

    def test_submit_rejects_empty_text(self):
        with self.assertRaises(ValidationError):
            self._submission(raw_text="qısa")

    def test_submit_requires_subject(self):
        with self.assertRaises(ValidationError):
            self._submission(subject="")

    def test_submit_requires_group(self):
        with self.assertRaises(ValidationError):
            self._submission(group_label="")

    def test_submit_with_student_group_fk(self):
        from apps.exams.models import StudentGroup

        group = StudentGroup.objects.create(teacher=self.teacher, organization=self.org, name="875i-qrup")
        submission = self._submission(student_group=group, group_label=group.name)
        self.assertEqual(submission.student_group, group)
        self.assertEqual(submission.group_label, "875i-qrup")

    def test_accept_creates_new_bank_with_questions(self):
        submission = self._submission()
        bank, created = accept_submission(submission, reviewer=self.exam_center, new_bank_name="Final bankı 2026")
        submission.refresh_from_db()
        self.assertEqual(submission.status, QuestionSubmission.STATUS_ACCEPTED)
        self.assertEqual(submission.accepted_bank, bank)
        self.assertEqual(created, 2)
        self.assertEqual(bank.name, "Final bankı 2026")
        self.assertEqual(bank.organization, self.org)
        self.assertEqual(BankQuestion.objects.filter(bank=bank).count(), 2)
        first = BankQuestion.objects.filter(bank=bank).order_by("id").first()
        self.assertTrue(first.options.filter(label="A", is_correct=True).exists())
        # Müəllimə qərar bildirişi.
        self.assertTrue(InAppNotification.objects.filter(recipient=self.teacher).exists())

    def test_accept_into_existing_bank(self):
        existing = QuestionBank.objects.create(
            name="Mövcud bank",
            organization=self.org,
            created_by=self.exam_center,
            default_question_type="test",
        )
        submission = self._submission()
        bank, created = accept_submission(submission, reviewer=self.exam_center, bank=existing)
        self.assertEqual(bank, existing)
        self.assertEqual(created, 2)

    def test_accept_twice_blocked(self):
        submission = self._submission()
        accept_submission(submission, reviewer=self.exam_center)
        with self.assertRaises(ValidationError):
            accept_submission(submission, reviewer=self.exam_center)

    def test_reject_then_resubmit_cycle(self):
        submission = self._submission(raw_text=TEXT_WITH_PROBLEM, title="Dövr testi")
        reject_submission(submission, reviewer=self.exam_center, note="Düzgün cavabları işarələyin.")
        submission.refresh_from_db()
        self.assertEqual(submission.status, QuestionSubmission.STATUS_REJECTED)
        self.assertEqual(submission.reviewer_note, "Düzgün cavabları işarələyin.")

        resubmit_question_set(submission, raw_text=VALID_TEXT)
        submission.refresh_from_db()
        self.assertEqual(submission.status, QuestionSubmission.STATUS_PENDING)
        self.assertEqual(submission.resubmission_count, 1)
        self.assertEqual(submission.error_count, 0)
        self.assertEqual(submission.reviewer_note, "")
        self.assertIsNone(submission.reviewer)

    def test_accepted_submission_cannot_be_resubmitted(self):
        submission = self._submission()
        accept_submission(submission, reviewer=self.exam_center)
        submission.refresh_from_db()
        with self.assertRaises(ValidationError):
            resubmit_question_set(submission, raw_text=VALID_TEXT)


class SubmissionViewTests(_Base):
    def test_teacher_creates_submission_via_view(self):
        client = self._client_for(self.teacher)
        response = client.post(
            reverse("exams:question_submission_create"),
            {
                "action": "save",
                "title": "View testi",
                "subject": "Riyaziyyat",
                "group_label": "842A1",
                "language": "az",
                "raw_text": VALID_TEXT,
            },
        )
        self.assertEqual(response.status_code, 302)
        submission = QuestionSubmission.objects.get(title="View testi")
        self.assertEqual(submission.teacher, self.teacher)
        self.assertEqual(submission.question_count, 2)
        self.assertEqual(submission.subject, "Riyaziyyat")
        self.assertEqual(submission.group_label, "842A1")

    def test_preview_shows_warnings_without_creating(self):
        client = self._client_for(self.teacher)
        response = client.post(
            reverse("exams:question_submission_create"),
            {"action": "preview", "title": "Preview", "language": "az", "raw_text": TEXT_WITH_PROBLEM},
        )
        self.assertEqual(response.status_code, 200)
        # Workbench preview: sual kartları + göndərmə formu render olunur.
        self.assertContains(response, 'id="saveForm"')
        self.assertContains(response, "q-card")
        self.assertEqual(QuestionSubmission.objects.count(), 0)

    def test_inbox_requires_exam_center(self):
        url = reverse("exams:question_submission_inbox")
        self.assertEqual(self._client_for(self.teacher).get(url).status_code, 403)
        self.assertEqual(self._client_for(self.exam_center).get(url).status_code, 200)

    def test_review_decide_accept_flow(self):
        submission = self._submission(title="Qərar axını")
        client = self._client_for(self.exam_center)

        review_url = reverse("exams:question_submission_review", kwargs={"submission_id": submission.id})
        self.assertEqual(client.get(review_url).status_code, 200)

        response = client.post(
            reverse("exams:question_submission_decide", kwargs={"submission_id": submission.id}),
            {"decision": "accept", "bank_id": "", "new_bank_name": "Qərar bankı"},
        )
        self.assertEqual(response.status_code, 302)
        submission.refresh_from_db()
        self.assertEqual(submission.status, QuestionSubmission.STATUS_ACCEPTED)
        self.assertEqual(BankQuestion.objects.filter(bank=submission.accepted_bank).count(), 2)

    def test_reject_requires_note(self):
        submission = self._submission(title="Qeydsiz rədd")
        client = self._client_for(self.exam_center)
        client.post(
            reverse("exams:question_submission_decide", kwargs={"submission_id": submission.id}),
            {"decision": "reject", "note": ""},
        )
        submission.refresh_from_db()
        self.assertEqual(submission.status, QuestionSubmission.STATUS_PENDING)

        client.post(
            reverse("exams:question_submission_decide", kwargs={"submission_id": submission.id}),
            {"decision": "reject", "note": "3-cü sual səhvdir."},
        )
        submission.refresh_from_db()
        self.assertEqual(submission.status, QuestionSubmission.STATUS_REJECTED)

    def test_teacher_cannot_open_others_submission(self):
        other_teacher = User.objects.create_user("qs_other", "qs_other@test.az", PASSWORD)
        _assign_user_to_org(other_teacher, self.org, ProfileRole.TEACHER, "teacher")
        submission = self._submission(title="Gizli göndəriş")

        response = self._client_for(other_teacher).get(
            reverse("exams:question_submission_detail", kwargs={"submission_id": submission.id})
        )
        self.assertEqual(response.status_code, 404)

    def test_exam_center_can_open_detail(self):
        submission = self._submission(title="Mərkəz baxışı")
        response = self._client_for(self.exam_center).get(
            reverse("exams:question_submission_detail", kwargs={"submission_id": submission.id})
        )
        self.assertEqual(response.status_code, 200)

    def test_view_submit_with_group_dropdown(self):
        from apps.exams.models import StudentGroup

        group = StudentGroup.objects.create(teacher=self.teacher, organization=self.org, name="Dropdown qrupu")
        client = self._client_for(self.teacher)
        client.post(
            reverse("exams:question_submission_create"),
            {
                "action": "save",
                "title": "Dropdown testi",
                "subject": "Fizika",
                "group_id": str(group.id),
                "group_label": "",
                "language": "az",
                "raw_text": VALID_TEXT,
            },
        )
        submission = QuestionSubmission.objects.get(title="Dropdown testi")
        self.assertEqual(submission.student_group, group)
        self.assertEqual(submission.group_label, "Dropdown qrupu")

    def test_view_save_respects_selection_and_points(self):
        client = self._client_for(self.teacher)
        client.post(
            reverse("exams:question_submission_create"),
            {
                "action": "save",
                "title": "Seçim testi",
                "subject": "İnformatika",
                "group_label": "875i",
                "language": "az",
                "raw_text": VALID_TEXT,
                "selected": ["2"],
                "selected_indices": "2",
                "points_payload": '{"2": "5"}',
            },
        )
        submission = QuestionSubmission.objects.get(title="Seçim testi")
        self.assertEqual(submission.question_count, 1)
        self.assertEqual(submission.parsed_snapshot[0]["correct"], ["B"])
        self.assertEqual(submission.parsed_snapshot[0].get("points"), 5)

    def test_view_save_carries_teacher_note(self):
        client = self._client_for(self.teacher)
        client.post(
            reverse("exams:question_submission_create"),
            {
                "action": "save",
                "title": "Qeydli göndəriş",
                "subject": "İnformatika",
                "group_label": "875i",
                "teacher_note": "5-8-ci suallar mühazirə 3-ə aiddir.",
                "language": "az",
                "raw_text": VALID_TEXT,
            },
        )
        submission = QuestionSubmission.objects.get(title="Qeydli göndəriş")
        self.assertEqual(submission.teacher_note, "5-8-ci suallar mühazirə 3-ə aiddir.")
        # Mərkəz baxış səhifəsində qeydi görür.
        response = self._client_for(self.exam_center).get(
            reverse("exams:question_submission_review", kwargs={"submission_id": submission.id})
        )
        self.assertContains(response, "mühazirə 3-ə aiddir")

    def test_view_submit_requires_group(self):
        client = self._client_for(self.teacher)
        response = client.post(
            reverse("exams:question_submission_create"),
            {
                "action": "save",
                "title": "Qrupsuz",
                "subject": "Fizika",
                "group_id": "",
                "group_label": "",
                "language": "az",
                "raw_text": VALID_TEXT,
            },
        )
        # Xəta mesajı ilə forma yenidən göstərilir, göndəriş yaranmır.
        self.assertEqual(response.status_code, 200)
        self.assertFalse(QuestionSubmission.objects.filter(title="Qrupsuz").exists())


class ProfileSectionTests(_Base):
    def test_teacher_sees_dashboard_section(self):
        client = self._client_for(self.teacher)
        response = client.get(f"{reverse('accounts:profile')}?section=question-submissions")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sual göndərişləri")
        self.assertContains(response, "Yeni göndəriş")

    def test_exam_center_sees_inbox_variant(self):
        self._submission(title="Bölmə testi")
        client = self._client_for(self.exam_center)
        response = client.get(f"{reverse('accounts:profile')}?section=question-submissions")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Qutunu aç")
        self.assertContains(response, "Bölmə testi")

    def test_teacher_sees_rejected_alert(self):
        submission = self._submission(title="Geri qaytarılan")
        reject_submission(submission, reviewer=self.exam_center, note="Düzəldin.")
        client = self._client_for(self.teacher)
        response = client.get(f"{reverse('accounts:profile')}?section=question-submissions")
        self.assertContains(response, "göndərişi geri qaytarıb")
        self.assertContains(response, "Geri qaytarılıb — düzəliş gözlənilir")

    def test_student_does_not_get_section(self):
        student = User.objects.create_user("qs_student", "qs_student@test.az", PASSWORD)
        _assign_user_to_org(student, self.org, ProfileRole.STUDENT, "student")
        client = self._client_for(student)
        response = client.get(f"{reverse('accounts:profile')}?section=question-submissions")
        # İcazəsiz bölmə default bölməyə düşür — göndəriş paneli görünmür.
        self.assertNotContains(response, "Yeni göndəriş", status_code=200)
