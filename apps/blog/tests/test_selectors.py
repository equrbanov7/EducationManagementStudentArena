from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.blog.models import Category, Post
from apps.blog.selectors import get_navbar_categories

User = get_user_model()


class BlogSelectorCacheFallbackTest(TestCase):
    def setUp(self):
        self.author = User.objects.create_user(
            username="selector_author",
            email="selector_author@example.com",
            password="StrongPass123!",
        )
        self.category = Category.objects.create(
            name="Announcements",
            slug="announcements",
            show_in_navbar=True,
        )
        Post.objects.create(
            author=self.author,
            title="Launch Update",
            content="Published content",
            is_published=True,
            category=self.category,
        )

    def test_get_navbar_categories_falls_back_when_cache_read_fails(self):
        with patch("apps.blog.selectors.cache.get", side_effect=ConnectionError("redis down")):
            categories = get_navbar_categories()

        self.assertIn("announcements", [category.slug for category in categories])
