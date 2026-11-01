"""Fixed027/029 cycle-held content fingerprints: deployed HEAD, private quarantine, cipher-only artifact."""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from four_cell_history_export import diagnostics
from journal_export_pack import envelope_digest, sha
from reviewed_followup import CONTAINER, PUBLIC_PEM_SHA, ROOT, command, verify_head
from syllabus_content_scope import REGISTRY_SHA

BATCHES = ("chair-cells-027", "chair-cells-029")

MAX_ENVELOPE = 8 * 1024 * 1024 * 4 // 3 + 4096


class CaptureFailure(ValueError):
    def __init__(self, fields):
        self.fields = fields
        super().__init__("fixed_syllabus_forensic_capture_refused")


def source_command(argv):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=180)
    if len(result.stdout) + len(result.stderr) > 65536:
        raise ValueError("source_diagnostic_output_budget")
    if result.returncode:
        fields = diagnostics().parse(result.stdout + "\n" + result.stderr, prefix="syllabus_forensic_diagnostic")
        fields = fields or diagnostics().describe(ValueError("source_capture_failed"), "source_capture")
        raise CaptureFailure(fields)
    return result.stdout


def inputs(value):
    if not isinstance(value, dict) or set(value) != {"actor", "batch"}:
        raise ValueError("fixed_forensic_inputs_required")
    actor, batch = value["actor"], value["batch"]
    if not isinstance(actor, str) or not re.fullmatch(r"[\w.@+-]{1,150}", actor) or batch not in BATCHES:
        raise ValueError("fixed_forensic_inputs_required")
    return actor, batch


def capture(actor, batch, env):
    inputs(dict(actor=actor, batch=batch))
    run, attempt, head = (env[k] for k in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_SHA"))
    if any(not re.fullmatch(r"[1-9][0-9]*", v) for v in (run, attempt)):
        raise ValueError("workflow_run_required")
    verify_head(head)
    public = ROOT / "scripts/data/wcu_workload_export_public.pem"
    if sha(public.read_bytes()) != PUBLIC_PEM_SHA:
        raise ValueError("fixed_public_key_required")
    folder = Path(env["RUNNER_TEMP"]) / f"syllabus-forensic-{run}-{attempt}"
    folder.mkdir(mode=0o700)
    quarantine, approved = folder / "quarantine", folder / "approved"
    quarantine.mkdir(mode=0o700)
    approved.mkdir(mode=0o700)
    remote = f"/tmp/wcu-syllabus-forensic-{run}-{attempt}"
    try:
        command(["docker", "exec", CONTAINER, "mkdir", "-m", "700", remote])
        command(["docker", "cp", str(public), CONTAINER + ":" + remote + "/public.pem"])
        raw = source_command(
            [
                "docker",
                "exec",
                CONTAINER,
                "python",
                "manage.py",
                "export_wcu_syllabus_forensic",
                "--batch",
                batch,
                "--actor",
                actor,
                "--public-key",
                remote + "/public.pem",
                "--output",
                remote + "/snapshot.enc.json",
            ]
        )
        match = re.fullmatch(r"encrypted_sha256=([a-f0-9]{64}) roots=20 versions=([0-9]+) cycles=([0-9]+)\s*", raw)
        if not match or int(match[2]) > 500 or int(match[3]) > 800:
            raise ValueError("fixed_history_summary_required")
        target = quarantine / "snapshot.enc.json"
        command(["docker", "cp", CONTAINER + ":" + remote + "/snapshot.enc.json", str(target)])
        if target.is_symlink() or not target.is_file() or not 0 < target.stat().st_size <= MAX_ENVELOPE:
            raise ValueError("history_ciphertext_invalid")
        target.chmod(0o600)
        if envelope_digest(target) != match[1]:
            raise ValueError("history_ciphertext_sha_changed")
        with target.open("rb") as stream:
            os.fsync(stream.fileno())
        os.replace(target, approved / "snapshot.enc.json")
        manifest = dict(
            format="wcu-syllabus-forensic-capture/1",
            head_sha=head,
            run_id=int(run),
            run_attempt=int(attempt),
            batch=batch,
            registry_sha256=REGISTRY_SHA,
            encrypted_sha256=match[1],
            file="snapshot.enc.json",
            eligible_for_apply=False,
            normal_content_export_usable=False,
            read_only=True,
            payload_format="wcu-syllabus-content-cycle-forensic/1",
        )
        with (approved / "capture-manifest.json").open("x") as out:
            os.chmod(out.name, 0o600)
            json.dump(manifest, out, sort_keys=True)
            out.flush()
            os.fsync(out.fileno())
        fd = os.open(approved, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        with open(env["GITHUB_OUTPUT"], "a") as out:
            out.write("artifact_dir=" + str(approved) + "\n")
        print("syllabus_forensic_capture: encrypted_sha256=" + match[1])
    finally:
        shutil.rmtree(quarantine)
        try:
            command(["docker", "exec", CONTAINER, "rm", "-rf", "--", remote])
        except Exception:
            pass


def main():
    os.umask(0o077)
    try:
        actor, batch = inputs(json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_bytes()).get("inputs"))
        print("::add-mask::" + actor, flush=True)
        capture(actor, batch, os.environ)
    except Exception as exc:
        fields = exc.fields if isinstance(exc, CaptureFailure) else diagnostics().describe(exc, "capture")
        print("syllabus_forensic_diagnostic: " + diagnostics().render(fields), file=sys.stderr)
        print("fixed_syllabus_forensic_capture_refused", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
