"""Pinned sequential packs and real workflow Bash: ciphertext-only, bounded failure."""

import base64
import copy
import importlib.util
import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "scripts/ops/journal_export_pack.py"
spec = importlib.util.spec_from_file_location("journal_pack_tests", PATH)
pack = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pack)
HEAD = "a" * 40


def envelope():
    return json.dumps(
        {
            "format": "wcu-workload-envelope/1",
            "cipher": "AES-256-GCM+RSA-OAEP-SHA256",
            "key_sha256": pack.KEY_SHA,
            "nonce": base64.b64encode(b"n" * 12).decode(),
            "wrapped_key": base64.b64encode(b"w" * 384).decode(),
            "ciphertext": base64.b64encode(b"c" * 16).decode(),
        }
    ).encode()


class PackTests(unittest.TestCase):
    def test_exact_registry_caps_and_priority(self):
        values = pack.packs()
        flat = [label for group in values.values() for label in group]
        self.assertEqual((len(values), len(flat), len(set(flat))), (19, 91, 91))
        self.assertLessEqual(max(map(len, values.values())), 5)
        self.assertEqual(flat[:8], [f"chair-cells-{n:03}" for n in (1, 2, 89, 43, 76, 77, 82, 55)])
        with self.assertRaises(pack.PackError):
            pack.pack_batches("journal-pack-001;id")

    def capture(self, folder, *, name="journal-pack-001", failed=None, raw=False, offerings=20, extra=False):
        calls = []
        encoded = envelope()

        def command(argv):
            calls.append(argv)
            if argv[1] == "exec":
                batch = argv[argv.index("--batch") + 1]
                if batch == failed:
                    return SimpleNamespace(
                        returncode=1,
                        stdout="PRIVATE_SENTINEL",
                        stderr="CommandError: history_course_budget_exceeded_split_batch\n",
                    )
                return SimpleNamespace(
                    returncode=0,
                    stdout=f"encrypted_sha256={pack.sha(encoded)} offerings={offerings} marks=30\n",
                    stderr="",
                )
            Path(argv[-1]).write_bytes(b"PRIVATE_SENTINEL" if raw else encoded)
            if extra:
                (folder / "notes.txt").write_text("PRIVATE_SENTINEL")
            return SimpleNamespace(returncode=0)

        output = io.StringIO()
        with patch.object(pack, "_command", side_effect=command), redirect_stdout(output):
            result = pack.run_pack(
                name=name,
                actor="audit_operator",
                container="audit-app",
                export_dir="/tmp/export",
                folder=folder,
                head=HEAD,
                run_id=12,
                attempt=1,
            )
        return result, json.loads((folder / "pack-manifest.json").read_text()), calls, output.getvalue()

    def test_sequential_complete_hashes_and_no_raw_output(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            result, manifest, calls, output = self.capture(folder)
            self.assertEqual(result, 0)
            self.assertTrue(manifest["complete"])
            self.assertEqual([c[1] for c in calls], ["exec", "cp", "exec", "cp"])
            for row in manifest["batches"]:
                self.assertEqual(pack.envelope_digest(folder / row["file"]), row["sha256"])
                self.assertEqual((folder / row["file"]).stat().st_mode & 0o777, 0o600)
            self.assertIn("manifest_sha256=" + pack.sha((folder / "pack-manifest.json").read_bytes()), output)
            self.assertNotIn("audit_operator", output)

    def test_partial_failure_continues_and_retains_only_completed_ciphertext(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            result, value, calls, output = self.capture(folder, name="journal-pack-002", failed="chair-cells-043")
            self.assertEqual((result, value["status"], value["complete"]), (2, "partial", False))
            self.assertEqual(sum(row["status"] == "complete" for row in value["batches"]), 4)
            self.assertEqual(len([c for c in calls if c[1] == "exec"]), 5)
            self.assertEqual(len(list(folder.iterdir())), 5)
            self.assertNotIn("PRIVATE_SENTINEL", output + json.dumps(value))
            self.assertIn("history_course_budget_exceeded_split_batch", json.dumps(value))

    def test_raw_copy_and_over_cap_never_become_artifacts(self):
        for kwargs in ({"raw": True}, {"offerings": 26}):
            with self.subTest(kwargs=kwargs), tempfile.TemporaryDirectory() as directory:
                folder = Path(directory)
                result, value, _, output = self.capture(folder, **kwargs)
                self.assertEqual(result, 2)
                self.assertEqual(list(folder.iterdir()), [folder / "pack-manifest.json"])
                self.assertFalse(value["complete"])
                self.assertNotIn("PRIVATE_SENTINEL", output)

    def test_unknown_file_suppresses_upload(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "cipher"
            folder.mkdir()
            github_output = Path(directory) / "output"
            with patch.dict(os.environ, GITHUB_OUTPUT=str(github_output)):
                with self.assertRaises(pack.PackError):
                    self.capture(folder, extra=True)
            self.assertTrue(github_output.read_text().endswith("pack_artifact_ready=false\n"))

    def test_manifest_rejects_traversal_false_completion_private_fields_and_wrong_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            _, original, _, _ = self.capture(Path(directory))
        changes = [
            lambda v: v.update(head_sha="b" * 40),
            lambda v: v.update(complete=False),
            lambda v: v.update(notes="PRIVATE_SENTINEL"),
            lambda v: v["batches"][0].update(file="../raw.json"),
            lambda v: v["batches"][0].update(offerings=True),
            lambda v: v["batches"].reverse(),
            lambda v: v["batches"][0].update(marks=250001),
        ]
        for change in changes:
            value = copy.deepcopy(original)
            change(value)
            with self.assertRaises(pack.PackError):
                pack.validate_manifest(value, expected_pack="journal-pack-001", expected_head=HEAD)

    def test_interrupted_copy_never_enters_upload_directory(self):
        for partial in (True, False):
            with self.subTest(partial=partial), tempfile.TemporaryDirectory() as directory:
                folder = Path(directory) / "approved"
                folder.mkdir()
                encoded = envelope()
                calls = []

                def command(argv, encoded=encoded, calls=calls, partial=partial):
                    if argv[1] == "exec":
                        return SimpleNamespace(
                            returncode=0,
                            stdout=f"encrypted_sha256={pack.sha(encoded)} offerings=20 marks=30\n",
                            stderr="",
                        )
                    target = Path(argv[-1])
                    calls.append(target)
                    if len(calls) == 2:
                        target.write_bytes(b"PRIVATE_SENTINEL" if partial else encoded)
                        raise SystemExit("simulated abrupt stop")
                    target.write_bytes(encoded)
                    return SimpleNamespace(returncode=0)

                with patch.object(pack, "_command", side_effect=command):
                    with self.assertRaises(SystemExit):
                        pack.run_pack(
                            name="journal-pack-001",
                            actor="audit_operator",
                            container="app",
                            export_dir="/tmp/export",
                            folder=folder,
                            head=HEAD,
                            run_id=12,
                            attempt=1,
                        )
                value = pack.finalize(name="journal-pack-001", folder=folder, head=HEAD, run_id=12, attempt=1)
                self.assertFalse(value["complete"])
                self.assertEqual([r["status"] for r in value["batches"]], ["complete", "not_attempted"])
                self.assertTrue(all(p.parent != folder for p in calls))
                self.assertNotIn(b"PRIVATE_SENTINEL", b"".join(p.read_bytes() for p in folder.glob("*.enc.json")))
                self.assertEqual(len(list(folder.glob("*.enc.json"))), 1)

    def test_interruption_after_approve_before_manifest_refuses_upload(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "approved"
            folder.mkdir()
            original = pack.save_manifest
            counter = []

            def save(value, target):
                counter.append(True)
                if len(counter) == 2:
                    raise SystemExit("before manifest commit")
                return original(value, target)

            with patch.object(pack, "save_manifest", side_effect=save):
                with self.assertRaises(SystemExit):
                    self.capture(folder)
            with self.assertRaises(pack.PackError):
                pack.finalize(name="journal-pack-001", folder=folder, head=HEAD, run_id=12, attempt=1)

    def test_finalizer_rejects_changed_ciphertext_and_symlinks(self):
        for symlink in (False, True):
            with self.subTest(symlink=symlink), tempfile.TemporaryDirectory() as directory:
                folder = Path(directory) / "approved"
                folder.mkdir()
                self.capture(folder)
                target = next(folder.glob("*.enc.json"))
                if symlink:
                    target.unlink()
                    target.symlink_to(folder / "pack-manifest.json")
                else:
                    target.write_text("PRIVATE_SENTINEL")
                with self.assertRaises(pack.PackError):
                    pack.finalize(name="journal-pack-001", folder=folder, head=HEAD, run_id=12, attempt=1)


class WorkflowTests(unittest.TestCase):
    def test_event_mask_and_strict_selectors_before_environment_export(self):
        for inputs, valid in [
            ({"actor": "audit_operator"}, True),
            ({"actor": "audit_operator", "journal_batch": "chair-cells-001"}, True),
            ({"actor": "audit_operator", "journal_pack": "journal-pack-001"}, True),
            (
                {"actor": "audit_operator", "journal_batch": "chair-cells-001", "journal_pack": "journal-pack-001"},
                False,
            ),
            ({"actor": "operator\nINJECT=x"}, False),
            ({"actor": "$(id)"}, False),
            ({"actor": "audit_operator", "journal_pack": "journal-pack-020"}, False),
            ({"actor": "audit_operator", "journal_batch": "chair-cells-001\n"}, False),
        ]:
            with self.subTest(inputs=inputs), tempfile.TemporaryDirectory() as directory:
                event, env = Path(directory) / "event", Path(directory) / "env"
                event.write_text(json.dumps({"inputs": inputs, "private": "PRIVATE_SENTINEL"}))
                result = subprocess.run(
                    ["python3", "scripts/ops/journal_export_inputs.py"],
                    cwd=ROOT,
                    env={**os.environ, "GITHUB_EVENT_PATH": str(event), "GITHUB_ENV": str(env)},
                    text=True,
                    capture_output=True,
                )
                self.assertEqual(result.returncode == 0, valid)
                self.assertNotIn("PRIVATE_SENTINEL", result.stdout + result.stderr)
                if valid:
                    self.assertTrue(result.stdout.startswith("::add-mask::audit_operator\n"))
                    self.assertIn("journal_export_selection: pack=", result.stdout)
                    self.assertIn("ACTOR=audit_operator\n", env.read_text())
                else:
                    self.assertFalse(env.exists())
                    self.assertNotIn("INJECT", result.stdout + result.stderr)

    def test_real_capture_bash_pack_partial_and_legacy_routes(self):
        workflow = yaml.safe_load((ROOT / ".github/workflows/workload-scoped-export.yml").read_text())
        job = workflow["jobs"]["export"]
        self.assertEqual(set(job["env"]), {"APP_CONTAINER", "EXPORT_DIR"})
        steps = job["steps"]
        capture = next(s["run"] for s in steps if s.get("id") == "capture")
        uploads = [s for s in steps if "upload-artifact@" in s.get("uses", "")]
        self.assertEqual(len(uploads), 2)
        self.assertIn("always()", uploads[0]["if"])
        self.assertIn("steps.pack_finalize.outputs.pack_artifact_ready", uploads[0]["if"])
        finalizer = next(s for s in steps if s.get("id") == "pack_finalize")
        self.assertIn("always()", finalizer["if"])
        self.assertIn("--finalize", finalizer["run"])
        self.assertEqual(
            uploads[0]["with"]["path"].splitlines(),
            [
                "${{ runner.temp }}/wcu-workload-export/*.enc.json",
                "${{ runner.temp }}/wcu-workload-export/pack-manifest.json",
            ],
        )
        for batch, name, fail in [
            ("", "", ""),
            ("chair-cells-001", "", ""),
            ("", "journal-pack-001", ""),
            ("", "journal-pack-002", "chair-cells-043"),
        ]:
            with self.subTest(batch=batch, pack=name, failure=fail), tempfile.TemporaryDirectory() as directory:
                folder = Path(directory)
                fake = folder / "docker"
                fake.write_text(
                    "#!/usr/bin/env python3\nimport os,sys,json,hashlib\nfrom pathlib import Path\na=sys.argv[1:]\n"
                    "if a[0]=='exec' and 'manage.py' in a:\n"
                    " b=a[a.index('--batch')+1] if '--batch' in a else 'metadata'\n"
                    " if b==os.environ.get('FAIL_BATCH'): print('PRIVATE_SENTINEL',file=sys.stderr);print('CommandError: history_course_budget_exceeded_split_batch',file=sys.stderr);sys.exit(2)\n"
                    " raw=Path(os.environ['ENVELOPE']).read_bytes();target=Path(os.environ['REMOTE'])/Path(a[a.index('--output')+1]).name;target.write_bytes(raw)\n"
                    " print('encrypted_sha256='+hashlib.sha256(raw).hexdigest()+' offerings=20 marks=30')\n"
                    "elif a[0]=='cp' and a[1].startswith('audit-app:'):\n"
                    " Path(a[2]).write_bytes((Path(os.environ['REMOTE'])/Path(a[1]).name).read_bytes())\n"
                )
                fake.chmod(0o700)
                remote = folder / "remote"
                remote.mkdir()
                encoded = folder / "fixture"
                encoded.write_bytes(envelope())
                result = subprocess.run(
                    ["bash", "-c", capture],
                    cwd=ROOT,
                    env={
                        **os.environ,
                        "PATH": directory + os.pathsep + os.environ["PATH"],
                        "RUNNER_TEMP": directory,
                        "APP_CONTAINER": "audit-app",
                        "ACTOR": "audit_operator",
                        "EXPORT_DIR": "/tmp/export",
                        "JOURNAL_BATCH": batch,
                        "JOURNAL_PACK": name,
                        "GITHUB_SHA": HEAD,
                        "GITHUB_RUN_ID": "12",
                        "GITHUB_RUN_ATTEMPT": "1",
                        "GITHUB_OUTPUT": str(folder / "output"),
                        "ENVELOPE": str(encoded),
                        "REMOTE": str(remote),
                        "FAIL_BATCH": fail,
                    },
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 2 if fail else 0, result.stderr)
                self.assertNotIn("PRIVATE_SENTINEL", result.stdout + result.stderr)
                target = folder / "wcu-workload-export"
                if name:
                    github_output = folder / "output"
                    self.assertFalse(github_output.exists())
                    final_env = {
                        **os.environ,
                        "RUNNER_TEMP": directory,
                        "JOURNAL_PACK": name,
                        "GITHUB_SHA": HEAD,
                        "GITHUB_RUN_ID": "12",
                        "GITHUB_RUN_ATTEMPT": "1",
                        "GITHUB_OUTPUT": str(github_output),
                    }
                    finalized = subprocess.run(
                        ["bash", "-c", finalizer["run"]], cwd=ROOT, env=final_env, capture_output=True, text=True
                    )
                    self.assertEqual(finalized.returncode, 0, finalized.stderr)
                    self.assertEqual(github_output.read_text(), "pack_artifact_ready=true\n")
                    github_output.unlink()
                    approved = next(target.glob("*.enc.json"))
                    saved = approved.read_bytes()
                    approved.write_text("PRIVATE_SENTINEL")
                    refused = subprocess.run(
                        ["bash", "-c", finalizer["run"]], cwd=ROOT, env=final_env, capture_output=True, text=True
                    )
                    self.assertNotEqual(refused.returncode, 0)
                    self.assertFalse(github_output.exists())
                    self.assertNotIn("PRIVATE_SENTINEL", refused.stdout + refused.stderr)
                    approved.write_bytes(saved)
                    value = json.loads((target / "pack-manifest.json").read_text())
                    self.assertEqual(value["complete"], not bool(fail))
                    self.assertEqual(
                        set(p.name for p in target.iterdir()),
                        {"pack-manifest.json"} | {r["file"] for r in value["batches"] if r["status"] == "complete"},
                    )
                else:
                    self.assertTrue((target / "snapshot.enc.json").is_file())
