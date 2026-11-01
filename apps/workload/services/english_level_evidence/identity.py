"""Pure exact identity evidence. Never name-match, create, reactivate or prioritize contradictions."""

import hashlib
import re
from collections import Counter, defaultdict


def fin(value):
    text = str(value or "").strip()
    return text.upper() if re.fullmatch(r"[0-9A-Za-z]{7}", text) and text != "0000000" else ""


def fingerprint(value):
    return hashlib.sha256(value.encode()).hexdigest() if value else None


def resolve(records, profiles, ledger):
    by_uid, identifiers, fins = {}, defaultdict(set), defaultdict(set)
    for row in profiles:
        uid = row["user_id"]
        by_uid[uid] = row
        if row["institutional_identifier"]:
            identifiers[row["institutional_identifier"]].add(uid)
        if fin(row["fin"]):
            fins[fin(row["fin"])].add(uid)
    source_fins = Counter(row["normalized_fin"] for row in records if row["normalized_fin"])
    result = []
    for row in records:
        methods = {
            "ledger": set(ledger.get(str(row["id"]), ())),
            "institutional": identifiers.get(row["institutional_identifier"], set()),
            "fin": (fins.get(row["normalized_fin"], set()) if row["normalized_fin"] else set()),
        }
        reasons = []
        if methods["ledger"] - by_uid.keys():
            reasons.append("ledger_target_outside_same_tenant_profiles")
        duplicate_source_fin = source_fins[row["normalized_fin"]] > 1
        if duplicate_source_fin and not (methods["ledger"] or methods["institutional"]):
            reasons.append("source_identity_duplicate")
        for key, values in methods.items():
            if len(values) > 1:
                reasons.append("ambiguous_" + key)
        candidates = set().union(*methods.values())
        if len(candidates) > 1:
            reasons.append("identity_evidence_contradiction")
        uid = next(iter(candidates)) if len(candidates) == 1 else None
        if uid in by_uid:
            target = by_uid[uid]
            target_fin = fin(target["fin"])
            if row["normalized_fin"] and target_fin and target_fin != row["normalized_fin"]:
                reasons.append("source_target_fin_disagrees")
            target_identifier = target["institutional_identifier"]
            if target_identifier and target_identifier != row["institutional_identifier"]:
                reasons.append("source_target_institutional_disagrees")
        if not candidates:
            reasons.append("no_exact_identity_match")
        result.append(
            {
                "source_id": row["id"],
                "source_row_sha256": row["source_row_sha256"],
                "source_fin_sha256": row["fin_sha256"],
                "source_fin_valid": row["fin_valid"],
                "source_fin_duplicate": duplicate_source_fin,
                "target_user_id": uid if not reasons else None,
                "method": (
                    next((key for key, values in methods.items() if uid in values), None) if not reasons else None
                ),
                "evidence_methods": [key for key, values in methods.items() if values],
                "same_tenant_candidate_user_ids": sorted(candidates & by_uid.keys()),
                "reasons": sorted(set(reasons)),
                "immutable_mapping": False,
            }
        )
    return result
