"""Paket E (2026-10-17) — kurs paneli bölmələri / dialoqları / üzvlər səhifəsi.

* kurs paneli kursu və üzvlüyü ikinci dəfə oxumur (`get_context_data` → `self.object`);
* panelin sorğu sayı lab/imtahan sayından asılı deyil (müəllim görünüşü);
* bölmələr Bootstrap akkordeon/list-group deyil, `cd-task` kartlarıdır; «əlavə et» düymələri panel başlığındadır;
* mövzu/resurs/üzv/redaktə dialoqları `ems-bsd` markup-ıdır (JS-in ID/qarmaqları saxlanılıb);
* üzvlər səhifəsi `ems_ui` başlığı + boş vəziyyət ilə render olunur.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.courses.models import Course, CourseMembership
from apps.exams.models import Exam
from apps.labs.models import Lab
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType

User = get_user_model()


def _join(user, org, profile_role, role_name):
    profile = user.profile
    profile.organization = org
    profile.organization_type = org.org_type
    profile.role = profile_role
    profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])
    Membership.objects.update_or_create(
        user=user,
        organization=org,
        defaults={"role": org.roles.get(name=role_name), "is_primary": True, "is_active": True},
    )


class CoursePanelPkgETests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("pkge_c_owner", "pkge_c_owner@example.com", "pw")
        self.org = Organization.objects.create(
            name="PkgE Org",
            slug="pkge-org",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.owner,
            status="active",
            is_active=True,
        )
        _join(self.owner, self.org, ProfileRole.TEACHER, "teacher")
        self.course = Course.objects.create(
            owner=self.owner, title="PkgE Course", organization=self.org, status="published"
        )
        self.url = reverse("courses:course_dashboard", kwargs={"course_id": self.course.id})
        self.client.force_login(self.owner)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()

    def _lab(self, index):
        now = timezone.now()
        return Lab.objects.create(
            course=self.course,
            title=f"Lab {index}",
            start_datetime=now - timedelta(hours=1),
            end_datetime=now + timedelta(days=3),
            status="published",
            created_by=self.owner,
        )

    def test_dashboard_fetches_course_and_membership_once(self):
        self.client.get(self.url)
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        course_reads = [q for q in ctx.captured_queries if 'FROM "courses_course"' in q["sql"] and "WHERE" in q["sql"]]
        membership_reads = [
            q
            for q in ctx.captured_queries
            if 'FROM "courses_coursemembership"' in q["sql"] and '"user_id"' in q["sql"] and "LIMIT 1" in q["sql"]
        ]
        self.assertEqual(len(course_reads), 1, [q["sql"][:120] for q in course_reads])
        self.assertLessEqual(len(membership_reads), 1)

    def test_teacher_dashboard_query_count_independent_of_lab_and_exam_count(self):
        self._lab(0)
        self.client.get(self.url)
        with CaptureQueriesContext(connection) as small:
            self.client.get(self.url)
        for index in range(1, 7):
            self._lab(index)
            Exam.objects.create(author=self.owner, course=self.course, title=f"E{index}", is_active=True)
        with CaptureQueriesContext(connection) as large:
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(small.captured_queries), len(large.captured_queries))

    def test_sections_are_task_cards_with_header_actions(self):
        self._lab(1)
        Exam.objects.create(author=self.owner, course=self.course, title="E1", is_active=True)
        html = self.client.get(self.url).content.decode("utf-8")
        self.assertIn("cd-task", html)
        self.assertNotIn("accordion-item", html)
        self.assertNotIn("list-group-item", html)
        self.assertIn('data-ems-overlay-open="addLabModal"', html)
        self.assertIn('data-ems-overlay-open="linkExamModal"', html)
        # Tapşırıq/layihə «əlavə et» düymələri də panel başlığındadır (bölmə partial-ında yox).
        self.assertIn('data-bs-target="#addAssignmentModal"', html)
        self.assertIn('data-bs-target="#addProjectModal"', html)
        self.assertIn('id="addLabModal"', html)
        self.assertIn('id="linkExamModal"', html)
        # JS qarmaqları dəyişməyib.
        for hook in ("js-edit-lab", "js-delete-lab", "js-open-course-exam-editor", "js-unlink-exam"):
            self.assertIn(hook, html)

    def test_course_dialogs_keep_js_hooks_and_use_static_markup(self):
        html = self.client.get(self.url).content.decode("utf-8")
        for needle in (
            'id="topicForm"',
            'id="topicErrors"',
            'id="topicEditForm"',
            'id="resourceForm"',
            'name="resource_type"',
            'id="editCourseForm"',
            'id="addStudentForm"',
            'id="addGroupForm"',
        ):
            self.assertIn(needle, html)
        self.assertGreaterEqual(html.count("ems-bsd__head"), 5)  # mövzu ×2, resurs, redaktə, üzv ×2 (altı)

    def test_empty_course_sections_show_empty_states_with_actions(self):
        html = self.client.get(self.url).content.decode("utf-8")
        self.assertIn("cd-empty", html)
        self.assertIn("cd-empty__ic--labs", html)
        self.assertIn("cd-empty__ic--exams", html)


class CourseMembersPageTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("pkge_m_owner", "pkge_m_owner@example.com", "pw")
        self.org = Organization.objects.create(
            name="PkgE M Org",
            slug="pkge-m-org",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.owner,
            status="active",
            is_active=True,
        )
        _join(self.owner, self.org, ProfileRole.TEACHER, "teacher")
        self.course = Course.objects.create(owner=self.owner, title="Members Course", organization=self.org)
        self.client.force_login(self.owner)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()
        self.url = reverse("courses:course_members", kwargs={"course_id": self.course.id})

    def test_empty_state_has_actions_and_no_horizontal_table(self):
        html = self.client.get(self.url).content.decode("utf-8")
        self.assertIn("ems-header", html)
        self.assertIn("ems-state", html)
        self.assertIn('data-bs-target="#addStudentModal"', html)
        self.assertNotIn("members-page-wrapper", html)

    def test_students_grouped_with_delete_hooks(self):
        student = User.objects.create_user("pkge_m_st", "pkge_m_st@example.com", "pw", first_name="Aysel")
        _join(student, self.org, ProfileRole.STUDENT, "student")
        membership = CourseMembership.objects.create(course=self.course, user=student, role="student", group_name="G1")
        html = self.client.get(self.url).content.decode("utf-8")
        self.assertIn("Aysel", html)
        self.assertIn(f'data-delete-member-id="{membership.id}"', html)
        self.assertIn("data-confirm-message", html)
