from dataclasses import FrozenInstanceError, replace
from types import SimpleNamespace

import pytest

from apps.legacy_import.services import mariadb_gateway
from apps.legacy_import.services.mariadb_gateway import (
    FreshPyMySQLConnectionFactory,
    MariaDBSourceConfig,
    MariaDBSourceGatewayError,
    load_mariadb_source_config,
)

_HOST = "source.internal.invalid"
_USER = "legacy-reader"
_PASSWORD = "synthetic-never-log-password"
_DATABASE = "legacy_source_private"


def _tls_config(tmp_path, **overrides):
    ca_path = tmp_path / "source-ca.pem"
    ca_path.write_text("synthetic test CA", encoding="ascii")
    values = {
        "host": _HOST,
        "port": 3306,
        "user": _USER,
        "password": _PASSWORD,
        "database": _DATABASE,
        "ca_path": str(ca_path),
        "deployment_mode": "production",
        "local_disposable": False,
        "connect_timeout": 5,
        "read_timeout": 60,
        "write_timeout": 10,
        "charset": "utf8mb4",
    }
    values.update(overrides)
    return MariaDBSourceConfig(**values)


def _local_config(**overrides):
    values = {
        "host": "127.0.0.1",
        "port": 43306,
        "user": _USER,
        "password": _PASSWORD,
        "database": _DATABASE,
        "ca_path": None,
        "deployment_mode": "test",
        "local_disposable": True,
        "connect_timeout": 5,
        "read_timeout": 60,
        "write_timeout": 10,
        "charset": "utf8mb4",
    }
    values.update(overrides)
    return MariaDBSourceConfig(**values)


def test_config_is_frozen_and_repr_and_safe_log_hide_all_connection_details(tmp_path):
    config = _tls_config(tmp_path)

    with pytest.raises(FrozenInstanceError):
        config.host = "changed.invalid"

    rendered = f"{config!r} {config} {config.to_safe_log_dict()}"
    for forbidden in (_HOST, _USER, _PASSWORD, _DATABASE, config.ca_path):
        assert forbidden not in rendered


def test_tls_factory_uses_verified_identity_bounded_io_and_safe_client_flags(tmp_path, monkeypatch):
    config = _tls_config(tmp_path)
    calls = []
    connections = [object(), object()]

    def fake_connect(**kwargs):
        calls.append(kwargs)
        return connections[len(calls) - 1]

    monkeypatch.setattr(mariadb_gateway.pymysql, "connect", fake_connect)
    factory = FreshPyMySQLConnectionFactory(config)

    assert factory() is connections[0]
    assert factory() is connections[1]
    assert len(calls) == 2
    assert calls[0] is not calls[1]
    assert calls[0]["ssl_ca"] == config.ca_path
    assert calls[0]["ssl_disabled"] is False
    assert calls[0]["ssl_verify_cert"] is True
    assert calls[0]["ssl_verify_identity"] is True
    assert calls[0]["connect_timeout"] == 5
    assert calls[0]["read_timeout"] == 60
    assert calls[0]["write_timeout"] == 10
    assert calls[0]["charset"] == "utf8mb4"
    assert calls[0]["autocommit"] is False
    assert calls[0]["client_flag"] == 0
    assert calls[0]["local_infile"] is False
    assert repr(factory) == "FreshPyMySQLConnectionFactory()"


def test_local_disposable_factory_is_explicit_plaintext_on_loopback(monkeypatch):
    captured = []
    monkeypatch.setattr(mariadb_gateway.pymysql, "connect", lambda **kwargs: captured.append(kwargs) or object())

    FreshPyMySQLConnectionFactory(_local_config())()

    assert captured[0]["ssl_disabled"] is True
    assert "ssl_ca" not in captured[0]
    assert "ssl_verify_cert" not in captured[0]
    assert "ssl_verify_identity" not in captured[0]


@pytest.mark.parametrize(
    "overrides",
    (
        {"host": "localhost"},
        {"host": "192.168.1.10"},
        {"port": 3306},
        {"port": 1023},
        {"deployment_mode": "production"},
        {"deployment_mode": "staging"},
        {"ca_path": "/tmp/misleading-ca.pem"},
    ),
)
def test_local_disposable_policy_fails_closed(overrides):
    with pytest.raises(MariaDBSourceGatewayError) as exc_info:
        _local_config(**overrides)

    assert exc_info.value.code == "legacy_mariadb_gateway_local_disposable_forbidden"


