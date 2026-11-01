"""Fixed four-only encrypted workflow capture; actor masked before any output."""

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from four_cell_history_scope import SPEC_SHA
from journal_export_pack import envelope_digest, sha
from reviewed_followup import CONTAINER, MAX_ENVELOPE, PUBLIC_PEM_SHA, ROOT, command, verify_head


def diagnostics():
    path = ROOT / "apps/workload/services/four_cell_diagnostics.py"
    spec = importlib.util.spec_from_file_location("fixed_four_safe_diagnostics", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CaptureFailure(ValueError):
    def __init__(self, fields, host_stage=None):
        self.fields = fields
        self.host_stage = host_stage or fields["stage"]
        super().__init__(fields, host_stage)

    def __str__(self):
        return "fixed_four_history_capture_refused"


def source_command(argv):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=180)
    if len(result.stdout) + len(result.stderr) > 65536:
        raise ValueError("source_diagnostic_output_budget")
    if result.returncode:
        fields = diagnostics().parse(result.stdout + "\n" + result.stderr)
        if fields is None:
            fields = diagnostics().describe(ValueError("source_capture_failed"), "source_capture")
        raise CaptureFailure(fields, host_stage="source_capture")
    return result.stdout


def capture(actor, env):
    progress = {"stage": "input"}
    try:
        return _capture(actor, env, progress)
    except CaptureFailure:
        raise
    except Exception as exc:
        raise CaptureFailure(diagnostics().describe(exc, progress["stage"])) from None


def inputs(value):
    if (
        not isinstance(value, dict)
        or set(value) != {"actor"}
        or not isinstance(value["actor"], str)
        or not re.fullmatch(r"[\w.@+-]{1,150}", value["actor"])
    ):
        raise ValueError("fixed_history_actor_required")
    return value["actor"]


def _capture(actor, env, progress):
    run, attempt = env["GITHUB_RUN_ID"], env["GITHUB_RUN_ATTEMPT"]
    if any(not re.fullmatch(r"[1-9][0-9]*", v) for v in (run, attempt)):
        raise ValueError("workflow_run_required")
    progress["stage"] = "verify_head"
    verify_head(env["GITHUB_SHA"])
    progress["stage"] = "prepare"
    folder = Path(env["RUNNER_TEMP"]) / f"four-cell-history-{run}-{attempt}"
    folder.mkdir(mode=0o700)
    remote = f"/tmp/wcu-four-cell-history-{run}-{attempt}"
    public = ROOT / "scripts/data/wcu_workload_export_public.pem"
    if sha(public.read_bytes()) != PUBLIC_PEM_SHA:
        raise ValueError("fixed_public_key_required")
    try:
        progress["stage"] = "remote_setup"
        command(["docker", "exec", CONTAINER, "mkdir", "-m", "700", remote])
        command(["docker", "cp", str(public), CONTAINER + ":" + remote + "/public.pem"])
        progress["stage"] = "source_capture"
        result = source_command(
            [
                "docker",
                "exec",
                CONTAINER,
                "python",
                "manage.py",
                "export_wcu_four_cell_history",
                "--actor",
                actor,
                "--public-key",
                remote + "/public.pem",
                "--output",
                remote + "/snapshot.enc.json",
            ]
        )
        matches = re.findall(
            r"^encrypted_sha256=([a-f0-9]{64}) cases=4 audits=([0-9]+) changes=([0-9]+)\s*$", result, re.M
        )
        if len(matches) != 1 or any(int(n) > 1000 for n in matches[0][1:]):
            raise ValueError("fixed_history_summary_required")
        progress["stage"] = "copy_cipher"
        command(["docker", "cp", CONTAINER + ":" + remote + "/snapshot.enc.json", str(folder / "snapshot.enc.json")])
        progress["stage"] = "verify_cipher"
        cipher = folder / "snapshot.enc.json"
        if cipher.is_symlink() or not cipher.is_file() or cipher.stat().st_size > MAX_ENVELOPE:
            raise ValueError("history_ciphertext_invalid")
        cipher.chmod(0o600)
        if envelope_digest(cipher) != matches[0][0]:
            raise ValueError("history_ciphertext_sha_changed")
        with cipher.open("rb") as stream:
            os.fsync(stream.fileno())
        progress["stage"] = "write_manifest"
        receipt = {
            "format": "wcu-four-cell-history-capture/1",
            "head_sha": env["GITHUB_SHA"],
            "run_id": int(run),
            "run_attempt": int(attempt),
            "source_spec_sha256": SPEC_SHA,
            "encrypted_sha256": matches[0][0],
            "file": "snapshot.enc.json",
            "eligible_for_apply": False,
        }
        with open(folder / "capture-manifest.json", "x") as out:
            os.chmod(out.name, 0o600)
            json.dump(receipt, out, sort_keys=True)
            out.flush()
            os.fsync(out.fileno())
        fd = os.open(folder, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        progress["stage"] = "publish_output"
        with open(env["GITHUB_OUTPUT"], "a") as out:
            out.write("artifact_dir=" + str(folder) + "\n")
        print("four_cell_history_capture: encrypted_sha256=" + matches[0][0])
    finally:
        try:
            command(["docker", "exec", CONTAINER, "rm", "-rf", "--", remote])
        except Exception:
            pass


def main():
    try:
        actor = inputs(json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_bytes()).get("inputs"))
        print("::add-mask::" + actor, flush=True)
        capture(actor, os.environ)
    except Exception as exc:
        fields = exc.fields if isinstance(exc, CaptureFailure) else diagnostics().describe(exc, "input")
        host_stage = exc.host_stage if isinstance(exc, CaptureFailure) else "input"
        print("four_cell_history_host_stage=" + host_stage, file=sys.stderr)
        print("four_cell_history_diagnostic: " + diagnostics().render(fields), file=sys.stderr)
        print("fixed_four_history_capture_refused", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
