"""Tests for post management features."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole, UserProfile
from apps.blog.models import Category, Post
from apps.blog.services import author_requires_post_approval, can_user_publish_post
from apps.notifications.models import InAppNotification
from apps.organizations.models import Membership, Organization, Role
from core.constants import OrganizationType, RoleScopeType

User = get_user_model()


def _create_org_with_roles(owner, name="Test Org"):
    """Helper to create org with standard roles.

    Organization.post_save signal auto-creates default roles, so we use
    get_or_create to avoid IntegrityError on duplicates.
    """
    org = Organization.objects.create(
        name=name,
        slug=name.lower().replace(" ", "-"),
        org_type=OrganizationType.UNIVERSITY,
        owner=owner,
        status="active",
    )
    admin_role, _ = Role.objects.get_or_create(
        organization=org,
        name="org_admin",
        defaults={
            "display_name": "Admin",
            "level": 80,
            "scope_type": RoleScopeType.ORGANIZATION,
            "is_system": True,
        },
    )
    teacher_role, _ = Role.objects.get_or_create(
        organization=org,
        name="teacher",
        defaults={
            "display_name": "Teacher",
            "level": 60,
            "scope_type": RoleScopeType.ORGANIZATION,
            "is_system": True,
        },
    )
    student_role, _ = Role.objects.get_or_create(
        organization=org,
        name="student",
        defaults={
            "display_name": "Student",
            "level": 10,
            "scope_type": RoleScopeType.ORGANIZATION,
            "is_system": True,
        },
    )
    staff_role, _ = Role.objects.get_or_create(
        organization=org,
        name="staff",
        defaults={
            "display_name": "Staff",
            "level": 50,
            "scope_type": RoleScopeType.ORGANIZATION,
            "is_system": True,
        },
    )
    return org, admin_role, teacher_role, student_role, staff_role


class UnapprovedMemberCannotPublishTest(TestCase):
    """Task 2: Users with inactive/unapproved membership cannot publish."""

    def setUp(self):
        self.superadmin = User.objects.create_superuser("superadmin", "sa@test.com", "pass1234")
        self.owner = User.objects.create_user("owner", "owner@test.com", "pass1234")
        UserProfile.objects.update_or_create(user=self.owner, defaults={"role": ProfileRole.ORG_OWNER})

        self.org, self.admin_role, self.teacher_role, self.student_role, _ = _create_org_with_roles(self.owner)

        # Teacher with INACTIVE membership (not yet approved)
        self.unapproved_teacher = User.objects.create_user("teacher_pending", "tp@test.com", "pass1234")
        UserProfile.objects.update_or_create(user=self.unapproved_teacher, defaults={"role": ProfileRole.TEACHER})
        Membership.objects.create(
            user=self.unapproved_teacher,
            organization=self.org,
            role=self.teacher_role,
            is_active=False,
        )

        # Student with INACTIVE membership
        self.unapproved_student = User.objects.create_user("student_pending", "sp@test.com", "pass1234")
        UserProfile.objects.update_or_create(user=self.unapproved_student, defaults={"role": ProfileRole.STUDENT})
        Membership.objects.create(
            user=self.unapproved_student,
            organization=self.org,
            role=self.student_role,
            is_active=False,
        )

        # Approved teacher
        self.approved_teacher = User.objects.create_user("teacher_ok", "tok@test.com", "pass1234")
        UserProfile.objects.update_or_create(user=self.approved_teacher, defaults={"role": ProfileRole.TEACHER})
        Membership.objects.create(
            user=self.approved_teacher,
            organization=self.org,
            role=self.teacher_role,
            is_active=True,
        )

        self.category = Category.objects.create(name="Test", slug="test")

    def test_unapproved_teacher_cannot_publish(self):
        can_publish, reason = can_user_publish_post(self.unapproved_teacher)
        self.assertFalse(can_publish)
        self.assertIn("təsdiqlənməyib", reason)

    def test_unapproved_student_cannot_publish(self):
        can_publish, reason = can_user_publish_post(self.unapproved_student)
        self.assertFalse(can_publish)

    def test_approved_teacher_can_publish(self):
        can_publish, reason = can_user_publish_post(self.approved_teacher)
        self.assertTrue(can_publish)

    def test_superadmin_can_always_publish(self):
        can_publish, reason = can_user_publish_post(self.superadmin)
        self.assertTrue(can_publish)

    def test_unapproved_teacher_create_post_rejected(self):
        self.client.login(username="teacher_pending", password="pass1234")
        resp = self.client.post(
            reverse("create_post"),
            {"title": "Test", "content": "Content", "category": self.category.pk},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 403)


class NoOrgUserSuperadminReviewTest(TestCase):
    """Task 2: Users without any org go to superadmin review."""

    def setUp(self):
        self.user_no_org = User.objects.create_user("lonely", "lonely@test.com", "pass1234")
        UserProfile.objects.update_or_create(user=self.user_no_org, defaults={"role": ProfileRole.STUDENT})

    def test_no_org_user_requires_approval(self):
        self.assertTrue(author_requires_post_approval(self.user_no_org))

    def test_no_org_user_can_publish(self):
        """User can submit but it goes to review queue."""
        can_publish, reason = can_user_publish_post(self.user_no_org)
        self.assertTrue(can_publish)


class PostDeletionTest(TestCase):
    """Task 3: Post deletion works correctly."""

    def setUp(self):
        self.user = User.objects.create_user("author1", "author@test.com", "pass1234")
        UserProfile.objects.update_or_create(user=self.user, defaults={"role": ProfileRole.TEACHER})
        self.category = Category.objects.create(name="Cat", slug="cat")
        self.post = Post.objects.create(
            title="To Delete",
            content="Content",
            author=self.user,
            category=self.category,
            is_published=True,
            slug="to-delete",
        )

    def test_author_can_delete_own_post(self):
        self.client.login(username="author1", password="pass1234")
        resp = self.client.post(
            reverse("delete_post", args=[self.post.pk]),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertFalse(Post.objects.filter(pk=self.post.pk).exists())

    def test_other_user_cannot_delete(self):
        other = User.objects.create_user("other", "other@test.com", "pass1234")
        UserProfile.objects.update_or_create(user=other, defaults={"role": ProfileRole.TEACHER})
        self.client.login(username="other", password="pass1234")
        resp = self.client.post(
            reverse("delete_post", args=[self.post.pk]),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 404)
        self.assertTrue(Post.objects.filter(pk=self.post.pk).exists())


class SuperadminPostManagementTest(TestCase):
    """Task 4: Superadmin can filter and delete posts with reason."""

    def setUp(self):
        self.superadmin = User.objects.create_superuser("sa", "sa@test.com", "pass1234")
        self.author = User.objects.create_user("author2", "a2@test.com", "pass1234")
        UserProfile.objects.update_or_create(user=self.author, defaults={"role": ProfileRole.TEACHER})
        self.category = Category.objects.create(name="C", slug="c")
        self.post = Post.objects.create(
            title="SA Managed",
            content="Content",
            author=self.author,
            category=self.category,
            is_published=True,
            slug="sa-managed",
        )

    def test_superadmin_can_view_page(self):
        self.client.login(username="sa", password="pass1234")
        resp = self.client.get(reverse("accounts:superadmin_post_management"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "SA Managed")

    def test_non_superadmin_denied(self):
        self.client.login(username="author2", password="pass1234")
        resp = self.client.get(reverse("accounts:superadmin_post_management"))
        self.assertEqual(resp.status_code, 403)

    def test_superadmin_delete_requires_reason(self):
        self.client.login(username="sa", password="pass1234")
        resp = self.client.post(
            reverse("accounts:superadmin_delete_post", args=[self.post.pk]),
            {"reason": ""},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertTrue(Post.objects.filter(pk=self.post.pk).exists())

    def test_superadmin_delete_with_reason(self):
        self.client.login(username="sa", password="pass1234")
        resp = self.client.post(
            reverse("accounts:superadmin_delete_post", args=[self.post.pk]),
            {"reason": "Violates policy"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Post.objects.filter(pk=self.post.pk).exists())

    def test_superadmin_delete_notifies_author(self):
        self.client.login(username="sa", password="pass1234")
        self.client.post(
            reverse("accounts:superadmin_delete_post", args=[self.post.pk]),
            {"reason": "Test reason"},
        )
        notif = InAppNotification.objects.filter(recipient=self.author).first()
        self.assertIsNotNone(notif)
        self.assertIn("superadmin", notif.title.lower())
        self.assertIn("Test reason", notif.message)

    def test_search_filter(self):
        self.client.login(username="sa", password="pass1234")
        resp = self.client.get(reverse("accounts:superadmin_post_management"), {"q": "SA Managed"})
        self.assertContains(resp, "SA Managed")
        resp2 = self.client.get(
            reverse("accounts:superadmin_post_management"),
            {"q": "nonexistent xyz"},
        )
        self.assertNotContains(resp2, "SA Managed")

    def test_status_filter(self):
        self.client.login(username="sa", password="pass1234")
        resp = self.client.get(reverse("accounts:superadmin_post_management"), {"status": "published"})
        self.assertContains(resp, "SA Managed")
        resp2 = self.client.get(reverse("accounts:superadmin_post_management"), {"status": "draft"})
        self.assertNotContains(resp2, "SA Managed")


class OrgAdminPostManagementTest(TestCase):
    """Task 5: Org owner/admin can access and moderate organization posts."""

    def setUp(self):
        self.owner = User.objects.create_user("orgowner", "oo@test.com", "pass1234")
        UserProfile.objects.update_or_create(user=self.owner, defaults={"role": ProfileRole.ORG_OWNER})
        self.org, self.admin_role, self.teacher_role, self.student_role, _ = _create_org_with_roles(self.owner)

        # Owner membership
        Membership.objects.create(
            user=self.owner,
            organization=self.org,
            role=self.admin_role,
            is_active=True,
        )

        # Teacher in org
        self.teacher = User.objects.create_user("orgteacher", "ot@test.com", "pass1234")
        UserProfile.objects.update_or_create(user=self.teacher, defaults={"role": ProfileRole.TEACHER})
        Membership.objects.create(
            user=self.teacher,
            organization=self.org,
            role=self.teacher_role,
            is_active=True,
        )

        self.category = Category.objects.create(name="OC", slug="oc")
        self.post = Post.objects.create(
            title="Org Post",
            content="Content",
            author=self.teacher,
            category=self.category,
            is_published=True,
            slug="org-post",
        )

    def test_org_admin_can_view_page(self):
        self.client.login(username="orgowner", password="pass1234")
        resp = self.client.get(reverse("accounts:org_post_management"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Org Post")

    def test_regular_user_denied(self):
        regular = User.objects.create_user("regular", "r@test.com", "pass1234")
        UserProfile.objects.update_or_create(user=regular, defaults={"role": ProfileRole.STUDENT})
        self.client.login(username="regular", password="pass1234")
        resp = self.client.get(reverse("accounts:org_post_management"))
        self.assertEqual(resp.status_code, 403)

    def test_org_admin_delete_post(self):
        self.client.login(username="orgowner", password="pass1234")
        resp = self.client.post(
            reverse("accounts:org_moderate_post", args=[self.post.pk]),
            {"action": "delete", "feedback": "Inappropriate"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Post.objects.filter(pk=self.post.pk).exists())

    def test_org_admin_request_changes(self):
        self.client.login(username="orgowner", password="pass1234")
        resp = self.client.post(
            reverse("accounts:org_moderate_post", args=[self.post.pk]),
            {"action": "request_changes", "feedback": "Please fix typos"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 200)
        self.post.refresh_from_db()
        self.assertEqual(self.post.approval_status, "needs_changes")
        self.assertFalse(self.post.is_published)

    def test_org_admin_delete_notifies_author(self):
        self.client.login(username="orgowner", password="pass1234")
        self.client.post(
            reverse("accounts:org_moderate_post", args=[self.post.pk]),
            {"action": "delete", "feedback": "Policy violation"},
        )
        notif = InAppNotification.objects.filter(recipient=self.teacher).first()
        self.assertIsNotNone(notif)
        self.assertIn("Policy violation", notif.message)

    def test_delete_requires_feedback(self):
        self.client.login(username="orgowner", password="pass1234")
        resp = self.client.post(
            reverse("accounts:org_moderate_post", args=[self.post.pk]),
            {"action": "delete", "feedback": ""},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 400)
        self.assertTrue(Post.objects.filter(pk=self.post.pk).exists())


class MyResultsPaginationSearchTest(TestCase):
    """Task 7: Pagination and search on student My Results page."""

    def setUp(self):
        self.student = User.objects.create_user("student1", "s1@test.com", "pass1234")
        UserProfile.objects.update_or_create(user=self.student, defaults={"role": ProfileRole.STUDENT})

    def test_my_results_page_loads(self):
        self.client.login(username="student1", password="pass1234")
        resp = self.client.get(reverse("accounts:my_results"))
        self.assertEqual(resp.status_code, 200)

    def test_my_results_with_search_param(self):
        self.client.login(username="student1", password="pass1234")
        resp = self.client.get(reverse("accounts:my_results"), {"q": "test search"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("search_query", resp.context)
        self.assertEqual(resp.context["search_query"], "test search")

    def test_my_results_with_type_filter(self):
        self.client.login(username="student1", password="pass1234")
        resp = self.client.get(reverse("accounts:my_results"), {"type": "exams"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context["active_filter"], "exams")

    def test_my_results_has_pagination(self):
        self.client.login(username="student1", password="pass1234")
        resp = self.client.get(reverse("accounts:my_results"))
        self.assertIn("page_obj", resp.context)
