"""
Müəllim → KAFEDRA MÜDİRİ → İmtahan Mərkəzi sual göndərişi axını testləri.

* Göndərmə: snapshot + xəbərdarlıq sayları, KAFEDRAYA marşrut və bildiriş.
* Preview: müəllim xəbərdarlıqları görür.
* Qəbul: suallar banka yazılır (yeni/mövcud), müəllimə bildiriş.
* Rədd + düzəliş + yenidən göndərmə dövrü.
* İcazələr: qutu/baxış yalnız imtahan mərkəzi; müəllim yalnız öz göndərişini görür.
"""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

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
from core.constants import OrganizationType, OrgUnitType

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

        # ── Kafedra strukturu: müəllim kafedraya bağlıdır, kafedranın müdiri var ──
        from apps.organizations.models import Membership, OrgUnit

        cls.faculty = OrgUnit.objects.create(
            organization=cls.org, name="Mühəndislik fakültəsi", unit_type=OrgUnitType.FACULTY
        )
        cls.chair = OrgUnit.objects.create(
            organization=cls.org, name="İnformatika kafedrası", unit_type=OrgUnitType.CHAIR, parent=cls.faculty
        )
        cls.other_chair = OrgUnit.objects.create(
            organization=cls.org, name="Fizika kafedrası", unit_type=OrgUnitType.CHAIR, parent=cls.faculty
        )
        Membership.objects.filter(user=cls.teacher, organization=cls.org).update(scope_unit=cls.chair)

        cls.chair_head = User.objects.create_user("qs_chair", "qs_chair@test.az", PASSWORD)
        _assign_user_to_org(cls.chair_head, cls.org, ProfileRole.MEMBER, "chair_head")
        Membership.objects.filter(user=cls.chair_head, organization=cls.org).update(scope_unit=cls.chair)

        cls.other_chair_head = User.objects.create_user("qs_chair2", "qs_chair2@test.az", PASSWORD)
        _assign_user_to_org(cls.other_chair_head, cls.org, ProfileRole.MEMBER, "chair_head")
        Membership.objects.filter(user=cls.other_chair_head, organization=cls.org).update(scope_unit=cls.other_chair)

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

    def _to_center(self, submission):
        """Kafedra təsdiqini simulyasiya edir — MƏRKƏZ mərhələsi testləri üçün."""
        QuestionSubmission.objects.filter(pk=submission.pk).update(
            status=QuestionSubmission.STATUS_CHAIR_APPROVED,
            chair_decision=QuestionSubmission.CHAIR_DECISION_APPROVED,
            chair_reviewer=self.chair_head,
            chair_reviewed_at=timezone.now(),
            reached_center_at=timezone.now(),
        )
        submission.refresh_from_db()
        return submission

    def _subject(self, name="İnformatika", code="INF101", group=None):
        """Registrar fənni yaradır; verilərsə qrupa bağlayır (müəllim fənləri
        qrup fənlərinin birləşməsindən gəlir)."""
        from apps.registrar.models import Subject

        subject = Subject.objects.create(organization=self.org, code=code, name=name)
        if group is not None:
            group.subjects.add(subject)
        return subject


