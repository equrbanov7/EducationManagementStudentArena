"""W7 `w7cohort` (2026-09-14): köhnə imtahan-kohort (`StudentGroup`) səthinin yığışdırılması.

Sahibin 2026-09-07 qərarı: qrup reyestri əsasdır, köhnə kohort səthi silinməyə
gedir. Bu dalğada məlumat silinmir, model qalır — yalnız səth gizlədilir:

* kohortu OLMAYAN təşkilat → `/exams/groups/` əvəzlənmə kartı (200, boş siyahı/
  modal/JS yoxdur; reyestr + sehrbaz keçidləri; `group.manage` olanda ikinci
  dərəcəli «köhnə kohort yarat» keçidi), yaratma səhifəsində kart + yığılmış forma,
  sehrbazda `allowed_groups` bloku yoxdur, nəticə filtrində kohort variantı yoxdur;
* kohortu OLAN tenant → hər şey əvvəlki kimi (köhnə siyahı şablonu, modal, forma);
* icazə qapıları dəyişmir (tələbə → 403).
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.exams.domain.student_group_deprecation import organization_has_legacy_cohorts
from apps.exams.models import Exam, StudentGroup
from apps.exams.tests.test_views import _assign_user_to_org
from apps.exams.views.teacher.results._group_options import KIND_COHORT, available_group_options
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()
PASSWORD = "StrongPass123!"

LIST_URL = reverse("exams:teacher_group_list")
CREATE_URL = reverse("exams:create_student_group")
DEPRECATED_TEMPLATE = "exams/teacher/teacher_group_list_deprecated.html"
LEGACY_TEMPLATE = "exams/teacher/teacher_group_list.html"
CREATE_TEMPLATE = "exams/teacher/create_student_group.html"


def _client_for(user, organization) -> Client:
    client = Client()
    client.force_login(user)
    session = client.session
    session["active_organization"] = organization.slug
    session.save()
    return client


class _Fixture(TestCase):
    """Bir təşkilat: sahib (group.manage), adi müəllim, tələbə; kohort YOXDUR."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("w7c_owner", "w7c_owner@test.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="W7C University",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(cls.owner, cls.org, ProfileRole.ORG_OWNER)
        cls.teacher = User.objects.create_user("w7c_teacher", "w7c_teacher@test.az", PASSWORD)
        _assign_user_to_org(cls.teacher, cls.org, ProfileRole.TEACHER)
        cls.student = User.objects.create_user("w7c_student", "w7c_student@test.az", PASSWORD)
        _assign_user_to_org(cls.student, cls.org, ProfileRole.STUDENT)

    def _make_cohort(self, name="W7C Cohort"):
        group = StudentGroup.objects.create(teacher=self.teacher, organization=self.org, name=name)
        group.teachers.add(self.teacher)
        group.students.add(self.student)
        return group

    def _registry_url(self):
        return f"{reverse('accounts:profile')}?section=groups-registry"

    def _wizard_url(self):
        return f"{reverse('accounts:profile')}?section=my-exams"


class OrganizationHasLegacyCohortsTest(_Fixture):
    def test_false_without_cohorts_and_none_org(self):
        self.assertFalse(organization_has_legacy_cohorts(self.org))
        self.assertFalse(organization_has_legacy_cohorts(None))

    def test_true_when_org_has_a_cohort_even_outside_actor_scope(self):
        # Meyar TƏŞKİLAT səviyyəsindədir — başqa müəllimin kohortu da səthi saxlayır.
        other = User.objects.create_user("w7c_other", "w7c_other@test.az", PASSWORD)
        _assign_user_to_org(other, self.org, ProfileRole.TEACHER)
        StudentGroup.objects.create(teacher=other, organization=self.org, name="Other's cohort")
        self.assertTrue(organization_has_legacy_cohorts(self.org))

    def test_is_a_single_exists_query(self):
        with CaptureQueriesContext(connection) as ctx:
            organization_has_legacy_cohorts(self.org)
        self.assertEqual(len(ctx.captured_queries), 1)
        # `.exists()` → `SELECT 1 … LIMIT 1` (sətirlər yüklənmir).
        self.assertIn("LIMIT 1", ctx.captured_queries[0]["sql"])


