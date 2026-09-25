"""Dözümlü axtarış (sahib 2026-09-26) — blog post axtarışları (başlıq/mətn/müəllif)."""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import ProfileRole, UserProfile
from apps.blog.models import Category, Post
from apps.blog.services import collect_reviewable_posts

User = get_user_model()


class BlogSearchTolerantTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superadmin = User.objects.create_superuser("bl26_sa", "bl26_sa@test.com", "pass1234")
        cls.author = User.objects.create_user(
            "bl26_author", "bl26_author@test.com", "pass1234", first_name="Şahzad", last_name="Əliyev"
        )
        cls.other_author = User.objects.create_user("bl26_other", "bl26_other@test.com", "pass1234")
        for user in (cls.author, cls.other_author):
            UserProfile.objects.update_or_create(user=user, defaults={"role": ProfileRole.TEACHER})
        category = Category.objects.create(name="C26", slug="c26")
        cls.hit = Post.objects.create(
            title="Verilənlər bazası dərsi",
            content="Mətn",
            author=cls.author,
            category=category,
            is_published=True,
            slug="bl26-hit",
        )
        cls.miss = Post.objects.create(
            title="Şəbəkə",
            content="Protokollar",
            author=cls.other_author,
            category=category,
            is_published=True,
            slug="bl26-miss",
        )

    def test_superadmin_post_management_title_and_author(self):
        self.client.force_login(self.superadmin)
        url = reverse("accounts:superadmin_post_management")
        for query in ("Verilenler", "verilenler baza", "Aliyev", "shahzad"):
            with self.subTest(query=query):
                response = self.client.get(url, {"q": query})
                self.assertEqual(response.status_code, 200)
                self.assertEqual([p.id for p in response.context["page_obj"]], [self.hit.id])

    def test_reviewable_posts_search_is_tolerant(self):
        items, search, *_ = collect_reviewable_posts(self.superadmin, search="Verilenler", status="all")
        self.assertEqual(search, "Verilenler")
        self.assertEqual([item["post"].id for item in items], [self.hit.id])

    @override_settings(UNIVERSITY_MODE=False)
    def test_public_home_search_is_tolerant(self):
        response = self.client.get(reverse("home"), {"q": "sebeke"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual([p.id for p in response.context["page_obj"]], [self.miss.id])
        response = self.client.get(reverse("home"), {"q": "verilenler dersi"})
        self.assertEqual([p.id for p in response.context["page_obj"]], [self.hit.id])
