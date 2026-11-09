"""Synthetic, offline guard tests; never dispatch or read production keys/data."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import capture_syllabus_single as runner


def run_row(number=123):
    return {
        "id": number,
        "head_sha": runner.shared.HEAD,
        "event": "workflow_dispatch",
        "head_branch": "main",
        "path": ".github/workflows/" + runner.WORKFLOW,
        "created_at": "2026-11-09T01:00:00Z",
        "run_attempt": 1,
        "conclusion": "success",
    }


def manifest():
    return {
        "format": "wcu-syllabus-content-capture/1",
        "head_sha": runner.shared.HEAD,
        "run_id": 123,
        "run_attempt": 1,
        "batch": runner.BATCHES[0],
        "registry_sha256": runner.single.REGISTRY_SHA,
        "encrypted_sha256": "a" * 64,
        "file": "snapshot.enc.json",
        "eligible_for_apply": False,
    }


class SingleCaptureTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.folder = Path(self.directory.name)
        self.folder.chmod(0o700)

    def tearDown(self):
        self.directory.cleanup()

    def test_default_is_offline_and_strict_selection(self):
        with (
            patch.object(runner, "HERE", self.folder),
            patch.object(runner.shared, "api", side_effect=AssertionError("network")),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            runner.main(["--private-dir", str(self.folder)])
        result = json.loads((self.folder / "syllabus_single_capture_plan.json").read_bytes())
        self.assertIs(result["dispatch_enabled"], False)
        self.assertEqual([row["batch"] for row in result["batches"]], list(runner.BATCHES))
        for selected in ([], ["chair-cells-001"], [runner.BATCHES[0]] * 2):
            with self.assertRaisesRegex(RuntimeError, "reviewed_single_selection_required"):
                runner.plan(selected)

    def test_both_queues_must_be_terminal(self):
        journal = {f"journal-pack-{index:03}": {"state": "complete"} for index in range(1, 20)}
        runner.shared.save(self.folder / "pack-dispatches.json", journal)
        with self.assertRaisesRegex(RuntimeError, "syllabus_pack_state_missing"):
            runner.require_queues_done(self.folder)
        packs = {name: {"state": "complete", "capture_status": "partial"} for name in runner.shared.APPROVED_SELECTION}
        path = self.folder / runner.shared.STATE_FILE
        runner.shared.save(path, packs)
        runner.require_queues_done(self.folder)
        packs[runner.shared.APPROVED_SELECTION[-1]]["state"] = "running"
        runner.shared.save(path, packs)
        with self.assertRaisesRegex(RuntimeError, "syllabus_pack_queue_not_complete"):
            runner.require_queues_done(self.folder)
        journal["journal-pack-019"]["state"] = "running"
        runner.shared.save(self.folder / "pack-dispatches.json", journal)
        with self.assertRaisesRegex(RuntimeError, "journal_queue_not_complete"):
            runner.require_queues_done(self.folder)

    def test_uncertain_dispatch_is_durable_and_never_retried(self):
        state = {}
        posts = []

        def api(path, payload=None):
            if payload is not None:
                durable = json.loads((self.folder / runner.STATE_FILE).read_bytes())
                self.assertEqual(durable[runner.BATCHES[0]]["state"], "dispatch_intent")
                self.assertNotIn("synthetic_operator", json.dumps(durable))
                posts.append(path)
                raise RuntimeError("synthetic_transport_error")
            return {"object": {"sha": runner.shared.HEAD}}

        with (
            patch.object(runner, "require_queues_done"),
            patch.object(runner.shared, "require_production_queue_idle"),
            patch.object(runner.shared, "api", side_effect=api),
            patch.object(runner, "runs", return_value=[]),
            patch.object(runner.time, "sleep"),
        ):
            with self.assertRaisesRegex(RuntimeError, "synthetic_transport_error"):
                runner.process(runner.BATCHES[0], state, self.folder, "synthetic_operator", b"not-a-key")
            with self.assertRaisesRegex(RuntimeError, "unresolved_dispatch_never_repeat_post"):
                runner.process(runner.BATCHES[0], state, self.folder, "synthetic_operator", b"not-a-key")
        self.assertEqual(len(posts), 1)
        self.assertEqual((self.folder / runner.STATE_FILE).stat().st_mode & 0o777, 0o600)

    def test_exact_run_identity_and_ambiguous_dispatch(self):
        valid = run_row()
        self.assertTrue(runner.matches(valid))
        for field, value in {
            "head_sha": "0" * 40,
            "event": "push",
            "head_branch": "develop",
            "path": "wrong.yml",
            "id": True,
        }.items():
            self.assertFalse(runner.matches({**valid, field: value}))
        item = {"submitted_at": "2026-11-09T01:00:00.123456+00:00", "before_ids": []}
        with patch.object(runner, "runs", return_value=[valid, run_row(124)]):
            with self.assertRaisesRegex(RuntimeError, "ambiguous_dispatch"):
                runner.resolve_run(item, {}, self.folder / "state.json")
        old = {**valid, "created_at": "2026-11-09T00:00:00Z"}
        with patch.object(runner, "runs", return_value=[old]), patch.object(runner.time, "sleep"):
            with self.assertRaisesRegex(RuntimeError, "unresolved_dispatch"):
                runner.resolve_run(item, {}, self.folder / "state.json")

    def test_manifest_exact_identity(self):
        original = manifest()
        self.assertEqual(runner.validate_manifest(original, batch=runner.BATCHES[0], run=run_row()), original)
        invalid = {
            "format": "other",
            "head_sha": "0" * 40,
            "run_id": 124,
            "run_attempt": True,
            "batch": runner.BATCHES[1],
            "registry_sha256": "0" * 64,
            "encrypted_sha256": "invalid",
            "file": "../snapshot.enc.json",
            "eligible_for_apply": 0,
        }
        for field, value in invalid.items():
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                runner.validate_manifest({**original, field: value}, batch=runner.BATCHES[0], run=run_row())
        with self.assertRaisesRegex(RuntimeError, "schema"):
            runner.validate_manifest({**original, "actor": "not-allowed"}, batch=runner.BATCHES[0], run=run_row())

    def test_artifact_types_and_cipher_hash(self):
        runner.shared.save(self.folder / "capture-manifest.json", manifest())
        cipher = self.folder / "snapshot.enc.json"
        cipher.write_bytes(b"synthetic")
        with patch.object(runner.shared.native, "cipher", return_value="a" * 64):
            runner.checked_artifact(self.folder, batch=runner.BATCHES[0], run=run_row())
        with patch.object(runner.shared.native, "cipher", return_value="b" * 64):
            with self.assertRaisesRegex(RuntimeError, "encrypted_digest_mismatch"):
                runner.checked_artifact(self.folder, batch=runner.BATCHES[0], run=run_row())
        cipher.unlink()
        cipher.symlink_to(self.folder / "capture-manifest.json")
        with self.assertRaisesRegex(RuntimeError, "artifact_file_type_invalid"):
            runner.checked_artifact(self.folder, batch=runner.BATCHES[0], run=run_row())

    def test_existing_plaintext_not_overwritten(self):
        path = self.folder / "payload.json"
        runner.write_plaintext(path, {"synthetic": 1})
        before = path.read_bytes()
        runner.write_plaintext(path, {"synthetic": 1})
        with self.assertRaisesRegex(RuntimeError, "existing_plaintext_differs"):
            runner.write_plaintext(path, {"synthetic": 2})
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        path.unlink()
        path.symlink_to(self.folder / "missing")
        with self.assertRaisesRegex(RuntimeError, "existing_plaintext_symlink"):
            runner.write_plaintext(path, {})

    def test_plaintext_batch_and_receipt_allowlist(self):
        batch = runner.BATCHES[0]
        item = {"batch": batch, "run_id": 123}
        destination = self.folder / "syllabus-single-082"
        destination.mkdir(mode=0o700)
        encrypted = destination / "encrypted"
        encrypted.mkdir(mode=0o700)
        (encrypted / "snapshot.enc.json").write_bytes(b"synthetic")
        inventory = {"artifacts": [{"name": "wcu-syllabus-content-123-1", "expired": False, "id": 456}]}
        payload = {"batch": runner.BATCHES[1]}
        with (
            patch.object(runner.shared, "api", return_value=inventory),
            patch.object(runner, "checked_artifact", return_value=(manifest(), "b" * 64)),
            patch.object(runner.shared.decoder, "decrypt_snapshot", return_value=payload),
        ):
            with self.assertRaisesRegex(RuntimeError, "plaintext_batch_mismatch"):
                runner.capture_artifact(item, self.folder, b"not-a-key", run_row())
        self.assertFalse((destination / (batch + ".json")).exists())
        state = {batch: {**item, "actor": "synthetic_operator", "key": "synthetic_key", "before_ids": [1]}}
        with patch.object(runner, "HERE", self.folder):
            runner.safe_receipt(state)
        raw = (self.folder / "syllabus_single_capture_receipt.json").read_text()
        for forbidden in ("synthetic_operator", "synthetic_key", "before_ids"):
            self.assertNotIn(forbidden, raw)


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(SingleCaptureTests)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    runner.shared.save(
        Path(__file__).with_name("syllabus_single_runner_validation.json"),
        {
            "tests_run": result.testsRun,
            "failures": len(result.failures),
            "errors": len(result.errors),
            "passed": result.wasSuccessful(),
            "network_calls": 0,
            "workflow_dispatches": 0,
            "production_data_or_keys_read": False,
        },
    )
    raise SystemExit(0 if result.wasSuccessful() else 1)
