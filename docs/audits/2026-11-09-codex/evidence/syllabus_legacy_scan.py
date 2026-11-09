"""SELECT-only legacy syllabus evidence. Persist IDs/counts/statuses/hashes, never body text."""

import hashlib
import html
import importlib
import json
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from read_sources import legacy, select

OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OUT.parents[3]))
subject_key = importlib.import_module("apps.legacy_import.services.delta.resolve").subject_key
SATELLITES = (
    "sillabus_serbest_is",
    "sillabus_imtahan_suallari",
    "sillabus_derslikler",
    "sillabus_elmi_maraq",
    "sillabus_certificates",
    "sillabus_eldeolunacaq_tecrubeler",
    "sillabus_dersin_islenme_formasi",
    "sillabus_yoxlama_formasi",
    "sillabus_tesviri_ve_meqsedi",
    "sillabus_qarsilama_mesaji",
)
HOURS = {"lecture": "muh_saat", "seminar": "sem_saat", "practical": "praktiki_saat", "lab": "lab_saat"}


def digest(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def name_key(value):
    return " ".join(unicodedata.normalize("NFKC", html.unescape(value or "")).casefold().split())


def hour(value):
    raw = str(value or "").strip()
    if not raw:
        return Decimal(0), None
    try:
        number = Decimal(raw)
        if not number.is_finite() or number < 0:
            return None, "invalid"
        return number, "fractional" if number % 1 else None
    except InvalidOperation:
        return None, "invalid"


def read_by_uniqid(conn, table, fields, ids):
    rows = []
    for offset in range(0, len(ids), 400):
        part = ids[offset : offset + 400]
        rows.extend(
            select(
                conn, f"SELECT {fields} FROM {table} WHERE uniqid IN ({','.join(['%s'] * len(part))}) ORDER BY id", part
            )
        )
    return rows


def run():
    started = datetime.now(timezone.utc).isoformat()
    with legacy() as conn:
        database = select(
            conn, "SELECT DATABASE() AS db, CURRENT_USER() AS role, @@tx_read_only AS readonly, @@version AS version"
        )[0]
        journals = select(
            conn,
            "SELECT id,uniqid,lesson_id,teacher_id,groups_id,sillabus_id,semestr,fake,sonra_sil,active,fenn_saati FROM journals WHERE semestr=14 ORDER BY id",
        )
        journal_dates = select(
            conn, "SELECT MIN(added_date) AS first_added,MAX(added_date) AS last_added FROM journals WHERE semestr=14"
        )[0]
        group_scopes = {
            row["id"]: row["kollec_or_uni"] for row in select(conn, "SELECT id,kollec_or_uni FROM groups ORDER BY id")
        }
        headers = select(
            conn, "SELECT id,uniqid,lesson_id,teacher_id,ders_saati,language,active FROM sillabus ORDER BY id"
        )
        lessons = select(conn, "SELECT id,name FROM lessons ORDER BY id")
        workers = {row["id"] for row in select(conn, "SELECT id FROM workers ORDER BY id")}
        names = {row["id"]: subject_key(row["name"]) for row in lessons}
        uniqid_counts = Counter(row["uniqid"] for row in headers)
        referenced = {row["sillabus_id"] for row in journals if row["sillabus_id"]}
        plan = json.loads((OUT / "syllabus_source_plan_inventory.json").read_text())["legacy_recovery_plan"]
        plan_source_ids = {int(key) for key in plan["sources"]}
        reference_headers = [row for row in headers if row["id"] in referenced | plan_source_ids]
        uniqids = sorted({row["uniqid"] for row in reference_headers if row["uniqid"]})
        weeks = defaultdict(list)
        for row in read_by_uniqid(
            conn, "sillabus_sem_muh", "id,uniqid,movzu,muh_saat,sem_saat,praktiki_saat,lab_saat,qeyd", uniqids
        ):
            weeks[row["uniqid"]].append(row)
        sections = defaultdict(lambda: defaultdict(list))
        table_counts = {"sillabus": len(headers)}
        table_counts["sillabus_sem_muh"] = select(conn, "SELECT count(*) AS n FROM sillabus_sem_muh")[0]["n"]
        for table in SATELLITES:
            table_counts[table] = select(conn, f"SELECT count(*) AS n FROM {table}")[0]["n"]
            for row in read_by_uniqid(conn, table, "id,uniqid,name", uniqids):
                sections[row["uniqid"]][table].append(row)

    source_rows = []
    source_map = {}
    for header in reference_headers:
        key = header["uniqid"]
        week = weeks[key]
        sums, issues = {}, []
        for kind, column in HOURS.items():
            total = Decimal(0)
            for row in week:
                number, issue = hour(row[column])
                if issue:
                    issues.append(
                        {"row_id": row["id"], "kind": kind, "issue": issue, "value_sha256": digest(row[column])}
                    )
                if number is not None:
                    total += number
            sums[kind] = str(total)
        header_hours, header_issue = hour(header["ders_saati"])
        data = {
            "legacy_syllabus_id": header["id"],
            "uniqid": key,
            "referenced_by_semester14": header["id"] in referenced,
            "referenced_by_recovery_plan": header["id"] in plan_source_ids,
            "subject_id": header["lesson_id"],
            "teacher_id": header["teacher_id"],
            "active": header["active"],
            "language_sha256": digest(header["language"]),
            "header_sha256": digest(header),
            "teacher_exists": header["teacher_id"] in workers,
            "subject_exists": header["lesson_id"] in names,
            "uniqid_header_count": uniqid_counts[key],
            "header_hours": str(header_hours) if header_hours is not None else None,
            "header_hours_issue": header_issue,
            "weekly_rows": len(week),
            "nonblank_weekly_topics": sum(bool(name_key(row["movzu"])) for row in week),
            "weekly_hours": sums,
            "weekly_total": str(sum(Decimal(v) for v in sums.values())),
            "hour_cell_issues": issues,
            "weekly_sha256": digest(week),
            "section_counts": {table: len(sections[key][table]) for table in SATELLITES},
            "section_sha256": {table: digest(sections[key][table]) for table in SATELLITES},
        }
        data["weekly_hours_complete"] = not issues
        data["header_weekly_hours_equal"] = (
            None if header_hours is None or issues else header_hours == Decimal(data["weekly_total"])
        )
        source_rows.append(data)
        source_map[header["id"]] = data

    journal_rows = []
    for journal in journals:
        sid = journal["sillabus_id"]
        source = source_map.get(sid)
        try:
            raw_groups = json.loads(journal["groups_id"] or "[]")
            groups = sorted({int(value) for value in raw_groups}) if isinstance(raw_groups, list) else []
            groups_valid = isinstance(raw_groups, list)
        except (ValueError, TypeError):
            groups, groups_valid = [], False
        scopes = {group_scopes.get(group_id, "unknown") for group_id in groups}
        group_scope = next(iter(scopes)) if len(scopes) == 1 else "mixed" if scopes else "unknown"
        if not sid:
            relation = "no_source_reference"
        elif source is None:
            relation = "missing_source_header"
        elif source["subject_id"] == journal["lesson_id"]:
            relation = "same_subject_id"
        elif names.get(source["subject_id"]) and names.get(source["subject_id"]) == names.get(journal["lesson_id"]):
            relation = "different_subject_id_same_normalized_name"
        else:
            relation = "different_subject_identity_review_required"
        hours, hours_issue = hour(journal["fenn_saati"])
        journal_rows.append(
            {
                "journal_id": journal["id"],
                "journal_uniqid": journal["uniqid"],
                "legacy_subject_id": journal["lesson_id"],
                "legacy_teacher_id": journal["teacher_id"],
                "legacy_group_ids": groups,
                "groups_valid": groups_valid,
                "legacy_group_scope": group_scope,
                "legacy_syllabus_id": sid,
                "semestr": journal["semestr"],
                "fake": journal["fake"],
                "sonra_sil": journal["sonra_sil"],
                "active": journal["active"],
                "journal_hours": str(hours) if hours is not None else None,
                "journal_hours_issue": hours_issue,
                "source_relation": relation,
                "same_source_teacher": bool(source and source["teacher_id"] == journal["teacher_id"]),
                "source_week_rows": source["weekly_rows"] if source else None,
                "source_week_topics": source["nonblank_weekly_topics"] if source else None,
                "source_uniqid_ambiguous": bool(source and source["uniqid_header_count"] != 1),
                "source_active": source["active"] if source else None,
                "source_teacher_exists": source["teacher_exists"] if source else None,
                "source_subject_name_sha256": digest(names.get(source["subject_id"])) if source else None,
                "journal_subject_name_sha256": digest(names.get(journal["lesson_id"])),
                "journal_row_sha256": digest(journal),
            }
        )
    eligible = [row for row in journal_rows if row["fake"] == 0 and row["sonra_sil"] == 0]
    name_groups = defaultdict(list)
    for key, value in names.items():
        if value:
            name_groups[value].append(key)
    duplicate_names = [
        {"name_sha256": digest(name), "legacy_subject_ids": sorted(ids)}
        for name, ids in name_groups.items()
        if len(ids) > 1
    ]
    summary = {
        "started_at_utc": started,
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": database,
        "source_snapshot_date": "unverified_local_legacy_snapshot",
        "journal_added_range": {key: str(value) for key, value in journal_dates.items()},
        "group_table_scopes": dict(Counter(group_scopes.values())),
        "is_current_production_audit": False,
        "journal_semester14_count": len(journals),
        "nonfake_not_deleted_journals": len(eligible),
        "nonfake_active_distribution": dict(Counter(str(row["active"]) for row in eligible)),
        "nonfake_group_scope_distribution": dict(Counter(row["legacy_group_scope"] for row in eligible)),
        "reference_categories_by_group_scope": {
            scope: dict(Counter(row["source_relation"] for row in eligible if row["legacy_group_scope"] == scope))
            for scope in sorted({row["legacy_group_scope"] for row in eligible})
        },
        "all_syllabus_headers": len(headers),
        "all_syllabus_uniqids": len(uniqid_counts),
        "referenced_syllabus_ids": len(referenced),
        "resolved_reference_headers": sum(row["referenced_by_semester14"] for row in source_rows),
        "extra_reviewed_plan_headers": sum(not row["referenced_by_semester14"] for row in source_rows),
        "reference_categories_all": dict(Counter(row["source_relation"] for row in journal_rows)),
        "reference_categories_nonfake": dict(Counter(row["source_relation"] for row in eligible)),
        "nonfake_source_teacher_mismatch": sum(
            row["legacy_syllabus_id"] in source_map and not row["same_source_teacher"] for row in eligible
        ),
        "nonfake_no_weekly_topics": sum(row["source_week_topics"] == 0 for row in eligible),
        "nonfake_inactive_source": sum(row["source_active"] == 0 for row in eligible),
        "nonfake_ambiguous_source_uniqid": sum(row["source_uniqid_ambiguous"] for row in eligible),
        "source_header_week_hours_differ": sum(
            row["header_weekly_hours_equal"] is False for row in source_rows if row["referenced_by_semester14"]
        ),
        "source_header_week_hours_unknown": sum(
            row["header_weekly_hours_equal"] is None for row in source_rows if row["referenced_by_semester14"]
        ),
        "source_hour_cell_issue_headers": sum(
            bool(row["hour_cell_issues"]) for row in source_rows if row["referenced_by_semester14"]
        ),
        "table_counts": table_counts,
        "legacy_subjects": len(names),
        "duplicate_normalized_legacy_subject_name_groups": len(duplicate_names),
        "duplicate_normalized_legacy_subject_name_cards": sum(
            len(row["legacy_subject_ids"]) for row in duplicate_names
        ),
        "limits": [
            "This legacy-only evidence does not establish current EMS state; consult the separate current metadata evidence.",
            "A source subject/teacher disagreement is a review candidate, not permission to overwrite current records.",
            "Legacy active0/2 journals retained as separate strata; no undocumented active filter was imposed.",
            "Hours are not rounded; invalid/fractional cells remain explicit.",
        ],
    }
    for name, payload in [
        ("syllabus_legacy_summary.json", summary),
        ("syllabus_legacy_journals.json", journal_rows),
        ("syllabus_legacy_sources.json", source_rows),
        ("subject_legacy_name_duplicates.json", duplicate_names),
        (
            "syllabus_legacy_base_headers.json",
            [
                {
                    "legacy_syllabus_id": row["id"],
                    "legacy_subject_id": row["lesson_id"],
                    "legacy_teacher_id": row["teacher_id"],
                    "active": row["active"],
                    "uniqid_header_count": uniqid_counts[row["uniqid"]],
                    "header_sha256": digest(row),
                }
                for row in headers
            ],
        ),
    ]:
        (OUT / name).write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    run()
