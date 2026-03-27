from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.blog.admin import CategoryAdmin
from apps.blog.models import Category

User = get_user_model()


class CategoryAdminPermissionTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.site = AdminSite()
        self.admin = CategoryAdmin(Category, self.site)
        self.superadmin = User.objects.create_superuser(
            username="blog_category_superadmin",
            email="blog_category_superadmin@example.com",
            password="StrongPass123!",
        )
        self.normal_user = User.objects.create_user(
            username="blog_category_teacher",
            email="blog_category_teacher@example.com",
            password="StrongPass123!",
        )

    def test_superadmin_can_manage_categories_in_admin(self):
        request = self.factory.get("/admin/blog/category/")
        request.user = self.superadmin

        self.assertTrue(self.admin.has_module_permission(request))
        self.assertTrue(self.admin.has_add_permission(request))
        self.assertTrue(self.admin.has_change_permission(request))
        self.assertTrue(self.admin.has_delete_permission(request))

    def test_normal_user_cannot_manage_categories_in_admin(self):
        request = self.factory.get("/admin/blog/category/")
        request.user = self.normal_user

        self.assertFalse(self.admin.has_module_permission(request))
        self.assertFalse(self.admin.has_add_permission(request))
        self.assertFalse(self.admin.has_change_permission(request))
        self.assertFalse(self.admin.has_delete_permission(request))
