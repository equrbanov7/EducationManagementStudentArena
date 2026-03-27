"""
Service tests for blog app.
"""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.blog.models import Category
from apps.blog.services import can_user_manage_categories, resolve_post_category_selection

User = get_user_model()


class BlogCategoryServiceTest(TestCase):
    def setUp(self):
        self.superadmin = User.objects.create_superuser(
            username="blog_service_superadmin",
            email="blog_service_superadmin@example.com",
            password="StrongPass123!",
        )
        self.normal_user = User.objects.create_user(
            username="blog_service_member",
            email="blog_service_member@example.com",
            password="StrongPass123!",
        )
        self.root_category = Category.objects.create(name="Service Root")
        self.subcategory = Category.objects.create(name="Service Child", parent=self.root_category)
        self.other_root = Category.objects.create(name="Other Root")

    def test_only_superadmin_can_manage_categories(self):
        self.assertTrue(can_user_manage_categories(self.superadmin))
        self.assertFalse(can_user_manage_categories(self.normal_user))

    def test_resolve_post_category_selection_accepts_matching_subcategory(self):
        resolved_category = resolve_post_category_selection(
            category=self.root_category,
            subcategory=self.subcategory,
        )

        self.assertEqual(resolved_category, self.subcategory)

    def test_resolve_post_category_selection_rejects_cross_tree_subcategory(self):
        with self.assertRaises(ValidationError):
            resolve_post_category_selection(
                category=self.other_root,
                subcategory=self.subcategory,
            )
