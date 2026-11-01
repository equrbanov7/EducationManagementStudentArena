"""Fixed four-only encrypted workflow capture; actor masked before any output."""

import json
import os
import re
import sys
from pathlib import Path

from four_cell_history_scope import SPEC_SHA
from journal_export_pack import envelope_digest, sha
from reviewed_followup import CONTAINER, MAX_ENVELOPE, PUBLIC_PEM_SHA, ROOT, command, verify_head


def inputs(value):
    if (
        not isinstance(value, dict)
        or set(value) != {"actor"}
        or not isinstance(value["actor"], str)
        or not re.fullmatch(r"[\w.@+-]{1,150}", value["actor"])
    ):
        raise ValueError("fixed_history_actor_required")
    return value["actor"]


def capture(actor, env):
    run, attempt = env["GITHUB_RUN_ID"], env["GITHUB_RUN_ATTEMPT"]
    if any(not re.fullmatch(r"[1-9][0-9]*", v) for v in (run, attempt)):
        raise ValueError("workflow_run_required")
    verify_head(env["GITHUB_SHA"])
    folder = Path(env["RUNNER_TEMP"]) / f"four-cell-history-{run}-{attempt}"
    folder.mkdir(mode=0o700)
    remote = f"/tmp/wcu-four-cell-history-{run}-{attempt}"
    public = ROOT / "scripts/data/wcu_workload_export_public.pem"
    if sha(public.read_bytes()) != PUBLIC_PEM_SHA:
        raise ValueError("fixed_public_key_required")
    try:
        command(["docker", "exec", CONTAINER, "mkdir", "-m", "700", remote])
        command(["docker", "cp", str(public), CONTAINER + ":" + remote + "/public.pem"])
        result = command(
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
        command(["docker", "cp", CONTAINER + ":" + remote + "/snapshot.enc.json", str(folder / "snapshot.enc.json")])
        cipher = folder / "snapshot.enc.json"
        if cipher.is_symlink() or not cipher.is_file() or cipher.stat().st_size > MAX_ENVELOPE:
            raise ValueError("history_ciphertext_invalid")
        cipher.chmod(0o600)
        if envelope_digest(cipher) != matches[0][0]:
            raise ValueError("history_ciphertext_sha_changed")
        with cipher.open("rb") as stream:
            os.fsync(stream.fileno())
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
    except Exception:
        print("fixed_four_history_capture_refused", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
