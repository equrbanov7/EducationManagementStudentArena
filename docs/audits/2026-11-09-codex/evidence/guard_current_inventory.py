"""Revalidate reviewed share-scope metadata without claiming global access coverage."""

import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("metadata", type=Path)
    args = parser.parse_args()
    data = json.loads(args.metadata.read_text())["data"]
    seen = {r["enrollment_id"] for r in data["repair_contact_share_rows"]}
    cases = []
    for offering in data["repair_contact_offerings"]:
        pk = offering["id"]
        selected = [r for r in data["repair_contact_enrollments"] if r["offering_id"] == pk]
        enrolled = sum(r["status"] == "enrolled" for r in selected)
        total = sum(
            r["count"] for r in data["enrollment_status_counts"] if r["offering_id"] == pk and r["status"] == "enrolled"
        )
        cases.append(
            {
                "offering_id": pk,
                "all_enrolled_count": total,
                "selected_enrolled_count": enrolled,
                "not_selected_enrolled_count": total - enrolled,
                "active_share_count": sum(
                    r["is_active"] for r in data["repair_contact_shares"] if r["offering_id"] == pk
                ),
            }
        )
    result = {
        "math": data["repair_math_history_scope"],
        "contact": {
            "offerings": len(data["repair_contact_offerings"]),
            "shares": len(data["repair_contact_shares"]),
            "through_rows": len(data["repair_contact_share_rows"]),
            "unique_selected_enrollments": len(seen),
            "exported_enrollments": len(data["repair_contact_enrollments"]),
            "enrollment_export_selected_only": True,
            "by_offering": cases,
        },
        "automatic_apply_authority": False,
        "note": "Unselected rows are not proof of denied owner access; full current permission and enrollment history required.",
    }
    output = Path(__file__).with_name("reviewed_guard_metadata.json")
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
