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
