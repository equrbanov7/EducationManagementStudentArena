"""Fail-closed safety gate for high-risk management commands.

Local and test settings explicitly opt into their respective environments.
Every other value is treated as production-like and denied unconditionally.
"""

import re

from django.conf import settings
from django.core.management.base import CommandError

_COMMAND_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_NON_PRODUCTION_ENVIRONMENTS = frozenset({"local", "test"})
_DENIED_PREFIX = "management_command_safety_denied"


def _validate_command_name(command_name: str) -> None:
    if not isinstance(command_name, str) or not _COMMAND_NAME_RE.fullmatch(command_name):
        raise CommandError(f"{_DENIED_PREFIX}: invalid protected command configuration")


def require_safe_management_command(command_name: str) -> None:
    """Deny a high-risk command unless its execution context is authorized.

    The default environment is deliberately production-like. A missing or
    misspelled setting can therefore never silently enable a protected command.
    Production authorization is deliberately unavailable for protected commands.
    """

    _validate_command_name(command_name)
    environment = str(getattr(settings, "MANAGEMENT_COMMAND_ENVIRONMENT", "production")).strip().casefold()
    if environment in _NON_PRODUCTION_ENVIRONMENTS:
        return

    raise CommandError(f"{_DENIED_PREFIX}: {command_name}; production execution is disabled")


class ProductionCommandSafetyMixin:
    """Add fail-closed production authorization to a Django command."""

    safety_command_name = ""

    def execute(self, *args, **options):
        require_safe_management_command(self.safety_command_name)
        return super().execute(*args, **options)
