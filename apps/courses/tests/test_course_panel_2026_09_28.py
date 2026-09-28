"""Kurs paneli redizaynı (2026-09-28) — yeni davranışların qoruyucu testləri.

* «Tələbə əlavə et» seçicisi tələbəni TƏŞKİLAT ÜZVLÜYÜNÜN rolundan tanıyır
  (real bazada `profile.role` hamı üçün «member»-dir — seçici heç kimi tapmırdı);
* «AI ilə kurs qur» plan endpoint-i heç nə yazmır, apply yalnız təsdiqlənəni yazır;
* qrupu kursdan çıxarma AJAX JSON qaytarır və yalnız tələbə üzvlüklərini silir;
* kurs paneli tabları serverdə render olunur, redaktə modalı səhifədədir.
"""

from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.courses.models import Course, CourseMembership, CourseResource, CourseTopic
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType

User = get_user_model()
AJAX = {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}


class _PanelBase(TestCase):
    def setUp(self):
        self.teacher = User.objects.create_user("cp_teacher", "cp_teacher@example.com", "pw")
        self.org = Organization.objects.create(
            name="CP Org",
            slug="cp-org",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        self._join(self.teacher, ProfileRole.TEACHER, "teacher")
        self.course = Course.objects.create(owner=self.teacher, title="CP Course", organization=self.org)
        self.client.force_login(self.teacher)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()

    def _join(self, user, profile_role, role_name):
        profile = user.profile
        profile.organization = self.org
        profile.organization_type = self.org.org_type
        profile.role = profile_role
        profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])
        Membership.objects.update_or_create(
            user=user,
            organization=self.org,
            defaults={"role": self.org.roles.get(name=role_name), "is_primary": True, "is_active": True},
        )


class AvailableStudentsMembershipRoleTest(_PanelBase):
    def test_student_found_by_org_membership_role_even_if_profile_role_is_member(self):
        student = User.objects.create_user("cp_member_student", "cp_ms@example.com", "pw", first_name="Aysel")
        self._join(student, "member", "student")
        other_teacher = User.objects.create_user("cp_other_teacher", "cp_ot@example.com", "pw")
        self._join(other_teacher, "member", "teacher")

        url = reverse("courses:available_students", kwargs={"course_id": self.course.id})
        ids = {row["id"] for row in self.client.get(url).json()["users"]}
        self.assertIn(student.id, ids)
        self.assertNotIn(other_teacher.id, ids)


class CourseAIViewsTest(_PanelBase):
    PLAN = {
        "topics": [
            {
                "title": "Həftə 1: Giriş",
                "description": "Kursa baxış",
                "resources": [
                    {"title": "Python docs", "url": "https://docs.python.org/3/"},
                    {"title": "Pis link", "url": "javascript:alert(1)"},
                ],
            },
            {"title": "", "description": "başlıqsız — atılmalıdır"},
        ]
    }

    def test_plan_does_not_write_and_normalises_payload(self):
        with mock.patch("apps.exams.public.generate_ai_json", return_value={"ok": True, "payload": self.PLAN}):
            response = self.client.post(
                reverse("courses:ai_plan", kwargs={"course_id": self.course.id}),
                data={"prompt": "Python başlanğıc"},
                content_type="application/json",
                **AJAX,
            )
        self.assertEqual(response.status_code, 200, response.content)
        plan = response.json()["plan"]
        self.assertEqual(len(plan["topics"]), 1)
        self.assertEqual([r["url"] for r in plan["topics"][0]["resources"]], ["https://docs.python.org/3/"])
        self.assertFalse(CourseTopic.objects.filter(course=self.course).exists())

    def test_plan_generation_failure_uses_course_message(self):
        failure = {"ok": False, "code": "generation_failed", "error": "AI xülasəsi yaradıla bilmədi"}
        with mock.patch("apps.exams.public.generate_ai_json", return_value=failure):
            response = self.client.post(
                reverse("courses:ai_plan", kwargs={"course_id": self.course.id}),
                data={"prompt": "x"},
                content_type="application/json",
                **AJAX,
            )
        self.assertEqual(response.status_code, 502)
        self.assertNotIn("xülasə", response.json()["error"])

    def test_apply_creates_topics_and_link_resources_atomically(self):
        response = self.client.post(
            reverse("courses:ai_apply", kwargs={"course_id": self.course.id}),
            data={"plan": self.PLAN},
            content_type="application/json",
            **AJAX,
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["created"], {"topics": 1, "resources": 1})
        topic = CourseTopic.objects.get(course=self.course)
        self.assertEqual(topic.order, 1)
        resource = CourseResource.objects.get(course=self.course)
        self.assertEqual((resource.topic_id, resource.resource_type), (topic.id, "link"))

    def test_non_owner_cannot_use_ai(self):
        stranger = User.objects.create_user("cp_stranger", "cp_s@example.com", "pw")
        self._join(stranger, ProfileRole.TEACHER, "teacher")
        self.client.force_login(stranger)
        response = self.client.post(
            reverse("courses:ai_apply", kwargs={"course_id": self.course.id}),
            data={"plan": self.PLAN},
            content_type="application/json",
            **AJAX,
        )
        self.assertIn(response.status_code, (403, 404))
        self.assertFalse(CourseTopic.objects.filter(course=self.course).exists())


