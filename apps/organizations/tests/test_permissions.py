"""
Permission tests for organizations app.
"""

from django.test import TestCase

from ..permissions import (expand_wildcard_permissions, get_all_permissions,
                           has_permission, validate_permissions)


class PermissionSystemTest(TestCase):
    """Tests for permission checking system."""

    def test_exact_permission_match(self):
        """Test exact permission matching."""
        user_perms = ["course.create", "course.view"]
        self.assertTrue(has_permission(user_perms, "course.create"))
        self.assertTrue(has_permission(user_perms, "course.view"))
        self.assertFalse(has_permission(user_perms, "course.delete"))

    def test_wildcard_all(self):
        """Test wildcard for all permissions."""
        user_perms = ["*"]
        self.assertTrue(has_permission(user_perms, "course.create"))
        self.assertTrue(has_permission(user_perms, "exam.host"))
        self.assertTrue(has_permission(user_perms, "anything.really"))

    def test_category_wildcard(self):
        """Test category wildcard permissions."""
        user_perms = ["course.*"]
        self.assertTrue(has_permission(user_perms, "course.create"))
        self.assertTrue(has_permission(user_perms, "course.view"))
        self.assertTrue(has_permission(user_perms, "course.delete"))
        self.assertFalse(has_permission(user_perms, "exam.create"))

    def test_empty_permissions(self):
        """Test with empty permission list."""
        user_perms = []
        self.assertFalse(has_permission(user_perms, "course.create"))

    def test_validate_permissions(self):
        """Test permission validation."""
        self.assertTrue(validate_permissions(["course.create", "exam.view"]))
        self.assertTrue(validate_permissions(["*"]))
        self.assertTrue(validate_permissions(["course.*"]))
        self.assertFalse(validate_permissions(["invalid.permission"]))

    def test_expand_wildcards(self):
        """Test expanding wildcard permissions."""
        perms = expand_wildcard_permissions(["course.*", "exam.view"])
        self.assertIn("course.create", perms)
        self.assertIn("course.view", perms)
        self.assertIn("exam.view", perms)
        self.assertNotIn("exam.create", perms)

    def test_get_all_permissions(self):
        """Test getting all available permissions."""
        all_perms = get_all_permissions()
        self.assertGreater(len(all_perms), 0)
        self.assertIn("course.create", all_perms)
        self.assertIn("exam.view", all_perms)
