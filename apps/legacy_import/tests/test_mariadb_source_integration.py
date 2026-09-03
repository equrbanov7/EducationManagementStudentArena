"""Disposable MariaDB conformance test for the legacy source adapter.

The test only opts in when a caller provides a guarded random database name
and non-default loopback port. Credentials below are fixed synthetic values for
an ephemeral local container, not deployable secrets.
"""

import os
import re

import pymysql
import pytest

from apps.legacy_import.services.field_contracts import (
    STUDENT_IDENTITY_FIELDS,
    WORKER_IDENTITY_FIELDS,
)
from apps.legacy_import.services.mariadb_source import build_mariadb_source_connection_factory
from apps.legacy_import.services.source_extraction import (
    LegacySourceExtractionError,
    open_audited_identity_stream,
)

pytestmark = pytest.mark.mariadb

_HOST = "127.0.0.1"
_ROOT_PASSWORD = "local-conformance-root-only"
_READER_USER = "legacy_adapter_reader"
_READER_PASSWORD = "local-conformance-reader-only"
_DATABASE_PATTERN = re.compile(r"emsarena_adapter_[a-f0-9]{12}\Z")


def _guarded_endpoint():
    if os.getenv("LEGACY_MARIADB_DISPOSABLE_GUARD") != "local-container-only":
        pytest.skip("disposable MariaDB guard is not enabled")
    database = os.getenv("LEGACY_MARIADB_DISPOSABLE_DATABASE", "")
    if not _DATABASE_PATTERN.fullmatch(database):
        pytest.fail("disposable MariaDB database name is not safely scoped")
    try:
        port = int(os.getenv("LEGACY_MARIADB_DISPOSABLE_PORT", ""))
    except ValueError:
        pytest.fail("disposable MariaDB port is invalid")
    if port == 3306 or not 1024 <= port <= 65535:
        pytest.fail("disposable MariaDB must use a non-default loopback port")
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
    }
    if database is not None:
        kwargs["database"] = database
    return pymysql.connect(**kwargs)


def _reader_connection(port, database):
    return pymysql.connect(
        host=_HOST,
        port=port,
        user=_READER_USER,
        password=_READER_PASSWORD,
        database=database,
        charset="utf8mb4",
        connect_timeout=5,
        read_timeout=10,
        write_timeout=10,
        autocommit=False,
    )


