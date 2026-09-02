"""`workload.*` icazə kataloqunun bütövlüyü (sillabus `test_permission_catalog` naxışı)."""

from django.test import TestCase

from apps.organizations.permissions import (
    PERMISSION_CATEGORIES,
    PERMISSION_CATEGORY_LABELS,
    PERMISSION_LABELS,
    get_all_permissions,
    validate_permissions,
)
from apps.workload.constants import (
    PERM_APPROVE,
    PERM_DISTRIBUTE,
    PERM_MANAGE,
    PERM_REPORT,
    PERM_REVIEW,
    PERM_SUBMIT,
    PERM_VIEW,
)

_MODULE_KEYS = (
    PERM_VIEW,
    PERM_MANAGE,
    PERM_SUBMIT,
    PERM_REVIEW,
    PERM_APPROVE,
    PERM_DISTRIBUTE,
    PERM_REPORT,
)


class WorkloadPermissionCatalogTest(TestCase):
    def test_category_exists_with_label(self):
        self.assertIn("workload", PERMISSION_CATEGORIES)
        self.assertIn("workload", PERMISSION_CATEGORY_LABELS)

    def test_every_module_key_is_in_the_catalog(self):
        catalog = set(get_all_permissions())
        for key in _MODULE_KEYS:
            self.assertIn(key, catalog, f"{key} kataloqda yoxdur")

    def test_every_key_has_a_human_label(self):
        for key in _MODULE_KEYS:
            self.assertIn(key, PERMISSION_LABELS, f"{key} üçün etiket yoxdur")

    def test_keys_validate(self):
        self.assertTrue(validate_permissions(list(_MODULE_KEYS)))
        self.assertTrue(validate_permissions(["workload.*"]))

    def test_default_roles_carry_the_expected_split(self):
        """Kafedra müdiri bölür, müəllim yalnız baxır, dekan təsdiqləmir."""
        from apps.organizations.default_roles_university import UNIVERSITY_ROLES

        roles = {role["name"]: set(role["permissions"]) for role in UNIVERSITY_ROLES}
        self.assertIn(PERM_DISTRIBUTE, roles["chair_head"])
        self.assertIn(PERM_MANAGE, roles["chair_head"])
        self.assertIn(PERM_VIEW, roles["teacher"])
        self.assertNotIn(PERM_DISTRIBUTE, roles["teacher"])
        self.assertNotIn(PERM_MANAGE, roles["teacher"])
        self.assertIn(PERM_VIEW, roles["dean"])
        self.assertNotIn(PERM_DISTRIBUTE, roles["dean"])
        # F2 hələ yoxdur — heç bir default rol `workload.approve` AÇIQ daşımır.
        for name, permissions in roles.items():
            if "*" in permissions or "workload.*" in permissions:
                continue
            self.assertNotIn(PERM_APPROVE, permissions, f"{name} rolunda approve açarı var")
