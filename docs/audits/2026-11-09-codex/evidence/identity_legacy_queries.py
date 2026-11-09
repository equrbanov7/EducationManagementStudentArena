"""Reproducible source-only identity checks; never emits identity text or FİN."""

import json
import re
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from read_sources import legacy, select

HERE = Path(__file__).resolve().parent
QUERIES = {
    "students": "SELECT id,first_name,last_name,father_name,fincode,birthday,group_id,azadedildi FROM students",
    "workers": "SELECT id,first_name,last_name,father_name,birthday,last_login_time,kollec_or_uni FROM workers",
    "groups": "SELECT id,kollec_or_uni FROM groups",
    "journal_activity": "SELECT teacher_id,COUNT(*) AS journals FROM journals WHERE semestr=14 AND fake=0 GROUP BY teacher_id",
    "student_activity": "SELECT p.student_id,COUNT(*) AS cells,COUNT(DISTINCT p.journal_uniqid) AS journals FROM journals_dates_points p WHERE EXISTS (SELECT 1 FROM journals j WHERE j.uniqid=p.journal_uniqid AND j.semestr=14 AND j.fake=0) GROUP BY p.student_id",
}


def normalized(value):
    text = unicodedata.normalize("NFKC", str(value or "")).replace("İ", "i").casefold()
    return " ".join(text.split())


def name_key(row):
    parts = tuple(normalized(row.get(key)) for key in ("last_name", "first_name", "father_name"))
    return parts if all(parts) else None


def birth_key(value):
    text = str(value or "").strip()
    for pattern in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, pattern).date().isoformat()
        except ValueError:
            pass
    return None


def grouped(rows, key):
    buckets = defaultdict(list)
    for row in rows:
        value = key(row)
        if value:
            buckets[value].append(row)
    return [members for members in buckets.values() if len(members) > 1]


def write(name, value):
    (HERE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def main():
    with legacy() as connection:
        rows = {key: select(connection, sql) for key, sql in QUERIES.items()}
        source = select(
            connection, "SELECT DATABASE() AS schema_name,CURRENT_USER() AS role_name,@@tx_read_only AS readonly"
        )[0]
    group_scope = {row["id"]: row["kollec_or_uni"] for row in rows["groups"]}
    students = [row for row in rows["students"] if group_scope.get(row["group_id"]) == "University"]
    workers = [row for row in rows["workers"] if row["kollec_or_uni"] == "University"]
    student_activity = {row["student_id"]: row for row in rows["student_activity"]}
    worker_activity = {row["teacher_id"]: row["journals"] for row in rows["journal_activity"]}

    def fin(row):
        value = re.sub(r"\s+", "", str(row.get("fincode") or "")).upper()
        return value if re.fullmatch(r"[A-Z0-9]{7}", value) and len(set(value)) > 1 else None

    def full_birth(row):
        name, birth = name_key(row), birth_key(row.get("birthday"))
        return (name, birth) if name and birth else None

    def student_case(members):
        return {
            "legacy_student_ids": sorted(row["id"] for row in members),
            "nonexpelled_ids": sorted(row["id"] for row in members if row["azadedildi"] == 0),
            "distinct_full_name_keys": len({name_key(row) for row in members if name_key(row)}),
            "distinct_valid_birth_dates": len(
                {birth_key(row["birthday"]) for row in members if birth_key(row["birthday"])}
            ),
            "group_ids": sorted({row["group_id"] for row in members}),
            "source_activity": [
                {
                    "legacy_student_id": row["id"],
                    "journals": student_activity.get(row["id"], {}).get("journals", 0),
                    "cells": student_activity.get(row["id"], {}).get("cells", 0),
                }
                for row in sorted(members, key=lambda item: item["id"])
            ],
            "current_ems_identity_verified": False,
            "keeper_recommendation": None,
        }

    def worker_case(members):
        return {
            "legacy_worker_ids": sorted(row["id"] for row in members),
            "source_activity": [
                {
                    "legacy_worker_id": row["id"],
                    "semester14_journals": worker_activity.get(row["id"], 0),
                    "has_source_login": bool(row["last_login_time"]),
                }
                for row in sorted(members, key=lambda item: item["id"])
            ],
            "current_ems_identity_verified": False,
            "keeper_recommendation": None,
        }

    findings = {
        "student_same_fin": [student_case(members) for members in grouped(students, fin)],
        "student_same_full_name_birth": [student_case(members) for members in grouped(students, full_birth)],
        "student_same_full_name": [student_case(members) for members in grouped(students, name_key)],
        "worker_same_full_name_birth": [worker_case(members) for members in grouped(workers, full_birth)],
        "worker_same_full_name": [worker_case(members) for members in grouped(workers, name_key)],
    }
    result = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "scope": "Legacy University only; source duplicates are candidates, not current EMS defects",
        "population": {
            "students_all_source": len(rows["students"]),
            "students_university": len(students),
            "students_university_nonexpelled": sum(row["azadedildi"] == 0 for row in students),
            "students_unknown_group": sum(row["group_id"] not in group_scope for row in rows["students"]),
            "workers_all_source": len(rows["workers"]),
            "workers_university": len(workers),
            "student_fin_valid_shape": sum(fin(row) is not None for row in students),
            "student_birthday_parseable": sum(birth_key(row["birthday"]) is not None for row in students),
        },
        "candidate_groups": {key: len(value) for key, value in findings.items()},
        "candidate_rows": {
            key: sum(len(row.get("legacy_student_ids", row.get("legacy_worker_ids", []))) for row in value)
            for key, value in findings.items()
        },
        "warning": "Categories overlap. Names and birthdays alone do not authorize account merge. Current EMS mappings, login and repair history are required.",
        "findings": findings,
    }
    write("identity_legacy_findings.json", result)
    write("identity_query_catalog.json", QUERIES)
    print(json.dumps({"population": result["population"], "candidate_groups": result["candidate_groups"]}))


if __name__ == "__main__":
    main()
