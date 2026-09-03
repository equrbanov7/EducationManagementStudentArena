"""Legacy reconcile PostgreSQL nəqliyyatının fail-closed təhlükəsizlik testləri."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.legacy_reconcile.transport import (  # noqa: E402
    TargetReader,
    TargetSecurityViolation,
    Timer,
)
from scripts.legacy_reconcile_report import build_parser  # noqa: E402

ORGANIZATION_ID = "a8a1a0f5-aeb7-43c5-848d-fcff008f7273"
RUN_ID = "137331f4-0d64-4a0b-b6bd-482a27624f60"


class _FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self._row = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, sql, params=None):
        self.connection.executed.append((sql, params))
        if "FROM pg_catalog.pg_roles" in sql:
            self._row = self.connection.role_row
        elif "current_setting('transaction_read_only')" in sql:
            self._row = self.connection.context_row
        else:
            self._row = None

    def fetchone(self):
        return self._row


class _FakeConnection:
    def __init__(self, *, role_row=("emsarena_app", False, False), context_row=None):
        self.role_row = role_row
        self.context_row = context_row or ("on", "off", ORGANIZATION_ID)
        self.executed = []
        self.session_calls = []
        self.rolled_back = False
        self.closed = False

    def set_session(self, **kwargs):
        self.session_calls.append(kwargs)

    def cursor(self, *args, **kwargs):
        return _FakeCursor(self)

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def _install_fake_psycopg(monkeypatch, connection):
    module = SimpleNamespace(connect=lambda **dsn: connection)
    monkeypatch.setitem(sys.modules, "psycopg2", module)


def _required_cli_args():
    return [
        "--db",
        "emsarena_rehearsal_deadbeefcafe",
        "--run-id",
        RUN_ID,
        "--organization-id",
        ORGANIZATION_ID,
        "--output",
        "/tmp/reconcile.md",
    ]


def test_parser_requires_valid_organization_uuid():
    parser = build_parser()
    args = parser.parse_args(_required_cli_args())
    assert args.organization_id == UUID(ORGANIZATION_ID)
    assert args.target_user == "emsarena_app"

    missing = _required_cli_args()
    del missing[4:6]
    with pytest.raises(SystemExit):
        parser.parse_args(missing)

    invalid = _required_cli_args()
    invalid[5] = "not-a-uuid"
    with pytest.raises(SystemExit):
        parser.parse_args(invalid)


def test_target_reader_establishes_verified_transaction_local_tenant_context(monkeypatch):
    connection = _FakeConnection()
    _install_fake_psycopg(monkeypatch, connection)

    reader = TargetReader(dsn={"dbname": "test"}, timer=Timer(), organization_id=ORGANIZATION_ID)

    assert connection.session_calls == [{"readonly": True, "autocommit": False}]
    statements = [sql for sql, _params in connection.executed]
    assert statements[0] == "SET TRANSACTION READ ONLY"
    assert "FROM pg_catalog.pg_roles" in statements[2]
    assert "set_config('app.bypass_rls', 'off', true)" in statements[3]
    assert connection.executed[4][1] == (ORGANIZATION_ID,)
    assert "current_setting('app.current_org_id', true)" in statements[5]

    reader.close()
    assert connection.rolled_back
    assert connection.closed


@pytest.mark.parametrize(
    "role_row",
    [
        ("postgres", True, False),
        ("rls_bypass", False, True),
    ],
)
def test_target_reader_refuses_privileged_roles_and_discards_connection(monkeypatch, role_row):
    connection = _FakeConnection(role_row=role_row)
    _install_fake_psycopg(monkeypatch, connection)

    with pytest.raises(TargetSecurityViolation, match="privileged_target_role_refused"):
        TargetReader(dsn={"dbname": "test"}, timer=Timer(), organization_id=ORGANIZATION_ID)

    assert connection.rolled_back
    assert connection.closed
    assert not any("app.current_org_id" in sql for sql, _params in connection.executed)


def test_target_reader_fails_closed_when_server_context_does_not_match(monkeypatch):
    connection = _FakeConnection(context_row=("on", "off", "00000000-0000-0000-0000-000000000000"))
    _install_fake_psycopg(monkeypatch, connection)

    with pytest.raises(TargetSecurityViolation, match="context_verification_failed"):
        TargetReader(dsn={"dbname": "test"}, timer=Timer(), organization_id=ORGANIZATION_ID)

    assert connection.rolled_back
    assert connection.closed


def test_target_reader_rejects_invalid_organization_before_connect(monkeypatch):
    calls = []
    monkeypatch.setitem(sys.modules, "psycopg2", SimpleNamespace(connect=lambda **dsn: calls.append(dsn)))

    with pytest.raises(ValueError, match="organization_id_invalid"):
        TargetReader(dsn={"dbname": "test"}, timer=Timer(), organization_id="not-a-uuid")

    assert calls == []
