"""Secure, explicit PyMySQL gateway for the audited legacy source adapter."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pymysql

from .mariadb_source import build_mariadb_source_connection_factory

_LOCAL_MODES = frozenset({"local", "test"})
_DEFAULT_MYSQL_PORT = 3306
_MIN_DISPOSABLE_PORT = 1024
_MAX_PORT = 65535
_MAX_TIMEOUT_SECONDS = 300


class MariaDBSourceGatewayError(Exception):
    """Sanitized gateway failure containing only a stable code."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _valid_text(value: object, *, maximum: int) -> bool:
    return (
        type(value) is str
        and 0 < len(value) <= maximum
        and value == value.strip()
        and all(character.isprintable() and character not in "\r\n\x00" for character in value)
    )


def _valid_timeout(value: object) -> bool:
    return type(value) is int and 1 <= value <= _MAX_TIMEOUT_SECONDS


def _valid_secret(value: object) -> bool:
    return type(value) is str and 0 < len(value) <= 4096 and not any(marker in value for marker in ("\r", "\n", "\x00"))


def _is_literal_loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@dataclass(frozen=True, repr=False, eq=False)
class MariaDBSourceConfig:
    """Immutable caller-supplied connection policy; never parses a DSN/env."""

    host: str
    port: int
    user: str
    password: str
    database: str
    ca_path: str | None
    deployment_mode: str
    local_disposable: bool
    connect_timeout: int
    read_timeout: int
    write_timeout: int
    charset: str

    def __post_init__(self) -> None:
        if not _valid_text(self.host, maximum=253):
            raise MariaDBSourceGatewayError("legacy_mariadb_gateway_config_invalid")
        if type(self.port) is not int or not 1 <= self.port <= _MAX_PORT:
            raise MariaDBSourceGatewayError("legacy_mariadb_gateway_config_invalid")
        if not _valid_text(self.user, maximum=128):
            raise MariaDBSourceGatewayError("legacy_mariadb_gateway_config_invalid")
        if not _valid_secret(self.password):
            raise MariaDBSourceGatewayError("legacy_mariadb_gateway_config_invalid")
        if not _valid_text(self.database, maximum=64):
            raise MariaDBSourceGatewayError("legacy_mariadb_gateway_config_invalid")
        if not _valid_text(self.deployment_mode, maximum=32):
            raise MariaDBSourceGatewayError("legacy_mariadb_gateway_config_invalid")
        if type(self.local_disposable) is not bool:
            raise MariaDBSourceGatewayError("legacy_mariadb_gateway_config_invalid")
        if not all(
            _valid_timeout(timeout) for timeout in (self.connect_timeout, self.read_timeout, self.write_timeout)
        ):
            raise MariaDBSourceGatewayError("legacy_mariadb_gateway_config_invalid")
        if self.charset != "utf8mb4":
            raise MariaDBSourceGatewayError("legacy_mariadb_gateway_config_invalid")

        if self.local_disposable:
            if self.deployment_mode.casefold() not in _LOCAL_MODES:
                raise MariaDBSourceGatewayError("legacy_mariadb_gateway_local_disposable_forbidden")
            if (
                not _is_literal_loopback(self.host)
                or self.port == _DEFAULT_MYSQL_PORT
                or self.port < _MIN_DISPOSABLE_PORT
                or self.ca_path is not None
            ):
                raise MariaDBSourceGatewayError("legacy_mariadb_gateway_local_disposable_forbidden")
            return

        if not _valid_text(self.ca_path, maximum=4096):
            raise MariaDBSourceGatewayError("legacy_mariadb_gateway_tls_required")
        ca_path = Path(self.ca_path)
        if not ca_path.is_absolute() or not ca_path.is_file():
            raise MariaDBSourceGatewayError("legacy_mariadb_gateway_tls_required")

    def __repr__(self) -> str:
        tls_policy = "local-disposable-plaintext" if self.local_disposable else "verified-tls"
        return f"MariaDBSourceConfig(tls_policy={tls_policy!r}, charset='utf8mb4')"

    def to_safe_log_dict(self) -> dict[str, object]:
        return {
            "autocommit": False,
            "charset": "utf8mb4",
            "tls_policy": "local-disposable-plaintext" if self.local_disposable else "verified-tls",
            "validation_result": "passed",
        }


