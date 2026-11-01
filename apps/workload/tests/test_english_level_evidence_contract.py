"""Synthetic identity/privacy contracts; no real person identifiers in fixtures."""

import hashlib
import importlib.util
import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from apps.workload.services import scoped_snapshot
from apps.workload.services.english_level_evidence import contract, identity, source, spec

ROOT = Path(__file__).resolve().parents[3]


def record(pk=1, fin="AB12345"):
    return {
        "id": pk,
        "institutional_identifier": str(pk),
        "normalized_fin": fin,
        "fin_sha256": identity.fingerprint(fin),
        "fin_valid": bool(fin),
        "fin_present": bool(fin),
        "source_row_sha256": "a" * 64,
    }


def profile(uid=10, inst="1", fin="AB12345"):
    return {
        "user_id": uid,
        "institutional_identifier": inst,
        "fin": fin,
        "organization_id": spec.ORG,
    }


def output():
    records = [record(i, "") for i in range(1, 1236)]
    data = {k: [] for k in contract.SCHEMAS}
    data["identity"] = identity.resolve(records, [], {})
    return {
        "format": spec.FORMAT,
        "organization_id": spec.ORG,
        "academic_year": spec.YEAR,
        "period_id": spec.PERIOD,
        "subject_ids": list(spec.SUBJECTS),
        "source_sha256": spec.SOURCE_SHA,
        "source_namespace": "myedu_new.students.id",
        "source_ids_sha256": spec.SOURCE_IDS_SHA,
        "source_rows_sha256": "a" * 64,
        "source_captured_at": "2026-11-01T00:00:00+00:00",
        "captured_at": "2026-11-01T01:00:00+00:00",
        "actor_id": 1,
        "read_only": True,
        "eligible_for_apply": False,
        "immutable_mapping": False,
        "data": data,
        "counts": {k: len(v) for k, v in data.items()},
        "coverage": dict.fromkeys(
            "written_marks_exported raw_lesson_marks_exported identity_creates_or_mutations archive_filter_applied teacher_access_attested".split(),
            False,
        ),
    }


class IdentityTests(unittest.TestCase):
    def test_fin_exact_case_space_no_zero_or_transliteration(self):
        self.assertEqual(identity.fin(" ab12345 "), "AB12345")
        self.assertEqual(identity.fin("0000000"), "")
        self.assertEqual(identity.fin("ƏB12345"), "")
        self.assertEqual(identity.fin("ß12345"), "")
        self.assertEqual(identity.fin("ſ123456"), "")

    def test_unique_numeric_institutional(self):
        r = identity.resolve([record()], [profile(fin="")], {})[0]
        self.assertEqual(r["target_user_id"], 10)
        self.assertEqual(r["method"], "institutional")
        self.assertFalse(r["immutable_mapping"])

    def test_no_numeric_code_coercion(self):
        r = identity.resolve([record(fin="")], [profile(inst="01", fin="")], {})[0]
        self.assertIsNone(r["target_user_id"])

    def test_unique_fin_when_no_code(self):
        r = identity.resolve([record()], [profile(inst="")], {})[0]
        self.assertEqual(r["method"], "fin")
        self.assertEqual(r["target_user_id"], 10)

    def test_typed_ledger_and_code_conflict(self):
        r = identity.resolve(
            [record(fin="")],
            [profile(uid=10, fin=""), profile(uid=11, inst="", fin="")],
            {"1": {11}},
        )[0]
        self.assertIn("identity_evidence_contradiction", r["reasons"])
        self.assertIsNone(r["target_user_id"])

    def test_code_fin_conflict(self):
        r = identity.resolve(
            [record()],
            [profile(fin="CD12345"), profile(uid=11, inst="", fin="AB12345")],
            {},
        )[0]
        self.assertIn("identity_evidence_contradiction", r["reasons"])

    def test_different_fin_not_silently_ignored(self):
        r = identity.resolve([record()], [profile(fin="CD12345")], {})[0]
        self.assertIn("source_target_fin_disagrees", r["reasons"])

    def test_foreign_ledger_profile_absent_holds(self):
        r = identity.resolve([record(fin="")], [], {"1": {999}})[0]
        self.assertIn("ledger_target_outside_same_tenant_profiles", r["reasons"])
        self.assertEqual(r["same_tenant_candidate_user_ids"], [])

    def test_two_different_profiles_same_fin_hold(self):
        r = identity.resolve([record()], [profile(inst=""), profile(uid=11, inst="")], {})[0]
        self.assertIn("ambiguous_fin", r["reasons"])

    def test_duplicate_same_uid_is_not_two_people(self):
        p = profile(inst="")
        r = identity.resolve([record()], [p, p.copy()], {})[0]
        self.assertEqual(r["target_user_id"], 10)

    def test_duplicate_source_fin_no_collapse_without_strong_id(self):
        rows = identity.resolve([record(), record(2)], [profile(inst="")], {})
        self.assertTrue(all("source_identity_duplicate" in r["reasons"] and r["target_user_id"] is None for r in rows))

    def test_source_duplicate_fin_positive_unique_code_only_resolves_that_entity(self):
        rows = identity.resolve([record(), record(2)], [profile()], {})
        self.assertEqual(rows[0]["target_user_id"], 10)
        self.assertTrue(rows[0]["source_fin_duplicate"])
        self.assertIsNone(rows[1]["target_user_id"])

    def test_names_never_used(self):
        p = profile(inst="", fin="")
        p["name"] = "Same name"
        r = identity.resolve([record(fin="")], [p], {})[0]
        self.assertEqual(r["reasons"], ["no_exact_identity_match"])


class SourceAndPrivacyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.file = Path(self.tmp.name) / "source.json"
        packet = {
            "format": spec.SOURCE_FORMAT,
            "organization_id": spec.ORG,
            "academic_year": spec.YEAR,
            "period_id": spec.PERIOD,
            "namespace": "myedu_new.students.id",
            "institutional_identifier_rule": "Canonical exact ID",
            "source_container": "ems-legacy-delta-src",
            "captured_at": "2026-10-01T00:00:00+00:00",
            "source_query_sha256": "a" * 64,
            "source_rows_sha256": "a" * 64,
            "roster_proof_sha256": "a" * 64,
            "source_ids_sha256": hashlib.sha256(
                json.dumps(list(range(1, 1236)), separators=(",", ":")).encode()
            ).hexdigest(),
            "records": [record(i, "AB12345" if i == 1 else "") for i in range(1, 1236)],
        }
        self.file.write_text(json.dumps(packet))
        self.file.chmod(0o600)
        for name, value in (
            ("SOURCE_SHA", hashlib.sha256(self.file.read_bytes()).hexdigest()),
            ("SOURCE_IDS_SHA", packet["source_ids_sha256"]),
        ):
            p = patch.object(spec, name, value)
            p.start()
            self.addCleanup(p.stop)

    def test_synthetic_fixed_source_count(self):
        data = source.load(self.file, spec.SOURCE_SHA)
        self.assertEqual(len(data["records"]), 1235)
        self.assertEqual(sum(r["fin_valid"] for r in data["records"]), 1)

    def test_arbitrary_source_digest_refused(self):
        with self.assertRaises(scoped_snapshot.SnapshotError):
            source.load(self.file, "0" * 64)

    def test_source_file_must_be_private(self):
        self.file.chmod(0o644)
        with self.assertRaises(scoped_snapshot.SnapshotError):
            source.load(self.file, spec.SOURCE_SHA)

    def test_output_allowlist_and_false_authority(self):
        p = output()
        contract.validate(p)
        self.assertNotIn("AB12345", json.dumps(p))
        self.assertFalse(p["immutable_mapping"])

    def test_raw_fin_notes_or_scores_forbidden(self):
        for key, value in [
            ("fin", "AB12345"),
            ("note", "private raw note"),
            ("score", 7),
            ("file_url", "https://private.invalid/"),
        ]:
            p = output()
            p["data"]["identity"][0][key] = value
            with self.assertRaises(ValueError):
                contract.validate(p)

    def test_no_claim_immutable_or_apply(self):
        for key in ("immutable_mapping", "eligible_for_apply"):
            p = output()
            p[key] = True
            with self.assertRaises(ValueError):
                contract.validate(p)

    def test_missing_source_row_fails_closed(self):
        p = output()
        p["data"]["identity"].pop()
        p["counts"]["identity"] -= 1
        with self.assertRaises(ValueError):
            contract.validate(p)

    def test_counterfeit_source_scope_fails(self):
        p = output()
        p["period_id"] = "00000000-0000-0000-0000-000000000000"
        with self.assertRaises(ValueError):
            contract.validate(p)

    def test_missing_header_proof_and_invalid_actor_rejected(self):
        for key, value in (
            ("source_rows_sha256", None),
            ("captured_at", None),
            ("actor_id", None),
            ("actor_id", 0),
        ):
            p = output()
            p[key] = value
            with self.assertRaises(ValueError):
                contract.validate(p)

    def test_nullable_boolean_and_primary_id_rejected(self):
        for key in ("source_id", "source_fin_valid", "immutable_mapping"):
            p = output()
            p["data"]["identity"][0][key] = None
            with self.assertRaises(ValueError):
                contract.validate(p)

    def test_contradictory_resolved_identity_rejected(self):
        p = output()
        p["data"]["identity"][0]["method"] = "fin"
        with self.assertRaises(ValueError):
            contract.validate(p)

    def test_real_standalone_validator_loads_exact_schema(self):
        path = ROOT / "scripts/ops/english_level_evidence_scope.py"
        script = importlib.util.spec_from_file_location("english_level_scope_test", path)
        module = importlib.util.module_from_spec(script)
        script.loader.exec_module(module)
        self.assertEqual(module.contract().SCHEMAS, contract.SCHEMAS)
        payload = output()
        payload["raw_fin"] = "PRIVATE_SENTINEL"
        with self.assertRaises(ValueError):
            module.validate(payload)

    def test_real_crypto_roundtrip_and_tamper(self):
        path = ROOT / "scripts/ops/decrypt_english_level_evidence.py"
        s = importlib.util.spec_from_file_location("private_level_decoder", path)
        decoder = importlib.util.module_from_spec(s)
        s.loader.exec_module(decoder)
        private = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        pub = private.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        der = private.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        finger = hashlib.sha256(der).hexdigest()
        key = private.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        p = output()
        with (
            patch.object(scoped_snapshot, "KEY_FINGERPRINT", finger),
            patch.object(decoder, "KEY_FINGERPRINT", finger),
            patch.object(
                decoder,
                "validator",
                return_value=types.SimpleNamespace(MAX_BYTES=spec.MAX_BYTES, validate=contract.validate),
            ),
        ):
            envelope = scoped_snapshot.encrypt(p, pub)
            encoded = json.dumps(envelope).encode()
            self.assertEqual(decoder.decrypt_snapshot(encoded, key), p)
            envelope["ciphertext"] = "AAAA" + envelope["ciphertext"][4:]
            with self.assertRaises(InvalidTag):
                decoder.decrypt_snapshot(json.dumps(envelope).encode(), key)


if __name__ == "__main__":
    unittest.main()
