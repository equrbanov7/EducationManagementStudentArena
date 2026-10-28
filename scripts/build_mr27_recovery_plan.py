#!/usr/bin/env python3
"""Yalnız MR27 mənbə proyeksiyası; READ ONLY Docker MariaDB → 0600 JSON. Credential çap olunmur."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from apps.legacy_import.services.field_contracts import (  # noqa: E402
    GROUP_STRUCTURE_FIELDS,
    SPECIALITY_STRUCTURE_FIELDS,
    STUDENT_IDENTITY_FIELDS,
)
from apps.legacy_import.services.mr27_plan import POINTS, validate  # noqa: E402


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
        raise SystemExit("mr27_source_read_failed")
    return [json.loads(line) for line in result.stdout.splitlines()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", default="ems-legacy-delta-src")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    specialty = extract(args.container, "speciality", SPECIALITY_STRUCTURE_FIELDS.allowed_fields, "id=103")
    groups = extract(args.container, "groups", GROUP_STRUCTURE_FIELDS.allowed_fields, "id=902")
    students = extract(args.container, "students", STUDENT_IDENTITY_FIELDS.allowed_fields, "id IN (10127,10128)")
    points = extract(
        args.container,
        "journals_dates_points",
        (
            "id",
            "journal_uniqid",
            "month_id",
            "day_number",
            "student_id",
            "time",
            "point",
            "sem_muh",
            "lab",
            "excusable",
        ),
        "id IN (" + ",".join(str(pk) for ids in POINTS.values() for pk in ids) + ")",
    )
    marks = []
    for row in points:
        if row["journal_uniqid"] != "bb0eC9HWWY" or row["lab"] or row["excusable"]:
            raise SystemExit("mr27_source_cell_scope")
        token = row["point"]
        marks.append(
            dict(
                source_point_id=row["id"],
                legacy_student_id=row["student_id"],
                date=f'2026-{int(row["month_id"]):02d}-{int(row["day_number"]):02d}',
                time=row["time"],
                kind="lecture" if row["sem_muh"] == 1 else "seminar",
                status="absent" if token == "qb" else "present",
                score=int(token) if token.isdigit() else None,
            )
        )
    if len(specialty) != 1 or len(groups) != 1:
        raise SystemExit("mr27_source_structure_scope")
    data = dict(format="mr27-recovery/1", speciality=specialty[0], group=groups[0], students=students, marks=marks)
    validate(data)
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2).encode()
    fd = os.open(args.out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as handle:
        handle.write(raw)
    print(f"mr27_source: students=2 points=21 sha256={hashlib.sha256(raw).hexdigest()}")


if __name__ == "__main__":
    main()