def test_tls_is_mandatory_when_not_explicitly_local_disposable(tmp_path):
    with pytest.raises(MariaDBSourceGatewayError) as missing:
        _tls_config(tmp_path, ca_path=None)
    assert missing.value.code == "legacy_mariadb_gateway_tls_required"

    with pytest.raises(MariaDBSourceGatewayError) as relative:
        _tls_config(tmp_path, ca_path="relative-ca.pem")
    assert relative.value.code == "legacy_mariadb_gateway_tls_required"


def test_connection_error_is_stable_and_never_echoes_driver_detail(tmp_path, monkeypatch):
    detail = f"host={_HOST} user={_USER} password={_PASSWORD} database={_DATABASE}"

    def fail_connect(**_kwargs):
        raise RuntimeError(detail)

    monkeypatch.setattr(mariadb_gateway.pymysql, "connect", fail_connect)
    with pytest.raises(MariaDBSourceGatewayError) as exc_info:
        FreshPyMySQLConnectionFactory(_tls_config(tmp_path))()

    assert exc_info.value.code == "legacy_mariadb_gateway_connection_failed"
    assert detail not in str(exc_info.value)
    assert _PASSWORD not in repr(exc_info.value)


def test_password_is_passed_exactly_without_normalization(tmp_path, monkeypatch):
    supplied_password = "  caller supplied passphrase  "
    captured = []
    monkeypatch.setattr(
        mariadb_gateway.pymysql,
        "connect",
        lambda **kwargs: captured.append(kwargs) or object(),
    )

    FreshPyMySQLConnectionFactory(_tls_config(tmp_path, password=supplied_password))()

    assert captured[0]["password"] == supplied_password


def test_disabled_settings_do_not_read_any_connection_secret():
    class DisabledSettings:
        LEGACY_MARIADB_SOURCE_ATTEST_ENABLED = False

        def __getattr__(self, name):
            raise AssertionError(f"unexpected setting read: {name}")

    with pytest.raises(MariaDBSourceGatewayError) as exc_info:
        load_mariadb_source_config(DisabledSettings())

    assert exc_info.value.code == "legacy_mariadb_gateway_disabled"


def test_incomplete_settings_fail_before_factory_or_network():
    incomplete = SimpleNamespace(
        LEGACY_MARIADB_SOURCE_ATTEST_ENABLED=True,
        MANAGEMENT_COMMAND_ENVIRONMENT="production",
        LEGACY_MARIADB_SOURCE_LOCAL_DISPOSABLE=False,
    )

    with pytest.raises(MariaDBSourceGatewayError) as exc_info:
        load_mariadb_source_config(incomplete)

    assert exc_info.value.code == "legacy_mariadb_gateway_config_incomplete"


def test_settings_loader_rejects_production_plaintext_even_with_marker():
    settings_object = SimpleNamespace(
        LEGACY_MARIADB_SOURCE_ATTEST_ENABLED=True,
        MANAGEMENT_COMMAND_ENVIRONMENT="production",
        LEGACY_MARIADB_SOURCE_LOCAL_DISPOSABLE=True,
        LEGACY_MARIADB_SOURCE_HOST="127.0.0.1",
        LEGACY_MARIADB_SOURCE_PORT="43306",
        LEGACY_MARIADB_SOURCE_USER=_USER,
        LEGACY_MARIADB_SOURCE_PASSWORD=_PASSWORD,
        LEGACY_MARIADB_SOURCE_DATABASE=_DATABASE,
        LEGACY_MARIADB_SOURCE_CA_PATH="",
    )

    with pytest.raises(MariaDBSourceGatewayError) as exc_info:
        load_mariadb_source_config(settings_object)

    assert exc_info.value.code == "legacy_mariadb_gateway_local_disposable_forbidden"


def test_replace_revalidates_frozen_config(tmp_path):
    config = _tls_config(tmp_path)

    with pytest.raises(MariaDBSourceGatewayError):
        replace(config, charset="latin1")
