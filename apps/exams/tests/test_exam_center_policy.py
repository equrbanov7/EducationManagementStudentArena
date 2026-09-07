"""
İmtahan mərkəzi siyasəti testləri.

Qayda:
* FINAL imtahanın sual məzmunu (əlavə/redaktə/silmə, workbench, bank picker,
  dil meneceri) — yalnız imtahan mərkəzi (və superadmin).
* Sual bankı yaratmaq — yalnız imtahan mərkəzi.
* Müəllim quiz/midterm/kateqoriyasız imtahanlarda sərbəstdir və ExamForm-da
  "final" kateqoriyasını seçə bilməz.
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.exams.forms import ExamForm
from apps.exams.models import Exam, QuestionBank
from apps.exams.services.access_policy import (
    can_create_question_bank,
    can_manage_exam_questions,
    is_exam_center_user,
)
from apps.organizations.models import Membership, Organization
from apps.registrar.models import Subject
from core.constants import OrganizationType

User = get_user_model()

PASSWORD = "StrongPass123!"


def _assign_user_to_org(user, organization, profile_role, membership_role_name):
    profile = user.profile
    profile.organization = organization
    profile.organization_type = organization.org_type
    profile.role = profile_role
    profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])
    Membership.objects.update_or_create(
        user=user,
        organization=organization,
        defaults={
            "role": organization.roles.get(name=membership_role_name),
            "is_primary": True,
            "is_active": True,
        },
    )


class _Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("ec_owner", "ec_owner@test.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="EC University",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )

        cls.teacher = User.objects.create_user("ec_teacher", "ec_teacher@test.az", PASSWORD)
        _assign_user_to_org(cls.teacher, cls.org, ProfileRole.TEACHER, "teacher")

        cls.exam_center = User.objects.create_user("ec_center", "ec_center@test.az", PASSWORD)
        _assign_user_to_org(cls.exam_center, cls.org, ProfileRole.MEMBER, "exam_center_head")

        # Final/midterm imtahanlar üçün fənn (registrar.Subject) məcburidir.
        cls.subject = Subject.objects.create(organization=cls.org, code="SUBJ101", name="Test Fənni")

        # Legacy hal: müəllifi müəllim olan final (məzmun idarəsi yenə bağlıdır).
        cls.final_exam = Exam.objects.create(
            title="Final imtahanı",
            author=cls.teacher,
            organization=cls.org,
            exam_type="test",
            exam_type_extended="final",
        )
        # Normal axın: finalı imtahan mərkəzi özü yaradır və suallarını yükləyir.
        cls.center_final_exam = Exam.objects.create(
            title="Mərkəz finalı",
            author=cls.exam_center,
            organization=cls.org,
            exam_type="test",
            exam_type_extended="final",
        )
        cls.quiz_exam = Exam.objects.create(
            title="Quiz imtahanı",
            author=cls.teacher,
            organization=cls.org,
            exam_type="test",
            exam_type_extended="quiz",
        )

    def _client_for(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client


class ExamCenterPolicyUnitTests(_Base):
    def setUp(self):
        # Rol yoxlamaları (is_exam_center və s.) aktiv org kontekstinə bağlıdır;
        # HTTP axınında bunu middleware qurur, unit testdə əl ilə veririk.
        self.teacher.set_active_organization_context(self.org)
        self.exam_center.set_active_organization_context(self.org)

    def test_is_exam_center_user(self):
        self.assertTrue(is_exam_center_user(self.exam_center))
        self.assertFalse(is_exam_center_user(self.teacher))

    def test_final_exam_questions_only_exam_center(self):
        self.assertFalse(can_manage_exam_questions(self.teacher, self.final_exam))
        self.assertTrue(can_manage_exam_questions(self.exam_center, self.final_exam))

    def test_non_final_exam_questions_open_to_teacher(self):
        self.assertTrue(can_manage_exam_questions(self.teacher, self.quiz_exam))
        # Kateqoriyasız (legacy) imtahan da müəllimə açıqdır.
        untyped = Exam.objects.create(title="Adi imtahan", author=self.teacher, organization=self.org, exam_type="test")
        self.assertTrue(can_manage_exam_questions(self.teacher, untyped))

    def test_question_bank_creation_teacher_and_exam_center(self):
        """2026-08-15: müəllim də yarada bilər (view qatı təyinatı «quiz»-ə bağlayır)."""
        self.assertTrue(can_create_question_bank(self.teacher))
        self.assertTrue(can_create_question_bank(self.exam_center))

    def test_superuser_bypasses(self):
        root = User.objects.create_superuser("ec_root", "root@test.az", PASSWORD)
        self.assertTrue(is_exam_center_user(root))
        self.assertTrue(can_manage_exam_questions(root, self.final_exam))
        self.assertTrue(can_create_question_bank(root))


class FinalExamQuestionViewTests(_Base):
    """View səviyyəsində: müəllim final imtahanın sual endpointlərinə düşə bilməz."""

    def _question_urls(self, exam):
        return [
            reverse("exams:add_exam_question", kwargs={"slug": exam.slug}),
            reverse("exams:test_question_bank", kwargs={"slug": exam.slug}),
            reverse("exams:exam_bank_picker", kwargs={"slug": exam.slug}),
            reverse("exams:exam_language_manager", kwargs={"slug": exam.slug}),
        ]

    def test_teacher_blocked_on_final_exam_question_views(self):
        client = self._client_for(self.teacher)
        for url in self._question_urls(self.final_exam):
            response = client.get(url)
            self.assertEqual(response.status_code, 403, url)

    def test_teacher_allowed_on_quiz_exam_question_views(self):
        client = self._client_for(self.teacher)
        for url in self._question_urls(self.quiz_exam):
            response = client.get(url)
            self.assertIn(response.status_code, (200, 302), url)
            if response.status_code == 302:
                self.assertNotIn("login", response["Location"])

    def test_exam_center_allowed_on_own_final_exam_question_views(self):
        client = self._client_for(self.exam_center)
        for url in self._question_urls(self.center_final_exam):
            response = client.get(url)
            self.assertIn(response.status_code, (200, 302), url)
            if response.status_code == 302:
                self.assertNotIn("login", response["Location"])

    def test_teacher_blocked_on_final_questions_bank_mutation(self):
        client = self._client_for(self.teacher)
        url = reverse("exams:teacher_questions_bank", kwargs={"slug": self.final_exam.slug})
        # GET (baxış) açıqdır…
        self.assertEqual(client.get(url).status_code, 200)
        # …amma mutasiya (bulk silmə) qadağandır.
        response = client.post(url, {"bulk_action": "delete_all"})
        self.assertEqual(response.status_code, 403)


class QuestionBankCreationViewTests(_Base):
    def test_teacher_creates_personal_quiz_bank_only(self):
        """2026-08-15: müəllim ŞƏXSİ bank yarada bilər — təyinat məcburi «quiz»,
        final/midterm göndərsə belə server «quiz»-ə bağlayır; bank paylaşılmır,
        mənbə müəllim özüdür."""
        client = self._client_for(self.teacher)
        response = client.post(
            reverse("exams:question_bank_list"),
            {"action": "create_bank", "name": "Müəllim bankı", "exam_kind": "final"},
        )
        self.assertEqual(response.status_code, 302)
        bank = QuestionBank.objects.get(name="Müəllim bankı")
        self.assertEqual(bank.exam_kind, "quiz")
        self.assertFalse(bank.is_shared)
        self.assertEqual(bank.created_by_id, self.teacher.id)
        self.assertEqual(bank.source_teacher_id, self.teacher.id)

    def test_overlong_bank_name_is_refused_not_500(self):
        """QA 2026-09-05 EXAMS-01: 255+ simvol bank adı DB DataError (500) verirdi."""
        client = self._client_for(self.teacher)
        response = client.post(
            reverse("exams:question_bank_list"),
            {"action": "create_bank", "name": "B" * 300, "exam_kind": "quiz"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(QuestionBank.objects.filter(name__startswith="BBBB").exists())

    def test_teacher_cannot_edit_own_bank_to_final(self):
        client = self._client_for(self.teacher)
        client.post(
            reverse("exams:question_bank_list"),
            {"action": "create_bank", "name": "Müəllim quiz bankı"},
        )
        bank = QuestionBank.objects.get(name="Müəllim quiz bankı")
        response = client.post(
            reverse("exams:question_bank_update", args=[bank.id]),
            {"name": "Müəllim quiz bankı", "exam_kind": "midterm"},
        )
        self.assertEqual(response.status_code, 302)
        bank.refresh_from_db()
        self.assertEqual(bank.exam_kind, "quiz")

    def test_duplicate_bank_name_is_refused_not_silently_created_twice(self):
        """QA 2026-09-05 EXAMS-05: eyni müəllim eyni adla ikinci bank yaradanda
        səssizcə iki ayrı bank (id 4/6) yaranırdı."""
        client = self._client_for(self.teacher)
        first = client.post(
            reverse("exams:question_bank_list"),
            {"action": "create_bank", "name": "QA-Bank T1", "exam_kind": "quiz"},
        )
        self.assertEqual(first.status_code, 302)
        second = client.post(
            reverse("exams:question_bank_list"),
            {"action": "create_bank", "name": "qa-bank t1", "exam_kind": "quiz"},
        )
        self.assertEqual(second.status_code, 302)
        self.assertEqual(QuestionBank.objects.filter(name__iexact="QA-Bank T1", created_by=self.teacher).count(), 1)

    def test_same_name_different_subject_is_allowed(self):
        """Eyni ad, FƏRQLİ fənn — bu dublikat sayılmır (`created_by`+`name`+`subject_ref`)."""
        client = self._client_for(self.teacher)
        client.post(
            reverse("exams:question_bank_list"),
            {"action": "create_bank", "name": "Ümumi bank", "exam_kind": "quiz"},
        )
        client.post(
            reverse("exams:question_bank_list"),
            {
                "action": "create_bank",
                "name": "Ümumi bank",
                "exam_kind": "quiz",
                "subject_id": str(self.subject.id),
            },
        )
        self.assertEqual(QuestionBank.objects.filter(name="Ümumi bank", created_by=self.teacher).count(), 2)

    def test_same_name_different_teacher_is_allowed(self):
        """Eyni ad, FƏRQLİ yaradan — dublikat qapısı YALNIZ öz banklarına baxır."""
        self._client_for(self.teacher).post(
            reverse("exams:question_bank_list"),
            {"action": "create_bank", "name": "Paylaşılan ad", "exam_kind": "quiz"},
        )
        self._client_for(self.exam_center).post(
            reverse("exams:question_bank_list"),
            {"action": "create_bank", "name": "Paylaşılan ad", "exam_kind": "quiz"},
        )
        self.assertEqual(QuestionBank.objects.filter(name="Paylaşılan ad").count(), 2)

    def test_exam_center_can_create_bank(self):
        client = self._client_for(self.exam_center)
        response = client.post(
            reverse("exams:question_bank_list"),
            {"action": "create_bank", "name": "Mərkəz bankı", "exam_kind": "final"},
        )
        self.assertEqual(response.status_code, 302)
        bank = QuestionBank.objects.get(name="Mərkəz bankı")
        self.assertEqual(bank.exam_kind, "final")


class ExamFormFinalCategoryTests(_Base):
    def setUp(self):
        self.teacher.set_active_organization_context(self.org)
        self.exam_center.set_active_organization_context(self.org)

    def _form_data(self, **overrides):
        data = {
            "title": "Yeni imtahan",
            "exam_type": "test",
            "exam_type_extended": "final",
            "random_question_count": 10,
            # Final/midterm üçün fənn məcburidir (bax ExamForm.clean).
            "subject": self.subject.pk,
        }
        data.update(overrides)
        return data

    def test_teacher_cannot_select_final_category(self):
        form = ExamForm(self._form_data(), user=self.teacher, organization=self.org)
        self.assertFalse(form.is_valid())
        self.assertIn("exam_type_extended", form.errors)

    def test_teacher_final_and_midterm_choices_hidden(self):
        # 2026-07 qaydası: midterm (kollokvium) da yalnız imtahan mərkəzinindir.
        form = ExamForm(user=self.teacher, organization=self.org)
        choice_values = {choice[0] for choice in form.fields["exam_type_extended"].choices}
        self.assertNotIn("final", choice_values)
        self.assertNotIn("midterm", choice_values)
        self.assertIn("quiz", choice_values)

    def test_exam_center_can_select_final_category(self):
        form = ExamForm(self._form_data(), user=self.exam_center, organization=self.org)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["exam_type_extended"], "final")

    def test_exam_center_can_open_create_exam_modal(self):
        response = self._client_for(self.exam_center).get(reverse("exams:create_exam") + "?modal=1")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="exam_type_extended"', html=False)
        self.assertContains(response, 'value="final"', html=False)

    def test_teacher_can_select_quiz_only(self):
        form = ExamForm(self._form_data(exam_type_extended="quiz"), user=self.teacher, organization=self.org)
        self.assertTrue(form.is_valid(), form.errors)

    def test_teacher_cannot_select_midterm(self):
        form = ExamForm(self._form_data(exam_type_extended="midterm"), user=self.teacher, organization=self.org)
        self.assertFalse(form.is_valid())
        self.assertIn("exam_type_extended", form.errors)

    def test_teacher_editing_existing_final_keeps_value(self):
        # Mövcud final instansının dəyəri dəyişmirsə redaktə partlamır.
        form = ExamForm(
            self._form_data(title="Final imtahanı"),
            instance=self.final_exam,
            user=self.teacher,
            organization=self.org,
        )
        self.assertTrue(form.is_valid(), form.errors)
