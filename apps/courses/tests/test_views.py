"""
View tests for courses app.
"""

import tempfile
from datetime import timedelta
from urllib.parse import quote

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import override, pgettext

from apps.accounts.models import ProfileRole
from apps.assignments.models import Assignment
from apps.courses.models import Course, CourseMembership, CourseResource, CourseTopic
from apps.exams.models import Exam
from apps.labs.models import Lab
from apps.organizations.models import Membership, Organization
from apps.projects.models import Project
from core.constants import OrganizationType

User = get_user_model()


def _assign_user_to_org(user, organization, profile_role, *, membership_role_name=None):
    membership_role_name = membership_role_name or {
        ProfileRole.TEACHER: "teacher",
        ProfileRole.STUDENT: "student",
    }.get(profile_role, "member")

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


class CourseOwnershipTenantFilteringTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            username="course_owner",
            email="course_owner@example.com",
            password="StrongPass123!",
        )
        self.student = User.objects.create_user(
            username="course_student",
            email="course_student@example.com",
            password="StrongPass123!",
        )
        self.other_teacher = User.objects.create_user(
            username="course_other_teacher",
            email="course_other_teacher@example.com",
            password="StrongPass123!",
        )
        self.external_student = User.objects.create_user(
            username="course_external_student",
            email="course_external_student@example.com",
            password="StrongPass123!",
        )

        self.org_a = Organization.objects.create(
            name="Course Org A",
            org_type=OrganizationType.SCHOOL,
            owner=self.owner,
            status="active",
            is_active=True,
        )
        self.org_b = Organization.objects.create(
            name="Course Org B",
            org_type=OrganizationType.UNIVERSITY,
            owner=self.owner,
            status="active",
            is_active=True,
        )

        _assign_user_to_org(self.owner, self.org_a, ProfileRole.TEACHER)
        _assign_user_to_org(self.student, self.org_a, ProfileRole.STUDENT)
        _assign_user_to_org(self.other_teacher, self.org_a, ProfileRole.TEACHER)
        _assign_user_to_org(self.external_student, self.org_b, ProfileRole.STUDENT)

        self.course_a = Course.objects.create(
            owner=self.owner,
            title="Tenant A Course",
            status="published",
            organization=self.org_a,
        )
        self.course_b = Course.objects.create(
            owner=self.owner,
            title="Tenant B Course",
            status="published",
            organization=self.org_b,
        )
        self.course_exam = Exam.objects.create(
            author=self.owner,
            course=self.course_a,
            title="Tenant A Course Exam",
            is_active=True,
        )
        now = timezone.now()
        self.assignment = Assignment.objects.create(
            course=self.course_a,
            title="Tenant A Assignment",
            start_date=now - timedelta(days=1),
            due_date=now + timedelta(days=7),
            status="published",
            created_by=self.owner,
        )
        self.project = Project.objects.create(
            course=self.course_a,
            title="Tenant A Project",
            start_date=now - timedelta(days=1),
            deadline=now + timedelta(days=7),
            status="active",
        )
        self.lab = Lab.objects.create(
            course=self.course_a,
            title="Tenant A Lab",
            start_datetime=now - timedelta(days=1),
            end_datetime=now + timedelta(days=7),
            status="published",
            created_by=self.owner,
        )

        CourseMembership.objects.create(course=self.course_a, user=self.student, role="student")
        CourseMembership.objects.create(course=self.course_b, user=self.student, role="student")

        self.client.force_login(self.owner)
        session = self.client.session
        session["active_organization"] = self.org_a.slug
        session.save()

    def test_my_courses_only_shows_owner_courses_in_active_tenant(self):
        response = self.client.get(reverse("courses:my_courses"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.course_a.title)
        self.assertNotContains(response, self.course_b.title)

    def test_student_courses_only_shows_assigned_courses_in_active_tenant(self):
        self.client.force_login(self.student)
        session = self.client.session
        session["active_organization"] = self.org_a.slug
        session.save()

        response = self.client.get(reverse("courses:student_courses"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.course_a.title)
        self.assertNotContains(response, self.course_b.title)

    def test_my_courses_shows_no_data_without_active_organization(self):
        from apps.courses.views import MyCoursesListView

        request = RequestFactory().get(reverse("courses:my_courses"))
        request.user = self.owner
        request.organization = None
        request.org_memberships = []
        request.org_permissions = []
        response = MyCoursesListView.as_view()(request)
        response.render()

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context_data["courses"].exists())

    def test_my_courses_requires_login(self):
        self.client.logout()

        response = self.client.get(reverse("courses:my_courses"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

    def test_course_dashboard_preserves_assigned_tasks_profile_return_context(self):
        self.client.force_login(self.student)
        session = self.client.session
        session["active_organization"] = self.org_a.slug
        session.save()

        response = self.client.get(
            reverse("courses:course_dashboard", kwargs={"course_id": self.course_a.id}),
            {"from_section": "assigned-exams", "assigned_type": "labs"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["profile_return_section"], "assigned-exams")
        self.assertEqual(
            response.context["profile_return_url"],
            f"{reverse('accounts:profile')}?section=assigned-exams&assigned_type=labs",
        )

    def test_course_dashboard_prefers_explicit_return_to_url(self):
        self.client.force_login(self.student)
        session = self.client.session
        session["active_organization"] = self.org_a.slug
        session.save()

        return_to = f"{reverse('accounts:profile')}?section=courses"
        response = self.client.get(
            reverse("courses:course_dashboard", kwargs={"course_id": self.course_a.id}),
            {"from_section": "assigned-courses", "return_to": return_to},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["profile_return_url"], return_to)

    def test_course_dashboard_renders_develop_style_visibility_panel(self):
        response = self.client.get(
            reverse("courses:course_dashboard", kwargs={"course_id": self.course_a.id}),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "courseVisibilityAccordion")
        self.assertContains(response, "course-status-toggle")
        self.assertContains(response, "course-status-switch-form")
        self.assertContains(response, "Kursun yayımı")
        self.assertContains(response, "Yayımlandı")

    def test_course_dashboard_uses_unified_view_answers_label_and_resource_title(self):
        expected_answer_labels = {
            "az": "Cavabları gör",
            "en": "View answers",
            "ru": "Посмотреть ответы",
            "tr": "Cevapları gör",
        }
        expected_resource_titles = {
            "az": "Resurslar",
            "en": "Resources",
            "ru": "Ресурсы",
            "tr": "Kaynaklar",
        }

        for language_code, expected_label in expected_answer_labels.items():
            with override(language_code):
                self.assertEqual(pgettext("assignment.section", "review_answers"), expected_label)
                self.assertEqual(pgettext("labs.template.lab_section", "action_answers"), expected_label)
                self.assertEqual(pgettext("exams.partial.exam_section", "action_results"), expected_label)
                self.assertEqual(pgettext("projects.section", "view_submissions"), expected_label)
                self.assertEqual(
                    pgettext("courses.partial.resource_accordion", "Resources"),
                    expected_resource_titles[language_code],
                )

        response = self.client.get(
            reverse("courses:course_dashboard", kwargs={"course_id": self.course_a.id}),
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Resurslar (")

    def test_course_dashboard_renders_exam_modal_triggers_and_shared_confirm_modal(self):
        response = self.client.get(
            reverse("courses:course_dashboard", kwargs={"course_id": self.course_a.id}),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "courseActionConfirmModal")
        self.assertContains(response, "courseExamEditorModal")
        self.assertContains(response, "js-open-course-exam-editor")
        self.assertContains(response, reverse("exams:edit_exam", args=[self.course_exam.slug]))
        self.assertContains(response, "Detallı imtahana bax")

    def test_course_dashboard_renders_assignment_and_project_modals_for_org_owner(self):
        owner = User.objects.create_user(
            username="org_owner_modal",
            email="org_owner_modal@example.com",
            password="StrongPass123!",
        )
        organization = Organization.objects.create(
            name="Org Owner Modal Org",
            org_type=OrganizationType.SCHOOL,
            owner=owner,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(
            owner,
            organization,
            ProfileRole.ORG_OWNER,
        )
        course = Course.objects.create(
            owner=owner,
            title="Org Owner Modal Course",
            status="published",
            organization=organization,
        )

        self.client.force_login(owner)
        session = self.client.session
        session["active_organization"] = organization.slug
        session.save()

        response = self.client.get(
            reverse("courses:course_dashboard", kwargs={"course_id": course.id}),
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-bs-target="#addAssignmentModal"')
        self.assertContains(response, 'id="addAssignmentModal"')
        self.assertContains(response, 'data-bs-target="#addProjectModal"')
        self.assertContains(response, 'id="addProjectModal"')

    def test_course_dashboard_exam_links_return_back_to_current_dashboard_path(self):
        self.client.force_login(self.owner)
        session = self.client.session
        session["active_organization"] = self.org_a.slug
        session.save()

        response = self.client.get(
            reverse("courses:course_dashboard", kwargs={"course_id": self.course_a.id}),
            {"from_section": "my-courses", "return_to": f"{reverse('accounts:profile')}?section=my-courses"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response, f'{reverse("exams:teacher_exam_detail", args=[self.course_exam.slug])}?from_section=my-courses'
        )
        self.assertContains(
            response, f'{reverse("exams:teacher_exam_results", args=[self.course_exam.slug])}?from_section=my-courses'
        )
        expected_return_to = quote(response.wsgi_request.get_full_path(), safe="/")
        self.assertContains(response, f"return_to={expected_return_to}")

    def test_course_dashboard_ignores_referer_when_no_explicit_return_to_is_provided(self):
        self.client.force_login(self.student)
        session = self.client.session
        session["active_organization"] = self.org_a.slug
        session.save()

        response = self.client.get(
            reverse("courses:course_dashboard", kwargs={"course_id": self.course_a.id}),
            HTTP_REFERER="/assignments/5/my-submissions/",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["profile_return_url"],
            f"{reverse('accounts:profile')}?section=assigned-courses",
        )

    def test_owner_can_update_course_status_from_dashboard(self):
        self.client.force_login(self.owner)
        session = self.client.session
        session["active_organization"] = self.org_a.slug
        session.save()

        self.course_a.status = "draft"
        self.course_a.save(update_fields=["status"])

        next_url = (
            f"{reverse('courses:course_dashboard', kwargs={'course_id': self.course_a.id})}?from_section=my-courses"
        )
        response = self.client.post(
            reverse("courses:update_course_status", kwargs={"course_id": self.course_a.id}),
            {"status": "published", "next": next_url},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, next_url)
        self.course_a.refresh_from_db()
        self.assertEqual(self.course_a.status, "published")

    def test_delete_course_redirects_to_new_profile_page(self):
        self.client.force_login(self.owner)
        session = self.client.session
        session["active_organization"] = self.org_a.slug
        session.save()

        response = self.client.post(
            reverse("courses:delete_course", kwargs={"course_id": self.course_a.id}),
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, f"{reverse('accounts:profile')}?section=my-courses")
        self.assertFalse(Course.objects.filter(id=self.course_a.id).exists())

    def test_edit_course_requires_login(self):
        self.client.logout()

        response = self.client.get(reverse("courses:edit_course", kwargs={"course_id": self.course_a.id}))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

    def test_create_course_requires_login(self):
        self.client.logout()

        response = self.client.get(reverse("courses:create_course"))

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("accounts:login"), response.url)

    def test_edit_course_clears_missing_cover_image_reference(self):
        edit_url = reverse("courses:edit_course", kwargs={"course_id": self.course_a.id})

        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                self.course_a.cover_image.save(
                    "cover.png",
                    SimpleUploadedFile("cover.png", b"fake-image-bytes", content_type="image/png"),
                    save=True,
                )
                missing_name = self.course_a.cover_image.name
                self.course_a.cover_image.storage.delete(missing_name)

                response = self.client.get(edit_url)
                self.assertEqual(response.status_code, 200)
                self.assertNotContains(response, missing_name)

                response = self.client.post(
                    edit_url,
                    {
                        "title": "Tenant A Course Updated",
                        "description": self.course_a.description,
                        "status": self.course_a.status,
                    },
                )

        self.assertEqual(response.status_code, 302)
        self.course_a.refresh_from_db()
        self.assertEqual(self.course_a.title, "Tenant A Course Updated")
        self.assertFalse(self.course_a.cover_image)

    def test_non_owner_teacher_gets_403_on_course_edit(self):
        self.client.force_login(self.other_teacher)
        session = self.client.session
        session["active_organization"] = self.org_a.slug
        session.save()

        response = self.client.get(reverse("courses:edit_course", kwargs={"course_id": self.course_a.id}))
        self.assertEqual(response.status_code, 403)

    def test_non_owner_teacher_cannot_add_or_remove_course_member(self):
        self.client.force_login(self.other_teacher)
        session = self.client.session
        session["active_organization"] = self.org_a.slug
        session.save()

        add_response = self.client.post(
            reverse("courses:add_member", kwargs={"course_id": self.course_a.id}),
            {"user_ids": [str(self.student.id)], "group_name": "A1"},
        )
        self.assertEqual(add_response.status_code, 403)

        member = CourseMembership.objects.get(course=self.course_a, user=self.student)
        delete_response = self.client.post(
            reverse("courses:delete_member", kwargs={"course_id": self.course_a.id, "member_id": member.id}),
        )
        self.assertEqual(delete_response.status_code, 403)
        self.assertTrue(CourseMembership.objects.filter(id=member.id).exists())

    def test_owner_cannot_add_cross_tenant_student(self):
        self.client.force_login(self.owner)
        session = self.client.session
        session["active_organization"] = self.org_a.slug
        session.save()

        response = self.client.post(
            reverse("courses:add_member", kwargs={"course_id": self.course_a.id}),
            {"user_ids": [str(self.external_student.id)], "group_name": "A2"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CourseMembership.objects.filter(course=self.course_a, user=self.external_student).exists())

    def test_owner_can_add_topic_ajax_and_dashboard_renders_it(self):
        response = self.client.post(
            reverse("courses:add_topic", kwargs={"course_id": self.course_a.id}),
            {
                "title": "Visible AJAX Topic",
                "description": "This topic must appear on the dashboard after reload.",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])

        topic = CourseTopic.objects.get(course=self.course_a, title="Visible AJAX Topic")
        self.assertEqual(topic.order, 1)

        dashboard = self.client.get(reverse("courses:course_dashboard", kwargs={"course_id": self.course_a.id}))
        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, "Visible AJAX Topic")
        self.assertContains(dashboard, f'id="topic-{topic.id}"')

    def test_owner_can_add_resource_to_topic_ajax_and_topic_panel_renders_it(self):
        topic = CourseTopic.objects.create(
            course=self.course_a,
            title="Resource Parent Topic",
            description="",
            order=1,
        )

        response = self.client.post(
            reverse("courses:add_resource", kwargs={"course_id": self.course_a.id}),
            {
                "title": "Topic Bound Resource",
                "description": "Resource attached to the selected topic.",
                "resource_type": "link",
                "url": "https://example.com/topic-resource",
                "topic": str(topic.id),
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])

        resource = CourseResource.objects.get(course=self.course_a, title="Topic Bound Resource")
        self.assertEqual(resource.topic, topic)

        dashboard = self.client.get(reverse("courses:course_dashboard", kwargs={"course_id": self.course_a.id}))
        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, "Resource Parent Topic")
        self.assertContains(dashboard, "Topic Bound Resource")

    def test_course_dashboard_wires_topic_resource_and_member_controls(self):
        topic = CourseTopic.objects.create(
            course=self.course_a,
            title="Wired Topic",
            description="",
            order=1,
        )
        CourseResource.objects.create(
            course=self.course_a,
            topic=topic,
            title="Wired Resource",
            resource_type="link",
            url="https://example.com/wired-resource",
        )

        response = self.client.get(reverse("courses:course_dashboard", kwargs={"course_id": self.course_a.id}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-delete-course-id="')
        self.assertContains(response, 'data-edit-topic-id="')
        self.assertContains(response, 'data-delete-topic-id="')
        self.assertContains(response, 'data-open-resource-modal-topic-id="')
        self.assertContains(response, 'data-delete-resource-id="')
        # shown.bs.modal wiring now lives in the external topic-edit-modal script
        # (CSP: no inline JS) rather than inline in the response — assert the
        # script that wires the topic edit modal is present on the page.
        self.assertContains(response, "courses/js/topic_edit_modal.js")
        self.assertContains(response, 'id="sidebar-members-count"')
        # The '.snav-item[data-key="members"] .snav-count' selector now lives in
        # the external member-accordion script (CSP: no inline JS) — assert that
        # script is wired on the page instead of the literal selector text.
        self.assertContains(response, "courses/js/member_accordion.js")


class StudentUserQuerysetRoleSourceTests(TestCase):
    def test_auth_groups_do_not_make_member_users_visible_as_students(self):
        from apps.courses.views.shared._helpers import _student_users_queryset

        real_student = User.objects.create_user(
            username="course_helper_student",
            email="course_helper_student@example.com",
            password="StrongPass123!",
        )
        member_user = User.objects.create_user(
            username="course_helper_member",
            email="course_helper_member@example.com",
            password="StrongPass123!",
        )

        real_student.profile.role = ProfileRole.STUDENT
        real_student.profile.save(update_fields=["role", "updated_at"])
        member_user.profile.role = ProfileRole.MEMBER
        member_user.profile.save(update_fields=["role", "updated_at"])

        student_group = Group.objects.create(name=ProfileRole.STUDENT)
        member_user.groups.add(student_group)

        result_ids = set(_student_users_queryset(User.objects.order_by("id")).values_list("id", flat=True))

        self.assertIn(real_student.id, result_ids)
        self.assertNotIn(member_user.id, result_ids)


# ════════════════════════════════════════════════════════════════════════════
# Tenant Isolation: Null Organization Edge-Case Tests
# ════════════════════════════════════════════════════════════════════════════


class CourseOrganizationRequiredTest(TestCase):
    """
    Tenant isolation: Course cannot be created or updated without an
    organization. These tests cover the null-organization edge cases.
    """

    def setUp(self):
        pass

        self.teacher = User.objects.create_user(
            username="org_req_teacher",
            email="org_req_teacher@example.com",
            password="StrongPass123!",
        )
        self.org = Organization.objects.create(
            name="OrgRequired Test Org",
            org_type=OrganizationType.SCHOOL,
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        _assign_user_to_org(self.teacher, self.org, ProfileRole.TEACHER)

    def test_course_model_raises_validation_error_without_organization(self):
        """Course.save() raises ValidationError when organization cannot be resolved."""
        from django.core.exceptions import ValidationError

        # Create a user with NO organization profile
        orphan_teacher = User.objects.create_user(
            username="orphan_teacher",
            email="orphan_teacher@example.com",
            password="StrongPass123!",
        )

        with self.assertRaises(ValidationError):
            Course.objects.create(
                owner=orphan_teacher,
                title="Orphan Course",
                status="draft",
                # organization intentionally omitted and profile has no org
            )

    def test_course_model_auto_assigns_organization_from_owner_profile(self):
        """Course.save() auto-assigns organization from owner profile when not set explicitly."""
        course = Course.objects.create(
            owner=self.teacher,
            title="Auto Org Course",
            status="draft",
            # organization intentionally omitted
        )
        self.assertEqual(course.organization, self.org)

    def test_create_course_view_raises_403_without_active_organization(self):
        """CreateCourseView form_valid raises PermissionDenied when request has no organization."""
        from django.core.exceptions import PermissionDenied

        from apps.courses.views import CreateCourseView

        # Simulate a request with organization=None (no active org)
        request = RequestFactory().post(
            reverse("courses:create_course"),
            {"title": "No Org Course", "description": "Should not be saved"},
        )
        request.user = self.teacher
        request.organization = None
        request.org_memberships = []
        request.org_permissions = ["course.create"]

        view = CreateCourseView()
        view.request = request
        view.args = []
        view.kwargs = {}
        view.object = None

        from apps.courses.forms import CourseForm

        form = CourseForm({"title": "No Org Course", "description": "Should not be saved"})
        form.instance.owner = self.teacher

        with self.assertRaises(PermissionDenied):
            view.form_valid(form)

        self.assertFalse(Course.objects.filter(title="No Org Course").exists())

    def test_superadmin_can_create_course_from_profile_org_when_session_org_missing(self):
        superadmin = User.objects.create_user(
            username="course_superadmin_restore",
            email="course_superadmin_restore@example.com",
            password="StrongPass123!",
        )
        profile = superadmin.profile
        profile.organization = self.org
        profile.organization_type = self.org.org_type
        profile.role = ProfileRole.SUPERADMIN
        profile.save(update_fields=["organization", "organization_type", "role", "updated_at"])

        self.client.force_login(superadmin)
        session = self.client.session
        session.pop("active_organization", None)
        session.save()

        response = self.client.post(
            reverse("courses:create_course") + "?modal=1",
            {
                "title": "Superadmin Restored Course",
                "description": "Created after restoring org context from profile.",
                "status": "published",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)

        created_course = Course.objects.get(title="Superadmin Restored Course")
        self.assertJSONEqual(
            response.content,
            {
                "success": True,
                "course_id": created_course.id,
                "dashboard_url": reverse("courses:course_dashboard", args=[created_course.id]),
            },
        )
        self.assertEqual(created_course.organization, self.org)
        self.assertEqual(created_course.owner, superadmin)
        self.assertEqual(self.client.session.get("active_organization"), self.org.slug)

    def test_superadmin_without_profile_org_can_choose_organization_in_create_course_modal(self):
        superadmin = User.objects.create_superuser(
            username="course_superadmin_modal",
            email="course_superadmin_modal@example.com",
            password="StrongPass123!",
        )

        self.client.force_login(superadmin)
        session = self.client.session
        session.pop("active_organization", None)
        session.save()

        modal_response = self.client.get(
            reverse("courses:create_course") + "?modal=1",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(modal_response.status_code, 200)
        self.assertContains(modal_response, 'name="organization"', html=False)
        self.assertContains(modal_response, self.org.name)

        response = self.client.post(
            reverse("courses:create_course") + "?modal=1",
            {
                "organization": str(self.org.pk),
                "title": "Superadmin Selected Org Course",
                "description": "Created by explicit organization selection.",
                "status": "published",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)

        created_course = Course.objects.get(title="Superadmin Selected Org Course")
        self.assertJSONEqual(
            response.content,
            {
                "success": True,
                "course_id": created_course.id,
                "dashboard_url": reverse("courses:course_dashboard", args=[created_course.id]),
            },
        )
        self.assertEqual(created_course.organization, self.org)
        self.assertEqual(created_course.owner, superadmin)
        self.assertEqual(self.client.session.get("active_organization"), self.org.slug)

    def test_course_with_explicit_organization_is_created_successfully(self):
        """Course explicitly bound to an organization is created without errors."""
        course = Course.objects.create(
            owner=self.teacher,
            title="Explicitly Bound Course",
            status="draft",
            organization=self.org,
        )
        self.assertEqual(course.organization, self.org)
        self.assertIsNotNone(course.pk)
