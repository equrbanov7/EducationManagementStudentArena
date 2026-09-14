from unittest.mock import patch

from django.core.checks import Error, Warning
from django.test import SimpleTestCase, override_settings

from apps.organizations import checks


class DatabaseRoleCheckTests(SimpleTestCase):
    def run_check(self, mode, *, result=(False, "runtime"), failure=None):
        with override_settings(EMS_DB_ROLE_ENFORCE=mode), patch.object(checks.connection, "vendor", "postgresql"):
            with patch.object(checks, "_current_role_bypasses_rls", return_value=result, side_effect=failure):
                return checks.check_db_role_not_superuser(None)

    def test_safe_role_passes(self):
        self.assertEqual(self.run_check("error"), [])

    def test_privileged_role_blocks_strict_mode(self):
        result = self.run_check("error", result=(True, "owner"))
        self.assertIsInstance(result[0], Error)
        self.assertEqual(result[0].id, "organizations.E011")

    def test_unreachable_database_blocks_strict_mode_without_secret(self):
        result = self.run_check("error", failure=RuntimeError("secret-password"))
        self.assertIsInstance(result[0], Error)
        self.assertEqual(result[0].id, "organizations.E013")
        self.assertNotIn("secret-password", str(result))

    def test_unreachable_database_warns_in_transition_mode(self):
        result = self.run_check("warn", failure=RuntimeError("unavailable"))
        self.assertIsInstance(result[0], Warning)
        self.assertEqual(result[0].id, "organizations.W013")

    def test_invalid_mode_does_not_silently_disable_protection(self):
        self.assertEqual(self.run_check("erorr")[0].id, "organizations.E012")

    def test_migration_mode_remains_explicitly_off(self):
        self.assertEqual(self.run_check("off", failure=RuntimeError("must not query")), [])
