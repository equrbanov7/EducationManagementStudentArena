"""
View tests for blog app.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.blog.models import Post

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

        self.teacher_post = Post.objects.create(
            author=self.teacher,
            title="Teacher Post",
            content="Teacher content",
            is_published=True,
        )

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
