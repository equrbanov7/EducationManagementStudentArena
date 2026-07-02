"""
Profile and dashboard permission tests.

Extracted from test_views.py to keep individual test modules focused.
Covers:
* Basic profile access control (authentication required)
* Dashboard access by role
* Role-level ordering
* Public profile page behaviour
"""

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.models import ProfileRole
from apps.blog.models import Category, Post

User = get_user_model()


def _ensure_default_blog_categories():
    """Sqlite sürətli dövrə (--no-migrations) üçün blog seed kateqoriyalarını təmin et.

    CI migrasiyaları işlədir və 0002_seed_default_categories bunları onsuz da
    yaradır — orada get_or_create no-op olur. Yerli --no-migrations rejimində
    isə bu testlərin arxalandığı "Technology"/"Programming" ağacı yaranır.
    """
    from apps.blog.models import Category

    technology, _ = Category.objects.get_or_create(
        slug="technology",
        defaults={"name": "Technology", "sort_order": 10, "show_in_navbar": True, "is_default": True},
    )
    Category.objects.get_or_create(
        slug="programming",
        defaults={"name": "Programming", "parent": technology, "sort_order": 10, "is_default": True},
    )
    return technology


class ProfileAccessTest(TestCase):
    """Test profile view access control."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user("profileuser", "profile@example.com", "StrongPass123!")
        self.profile_url = reverse("accounts:profile")

    def test_profile_requires_authentication(self):
        """Test that profile page requires login."""
        response = self.client.get(self.profile_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_profile_accessible_when_logged_in(self):
        """Test that profile page is accessible when logged in."""
        self.client.login(username="profileuser", password="StrongPass123!")
        response = self.client.get(self.profile_url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("profile", response.context)

    def test_profile_shows_user_information(self):
        """Test that profile shows user information."""
        self.client.login(username="profileuser", password="StrongPass123!")
        response = self.client.get(self.profile_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.user.username)


class DashboardViewTest(TestCase):
    """Test dashboard view functionality."""

    def setUp(self):
        self.client = Client()
        self.teacher = User.objects.create_user("teacher", "teacher@example.com", "StrongPass123!")
        self.student = User.objects.create_user("student", "student@example.com", "StrongPass123!")

        self.teacher.profile.role = ProfileRole.TEACHER
        self.teacher.profile.save(update_fields=["role", "updated_at"])

        self.student.profile.role = ProfileRole.STUDENT
        self.student.profile.save(update_fields=["role", "updated_at"])

        self.dashboard_url = reverse("accounts:dashboard")

    def test_dashboard_requires_authentication(self):
        """Test that dashboard requires login."""
        response = self.client.get(self.dashboard_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_teacher_dashboard_accessible(self):
        """Test that teacher can access dashboard."""
        self.client.login(username="teacher", password="StrongPass123!")
        response = self.client.get(self.dashboard_url)
        # Dashboard should be accessible
        self.assertIn(response.status_code, [200, 302])

    def test_student_dashboard_accessible(self):
        """Test that student can access dashboard."""
        self.client.login(username="student", password="StrongPass123!")
        response = self.client.get(self.dashboard_url)
        # Dashboard should be accessible
        self.assertIn(response.status_code, [200, 302])


class RoleBasedAccessTest(TestCase):
    """Test role-based access control."""

    def setUp(self):
        self.client = Client()
        self.superadmin = User.objects.create_user("superadmin", "superadmin@example.com", "StrongPass123!")
        self.teacher = User.objects.create_user("teacher", "teacher@example.com", "StrongPass123!")
        self.student = User.objects.create_user("student", "student@example.com", "StrongPass123!")

        self.superadmin.profile.role = ProfileRole.SUPERADMIN
        self.superadmin.profile.save(update_fields=["role", "updated_at"])

        self.teacher.profile.role = ProfileRole.TEACHER
        self.teacher.profile.save(update_fields=["role", "updated_at"])

        self.student.profile.role = ProfileRole.STUDENT
        self.student.profile.save(update_fields=["role", "updated_at"])

    def test_different_roles_have_different_levels(self):
        """Test that different roles have different access levels."""
        self.assertGreater(self.superadmin.profile.role_level, self.teacher.profile.role_level)
        self.assertGreater(self.teacher.profile.role_level, self.student.profile.role_level)

    def test_profile_url_accessible_for_all_roles(self):
        """Test that profile page is accessible for all authenticated users."""
        profile_url = reverse("accounts:profile")

        # Superadmin
        self.client.login(username="superadmin", password="StrongPass123!")
        response = self.client.get(profile_url)
        self.assertEqual(response.status_code, 200)
        self.client.logout()

        # Teacher
        self.client.login(username="teacher", password="StrongPass123!")
        response = self.client.get(profile_url)
        self.assertEqual(response.status_code, 200)
        self.client.logout()

        # Student
        self.client.login(username="student", password="StrongPass123!")
        response = self.client.get(profile_url)
        self.assertEqual(response.status_code, 200)


class PublicProfileViewTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.owner = User.objects.create_user("publicowner", "publicowner@example.com", "StrongPass123!")
        self.viewer = User.objects.create_user("publicviewer", "publicviewer@example.com", "StrongPass123!")
        self.reported_zap_usernames = (
            "wcu",
            "individual_teacher_1",
            "individual_teacher_2",
            "kelvin",
            "learnhub_coach",
            "learnhub_editor",
            "school_teacher_1",
            "school_teacher_2",
            "university_teacher_1",
            "university_teacher_2",
            "tmp_img_user3",
            "tmp_img_user4",
        )
        self.reported_zap_payloads = ("'", '"', ";", "'(", "ZAP%n%s%n%s", "ZAP%x%x%x%x")
        self.category = Category.objects.create(name="Frontend", slug="frontend")
        self.other_category = Category.objects.create(name="Backend", slug="backend")
        self.demo_category = Category.objects.create(name="Demo Xəbərlər", slug="demo-xeberler")

        owner_profile = self.owner.profile
        owner_profile.bio = "Açıq bio məlumatı"
        owner_profile.location = "Bakı"
        owner_profile.save(update_fields=["bio", "location", "updated_at"])

        Post.objects.create(
            author=self.owner,
            category=self.category,
            title="Public Post",
            excerpt="Visible excerpt",
            content="Visible content",
            is_published=True,
        )
        Post.objects.create(
            author=self.owner,
            category=self.category,
            title="Private Draft",
            excerpt="Hidden excerpt",
            content="Hidden content",
            is_published=False,
        )

        for index in range(7):
            Post.objects.create(
                author=self.owner,
                category=self.category,
                title=f"Pagination Post {index}",
                excerpt=f"Excerpt {index}",
                content=f"Content {index}",
                is_published=True,
            )

        Post.objects.create(
            author=self.owner,
            category=self.category,
            title="Alpha Search Match",
            excerpt="Searchable excerpt",
            content="Searchable content",
            is_published=True,
        )
        Post.objects.create(
            author=self.owner,
            category=self.other_category,
            title="Backend Public Post",
            excerpt="Backend excerpt",
            content="Backend content",
            is_published=True,
        )

        for username in self.reported_zap_usernames:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "email": f"{username}@example.com",
                },
            )
            if created:
                user.set_password("StrongPass123!")
                user.save(update_fields=["password"])
            user.profile.save(update_fields=["updated_at"])
            Post.objects.get_or_create(
                author=user,
                category=self.demo_category,
                title=f"{username} demo post",
                defaults={
                    "excerpt": "Visible excerpt",
                    "content": "Visible content",
                    "is_published": True,
                },
            )

    def test_public_profile_is_accessible_anonymously_and_hides_private_sections(self):
        response = self.client.get(reverse("accounts:public_profile", args=[self.owner.username]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alpha Search Match")
        self.assertNotContains(response, "Private Draft")
        self.assertContains(response, "Açıq bio məlumatı")
        self.assertContains(response, "Bakı")
        self.assertNotContains(response, reverse("create_post"))
        self.assertNotContains(response, reverse("courses:my_courses"))
        self.assertNotContains(response, reverse("courses:create_course"))
        self.assertNotContains(response, reverse("exams:create_exam"))
        self.assertNotContains(response, reverse("accounts:assigned_exams"))

    def test_public_profile_redirects_owner_to_private_profile(self):
        self.client.force_login(self.owner)

        response = self.client.get(reverse("accounts:public_profile", args=[self.owner.username]))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("accounts:profile"))

    def test_public_profile_hides_avatar_image_from_anonymous_visitors(self):
        tiny_png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0cIDATx\x9cc`\x00"
            b"\x00\x00\x02\x00\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        self.owner.profile.avatar = SimpleUploadedFile("avatar.png", tiny_png, content_type="image/png")
        self.owner.profile.save(update_fields=["avatar", "updated_at"])

        response = self.client.get(reverse("accounts:public_profile", args=[self.owner.username]))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(
            response,
            reverse("accounts:profile_avatar", kwargs={"user_id": self.owner.id}),
            html=False,
        )
        self.assertContains(response, "public-profile-avatar__fallback", html=False)

    def test_public_profile_search_and_pagination_work(self):
        search_response = self.client.get(
            reverse("accounts:public_profile", args=[self.owner.username]),
            {"q": "Alpha"},
        )
        self.assertEqual(search_response.status_code, 200)
        self.assertContains(search_response, "Alpha Search Match")
        self.assertNotContains(search_response, "Public Post")

        page_response = self.client.get(
            reverse("accounts:public_profile", args=[self.owner.username]),
            {"page": 2},
        )
        self.assertEqual(page_response.status_code, 200)
        self.assertEqual(page_response.context["posts"].number, 2)

    def test_public_profile_rejects_semicolon_only_search_with_empty_results(self):
        response = self.client.get(
            reverse("accounts:public_profile", args=[self.owner.username]),
            {"q": ";"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["search_query"], "")
        self.assertEqual(response.context["posts"].paginator.count, 0)

    def test_public_profile_malicious_query_params_return_empty_results(self):
        payloads = (
            {"q": "'("},
            {"q": '"'},
            {"q": "()"},
            {"category": ";"},
            {"category": "demo-xeberler", "q": "'("},
        )

        for params in payloads:
            with self.subTest(params=params):
                response = self.client.get(
                    reverse("accounts:public_profile", args=[self.owner.username]),
                    params,
                )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["posts"].paginator.count, 0)
                self.assertNotIn("%27", response.context["extra_query"])
                self.assertNotIn(";", response.context["extra_query"])

    def test_public_profile_rejects_non_numeric_page_payloads(self):
        for username in ("wcu", "school_teacher_1", "university_teacher_1", "tmp_img_user3"):
            for payload in ("'", '"', ";", "'("):
                with self.subTest(username=username, payload=payload):
                    response = self.client.get(
                        reverse("accounts:public_profile", args=[username]),
                        {"page": payload},
                    )

                    self.assertEqual(response.status_code, 400)
                    self.assertContains(response, "Invalid page parameter.", status_code=400)

    def test_public_profile_reported_zap_payloads_never_return_500(self):
        for username in self.reported_zap_usernames:
            for payload in self.reported_zap_payloads:
                for params, expected_extra_query, expected_category in (
                    ({"category": payload}, "", ""),
                    ({"q": payload}, "", ""),
                    (
                        {"category": self.demo_category.slug, "q": payload},
                        f"category={self.demo_category.slug}",
                        self.demo_category.slug,
                    ),
                ):
                    with self.subTest(username=username, params=params):
                        response = self.client.get(
                            reverse("accounts:public_profile", args=[username]),
                            params,
                        )

                        self.assertEqual(response.status_code, 200)
                        self.assertEqual(response.context["posts"].paginator.count, 0)
                        self.assertEqual(response.context["search_query"], "")
                        self.assertEqual(response.context["selected_category"], expected_category)
                        self.assertEqual(response.context["extra_query"], expected_extra_query)
                        self.assertNotIn("%27", response.context["extra_query"])
                        self.assertNotIn("%22", response.context["extra_query"])
                        self.assertNotIn("%3B", response.context["extra_query"])
                        self.assertNotIn("%28", response.context["extra_query"])

    def test_public_profile_active_category_link_toggles_filter_off(self):
        response = self.client.get(
            reverse("accounts:public_profile", args=[self.owner.username]),
            {"category": self.category.slug, "q": "Alpha"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alpha Search Match")
        self.assertNotContains(response, "Backend Public Post")
        self.assertContains(
            response,
            f'href="{reverse("accounts:public_profile", args=[self.owner.username])}?q=Alpha"',
            html=False,
        )

    def test_public_profile_parent_category_filter_includes_child_category_posts(self):
        _ensure_default_blog_categories()
        programming = Category.objects.get(slug="programming")
        Post.objects.create(
            author=self.owner,
            category=programming,
            title="Programming Article",
            excerpt="Hierarchy excerpt",
            content="Hierarchy content",
            is_published=True,
        )

        response = self.client.get(
            reverse("accounts:public_profile", args=[self.owner.username]),
            {"category": "technology"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Programming Article")
        self.assertNotContains(response, "Backend Public Post")
