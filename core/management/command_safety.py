"""Fail-closed safety gate for high-risk management commands.

Local and test settings explicitly opt into their respective environments.
Every other value is treated as production-like and denied unconditionally.
"""

import os
import re

from django.conf import settings
from django.core.management.base import CommandError

_COMMAND_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_NON_PRODUCTION_ENVIRONMENTS = frozenset({"local", "test"})
_DENIED_PREFIX = "management_command_safety_denied"
#: Sahibin qərarı 2026-09-16: istehsalda YALNIZ bu komandalar, yalnız həmin icra üçün
#: verilən açıq ACK ilə işləyir (`MANAGEMENT_COMMAND_PRODUCTION_ACK=<komanda adı>`,
#: məs. `docker exec -e ... app manage.py provision_student_credentials …`). Seed/demo
#: komandaları siyahıda DEYİL — onlar üçün istehsal icazəsi yenə mövcud deyil.
_PRODUCTION_ACK_ALLOWED = frozenset({"provision_student_credentials"})
PRODUCTION_ACK_ENV = "MANAGEMENT_COMMAND_PRODUCTION_ACK"


def _validate_command_name(command_name: str) -> None:
    if not isinstance(command_name, str) or not _COMMAND_NAME_RE.fullmatch(command_name):
        raise CommandError(f"{_DENIED_PREFIX}: invalid protected command configuration")


def require_safe_management_command(command_name: str) -> None:
    """Deny a high-risk command unless its execution context is authorized.

    The default environment is deliberately production-like. A missing or
    misspelled setting can therefore never silently enable a protected command.
    Production authorization exists only for ``_PRODUCTION_ACK_ALLOWED`` commands and
    only when the process environment carries ``PRODUCTION_ACK_ENV`` equal to the exact
    command name — a per-invocation, explicit acknowledgement; never a persistent setting.
    """

    _validate_command_name(command_name)
    environment = str(getattr(settings, "MANAGEMENT_COMMAND_ENVIRONMENT", "production")).strip().casefold()
    if environment in _NON_PRODUCTION_ENVIRONMENTS:
        return
    if command_name in _PRODUCTION_ACK_ALLOWED and os.environ.get(PRODUCTION_ACK_ENV, "").strip() == command_name:
        return

    raise CommandError(f"{_DENIED_PREFIX}: {command_name}; production execution is disabled")


class ProductionCommandSafetyMixin:
    """Add fail-closed production authorization to a Django command."""

    safety_command_name = ""

    def execute(self, *args, **options):
        require_safe_management_command(self.safety_command_name)
        return super().execute(*args, **options)
