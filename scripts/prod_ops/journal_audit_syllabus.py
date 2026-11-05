"""Match fresh authenticated syllabus fingerprints to locally inspectable content.

An unchanged version UUID alone is not content evidence. Only exact canonical
body or weekly-section hashes make an older body usable for current review.
"""

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from journal_audit_checks import normalize


def digest(value):
    """Wire protocol exact_syllabus_recovery.digest/1; preserve text and order."""
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True, default=str).encode()).hexdigest()


def inspect(payloads, baseline, inventory):
    current = {row["offering_id"]: row for row in inventory["inventory"]}
    bodies = defaultdict(dict)
    for section in baseline["syllabus.SyllabusSection"]:
        bodies[section["version_id"]][section["section_id"]] = section["data"]
    body_hashes, week_hashes = {}, {}
    for vid, body in bodies.items():
        body_hashes[digest(body)] = vid
        if "week" in body:
            week_hashes[digest(body["week"])] = vid
    roots = {}
    for payload in sorted(payloads, key=lambda p: (p["captured_at"], p["batch"])):
        for root in payload["data"]["roots"]:
            roots[root["offering_id"]] = (root, payload)
    issues = defaultdict(list)
    result = []
    identical_topics = defaultdict(list)
    for oid, context in sorted(current.items()):
        out = {"offering_id": oid, "body_evidence": "not_captured", "semantic_review": "not_manually_certified"}
        if oid not in roots:
            result.append(out)
            continue
        root, payload = roots[oid]
        data = payload["data"]
        versions = {row["id"]: row for row in data["versions"]}
        syllabi = {row["id"]: row for row in data["syllabi"]}
        vid, sid = root["effective_approved_version_id"], root["selected_syllabus_id"]
        out.update(
            batch=payload["batch"],
            captured_at=payload["captured_at"],
            syllabus_id=sid,
            approved_version_id=vid,
            relation=root["relation"],
        )
        out["syllabus_state"] = "missing" if not sid else "unapproved" if not vid else "approved"
        out["body_evidence"] = "fresh_resolver_no_approved_body" if not vid else "fresh_fingerprint_only"
        held = next((r for r in data.get("held_roots", []) if r["offering_id"] == oid), None)
        if held:
            out["lineage_cycle_affected"] = held["lineage_cycle_affected"]
            if held["lineage_cycle_affected"]:
                issues["lineage_cycle_affected"].append(dict(out))
        if sid and syllabi[sid]["subject_id"] != context["subject_id"]:
            issues["wrong_subject_id_link"].append(
                {**out, "syllabus_subject_id": syllabi[sid]["subject_id"], "journal_subject_id": context["subject_id"]}
            )
        if not vid:
            result.append(out)
            continue
        version = versions[vid]
        assert version["canonical_policy"] == "exact_syllabus_recovery.digest/1"
        out["topic_summary"] = version["topic_summary"]
        out["plan_hours"] = version["plan_hours"]
        out["body_sha256"] = version["canonical_body_sha256"]
        baseline_vid = body_hashes.get(version["canonical_body_sha256"])
        week = next((s for s in data["sections"] if s["version_id"] == vid and s["section_id"] == "week"), None)
        week_vid = week_hashes.get(week["raw_data_sha256"]) if week else None
        if baseline_vid:
            out["body_evidence"] = "full_body_exact_hash_verified"
            out["baseline_body_version_id"] = baseline_vid
        elif week_vid:
            out["body_evidence"] = "weekly_topics_exact_hash_verified"
        if week_vid:
            out["baseline_week_version_id"] = week_vid
            topics = [
                str(row.get("topic") or "").strip()
                for row in bodies[week_vid]["week"].get("rows", [])
                if isinstance(row, dict) and str(row.get("topic") or "").strip()
            ]
            out["topics"] = topics
            if len(topics) >= 5:
                identical_topics[tuple(normalize(t) for t in topics)].append(oid)
        summary = version["topic_summary"]
        if summary["nonempty_topic_count"] == 0:
            issues["approved_empty_weekly_topics"].append(dict(out))
        if summary["hours_without_topic_count"]:
            issues["hours_without_topics"].append(dict(out))
        if summary.get("invalid_shape_or_hours_count"):
            issues["invalid_weekly_shape_or_hours"].append(dict(out))
        if version["plan_hours"]["valid"]:
            total = sum(version["plan_hours"]["hours"].values())
            out["plan_total"] = total
            if summary.get("totals_complete"):
                weekly_total = sum(summary["hours_by_kind"].values())
                out["weekly_total"] = weekly_total
                if weekly_total != total:
                    issues["weekly_total_differs_from_version_plan"].append(dict(out))
            if total and context["lesson_hours"] and total != context["lesson_hours"]:
                issues["journal_syllabus_hours_difference"].append(
                    {**out, "journal_hours": context["lesson_hours"], "syllabus_hours": total}
                )
        result.append(out)
    for oids in identical_topics.values():
        if len({normalize(current[oid]["subject"]) for oid in oids}) > 1:
            issues["identical_topics_different_subject_names"].append(
                {
                    "offering_ids": oids,
                    "subjects": sorted({current[oid]["subject"] for oid in oids}),
                    "confirmed_mismatch": False,
                }
            )
    return {
        "read_only": True,
        "counts": {"current_journals": len(current), "fresh_resolver_covered": sum(oid in roots for oid in current)},
        "body_evidence_counts": dict(Counter(row["body_evidence"] for row in result)),
        "issue_counts": {key: len(value) for key, value in sorted(issues.items())},
        "issues": dict(issues),
        "inventory": result,
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("inventory", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    payloads = [json.loads(p.read_bytes()) for p in sorted(args.directory.glob("*.json"))]
    result = inspect(payloads, json.loads(args.baseline.read_bytes()), json.loads(args.inventory.read_bytes()))
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    args.output.chmod(0o600)
    print(
        json.dumps({key: result[key] for key in ("counts", "body_evidence_counts", "issue_counts")}, ensure_ascii=False)
    )
