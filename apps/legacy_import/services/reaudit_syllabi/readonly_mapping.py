"""Read-only counterpart of native versioning.latest_version; never creates v1."""

from collections import defaultdict

from .contracts import RestoreError


def require(condition, code):
    if not condition:
        raise RestoreError(code)


FIELDS = ("source_row_hash", "transform_version", "target_model_label", "target_pk", "state", "reconciliation_status")


def effective_maps(base_rows, versions):
    grouped = defaultdict(list)
    base_ids = {row["id"] for row in base_rows}
    require(all(row["entity_map_id"] in base_ids for row in versions), "ledger_version_base_closure_missing")
    for row in versions:
        grouped[row["entity_map_id"]].append(row)
    output = []
    for base in base_rows:
        ordered = sorted(grouped[base["id"]], key=lambda row: row["version_number"])
        current = dict(base)
        previous = None
        for index, version in enumerate(ordered, 1):
            require(
                version["organization_id"] == base["organization_id"] and version["version_number"] == index,
                "ledger_version_chain_invalid",
            )
            if index == 1:
                require(
                    all(version[field] == base[field] for field in FIELDS)
                    and version["recorded_run_id"] == base["created_run_id"]
                    and version["supersedes_id"] is None,
                    "ledger_initial_version_changed",
                )
            else:
                require(
                    version["supersedes_id"] == previous["id"]
                    and all(
                        version.get(key)
                        for key in (
                            "approved_issue_id",
                            "reviewed_by_id",
                            "reviewed_at",
                            "review_reason_code",
                            "review_evidence_digest",
                            "applied_by_id",
                        )
                    ),
                    "ledger_unapplied_or_unreviewed_version",
                )
            current.update({field: version[field] for field in FIELDS})
            current["canonical_version_id"] = version["id"]
            previous = version
        if current["state"] == "migrated":
            output.append(current)
    return output
