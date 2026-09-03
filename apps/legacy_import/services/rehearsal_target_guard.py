"""Fail-closed interlocks proving a rehearsal target database is disposable.

Five independent classes of evidence are all required: an explicit settings
opt-in, a non-production environment, a shaped loopback endpoint on a
non-default port, a database-scoped marker that only a deliberate ``ALTER
DATABASE`` can set, and an unprivileged role with no active RLS bypass.  The
attestation reports a *shape* token instead of the real database name because
the rehearsal report artifact is committed to the repository.

Provisioning contract for the operator::

    CREATE DATABASE emsarena_rehearsal_ab12cd34ef56;
    ALTER DATABASE emsarena_rehearsal_ab12cd34ef56
        SET emsarena.rehearsal_target = 'disposable';
"""

from __future__ import annotations

import hashlib
import ipaddress
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from django.db import connection as default_connection
from django.db.migrations.executor import MigrationExecutor

from .rehearsal_contracts import LegacyRehearsalConfigError, canonical_json_digest, encoded_part

REHEARSAL_TARGET_DB_PATTERN = re.compile(r"emsarena_rehearsal_[a-f0-9]{12}\Z")
REHEARSAL_TARGET_DB_SHAPE = "emsarena_rehearsal_<12hex>"
REHEARSAL_TARGET_GUC = "emsarena.rehearsal_target"
REHEARSAL_TARGET_GUC_VALUE = "disposable"
RLS_BYPASS_GUC = "app.bypass_rls"
_RLS_BYPASS_ACTIVE_VALUE = "on"
_TARGET_VENDOR = "postgresql"
_DEFAULT_POSTGRES_PORT = 5432
_MIN_DISPOSABLE_PORT = 1024
_MAX_PORT = 65535
_LOCAL_ENVIRONMENTS = frozenset({"local", "test"})
_LOOPBACK_HOST_NAMES = frozenset({"localhost"})
_MIGRATION_HEAD_NAMESPACE = b"legacy-rehearsal-migration-head-v1\x00"


@dataclass(frozen=True, repr=False)
class TargetGuardAttestation:
    """PII-free, name-free proof that the interlocks were all satisfied."""

    vendor: str
    database_name_shape: str
    loopback: bool
    non_default_port: bool
    disposable_marker: bool
    role_is_superuser: bool
    role_bypasses_rls: bool
    rls_bypass_active: bool
    migration_head_digest: str

    def __repr__(self) -> str:
        return (
            "TargetGuardAttestation("
            f"vendor={self.vendor!r}, database_name_shape={self.database_name_shape!r}, "
            f"disposable_marker={self.disposable_marker})"
        )

    def to_safe_log_dict(self) -> dict[str, object]:
        return {
            "database_name_shape": self.database_name_shape,
            "disposable_marker": self.disposable_marker,
            "loopback": self.loopback,
            "migration_head_digest": self.migration_head_digest,
            "non_default_port": self.non_default_port,
            "rls_bypass_active": self.rls_bypass_active,
            "role_bypasses_rls": self.role_bypasses_rls,
            "role_is_superuser": self.role_is_superuser,
            "vendor": self.vendor,
        }

    def guard_digest(self) -> str:
        return canonical_json_digest(self.to_safe_log_dict())


def _settings_dict(connection: object) -> Mapping[str, object]:
    settings_dict = getattr(connection, "settings_dict", None)
    if not isinstance(settings_dict, Mapping):
        raise LegacyRehearsalConfigError("legacy_rehearsal_target_name_invalid")
    return settings_dict


def _is_loopback_host(host: object) -> bool:
    if type(host) is not str or not host:
        return False
    if host.casefold() in _LOOPBACK_HOST_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _target_port(value: object) -> int:
    try:
        if type(value) is int:
            port = value
        elif type(value) is str and value.isascii() and value.isdecimal():
            port = int(value, 10)
        else:
            raise ValueError
    except ValueError:
        raise LegacyRehearsalConfigError("legacy_rehearsal_target_port_invalid") from None
    if port == _DEFAULT_POSTGRES_PORT or not _MIN_DISPOSABLE_PORT <= port <= _MAX_PORT:
        raise LegacyRehearsalConfigError("legacy_rehearsal_target_port_invalid")
    return port


def _fetch_one(connection: object, *, statement: str, parameters: Sequence[object], code: str) -> Sequence[object]:
    try:
        with connection.cursor() as cursor:
            cursor.execute(statement, list(parameters))
            row = cursor.fetchone()
    except Exception:
        raise LegacyRehearsalConfigError(code) from None
    if row is None or isinstance(row, (str, bytes, Mapping)) or not isinstance(row, Sequence):
        raise LegacyRehearsalConfigError(code)
    return row


def _fetch_all(connection: object, *, statement: str, code: str) -> Sequence[object]:
    try:
        with connection.cursor() as cursor:
            cursor.execute(statement, [])
            rows = cursor.fetchall()
    except Exception:
        raise LegacyRehearsalConfigError(code) from None
    if isinstance(rows, (str, bytes, Mapping)) or not isinstance(rows, Sequence):
        raise LegacyRehearsalConfigError(code)
    return rows