class SubmissionServiceTests(_Base):
    def test_submit_builds_snapshot_and_counts(self):
        submission = self._submission()
        self.assertEqual(submission.status, QuestionSubmission.STATUS_SUBMITTED_TO_CHAIR)
        self.assertEqual(submission.chair_unit, self.chair)
        self.assertFalse(submission.routed_to_dean)
        self.assertIsNone(submission.reached_center_at)
        self.assertEqual(submission.question_count, 2)
        self.assertEqual(submission.error_count, 0)
        self.assertEqual(len(submission.parsed_snapshot), 2)
        self.assertEqual(submission.parsed_snapshot[0]["correct"], ["A"])

    def test_submit_records_warnings_for_problem_text(self):
        submission = self._submission(raw_text=TEXT_WITH_PROBLEM, title="Problemli toplu")
        self.assertGreaterEqual(submission.error_count, 1)
        warning_types = {w["type"] for q in submission.parsed_snapshot for w in q.get("warnings", [])}
        self.assertIn("correct_defaulted", warning_types)

    def test_submit_notifies_chair_head_not_exam_center(self):
        self._submission()
        self.assertTrue(InAppNotification.objects.filter(recipient=self.chair_head).exists())
        # Mərkəz kafedra təsdiqindən ƏVVƏL heç nə görmür/bilmir.
        self.assertFalse(InAppNotification.objects.filter(recipient=self.exam_center).exists())

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
        submission = self._to_center(self._submission())
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

    def test_accept_carries_submission_meta_to_new_bank(self):
        # Fənn (kataloq bağlantısı), imtahan növü və mənbə müəllim yeni banka köçür.
        subject = self._subject(name="Riyazi analiz", code="RIY201")
        submission = self._to_center(
            self._submission(title="Meta daşıma", subject=subject.name, subject_ref=subject, exam_kind="midterm")
        )
        bank, _created = accept_submission(submission, reviewer=self.exam_center)
        self.assertEqual(bank.subject_ref, subject)
        self.assertEqual(bank.subject, "Riyazi analiz")
        self.assertEqual(bank.exam_kind, "midterm")
        self.assertEqual(bank.source_teacher, self.teacher)
        # Banklar default gizlidir — paylaşım UI-dan çıxarılıb.
        self.assertFalse(bank.is_shared)

    def test_accept_into_existing_bank(self):
        existing = QuestionBank.objects.create(
            name="Mövcud bank",
            organization=self.org,
            created_by=self.exam_center,
            default_question_type="test",
        )
        submission = self._to_center(self._submission())
        bank, created = accept_submission(submission, reviewer=self.exam_center, bank=existing)
        self.assertEqual(bank, existing)
        self.assertEqual(created, 2)

    def test_accept_twice_blocked(self):
        submission = self._to_center(self._submission())
        accept_submission(submission, reviewer=self.exam_center)
        with self.assertRaises(ValidationError):
            accept_submission(submission, reviewer=self.exam_center)

    def test_reject_then_resubmit_cycle(self):
        submission = self._to_center(self._submission(raw_text=TEXT_WITH_PROBLEM, title="Dövr testi"))
        reject_submission(submission, reviewer=self.exam_center, note="Düzgün cavabları işarələyin — hamısında.")
        submission.refresh_from_db()
        self.assertEqual(submission.status, QuestionSubmission.STATUS_REJECTED)
        self.assertEqual(submission.reviewer_note, "Düzgün cavabları işarələyin — hamısında.")

        resubmit_question_set(submission, raw_text=VALID_TEXT)
        submission.refresh_from_db()
        # Düzəlişdən sonra dəst YENİDƏN kafedradan keçir — mərkəzə birbaşa qayıtmır.
        self.assertEqual(submission.status, QuestionSubmission.STATUS_SUBMITTED_TO_CHAIR)
        self.assertIsNone(submission.reached_center_at)
        self.assertEqual(submission.resubmission_count, 1)
        self.assertEqual(submission.error_count, 0)
        self.assertEqual(submission.reviewer_note, "")
        self.assertIsNone(submission.reviewer)

    def test_accepted_submission_cannot_be_resubmitted(self):
        submission = self._to_center(self._submission())
        accept_submission(submission, reviewer=self.exam_center)
        submission.refresh_from_db()
        with self.assertRaises(ValidationError):
            resubmit_question_set(submission, raw_text=VALID_TEXT)


