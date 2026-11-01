"""Optional six-journal typed rights contract; no database or production key."""

import ast
import copy
import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from tests import test_workload_snapshot_decrypt as crypto_fixture

PATH = Path(__file__).resolve().parents[1] / "scripts/ops/workload_contact_rights_scope.py"
SPEC = importlib.util.spec_from_file_location("contact_scope", PATH)
scope = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(scope)


class ContactRightsDecoderTests(unittest.TestCase):
    envelope = crypto_fixture.DecryptSnapshotTests.envelope

    @classmethod
    def setUpClass(cls):
        crypto_fixture.DecryptSnapshotTests.setUpClass.__func__(cls)

    def payload(self):
        oid = "86236c69-0011-46e3-88a4-0e5124290d0f"
        values = {"repair_contact_" + key: [] for key in scope.SCHEMAS}
        values["repair_contact_sources"] = [
            {"offering_id": key, **value} for key, value in sorted(scope.SOURCES.items())
        ]
        values["repair_contact_rights_scope"] = [
            {
                "organization_id": scope.ORG,
                "offering_ids": sorted(scope.SOURCES),
                "teacher_ids": sorted({uid for v in scope.SOURCES.values() for uid in v["teacher_ids"]}),
                "official_source_sha256s": sorted({v["official_source_sha256"] for v in scope.SOURCES.values()}),
                "root_offering_ids": [oid],
                "metadata_rows": 2,
                "automatic_apply_authority": False,
            }
        ]
        values["repair_contact_offerings"] = [
            {
                "id": oid,
                "organization_id": scope.ORG,
                "subject_id": "f5411cd5-510d-43bd-9093-5199ebc31ccc",
                "period_id": "a4f88744-8d49-4772-84ef-c28a96c3b372",
                "group_id": "4e5ad122-f2a9-4685-9fcb-45f4f9e05d4c",
                "instructor_id": 7885,
                "lesson_hours": 150,
                "is_active": True,
            }
        ]
        values["repair_contact_shares"] = [
            {
                "id": "00000000-0000-4000-8000-000000000001",
                "organization_id": scope.ORG,
                "offering_id": oid,
                "teacher_id": 9524,
                "source": "legacy",
                "is_active": True,
                "created_by_id": 123,
                "created_at": "2026-10-27T12:00:00Z",
                "updated_at": "2026-10-27T12:00:00Z",
                "kinds": ["seminar"],
                "kinds_valid": True,
                "kinds_sha256": "1" * 64,
                "batch_code": "shares-20261027-120000-abcd",
                "batch_present": True,
                "batch_sha256": "2" * 64,
                "enrollment_ids": [],
                "enrollments_restricted": False,
                "raw_record_sha256": "3" * 64,
                "rights_sha256": "4" * 64,
            }
        ]
        return {
            "data": values,
            "schema_fields": {
                key: sorted(scope.SCHEMAS[key.removeprefix("repair_contact_")]) if value else []
                for key, value in values.items()
            },
        }

    def decode(self, payload):
        with patch.object(crypto_fixture.decoder, "KEY_FINGERPRINT", self.fingerprint):
            return crypto_fixture.decoder.decrypt_snapshot(json.dumps(self.envelope(**payload)).encode(), self.private)

    def test_fixed_six_source_pins_and_legacy_manual_distinction(self):
        self.assertEqual(len(scope.SOURCES), 6)
        self.assertEqual(len({v["case_code"] for v in scope.SOURCES.values()}), 4)
        for source in ("legacy", "manual", "workload"):
            value = self.payload()
            value["data"]["repair_contact_shares"][0]["source"] = source
            decoded = self.decode(value)
            self.assertEqual(decoded["data"], value["data"])

    def test_producer_decoder_pins_match_exact_reviewed_six_course_source_contract(self):
        root = PATH.parents[2]
        spec = importlib.util.spec_from_file_location(
            "contact_probe", root / "apps/workload/services/scoped_snapshot/repair_contact_rights.py"
        )
        producer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(producer)
        tree = ast.parse((root / "apps/workload/services/reviewed_chair_contacts/spec.py").read_text())
        cases = next(
            ast.literal_eval(node.value)
            for node in tree.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "CASES" for target in node.targets)
        )
        expected = {
            pk: {
                "case_code": name,
                "official_source_sha256": case["source"]["sha256"],
                "teacher_ids": sorted(
                    {
                        a[side]["teacher_id"]
                        for row in case["rows"]
                        for a in row["assignments"]
                        for side in ("old", "new")
                        if a[side]
                    }
                ),
            }
            for name, case in cases.items()
            for pk in case["offerings"]
        }
        self.assertEqual(producer.SOURCES, expected)
        self.assertEqual(scope.SOURCES, expected)

    def test_old_payload_optional_and_empty_visible_roots_are_explicit(self):
        old = {"data": {f"existing_{i}": [] for i in range(41)}}
        self.assertEqual(self.decode(old)["data"], old["data"])
        value = self.payload()
        value["data"]["repair_contact_shares"] = []
        value["data"]["repair_contact_offerings"] = []
        value["data"]["repair_contact_rights_scope"][0].update(root_offering_ids=[], metadata_rows=0)
        value["schema_fields"]["repair_contact_shares"] = []
        value["schema_fields"]["repair_contact_offerings"] = []
        self.decode(value)

    def test_no_raw_notes_unknown_batch_wrong_tenant_or_new_authority(self):
        mutations = [
            lambda d: d["repair_contact_shares"][0].update(note="PRIVATE"),
            lambda d: d["repair_contact_shares"][0].update(batch_code="PRIVATE_CONTACT"),
            lambda d: d["repair_contact_shares"][0].update(organization_id="FOREIGN"),
            lambda d: d["repair_contact_rights_scope"][0].update(automatic_apply_authority=True),
            lambda d: d["repair_contact_sources"][0].update(official_source_sha256="0" * 64),
            lambda d: d.pop("repair_contact_handovers"),
        ]
        for change in mutations:
            value = copy.deepcopy(self.payload())
            change(value["data"])
            with self.assertRaisesRegex(ValueError, "contact_rights"):
                self.decode(value)
