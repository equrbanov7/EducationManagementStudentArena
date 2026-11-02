"""Fixed 027 metadata-only cycle evidence; never a normal content/recovery capsule."""

import hashlib
import json
from pathlib import Path

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
PERIOD = "a4f88744-8d49-4772-84ef-c28a96c3b372"
YEAR = "2026/2027"
BATCH = "chair-cells-027"
FORMAT = "wcu-syllabus-lineage-diagnostic/1"
REGISTRY_SHA = "52e620563eea6080993111f9e51bf8f0a9f5689115bd3632e0dcb3048b45773d"
MAX_BYTES = 2 * 1024 * 1024
MAX_COURSES = 25
MAX_SYLLABI = 300
MAX_VERSIONS = 500
MAX_DEPTH = 16
SCHEMAS = {
    "roots": set("offering_id selected_syllabus_id effective_approved_version_id".split()),
    "offerings": set("id organization_id subject_id period_id group_id instructor_id lesson_hours is_active".split()),
    "syllabi": set(
        "id organization_id subject_id offering_id period_id author_id chair_unit_id program_id is_active current_version_id approved_version_id reused_from_id created_at updated_at record_sha256".split()
    ),
    "versions": set(
        "id organization_id syllabus_id status source_version_id applies_to_period_id approval_source approved_by_id approved_at created_at updated_at record_sha256".split()
    ),
    "edges": set("from_model from_id relation to_model to_id".split()),
    "cycles": set("model relation node_ids".split()),
    "owner_mismatches": set("syllabus_id version_id relation".split()),
}
SYLLABUS_FIELDS = tuple(sorted(SCHEMAS["syllabi"] - {"record_sha256"}))
VERSION_FIELDS = tuple(sorted(SCHEMAS["versions"] - {"record_sha256"}))


def selection():
    path = Path(__file__).with_name("chair_cells_export") / "batches.json"
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != REGISTRY_SHA:
        raise ValueError("registry_fingerprint_mismatch")
    selected = json.loads(raw)["batches"][BATCH]
    if len(selected["offerings"]) != 20:
        raise ValueError("syllabus_root_scope_invalid")
    return selected


def graph(syllabi, versions):
    """Deterministic exact edges and simple pointer cycles; no interpretation or repair."""
    sy, ve = {str(s["id"]): s for s in syllabi}, {str(v["id"]): v for v in versions}
    edges, mismatches, cycles = [], [], []
    for key, row in sorted(sy.items()):
        for relation, target_model in (
            ("current_version_id", "version"),
            ("approved_version_id", "version"),
            ("reused_from_id", "syllabus"),
        ):
            if row[relation]:
                target = str(row[relation])
                edges.append(
                    dict(from_model="syllabus", from_id=key, relation=relation, to_model=target_model, to_id=target)
                )
                if target_model == "version" and target in ve and str(ve[target]["syllabus_id"]) != key:
                    mismatches.append(dict(syllabus_id=key, version_id=target, relation=relation))
    for key, row in sorted(ve.items()):
        if row["source_version_id"]:
            edges.append(
                dict(
                    from_model="version",
                    from_id=key,
                    relation="source_version_id",
                    to_model="version",
                    to_id=str(row["source_version_id"]),
                )
            )
    for label, objects, relation in (("syllabus", sy, "reused_from_id"), ("version", ve, "source_version_id")):
        found = set()
        for start in sorted(objects):
            path, seen, current = [], {}, start
            while current in objects and current not in seen:
                seen[current] = len(path)
                path.append(current)
                target = objects[current][relation]
                current = str(target) if target else None
            if current in seen:
                cycle = path[seen[current] :]
                offset = cycle.index(min(cycle))
                found.add(tuple(cycle[offset:] + cycle[:offset]))
        cycles.extend(dict(model=label, relation=relation, node_ids=list(nodes)) for nodes in sorted(found))
    return edges, cycles, mismatches
