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
    PERM_OBJECT,
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
    PERM_OBJECT,
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
        """Kafedra müdiri bölür, müəllim yalnız baxır+etiraz edir, dekan bölmür."""
        from apps.organizations.default_roles_university import UNIVERSITY_ROLES

        roles = {role["name"]: set(role["permissions"]) for role in UNIVERSITY_ROLES}
        self.assertIn(PERM_DISTRIBUTE, roles["chair_head"])
        self.assertIn(PERM_MANAGE, roles["chair_head"])
        self.assertIn(PERM_VIEW, roles["teacher"])
        self.assertNotIn(PERM_DISTRIBUTE, roles["teacher"])
        self.assertNotIn(PERM_MANAGE, roles["teacher"])
        self.assertIn(PERM_VIEW, roles["dean"])
        self.assertNotIn(PERM_DISTRIBUTE, roles["dean"])

    def test_stage4_chain_is_split_across_roles(self):
        """Zəncirin dörd halqası dörd AYRI rolda (səlahiyyət ayrılığı).

        Mərhələ 4-ə qədər `workload.approve` heç bir rolda AÇIQ deyildi (F2
        yox idi); indi o, YALNIZ dekandadır və dekanda `submit`/`distribute`
        YOXDUR — yəni bir nəfər zənciri təkbaşına keçirə bilmir.
        """
        from apps.organizations.default_roles_university import UNIVERSITY_ROLES

        roles = {role["name"]: set(role["permissions"]) for role in UNIVERSITY_ROLES}
        operators = {name for name, perms in roles.items() if "*" in perms or "workload.*" in perms}

        self.assertIn(PERM_SUBMIT, roles["teaching_office_head"])
        self.assertNotIn(PERM_APPROVE, roles["teaching_office_head"])
        self.assertNotIn(PERM_DISTRIBUTE, roles["teaching_office_head"])

        self.assertIn(PERM_REVIEW, roles["program_coordinator"])
        self.assertNotIn(PERM_APPROVE, roles["program_coordinator"])

        self.assertIn(PERM_APPROVE, roles["dean"])
        self.assertNotIn(PERM_SUBMIT, roles["dean"])

        self.assertIn(PERM_OBJECT, roles["teacher"])
        self.assertNotIn(PERM_APPROVE, roles["teacher"])

        # `approve` açarı YALNIZ dekanda (+ operator rolları) açıqdır.
        holders = {name for name, permissions in roles.items() if PERM_APPROVE in permissions and name not in operators}
        self.assertEqual(holders, {"dean"}, f"gözlənilməz approve daşıyıcıları: {holders}")