def _create_source_fixture(port, database):
    root = _root_connection(port)
    try:
        with root.cursor() as cursor:
            cursor.execute("SET GLOBAL read_only = OFF")
            cursor.execute(f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4")
            cursor.execute(
                "CREATE USER IF NOT EXISTS 'legacy_adapter_reader'@'%' " "IDENTIFIED BY 'local-conformance-reader-only'"
            )
            columns = [f"`{field_name}` VARCHAR(191) NULL" for field_name in STUDENT_IDENTITY_FIELDS.allowed_fields]
            columns.extend(
                (
                    "`password` VARCHAR(191) NULL",
                    "`show_password` VARCHAR(191) NULL",
                    "PRIMARY KEY (`group_id`, `id`)",
                )
            )
            cursor.execute(f"CREATE TABLE `{database}`.`students` ({', '.join(columns)}) ENGINE=InnoDB")

            insert_fields = (
                *STUDENT_IDENTITY_FIELDS.allowed_fields,
                "password",
                "show_password",
            )
            insert_sql = (
                f"INSERT INTO `{database}`.`students` "
                f"({', '.join(f'`{field}`' for field in insert_fields)}) "
                f"VALUES ({', '.join(['%s'] * len(insert_fields))})"
            )
            for row_id, group_id in (("2", "b"), ("1", "a"), ("3", "a")):
                safe_values = [f"value-{row_id}-{position}" for position in range(len(insert_fields))]
                safe_values[0] = row_id
                safe_values[7] = group_id
                safe_values[-2:] = ["credential-must-not-stream", "credential-must-not-stream"]
                cursor.execute(insert_sql, safe_values)

            worker_fields = (
                *WORKER_IDENTITY_FIELDS.allowed_fields,
                "password",
                "pin_for_lock",
            )
            worker_columns = [f"`{field_name}` VARCHAR(191) NULL" for field_name in worker_fields]
            worker_columns.append("PRIMARY KEY (`id`)")
            cursor.execute(f"CREATE TABLE `{database}`.`workers` ({', '.join(worker_columns)}) ENGINE=InnoDB")
            worker_insert = (
                f"INSERT INTO `{database}`.`workers` "
                f"({', '.join(f'`{field}`' for field in worker_fields)}) "
                f"VALUES ({', '.join(['%s'] * len(worker_fields))})"
            )
            worker_values = [f"worker-{position}" for position in range(len(worker_fields))]
            worker_values[0] = "worker-1"
            worker_values[-2:] = ["credential-must-not-stream", "credential-must-not-stream"]
            cursor.execute(worker_insert, worker_values)

            cursor.execute(f"GRANT SELECT ON `{database}`.* TO 'legacy_adapter_reader'@'%'")
            cursor.execute("FLUSH PRIVILEGES")
    finally:
        root.close()


def _drop_source_fixture(port, database):
    root = _root_connection(port)
    try:
        with root.cursor() as cursor:
            cursor.execute("SET GLOBAL read_only = OFF")
            cursor.execute(f"DROP DATABASE IF EXISTS `{database}`")
            cursor.execute("DROP USER IF EXISTS 'legacy_adapter_reader'@'%'")
    finally:
        root.close()


def test_disposable_mariadb_read_only_snapshot_schema_and_streaming_conformance():
    port, database = _guarded_endpoint()
    _create_source_fixture(port, database)
    try:
        # The adapter must reject a writable primary before any schema read.
        writable_raw = _reader_connection(port, database)
        writable_factory = build_mariadb_source_connection_factory(lambda: writable_raw)
        with pytest.raises(LegacySourceExtractionError) as exc_info:
            with open_audited_identity_stream(
                connection_factory=writable_factory,
                contract=STUDENT_IDENTITY_FIELDS,
            ):
                pass
        assert exc_info.value.code == "legacy_source_server_not_read_only"

        root = _root_connection(port)
        try:
            with root.cursor() as cursor:
                cursor.execute("SET GLOBAL read_only = ON")
        finally:
            root.close()

        raw_connections = []

        def fresh_reader():
            connection = _reader_connection(port, database)
            raw_connections.append(connection)
            return connection

        factory = build_mariadb_source_connection_factory(fresh_reader)
        with open_audited_identity_stream(
            connection_factory=factory,
            contract=STUDENT_IDENTITY_FIELDS,
            chunk_size=2,
        ) as stream:
            rows = [row.to_transform_dict() for row in stream]

        assert [(row["group_id"], row["id"]) for row in rows] == [
            ("a", "1"),
            ("a", "3"),
            ("b", "2"),
        ]
        assert all("password" not in row for row in rows)
        assert all(connection.open is False for connection in raw_connections)

        with open_audited_identity_stream(
            connection_factory=factory,
            contract=WORKER_IDENTITY_FIELDS,
            chunk_size=2,
        ) as stream:
            worker_rows = [row.to_transform_dict() for row in stream]
        assert [row["id"] for row in worker_rows] == ["worker-1"]
        assert all("password" not in row and "pin_for_lock" not in row for row in worker_rows)

        # Early exit over a real SSCursor must close the connection promptly.
        with open_audited_identity_stream(
            connection_factory=factory,
            contract=STUDENT_IDENTITY_FIELDS,
            chunk_size=1,
        ) as stream:
            assert next(stream)["id"] == "1"
        assert raw_connections[-1].open is False
    finally:
        _drop_source_fixture(port, database)
