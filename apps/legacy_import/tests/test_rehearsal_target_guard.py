import pytest

from apps.legacy_import.services import rehearsal_target_guard as target_guard_module
from apps.legacy_import.services.rehearsal_contracts import LegacyRehearsalConfigError
from apps.legacy_import.services.rehearsal_target_guard import (
    REHEARSAL_TARGET_DB_SHAPE,
    REHEARSAL_TARGET_GUC,
    REHEARSAL_TARGET_GUC_VALUE,
    RLS_BYPASS_GUC,
    _assert_schema_current,
    assert_disposable_rehearsal_target,
)

_REAL_DATABASE_NAME = "emsarena_rehearsal_ab12cd34ef56"
_MIGRATION_ROWS = (("legacy_import", "0001_initial"), ("organizations", "0027_seed_grade_approval_permissions"))


@pytest.fixture(autouse=True)
def _fake_connections_have_a_current_schema(monkeypatch):
    """The unit fake is not a Django connection; schema parity has focused tests."""

    monkeypatch.setattr(target_guard_module, "_assert_schema_current", lambda _connection: None)


class _Settings:
    def __init__(self, *, disposable=True, environment="test"):
        self.LEGACY_REHEARSAL_TARGET_DISPOSABLE = disposable
        self.MANAGEMENT_COMMAND_ENVIRONMENT = environment


class _Cursor:
    def __init__(self, connection):
        self._connection = connection
        self._rows = ()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self._connection.closed_cursors += 1
        return False

    def execute(self, statement, parameters):
        self._connection.statements.append((statement, tuple(parameters)))
        if "current_setting" in statement:
            self._rows = ((self._connection.settings.get(parameters[0]),),)
        elif "pg_roles" in statement:
            self._rows = ((self._connection.role_is_superuser, self._connection.role_bypasses_rls),)
        elif "django_migrations" in statement:
            self._rows = tuple(self._connection.migration_rows)
        else:  # pragma: no cover - the guard issues no other statement
            raise AssertionError("unexpected statement")

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


class _Connection:
    def __init__(
        self,
        *,
        vendor="postgresql",
        name=_REAL_DATABASE_NAME,
        host="127.0.0.1",
        port="55432",
        marker=REHEARSAL_TARGET_GUC_VALUE,
        rls_bypass="off",
        role_is_superuser=False,
        role_bypasses_rls=False,
        migration_rows=_MIGRATION_ROWS,
    ):
        self.vendor = vendor
        self.settings_dict = {"NAME": name, "HOST": host, "PORT": port}
        self.settings = {REHEARSAL_TARGET_GUC: marker, RLS_BYPASS_GUC: rls_bypass}
        self.role_is_superuser = role_is_superuser
        self.role_bypasses_rls = role_bypasses_rls
        self.migration_rows = migration_rows
        self.statements = []
        self.closed_cursors = 0

    def cursor(self):
        return _Cursor(self)


def _attest(settings_object=None, **connection_overrides):
    return assert_disposable_rehearsal_target(
        settings_object=settings_object or _Settings(),
        connection=_Connection(**connection_overrides),
    )


def _refused(settings_object=None, **connection_overrides):
    with pytest.raises(LegacyRehearsalConfigError) as exc_info:
        _attest(settings_object, **connection_overrides)
    return exc_info.value.code


def test_guard_passes_only_when_every_interlock_holds():
    connection = _Connection()

    attestation = assert_disposable_rehearsal_target(settings_object=_Settings(), connection=connection)

    assert attestation.vendor == "postgresql"
    assert attestation.database_name_shape == REHEARSAL_TARGET_DB_SHAPE
    assert (attestation.loopback, attestation.non_default_port, attestation.disposable_marker) == (True, True, True)
    assert (attestation.role_is_superuser, attestation.role_bypasses_rls, attestation.rls_bypass_active) == (
        False,
        False,
        False,
    )
    assert len(attestation.migration_head_digest) == 64
    assert len(attestation.guard_digest()) == 64
    assert connection.closed_cursors == len(connection.statements) == 4


@pytest.mark.parametrize("disposable", [False, "1", 1, "true", "disposable", None])
def test_guard_requires_explicit_disposable_setting(disposable):
    assert _refused(_Settings(disposable=disposable)) == "legacy_rehearsal_target_not_opted_in"


@pytest.mark.parametrize("environment", ["production", "staging", "", "Production"])
def test_guard_requires_a_non_production_environment(environment):
    code = _refused(_Settings(environment=environment))

    assert code == "legacy_rehearsal_target_environment_denied"


@pytest.mark.parametrize("environment", ["local", "TEST"])
def test_guard_accepts_case_insensitive_local_environments(environment):
    assert _attest(_Settings(environment=environment)).disposable_marker is True


@pytest.mark.parametrize("vendor", ["sqlite", "mysql", "", None])
def test_guard_rejects_non_postgresql_vendor(vendor):
    assert _refused(vendor=vendor) == "legacy_rehearsal_target_vendor_invalid"


