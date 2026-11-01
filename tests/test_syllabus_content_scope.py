"""Offline text-free scope rejects schema injection and incomplete/foreign root evidence."""

import copy
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/ops/syllabus_content_scope.py"


def validator():
    spec = importlib.util.spec_from_file_location("syllabus_content_scope_pure", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SyllabusScopeTests(unittest.TestCase):
    def setUp(self):
        self.v = validator()
        selected = json.loads(self.v.REGISTRY_PATH.read_text())["batches"]["chair-cells-001"]
        data = {key: [] for key in self.v.SCHEMAS}
        for pin in selected["offerings"]:
            data["roots"].append(
                {
                    "organization_id": self.v.ORG,
                    "offering_id": pin["id"],
                    "selected_syllabus_id": None,
                    "current_version_id": None,
                    "stored_approved_version_id": None,
                    "effective_approved_version_id": None,
                    "relation": "none",
                    "lookup_complete": True,
                    "base_candidates_complete": True,
                    "base_candidate_count": 0,
                }
            )
            data["offerings"].append(
                {
                    "id": pin["id"],
                    "organization_id": self.v.ORG,
                    "subject_id": "11111111-1111-1111-1111-111111111111",
                    "period_id": self.v.PERIOD,
                    "group_id": None,
                    "instructor_id": None,
                    "lesson_hours": 0,
                    "is_active": True,
                }
            )
        self.payload = {
            "format": self.v.FORMAT,
            "organization_id": self.v.ORG,
            "academic_year": "2026/2027",
            "period_id": self.v.PERIOD,
            "batch": "chair-cells-001",
            "registry_sha256": self.v.REGISTRY_SHA,
            "captured_at": "2026-11-01T00:00:00Z",
            "actor_id": 1,
            "read_only": True,
            "eligible_for_apply": False,
            "selection": selected,
            "coverage": {
                "lookup_complete": True,
                "closure_complete": True,
                "truncated": False,
                "canonical_hash_policy": self.v.POLICY,
                "body_scope": "selected_owned_current_approved_ancestry",
                "base_candidates_metadata_only": True,
                "root_count": len(selected["offerings"]),
                "course_context_count": len(selected["offerings"]),
                "absence_claim": False,
                "automatic_content_verdict": False,
            },
            "data": data,
            "counts": {key: len(rows) for key, rows in data.items()},
            "schema_fields": {key: sorted({k for r in rows for k in r}) for key, rows in data.items()},
        }

    def test_real_registry_root_set_valid_and_not_an_absence_claim(self):
        self.v.validate(self.payload)
        self.assertFalse(self.payload["coverage"]["absence_claim"])

    def test_extra_raw_text_and_foreign_tenant_are_rejected(self):
        for mutate in (
            lambda p: p["data"]["offerings"][0].update(email="PRIVATE_CONTACT"),
            lambda p: p["data"]["offerings"][0].update(organization_id="22222222-2222-2222-2222-222222222222"),
        ):
            p = copy.deepcopy(self.payload)
            mutate(p)
            with self.assertRaises(ValueError):
                self.v.validate(p)

    def test_unproven_missing_selection_and_wrong_registry_are_rejected(self):
        for mutate in (
            lambda p: p["data"]["roots"][0].update(selected_syllabus_id="22222222-2222-2222-2222-222222222222"),
            lambda p: p.update(registry_sha256="0" * 64),
            lambda p: p["selection"]["offerings"][0].update(id="22222222-2222-2222-2222-222222222222"),
        ):
            p = copy.deepcopy(self.payload)
            mutate(p)
            with self.assertRaises(ValueError):
                self.v.validate(p)

    def test_false_complete_flags_and_boolean_counts_are_rejected(self):
        for mutate in (
            lambda p: p["data"]["roots"][0].update(lookup_complete=False),
            lambda p: p["coverage"].update(absence_claim=0),
            lambda p: p["counts"].update(topics=False),
        ):
            p = copy.deepcopy(self.payload)
            mutate(p)
            with self.assertRaises(ValueError):
                self.v.validate(p)

    def test_duplicate_context_ids_and_schema_keys_are_rejected(self):
        p = copy.deepcopy(self.payload)
        p["data"]["offerings"].append(copy.deepcopy(p["data"]["offerings"][0]))
        p["counts"]["offerings"] += 1
        p["coverage"]["course_context_count"] += 1
        with self.assertRaises(ValueError):
            self.v.validate(p)
        p = copy.deepcopy(self.payload)
        p["schema_fields"]["roots"].append("organization_id")
        with self.assertRaises(ValueError):
            self.v.validate(p)

    def test_unknown_format_and_untyped_timestamp_are_rejected(self):
        for mutate in (
            lambda p: p.update(format="wcu-workload-snapshot/1"),
            lambda p: p.update(captured_at="PRIVATE_EMAIL"),
        ):
            p = copy.deepcopy(self.payload)
            mutate(p)
            with self.assertRaises(ValueError):
                self.v.validate(p)