class RemoveGroupAjaxTest(_PanelBase):
    def test_removes_only_student_memberships_of_that_group(self):
        s1 = User.objects.create_user("cp_s1", "cp_s1@example.com", "pw")
        s2 = User.objects.create_user("cp_s2", "cp_s2@example.com", "pw")
        CourseMembership.objects.create(course=self.course, user=s1, role="student", group_name="G-1")
        CourseMembership.objects.create(course=self.course, user=s2, role="student", group_name="G-2")
        response = self.client.post(
            reverse("courses:delete_group_from_course", kwargs={"course_id": self.course.id}),
            {"group_name": "G-1"},
            **AJAX,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["deleted_count"], 1)
        self.assertEqual(
            list(CourseMembership.objects.filter(course=self.course).values_list("group_name", flat=True)),
            ["G-2"],
        )


class DashboardShellTest(_PanelBase):
    def test_tabs_are_server_rendered_with_counts_and_edit_modal(self):
        CourseTopic.objects.create(course=self.course, title="T1", order=1)
        response = self.client.get(reverse("courses:course_dashboard", kwargs={"course_id": self.course.id}))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        for key in ("topics", "assignments", "labs", "exams", "projects", "resources", "members"):
            self.assertIn(f'data-cd-tab="{key}"', html)
        self.assertIn('id="editCourseModal"', html)
        self.assertIn('id="editCourseForm"', html)
        self.assertNotIn("\\u002D", html)

    def test_student_sees_no_members_tab_or_owner_controls(self):
        student = User.objects.create_user("cp_student", "cp_st@example.com", "pw")
        self._join(student, ProfileRole.STUDENT, "student")
        self.course.status = "published"
        self.course.save(update_fields=["status"])
        CourseMembership.objects.create(course=self.course, user=student, role="student")
        self.client.force_login(student)
        html = self.client.get(
            reverse("courses:course_dashboard", kwargs={"course_id": self.course.id})
        ).content.decode()
        self.assertNotIn('data-cd-tab="members"', html)
        self.assertNotIn('id="editCourseModal"', html)
        self.assertNotIn("data-delete-course-id", html)


class AddMemberStudentsOnlyTest(_PanelBase):
    """Audit 2026-09-28 T-03: add_member müəllimi «tələbə» kimi qəbul etmir."""

    def test_teacher_id_is_ignored(self):
        colleague = User.objects.create_user("cp_colleague", "cp_col@example.com", "pw")
        self._join(colleague, "member", "teacher")
        student = User.objects.create_user("cp_real_student", "cp_rs@example.com", "pw")
        self._join(student, "member", "student")
        self.client.post(
            reverse("courses:add_member", kwargs={"course_id": self.course.id}),
            {"user_ids": [str(colleague.id), str(student.id)]},
        )
        self.assertEqual(
            list(CourseMembership.objects.filter(course=self.course).values_list("user_id", flat=True)),
            [student.id],
        )


class AuditGuardsTest(_PanelBase):
    """Audit 2026-09-28 DB-04 / DB-05 qoruyucuları."""

    def test_too_many_group_ids_are_rejected(self):
        response = self.client.post(
            reverse("courses:add_members_bulk", kwargs={"course_id": self.course.id}),
            {"group_ids": [f"00000000-0000-0000-0000-{i:012d}" for i in range(21)]},
        )
        self.assertEqual(response.status_code, 400)

    # Test ayarlarında DummyCache-dir (``add`` həmişə True) — kilid real cache istəyir.
    @override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
    def test_parallel_ai_plan_request_is_refused(self):
        from django.core.cache import cache

        cache.add(f"courses:ai-plan:inflight:{self.teacher.id}", 1, timeout=60)
        try:
            with mock.patch("apps.exams.public.generate_ai_json") as generate:
                response = self.client.post(
                    reverse("courses:ai_plan", kwargs={"course_id": self.course.id}),
                    data={"prompt": "x"},
                    content_type="application/json",
                    **AJAX,
                )
            self.assertEqual(response.status_code, 429)
            generate.assert_not_called()
        finally:
            cache.delete(f"courses:ai-plan:inflight:{self.teacher.id}")
