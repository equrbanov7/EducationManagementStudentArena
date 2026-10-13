"""Rol auditi 2026-10-13 — B12 (sərbəst iş / kurs işi kurs sistemində) və B19 (unit-exams əhatəsi).

B12: sahib qaydası 2026-10-10 «sərbəst iş ləğv olur — kodu saxla». Kurs sisteminin «Sərbəst iş»
(kurs tapşırığı) və «Kurs işi» (layihə) sətirləri/tabları/badge-ləri RİM bayrağı
(`academic.selfwork_enabled` / `academic.coursework_enabled`, defolt SÖNDÜRÜLÜ) ilə gizlənir;
imtahan və lab işi həmişə qalır.

B19: `unit-exams` əvvəl müəllifin alt-ağacda İSTƏNİLƏN üzvlüyünü sayırdı — başqa kafedranın yükünü
alan müəllimin ƏLAVƏ (`is_primary=False`) üzvlüyü onun bütün imtahanlarını bu dekana açırdı.
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.organizations.models import Membership, Organization, OrgUnit, Role
from core.constants import OrganizationType, OrgUnitType, RoleScopeType

User = get_user_model()

FLAGS_ON = {"ACADEMIC_SELFWORK_ENABLED": True, "ACADEMIC_COURSEWORK_ENABLED": True}


def _assign(user, organization, profile_role, role_name):
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


class _CourseWorld(TestCase):
    """Bir müəllim, bir tələbə; imtahan + tapşırıq + layihə + lab — hamısı «yoxlanılacaq» vəziyyətdə."""

    @classmethod
    def setUpTestData(cls):
        from apps.assignments.models import Assignment, Submission
        from apps.courses.models import Course
        from apps.exams.models import Exam, ExamAttempt
        from apps.labs.models import Lab, LabAssignment, LabSubmission
        from apps.projects.models import Project, ProjectSubmission

        now = timezone.now()
        cls.teacher = User.objects.create_user("rab12_teacher", "rab12_t@x.test", "pw12345678")
        cls.student = User.objects.create_user("rab12_student", "rab12_s@x.test", "pw12345678")
        cls.org = Organization.objects.create(
            name="RAB12", org_type=OrganizationType.SCHOOL, owner=cls.teacher, status="active", is_active=True
        )
        _assign(cls.teacher, cls.org, ProfileRole.TEACHER, "teacher")
        _assign(cls.student, cls.org, ProfileRole.STUDENT, "student")
        course = Course.objects.create(owner=cls.teacher, title="RAB12 Kurs", status="published")
        exam = Exam.objects.create(
            author=cls.teacher, title="RAB12 Imtahan", exam_type="written", is_active=True, is_public=True
        )
        ExamAttempt.objects.create(user=cls.student, exam=exam, status="submitted")
        assignment = Assignment.objects.create(
            course=course, title="RAB12 Tapshiriq", start_date=now - timedelta(days=1), status="published"
        )
        Submission.objects.create(assignment=assignment, user=cls.student, content="a", status="submitted")
        project = Project.objects.create(
            course=course,
            title="RAB12 Layihe",
            start_date=now - timedelta(days=1),
            deadline=now + timedelta(days=3),
            status="active",
        )
        ProjectSubmission.objects.create(project=project, student=cls.student, content="p", status="pending")
        lab = Lab.objects.create(
            course=course,
            title="RAB12 Lab",
            start_datetime=now - timedelta(days=1),
            end_datetime=now + timedelta(days=2),
            status="published",
            created_by=cls.teacher,
        )
        LabSubmission.objects.create(
            assignment=LabAssignment.objects.create(lab=lab, student=cls.student),
            submission_text="l",
            status="submitted",
        )

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _titles(self, items):
        return {item["title"] for item in items}


class SelfworkHiddenByDefaultTest(_CourseWorld):
    """Defolt (bayraqlar SÖNDÜRÜLÜ) — tapşırıq və layihə sətirləri, tabları və badge-ləri yoxdur."""

    def test_my_results_rows_counts_and_tabs(self):
        response = self._client(self.student).get(reverse("accounts:my_results"))
        self.assertEqual(response.status_code, 200)
        titles = self._titles(response.context["items"])
        self.assertIn("RAB12 Lab", titles)
        self.assertNotIn("RAB12 Tapshiriq", titles)
        self.assertNotIn("RAB12 Layihe", titles)
        self.assertEqual(response.context["counts"]["courses"], 0)
        self.assertEqual(response.context["counts"]["independent"], 0)
        self.assertNotContains(response, "?type=courses")
        self.assertNotContains(response, "?type=independent")
        self.assertContains(response, "?type=labs")

    def test_hidden_tab_in_url_falls_back_to_all(self):
        response = self._client(self.student).get(reverse("accounts:my_results") + "?type=courses")
        self.assertEqual(response.context["active_filter"], "all")
        self.assertNotIn("RAB12 Tapshiriq", self._titles(response.context["items"]))

    def test_pending_answers_keeps_exam_and_lab_only(self):
        response = self._client(self.student).get(reverse("accounts:profile") + "?section=pending-answers")
        self.assertEqual(response.status_code, 200)
        titles = self._titles(response.context["pending_answer_items"])
        self.assertEqual(titles, {"RAB12 Imtahan", "RAB12 Lab"})
        counts = response.context["pending_answer_counts"]
        self.assertEqual((counts["courses"], counts["independent"], counts["all"]), (0, 0, 2))
        self.assertNotContains(response, 'value="courses"')
        self.assertNotContains(response, 'value="independent"')

    def test_pending_review_keeps_exam_and_lab_only(self):
        response = self._client(self.teacher).get(reverse("accounts:pending_review") + "?type=assignments")
        self.assertEqual(response.status_code, 200)
        types = {item["type"] for item in response.context["review_items"]}
        self.assertEqual(types, {"exam", "lab"})
        self.assertNotContains(response, 'value="assignments"')
        self.assertNotContains(response, 'value="projects"')

    def test_assigned_exams_hides_selfwork_and_coursework_tabs(self):
        """2026-10-14: «Mənə təyin edilmiş tapşırıqlar» — sətirlər süzülürdü, «0»-lı tablar qalırdı."""
        client = self._client(self.student)
        response = client.get(reverse("accounts:profile") + "?section=assigned-exams")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "assigned_type=assignments")
        self.assertNotContains(response, "assigned_type=independent")
        self.assertContains(response, "assigned_type=labs")
        # Köhnə link: gizli tab «hamısı»na düşür (URL səhifədə əks olunduğu üçün HTML yox, kontekst yoxlanır).
        stale = client.get(reverse("accounts:profile") + "?section=assigned-exams&assigned_type=assignments")
        self.assertEqual(stale.context["assigned_tasks_active_filter"], "all")

    def test_badge_counters_skip_hidden_kinds(self):
        from apps.accounts.views._dashboard_helpers.cheap_counts import compute_review_badge_counts
        from apps.courses.models import Course
        from apps.exams.models import Exam

        pending, _evaluated = compute_review_badge_counts(
            my_exams_qs=Exam.objects.filter(author=self.teacher),
            teacher_courses=Course.objects.filter(owner=self.teacher),
        )
        self.assertEqual(pending, 2)  # imtahan + lab


@override_settings(**FLAGS_ON)
class SelfworkShownWhenEnabledTest(_CourseWorld):
    """RİM bayrağı yandırılanda köhnə görünüş TAM geri gəlir (kod saxlanılıb)."""

    def test_my_results_shows_everything(self):
        response = self._client(self.student).get(reverse("accounts:my_results"))
        titles = self._titles(response.context["items"])
        self.assertTrue({"RAB12 Tapshiriq", "RAB12 Layihe", "RAB12 Lab"} <= titles)
        self.assertContains(response, "?type=courses")
        self.assertContains(response, "?type=independent")

    def test_assigned_exams_shows_all_tabs(self):
        response = self._client(self.student).get(reverse("accounts:profile") + "?section=assigned-exams")
        self.assertContains(response, "assigned_type=assignments")
        self.assertContains(response, "assigned_type=independent")

    def test_pending_review_shows_everything(self):
        response = self._client(self.teacher).get(reverse("accounts:pending_review"))
        types = {item["type"] for item in response.context["review_items"]}
        self.assertEqual(types, {"exam", "assignment", "project", "lab"})


class UnitExamsLinkageTest(TestCase):
    """B19 — dekanın `unit-exams` siyahısı imtahanın ÖZ bağlantısı + müəllifin ƏSAS üzvlüyü ilə."""

    @classmethod
    def setUpTestData(cls):
        from apps.exams.models import Exam
        from apps.registrar.models import Subject

        owner = User.objects.create_user("rab19_owner", "rab19_o@x.test", "pw")
        cls.org = Organization.objects.create(
            name="RAB19", slug="rab19", org_type=OrganizationType.UNIVERSITY, owner=owner, status="active"
        )
        unit = lambda name, kind, parent=None: OrgUnit.objects.create(  # noqa: E731
            organization=cls.org, name=name, slug=f"rab19-{name}", unit_type=kind, parent=parent
        )
        fac1, fac2 = unit("f1", OrgUnitType.FACULTY), unit("f2", OrgUnitType.FACULTY)
        chair1, chair2 = unit("c1", OrgUnitType.CHAIR, fac1), unit("c2", OrgUnitType.CHAIR, fac2)
        teacher_role = Role.objects.create(
            organization=cls.org,
            name="rab19_teacher",
            display_name="T",
            level=40,
            permissions=["exam.create"],
            scope_type=RoleScopeType.UNIT,
        )
        dean_role = Role.objects.create(
            organization=cls.org,
            name="rab19_dean",
            display_name="D",
            level=75,
            permissions=["exam.view"],
            scope_type=RoleScopeType.UNIT,
        )
        cls.dean = User.objects.create_user("rab19_dean", "rab19_d@x.test", "pw")
        Membership.objects.create(
            organization=cls.org, user=cls.dean, role=dean_role, scope_unit=fac1, is_active=True, is_primary=True
        )

        def teacher(username, *memberships):
            user = User.objects.create_user(username, f"{username}@x.test", "pw")
            for scope_unit, primary in memberships:
                Membership.objects.create(
                    organization=cls.org,
                    user=user,
                    role=teacher_role,
                    scope_unit=scope_unit,
                    is_active=True,
                    is_primary=primary,
                )
            return user

        home = teacher("rab19_home", (chair1, True))
        outsider = teacher("rab19_out", (chair2, True), (chair1, False))  # Forma 1 «əlavə» üzvlük
        legacy = teacher("rab19_legacy", (chair1, False))  # əsas işarəsi olmayan köhnə hesab
        subj1 = Subject.objects.create(organization=cls.org, code="RAB19-1", name="F1 fənni", chair_unit=chair1)
        subj2 = Subject.objects.create(organization=cls.org, code="RAB19-2", name="F2 fənni", chair_unit=chair2)

        def exam(title, author, subject=None):
            return Exam.objects.create(organization=cls.org, author=author, title=title, subject=subject)

        exam("home-unlinked", home)
        exam("legacy-unlinked", legacy)
        exam("outsider-own-subject-in-f1", outsider, subj1)
        exam("outsider-unlinked", outsider)
        exam("outsider-f2-subject", outsider, subj2)
        exam("home-f2-subject", home, subj2)

    def _titles(self):
        from apps.accounts.views.profile._sections.unit_exams import build_unit_exams_context

        request = RequestFactory().get("/accounts/profile/", {"section": "unit-exams"})
        request.user = self.dean
        request.organization = self.org
        context = build_unit_exams_context(request, allowed_sections={"unit-exams"}, active_section="unit-exams")
        return {exam.title for exam in context["unit_exams_page_obj"].object_list}

    def test_extra_membership_does_not_leak_other_faculty_exams(self):
        self.assertEqual(
            self._titles(),
            {"home-unlinked", "legacy-unlinked", "outsider-own-subject-in-f1"},
        )
