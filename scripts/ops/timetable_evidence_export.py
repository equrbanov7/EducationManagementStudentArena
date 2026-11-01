"""Fixed review cohort only, encrypted capture on the verified deployed container."""

import json
import os
import re
import sys
from pathlib import Path

from journal_export_pack import envelope_digest, sha
from reviewed_followup import CONTAINER, PUBLIC_PEM_SHA, ROOT, command, verify_head
from timetable_evidence_scope import BATCHES, MANIFEST_SHA, MAX_BYTES, selection

MAX_ENVELOPE = MAX_BYTES * 4 // 3 + 4096


def inputs(value):
    if type(value) is not dict or set(value) != {"actor", "batch"}:
        raise ValueError("fixed_timetable_inputs_required")
    actor, batch = value["actor"], value["batch"]
    if type(actor) is not str or not re.fullmatch(r"[\w.@+-]{1,150}", actor) or batch not in BATCHES:
        raise ValueError("fixed_timetable_inputs_required")
    selection(batch)  # Recheck immutable manifest before any container execution.
    return actor, batch


def capture(actor, batch, env):
    run, attempt = env["GITHUB_RUN_ID"], env["GITHUB_RUN_ATTEMPT"]
    if any(not re.fullmatch(r"[1-9][0-9]*", v) for v in (run, attempt)):
        raise ValueError("workflow_run_required")
    verify_head(env["GITHUB_SHA"])
    folder = Path(env["RUNNER_TEMP"]) / f"timetable-evidence-{run}-{attempt}"
    folder.mkdir(mode=0o700)
    remote = f"/tmp/wcu-timetable-evidence-{run}-{attempt}"
    public = ROOT / "scripts/data/wcu_workload_export_public.pem"
    if sha(public.read_bytes()) != PUBLIC_PEM_SHA:
        raise ValueError("fixed_public_key_required")
    try:
        command(["docker", "exec", CONTAINER, "mkdir", "-m", "700", remote])
        command(["docker", "cp", str(public), CONTAINER + ":" + remote + "/public.pem"])
        raw = command(
            [
                "docker",
                "exec",
                CONTAINER,
                "python",
                "manage.py",
                "export_wcu_timetable_evidence",
                "--actor",
                actor,
                "--batch",
                batch,
                "--public-key",
                remote + "/public.pem",
                "--output",
                remote + "/snapshot.enc.json",
            ]
        )
        if len(raw) > 1024:
            raise ValueError("timetable_summary_budget")
        match = re.fullmatch(r"encrypted_sha256=([a-f0-9]{64}) roots=([0-9]+)\s*", raw)
        if not match or int(match[2]) != len(selection(batch)):
            raise ValueError("fixed_timetable_summary_required")
        command(["docker", "cp", CONTAINER + ":" + remote + "/snapshot.enc.json", str(folder / "snapshot.enc.json")])
        cipher = folder / "snapshot.enc.json"
        if cipher.is_symlink() or not cipher.is_file() or cipher.stat().st_size > MAX_ENVELOPE:
            raise ValueError("timetable_ciphertext_invalid")
        cipher.chmod(0o600)
        if envelope_digest(cipher) != match[1]:
            raise ValueError("timetable_ciphertext_changed")
        with cipher.open("rb") as stream:
            os.fsync(stream.fileno())
        receipt = {
            "format": "wcu-timetable-evidence-capture/1",
            "head_sha": env["GITHUB_SHA"],
            "run_id": int(run),
            "run_attempt": int(attempt),
            "manifest_sha256": MANIFEST_SHA,
            "batch": batch,
            "encrypted_sha256": match[1],
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
        with open(env["GITHUB_OUTPUT"], "a") as out:
            out.write("artifact_dir=" + str(folder) + "\n")
        print("timetable_evidence_capture: encrypted_sha256=" + match[1])
    finally:
        command(["docker", "exec", CONTAINER, "rm", "-rf", "--", remote])


def main():
    try:
        actor, batch = inputs(json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_bytes()).get("inputs"))
        print("::add-mask::" + actor, flush=True)
        capture(actor, batch, os.environ)
    except Exception:
        print("fixed_timetable_evidence_capture_refused", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