class GroupListWithoutCohortsTest(_Fixture):
    def test_manager_sees_deprecation_notice_with_registry_wizard_and_secondary_create_links(self):
        response = _client_for(self.owner, self.org).get(LIST_URL)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, DEPRECATED_TEMPLATE)
        self.assertTemplateNotUsed(response, LEGACY_TEMPLATE)
        html = response.content.decode()
        self.assertIn("data-legacy-cohort-notice", html)
        self.assertIn(f'href="{self._registry_url()}" data-legacy-cohort-registry-link', html)
        self.assertIn(f'href="{self._wizard_url()}" data-legacy-cohort-wizard-link', html)
        # `group.manage` → ikinci dərəcəli köhnə yaratma keçidi qalır (tenant hələ istəyə bilər).
        self.assertIn(f'href="{CREATE_URL}" data-legacy-cohort-create-link', html)
        # Boş siyahı, modal və siyahı JS-i render OLUNMUR.
        self.assertNotIn('id="groupModal"', html)
        self.assertNotIn("exams/js/teacher_group_list.js", html)
        self.assertNotIn('id="groupListSearch"', html)
        self.assertIn("exams/css/legacy_cohort_notice.css", html)

    def test_plain_teacher_sees_notice_without_create_link(self):
        response = _client_for(self.teacher, self.org).get(LIST_URL)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, DEPRECATED_TEMPLATE)
        html = response.content.decode()
        self.assertIn("data-legacy-cohort-notice", html)
        self.assertNotIn(CREATE_URL, html)
        self.assertIn(self._registry_url(), html)

    def test_student_permission_gate_unchanged(self):
        client = _client_for(self.student, self.org)
        self.assertEqual(client.get(LIST_URL).status_code, 403)
        self.assertEqual(client.get(CREATE_URL).status_code, 403)

    def test_plain_teacher_still_cannot_open_create_page(self):
        self.assertEqual(_client_for(self.teacher, self.org).get(CREATE_URL).status_code, 403)

    def test_notice_page_has_no_inline_style_or_script(self):
        html = _client_for(self.owner, self.org).get(LIST_URL).content.decode()
        notice = html[html.index("data-legacy-cohort-page") :]
        notice = notice[: notice.index("</section>")]
        self.assertNotIn("<style", notice)
        self.assertNotIn("<script", notice)
        self.assertNotIn(' style="', notice)


class CreatePageWithoutCohortsTest(_Fixture):
    def test_manager_gets_notice_and_collapsed_legacy_form(self):
        response = _client_for(self.owner, self.org).get(CREATE_URL)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, CREATE_TEMPLATE)
        html = response.content.decode()
        self.assertIn('data-legacy-cohort-page="create"', html)
        self.assertIn("data-legacy-cohort-notice", html)
        self.assertIn(self._registry_url(), html)
        self.assertIn(self._wizard_url(), html)
        # Kartda «köhnə kohort yarat» keçidi YOXDUR — artıq yaratma səhifəsindəyik.
        self.assertNotIn("data-legacy-cohort-create-link", html)
        # Forma qalır, amma yığılmış <details> içindədir (icazə qapısı dəyişməyib).
        details_start = html.index("data-legacy-cohort-form-details")
        self.assertIn(reverse("exams:teacher_create_group"), html[details_start:])
        self.assertIn('id="createGroupForm"', html[details_start:])
        self.assertNotIn('<details class="legacy-cohort-details" open', html)

    def test_invalid_post_rerender_keeps_notice_context(self):
        client = _client_for(self.owner, self.org)
        response = client.post(reverse("exams:teacher_create_group"), {"name": ""})
        self.assertEqual(response.status_code, 400)
        html = response.content.decode()
        self.assertIn("data-legacy-cohort-notice", html)
        self.assertIn("data-legacy-cohort-form-details", html)


