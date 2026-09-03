"""Real disposable MariaDB conformance for registry-bound PK inventory."""

import json
import os
import re

import pymysql
import pytest

from apps.legacy_import.services.mariadb_gateway import (
    MariaDBSourceConfig,
    build_configured_mariadb_source_factory,
)
from apps.legacy_import.services.pk_inventory import (
    LegacyPKInventoryError,
    inventory_registered_pk_table,
)
from apps.legacy_import.services.pk_inventory_contracts import MAX_LEDGER_PRIMARY_KEY
from apps.legacy_import.services.table_plan import load_legacy_table_plan

pytestmark = pytest.mark.mariadb

_HOST = "127.0.0.1"
_ROOT_PASSWORD = "local-pk-conformance-root-only"
_READER_USER = "legacy_pk_reader"
_READER_PASSWORD = "local-pk-conformance-reader-only"
_DATABASE_PATTERN = re.compile(r"emsarena_pk_[a-f0-9]{12}\Z")


def _guarded_endpoint():
    if os.getenv("LEGACY_MARIADB_PK_DISPOSABLE_GUARD") != "local-container-only":
        pytest.skip("disposable PK inventory MariaDB guard is not enabled")
    database = os.getenv("LEGACY_MARIADB_PK_DISPOSABLE_DATABASE", "")
    if not _DATABASE_PATTERN.fullmatch(database):
        pytest.fail("disposable PK inventory database name is not safely scoped")
    try:
        port = int(os.getenv("LEGACY_MARIADB_PK_DISPOSABLE_PORT", ""))
    except ValueError:
        pytest.fail("disposable PK inventory MariaDB port is invalid")
    if port == 3306 or not 1024 <= port <= 65535:
        pytest.fail("disposable PK inventory MariaDB must use a non-default loopback port")
    return port, database


def _root_connection(port, database=None):
    kwargs = {
        "host": _HOST,
        "port": port,
        "user": "root",
        "password": _ROOT_PASSWORD,
        "charset": "utf8mb4",
        "connect_timeout": 5,
        "read_timeout": 10,
        "write_timeout": 10,
        "autocommit": True,
        "ssl_disabled": True,
    }
    if database is not None:
        kwargs["database"] = database
    return pymysql.connect(**kwargs)