def _current_setting(connection: object, *, name: str, code: str) -> str:
    row = _fetch_one(
        connection,
        statement="SELECT current_setting(%s, true)",
        parameters=[name],
        code=code,
    )
    if len(row) != 1:
        raise LegacyRehearsalConfigError(code)
    value = row[0]
    if value is None:
        return ""
    if type(value) is not str:
        raise LegacyRehearsalConfigError(code)
    return value.strip()


def _assert_unprivileged_role(connection: object) -> None:
    row = _fetch_one(
        connection,
        statement="SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user",
        parameters=[],
        code="legacy_rehearsal_target_role_privileged",
    )
    if len(row) != 2 or row[0] is not False or row[1] is not False:
        raise LegacyRehearsalConfigError("legacy_rehearsal_target_role_privileged")


def _migration_head_digest(connection: object) -> str:
    rows = _fetch_all(
        connection,
        statement="SELECT app, name FROM django_migrations",
        code="legacy_rehearsal_target_schema_unmigrated",
    )
    applied: list[tuple[str, str]] = []
    for row in rows:
        if isinstance(row, (str, bytes, Mapping)) or not isinstance(row, Sequence) or len(row) != 2:
            raise LegacyRehearsalConfigError("legacy_rehearsal_target_schema_unmigrated")
        app_label, name = row
        if type(app_label) is not str or type(name) is not str or not app_label or not name:
            raise LegacyRehearsalConfigError("legacy_rehearsal_target_schema_unmigrated")
        applied.append((app_label, name))
    if not applied:
        raise LegacyRehearsalConfigError("legacy_rehearsal_target_schema_unmigrated")
    digest = hashlib.sha256(_MIGRATION_HEAD_NAMESPACE)
    for app_label, name in sorted(applied):
        digest.update(encoded_part(app_label))
        digest.update(encoded_part(name))
    return digest.hexdigest()


def _assert_schema_current(connection: object, *, executor_class=MigrationExecutor) -> None:
    """Fail closed when the code expects migrations absent from the target.

    A non-empty ``django_migrations`` table proves only that *some* schema was
    installed.  It does not prove that the disposable target matches the code
    which is about to write it.  ``migrate --check`` uses the same canonical
    migration plan: any forward step means the target is stale and the
    rehearsal must not start.
    """

    try:
        executor = executor_class(connection)
        targets = executor.loader.graph.leaf_nodes()
        plan = executor.migration_plan(targets)
    except Exception:
        raise LegacyRehearsalConfigError("legacy_rehearsal_target_schema_unmigrated") from None
    if plan:
        raise LegacyRehearsalConfigError("legacy_rehearsal_target_schema_unmigrated")


def assert_disposable_rehearsal_target(*, settings_object: object, connection: object = None) -> TargetGuardAttestation:
    """Refuse to touch a target that is not provably disposable."""

    target = default_connection if connection is None else connection
    if getattr(settings_object, "LEGACY_REHEARSAL_TARGET_DISPOSABLE", False) is not True:
        raise LegacyRehearsalConfigError("legacy_rehearsal_target_not_opted_in")
    environment = getattr(settings_object, "MANAGEMENT_COMMAND_ENVIRONMENT", "production")
    if str(environment).strip().casefold() not in _LOCAL_ENVIRONMENTS:
        raise LegacyRehearsalConfigError("legacy_rehearsal_target_environment_denied")
    if getattr(target, "vendor", None) != _TARGET_VENDOR:
        raise LegacyRehearsalConfigError("legacy_rehearsal_target_vendor_invalid")

    settings_dict = _settings_dict(target)
    database_name = settings_dict.get("NAME")
    if type(database_name) is not str or not REHEARSAL_TARGET_DB_PATTERN.fullmatch(database_name):
        raise LegacyRehearsalConfigError("legacy_rehearsal_target_name_invalid")
    if not _is_loopback_host(settings_dict.get("HOST")):
        raise LegacyRehearsalConfigError("legacy_rehearsal_target_host_invalid")
    _target_port(settings_dict.get("PORT"))

    marker = _current_setting(
        target,
        name=REHEARSAL_TARGET_GUC,
        code="legacy_rehearsal_target_marker_missing",
    )
    if marker != REHEARSAL_TARGET_GUC_VALUE:
        raise LegacyRehearsalConfigError("legacy_rehearsal_target_marker_missing")
    _assert_unprivileged_role(target)
    bypass = _current_setting(
        target,
        name=RLS_BYPASS_GUC,
        code="legacy_rehearsal_target_rls_bypassed",
    )
    if bypass.casefold() == _RLS_BYPASS_ACTIVE_VALUE:
        raise LegacyRehearsalConfigError("legacy_rehearsal_target_rls_bypassed")
    _assert_schema_current(target)

    return TargetGuardAttestation(
        vendor=_TARGET_VENDOR,
        database_name_shape=REHEARSAL_TARGET_DB_SHAPE,
        loopback=True,
        non_default_port=True,
        disposable_marker=True,
        role_is_superuser=False,
        role_bypasses_rls=False,
        rls_bypass_active=False,
        migration_head_digest=_migration_head_digest(target),
    )
