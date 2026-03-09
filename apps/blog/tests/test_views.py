"""
View tests for blog app.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.blog.models import Post
from apps.exams.models import StudentGroup
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class BlogRoleAccessTest(TestCase):
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

        teacher_profile = self.teacher.profile
        teacher_profile.role = ProfileRole.TEACHER
        teacher_profile.save(update_fields=["role", "updated_at"])

        student_profile = self.student.profile
        student_profile.role = ProfileRole.STUDENT
        student_profile.save(update_fields=["role", "updated_at"])

        self.organization = Organization.objects.create(
            name="Blog Approval Org",
            slug="blog-approval-org",
            org_type=OrganizationType.COURSE_CENTER,
            owner=self.teacher,
        )

        teacher_profile.organization = self.organization
        teacher_profile.organization_type = self.organization.org_type
        teacher_profile.save(update_fields=["organization", "organization_type", "updated_at"])

        student_profile.organization = self.organization
        student_profile.organization_type = self.organization.org_type
        student_profile.save(update_fields=["organization", "organization_type", "updated_at"])

        self.other_teacher = User.objects.create_user(
            username="blog_other_teacher",
            email="blog_other_teacher@example.com",
            password="StrongPass123!",
        )
        other_teacher_profile = self.other_teacher.profile
        other_teacher_profile.role = ProfileRole.TEACHER
        other_teacher_profile.organization = self.organization
        other_teacher_profile.organization_type = self.organization.org_type
        other_teacher_profile.save(
            update_fields=["role", "organization", "organization_type", "updated_at"]
        )

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

    def test_student_can_open_create_post_page(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse("create_post"))
        self.assertEqual(response.status_code, 200)

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

    def test_post_detail_renders_back_link_with_public_profile_fallback(self):
        response = self.client.get(reverse("post_detail", args=[self.teacher_post.slug]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Geri qayıt")
        self.assertContains(response, reverse("accounts:public_profile", args=[self.teacher.username]))
        self.assertContains(response, "window.history.back()")

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

    def test_reviewer_can_open_pending_post_detail(self):
        pending_post = Post.objects.create(
            author=self.student,
            title="Pending Detail Access",
            content="Teacher should still review this post",
            requires_approval=True,
            approval_status=Post.ApprovalStatus.PENDING,
            is_published=False,
        )

        self.client.force_login(self.teacher)
        response = self.client.get(reverse("post_detail", args=[pending_post.slug]))
        self.assertEqual(response.status_code, 200)
