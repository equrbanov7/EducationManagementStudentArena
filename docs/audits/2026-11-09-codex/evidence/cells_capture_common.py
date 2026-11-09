"""Read verified encrypted-export plaintext locally; never persist free text."""

import collections
import hashlib
import json
from pathlib import Path

ROOT = Path("/Users/elvin/Desktop/RIM/Secret/reaudit-20261109")
OUT = Path(__file__).resolve().parent
ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
PERIOD = "a4f88744-8d49-4772-84ef-c28a96c3b372"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str) + "\n")


def load_captures():
    captures, invalid = [], []
    for path in sorted(ROOT.glob("journal-pack-*/chair-cells-*.json")):
        if ".enc." in path.name:
            continue
        raw = path.read_bytes()
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            invalid.append({"path": str(path.relative_to(ROOT)), "reason": "write_not_complete"})
            continue
        assert value["organization_id"] == ORG and value["period_id"] == PERIOD
        assert value["read_only"] is True and value["eligible_for_apply"] is False
        assert all(value["counts"][k] == len(v) for k, v in value["data"].items())
        for rows in value["data"].values():
            assert all(r.get("organization_id", ORG) == ORG for r in rows)
        value["_source"] = {
            "path": str(path.relative_to(ROOT)),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "batch": value["batch"],
            "captured_at": value["captured_at"],
        }
        captures.append(value)
    captures.sort(key=lambda c: (c["captured_at"], c["batch"]))
    selected, versions = {}, collections.defaultdict(list)
    for capture in captures:
        for offering in capture["data"]["offerings"]:
            oid = offering["id"]
            versions[oid].append(capture)
            selected[oid] = capture
    return captures, selected, versions, invalid


def own_graph(capture, offering_id):
    data = capture["data"]
    offering = next(r for r in data["offerings"] if r["id"] == offering_id)
    enrollments = {r["id"]: r for r in data["enrollments"] if r["offering_id"] == offering_id}
    lessons = {r["id"]: r for r in data["lessons"] if r["offering_id"] == offering_id}
    marks = [r for r in data["marks"] if r["lesson_id"] in lessons or r["enrollment_id"] in enrollments]
    return offering, enrollments, lessons, marks


def typed_maps(capture):
    maps = collections.defaultdict(lambda: collections.defaultdict(set))
    for row in capture["data"]["ledger"]:
        if row["state"] == "migrated":
            maps[(row["entity_type"], row["target_model_label"])][row["legacy_pk"]].add(row["target_pk"])
    return maps


def target_ids(maps, entity, label, legacy_key):
    return maps[(entity, label)].get(str(legacy_key), set())


def public_cell_values(value):
    """Keep per-cell grade presence/zero flags, never an individual's numeric grade."""
    if isinstance(value, list):
        return [public_cell_values(row) for row in value]
    if not isinstance(value, dict):
        return value
    result = {}
    for key, child in value.items():
        if key in {"score", "source_score", "current_score", "winner_score"}:
            result[key + "_present"] = child is not None
            result[key + "_is_zero"] = child is not None and float(child) == 0
        else:
            result[key] = public_cell_values(child)
    return result