class SubmissionViewTests(_Base):
    def test_teacher_creates_submission_via_view(self):
        from apps.exams.models import StudentGroup

        group = StudentGroup.objects.create(teacher=self.teacher, organization=self.org, name="842A1")
        subject = self._subject(name="Riyaziyyat", code="RIY101", group=group)
        client = self._client_for(self.teacher)
        response = client.post(
            reverse("exams:question_submission_create"),
            {
                "action": "save",
                "title": "View testi",
                "subject": str(subject.pk),
                "exam_kind": "final",
                "group_id": str(group.id),
                "language": "az",
                "raw_text": VALID_TEXT,
            },
        )
        self.assertEqual(response.status_code, 302)
        submission = QuestionSubmission.objects.get(title="View testi")
        self.assertEqual(submission.teacher, self.teacher)
        self.assertEqual(submission.question_count, 2)
        self.assertEqual(submission.subject, "Riyaziyyat")
        self.assertEqual(submission.subject_ref, subject)
        self.assertEqual(submission.exam_kind, "final")
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

    def test_inbox_redirects_to_profile_section(self):
        # Köhnə ayrıca qutu səhifəsi ləğv edilib — profil bölməsinə yönləndirir.
        url = reverse("exams:question_submission_inbox")
        for user in (self.teacher, self.exam_center):
            response = self._client_for(user).get(url)
            self.assertEqual(response.status_code, 302)
            self.assertIn("section=question-submissions", response["Location"])

    def test_review_decide_accept_flow(self):
        submission = self._to_center(self._submission(title="Qərar axını"))
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
        submission = self._to_center(self._submission(title="Qeydsiz rədd"))
        client = self._client_for(self.exam_center)
        client.post(
            reverse("exams:question_submission_decide", kwargs={"submission_id": submission.id}),
            {"decision": "reject", "note": ""},
        )
        submission.refresh_from_db()
        self.assertEqual(submission.status, QuestionSubmission.STATUS_CHAIR_APPROVED)

        # Qısa qeyd də KİFAYƏT ETMİR (≥20 simvol).
        client.post(
            reverse("exams:question_submission_decide", kwargs={"submission_id": submission.id}),
            {"decision": "reject", "note": "səhvdir"},
        )
        submission.refresh_from_db()
        self.assertEqual(submission.status, QuestionSubmission.STATUS_CHAIR_APPROVED)

        client.post(
            reverse("exams:question_submission_decide", kwargs={"submission_id": submission.id}),
            {"decision": "reject", "note": "3-cü sualda düzgün cavab işarələnməyib."},
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
        submission = self._to_center(self._submission(title="Mərkəz baxışı"))
        response = self._client_for(self.exam_center).get(
            reverse("exams:question_submission_detail", kwargs={"submission_id": submission.id})
        )
        self.assertEqual(response.status_code, 200)

    def test_view_submit_with_group_dropdown(self):
        from apps.exams.models import StudentGroup

        group = StudentGroup.objects.create(teacher=self.teacher, organization=self.org, name="Dropdown qrupu")
        subject = self._subject(name="Fizika", code="FIZ101", group=group)
        client = self._client_for(self.teacher)
        client.post(
            reverse("exams:question_submission_create"),
            {
                "action": "save",
                "title": "Dropdown testi",
                "subject": str(subject.pk),
                "exam_kind": "quiz",
                "group_id": str(group.id),
                "group_label": "",
                "language": "az",
                "raw_text": VALID_TEXT,
            },
        )
        submission = QuestionSubmission.objects.get(title="Dropdown testi")
        self.assertEqual(submission.student_group, group)
        self.assertEqual(submission.group_label, "Dropdown qrupu")

    def test_view_subject_scoped_to_group_subjects(self):
        # Bənd 4-5: qrupa təyin olunmuş fənn seçiləndə göndəriş uğurludur.
        from apps.exams.models import StudentGroup

        group = StudentGroup.objects.create(teacher=self.teacher, organization=self.org, name="875i-fenn")
        subject = self._subject(group=group)

        client = self._client_for(self.teacher)
        response = client.post(
            reverse("exams:question_submission_create"),
            {
                "action": "save",
                "title": "Fənn skoplu",
                "subject": str(subject.pk),
                "exam_kind": "final",
                "group_id": str(group.id),
                "language": "az",
                "raw_text": VALID_TEXT,
            },
        )
        self.assertEqual(response.status_code, 302)
        submission = QuestionSubmission.objects.get(title="Fənn skoplu")
        self.assertEqual(submission.subject, "İnformatika")
        self.assertEqual(submission.subject_ref, subject)
        self.assertEqual(submission.student_group, group)

    def test_create_page_renders_subject_dropdown_and_map(self):
        # Şablon + kontekst uçdan-uca: fənn <select> + qrup→fənn JSON adası render olunur.
        from apps.exams.models import StudentGroup
        from apps.registrar.models import Subject

        subject = Subject.objects.create(organization=self.org, code="INF101", name="İnformatika")
        group = StudentGroup.objects.create(teacher=self.teacher, organization=self.org, name="875i-render")
        group.subjects.add(subject)

        client = self._client_for(self.teacher)
        response = client.get(reverse("exams:question_submission_create"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="qsubSubject"')
        self.assertContains(response, "qsubGroupsSubjects")  # JSON data adası
        self.assertContains(response, "INF101")  # fənn xəritədə (kod, ascii-təhlükəsiz)
        self.assertContains(response, "question_submission_subjects.js")  # skoplama skripti

    def test_view_rejects_subject_not_in_group(self):
        # Bənd 5: müəllimin fənləri arasında olmayan fənn rədd edilir.
        from apps.exams.models import StudentGroup

        group = StudentGroup.objects.create(teacher=self.teacher, organization=self.org, name="875i-fenn2")
        self._subject(group=group)
        foreign_subject = self._subject(name="Kimya", code="KIM101")  # heç bir qrupa bağlı deyil

        client = self._client_for(self.teacher)
        response = client.post(
            reverse("exams:question_submission_create"),
            {
                "action": "save",
                "title": "Yanlış fənn",
                "subject": str(foreign_subject.pk),  # müəllimin fənni deyil
                "exam_kind": "final",
                "group_id": str(group.id),
                "language": "az",
                "raw_text": VALID_TEXT,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(QuestionSubmission.objects.filter(title="Yanlış fənn").exists())

    def test_view_requires_exam_kind(self):
        # İmtahan növü məcburidir — seçilməyibsə göndəriş yaranmır.
        from apps.exams.models import StudentGroup

        group = StudentGroup.objects.create(teacher=self.teacher, organization=self.org, name="875i-novsuz")
        subject = self._subject(group=group)

        client = self._client_for(self.teacher)
        response = client.post(
            reverse("exams:question_submission_create"),
            {
                "action": "save",
                "title": "Növsüz göndəriş",
                "subject": str(subject.pk),
                "group_id": str(group.id),
                "language": "az",
                "raw_text": VALID_TEXT,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(QuestionSubmission.objects.filter(title="Növsüz göndəriş").exists())

    def test_view_save_respects_selection_and_points(self):
        from apps.exams.models import StudentGroup

        group = StudentGroup.objects.create(teacher=self.teacher, organization=self.org, name="875i")
        subject = self._subject(group=group)
        client = self._client_for(self.teacher)
        client.post(
            reverse("exams:question_submission_create"),
            {
                "action": "save",
                "title": "Seçim testi",
                "subject": str(subject.pk),
                "exam_kind": "final",
                "group_id": str(group.id),
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
        from apps.exams.models import StudentGroup

        group = StudentGroup.objects.create(teacher=self.teacher, organization=self.org, name="875i")
        subject = self._subject(group=group)
        client = self._client_for(self.teacher)
        client.post(
            reverse("exams:question_submission_create"),
            {
                "action": "save",
                "title": "Qeydli göndəriş",
                "subject": str(subject.pk),
                "exam_kind": "final",
                "group_id": str(group.id),
                "teacher_note": "5-8-ci suallar mühazirə 3-ə aiddir.",
                "language": "az",
                "raw_text": VALID_TEXT,
            },
        )
        submission = QuestionSubmission.objects.get(title="Qeydli göndəriş")
        self.assertEqual(submission.teacher_note, "5-8-ci suallar mühazirə 3-ə aiddir.")
        # Mərkəz baxış səhifəsində qeydi görür (kafedra təsdiqindən SONRA).
        self._to_center(submission)
        response = self._client_for(self.exam_center).get(
            reverse("exams:question_submission_review", kwargs={"submission_id": submission.id})
        )
        self.assertContains(response, "mühazirə 3-ə aiddir")

    def test_detail_edit_uses_workbench_and_resubmits(self):
        # Detal redaktəsi yeni-göndəriş workbench-i ilə eynidir: GET-də workbench
        # render olunur, action=save yenidən göndərmə (resubmit) deməkdir.
        from apps.exams.models import StudentGroup

        group = StudentGroup.objects.create(teacher=self.teacher, organization=self.org, name="875i-resubmit")
        subject = self._subject(group=group)
        submission = self._to_center(self._submission(title="Workbench redaktə", raw_text=TEXT_WITH_PROBLEM))
        reject_submission(submission, reviewer=self.exam_center, note="Düzəldin — cavablar işarəsizdir.")

        client = self._client_for(self.teacher)
        url = reverse("exams:question_submission_detail", kwargs={"submission_id": submission.id})
        response = client.get(url)
        self.assertContains(response, 'id="saveForm"')
        self.assertContains(response, "q-card")  # workbench sual kartları

        response = client.post(
            url,
            {
                "action": "save",
                "title": "Workbench redaktə 2",
                "subject": str(subject.pk),
                "exam_kind": "final",
                "group_id": str(group.id),
                "language": "az",
                "raw_text": VALID_TEXT,
            },
        )
        self.assertEqual(response.status_code, 302)
        submission.refresh_from_db()
        self.assertEqual(submission.status, QuestionSubmission.STATUS_SUBMITTED_TO_CHAIR)
        self.assertEqual(submission.title, "Workbench redaktə 2")
        self.assertEqual(submission.resubmission_count, 1)
        self.assertEqual(submission.error_count, 0)

    def test_view_submit_requires_group(self):
        from apps.exams.models import StudentGroup

        group = StudentGroup.objects.create(teacher=self.teacher, organization=self.org, name="875i-qrupsuz")
        subject = self._subject(group=group)
        client = self._client_for(self.teacher)
        response = client.post(
            reverse("exams:question_submission_create"),
            {
                "action": "save",
                "title": "Qrupsuz",
                "subject": str(subject.pk),
                "exam_kind": "final",
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

    def test_exam_center_sees_inline_filters(self):
        # "Qutunu aç" düyməsi ləğv edilib — filtr paneli bölmənin özündədir.
        self._to_center(self._submission(title="Bölmə testi"))
        client = self._client_for(self.exam_center)
        response = client.get(f"{reverse('accounts:profile')}?section=question-submissions")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bölmə testi")
        self.assertContains(response, "qsubf-bar")
        self.assertContains(response, 'name="qsub_faculty"')
        self.assertContains(response, 'name="qsub_lang"')
        self.assertNotContains(response, "Qutunu aç")

    def test_section_search_filters_list(self):
        self._submission(title="Riyaziyyat toplusu")
        self._submission(title="Fizika toplusu")
        client = self._client_for(self.teacher)
        response = client.get(f"{reverse('accounts:profile')}?section=question-submissions&qsub_q=Fizika")
        self.assertContains(response, "Fizika toplusu")
        self.assertNotContains(response, "Riyaziyyat toplusu")

    def test_section_status_filter(self):
        accepted = self._to_center(self._submission(title="Qəbul olunan toplu"))
        accept_submission(accepted, reviewer=self.exam_center)
        self._submission(title="Gözləyən toplu")
        client = self._client_for(self.teacher)
        response = client.get(f"{reverse('accounts:profile')}?section=question-submissions&qsub_status=accepted")
        self.assertContains(response, "Qəbul olunan toplu")
        self.assertNotContains(response, "Gözləyən toplu")

    def test_section_pagination(self):
        for i in range(12):
            self._submission(title=f"Səhifə testi {i:02d}")
        client = self._client_for(self.teacher)
        response = client.get(f"{reverse('accounts:profile')}?section=question-submissions")
        # 10 element/səhifə: ən yenilər birinci səhifədə, pager 2-ci səhifəyə link verir.
        self.assertContains(response, "Səhifə testi 11")
        self.assertNotContains(response, "Səhifə testi 01")
        self.assertContains(response, "qsub_page=2")

    def test_section_language_filter_for_reviewer(self):
        self._to_center(self._submission(title="AZ toplusu"))
        self._to_center(self._submission(title="EN toplusu", language="en"))
        client = self._client_for(self.exam_center)
        response = client.get(f"{reverse('accounts:profile')}?section=question-submissions&qsub_lang=en")
        self.assertContains(response, "EN toplusu")
        self.assertNotContains(response, "AZ toplusu")

    def test_section_faculty_filter_for_reviewer(self):
        from apps.exams.models import StudentGroup

        # Struktur `_Base`-də qurulub (fakültə → kafedra) — təkrar yaradılmır.
        faculty, kafedra = self.faculty, self.chair
        group = StudentGroup.objects.create(
            teacher=self.teacher, organization=self.org, name="875i-fak", org_unit=kafedra
        )
        self._to_center(self._submission(title="Fakültə daxili toplu", student_group=group, groups=[group]))
        self._to_center(self._submission(title="Fakültə xarici toplu"))

        client = self._client_for(self.exam_center)
        response = client.get(f"{reverse('accounts:profile')}?section=question-submissions&qsub_faculty={faculty.pk}")
        self.assertContains(response, "Fakültə daxili toplu")
        self.assertNotContains(response, "Fakültə xarici toplu")
        # Kafedra filtri subtree üzrə də işləyir.
        response = client.get(
            f"{reverse('accounts:profile')}?section=question-submissions"
            f"&qsub_faculty={faculty.pk}&qsub_kafedra={kafedra.pk}"
        )
        self.assertContains(response, "Fakültə daxili toplu")
        self.assertNotContains(response, "Fakültə xarici toplu")

    def test_teacher_can_delete_pending_submission(self):
        submission = self._submission(title="Silinəcək toplu")
        client = self._client_for(self.teacher)
        response = client.post(reverse("exams:question_submission_delete", kwargs={"submission_id": submission.id}))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(QuestionSubmission.objects.filter(id=submission.id).exists())

    def test_teacher_cannot_delete_accepted_submission(self):
        submission = self._to_center(self._submission(title="Silinməz toplu"))
        accept_submission(submission, reviewer=self.exam_center)
        client = self._client_for(self.teacher)
        client.post(reverse("exams:question_submission_delete", kwargs={"submission_id": submission.id}))
        self.assertTrue(QuestionSubmission.objects.filter(id=submission.id).exists())

    def test_rejected_detail_shows_verdict_banner(self):
        submission = self._to_center(self._submission(title="Bannerli toplu"))
        reject_submission(submission, reviewer=self.exam_center, note="2-ci sualı mütləq düzəldin.")
        client = self._client_for(self.teacher)
        response = client.get(reverse("exams:question_submission_detail", kwargs={"submission_id": submission.id}))
        self.assertContains(response, "qsubd-verdict--rejected")
        self.assertContains(response, "2-ci sualı mütləq düzəldin.")

    def test_review_page_renders_decision_choices(self):
        submission = self._to_center(self._submission(title="Qərar UI toplusu"))
        response = self._client_for(self.exam_center).get(
            reverse("exams:question_submission_review", kwargs={"submission_id": submission.id})
        )
        self.assertContains(response, "qsubr-choice--accept")
        self.assertContains(response, "qsubr-choice--reject")
        self.assertContains(response, 'name="decision"')

    def test_teacher_sees_rejected_alert(self):
        submission = self._to_center(self._submission(title="Geri qaytarılan"))
        reject_submission(submission, reviewer=self.exam_center, note="Düzəldin — cavablar işarəsizdir.")
        client = self._client_for(self.teacher)
        response = client.get(f"{reverse('accounts:profile')}?section=question-submissions")
        self.assertContains(response, "göndərişi geri qaytarıb")
        self.assertContains(response, "Rədd edilib — düzəldib yenidən göndərə bilərsiniz")

    def test_student_does_not_get_section(self):
        student = User.objects.create_user("qs_student", "qs_student@test.az", PASSWORD)
        _assign_user_to_org(student, self.org, ProfileRole.STUDENT, "student")
        client = self._client_for(student)
        response = client.get(f"{reverse('accounts:profile')}?section=question-submissions")
        # İcazəsiz bölmə default bölməyə düşür — göndəriş paneli görünmür.
        self.assertNotContains(response, "Yeni göndəriş", status_code=200)

    def test_teacher_sees_accepted_bank_name_in_list(self):
        # Qəbul edilən göndərişdə mərkəzin yazdığı bankın adı müəllimə görünür.
        submission = self._to_center(self._submission(title="Bank izi toplusu"))
        accept_submission(submission, reviewer=self.exam_center, new_bank_name="İz bankı 2026")
        client = self._client_for(self.teacher)
        response = client.get(f"{reverse('accounts:profile')}?section=question-submissions")
        self.assertContains(response, "İz bankı 2026")
        self.assertContains(response, "bankına əlavə olunub")


class QuestionBankCatalogTests(_Base):
    """Bank yaratma kartının yeni sahələri: kataloq fənni, imtahan növü,
    mənbə müəllim; siyahı filtri və müəllim axtarışı endpoint-i."""

    def test_center_creates_bank_with_catalog_fields(self):
        subject = self._subject(name="Aqrokimya", code="AQR201")
        client = self._client_for(self.exam_center)
        response = client.post(
            reverse("exams:question_bank_list"),
            {
                "action": "create_bank",
                "name": "Aqrokimya final bankı",
                "subject_id": str(subject.pk),
                "exam_kind": "final",
                "source_teacher_id": str(self.teacher.pk),
                "language": "az",
                "default_question_type": "test",
                # Köhnə formadan gələ biləcək paylaşım parametri nəzərə alınmır.
                "is_shared": "1",
            },
        )
        self.assertEqual(response.status_code, 302)
        bank = QuestionBank.objects.get(name="Aqrokimya final bankı")
        self.assertEqual(bank.subject_ref, subject)
        self.assertEqual(bank.subject, "Aqrokimya")
        self.assertEqual(bank.exam_kind, "final")
        self.assertEqual(bank.source_teacher, self.teacher)
        self.assertFalse(bank.is_shared)

    def test_bank_update_keeps_legacy_subject_text(self):
        bank = QuestionBank.objects.create(
            name="Köhnə bank",
            subject="Köhnə fənn",
            organization=self.org,
            created_by=self.exam_center,
        )
        client = self._client_for(self.exam_center)
        client.post(
            reverse("exams:question_bank_update", kwargs={"bank_id": bank.id}),
            {
                "name": "Köhnə bank",
                "subject_id": "text:Köhnə fənn",
                "exam_kind": "quiz",
                "language": "az",
                "default_question_type": "test",
            },
        )
        bank.refresh_from_db()
        self.assertEqual(bank.subject, "Köhnə fənn")
        self.assertIsNone(bank.subject_ref)
        self.assertEqual(bank.exam_kind, "quiz")

    def test_bank_section_kind_filter(self):
        QuestionBank.objects.create(
            name="Final toplusu QBX", organization=self.org, created_by=self.exam_center, exam_kind="final"
        )
        QuestionBank.objects.create(
            name="Quiz toplusu QBX", organization=self.org, created_by=self.exam_center, exam_kind="quiz"
        )
        client = self._client_for(self.exam_center)
        response = client.get(f"{reverse('accounts:profile')}?section=question-bank&bank_kind=final")
        self.assertContains(response, "Final toplusu QBX")
        self.assertNotContains(response, "Quiz toplusu QBX")

    def test_bank_section_search_matches_teacher_and_subject_code(self):
        subject = self._subject(name="Bitki mühafizəsi", code="BM203")
        QuestionBank.objects.create(
            name="Axtarış bankı QBX",
            organization=self.org,
            created_by=self.exam_center,
            subject_ref=subject,
            source_teacher=self.teacher,
        )
        client = self._client_for(self.exam_center)
        # Fənn kodu üzrə tapılır.
        response = client.get(f"{reverse('accounts:profile')}?section=question-bank&bank_search=BM203")
        self.assertContains(response, "Axtarış bankı QBX")
        # Müəllim istifadəçi adı üzrə tapılır.
        response = client.get(f"{reverse('accounts:profile')}?section=question-bank&bank_search=qs_teacher")
        self.assertContains(response, "Axtarış bankı QBX")

    def test_bank_teacher_search_endpoint(self):
        client = self._client_for(self.exam_center)
        response = client.get(reverse("exams:bank_teacher_search"), {"q": "qs_teacher"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(any(item["id"] == str(self.teacher.pk) for item in payload["results"]))

    def test_center_member_can_open_colleague_bank(self):
        # Mərkəz bank hovuzunun idarəçisidir: başqa mərkəz üzvünün yaratdığı
        # (paylaşılmamış) org bankı da açılmalıdır — əvvəl 404 idi.
        other_center = User.objects.create_user("qs_center2", "qs_center2@test.az", PASSWORD)
        _assign_user_to_org(other_center, self.org, ProfileRole.MEMBER, "exam_center")
        bank = QuestionBank.objects.create(
            name="Kolleqa bankı QBX", organization=self.org, created_by=other_center, is_shared=False
        )
        response = self._client_for(self.exam_center).get(
            reverse("exams:question_bank_detail", kwargs={"bank_id": bank.id})
        )
        self.assertEqual(response.status_code, 200)

    def test_center_cannot_open_foreign_org_bank(self):
        foreign_owner = User.objects.create_user("qs_foreign", "qs_foreign@test.az", PASSWORD)
        foreign_org = Organization.objects.create(
            name="Foreign University",
            org_type=OrganizationType.UNIVERSITY,
            owner=foreign_owner,
            status="active",
            is_active=True,
        )
        bank = QuestionBank.objects.create(name="Yad bank", organization=foreign_org, created_by=foreign_owner)
        response = self._client_for(self.exam_center).get(
            reverse("exams:question_bank_detail", kwargs={"bank_id": bank.id})
        )
        self.assertEqual(response.status_code, 404)


class SubmissionQuestionsEndpointTests(_Base):
    """Review sual siyahısının lazy fraqment endpoint-i: səhifələmə, filtr,
    axtarış və icazələr."""

    def _payload(self, client, submission, **params):
        response = client.get(
            reverse("exams:question_submission_questions", kwargs={"submission_id": submission.id}), params
        )
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_endpoint_paginates_with_stable_numbers(self):
        submission = self._to_center(self._submission(title="Lazy səhifələmə"))
        client = self._client_for(self.exam_center)
        first = self._payload(client, submission, offset=0, limit=1)
        self.assertEqual(first["returned"], 1)
        self.assertTrue(first["has_more"])
        self.assertIn("#1", first["html"])
        second = self._payload(client, submission, offset=1, limit=1)
        self.assertEqual(second["returned"], 1)
        self.assertFalse(second["has_more"])
        # Nömrə dilimdə də tam siyahıdakı yerini saxlayır.
        self.assertIn("#2", second["html"])
        self.assertEqual(second["counts"]["all"], 2)

    def test_endpoint_filters_and_search(self):
        submission = self._to_center(self._submission(raw_text=TEXT_WITH_PROBLEM, title="Lazy filtr"))
        client = self._client_for(self.exam_center)
        self.assertEqual(self._payload(client, submission, flag="error")["filtered_total"], 1)
        self.assertEqual(self._payload(client, submission, flag="clean")["filtered_total"], 0)
        self.assertEqual(self._payload(client, submission, q="Problemli")["filtered_total"], 1)
        # Variant mətnində də axtarır.
        self.assertEqual(self._payload(client, submission, q="Dördüncü")["filtered_total"], 1)
        self.assertEqual(self._payload(client, submission, q="tapılmayan-söz")["filtered_total"], 0)

    def test_endpoint_permission(self):
        submission = self._to_center(self._submission(title="Lazy icazə"))
        other_teacher = User.objects.create_user("qs_lazy_other", "qs_lazy_other@test.az", PASSWORD)
        _assign_user_to_org(other_teacher, self.org, ProfileRole.TEACHER, "teacher")
        response = self._client_for(other_teacher).get(
            reverse("exams:question_submission_questions", kwargs={"submission_id": submission.id})
        )
        self.assertEqual(response.status_code, 404)
        # Sahib müəllim, KAFEDRA MÜDİRİ və mərkəz görə bilir.
        self._payload(self._client_for(self.teacher), submission)
        self._payload(self._client_for(self.chair_head), submission)
        self._payload(self._client_for(self.exam_center), submission)

    def test_review_page_renders_lazy_shell(self):
        submission = self._to_center(self._submission(title="Lazy shell"))
        response = self._client_for(self.exam_center).get(
            reverse("exams:question_submission_review", kwargs={"submission_id": submission.id})
        )
        self.assertContains(response, "js-qsubq")
        self.assertContains(response, "data-questions-url")
        self.assertContains(response, "question_submission_review_questions.js")
