"""One-job orchestration uses real encrypted artifacts; no production access or writes."""

import base64
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/ops"))
import decrypt_workload_snapshot as decoder  # noqa: E402
import journal_export_pack as envelope  # noqa: E402
import own_syllabi_package as runner  # noqa: E402
import own_syllabi_package_artifacts as artifacts  # noqa: E402

HEAD = "a" * 40
RECEIPT = "11111111-2222-4333-8444-555555555555"
PRIVATE_SOURCE = b"synthetic-private-source-not-an-artifact"


def result(status="dry_run", *, baseline="a" * 64):
    value = dict(
        status=status,
        baseline=baseline,
        receipt=None if status == "dry_run" else RECEIPT,
        cases=2,
        human_drafts_preserved=2,
        versions_created=2 if status == "applied" else 0,
        versions_archived=0,
    )
    if status != "dry_run":
        value["after_baseline"] = "b" * 64
    return value


class PackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        cls.private = cls.key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
        der = cls.key.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        cls.fingerprint = artifacts.sha(der)
        payload = dict(
            format="wcu-workload-snapshot/1", organization_id=decoder.ORG, academic_year="2026/2027", data={}
        )
        metadata = dict(
            format="wcu-workload-envelope/1", cipher="AES-256-GCM+RSA-OAEP-SHA256", key_sha256=cls.fingerprint
        )
        key, nonce = AESGCM.generate_key(bit_length=256), os.urandom(12)
        wrapped = cls.key.public_key().encrypt(
            key, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
        )
        cipher = AESGCM(key).encrypt(nonce, json.dumps(payload).encode(), json.dumps(metadata, sort_keys=True).encode())
        cls.cipher = json.dumps(
            {
                **metadata,
                "nonce": base64.b64encode(nonce).decode(),
                "wrapped_key": base64.b64encode(wrapped).decode(),
                "ciphertext": base64.b64encode(cipher).decode(),
            }
        ).encode()

    @contextlib.contextmanager
    def harness(self, *, summaries=None, fail_capture=None, bad_counts=False, bad_source=False, fail_head_at=None):
        with tempfile.TemporaryDirectory() as tmp, contextlib.ExitStack() as stack:
            env = dict(
                GITHUB_RUN_ID="123",
                GITHUB_RUN_ATTEMPT="1",
                GITHUB_SHA=HEAD,
                RUNNER_TEMP=tmp,
                GITHUB_OUTPUT=str(Path(tmp) / "outputs"),
            )
            calls, remote = [], {}
            summaries = iter(
                summaries
                if summaries is not None
                else [
                    result(),
                    result("applied"),
                    result("already_present", baseline="b" * 64),
                    result("already_present", baseline="b" * 64),
                ]
            )
            heads = []

            def verify(head):
                heads.append(head)
                if fail_head_at and len(heads) == fail_head_at:
                    raise ValueError("deployed_head_changed")

            def command(argv):
                calls.append(argv)
                if "manage.py" in argv:
                    name = argv[5]
                    if name == fail_capture:
                        raise ValueError("private body must never be logged")
                    output = argv[argv.index("--output") + 1]
                    remote[output] = self.cipher
                    fields = (
                        "offerings=20 marks=0"
                        if name == "export_wcu_journal_cells"
                        else "roots=20 versions=2" if name == "export_wcu_syllabus_content" else "tasks=1 rows=2"
                    )
                    if bad_counts:
                        fields = "roots=21 versions=2"
                    return f"encrypted_sha256={artifacts.sha(self.cipher)} {fields}\n"
                if argv[:2] == ["docker", "cp"] and argv[2].startswith(runner.CONTAINER + ":"):
                    Path(argv[3]).write_bytes(remote[argv[2].split(":", 1)[1]])
                return ""

            def source(folder, _env):
                p = folder / "source.json"
                p.write_bytes(b"changed" if bad_source else PRIVATE_SOURCE)
                p.chmod(0o600)
                return p

            def operation(argv):
                calls.append(argv)
                return json.dumps(next(summaries))

            pins = {name: artifacts.sha((ROOT / name).read_bytes()) for name in runner.PINNED_FILES}
            for obj, name, replacement in (
                (runner, "verify_head", verify),
                (runner, "source_pins", lambda head: pins),
                (runner, "command", command),
                (artifacts, "command", command),
                (runner.fixed, "source", source),
                (runner.fixed, "source_command", operation),
                (runner, "write_private_source", lambda *a, **k: None),
            ):
                stack.enter_context(patch.object(obj, name, side_effect=replacement))
            stack.enter_context(patch.object(runner.fixed, "SOURCE_SHA", artifacts.sha(PRIVATE_SOURCE)))
            stack.enter_context(patch.object(artifacts, "SOURCE_SHA", artifacts.sha(PRIVATE_SOURCE)))
            stack.enter_context(patch.object(envelope, "KEY_SHA", self.fingerprint))
            yield env, calls

    def run_package(self, env, apply=True):
        with contextlib.redirect_stdout(io.StringIO()):
            return runner.execute(
                {"actor": "synthetic_actor", "apply": apply, "confirm": "APPLY" if apply else ""}, env
            )

    def test_ten_capsules_exact_order_fresh_baseline_repeat_receipt_and_real_decode(self):
        with self.harness() as (env, calls):
            value = self.run_package(env)
            self.assertEqual(value["status"], "applied_PENDING_INDEPENDENT_VERIFICATION")
            directory = artifacts.folder(env)
            artifacts.validate(directory, HEAD, require_complete=True)
            self.assertEqual(
                [e["phase"] for e in value["events"]],
                ["pre"] * 5 + ["dry", "apply", "repeat-dry", "repeat-apply"] + ["post"] * 5,
            )
            mutations = [c for c in calls if "recover_blank_draft_syllabi" in c]
            self.assertEqual(len(mutations), 4)
            self.assertNotIn("--apply", mutations[0])
            self.assertEqual(mutations[1][mutations[1].index("--baseline") + 1], "a" * 64)
            self.assertEqual(mutations[3][mutations[3].index("--baseline") + 1], "b" * 64)
            for call in calls:
                self.assertNotIn("--user", call)
                self.assertNotIn("-u", call)
            capsules = list(directory.rglob("*.enc.json"))
            self.assertEqual(len(capsules), 10)
            for file in directory.rglob("*"):
                if file.is_file():
                    self.assertNotIn(PRIVATE_SOURCE, file.read_bytes())
                    self.assertNotIn(b"synthetic_actor", file.read_bytes())
            with patch.object(decoder, "KEY_FINGERPRINT", self.fingerprint):
                decoded = decoder.decrypt_snapshot(
                    (directory / "pre/standard/snapshot.enc.json").read_bytes(), self.private
                )
            self.assertEqual(decoded["data"], {})
            self.assertFalse(directory.with_name(directory.name + "-private").exists())
            self.assertFalse(directory.with_name(directory.name + "-quarantine").exists())
            runner.finalize(env)
            self.assertIn("artifact_ready=true", Path(env["GITHUB_OUTPUT"]).read_text())

    def test_default_dry_has_no_apply_and_still_ten_capsules(self):
        with self.harness(summaries=[result(), result()]) as (env, calls):
            value = self.run_package(env, apply=False)
            self.assertEqual(value["status"], "dry_run_PENDING_INDEPENDENT_VERIFICATION")
            self.assertFalse(any("--apply" in c for c in calls))
            self.assertEqual(len(list(artifacts.folder(env).rglob("*.enc.json"))), 10)

    def test_export_failure_stops_before_any_repair_and_preserves_prior_ciphertext(self):
        with self.harness(fail_capture="export_wcu_syllabus_content") as (env, calls):
            with self.assertRaises(ValueError):
                self.run_package(env)
            self.assertFalse(any("recover_blank_draft_syllabi" in c for c in calls))
            value = artifacts.validate(artifacts.folder(env), HEAD)
            self.assertEqual(value["status"], "failed")
            self.assertEqual(len(list(artifacts.folder(env).rglob("*.enc.json"))), 3)
            self.assertEqual(calls[-1][-2:], ["--", "/tmp/wcu-blank-draft-syllabus-123-1"])

    def test_source_hash_head_and_unknown_counts_stop_before_apply(self):
        for kwargs in ({"bad_source": True}, {"bad_counts": True}, {"fail_head_at": 7}):
            with self.subTest(kwargs=kwargs), self.harness(**kwargs) as (env, calls):
                with self.assertRaises(ValueError):
                    self.run_package(env)
                self.assertFalse(any("--apply" in c for c in calls))
                value = artifacts.validate(artifacts.folder(env), HEAD)
                self.assertEqual(value["status"], "failed")

    def test_wrong_dry_or_apply_baseline_or_repeat_receipt_stops(self):
        wrong_receipt = result("already_present", baseline="b" * 64)
        wrong_receipt["receipt"] = "99999999-2222-4333-8444-555555555555"
        variants = (
            [result("already_present")],
            [result(), result("applied", baseline="c" * 64)],
            [result(), result("applied"), wrong_receipt],
        )
        for values in variants:
            with self.subTest(values=values), self.harness(summaries=values) as (env, calls):
                with self.assertRaises(ValueError):
                    self.run_package(env)
                self.assertLessEqual(sum("--apply" in c for c in calls), 1)
                self.assertEqual(
                    json.loads((artifacts.folder(env) / "package-manifest.json").read_bytes())["status"], "failed"
                )

    def test_manifest_tamper_plaintext_extra_and_symlink_block_upload(self):
        with self.harness() as (env, _calls):
            self.run_package(env)
            directory = artifacts.folder(env)
            original = (directory / "package-manifest.json").read_bytes()
            value = json.loads(original)
            value["events"][0]["counts"] = [1, 0]
            (directory / "package-manifest.json").write_text(json.dumps(value))
            with self.assertRaises(ValueError):
                runner.finalize(env)
            (directory / "package-manifest.json").write_bytes(original)
            extra = directory / "plaintext.json"
            extra.write_bytes(PRIVATE_SOURCE)
            with self.assertRaises(ValueError):
                runner.finalize(env)
            extra.unlink()
            extra.symlink_to(directory / "pre/standard/snapshot.enc.json")
            with self.assertRaises(ValueError):
                runner.finalize(env)

    def test_head_change_after_apply_keeps_receipt_and_stops_before_repeat(self):
        with self.harness(fail_head_at=9) as (env, calls):
            with self.assertRaisesRegex(ValueError, "deployed_head_changed"):
                self.run_package(env)
            value = artifacts.validate(artifacts.folder(env), HEAD)
            applied = next(e["result"] for e in value["events"] if e["phase"] == "apply")
            self.assertEqual(applied["receipt"], RECEIPT)
            self.assertEqual(sum("--apply" in c for c in calls), 1)
            self.assertEqual(value["events"][-1]["phase"], "failed")

    def test_rehashed_unknown_counts_or_phase_order_still_rejected(self):
        for change in ("counts", "phase", "status", "receipt", "pins"):
            with self.subTest(change=change), self.harness() as (env, _calls):
                self.run_package(env)
                directory = artifacts.folder(env)
                manifest = json.loads((directory / "package-manifest.json").read_bytes())
                if change == "counts":
                    manifest["events"][1]["counts"] = [21, 0]
                elif change == "phase":
                    manifest["events"][0]["phase"] = "post"
                    manifest["events"][0]["file"] = "post/standard/snapshot.enc.json"
                elif change == "status":
                    manifest["status"] = "fully_verified"
                elif change == "receipt":
                    manifest["events"][7]["result"]["receipt"] = "99999999-2222-4333-8444-555555555555"
                else:
                    manifest["source_pins"].pop(next(iter(manifest["source_pins"])))
                previous = "0" * 64
                for event in manifest["events"]:
                    event.pop("event_sha256")
                    event["previous_sha256"] = previous
                    previous = artifacts.sha(artifacts.canonical(event))
                    event["event_sha256"] = previous
                manifest["chain_sha256"] = previous
                (directory / "package-manifest.json").write_text(json.dumps(manifest))
                with self.assertRaises(ValueError):
                    runner.finalize(env)

    def test_ciphertext_mutation_and_wrong_head_block_upload(self):
        with self.harness() as (env, _calls):
            self.run_package(env)
            with self.assertRaises(ValueError):
                artifacts.validate(artifacts.folder(env), "b" * 40)
            path = artifacts.folder(env) / "pre/standard/snapshot.enc.json"
            payload = json.loads(path.read_bytes())
            payload["ciphertext"] = base64.b64encode(b"changed-valid-length-ciphertext").decode()
            path.write_text(json.dumps(payload))
            with self.assertRaises(ValueError):
                runner.finalize(env)

    def test_code_pins_are_verified_against_checkout_and_rechecked_before_each_phase(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in runner.PINNED_FILES:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("synthetic tracked source\n")

            def git(argv):
                return HEAD if argv[1] == "rev-parse" else "synthetic tracked source\n"

            with patch.object(runner, "ROOT", root), patch.object(runner, "command", side_effect=git):
                pins = runner.source_pins(HEAD)
                self.assertEqual(set(pins), set(runner.PINNED_FILES))
                (root / runner.PINNED_FILES[0]).write_text("changed source")
                with patch.object(runner, "verify_head"):
                    with self.assertRaisesRegex(ValueError, "source_pins_changed"):
                        runner.guard(HEAD, pins)
                with self.assertRaisesRegex(ValueError, "code_changed"):
                    runner.source_pins(HEAD)

    def test_main_sanitizes_exception_body_and_has_no_automatic_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            event = Path(tmp) / "event.json"
            event.write_text(json.dumps({"inputs": {"actor": "x"}}))
            output = io.StringIO()
            with (
                patch.dict(os.environ, {"GITHUB_EVENT_PATH": str(event)}),
                patch.object(sys, "argv", ["own_syllabi_package.py"]),
                patch.object(runner, "execute", side_effect=RuntimeError("private body secret actor")) as execute,
                contextlib.redirect_stderr(output),
            ):
                self.assertEqual(runner.main(), 2)
            self.assertNotIn("private body", output.getvalue())
            self.assertIn("no_automatic_retry", output.getvalue())
            self.assertEqual(execute.call_count, 1)

    def test_input_scope_is_fixed_and_apply_requires_confirmation(self):
        for value in (
            {"actor": "x", "apply": True},
            {"actor": "x", "batch": "other"},
            {"actor": "x", "undo": RECEIPT},
            {"actor": "x", "apply": 1},
        ):
            with self.assertRaises(ValueError):
                runner.inputs(value)
        self.assertEqual(runner.inputs({"actor": "x"}), ("x", False))

    def test_workflow_single_job_lock_and_finalized_cipher_only_upload(self):
        value = yaml.safe_load((ROOT / ".github/workflows/own-syllabi-v2-package.yml").read_bytes())
        event = value.get("on", value.get(True))
        self.assertEqual(set(event), {"workflow_dispatch"})
        self.assertEqual(set(event["workflow_dispatch"]["inputs"]), {"actor", "apply", "confirm"})
        self.assertFalse(event["workflow_dispatch"]["inputs"]["apply"]["default"])
        self.assertEqual(value["concurrency"], {"group": "production-deploy", "cancel-in-progress": False})
        self.assertEqual(set(value["jobs"]), {"package"})
        steps = value["jobs"]["package"]["steps"]
        upload = next(s for s in steps if "upload-artifact" in s.get("uses", ""))
        self.assertEqual(upload["if"], "always() && steps.finalize.outputs.artifact_ready == 'true'")
        self.assertEqual(upload["with"]["retention-days"], 1)
        self.assertTrue(any(s.get("if") == "always()" and "-private" in s.get("run", "") for s in steps))
