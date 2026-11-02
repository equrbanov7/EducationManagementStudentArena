"""Actual independent workflow Bash, interrupted-copy privacy and masked dispatch input."""

import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml

from tests.test_journal_export_packs import envelope

ROOT = Path(__file__).resolve().parents[1]
HELPERS = ROOT / "scripts/ops"
with patch.object(sys, "path", [str(HELPERS), *sys.path]):
    spec = importlib.util.spec_from_file_location("journal_part_runtime", HELPERS / "journal_part_export.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
HEAD = "a" * 40


class JournalPartWorkflowTests(unittest.TestCase):
    def execute(self, *, fail=False, interrupt=None):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "approved"
            folder.mkdir()
            encoded = envelope()
            copies = []

            def command(argv):
                if "cat" in argv:
                    return SimpleNamespace(returncode=0, stdout=json.dumps({"sha": HEAD}))
                if argv[1] == "exec":
                    part = argv[argv.index("--part") + 1]
                    if fail and part.endswith("002"):
                        return SimpleNamespace(
                            returncode=2,
                            stdout="PRIVATE_SENTINEL",
                            stderr="CommandError: history_course_budget_exceeded_split_batch\n",
                        )
                    return SimpleNamespace(
                        returncode=0,
                        stdout=f"encrypted_sha256={runner.sha(encoded)} roots=10 offerings=20 marks=30\n",
                        stderr="",
                    )
                target = Path(argv[-1])
                copies.append(target)
                if interrupt and len(copies) == 2:
                    target.write_bytes(b"PRIVATE_SENTINEL" if interrupt == "raw" else encoded)
                    raise SystemExit("simulated interruption")
                target.write_bytes(encoded)
                return SimpleNamespace(returncode=0)

            stdout = io.StringIO()
            with patch.object(runner, "_command", side_effect=command), redirect_stdout(stdout):
                if interrupt:
                    with self.assertRaises(SystemExit):
                        runner.run_parts(
                            name="chair-cells-043",
                            actor="audit_operator",
                            container="app",
                            export_dir="/tmp/export",
                            folder=folder,
                            head=HEAD,
                            run_id=12,
                            attempt=1,
                        )
                else:
                    result = runner.run_parts(
                        name="chair-cells-043",
                        actor="audit_operator",
                        container="app",
                        export_dir="/tmp/export",
                        folder=folder,
                        head=HEAD,
                        run_id=12,
                        attempt=1,
                    )
                    self.assertEqual(result, 2 if fail else 0)
            manifest = runner.finalize(name="chair-cells-043", folder=folder, head=HEAD, run_id=12, attempt=1)
            self.assertNotIn("PRIVATE_SENTINEL", stdout.getvalue() + json.dumps(manifest))
            self.assertNotIn(b"PRIVATE_SENTINEL", b"".join(p.read_bytes() for p in folder.glob("*.enc.json")))
            self.assertTrue(all(p.parent != folder for p in copies))
            return manifest

    def test_normal_partial_and_abrupt_copy_preserve_only_approved_envelopes(self):
        self.assertTrue(self.execute()["complete"])
        self.assertEqual([r["status"] for r in self.execute(fail=True)["parts"]], ["complete", "failed"])
        for kind in ("raw", "valid"):
            self.assertEqual(
                [r["status"] for r in self.execute(interrupt=kind)["parts"]], ["complete", "not_attempted"]
            )

    def test_deployed_head_mismatch_stops_before_any_export(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            with patch.object(
                runner, "_command", return_value=SimpleNamespace(returncode=0, stdout=json.dumps({"sha": "b" * 40}))
            ) as command:
                with self.assertRaisesRegex(runner.PackError, "deployed_head_mismatch"):
                    runner.run_parts(
                        name="chair-cells-043",
                        actor="audit_operator",
                        container="app",
                        export_dir="/tmp/export",
                        folder=folder,
                        head=HEAD,
                        run_id=12,
                        attempt=1,
                    )
            self.assertEqual(len(command.call_args_list), 1)
            self.assertNotIn("manage.py", command.call_args.args[0])
            self.assertEqual(list(folder.iterdir()), [])

    def test_input_masks_before_env_and_refuses_selectors_injection(self):
        for parent, actor, valid in [
            ("chair-cells-040", "audit_operator", True),
            ("chair-cells-069", "audit_operator", True),
            ("chair-cells-070", "audit_operator", False),
            ("chair-cells-091", "audit_operator", False),
            ("chair-cells-042", "audit_operator", False),
            ("$(id)", "audit_operator", False),
            ("chair-cells-043", "bad\nINJECT=x", False),
        ]:
            with self.subTest(parent=parent), tempfile.TemporaryDirectory() as directory:
                folder = Path(directory)
                event = folder / "event"
                env = folder / "env"
                event.write_text(
                    json.dumps(
                        {"inputs": {"actor": actor, "journal_parent": parent}, "private": "PRIVATE_EVENT_SENTINEL"}
                    )
                )
                result = subprocess.run(
                    ["python3", str(HELPERS / "journal_part_inputs.py")],
                    env={**os.environ, "GITHUB_EVENT_PATH": str(event), "GITHUB_ENV": str(env)},
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode == 0, valid)
                self.assertNotIn("PRIVATE_EVENT_SENTINEL", result.stdout + result.stderr)
                if valid:
                    self.assertTrue(result.stdout.startswith("::add-mask::audit_operator\n"))
                    self.assertIn("journal_part_selection: parent=" + parent, result.stdout)
                else:
                    self.assertFalse(env.exists())

    def test_real_workflow_bash_partial_finalize_artifact_allowlist_and_cleanup(self):
        workflow = yaml.safe_load((ROOT / ".github/workflows/journal-cells-parts.yml").read_text())
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        job = workflow["jobs"]["export"]
        self.assertEqual(set(job["env"]), {"APP_CONTAINER", "EXPORT_DIR"})
        steps = job["steps"]
        capture = next(s["run"] for s in steps if s.get("id") == "capture")
        finalize = next(s for s in steps if s.get("id") == "finalize")
        upload = next(s for s in steps if "upload-artifact" in s.get("uses", ""))
        self.assertIn("always()", finalize["if"])
        self.assertIn("steps.finalize.outputs.parts_artifact_ready", upload["if"])
        self.assertEqual(
            upload["with"]["path"].splitlines(),
            [
                "${{ runner.temp }}/wcu-journal-parts/*.enc.json",
                "${{ runner.temp }}/wcu-journal-parts/part-manifest.json",
            ],
        )
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            remote = folder / "remote"
            remote.mkdir()
            encoded = folder / "fixture"
            encoded.write_bytes(envelope())
            docker = folder / "docker"
            docker.write_text(
                "#!/usr/bin/env python3\nimport os,sys,hashlib\nfrom pathlib import Path\na=sys.argv[1:]\nif a[0]=='exec' and 'cat' in a: print(__import__('json').dumps(dict(sha=os.environ['GITHUB_SHA'])))\nelif a[0]=='exec' and 'manage.py' in a:\n p=a[a.index('--part')+1]\n if p.endswith('002'): print('PRIVATE_ERROR_SENTINEL',file=sys.stderr);print('CommandError: history_course_budget_exceeded_split_batch',file=sys.stderr);sys.exit(2)\n raw=Path(os.environ['ENVELOPE']).read_bytes();(Path(os.environ['REMOTE'])/Path(a[a.index('--output')+1]).name).write_bytes(raw);print('encrypted_sha256='+hashlib.sha256(raw).hexdigest()+' roots=10 offerings=20 marks=30')\nelif a[0]=='cp' and a[1].startswith('audit-app:'): Path(a[2]).write_bytes((Path(os.environ['REMOTE'])/Path(a[1]).name).read_bytes())\n"
            )
            docker.chmod(0o700)
            env = {
                **os.environ,
                "PATH": directory + os.pathsep + os.environ["PATH"],
                "RUNNER_TEMP": directory,
                "JOURNAL_PARENT": "chair-cells-043",
                "ACTOR": "audit_operator",
                "APP_CONTAINER": "audit-app",
                "EXPORT_DIR": "/tmp/parts",
                "GITHUB_SHA": HEAD,
                "GITHUB_RUN_ID": "12",
                "GITHUB_RUN_ATTEMPT": "1",
                "GITHUB_OUTPUT": str(folder / "output"),
                "ENVELOPE": str(encoded),
                "REMOTE": str(remote),
            }
            result = subprocess.run(["bash", "-c", capture], cwd=ROOT, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertNotIn("PRIVATE_ERROR_SENTINEL", result.stdout + result.stderr)
            self.assertFalse((folder / "output").exists())
            validated = subprocess.run(
                ["bash", "-c", finalize["run"]], cwd=ROOT, env=env, capture_output=True, text=True
            )
            self.assertEqual(validated.returncode, 0, validated.stderr)
            self.assertEqual((folder / "output").read_text(), "parts_artifact_ready=true\n")
            approved = folder / "wcu-journal-parts"
            manifest = json.loads((approved / "part-manifest.json").read_text())
            self.assertFalse(manifest["complete"])
            self.assertIn(runner.sha((approved / "part-manifest.json").read_bytes()), result.stdout)
            (folder / "output").unlink()
            next(approved.glob("*.enc.json")).write_text("PRIVATE_RAW_SENTINEL")
            refused = subprocess.run(["bash", "-c", finalize["run"]], cwd=ROOT, env=env, capture_output=True, text=True)
            self.assertNotEqual(refused.returncode, 0)
            self.assertFalse((folder / "output").exists())
            cleanup = subprocess.run(
                ["bash", "-c", steps[-1]["run"]], cwd=ROOT, env=env, capture_output=True, text=True
            )
            self.assertEqual(cleanup.returncode, 0)
            self.assertFalse(approved.exists())
            self.assertFalse((folder / "wcu-journal-parts-quarantine").exists())
