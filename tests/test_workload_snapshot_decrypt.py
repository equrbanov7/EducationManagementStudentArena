"""Pure crypto/local-file checks, runnable with unittest without PostgreSQL."""

import base64
import hashlib
import importlib.util
import json
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


class ExportWorkflowTests(unittest.TestCase):
    def test_manual_only_fixed_command_encrypted_artifact(self):
        import yaml

        path = PATH.parents[2] / ".github/workflows/workload-scoped-export.yml"
        workflow = yaml.safe_load(path.read_text())
        triggers = workflow.get("on", workflow.get(True))
        self.assertEqual(set(triggers), {"workflow_dispatch"})
        self.assertEqual(set(triggers["workflow_dispatch"]["inputs"]), {"actor"})
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        self.assertEqual(workflow["concurrency"]["group"], "production-deploy")
        steps = workflow["jobs"]["export"]["steps"]
        upload = next(x for x in steps if str(x.get("uses", "")).startswith("actions/upload-artifact@"))
        self.assertEqual(upload["with"]["retention-days"], 1)
        self.assertTrue(upload["with"]["path"].endswith("/snapshot.enc.json"))
        self.assertNotIn("pg_dump", json.dumps(workflow))
        self.assertNotIn("bypass_rls", json.dumps(workflow))


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
