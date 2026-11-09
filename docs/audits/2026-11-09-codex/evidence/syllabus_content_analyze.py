"""Analyze native text-free syllabus captures; no Django, DB or network access."""

import ast
import hashlib
import importlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
PRIVATE = Path("/Users/elvin/Desktop/RIM/Secret/reaudit-20261109")
sys.path.insert(0, str(ROOT / "scripts/ops"))
scope = importlib.import_module("syllabus_content_scope")
native = importlib.import_module("syllabus_export_pack")
HEAD = "45892d9011e6e31d9ad39f9999fa3cb7f6717f84"


def read(path):
    return json.loads(path.read_bytes())


def write(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n")


def literal(path, name):
    for statement in ast.parse(path.read_text()).body:
        if isinstance(statement, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in statement.targets
        ):
            return ast.literal_eval(statement.value)
    raise ValueError("missing_literal_pin")


def register_capture(payload, path, manifest, roots, captures):
    source = {
        "file": str(path.relative_to(PRIVATE)),
        "batch": payload["batch"],
        "captured_at": payload["captured_at"],
        "plaintext_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "run_id": manifest["run_id"],
        "root_count": len(payload["data"]["roots"]),
    }
    captures.append(source)
    for root in payload["data"]["roots"]:
        old = roots.get(root["offering_id"])
        if old is None or source["captured_at"] > old[2]["captured_at"]:
            roots[root["offering_id"]] = root, payload["data"], source


def read_single_captures(roots, captures, pending):
    receipt_path = OUT / "syllabus_single_capture_receipt.json"
    if not receipt_path.exists():
        return
    for receipt in read(receipt_path).get("runs", []):
        if receipt.get("capture_status") != "complete":
            continue
        directory = receipt["private_directory"]
        if not re.fullmatch(r"syllabus-single-(031|082)", directory):
            raise ValueError("single_capture_scope_unreviewed")
        folder = PRIVATE / directory
        path = folder / f"chair-cells-{directory[-3:]}.json"
        if not path.exists():
            pending.append(str(path.relative_to(PRIVATE)))
            continue
        manifest_raw = (folder / "encrypted/capture-manifest.json").read_bytes()
        manifest = json.loads(manifest_raw)
        expected = {
            "format": "wcu-syllabus-content-capture/1",
            "head_sha": HEAD,
            "run_id": receipt["run_id"],
            "run_attempt": receipt["run_attempt"],
            "batch": receipt["batch"],
            "registry_sha256": scope.REGISTRY_SHA,
            "encrypted_sha256": manifest.get("encrypted_sha256"),
            "file": "snapshot.enc.json",
            "eligible_for_apply": False,
        }
        if (
            manifest != expected
            or receipt["batch"] != f"chair-cells-{directory[-3:]}"
            or receipt["head"] != HEAD
            or hashlib.sha256(manifest_raw).hexdigest() != receipt["manifest_sha256"]
            or receipt["encrypted_sha256"] != manifest["encrypted_sha256"]
            or hashlib.sha256((folder / "encrypted/snapshot.enc.json").read_bytes()).hexdigest()
            != manifest["encrypted_sha256"]
            or hashlib.sha256(path.read_bytes()).hexdigest() != receipt["plaintext_sha256"]
        ):
            raise ValueError("single_capture_receipt_digest_mismatch")
        payload = read(path)
        scope.validate(payload)
        if payload["batch"] != receipt["batch"]:
            raise ValueError("single_capture_batch_mismatch")
        register_capture(payload, path, manifest, roots, captures)


def run():
    metadata = {r["id"]: r for r in read(OUT / "syllabus_current_offerings.json")}
    inventory = read(OUT / "syllabus_source_plan_inventory.json")
    recovery = read(OUT / "syllabus_reviewed_current_status.json")["legacy_recovery_plan"]
    plan_by_target = {oid: row for row in recovery for oid in row["candidate_offering_ids"]}
    hashes = {
        row["content_sha256"]: {"kind": "repo_recovery_plan", "legacy_syllabus_id": int(sid)}
        for sid, row in inventory["legacy_recovery_plan"]["sources"].items()
    }
    hashes[literal(ROOT / "apps/legacy_import/services/reviewed_pervin_syllabus_spec.py", "BODY_SHA")] = {
        "kind": "reviewed_own60",
        "legacy_syllabus_id": 8573,
    }
    hashes[inventory["reviewed_pins"][2]["constants"]["SOURCE_BODY_SHA"]] = {
        "kind": "reviewed_subject_rebind",
        "legacy_syllabus_id": 7456,
    }
    important = {
        r["id"]
        for r in metadata.values()
        if r["is_active"]
        and r["current_period"]
        and (r["visibility"] in {"missing", "unapproved"} or r["scope_mismatch_fields"])
    }
    important |= set(plan_by_target)
    for pin in inventory["reviewed_pins"][:2]:
        important |= set(pin["ids"].get("courses", pin["ids"].get("offerings", [])))
    important.add(inventory["reviewed_pins"][2]["constants"]["TARGET"])
    important |= set(inventory["reviewed_pins"][3]["constants"]["OFFERINGS"])
    captures, roots, pending = [], {}, []
    receipt_path = OUT / "syllabus_capture_receipt.json"
    receipt_rows = read(receipt_path).get("runs", []) if receipt_path.exists() else []
    receipts = {row["pack"]: row for row in receipt_rows}
    for path in sorted(PRIVATE.glob("syllabus-pack-*/*.json")):
        try:
            payload = read(path)
        except (json.JSONDecodeError, OSError):
            pending.append(str(path.relative_to(PRIVATE)))
            continue
        scope.validate(payload)
        receipt = receipts.get(path.parent.name)
        batch_receipt = next((r for r in (receipt or {}).get("batches", []) if r["batch"] == payload["batch"]), None)
        if not batch_receipt:
            pending.append(str(path.relative_to(PRIVATE)) + ":receipt_pending")
            continue
        manifest_raw = (path.parent / "encrypted/pack-manifest.json").read_bytes()
        manifest = native.validate_manifest(json.loads(manifest_raw), name=path.parent.name, head=HEAD)
        if (
            hashlib.sha256(path.read_bytes()).hexdigest() != batch_receipt["plaintext_sha256"]
            or hashlib.sha256(manifest_raw).hexdigest() != receipt["manifest_sha256"]
            or manifest["run_id"] != receipt["run_id"]
        ):
            raise ValueError("capture_receipt_digest_mismatch")
        register_capture(payload, path, manifest, roots, captures)
    read_single_captures(roots, captures, pending)
    rows = []
    for oid in sorted(important):
        if oid not in roots:
            rows.append({"offering_id": oid, "content_capture_available": False})
            continue
        root, data, source = roots[oid]
        offering = next(r for r in data["offerings"] if r["id"] == oid)
        syllabi = {r["id"]: r for r in data["syllabi"]}
        versions = {r["id"]: r for r in data["versions"]}
        sections = defaultdict(list)
        for section in data["sections"]:
            sections[section["version_id"]].append(section)
        selected = syllabi.get(root["selected_syllabus_id"])
        current = versions.get(root["current_version_id"])
        approved = versions.get(root["effective_approved_version_id"])
        visibility = "missing" if selected is None else "approved" if approved else "unapproved"
        identity_fields = ("subject_id", "period_id", "group_id", "instructor_id", "is_active")
        same_identity = all(offering[k] == metadata[oid][k] for k in identity_fields) if oid in metadata else None
        nonblank = [
            r["section_id"] for r in sections.get(root["current_version_id"], []) if r["nonblank_string_present"]
        ]
        blank_structure = bool(
            current
            and current["status"] == "draft"
            and current["approval_source"] == "human"
            and set(nonblank) <= {"info"}
        )
        protected_content = bool(
            current
            and current["status"] == "draft"
            and current["approval_source"] == "human"
            and set(nonblank) - {"info"}
        )
        legacy_sources = [
            r["legacy_numeric_id"]
            for r in data["ledger"]
            if r["target_model_label"] == "syllabus.syllabus"
            and r["target_pk"] == root["selected_syllabus_id"]
            and r["entity_type"] == "syllabus"
            and r["source_system"] == "myedu_mariadb"
            and r["state"] == "migrated"
            and r["legacy_numeric_id"] is not None
        ]
        own_base = [
            r
            for r in data["syllabi"]
            if r["offering_id"] is None
            and r["subject_id"] == offering["subject_id"]
            and r["author_id"] == offering["instructor_id"]
            and r["is_active"]
            and r["period_id"] in (None, offering["period_id"])
        ]
        candidates = []
        for candidate in own_base:
            version = versions.get(candidate["approved_version_id"])
            candidates.append(
                {
                    "syllabus_id": candidate["id"],
                    "period_id": candidate["period_id"],
                    "approved_version_id": candidate["approved_version_id"],
                    "body_included": candidate["body_included"],
                    "approved_status_verified": bool(version and version["status"] == "approved"),
                    "plan_hours": version["plan_hours"] if version else None,
                    "canonical_body_sha256": version["canonical_body_sha256"] if version else None,
                }
            )
        row = {
            "offering_id": oid,
            "content_capture_available": True,
            "capture": source,
            "same_identity_as_metadata": same_identity,
            "metadata_visibility": metadata.get(oid, {}).get("visibility"),
            "content_visibility": visibility,
            "root": root,
            "offering_subject_id": offering["subject_id"],
            "offering_instructor_id": offering["instructor_id"],
            "offering_lesson_hours": offering["lesson_hours"],
            "selected_syllabus": selected,
            "selected_subject_mismatch": bool(selected and selected["subject_id"] != offering["subject_id"]),
            "selected_period_mismatch": bool(selected and selected["period_id"] not in (None, offering["period_id"])),
            "current_version": current,
            "effective_approved_version": approved,
            "current_nonblank_section_ids": nonblank,
            "blank_draft_structure_candidate_review_history_not_exported": blank_structure,
            "human_draft_content_present_preserve": protected_content,
            "direct_legacy_syllabus_ids": sorted(set(legacy_sources)),
            "approved_body_matches_reviewed_source": (
                hashes.get(approved["canonical_body_sha256"]) if approved else None
            ),
            "same_author_subject_base_candidates": candidates,
            "apply_ready": False,
        }
        plan = plan_by_target.get(oid)
        if plan:
            original = inventory["legacy_recovery_plan"]["targets"][plan["plan_target_index"]]
            desired = {kind: original["plan"].get(kind, 0) for kind in ("lecture", "seminar", "practical", "lab")}
            row["reviewed_plan_comparison"] = {
                "source_id": plan["source_id"],
                "action": plan["action"],
                "offering_hours_match": offering["lesson_hours"] == original["lesson_hours"],
                "version_plan_hours_match": bool(
                    approved and approved["plan_hours"]["valid"] and approved["plan_hours"]["hours"] == desired
                ),
                "body_matches_expected_source": (
                    bool(
                        approved
                        and plan["source_id"]
                        and approved["canonical_body_sha256"]
                        == inventory["legacy_recovery_plan"]["sources"][plan["source_id"]]["content_sha256"]
                    )
                    if plan["source_id"]
                    else None
                ),
                "desired_plan_hours": desired,
            }
        rows.append(row)
    present = [r for r in rows if r["content_capture_available"]]
    original_gaps = [r for r in present if r["metadata_visibility"] in {"missing", "unapproved"}]
    summary = {
        "batch_count": len(captures),
        "pack_directories": len({r["file"].split("/")[0] for r in captures if r["file"].startswith("syllabus-pack-")}),
        "single_batch_captures": sum(r["file"].startswith("syllabus-single-") for r in captures),
        "unique_captured_roots": len(roots),
        "priority_offerings": len(important),
        "priority_captured": len(present),
        "priority_not_captured": len(rows) - len(present),
        "pending_files": pending,
        "original_missing_draft_captured": len(original_gaps),
        "original_missing_draft_current_visibility": dict(Counter(r["content_visibility"] for r in original_gaps)),
        "blank_draft_structure_candidates_reviews_unchecked": sum(
            r["blank_draft_structure_candidate_review_history_not_exported"] for r in original_gaps
        ),
        "human_draft_content_present": sum(r["human_draft_content_present_preserve"] for r in original_gaps),
        "captured_draft_unique_dossiers": len(
            {r["root"]["selected_syllabus_id"] for r in original_gaps if r["content_visibility"] == "unapproved"}
        ),
        "blank_structure_unique_dossiers_reviews_unchecked": len(
            {
                r["root"]["selected_syllabus_id"]
                for r in original_gaps
                if r["blank_draft_structure_candidate_review_history_not_exported"]
            }
        ),
        "human_draft_content_unique_dossiers": len(
            {r["root"]["selected_syllabus_id"] for r in original_gaps if r["human_draft_content_present_preserve"]}
        ),
        "same_author_subject_base_candidates": sum(
            bool(r["same_author_subject_base_candidates"]) for r in original_gaps
        ),
        "approved_version_provenance": dict(
            Counter(
                r["effective_approved_version"]["approval_source"] for r in present if r["effective_approved_version"]
            )
        ),
        "draft_provenance": dict(
            Counter(r["current_version"]["approval_source"] for r in original_gaps if r["current_version"])
        ),
        "subject_mismatch_targets": [r["offering_id"] for r in present if r["selected_subject_mismatch"]],
        "metadata_identity_changed_targets": [
            r["offering_id"] for r in present if r["same_identity_as_metadata"] is False
        ],
        "human_draft_content_targets": [
            r["offering_id"] for r in original_gaps if r["human_draft_content_present_preserve"]
        ],
        "reviewed_plan_comparisons": [
            {"offering_id": r["offering_id"], **r["reviewed_plan_comparison"]}
            for r in present
            if "reviewed_plan_comparison" in r
        ],
        "any_apply_ready": False,
        "limits": [
            "Full target review history and academic meaning of authored prose are not exported.",
            "Base candidates may be metadata-only; nonnull approval pointer alone is not verified approval.",
            "Source plan body hash equality proves exact reviewed bytes, not universal academic suitability.",
            "Latest capture is used per root; the original metadata capture remains separately preserved.",
        ],
    }
    write("syllabus_content_summary.json", summary)
    write("syllabus_content_targets.json", rows)
    write("syllabus_content_manifest.json", captures)
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    run()
