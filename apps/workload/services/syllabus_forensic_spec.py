"""Only two held registry batches: body fingerprints with explicit invalid lineage."""

FORMAT = "wcu-syllabus-content-cycle-forensic/1"
BATCHES = ("chair-cells-027", "chair-cells-029")
SCHEMAS = {
    "lineage_edges": set("from_model from_id relation to_model to_id".split()),
    "lineage_cycles": set("model relation node_ids".split()),
    "held_roots": set("organization_id offering_id lineage_cycle_affected".split()),
}


def analysis(data, *, graph_builder=None):
    if graph_builder is None:
        from .syllabus_lineage_spec import graph as graph_builder

    edges, cycles, mismatches = graph_builder(data["syllabi"], data["versions"])
    if mismatches:
        raise ValueError("syllabus_version_owner_mismatch")
    adjacent = {}
    for edge in edges:
        adjacent.setdefault((edge["from_model"], edge["from_id"]), set()).add((edge["to_model"], edge["to_id"]))
    # Owners are part of the exported closure too, including their current pointer.
    for row in data["versions"]:
        adjacent.setdefault(("version", str(row["id"])), set()).add(("syllabus", str(row["syllabus_id"])))
    cyclic = {(row["model"], pk) for row in cycles for pk in row["node_ids"]}
    roots = []
    for root in data["roots"]:
        pending = [("syllabus", str(root["selected_syllabus_id"]))] if root["selected_syllabus_id"] else []
        seen = set()
        while pending:
            key = pending.pop()
            if key not in seen:
                seen.add(key)
                pending.extend(adjacent.get(key, ()))
        roots.append(
            dict(
                organization_id=root["organization_id"],
                offering_id=root["offering_id"],
                lineage_cycle_affected=bool(seen & cyclic),
            )
        )
    return {"lineage_edges": edges, "lineage_cycles": cycles, "held_roots": roots}
