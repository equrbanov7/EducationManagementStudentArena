"""Fail-closed tests for credential/demo management commands."""

import importlib
from io import StringIO
from unittest.mock import Mock

from django.core.management.base import CommandError
from django.test import SimpleTestCase

from core.management.command_safety import ProductionCommandSafetyMixin, require_safe_management_command

_PROTECTED_COMMAND_MODULES = (
    "apps.accounts.management.commands.provision_student_credentials",
    "apps.accounts.management.commands.import_users_from_excel",
    "apps.exams.management.commands.seed_demo_hierarchy",
    "apps.exams.management.commands.seed_final_exam_demo",
    "apps.exams.management.commands.seed_group_demo_data",
    "apps.exams.management.commands.seed_room_monitor_demo",
    "apps.exams.management.commands.seed_stress_exam_journal",
    "apps.exams.management.commands.seed_stress_test",
    "apps.organizations.management.commands.create_sample_orgs",
    "apps.organizations.management.commands.seed_ci_e2e_scenario",
    "apps.organizations.management.commands.seed_ci_e2e_user",
    "apps.organizations.management.commands.seed_western_caspian",
)

_SENSITIVE_VALUE = "RealCredential-Do-Not-Log!"


def _command(module_name):
    return importlib.import_module(module_name).Command()


def _base_execute_options():
    return {
        "force_color": False,
        "no_color": False,
        "skip_checks": True,
    }


class ManagementCommandSafetyTests(SimpleTestCase):
    def test_production_denies_every_protected_command_before_handle(self):
        with self.settings(MANAGEMENT_COMMAND_ENVIRONMENT="production"):
            for module_name in _PROTECTED_COMMAND_MODULES:
                with self.subTest(module=module_name):
                    command = _command(module_name)
                    command.handle = Mock()

                    with self.assertRaisesMessage(
                        CommandError,
                        f"management_command_safety_denied: {command.safety_command_name}",
                    ):
                        command.execute(password=_SENSITIVE_VALUE, **_base_execute_options())

                    command.handle.assert_not_called()

    def test_unknown_environment_fails_closed(self):
        with self.settings(MANAGEMENT_COMMAND_ENVIRONMENT="prodution"):
            with self.assertRaises(CommandError):
                require_safe_management_command("provision_student_credentials")

    def test_local_and_test_environments_preserve_command_execution(self):
        for environment in ("local", "test"):
            with self.subTest(environment=environment), self.settings(MANAGEMENT_COMMAND_ENVIRONMENT=environment):
                for module_name in _PROTECTED_COMMAND_MODULES:
                    with self.subTest(module=module_name):
                        command = _command(module_name)
                        command.handle = Mock(return_value=None)

                        command.execute(**_base_execute_options())

                        command.handle.assert_called_once()

    def test_all_protected_command_names_are_non_empty_and_valid(self):
        for module_name in _PROTECTED_COMMAND_MODULES:
            with self.subTest(module=module_name):
                command = _command(module_name)
                name = command.safety_command_name
                self.assertEqual(name, module_name.rsplit(".", 1)[-1])
                self.assertRegex(name, r"^[a-z][a-z0-9_]*$")
                self.assertIs(command.__class__.__mro__[1], ProductionCommandSafetyMixin)

    def test_invalid_command_configuration_fails_closed_even_locally(self):
        with self.settings(MANAGEMENT_COMMAND_ENVIRONMENT="local"):
            for invalid_name in ("", "UPPER", "contains-dash", None):
                with self.subTest(name=invalid_name), self.assertRaises(CommandError):
                    require_safe_management_command(invalid_name)

    def test_multi_inheritance_command_runs_safety_execute_first(self):
        command = _command("apps.exams.management.commands.seed_group_demo_data")
        command.handle = Mock()
        self.assertIs(command.__class__.__mro__[1], ProductionCommandSafetyMixin)

        with self.settings(MANAGEMENT_COMMAND_ENVIRONMENT="production"), self.assertRaises(CommandError):
            command.execute(**_base_execute_options())

        command.handle.assert_not_called()

    def test_denial_never_echoes_supplied_credentials_or_writes_output(self):
        stdout = StringIO()
        stderr = StringIO()
        command = _command(_PROTECTED_COMMAND_MODULES[0])

        with self.settings(MANAGEMENT_COMMAND_ENVIRONMENT="production"):
            with self.assertRaises(CommandError) as raised:
                command.execute(
                    password=_SENSITIVE_VALUE,
                    stdout=stdout,
                    stderr=stderr,
                    **_base_execute_options(),
                )

        combined = f"{raised.exception}\n{stdout.getvalue()}\n{stderr.getvalue()}"
        self.assertNotIn(_SENSITIVE_VALUE, combined)
        self.assertIn("management_command_safety_denied", combined)
