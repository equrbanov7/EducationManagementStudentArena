"""Pure crypto/local-file checks, runnable with unittest without PostgreSQL."""

import base64
import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PATH = Path(__file__).resolve().parents[1] / "scripts/ops/decrypt_workload_snapshot.py"
SPEC = importlib.util.spec_from_file_location("snapshot_decrypt", PATH)
decoder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(decoder)


class DecryptSnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        cls.private = cls.key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
        der = cls.key.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        cls.fingerprint = hashlib.sha256(der).hexdigest()

    def envelope(self, **changes):
        payload = {
            "format": "wcu-workload-snapshot/1",
            "organization_id": decoder.ORG,
            "academic_year": "2026/2027",
            **changes,
        }
        metadata = {
            "format": "wcu-workload-envelope/1",
            "cipher": "AES-256-GCM+RSA-OAEP-SHA256",
            "key_sha256": self.fingerprint,
        }
        key, nonce = AESGCM.generate_key(bit_length=256), b"fake-nonce12"
        # 12bytes required; this deterministic nonce is used with a fresh random test key.
        nonce = nonce.ljust(12, b"0")
        wrapped = self.key.public_key().encrypt(
            key, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
        )
        cipher = AESGCM(key).encrypt(nonce, json.dumps(payload).encode(), json.dumps(metadata, sort_keys=True).encode())
        return {
            **metadata,
            "nonce": base64.b64encode(nonce).decode(),
            "wrapped_key": base64.b64encode(wrapped).decode(),
            "ciphertext": base64.b64encode(cipher).decode(),
        }

    def test_authenticated_scope_and_tampering(self):
        env = self.envelope()
        with patch.object(decoder, "KEY_FINGERPRINT", self.fingerprint):
            payload = decoder.decrypt_snapshot(json.dumps(env).encode(), self.private)
            self.assertEqual(payload["organization_id"], decoder.ORG)
            env["ciphertext"] = base64.b64encode(b"corrupt cipher").decode()
            with self.assertRaises(InvalidTag):
                decoder.decrypt_snapshot(json.dumps(env).encode(), self.private)
            with self.assertRaisesRegex(ValueError, "scope"):
                decoder.decrypt_snapshot(
                    json.dumps(self.envelope(organization_id="OTHER_TENANT")).encode(), self.private
                )

    def test_new_dated_private_files_do_not_replace_old_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = Path(tmp) / "ems_prod_1027.json"
            old.write_text("untouched")
            a = decoder.write_new_snapshot({"safe": 1}, tmp)
            b = decoder.write_new_snapshot({"safe": 2}, tmp)
            self.assertNotEqual(a, b)
            self.assertEqual(a.stat().st_mode & 0o777, 0o600)
            self.assertEqual(old.read_text(), "untouched")

    def history_payload(self):
        spec = importlib.util.spec_from_file_location("history_scope", PATH.with_name("workload_history_scope.py"))
        scope = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(scope)
        row = dict.fromkeys(scope.FIELDS)
        row.update(
            model_label="workload.TeachingTaskRow",
            id=scope.ROW,
            organization_id=scope.ORG,
            created_at="2026-11-01T03:00:00Z",
            updated_at="2026-11-01T03:00:00Z",
            foreign_keys={"organization_id": scope.ORG, "task_id": scope.TASK},
            foreign_key_models={"organization_id": "organizations.Organization", "task_id": "workload.TeachingTask"},
            material={"total_hours": 45},
            old_material={},
            new_material={},
            raw_record_sha256="1" * 64,
            note_present=False,
            document_present=False,
        )
        declaration = dict(
            organization_id=scope.ORG,
            task_id=scope.TASK,
            row_id=scope.ROW,
            expected_assignment_ids=sorted(scope.ASSIGNMENTS),
            actual_assignment_ids=[],
            root_present=True,
            closure_rows=1,
            typed_metadata_only=True,
            automatic_apply_authority=False,
        )
        return {
            "data": {"repair_math_history": [row], "repair_math_history_scope": [declaration]},
            "schema_fields": {
                "repair_math_history": sorted(scope.FIELDS),
                "repair_math_history_scope": sorted(scope.SCOPE_FIELDS),
            },
        }

    def test_old_41_section_and_additive_math_history_payloads_roundtrip(self):
        old = {"data": {f"existing_section_{i}": [] for i in range(41)}}
        for extra in (old, self.history_payload()):
            with (
                self.subTest(history="repair_math_history" in extra["data"]),
                patch.object(decoder, "KEY_FINGERPRINT", self.fingerprint),
            ):
                result = decoder.decrypt_snapshot(json.dumps(self.envelope(**extra)).encode(), self.private)
                self.assertEqual(result["data"], extra["data"])

    def test_math_history_decoder_rejects_raw_json_notes_scope_and_closure_tampering(self):
        original = self.history_payload()
        cases = []
        value = copy.deepcopy(original)
        value["data"]["repair_math_history"][0]["old_material"] = {"note": "PRIVATE"}
        cases.append(value)
        value = copy.deepcopy(original)
        value["data"]["repair_math_history"][0]["raw_note"] = "PRIVATE"
        cases.append(value)
        value = copy.deepcopy(original)
        value["data"]["repair_math_history"][0]["material"] = {"phone": 123456789}
        cases.append(value)
        value = copy.deepcopy(original)
        value["data"]["repair_math_history"][0]["created_at"] = "PRIVATE"
        cases.append(value)
        value = copy.deepcopy(original)
        value["data"]["repair_math_history"][0]["organization_id"] = "FOREIGN"
        cases.append(value)
        value = copy.deepcopy(original)
        value["data"]["repair_math_history_scope"][0]["automatic_apply_authority"] = True
        cases.append(value)
        value = copy.deepcopy(original)
        value["data"]["repair_math_history"][0]["id"] = "00000000-0000-4000-8000-000000000000"
        cases.append(value)
        value = copy.deepcopy(original)
        del value["data"]["repair_math_history_scope"]
        cases.append(value)
        for extra in cases:
            with self.subTest(extra=cases.index(extra)), patch.object(decoder, "KEY_FINGERPRINT", self.fingerprint):
                with self.assertRaisesRegex(ValueError, "math_history"):
                    decoder.decrypt_snapshot(json.dumps(self.envelope(**extra)).encode(), self.private)


