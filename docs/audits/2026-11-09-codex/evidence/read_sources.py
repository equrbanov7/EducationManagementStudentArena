"""Audit evidence helper: read-only legacy transactions, no application setup.

Run with the existing repository venv and PYTHONDONTWRITEBYTECODE=1.
Credentials stay in memory and are read from the named existing container.
No production/clone connector is enabled until its provenance is established.
"""

import json
import subprocess
from contextlib import contextmanager

import pymysql

LEGACY_CONTAINER = "ems-legacy-delta-src"
LEGACY_SCHEMA = "myedu_new"


def container_metadata(name):
    result = subprocess.run(["docker", "inspect", name], capture_output=True, check=True, text=True)
    return json.loads(result.stdout)[0]


@contextmanager
def legacy():
    metadata = container_metadata(LEGACY_CONTAINER)
    if not metadata["State"]["Running"]:
        raise RuntimeError("legacy_container_not_running")
    environment = dict(value.split("=", 1) for value in metadata["Config"]["Env"] if "=" in value)
    password = environment.get("MARIADB_ROOT_PASSWORD") or environment.get("MYSQL_ROOT_PASSWORD")
    if not password:
        raise RuntimeError("legacy_credential_unavailable")
    connection = pymysql.connect(
        host="127.0.0.1",
        port=50330,
        user="root",
        password=password,
        database=LEGACY_SCHEMA,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
        connect_timeout=5,
        read_timeout=90,
        write_timeout=10,
        local_infile=False,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET SESSION TRANSACTION ISOLATION LEVEL REPEATABLE READ")
            cursor.execute("SET SESSION TRANSACTION READ ONLY")
            cursor.execute("START TRANSACTION WITH CONSISTENT SNAPSHOT")
            cursor.execute("SELECT @@tx_read_only AS readonly")
            if cursor.fetchone()["readonly"] != 1:
                raise RuntimeError("legacy_read_only_required")
        yield connection
    finally:
        connection.rollback()
        connection.close()


def select(connection, sql, parameters=()):
    if not sql.lstrip().upper().startswith(("SELECT ", "WITH ", "SHOW ")):
        raise ValueError("select_query_required")
    with connection.cursor() as cursor:
        cursor.execute(sql, parameters)
        return cursor.fetchall()
