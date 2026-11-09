"""Fixed native read-only snapshot command with exact deployed HEAD verification."""

import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTAINER = "educationmanagementstudentarena-app-1"
PUBLIC_SHA = "e20fe8121835f907deec3e05ea1a449758fdc6ef22a3920513516efb70bec224"
SHA = r"[a-f0-9]{40}"
ERROR_PREFIX = "reaudit_snapshot_error: "
SCOPES = ("full", "core")


class NativeSnapshotError(ValueError):
    def __init__(self, diagnostic):
        self.diagnostic = diagnostic
        super().__init__("snapshot_native_failed")


def native_command(argv, timeout=720):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    if not result.returncode:
        return result.stdout
    # Share the native fixed contract without importing Django on the runner.
    path = ROOT / "apps/legacy_import/services/reaudit_snapshot/diagnostics.py"
    spec = importlib.util.spec_from_file_location("reaudit_snapshot_diagnostics", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    lines = [line[len(ERROR_PREFIX) :] for line in result.stderr.splitlines() if line.startswith(ERROR_PREFIX)]
    if len(result.stderr) > 256 * 1024 or len(lines) != 1:
        raise ValueError("snapshot_safe_diagnostic_required")
    try:
        diagnostic = module.validate(json.loads(lines[0]))
    except (ValueError, TypeError, KeyError):
        raise ValueError("snapshot_safe_diagnostic_invalid") from None
    raise NativeSnapshotError(diagnostic)


def failure_message(exc):
    prefix = ""
    if isinstance(exc, NativeSnapshotError):
        prefix = ERROR_PREFIX + json.dumps(exc.diagnostic, sort_keys=True) + "\n"
    return prefix + "reaudit_capture_refused:" + type(exc).__name__


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(argv, timeout=30):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise ValueError("snapshot_transport_failed")
    return result.stdout


def inputs(values):
    if not isinstance(values, dict) or values.get("scope") != "reaudit":
        raise ValueError("reaudit_scope_required")
    actor, deployed = values.get("actor", ""), values.get("deployed_head", "")
    if not isinstance(actor, str) or not re.fullmatch(r"[\w.@+-]{1,150}", actor):
        raise ValueError("actor_required")
    if not isinstance(deployed, str) or not re.fullmatch(SHA, deployed):
        raise ValueError("deployed_head_required")
    scope = values.get("capture_scope", "full") or "full"
    if scope not in SCOPES:
        raise ValueError("capture_scope_required")
    return actor, deployed, scope


def verify_head(expected):
    raw = command(["docker", "exec", CONTAINER, "cat", "/app/build-info.json"])
    if json.loads(raw).get("sha") != expected:
        raise ValueError("deployed_head_changed")


def verify_artifact(folder, scope="full"):
    manifest = json.loads((folder / "manifest.json").read_bytes())
    if manifest.get("format") != "qku-reaudit-state/1" or manifest.get("complete") is not True:
        raise ValueError("complete_snapshot_required")
    if manifest.get("scope", "full") != scope:
        raise ValueError("capture_scope_changed")
    expected = {"manifest.json"}
    counts = {}
    for shard in manifest["shards"]:
        name = shard["file"]
        if not re.fullmatch(r"[a-z_]+\.[a-z_]+-[0-9]{4}\.enc\.json", name) or name in expected:
            raise ValueError("fixed_shard_path_required")
        expected.add(name)
        path = folder / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 48 * 1024 * 1024:
            raise ValueError("encrypted_shard_invalid")
        if digest(path) != shard["sha256"]:
            raise ValueError("encrypted_shard_changed")
        envelope = json.loads(path.read_bytes())
        if envelope.get("format") != "wcu-workload-envelope/1":
            raise ValueError("encrypted_envelope_required")
        counts[shard["model"]] = counts.get(shard["model"], 0) + shard["rows"]
    if {p.name for p in folder.iterdir()} != expected:
        raise ValueError("unexpected_artifact_file")
    if any(counts.get(label, 0) != table["rows"] for label, table in manifest["tables"].items()):
        raise ValueError("table_count_mismatch")
    if sum(counts.values()) != manifest["total_rows"]:
        raise ValueError("total_count_mismatch")
    return manifest


def run(env):
    actor, deployed, scope = inputs(json.loads(Path(env["GITHUB_EVENT_PATH"]).read_bytes()).get("inputs"))
    print("::add-mask::" + actor, flush=True)
    run_id, attempt = env["GITHUB_RUN_ID"], env["GITHUB_RUN_ATTEMPT"]
    if any(not re.fullmatch(r"[1-9][0-9]*", v) for v in (run_id, attempt)):
        raise ValueError("workflow_run_required")
    if not re.fullmatch(SHA, env["GITHUB_SHA"]):
        raise ValueError("tool_head_required")
    if deployed != env["GITHUB_SHA"]:
        raise ValueError("deployed_tool_head_must_match")
    verify_head(deployed)
    public = ROOT / "scripts/data/wcu_workload_export_public.pem"
    if digest(public) != PUBLIC_SHA:
        raise ValueError("fixed_public_key_required")
    base = Path(env["RUNNER_TEMP"]) / ("reaudit-" + run_id + "-" + attempt)
    base.mkdir(mode=0o700)
    output = base / "output"
    output.mkdir(mode=0o700)
    remote = "/tmp/ems-reaudit-" + run_id + "-" + attempt
    try:
        command(["docker", "exec", CONTAINER, "mkdir", "-m", "700", remote])
        command(["docker", "cp", str(public), CONTAINER + ":" + remote + "/public.pem"])
        command(["docker", "exec", CONTAINER, "mkdir", "-m", "700", remote + "/output"])
        raw = native_command(
            [
                "docker",
                "exec",
                CONTAINER,
                "python",
                "manage.py",
                "export_reaudit_state_20261109",
                "--actor",
                actor,
                "--public-key",
                remote + "/public.pem",
                "--output-dir",
                remote + "/output",
                "--scope",
                scope,
            ],
            timeout=720,
        )
        summary = json.loads(raw.strip().splitlines()[-1])
        if set(summary) != {"tables", "shards", "rows", "sha256"}:
            raise ValueError("fixed_capture_summary_required")
        verify_head(deployed)
        command(["docker", "cp", CONTAINER + ":" + remote + "/output/.", str(output)], timeout=180)
        manifest = verify_artifact(output, scope)
        if digest(output / "manifest.json") != summary["sha256"]:
            raise ValueError("manifest_changed")
        receipt = {
            "format": "qku-reaudit-transport/1",
            "scope": scope,
            "tool_head": env["GITHUB_SHA"],
            "deployed_head": deployed,
            "run_id": run_id,
            "run_attempt": attempt,
            "manifest_sha256": summary["sha256"],
            "total_rows": manifest["total_rows"],
        }
        (output / "transport.json").write_text(json.dumps(receipt, sort_keys=True))
        for file in output.iterdir():
            file.chmod(0o600)
        with open(env["GITHUB_OUTPUT"], "a") as stream:
            stream.write("artifact_dir=" + str(output) + "\n")
        print(json.dumps(summary, sort_keys=True))
    finally:
        command(["docker", "exec", CONTAINER, "rm", "-rf", "--", remote])


if __name__ == "__main__":
    try:
        run(os.environ)
    except Exception as exc:
        print(failure_message(exc), file=sys.stderr)
        sys.exit(2)
