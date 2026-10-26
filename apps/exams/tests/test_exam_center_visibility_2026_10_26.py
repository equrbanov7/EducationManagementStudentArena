"""İmtahan mərkəzi midterm/final-ı yaradandan asılı olmayaraq görür (sahib 2026-10-26).

Sahib: «Midterm ya da final imtahanı yaradılıbsa onu imtahan mərkəzi işçisi də, imtahan
mərkəzi rəhbəri də görsün — bu, profildən asılı olmasın. Çünki sonra nə isə etmək lazım
gələndə başqa profil axtarılır.»

Kök səbəb: «İmtahanlarım» siyahısı və müəllim paneli səthləri (detal, redaktə, nəticə,
suallar, aktivləşdirmə) ``author=request.user`` ilə süzülürdü — mərkəzin bir hesabının
(və ya RİM-in) yaratdığı midterm/final digər mərkəz əməkdaşına 404 verirdi.

Yoxlanılır:
* mərkəz işçisi də, rəhbəri də başqasının midterm/final-ını «Midterm / Final» tabında
  görür (yaradanın adı ilə), detal / nəticə / redaktə / nəticə görünürlüyü işləyir;
* başqasının quiz-i görünmür və açılmır (əvvəlki kimi);
* başqa təşkilatın midterm-i heç vaxt görünmür / açılmır (tenant sərhədi);
* müəllimin görünüşü dəyişmir (tab yoxdur, başqasının midterm-i 404).
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.exams.models import Exam
from apps.exams.services.access_policy import (
    can_center_oversee_exam,
    is_exam_center_member,
    manageable_exams_q,
)
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType

User = get_user_model()

PROFILE_URL = reverse("accounts:profile")
CENTER_TAB_URL = f"{PROFILE_URL}?section=my-exams&exam_scope=center"
OWN_TAB_URL = f"{PROFILE_URL}?section=my-exams"


def _assign(user, organization, role_name, profile_role=ProfileRole.MEMBER):
    profile = user.profile
    profile.organization = organization
    profile.organization_type = organization.org_type
    profile.role = profile_role
    profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])
    Membership.objects.update_or_create(
        user=user,
        organization=organization,
        defaults={"role": organization.roles.get(name=role_name), "is_primary": True, "is_active": True},
    )


def _org(name, owner):
    return Organization.objects.create(
        name=name, org_type=OrganizationType.UNIVERSITY, owner=owner, status="active", is_active=True
    )


class _Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("ecv_owner", "ecv_owner@test.az", "x")
        cls.org = _org("ECV University", cls.owner)
        cls.other_org = _org("ECV Other University", cls.owner)

        cls.teacher = User.objects.create_user("ecv_teacher", "ecv_teacher@test.az", "x", first_name="Aygün")
        _assign(cls.teacher, cls.org, "teacher", ProfileRole.TEACHER)
        cls.other_teacher = User.objects.create_user("ecv_teacher2", "ecv_teacher2@test.az", "x")
        _assign(cls.other_teacher, cls.org, "teacher", ProfileRole.TEACHER)
        cls.head = User.objects.create_user("ecv_head", "ecv_head@test.az", "x")
        _assign(cls.head, cls.org, "exam_center_head")
        cls.staff = User.objects.create_user("ecv_staff", "ecv_staff@test.az", "x")
        _assign(cls.staff, cls.org, "exam_center_staff")
        cls.foreign_author = User.objects.create_user("ecv_foreign", "ecv_foreign@test.az", "x")
        _assign(cls.foreign_author, cls.other_org, "teacher", ProfileRole.TEACHER)

        def exam(title, author, category, organization=None):
            return Exam.objects.create(
                title=title,
                author=author,
                organization=organization or cls.org,
                exam_type="test",
                exam_type_extended=category,
            )

        cls.midterm = exam("ECV Midterm Fizika", cls.teacher, "midterm")
        cls.final = exam("ECV Final Kimya", cls.teacher, "final")
        cls.quiz = exam("ECV Quiz Riyaziyyat", cls.teacher, "quiz")
        cls.foreign_midterm = exam("ECV Yad Midterm", cls.foreign_author, "midterm", organization=cls.other_org)

    def _client(self, user, organization=None):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = (organization or self.org).slug
        session.save()
        return client


class ExamCenterOversightPolicyTests(_Base):
    def test_member_detection_and_tenant_boundary(self):
        for user in (self.head, self.staff):
            user.set_active_organization_context(self.org)
            self.assertTrue(is_exam_center_member(user, self.org))
            # Başqa təşkilat aktiv deyil — mərkəz üzvlüyü oraya keçmir.
            self.assertFalse(is_exam_center_member(user, self.other_org))
            self.assertTrue(can_center_oversee_exam(user, self.midterm))
            self.assertTrue(can_center_oversee_exam(user, self.final))
            self.assertFalse(can_center_oversee_exam(user, self.quiz))
            self.assertFalse(can_center_oversee_exam(user, self.foreign_midterm))
        self.teacher.set_active_organization_context(self.org)
        self.assertFalse(is_exam_center_member(self.teacher, self.org))
        self.assertFalse(can_center_oversee_exam(self.teacher, self.midterm))

    def test_manageable_q(self):
        self.staff.set_active_organization_context(self.org)
        visible = set(Exam.objects.filter(manageable_exams_q(self.staff, self.org)).values_list("pk", flat=True))
        self.assertEqual(visible, {self.midterm.pk, self.final.pk})
        self.other_teacher.set_active_organization_context(self.org)
        self.assertFalse(Exam.objects.filter(manageable_exams_q(self.other_teacher, self.org)).exists())


class ExamCenterListTests(_Base):
    def test_head_and_staff_see_teacher_midterm_and_final_in_center_tab(self):
        for user in (self.head, self.staff):
            with self.subTest(user=user.username):
                response = self._client(user).get(CENTER_TAB_URL)
                self.assertEqual(response.status_code, 200)
                listed = {exam.pk for exam in response.context["my_exams"]}
                self.assertEqual(listed, {self.midterm.pk, self.final.pk})
                center = response.context["my_exams_dashboard"]["center"]
                self.assertTrue(center["enabled"])
                self.assertTrue(center["is_open"])
                self.assertEqual(center["count"], 2)
                self.assertContains(response, "ECV Midterm Fizika")
                self.assertContains(response, "ECV Final Kimya")
                self.assertNotContains(response, "ECV Quiz Riyaziyyat")
                self.assertNotContains(response, "ECV Yad Midterm")
                # Kartda yaradan + tab.
                self.assertContains(response, "tx-tag--author", html=False)
                # Sahib 2026-10-26: «Kim tərəfindən yaradıldığı da görünsün» — hər kartda ad.
                self.assertContains(response, "data-exam-creator", count=2, html=False)
                self.assertContains(response, "Aygün")
                self.assertContains(response, "exam_scope=center", html=False)

    def test_center_tab_search_matches_creator_name(self):
        response = self._client(self.staff).get(
            PROFILE_URL, {"section": "my-exams", "exam_scope": "center", "exam_q": "Aygün"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual({exam.pk for exam in response.context["my_exams"]}, {self.midterm.pk, self.final.pk})

    def test_own_tab_stays_author_only_with_center_tab_count(self):
        response = self._client(self.staff).get(OWN_TAB_URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["my_exams"]), [])
        center = response.context["my_exams_dashboard"]["center"]
        self.assertTrue(center["enabled"])
        self.assertFalse(center["is_open"])
        self.assertEqual(center["count"], 2)

    def test_teacher_has_no_center_tab_and_scope_param_is_ignored(self):
        response = self._client(self.other_teacher).get(CENTER_TAB_URL)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["my_exams_dashboard"]["center"]["enabled"])
        self.assertEqual(list(response.context["my_exams"]), [])
        self.assertNotContains(response, "ECV Midterm Fizika")
        # Müəllifin öz siyahısı dəyişmir.
        own = self._client(self.teacher).get(OWN_TAB_URL)
        self.assertEqual({exam.pk for exam in own.context["my_exams"]}, {self.midterm.pk, self.final.pk, self.quiz.pk})
        self.assertNotContains(own, "tx-tag--author", html=False)

    def test_center_sees_deleted_midterm_in_trash(self):
        Exam.objects.filter(pk=self.midterm.pk).update(is_deleted=True)
        response = self._client(self.head).get(f"{PROFILE_URL}?section=my-exams&exam_view=trash")
        self.assertEqual(response.context["my_exams_dashboard"]["trash"]["count"], 1)


class ExamCenterDetailAccessTests(_Base):
    def test_head_and_staff_open_detail_and_results(self):
        for user in (self.head, self.staff):
            client = self._client(user)
            for exam in (self.midterm, self.final):
                with self.subTest(user=user.username, exam=exam.title):
                    detail = client.get(reverse("exams:teacher_exam_detail", kwargs={"slug": exam.slug}))
                    self.assertEqual(detail.status_code, 200)
                    self.assertContains(detail, "data-exam-creator", html=False)
                    self.assertContains(detail, "Aygün")
                    results = client.get(reverse("exams:teacher_exam_results", kwargs={"slug": exam.slug}))
                    self.assertEqual(results.status_code, 200)
                    self.assertContains(results, "Aygün")
                    edit = client.get(reverse("exams:edit_exam", kwargs={"slug": exam.slug}) + "?modal=1")
                    self.assertEqual(edit.status_code, 200)

    def test_creator_shown_to_center_on_own_exam_but_not_to_author_teacher(self):
        own_final = Exam.objects.create(
            title="ECV Mərkəz finalı",
            author=self.head,
            organization=self.org,
            exam_type="test",
            exam_type_extended="final",
        )
        detail = self._client(self.head).get(reverse("exams:teacher_exam_detail", kwargs={"slug": own_final.slug}))
        self.assertContains(detail, "data-exam-creator", html=False)
        teacher_detail = self._client(self.teacher).get(
            reverse("exams:teacher_exam_detail", kwargs={"slug": self.midterm.slug})
        )
        self.assertEqual(teacher_detail.status_code, 200)
        self.assertNotContains(teacher_detail, "data-exam-creator", html=False)

    def test_staff_can_toggle_results_visibility_of_teacher_midterm(self):
        response = self._client(self.staff).post(
            reverse("exams:toggle_exam_results_visibility", kwargs={"slug": self.midterm.slug}),
            {"desired_state": "1"},
        )
        self.assertEqual(response.status_code, 302)
        self.midterm.refresh_from_db()
        self.assertTrue(self.midterm.results_hidden_from_students)

    def test_quiz_and_foreign_org_exam_stay_closed(self):
        client = self._client(self.staff)
        for exam in (self.quiz, self.foreign_midterm):
            with self.subTest(exam=exam.title):
                detail = client.get(reverse("exams:teacher_exam_detail", kwargs={"slug": exam.slug}))
                self.assertEqual(detail.status_code, 404)
                edit = client.get(reverse("exams:edit_exam", kwargs={"slug": exam.slug}) + "?modal=1")
                self.assertIn(edit.status_code, (403, 404))

    def test_other_teacher_still_gets_404_on_foreign_midterm(self):
        client = self._client(self.other_teacher)
        detail = client.get(reverse("exams:teacher_exam_detail", kwargs={"slug": self.midterm.slug}))
        self.assertEqual(detail.status_code, 404)
        results = client.get(reverse("exams:teacher_exam_results", kwargs={"slug": self.midterm.slug}))
        self.assertEqual(results.status_code, 404)
