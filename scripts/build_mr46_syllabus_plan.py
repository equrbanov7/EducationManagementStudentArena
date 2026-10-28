#!/usr/bin/env python3
"""MR46 source-only Docker çıxarışı → 0600 JSON; heç bir hədəf DB-yə yazmır."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from apps.legacy_import.services.syllabus_migration_contracts import (  # noqa:E402
    SYLLABUS_HEADER_FIELDS,
    SYLLABUS_SECTION_CONTRACTS,
    SYLLABUS_WEEK_FIELDS,
)


def extract(container, table, fields, where):
    expression = ",".join(f"'{name}',`{name}`" for name in fields)
    sql = f"SET SESSION TRANSACTION READ ONLY; START TRANSACTION; SELECT JSON_OBJECT({expression}) FROM `{table}` WHERE {where} ORDER BY id; ROLLBACK;"
    result = subprocess.run(
        [
            "docker",
            "exec",
            "-i",
            container,
            "sh",
            "-c",
            'MYSQL_PWD="$MARIADB_ROOT_PASSWORD" exec mariadb -uroot --batch --raw --skip-column-names myedu_new',
        ],
        input=sql,
        text=True,
        capture_output=True,
    )
    if result.returncode:
        raise SystemExit("mr46_source_read_failed")
    return [json.loads(line) for line in result.stdout.splitlines()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", default="ems-legacy-delta-src")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    header = extract(args.container, "sillabus", SYLLABUS_HEADER_FIELDS.allowed_fields, "id=8891")
    journal = extract(args.container, "journals", ("id", "teacher_id", "lesson_id", "sillabus_id"), "id=15363")
    if (
        len(header) != 1
        or len(journal) != 1
        or header[0]["uniqid"] != "qVHmrlOPQd3p6Rk4UBsT"
        or journal[0]["sillabus_id"] != 8891
        or journal[0]["teacher_id"] != 442
    ):
        raise SystemExit("mr46_source_scope")
    source = header[0]
    source["week"] = extract(
        args.container, "sillabus_sem_muh", SYLLABUS_WEEK_FIELDS.allowed_fields, "uniqid='qVHmrlOPQd3p6Rk4UBsT'"
    )
    source["sections"] = {
        table: [
            [row["id"], row["name"]]
            for row in extract(args.container, table, contract.allowed_fields, "uniqid='qVHmrlOPQd3p6Rk4UBsT'")
        ]
        for table, contract in SYLLABUS_SECTION_CONTRACTS.items()
    }
    if len(source["week"]) != 23 or len(source["sections"]["sillabus_serbest_is"]) != 18:
        raise SystemExit("mr46_source_counts")
    data = dict(format="mr46-syllabus/1", source=source, source_journal=journal[0])
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2).encode()
    fd = os.open(args.out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(raw)
    print(f"mr46_source: topics=23 selfwork=18 sha256={hashlib.sha256(raw).hexdigest()}")


if __name__ == "__main__":
    main()
