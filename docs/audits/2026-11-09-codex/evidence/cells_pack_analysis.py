"""Incremental own-journal grid and graph audit, without asserting missing group masks."""

import collections
import json

from cells_capture_common import ROOT, digest, load_captures, own_graph, save


def main():
    captures, selected, versions, incomplete = load_captures()
    metadata = json.loads((ROOT / "metadata.json").read_text())
    current = {
        r["id"]: r for r in metadata["data"]["offerings"] if r["period_id"] == "a4f88744-8d49-4772-84ef-c28a96c3b372"
    }
    active_ids = {oid for oid, r in current.items() if r["is_active"]}
    inventory, blanks, anomalies, repeated = [], [], [], []
    for oid, capture in selected.items():
        offering, es, ls, marks = own_graph(capture, oid)
        enrolled = {eid: e for eid, e in es.items() if e["status"] == "enrolled"}
        pairs = collections.defaultdict(list)
        for m in marks:
            if m["lesson_id"] not in ls or m["enrollment_id"] not in es:
                anomalies.append(
                    {"type": "cross_offering_mark", "offering_id": oid, "mark_id": m["id"], "capture": capture["batch"]}
                )
                continue
            pairs[(m["lesson_id"], m["enrollment_id"])].append(m)
            if m["score"] is not None and not 0 <= float(m["score"]) <= 10:
                anomalies.append({"type": "score_out_of_range", "offering_id": oid, "mark_id": m["id"]})
            if m["score"] is not None and m["status"] != "present":
                anomalies.append({"type": "score_status_conflict", "offering_id": oid, "mark_id": m["id"]})
        all_pairs = [(lid, eid) for lid in ls for eid in enrolled]
        empty = [pair for pair in all_pairs if pair not in pairs]
        for lid, eid in empty:
            blanks.append(
                {
                    "offering_id": oid,
                    "offering_active": offering["is_active"],
                    "lesson_id": lid,
                    "enrollment_id": eid,
                    "enrollment_status": es[eid]["status"],
                    "student_id": es[eid]["student_id"],
                    "date": ls[lid]["date"],
                    "kind": ls[lid]["kind"],
                    "start_time": ls[lid]["start_time"],
                    "capture_batch": capture["batch"],
                    "applicability": "unknown_missing_lab_seminar_masks",
                    "eligible_for_apply": False,
                }
            )
        graph_hash = digest(
            {"offering": offering, "enrollments": list(es.values()), "lessons": list(ls.values()), "marks": marks}
        )
        hashes = set()
        for previous in versions[oid]:
            po, pe, pl, pm = own_graph(previous, oid)
            hashes.add(
                digest({"offering": po, "enrollments": list(pe.values()), "lessons": list(pl.values()), "marks": pm})
            )
        if len(hashes) > 1:
            repeated.append(
                {
                    "offering_id": oid,
                    "capture_batches": [x["batch"] for x in versions[oid]],
                    "versions": len(hashes),
                    "policy": "latest complete own-journal capture selected; not a single all-org transaction",
                }
            )
        inventory.append(
            {
                "offering_id": oid,
                "subject_id": offering["subject_id"],
                "group_id": offering["group_id"],
                "instructor_id": offering["instructor_id"],
                "is_active_at_capture": offering["is_active"],
                "enrollment_count": len(es),
                "enrolled_count": len(enrolled),
                "lessons": len(ls),
                "marks_all_statuses": len(marks),
                "structural_grid_pairs": len(all_pairs),
                "structural_filled_pairs": len(all_pairs) - len(empty),
                "structural_unfilled_pairs": len(empty),
                "applicable_blank_count": None,
                "duplicate_cell_keys": sum(len(v) > 1 for v in pairs.values()),
                "capture_batch": capture["batch"],
                "captured_at": capture["captured_at"],
                "own_graph_sha256": graph_hash,
            }
        )
    summary = {
        "capture_batches": len(captures),
        "expected_batches": 91,
        "unique_captured_offerings_including_history": len(selected),
        "metadata_active_current_offerings": len(active_ids),
        "metadata_active_current_captured": len(active_ids & selected.keys()),
        "metadata_active_current_missing": len(active_ids - selected.keys()),
        "capture_start": min((c["captured_at"] for c in captures), default=None),
        "capture_end": max((c["captured_at"] for c in captures), default=None),
        "structural_grid_pairs": sum(r["structural_grid_pairs"] for r in inventory),
        "structural_unfilled_pairs": len(blanks),
        "active_structural_grid_pairs": sum(r["structural_grid_pairs"] for r in inventory if r["is_active_at_capture"]),
        "active_structural_unfilled_pairs": sum(
            r["structural_unfilled_pairs"] for r in inventory if r["is_active_at_capture"]
        ),
        "inactive_structural_unfilled_pairs": sum(
            r["structural_unfilled_pairs"] for r in inventory if not r["is_active_at_capture"]
        ),
        "applicable_blank_count": None,
        "group_masks_missing": True,
        "offering_captures_changed_during_window": len(repeated),
        "numeric_or_cross_fk_anomalies": len(anomalies),
        "all_current_journals_complete": False,
        "data_writes": False,
        "eligible_for_apply": False,
    }
    save(
        "cells_pack_coverage.json",
        {
            "summary": summary,
            "sources": [c["_source"] for c in captures],
            "offerings": inventory,
            "missing_current_active_offering_ids": sorted(active_ids - selected.keys()),
            "capture_variations": repeated,
            "incomplete_files": incomplete,
        },
    )
    save(
        "cells_pack_unfilled_pairs.json",
        {"scope": "unfilled Cartesian pairs only; applicability unknown without current group masks", "rows": blanks},
    )
    save("cells_pack_anomalies.json", {"rows": anomalies})
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
