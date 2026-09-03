"""Real conformance for a caller-provided disposable loopback MariaDB."""

import json
import os
import re
from io import StringIO

from django.core.management import call_command
from django.test import override_settings

import pymysql
import pytest

from apps.legacy_import.services.field_contracts import (
    STUDENT_IDENTITY_FIELDS,
    WORKER_IDENTITY_FIELDS,
)

pytestmark = pytest.mark.mariadb

_HOST = "127.0.0.1"
_ROOT_PASSWORD = "local-conformance-root-only"
_READER_USER = "legacy_attest_reader"
_READER_PASSWORD = "local-conformance-attest-reader-only"
_DATABASE_PATTERN = re.compile(r"emsarena_attest_[a-f0-9]{12}\Z")


def _guarded_endpoint():
    if os.getenv("LEGACY_MARIADB_ATTEST_DISPOSABLE_GUARD") != "local-container-only":
        pytest.skip("disposable attestation MariaDB guard is not enabled")
    database = os.getenv("LEGACY_MARIADB_ATTEST_DISPOSABLE_DATABASE", "")
    if not _DATABASE_PATTERN.fullmatch(database):
        pytest.fail("disposable attestation database name is not safely scoped")
    try:
        port = int(os.getenv("LEGACY_MARIADB_ATTEST_DISPOSABLE_PORT", ""))
    except ValueError:
        pytest.fail("disposable attestation MariaDB port is invalid")
    if port == 3306 or not 1024 <= port <= 65535:
        pytest.fail("disposable attestation MariaDB must use a non-default loopback port")
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
                "CREATE USER IF NOT EXISTS 'legacy_attest_reader'@'%' "
                "IDENTIFIED BY 'local-conformance-attest-reader-only'"
            )

            student_columns = [
                f"`{field_name}` VARCHAR(191) NULL" for field_name in STUDENT_IDENTITY_FIELDS.allowed_fields
            ]
            student_columns.extend(
                (
                    "`password` VARCHAR(191) NULL",
                    "`show_password` VARCHAR(191) NULL",
                    "PRIMARY KEY (`group_id`, `id`)",
                )
            )
            cursor.execute(f"CREATE TABLE `{database}`.`students` ({', '.join(student_columns)}) ENGINE=InnoDB")
            student_fields = (*STUDENT_IDENTITY_FIELDS.allowed_fields, "password", "show_password")
            student_insert = (
                f"INSERT INTO `{database}`.`students` "
                f"({', '.join(f'`{field}`' for field in student_fields)}) "
                f"VALUES ({', '.join(['%s'] * len(student_fields))})"
            )
            for row_id, group_id in (("2", "b"), ("1", "a"), ("3", "a")):
                values = [f"student-private-{row_id}-{position}" for position in range(len(student_fields))]
                values[0] = row_id
                values[7] = group_id
                values[-2:] = ["credential-never-output", "credential-never-output"]
                cursor.execute(student_insert, values)

            worker_fields = (*WORKER_IDENTITY_FIELDS.allowed_fields, "password", "pin_for_lock")
            worker_columns = [f"`{field_name}` VARCHAR(191) NULL" for field_name in worker_fields]
            worker_columns.append("PRIMARY KEY (`id`)")
            cursor.execute(f"CREATE TABLE `{database}`.`workers` ({', '.join(worker_columns)}) ENGINE=InnoDB")
            worker_insert = (
                f"INSERT INTO `{database}`.`workers` "
                f"({', '.join(f'`{field}`' for field in worker_fields)}) "
                f"VALUES ({', '.join(['%s'] * len(worker_fields))})"
            )
            worker_values = [f"worker-private-{position}" for position in range(len(worker_fields))]
            worker_values[0] = "worker-1"
            worker_values[-2:] = ["credential-never-output", "credential-never-output"]
            cursor.execute(worker_insert, worker_values)

            cursor.execute(f"GRANT SELECT ON `{database}`.* TO 'legacy_attest_reader'@'%'")
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
            cursor.execute("DROP USER IF EXISTS 'legacy_attest_reader'@'%'")
    finally:
        root.close()


def _reader_session_count(port):
    root = _root_connection(port)
    try:
        with root.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) FROM information_schema.PROCESSLIST WHERE USER = %s",
                (_READER_USER,),
            )
            return cursor.fetchone()[0]
    finally:
        root.close()


def test_disposable_mariadb_gateway_and_attestation_command_conformance():
    port, database = _guarded_endpoint()
    _create_fixture(port, database)
    try:
        stdout = StringIO()
        with override_settings(
            MANAGEMENT_COMMAND_ENVIRONMENT="test",
            LEGACY_MARIADB_SOURCE_ATTEST_ENABLED=True,
            LEGACY_MARIADB_SOURCE_LOCAL_DISPOSABLE=True,
            LEGACY_MARIADB_SOURCE_HOST=_HOST,
            LEGACY_MARIADB_SOURCE_PORT=port,
            LEGACY_MARIADB_SOURCE_USER=_READER_USER,
            LEGACY_MARIADB_SOURCE_PASSWORD=_READER_PASSWORD,
            LEGACY_MARIADB_SOURCE_DATABASE=database,
            LEGACY_MARIADB_SOURCE_CA_PATH="",
            LEGACY_MARIADB_SOURCE_CONNECT_TIMEOUT=5,
            LEGACY_MARIADB_SOURCE_READ_TIMEOUT=30,
            LEGACY_MARIADB_SOURCE_WRITE_TIMEOUT=10,
        ):
            call_command("legacy_import_source_attest", stdout=stdout)

        output = stdout.getvalue()
        report = json.loads(output)
        assert report["status"] == "passed"
        assert [item["projected_row_count"] for item in report["contracts"]] == [3, 1]
        assert all(item["engine"] == "InnoDB" for item in report["contracts"])
        assert all(item["credential_field_output_count"] == 0 for item in report["contracts"])
        assert _reader_session_count(port) == 0

        for forbidden in (
            _HOST,
            _READER_USER,
            _READER_PASSWORD,
            database,
            "first_name",
            "password",
            "pin_for_lock",
            "student-private",
            "worker-private",
            "credential-never-output",
        ):
            assert forbidden not in output
    finally:
        _drop_fixture(port, database)
