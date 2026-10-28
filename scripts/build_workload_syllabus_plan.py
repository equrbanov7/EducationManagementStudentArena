#!/usr/bin/env python3
"""Bilalın mənbə sillabusunu read-only çıxar; digər müəlliflərə plan yaratmır."""

import argparse
import hashlib
import json
import os

from build_mr46_syllabus_plan import SYLLABUS_HEADER_FIELDS, SYLLABUS_SECTION_CONTRACTS, SYLLABUS_WEEK_FIELDS, extract


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--container", default="ems-legacy-delta-src")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    source = extract(args.container, "sillabus", SYLLABUS_HEADER_FIELDS.allowed_fields, "id=8430")
    journal = extract(args.container, "journals", ("id", "teacher_id", "lesson_id", "sillabus_id"), "id=14080")
    if len(source) != 1 or len(journal) != 1 or journal[0]["teacher_id"] != 679 or journal[0]["sillabus_id"] != 8430:
        raise SystemExit("workload_syllabus_source_scope")
    source = source[0]
    if source["uniqid"] != "WaccQbauu5QCDnYunfZL":
        raise SystemExit("workload_syllabus_source_scope")
    where = "uniqid='WaccQbauu5QCDnYunfZL'"
    source["week"] = extract(args.container, "sillabus_sem_muh", SYLLABUS_WEEK_FIELDS.allowed_fields, where)
    source["sections"] = {
        table: [[row["id"], row["name"]] for row in extract(args.container, table, contract.allowed_fields, where)]
        for table, contract in SYLLABUS_SECTION_CONTRACTS.items()
    }
    data = dict(format="workload-syllabi/1", source=source, source_journal=journal[0])
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2).encode()
    fd = os.open(args.out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
    print(f"workload_syllabus_source: topics={len(source['week'])} sha256={hashlib.sha256(raw).hexdigest()}")


if __name__ == "__main__":
    main()
