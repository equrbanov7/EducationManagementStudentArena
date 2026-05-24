"""
Permission tests for organizations app.
"""

from django.test import TestCase

from ..permissions import expand_wildcard_permissions, get_all_permissions, has_permission, validate_permissions


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

    def test_grading_alias_permissions_match_legacy_prefix(self):
        """Legacy `grading.*` roles should satisfy current `grade.*` checks."""
        self.assertTrue(has_permission(["grading.input"], "grade.input"))
        self.assertTrue(has_permission(["grading.*"], "grade.input"))
        self.assertTrue(validate_permissions(["grading.*"]))
        self.assertIn("grade.input", expand_wildcard_permissions(["grading.*"]))

    def test_plural_category_aliases_match_singular_permission_checks(self):
        """Legacy plural role wildcards should satisfy current singular checks."""
        self.assertTrue(has_permission(["courses.*"], "course.create"))
        self.assertTrue(has_permission(["exams.*"], "exam.host"))
        self.assertTrue(has_permission(["members.*"], "member.edit"))
        self.assertTrue(has_permission(["roles.*"], "role.assign"))
        self.assertTrue(validate_permissions(["courses.*", "exams.*", "members.*", "roles.*"]))
        self.assertIn("course.create", expand_wildcard_permissions(["courses.*"]))
        self.assertIn("exam.host", expand_wildcard_permissions(["exams.*"]))

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
        self.assertIn("assignment.delete", all_perms)
        self.assertIn("project.delete", all_perms)
        self.assertIn("lab.delete", all_perms)


class DefaultRolesCanonicalPermissionTest(TestCase):
    """FAZA 10 — default role templates must use only canonical prefixes."""

    LEGACY_PREFIXES = ("grading.", "courses.", "exams.", "members.", "structure.")

    def test_default_roles_use_no_legacy_prefixes(self):
        """default_roles.py must emit canonical names only."""
        from apps.organizations.default_roles import DEFAULT_ROLES

        offenders = []
        for org_type, roles in DEFAULT_ROLES.items():
            for role in roles:
                for perm in role.get("permissions", []):
                    if isinstance(perm, str) and perm.startswith(self.LEGACY_PREFIXES):
                        offenders.append(f"{org_type}/{role['name']}: {perm}")
        self.assertEqual(offenders, [], f"Legacy permission prefixes still present: {offenders}")

    def test_default_roles_permissions_are_all_valid(self):
        """Every permission in every default role must validate."""
        from apps.organizations.default_roles import DEFAULT_ROLES

        for org_type, roles in DEFAULT_ROLES.items():
            for role in roles:
                perms = role.get("permissions", [])
                self.assertTrue(
                    validate_permissions(perms),
                    f"Invalid permission set in {org_type}/{role['name']}: {perms}",
                )


class LegacyPermissionMigrationTest(TestCase):
    """FAZA 10 — the canonicalization logic used by migration 0006."""

    def test_canonicalize_rewrites_legacy_prefixes(self):
        # The migration module name starts with a digit, so it must be loaded
        # via importlib rather than a normal import statement.
        import importlib

        mod = importlib.import_module("apps.organizations.migrations.0006_migrate_legacy_permission_aliases")
        canonical = mod._canonicalize
        self.assertEqual(canonical("grading.input"), "grade.input")
        self.assertEqual(canonical("courses.*"), "course.*")
        self.assertEqual(canonical("exams.host"), "exam.host")
        self.assertEqual(canonical("members.edit"), "member.edit")
        self.assertEqual(canonical("structure.*"), "unit.*")
        # Already-canonical names are untouched.
        self.assertEqual(canonical("grade.input"), "grade.input")
        self.assertEqual(canonical("*"), "*")