@pytest.mark.parametrize(
    "name",
    [
        "emsarena",
        "emsarena_rehearsal_",
        "emsarena_rehearsal_AB12CD34EF56",
        "emsarena_rehearsal_ab12cd34ef5",
        "emsarena_rehearsal_ab12cd34ef56x",
        "x_emsarena_rehearsal_ab12cd34ef56",
        None,
    ],
)
def test_guard_rejects_unpatterned_database_name(name):
    assert _refused(name=name) == "legacy_rehearsal_target_name_invalid"


@pytest.mark.parametrize("host", ["10.0.2.42", "db.internal", "", None, "example.com"])
def test_guard_rejects_non_loopback_host(host):
    assert _refused(host=host) == "legacy_rehearsal_target_host_invalid"


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1", "127.0.0.5"])
def test_guard_accepts_literal_loopback_hosts(host):
    assert _attest(host=host).loopback is True


@pytest.mark.parametrize("port", [5432, "5432", 80, 70000, "", None, "abc", -1])
def test_guard_rejects_default_port(port):
    assert _refused(port=port) == "legacy_rehearsal_target_port_invalid"


@pytest.mark.parametrize("marker", [None, "", "Disposable", "production", "disposable-local-only", 1])
def test_guard_rejects_missing_disposable_marker(marker):
    assert _refused(marker=marker) == "legacy_rehearsal_target_marker_missing"


def test_guard_accepts_the_marker_regardless_of_surrounding_whitespace():
    assert _attest(marker=" disposable ").disposable_marker is True


@pytest.mark.parametrize(
    ("superuser", "bypassrls"),
    [(True, False), (False, True), (True, True), (None, False), (False, "f")],
)
def test_guard_rejects_superuser_or_bypassrls_role(superuser, bypassrls):
    code = _refused(role_is_superuser=superuser, role_bypasses_rls=bypassrls)

    assert code == "legacy_rehearsal_target_role_privileged"


@pytest.mark.parametrize("bypass", ["on", "ON", " on "])
def test_guard_rejects_active_rls_bypass(bypass):
    assert _refused(rls_bypass=bypass) == "legacy_rehearsal_target_rls_bypassed"


@pytest.mark.parametrize("rows", [(), (("legacy_import",),), ((None, "0001_initial"),), ("legacy_import",)])
def test_guard_rejects_unmigrated_or_malformed_schema(rows):
    assert _refused(migration_rows=rows) == "legacy_rehearsal_target_schema_unmigrated"


class _MigrationGraph:
    def leaf_nodes(self):
        return (("accounts", "0017_userprofile_demographics"),)


class _MigrationLoader:
    graph = _MigrationGraph()


def _executor_with_plan(plan):
    class _Executor:
        loader = _MigrationLoader()

        def __init__(self, connection):
            self.connection = connection

        def migration_plan(self, targets):
            assert targets == (("accounts", "0017_userprofile_demographics"),)
            return plan

    return _Executor


def test_schema_parity_accepts_an_empty_forward_plan():
    _assert_schema_current(object(), executor_class=_executor_with_plan([]))


def test_schema_parity_rejects_a_pending_code_migration():
    with pytest.raises(LegacyRehearsalConfigError) as exc_info:
        _assert_schema_current(
            object(),
            executor_class=_executor_with_plan([("accounts.0017", False)]),
        )

    assert exc_info.value.code == "legacy_rehearsal_target_schema_unmigrated"


def test_schema_parity_fails_closed_when_the_migration_graph_cannot_be_read():
    class _BrokenExecutor:
        def __init__(self, _connection):
            raise RuntimeError("unreadable migration graph")

    with pytest.raises(LegacyRehearsalConfigError) as exc_info:
        _assert_schema_current(object(), executor_class=_BrokenExecutor)

    assert exc_info.value.code == "legacy_rehearsal_target_schema_unmigrated"


def test_migration_head_digest_is_order_independent_but_content_sensitive():
    forward = _attest(migration_rows=_MIGRATION_ROWS).migration_head_digest
    reversed_rows = _attest(migration_rows=tuple(reversed(_MIGRATION_ROWS))).migration_head_digest
    extended = _attest(migration_rows=(*_MIGRATION_ROWS, ("accounts", "0002_extra"))).migration_head_digest

    assert forward == reversed_rows
    assert forward != extended


def test_guard_attestation_never_exposes_real_database_name():
    connection = _Connection()
    attestation = assert_disposable_rehearsal_target(settings_object=_Settings(), connection=connection)
    exposed = (repr(attestation), str(attestation.to_safe_log_dict()), attestation.guard_digest())

    assert _REAL_DATABASE_NAME not in " ".join(exposed)
    assert "ab12cd34ef56" not in " ".join(exposed)
    assert attestation.to_safe_log_dict()["database_name_shape"] == REHEARSAL_TARGET_DB_SHAPE
    assert set(attestation.to_safe_log_dict()) == {
        "database_name_shape",
        "disposable_marker",
        "loopback",
        "migration_head_digest",
        "non_default_port",
        "rls_bypass_active",
        "role_bypasses_rls",
        "role_is_superuser",
        "vendor",
    }


def test_guard_digest_changes_with_the_migration_head():
    first = _attest()
    second = _attest(migration_rows=(*_MIGRATION_ROWS, ("exams", "0044_answer_snapshot")))

    assert first.guard_digest() != second.guard_digest()
    assert first.guard_digest() == _attest().guard_digest()