class ExportWorkflowTests(unittest.TestCase):
    def test_manual_only_fixed_command_encrypted_artifact(self):
        import yaml

        path = PATH.parents[2] / ".github/workflows/workload-scoped-export.yml"
        workflow = yaml.safe_load(path.read_text())
        triggers = workflow.get("on", workflow.get(True))
        self.assertEqual(set(triggers), {"workflow_dispatch"})
        self.assertEqual(set(triggers["workflow_dispatch"]["inputs"]), {"actor", "journal_batch", "journal_pack"})
        self.assertEqual(triggers["workflow_dispatch"]["inputs"]["journal_batch"]["default"], "")
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        self.assertEqual(workflow["concurrency"]["group"], "production-deploy")
        steps = workflow["jobs"]["export"]["steps"]
        upload = next(x for x in steps if x.get("with", {}).get("name", "").startswith("wcu-workload-snapshot-"))
        self.assertEqual(upload["with"]["retention-days"], 1)
        self.assertTrue(upload["with"]["path"].endswith("/snapshot.enc.json"))
        self.assertNotIn("pg_dump", json.dumps(workflow))
        self.assertNotIn("bypass_rls", json.dumps(workflow))

    def test_pinned_batch_routes_only_reviewed_command_and_rejects_shell_or_unbounded_input(self):
        import yaml

        root = PATH.parents[2]
        workflow = yaml.safe_load((root / ".github/workflows/workload-scoped-export.yml").read_text())
        script = next(
            step["run"] for step in workflow["jobs"]["export"]["steps"] if step.get("name", "").startswith("Read fixed")
        )
        for batch in ("", "chair-cells-001", "../all", "chair-cells-001\n", "$(id)"):
            with self.subTest(batch=batch), tempfile.TemporaryDirectory() as folder:
                directory = Path(folder)
                docker = directory / "docker"
                docker.write_text(
                    "#!/usr/bin/env python3\nimport json,os,sys\nfrom pathlib import Path\n"
                    "args=sys.argv[1:]\n"
                    "if 'manage.py' in args: Path(os.environ['ARG_LOG']).write_text(json.dumps(args))\n"
                    "if len(args)>2 and args[0]=='cp' and args[1].startswith('audit-app:'): Path(args[2]).write_text('encrypted-fixture')\n"
                )
                docker.chmod(0o700)
                log = directory / "arguments.json"
                result = subprocess.run(
                    ["bash", "-c", script],
                    cwd=root,
                    env={
                        **os.environ,
                        "PATH": folder + os.pathsep + os.environ["PATH"],
                        "RUNNER_TEMP": folder,
                        "APP_CONTAINER": "audit-app",
                        "ACTOR": "audit-admin",
                        "EXPORT_DIR": "/tmp/fixed-audit",
                        "JOURNAL_BATCH": batch,
                        "JOURNAL_PACK": "",
                        "ARG_LOG": str(log),
                    },
                    capture_output=True,
                    text=True,
                )
                if batch in ("", "chair-cells-001"):
                    self.assertEqual(result.returncode, 0, result.stderr)
                    args = json.loads(log.read_text())
                    command = "export_wcu_journal_cells" if batch else "export_wcu_workload_snapshot"
                    self.assertIn(command, args)
                    self.assertEqual("--batch" in args, bool(batch))
                    self.assertTrue((directory / "wcu-workload-export/snapshot.enc.json").is_file())
                else:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(log.exists())


class StudentSetTokenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = PATH.parents[2] / "apps/workload/services/scoped_snapshot/roster_tokens.py"
        spec = importlib.util.spec_from_file_location("snapshot_roster_tokens", path)
        cls.tokens = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.tokens)

    def convert(self, records, secret=b"x" * 32):
        return self.tokens.tokenize(
            records, secret=secret, organization=decoder.ORG, group_fields=("group_id", "status")
        )

    def test_overlap_stable_only_within_one_snapshot_and_deduplicated(self):
        rows = [
            {"group_id": g, "status": "enrolled", "student_id": i}
            for g, i in [("233KE", 101), ("233KEaz", 101), ("233KEaz", 101), ("233KEaz", 102)]
        ]
        converted = self.convert(rows)
        self.assertEqual(len(set(converted[0]["student_tokens"]) & set(converted[1]["student_tokens"])), 1)
        self.assertEqual([r["count"] for r in converted], [1, 2])
        self.assertNotEqual(converted, self.convert(rows, secret=b"y" * 32))
        self.assertNotIn("student_id", json.dumps(converted))

    def test_parent_children_and_english_sector_remain_distinct(self):
        groups = ["234K", "234K1", "234K2", "234King"]
        rows = [{"group_id": group, "status": "enrolled", "student_id": 101} for group in groups]
        converted = self.convert(rows)
        self.assertEqual({r["group_id"] for r in converted}, set(groups))
        self.assertEqual(len({r["student_tokens"][0] for r in converted}), 1)
        self.assertEqual(len(converted), 4)
