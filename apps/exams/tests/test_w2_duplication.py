"""
2026-09-14 (audit 2026-09-13, `findings/tests.md` §1 · F-T11) — `apps/exams/services/duplication.py`
0 % coverage idi: imtahan dublikatı (parametrlər + giriş icazələri + nəzarət
konfiqurasiyası) heç bir testlə örtülmürdü.

Servisin SƏNƏDLƏŞDİRİLMİŞ müqaviləsi (modul docstring-i):
* skalyar parametrlər (növ, vaxt, sual paylanması, rejim) kopyalanır;
* `slug` YENİ, `is_active=False` (qaralama), `access_code` boş, arxiv/silinmiş
  bayraqları sıfırlanır, tenant/kurs saxlanılır;
* M2M giriş icazələri (qruplar, fərdi tələbələr, istisnalar) kopyalanır;
* `ExamSupervisionConfig` varsa klonlanır;
* SUALLAR KÖÇÜRÜLMÜR (qəsdən — «dublikat → qaralama», müəllim bankdan sual
  qoşur). Brief «sual/variant/blok/dil variantı köçürülür» deyirdi; kod və
  docstring əksini deyir, test FAKTİKİ davranışı sənədləşdirir.

HTTP qatı (`exams:duplicate_exam`): yalnız POST, sahib-yalnız (403), yad
tenant / silinmiş imtahan → 404 (mövcudluq sızmır).
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.exams.models import (
    Exam,
    ExamLanguageVariant,
    ExamQuestion,
    ExamQuestionOption,
    ExamSupervisionConfig,
    QuestionBlock,
    StudentGroup,
)
from apps.exams.services.duplication import duplicate_exam
from apps.exams.tests.test_exam_center_policy import PASSWORD, _assign_user_to_org
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class _DuplicationBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("dup_owner", "dup_owner@test.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="Dup University",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        cls.teacher = User.objects.create_user("dup_teacher", "dup_teacher@test.az", PASSWORD)
        _assign_user_to_org(cls.teacher, cls.org, ProfileRole.TEACHER, "teacher")
        cls.other_teacher = User.objects.create_user("dup_teacher2", "dup_teacher2@test.az", PASSWORD)
        _assign_user_to_org(cls.other_teacher, cls.org, ProfileRole.TEACHER, "teacher")
        cls.student_a = User.objects.create_user("dup_student_a", "dup_a@test.az", PASSWORD)
        _assign_user_to_org(cls.student_a, cls.org, ProfileRole.STUDENT, "student")
        cls.student_b = User.objects.create_user("dup_student_b", "dup_b@test.az", PASSWORD)
        _assign_user_to_org(cls.student_b, cls.org, ProfileRole.STUDENT, "student")

        # Yad tenant — cross-org mənbə üçün.
        cls.other_owner = User.objects.create_user("dup_other_owner", "dup_oo@test.az", PASSWORD)
        cls.other_org = Organization.objects.create(
            name="Other Dup University",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.other_owner,
            status="active",
            is_active=True,
        )
        cls.foreign_teacher = User.objects.create_user("dup_foreign", "dup_foreign@test.az", PASSWORD)
        _assign_user_to_org(cls.foreign_teacher, cls.other_org, ProfileRole.TEACHER, "teacher")

        cls.group = StudentGroup.objects.create(organization=cls.org, teacher=cls.teacher, name="Qrup 101")
        cls.group.students.add(cls.student_a, cls.student_b)

        now = timezone.now()
        cls.source = Exam.objects.create(
            title="Mənbə imtahan",
            description="Təsvir",
            author=cls.teacher,
            organization=cls.org,
            exam_type="test",
            exam_type_extended="quiz",
            mode="hybrid",
            proctoring_level="strict",
            is_active=True,
            results_hidden_from_students=True,
            total_duration_minutes=45,
            default_question_time_seconds=90,
            max_attempts_per_user=2,
            random_question_count=7,
            fair_question_distribution_enabled=False,
            default_question_points=3,
            start_datetime=now + timedelta(days=1),
            end_datetime=now + timedelta(days=2),
            access_code="ABC123",
            settings={"shuffle": True, "nested": {"k": 1}},
            enable_paint=True,
        )
        cls.source.allowed_groups.set([cls.group])
        cls.source.allowed_users.set([cls.student_a])
        cls.source.excluded_users.set([cls.student_b])
        ExamSupervisionConfig.objects.create(
            exam=cls.source,
            enabled=True,
            force_fullscreen=True,
            grace_period_seconds=42,
            max_fullscreen_violations=7,
            detect_tab_switch=False,
        )
        block = QuestionBlock.objects.create(exam=cls.source, name="Blok 1", order=1)
        question = ExamQuestion.objects.create(
            exam=cls.source, block=block, order=1, text="Mənbə sualı", points=2, is_active=True
        )
        ExamQuestionOption.objects.create(question=question, text="A", is_correct=True)
        ExamQuestionOption.objects.create(question=question, text="B", is_correct=False)
        ExamLanguageVariant.objects.create(exam=cls.source, language="az", display_name="Azərbaycan", is_active=True)


class DuplicateExamServiceTests(_DuplicationBase):
    def test_scalar_settings_are_copied_but_state_is_reset(self):
        copy = duplicate_exam(exam=self.source, user=self.teacher)
        copy.refresh_from_db()

        self.assertNotEqual(copy.pk, self.source.pk)
        self.assertEqual(copy.title, "Mənbə imtahan (kopya)")
        for field in (
            "description",
            "exam_type",
            "exam_type_extended",
            "mode",
            "proctoring_level",
            "results_hidden_from_students",
            "total_duration_minutes",
            "default_question_time_seconds",
            "max_attempts_per_user",
            "random_question_count",
            "fair_question_distribution_enabled",
            "default_question_points",
            "start_datetime",
            "end_datetime",
            "enable_paint",
        ):
            with self.subTest(field=field):
                self.assertEqual(getattr(copy, field), getattr(self.source, field))

        # Qaralama vəziyyəti: nəşr olunmayıb, kod boş, arxiv/silinmiş deyil.
        self.assertFalse(copy.is_active)
        self.assertEqual(copy.access_code, "")
        self.assertFalse(copy.is_archived)
        self.assertIsNone(copy.archived_at)
        self.assertFalse(copy.is_deleted)
        self.assertIsNone(copy.deleted_at)
        # Yeni slug (unikal) və eyni tenant/müəllif.
        self.assertTrue(copy.slug)
        self.assertNotEqual(copy.slug, self.source.slug)
        self.assertEqual(copy.organization_id, self.org.pk)
        self.assertEqual(copy.author_id, self.teacher.pk)

    def test_settings_json_is_a_detached_copy(self):
        copy = duplicate_exam(exam=self.source, user=self.teacher)
        self.assertEqual(copy.settings, self.source.settings)
        copy.settings["shuffle"] = False
        copy.settings["added"] = 1
        self.source.refresh_from_db()
        self.assertEqual(self.source.settings, {"shuffle": True, "nested": {"k": 1}})

    def test_access_lists_are_copied(self):
        copy = duplicate_exam(exam=self.source, user=self.teacher)
        self.assertEqual(set(copy.allowed_groups.values_list("id", flat=True)), {self.group.pk})
        self.assertEqual(set(copy.allowed_users.values_list("id", flat=True)), {self.student_a.pk})
        self.assertEqual(set(copy.excluded_users.values_list("id", flat=True)), {self.student_b.pk})

    def test_supervision_config_is_cloned_not_shared(self):
        copy = duplicate_exam(exam=self.source, user=self.teacher)
        source_cfg = self.source.supervision_config
        copy_cfg = ExamSupervisionConfig.objects.get(exam=copy)
        self.assertNotEqual(copy_cfg.pk, source_cfg.pk)
        for field in (
            "enabled",
            "force_fullscreen",
            "grace_period_seconds",
            "max_fullscreen_violations",
            "detect_tab_switch",
            "violation_action",
        ):
            with self.subTest(field=field):
                self.assertEqual(getattr(copy_cfg, field), getattr(source_cfg, field))

    def test_without_supervision_config_copy_has_none(self):
        bare = Exam.objects.create(title="Konfiqsiz", author=self.teacher, organization=self.org, exam_type="test")
        copy = duplicate_exam(exam=bare, user=self.teacher)
        self.assertFalse(ExamSupervisionConfig.objects.filter(exam=copy).exists())

    def test_questions_blocks_and_variants_are_not_copied_by_design(self):
        """Docstring müqaviləsi: kopya 0 sualla başlayır; mənbə toxunulmaz qalır."""
        copy = duplicate_exam(exam=self.source, user=self.teacher)
        self.assertEqual(copy.questions.count(), 0)
        self.assertEqual(QuestionBlock.objects.filter(exam=copy).count(), 0)
        self.assertEqual(ExamLanguageVariant.objects.filter(exam=copy).count(), 0)
        # Mənbə dəyişmir.
        self.source.refresh_from_db()
        self.assertEqual(self.source.questions.count(), 1)
        self.assertEqual(QuestionBlock.objects.filter(exam=self.source).count(), 1)
        self.assertEqual(ExamLanguageVariant.objects.filter(exam=self.source).count(), 1)
        self.assertTrue(self.source.is_active)
        self.assertEqual(self.source.access_code, "ABC123")

    def test_copy_author_can_differ_from_source_author(self):
        """Superadmin başqasının imtahanını kopyalayanda kopya ONUN adına yaranır."""
        copy = duplicate_exam(exam=self.source, user=self.other_teacher)
        self.assertEqual(copy.author_id, self.other_teacher.pk)
        self.assertEqual(copy.organization_id, self.source.organization_id)

    def test_custom_title_suffix(self):
        copy = duplicate_exam(exam=self.source, user=self.teacher, title_suffix=" — 2027")
        self.assertEqual(copy.title, "Mənbə imtahan — 2027")

    def test_deleted_source_yields_live_draft(self):
        """Silinmiş mənbədən kopya «silinmiş» başlamamalıdır."""
        Exam.objects.filter(pk=self.source.pk).update(is_deleted=True, deleted_at=timezone.now())
        source = Exam.objects.get(pk=self.source.pk)
        copy = duplicate_exam(exam=source, user=self.teacher)
        self.assertFalse(copy.is_deleted)
        self.assertIsNone(copy.deleted_at)

    def test_two_copies_get_distinct_slugs(self):
        first = duplicate_exam(exam=self.source, user=self.teacher)
        second = duplicate_exam(exam=self.source, user=self.teacher)
        self.assertNotEqual(first.slug, second.slug)
        self.assertEqual(Exam.objects.filter(title="Mənbə imtahan (kopya)").count(), 2)


class DuplicateExamViewTests(_DuplicationBase):
    def _client_for(self, user, organization=None):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = (organization or self.org).slug
        session.save()
        return client

    def _url(self, exam=None):
        return reverse("exams:duplicate_exam", args=[(exam or self.source).slug])

    def test_owner_post_creates_draft_copy_and_redirects(self):
        client = self._client_for(self.teacher)
        before = Exam.objects.count()
        response = client.post(self._url())
        self.assertEqual(response.status_code, 302)
        self.assertIn("section=my-exams", response["Location"])
        self.assertEqual(Exam.objects.count(), before + 1)
        copy = Exam.objects.exclude(pk=self.source.pk).get(title="Mənbə imtahan (kopya)")
        self.assertFalse(copy.is_active)
        self.assertEqual(copy.organization_id, self.org.pk)
        self.assertEqual(copy.author_id, self.teacher.pk)

    def test_get_is_not_allowed(self):
        client = self._client_for(self.teacher)
        self.assertEqual(client.get(self._url()).status_code, 405)

    def test_non_owner_in_same_org_is_forbidden(self):
        client = self._client_for(self.other_teacher)
        before = Exam.objects.count()
        self.assertEqual(client.post(self._url()).status_code, 403)
        self.assertEqual(Exam.objects.count(), before)

    def test_foreign_tenant_source_is_404(self):
        """Yad təşkilatın müəllimi mənbəni GÖRMÜR — 403 deyil, 404 (IDOR)."""
        client = self._client_for(self.foreign_teacher, organization=self.other_org)
        before = Exam.objects.count()
        self.assertEqual(client.post(self._url()).status_code, 404)
        self.assertEqual(Exam.objects.count(), before)

    def test_deleted_source_is_404_via_http(self):
        Exam.objects.filter(pk=self.source.pk).update(is_deleted=True, deleted_at=timezone.now())
        client = self._client_for(self.teacher)
        self.assertEqual(client.post(self._url()).status_code, 404)

    def test_anonymous_is_redirected_to_login(self):
        response = Client().post(self._url())
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"])