class SurfacesWithCohortsUnchangedTest(_Fixture):
    def setUp(self):
        self.cohort = self._make_cohort()

    def test_list_renders_legacy_page_without_notice(self):
        response = _client_for(self.owner, self.org).get(LIST_URL)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, LEGACY_TEMPLATE)
        self.assertTemplateNotUsed(response, DEPRECATED_TEMPLATE)
        html = response.content.decode()
        self.assertIn("W7C Cohort", html)
        self.assertIn('id="groupModal"', html)
        self.assertIn(CREATE_URL, html)
        self.assertNotIn("data-legacy-cohort-notice", html)
        self.assertNotIn("legacy_cohort_notice.css", html)

    def test_plain_teacher_sees_own_cohort_list_without_create_link(self):
        response = _client_for(self.teacher, self.org).get(LIST_URL)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, LEGACY_TEMPLATE)
        self.assertContains(response, "W7C Cohort")
        self.assertNotContains(response, CREATE_URL)

    def test_create_page_renders_plain_form_without_notice_or_details(self):
        response = _client_for(self.owner, self.org).get(CREATE_URL)
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertNotIn("data-legacy-cohort-notice", html)
        self.assertNotIn("data-legacy-cohort-form-details", html)
        self.assertNotIn("<details", html)
        self.assertIn('id="createGroupForm"', html)
        self.assertIn(reverse("exams:teacher_create_group"), html)

    def test_list_query_count_independent_of_cohort_count(self):
        client = _client_for(self.owner, self.org)
        # İlk sorğu soyuq keşləri (content-type, sessiya) doldurur — müqayisə isti vəziyyətdədir.
        self.assertEqual(client.get(LIST_URL).status_code, 200)
        with CaptureQueriesContext(connection) as one:
            self.assertEqual(client.get(LIST_URL).status_code, 200)
        for index in range(3):
            self._make_cohort(name=f"W7C Cohort {index}")
        with CaptureQueriesContext(connection) as many:
            response = client.get(LIST_URL)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "W7C Cohort 2")
        self.assertEqual(len(one.captured_queries), len(many.captured_queries))


class WizardAndResultsWithoutCohortsTest(_Fixture):
    def _exam(self, title="W7C Exam"):
        return Exam.objects.create(
            title=title,
            author=self.teacher,
            organization=self.org,
            exam_type="test",
            exam_type_extended="quiz",
            is_active=True,
            is_public=False,
            start_datetime=timezone.now() - timedelta(hours=1),
            end_datetime=timezone.now() + timedelta(days=2),
        )

    def test_wizard_has_no_legacy_cohort_block_without_cohorts(self):
        client = _client_for(self.teacher, self.org)
        response = client.get(reverse("exams:create_exam"), {"modal": "1"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('name="allowed_units"', html)
        self.assertNotIn('name="allowed_groups"', html)
        self.assertNotIn("create-exam-legacy-groups", html)

    def test_wizard_shows_legacy_cohort_block_when_org_has_cohorts(self):
        self._make_cohort()
        client = _client_for(self.teacher, self.org)
        response = client.get(reverse("exams:create_exam"), {"modal": "1"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn('name="allowed_units"', html)
        self.assertIn('name="allowed_groups"', html)

    def test_results_group_options_contain_no_cohort_kind_without_cohorts(self):
        exam = self._exam()
        options = available_group_options(exam)
        self.assertEqual([option for option in options if option.kind == KIND_COHORT], [])

    def test_results_group_options_include_cohort_when_exam_is_assigned_one(self):
        exam = self._exam()
        cohort = self._make_cohort()
        exam.allowed_groups.add(cohort)
        options = available_group_options(exam)
        self.assertEqual([option.name for option in options if option.kind == KIND_COHORT], ["W7C Cohort"])
