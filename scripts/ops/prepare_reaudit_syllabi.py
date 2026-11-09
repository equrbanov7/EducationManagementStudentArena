#!/usr/bin/env python3
"""Prepare a private source packet from a verified fresh capture plus SELECT-only legacy.

No PostgreSQL connection or production command is permitted by this script.
"""

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def checked_json(path, expected):
    raw = path.read_bytes()
    if not expected or hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("private_input_sha256_mismatch")
    return json.loads(raw)


def save_new(path, value):
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as stream:
        stream.write(raw)
    return hashlib.sha256(raw).hexdigest()


def validate_capture(snapshot, manifest, manifest_sha):
    if snapshot.get("manifest") != manifest or snapshot.get("transport", {}).get("manifest_sha256") != manifest_sha:
        raise ValueError("decoded_snapshot_manifest_identity_changed")
    if not manifest.get("complete") or set(snapshot["tables"]) != set(manifest["tables"]):
        raise ValueError("complete_snapshot_required")
    for label, spec in manifest["tables"].items():
        rows = snapshot["tables"][label]
        if len(rows) != spec["rows"] or len({str(row["id"]) for row in rows}) != len(rows):
            raise ValueError("snapshot_table_count_or_duplicate_mismatch")
        if any(set(row) != set(spec["fields"]) for row in rows):
            raise ValueError("snapshot_field_contract_changed")
    if sum(map(len, snapshot["tables"].values())) != manifest["total_rows"]:
        raise ValueError("snapshot_total_mismatch")


def no_database(execute, sql, params, many, context):
    raise RuntimeError("offline_plan_prohibits_application_database_access")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", required=True, type=Path)
    parser.add_argument("--snapshot-sha256", required=True)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--offering", action="append", default=[])
    args = parser.parse_args(argv)
    output = args.output_dir.resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError("private_output_outside_repository_required")
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    if output.stat().st_mode & 0o077:
        raise ValueError("private_output_permissions_required")
    snapshot = checked_json(args.snapshot, args.snapshot_sha256)
    manifest = checked_json(args.manifest, args.manifest_sha256)
    validate_capture(snapshot, manifest, args.manifest_sha256)
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.test"
    # A syntactically valid unreachable DB; execute_wrapper additionally refuses every SQL.
    os.environ["DATABASE_URL"] = "postgresql://offline:offline@127.0.0.1:1/offline"
    import django

    django.setup()
    from django.db import connection

    from apps.legacy_import.services.reaudit_syllabi.contracts import SCOPE
    from apps.legacy_import.services.reaudit_syllabi.source_plan import prepare_sources
    from apps.legacy_import.services.syllabus_migration_contracts import SYLLABUS_SECTION_CONTRACTS

    if (
        manifest.get("format") != "qku-reaudit-state/1"
        or not manifest.get("read_only")
        or manifest.get("organization_id") != SCOPE["organization_id"]
        or manifest.get("period_id") != SCOPE["period_id"]
    ):
        raise ValueError("fresh_capture_manifest_scope")
    spec = importlib.util.spec_from_file_location(
        "reaudit_read_sources", ROOT / "docs/audits/2026-11-09-codex/evidence/read_sources.py"
    )
    reader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader)
    with connection.execute_wrapper(no_database), reader.legacy() as source:
        headers = reader.select(
            source, "SELECT id,uniqid,lesson_id,teacher_id,ders_saati,language,active FROM sillabus ORDER BY id"
        )
        journals = reader.select(
            source,
            "SELECT id,teacher_id,lesson_id,sillabus_id,semestr,fake,sonra_sil,groups_id FROM journals WHERE semestr=14 ORDER BY id",
        )
        for row in journals:
            try:
                value = json.loads(row.pop("groups_id") or "[]")
                row["group_ids"] = [int(v) for v in value] if isinstance(value, list) else []
            except (ValueError, TypeError):
                row["group_ids"] = []

        def load(header):
            result = dict(header)
            result["week"] = reader.select(
                source,
                "SELECT id,uniqid,movzu,muh_saat,sem_saat,praktiki_saat,lab_saat,qeyd FROM sillabus_sem_muh WHERE uniqid=%s ORDER BY id",
                (header["uniqid"],),
            )
            result["sections"] = {}
            for table in SYLLABUS_SECTION_CONTRACTS:
                rows = reader.select(
                    source, f"SELECT id,name FROM `{table}` WHERE uniqid=%s ORDER BY id", (header["uniqid"],)
                )
                result["sections"][table] = [[r["id"], r["name"]] for r in rows]
            return result

        packet, plan = prepare_sources(snapshot, headers, journals, load, offering_ids=args.offering)
    packet_sha = save_new(output / "source-packet.json", packet)
    plan.update(
        snapshot_sha256=args.snapshot_sha256,
        manifest_sha256=args.manifest_sha256,
        captured_at=manifest.get("captured_at"),
        source_packet_sha256=packet_sha,
    )
    plan_sha = save_new(output / "selection-plan.json", plan)
    print(
        json.dumps(
            {
                "source_packet_sha256": packet_sha,
                "selection_plan_sha256": plan_sha,
                "counts": plan["counts"],
                "binding_count": plan["binding_count"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError, OSError, KeyError):
        raise SystemExit("source_plan_precondition_failed; private inputs were not printed") from None
