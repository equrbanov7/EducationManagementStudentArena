"""Two byte-pinned technical imports, reviewed under the new fixed-four restoration authority.

These remain visible delete evidence. They are not a teacher clear exemption:
all other later/unknown audit, formal correction and current-cell guards remain.
The 2026-10-27 immutable archive and diagnostic 41326871426 agree on both rows.
"""

from . import reviewed_content_four_spec as fixed
from .reviewed_content_spec import ORG
from .reviewed_content_state import digest

RESOURCE = "legacy_import.empty_lesson"
PINS = {
    "0c6722f8-7441-43ce-a432-e1363a12754a": {
        "row_sha256": "bda40e1620bdb0def466563971ff48f4cb80bbc123a58078d23760c50578ef7a",
        "old_values_sha256": "469f3996a9671e932499633854c8efffa05f5b9a9891bf245a8c133399eb0e1e",
        "old_values_sql_sha256": "e700c6505fda8699cda6c4b884a8810fd0764e4f0797308392bf22b7489f7a45",
        "offering_id": "03ac22fc-5153-4e27-bec2-c804373c612f",
        "case_ids": [5558632, 5558637, 5558643],
        "actor_id": 8444,
        # This imported absent-only column contained the three exact source
        # students at 2026-10-20 15:15 seminar. The older empty column was Sep 1.
        "classification": "reviewed_source_three_qb_technical_bulk_cleanup",
    },
    "f3124fb0-87f1-4e65-83fb-cd0e55dcfc7f": {
        "row_sha256": "831767cb0c7d8e6b59c232de0f53485f3dcc976bca538b2dba87b45104764b91",
        "old_values_sha256": "c5d5314b8694c10e5e95f6945ee0ef6c1bbe3620162ee9ee16950be81fcc3261",
        "old_values_sql_sha256": "dca81fd1fcec504ff432d4f9418bec9fa140f1d606070876b2e19268e033d3c0",
        "offering_id": "b9add126-024d-4865-97b4-26abdfbd3193",
        "case_ids": [5458056],
        "actor_id": 8444,
        # Empty Sep 7 13:35 column, no marks. Fixed source point is Oct 7.
        "classification": "unrelated_september_empty_column_without_marks",
    },
}


def permits_reviewed_cleanup(row, data):
    """No dynamic selector or resource-prefix exemption; unchanged entire bytes required."""
    pin = PINS.get(row.get("id"))
    if pin is None:
        return False
    raw = {k: v for k, v in data.items() if k not in {"selected_target_ids", "until_date"}}
    return bool(
        digest(raw) == fixed.PAYLOAD_DIGEST
        and set(data.get("selected_target_ids", [])) == set(fixed.TARGETS)
        and {point["id"] for point in data.get("points", [])} == set(fixed.CASES)
        and row.get("organization_id") == ORG
        and row.get("raw_record_sha256") == pin["row_sha256"]
        and row.get("old_values_sha256") == pin["old_values_sha256"]
        and row.get("new_values_sha256") == digest(None)
        and row.get("changes_sha256") == digest(None)
        and row.get("resource_kind") == "other"
        and row.get("resource_kind_sha256") == digest(RESOURCE)
        and row.get("resource_id") == pin["offering_id"]
        and row.get("user_id") == pin["actor_id"]
        and row.get("action") == "delete"
        and row.get("case_ids") == pin["case_ids"]
        and row.get("contrary_delete_evidence") is True
        and row.get("contrary_clear_evidence") is False
        and row.get("malformed_intent") is False
        and row.get("source_undo_marker") is False
        and row.get("unresolved_scope_row") is False
        and row.get("reason_present") is True
    )
