"""
View tests for blog app.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.blog.models import Category, Post
from apps.exams.models import StudentGroup
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType

User = get_user_model()


def _assign_user_to_org(user, organization, profile_role, *, membership_role_name=None):
    membership_role_name = membership_role_name or {
        ProfileRole.TEACHER: "instructor" if organization.org_type == OrganizationType.COURSE_CENTER else "teacher",
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


class BlogRoleAccessTest(TestCase):
    def _activate_org(self, user):
        self.client.force_login(user)
        session = self.client.session
        session["active_organization"] = self.organization.slug
        session.save()

    def setUp(self):
        self.teacher = User.objects.create_user(
            username="blog_teacher",
            email="blog_teacher@example.com",
            password="StrongPass123!",
        )
        self.student = User.objects.create_user(
            username="blog_student",
            email="blog_student@example.com",
            password="StrongPass123!",
        )

        self.organization = Organization.objects.create(
            name="Blog Approval Org",
            slug="blog-approval-org",
            org_type=OrganizationType.COURSE_CENTER,
            owner=self.teacher,
        )
        _assign_user_to_org(self.teacher, self.organization, ProfileRole.TEACHER)
        _assign_user_to_org(self.student, self.organization, ProfileRole.STUDENT)

        self.other_teacher = User.objects.create_user(
            username="blog_other_teacher",
            email="blog_other_teacher@example.com",
            password="StrongPass123!",
        )
        _assign_user_to_org(self.other_teacher, self.organization, ProfileRole.TEACHER)

        self.teacher_post = Post.objects.create(
            author=self.teacher,
            title="Teacher Post",
            content="Teacher content",
            is_published=True,
        )
        self.student_group = StudentGroup.objects.create(
            teacher=self.teacher,
            organization=self.organization,
            name="Qrup 101",
        )
        self.student_group.students.add(self.student)

    def test_homepage_is_available_at_root(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "blog/home.html")

    def test_legacy_blog_home_redirects_to_root(self):
        response = self.client.get("/blog/?q=Teacher&page=2")

        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.url, "/?q=Teacher&page=2")

    def test_student_can_open_create_post_page(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("create_post"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="new_category"')

    def test_student_cannot_edit_other_users_post(self):
        self.client.force_login(self.student)
        response = self.client.post(
            reverse("post_edit_ajax", args=[self.teacher_post.id]),
            {
                "title": "Updated",
                "content": "Updated content",
                "excerpt": "",
                "category": "",
                "image_url": "",
            },
        )
        self.assertEqual(response.status_code, 404)

    def test_teacher_can_open_create_post_page(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("create_post"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="new_category"')

    def test_student_cannot_create_new_category_when_submitting_post(self):
        self.client.force_login(self.student)
        response = self.client.post(
            reverse("create_post"),
            {
                "title": "Student Category Attempt",
                "content": "Student content",
                "excerpt": "",
                "category": "",
                "new_category": "Unauthorized Student Category",
                "image_url": "",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(Category.objects.filter(name="Unauthorized Student Category").exists())
        self.assertIn("Yeni kateqoriya yaratmaq", response.json()["errors"]["new_category"][0])

    def test_teacher_can_create_new_category_when_submitting_post(self):
        self.client.force_login(self.teacher)
        response = self.client.post(
            reverse("create_post"),
            {
                "title": "Teacher Category Post",
                "content": "Teacher content",
                "excerpt": "",
                "category": "",
                "new_category": "Teacher Created Category",
                "image_url": "",
                "is_published": "on",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        created_post = Post.objects.get(author=self.teacher, title="Teacher Category Post")
        self.assertEqual(created_post.category.name, "Teacher Created Category")
        self.assertTrue(Category.objects.filter(name="Teacher Created Category").exists())

    def test_author_can_delete_own_post_via_ajax(self):
        self.client.force_login(self.teacher)
        response = self.client.post(
            reverse("delete_post", args=[self.teacher_post.id]),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertIn("Teacher Post", payload["message"])
        self.assertFalse(Post.objects.filter(id=self.teacher_post.id).exists())

    def test_other_user_cannot_delete_post(self):
        self.client.force_login(self.student)
        response = self.client.post(
            reverse("delete_post", args=[self.teacher_post.id]),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Post.objects.filter(id=self.teacher_post.id).exists())

    def test_author_delete_post_non_ajax_redirects_to_new_profile(self):
        self.client.force_login(self.teacher)
        response = self.client.post(
            reverse("delete_post", args=[self.teacher_post.id]),
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, f"{reverse('accounts:profile')}?section=posts")

    def test_legacy_user_profile_redirects_own_username_to_accounts_profile(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("user_profile", args=[self.teacher.username]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("accounts:profile"))

    def test_legacy_user_profile_redirects_other_username_to_accounts_public_profile(self):
        self.client.force_login(self.teacher)
        response = self.client.get(reverse("user_profile", args=[self.student.username]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("accounts:public_profile", args=[self.student.username]))

    def test_article_detail_renders_back_link_with_public_profile_fallback(self):
        response = self.client.get(reverse("article_detail", args=[self.teacher_post.slug]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Geri qayıt")
        self.assertContains(response, reverse("accounts:public_profile", args=[self.teacher.username]))
        self.assertContains(response, "window.history.back()")

    def test_legacy_blog_article_detail_redirects_to_article_route(self):
        response = self.client.get(f"/blog/posts/{self.teacher_post.slug}/")

        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.url, reverse("article_detail", args=[self.teacher_post.slug]))

    def test_author_can_create_post_via_ajax(self):
        self.client.force_login(self.teacher)
        response = self.client.post(
            reverse("create_post"),
            {
                "title": "Ajax Created Post",
                "content": "Ajax content",
                "excerpt": "Ajax excerpt",
                "category": "",
                "new_category": "",
                "image_url": "",
                "is_published": "on",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '"success": true')
        self.assertTrue(Post.objects.filter(author=self.teacher, title="Ajax Created Post").exists())

    def test_legacy_blog_create_post_ajax_endpoint_still_works(self):
        self.client.force_login(self.teacher)
        response = self.client.post(
            "/blog/posts/create/",
            {
                "title": "Legacy Ajax Created Post",
                "content": "Legacy ajax content",
                "excerpt": "Legacy ajax excerpt",
                "category": "",
                "new_category": "",
                "image_url": "",
                "is_published": "on",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '"success": true')
        self.assertTrue(Post.objects.filter(author=self.teacher, title="Legacy Ajax Created Post").exists())

    def test_student_created_post_stays_pending_until_approval(self):
        self.client.force_login(self.student)
        response = self.client.post(
            reverse("create_post"),
            {
                "title": "Student Pending Post",
                "content": "Student content",
                "excerpt": "",
                "category": "",
                "new_category": "",
                "image_url": "",
                "is_published": "on",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        created_post = Post.objects.get(author=self.student, title="Student Pending Post")
        self.assertTrue(created_post.requires_approval)
        self.assertEqual(created_post.approval_status, Post.ApprovalStatus.PENDING)
        self.assertFalse(created_post.is_published)

    def test_group_teacher_can_approve_student_post(self):
        pending_post = Post.objects.create(
            author=self.student,
            title="Approval Candidate",
            content="Needs teacher approval",
            requires_approval=True,
            approval_status=Post.ApprovalStatus.PENDING,
            is_published=False,
        )

        self.client.force_login(self.teacher)
        response = self.client.post(
            reverse("review_post", args=[pending_post.id]),
            {
                "action": "approve",
                "feedback": "Yaxşı hazırlanıb.",
            },
        )
        self.assertEqual(response.status_code, 302)

        pending_post.refresh_from_db()
        self.assertTrue(pending_post.is_published)
        self.assertEqual(pending_post.approval_status, Post.ApprovalStatus.APPROVED)
        self.assertEqual(pending_post.approved_by, self.teacher)
        self.assertEqual(pending_post.approval_feedback, "Yaxşı hazırlanıb.")

    def test_teacher_outside_group_cannot_approve_student_post(self):
        pending_post = Post.objects.create(
            author=self.student,
            title="Blocked Candidate",
            content="Only assigned teacher can approve",
            requires_approval=True,
            approval_status=Post.ApprovalStatus.PENDING,
            is_published=False,
        )

        self.client.force_login(self.other_teacher)
        response = self.client.post(
            reverse("review_post", args=[pending_post.id]),
            {"action": "approve"},
        )
        self.assertEqual(response.status_code, 403)
        pending_post.refresh_from_db()
        self.assertEqual(pending_post.approval_status, Post.ApprovalStatus.PENDING)
        self.assertFalse(pending_post.is_published)

    def test_reviewer_can_open_pending_article_detail(self):
        pending_post = Post.objects.create(
            author=self.student,
            title="Pending Detail Access",
            content="Teacher should still review this post",
            requires_approval=True,
            approval_status=Post.ApprovalStatus.PENDING,
            is_published=False,
        )

        self.client.force_login(self.teacher)
        response = self.client.get(reverse("article_detail", args=[pending_post.slug]))
        self.assertEqual(response.status_code, 200)

    def test_pending_post_approvals_section_shows_show_more_toggle_for_long_content(self):
        pending_post = Post.objects.create(
            author=self.student,
            title="Long Approval Content",
            content="Uzun content " * 80,
            requires_approval=True,
            approval_status=Post.ApprovalStatus.PENDING,
            is_published=False,
        )

        self._activate_org(self.teacher)
        response = self.client.get(reverse("accounts:profile") + "?section=pending-post-approvals")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, pending_post.title)
        self.assertContains(response, "Show more")
        self.assertContains(response, "data-pending-post-toggle")
        self.assertContains(response, "data-pending-post-full")