class FreshPyMySQLConnectionFactory:
    """Zero-argument callable that creates a fresh bounded connection."""

    def __init__(self, config: MariaDBSourceConfig) -> None:
        if not isinstance(config, MariaDBSourceConfig):
            raise MariaDBSourceGatewayError("legacy_mariadb_gateway_config_invalid")
        self._config = config

    def __repr__(self) -> str:
        return "FreshPyMySQLConnectionFactory()"

    def __call__(self) -> Any:
        config = self._config
        kwargs: dict[str, object] = {
            "host": config.host,
            "port": config.port,
            "user": config.user,
            "password": config.password,
            "database": config.database,
            "charset": config.charset,
            "connect_timeout": config.connect_timeout,
            "read_timeout": config.read_timeout,
            "write_timeout": config.write_timeout,
            "autocommit": False,
            "client_flag": 0,
            "local_infile": False,
            "defer_connect": False,
        }
        if config.local_disposable:
            kwargs["ssl_disabled"] = True
        else:
            kwargs.update(
                {
                    "ssl_ca": config.ca_path,
                    "ssl_disabled": False,
                    "ssl_verify_cert": True,
                    "ssl_verify_identity": True,
                }
            )
        try:
            return pymysql.connect(**kwargs)
        except Exception:
            raise MariaDBSourceGatewayError("legacy_mariadb_gateway_connection_failed") from None


def build_configured_mariadb_source_factory(config: MariaDBSourceConfig):
    """Build the existing audited adapter around a fresh raw connection."""

    raw_factory = FreshPyMySQLConnectionFactory(config)
    return build_mariadb_source_connection_factory(raw_factory)


def _setting(settings_object: object, name: str) -> object:
    try:
        return getattr(settings_object, name)
    except Exception:
        raise MariaDBSourceGatewayError("legacy_mariadb_gateway_config_incomplete") from None


def _setting_int(settings_object: object, name: str, default: int | None = None) -> int:
    try:
        raw = getattr(settings_object, name) if default is None else getattr(settings_object, name, default)
        if type(raw) is int:
            return raw
        if type(raw) is str and raw.isascii() and raw.isdecimal():
            return int(raw, 10)
    except Exception:
        pass
    raise MariaDBSourceGatewayError("legacy_mariadb_gateway_config_incomplete")


def load_mariadb_source_config(settings_object: object) -> MariaDBSourceConfig:
    """Read opt-in Django settings without inspecting secrets when disabled."""

    try:
        enabled = getattr(settings_object, "LEGACY_MARIADB_SOURCE_ATTEST_ENABLED", False)
    except Exception:
        enabled = False
    if enabled is not True:
        raise MariaDBSourceGatewayError("legacy_mariadb_gateway_disabled")

    ca_path = getattr(settings_object, "LEGACY_MARIADB_SOURCE_CA_PATH", None)
    if ca_path == "":
        ca_path = None
    try:
        return MariaDBSourceConfig(
            host=_setting(settings_object, "LEGACY_MARIADB_SOURCE_HOST"),
            port=_setting_int(settings_object, "LEGACY_MARIADB_SOURCE_PORT"),
            user=_setting(settings_object, "LEGACY_MARIADB_SOURCE_USER"),
            password=_setting(settings_object, "LEGACY_MARIADB_SOURCE_PASSWORD"),
            database=_setting(settings_object, "LEGACY_MARIADB_SOURCE_DATABASE"),
            ca_path=ca_path,
            deployment_mode=getattr(settings_object, "MANAGEMENT_COMMAND_ENVIRONMENT", "production"),
            local_disposable=getattr(settings_object, "LEGACY_MARIADB_SOURCE_LOCAL_DISPOSABLE", False),
            connect_timeout=_setting_int(settings_object, "LEGACY_MARIADB_SOURCE_CONNECT_TIMEOUT", 5),
            read_timeout=_setting_int(settings_object, "LEGACY_MARIADB_SOURCE_READ_TIMEOUT", 60),
            write_timeout=_setting_int(settings_object, "LEGACY_MARIADB_SOURCE_WRITE_TIMEOUT", 10),
            charset="utf8mb4",
        )
    except MariaDBSourceGatewayError:
        raise
    except Exception:
        raise MariaDBSourceGatewayError("legacy_mariadb_gateway_config_incomplete") from None