def _create_fixture(port, database):
    root = _root_connection(port)
    try:
        with root.cursor() as cursor:
            cursor.execute("SET GLOBAL read_only = OFF")
            cursor.execute(f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4")
            cursor.execute(
                "CREATE USER IF NOT EXISTS 'legacy_pk_reader'@'%' " "IDENTIFIED BY 'local-pk-conformance-reader-only'"
            )
            cursor.execute(
                f"CREATE TABLE `{database}`.`curricula_tasks_content` ("
                "`private_pk` BIGINT NOT NULL, `password` VARCHAR(100), "
                "`private_payload` VARCHAR(100), PRIMARY KEY (`private_pk`)) ENGINE=InnoDB"
            )
            cursor.executemany(
                f"INSERT INTO `{database}`.`curricula_tasks_content` "
                "(`private_pk`, `password`, `private_payload`) VALUES (%s, %s, %s)",
                [(value, "credential-never-output", f"pii-never-output-{value}") for value in (1, 3, 10, 11, 99)],
            )
            cursor.execute(
                f"CREATE TABLE `{database}`.`curricula_tasks` ("
                "`private_pk` BIGINT NOT NULL, PRIMARY KEY (`private_pk`)) ENGINE=InnoDB"
            )
            cursor.execute(f"INSERT INTO `{database}`.`curricula_tasks` (`private_pk`) VALUES (0)")
            cursor.execute(
                f"CREATE TABLE `{database}`.`curricula_plan_patok` ("
                "`private_pk` BIGINT UNSIGNED NOT NULL, PRIMARY KEY (`private_pk`)) ENGINE=InnoDB"
            )
            cursor.execute(
                f"INSERT INTO `{database}`.`curricula_plan_patok` (`private_pk`) VALUES (%s)",
                (MAX_LEDGER_PRIMARY_KEY + 1,),
            )
            cursor.execute(f"GRANT SELECT ON `{database}`.* TO 'legacy_pk_reader'@'%'")
            cursor.execute("FLUSH PRIVILEGES")
            cursor.execute("SET GLOBAL read_only = ON")
    finally:
        root.close()


def _drop_fixture(port, database):
    root = _root_connection(port)
    try:
        with root.cursor() as cursor:
            cursor.execute("SET GLOBAL read_only = OFF")
            cursor.execute(f"DROP DATABASE IF EXISTS `{database}`")
            cursor.execute("DROP USER IF EXISTS 'legacy_pk_reader'@'%'")
    finally:
        root.close()


def _factory(port, database):
    config = MariaDBSourceConfig(
        host=_HOST,
        port=port,
        user=_READER_USER,
        password=_READER_PASSWORD,
        database=database,
        ca_path=None,
        deployment_mode="test",
        local_disposable=True,
        connect_timeout=5,
        read_timeout=30,
        write_timeout=10,
        charset="utf8mb4",
    )
    return build_configured_mariadb_source_factory(config)


def _attested_connection(factory):
    connection = factory()
    assert connection.server_is_read_only() is True
    connection.begin_read_only_snapshot()
    assert connection.session_is_read_only() is True
    return connection


def _cleanup(connection):
    connection.rollback()
    connection.close()


def _global_read_only_and_reader_sessions(port):
    root = _root_connection(port)
    try:
        with root.cursor() as cursor:
            cursor.execute("SELECT @@GLOBAL.read_only")
            read_only = cursor.fetchone()[0]
            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.PROCESSLIST WHERE USER = %s",
                (_READER_USER,),
            )
            sessions = cursor.fetchone()[0]
            return read_only, sessions
    finally:
        root.close()


def test_disposable_mariadb_pk_inventory_keyset_bounds_and_cleanup_conformance():
    port, database = _guarded_endpoint()
    _create_fixture(port, database)
    plan = load_legacy_table_plan()
    factory = _factory(port, database)
    try:
        connection = _attested_connection(factory)
        try:
            entry = plan.entry_for("curricula_tasks_content")
            state, metadata = inventory_registered_pk_table(
                connection=connection,
                plan=plan,
                entry=entry,
                batch_size=2,
            )
        finally:
            _cleanup(connection)

        safe_result = json.dumps(
            {
                "after_pk": state.after_pk,
                "digest": state.ordered_pk_digest,
                "maximum_pk": state.maximum_pk,
                "minimum_pk": state.minimum_pk,
                "observed_rows": state.observed_rows,
                "pk_fingerprint": metadata.primary_key_fingerprint,
                "sequence": state.sequence,
            },
            sort_keys=True,
        )
        assert state.observed_rows == 5
        assert (state.minimum_pk, state.maximum_pk, state.sequence) == (1, 99, 3)
        assert metadata.primary_key_data_type == "bigint"

        for table_name, expected_code in (
            ("curricula_tasks", "legacy_pk_inventory_pk_nonpositive"),
            ("curricula_plan_patok", "legacy_pk_inventory_pk_out_of_range"),
        ):
            connection = _attested_connection(factory)
            try:
                with pytest.raises(LegacyPKInventoryError) as exc_info:
                    inventory_registered_pk_table(
                        connection=connection,
                        plan=plan,
                        entry=plan.entry_for(table_name),
                        batch_size=2,
                    )
                assert exc_info.value.code == expected_code
            finally:
                _cleanup(connection)

        assert _global_read_only_and_reader_sessions(port) == (1, 0)
        for forbidden in (
            _HOST,
            _READER_USER,
            _READER_PASSWORD,
            database,
            "private_pk",
            "password",
            "private_payload",
            "credential-never-output",
            "pii-never-output",
        ):
            assert forbidden not in safe_result
    finally:
        _drop_fixture(port, database)
