"""One fixed English identity source, read-only capture, encrypted output only."""

import json
import os
import re
import shutil
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

from english_level_evidence_scope import contract
from four_cell_history_export import diagnostics
from journal_export_pack import envelope_digest, sha
from reviewed_followup import CONTAINER, PUBLIC_PEM_SHA, ROOT, command, verify_head

TAG = "english-level-evidence-20261101"
ASSET = "english-level-source.json.enc"
CIPHER_SHA = "bc1d7e68d309b96e1df6680152e4ae0511bda06b2e021dd132e7fdab1f91548b"
REPO = "equrbanov7/EducationManagementStudentArena"
MAX_SOURCE = 1024 * 1024
MAX_OUTPUT = 16 * 1024 * 1024
SOURCE_SHA = contract().spec.SOURCE_SHA


@contextmanager
def source_folder(root, run, attempt):
    folder = root / f"english-level-private-{run}-{attempt}"
    folder.mkdir(mode=0o700)
    try:
        yield folder
    finally:
        shutil.rmtree(folder)


class SourceCaptureFailure(ValueError):
    def __init__(self, fields):
        self.fields = fields
        super().__init__("english_level_source_capture_refused")


def source_command(argv):
    result = subprocess.run(argv, capture_output=True, text=True, timeout=180)
    if len(result.stdout) + len(result.stderr) > 65536:
        raise ValueError("english_source_output_budget")
    if result.returncode:
        output = result.stdout + "\n" + result.stderr
        fields = diagnostics().parse(output.replace("english_level_diagnostic: ", "four_cell_history_diagnostic: "))
        if fields is None:
            fields = diagnostics().describe(ValueError("source_capture_failed"), "source_capture")
        raise SourceCaptureFailure(fields)
    return result.stdout


def actor_input(value):
    if (
        not isinstance(value, dict)
        or set(value) != {"actor"}
        or not isinstance(value["actor"], str)
        or not re.fullmatch(r"[\w.@+-]{1,150}", value["actor"])
    ):
        raise ValueError("fixed_english_actor_required")
    return value["actor"]


def summary(raw):
    match = re.fullmatch(
        r"encrypted_sha256=([a-f0-9]{64}) identities=1235 offerings=([0-9]+) placements=([0-9]+)\s*", raw
    )
    if not match or not 0 < int(match[2]) <= 150 or int(match[3]) > 10000:
        raise ValueError("fixed_english_summary_required")
    return match[1]


def private_regular(path, cap):
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= cap:
        raise ValueError("fixed_english_file_invalid")
    path.chmod(0o600)


def decrypt_source(folder, env):
    command(["gh", "release", "download", TAG, "--repo", REPO, "--pattern", ASSET, "--dir", str(folder)])
    cipher = folder / ASSET
    private_regular(cipher, MAX_SOURCE)
    if sha(cipher.read_bytes()) != CIPHER_SHA:
        raise ValueError("fixed_english_cipher_changed")
    source = folder / "source.json"
    if not env.get("STAFF_PLAN_KEY"):
        raise ValueError("fixed_english_decryption_key_required")
    # The secret remains in the masked environment, never command arguments/output.
    result = subprocess.run(
        [
            "openssl",
            "enc",
            "-d",
            "-aes-256-cbc",
            "-pbkdf2",
            "-iter",
            "200000",
            "-md",
            "sha256",
            "-in",
            str(cipher),
            "-out",
            str(source),
            "-pass",
            "env:STAFF_PLAN_KEY",
        ],
        env=env,
        capture_output=True,
        timeout=30,
    )
    if result.returncode:
        raise ValueError("fixed_english_decryption_failed")
    private_regular(source, MAX_SOURCE)
    if sha(source.read_bytes()) != SOURCE_SHA:
        raise ValueError("fixed_english_plaintext_changed")
    return source


def capture(actor, env):
    run, attempt, head = (env[k] for k in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT", "GITHUB_SHA"))
    if any(not re.fullmatch(r"[1-9][0-9]*", value) for value in (run, attempt)):
        raise ValueError("workflow_run_required")
    verify_head(head)
    remote = f"/tmp/wcu-english-level-{run}-{attempt}"
    root = Path(env["RUNNER_TEMP"])
    artifact = root / f"english-level-artifact-{run}-{attempt}"
    artifact.mkdir(mode=0o700)
    public = ROOT / "scripts/data/wcu_workload_export_public.pem"
    if sha(public.read_bytes()) != PUBLIC_PEM_SHA:
        raise ValueError("fixed_public_key_required")
    with source_folder(root, run, attempt) as folder:
        try:
            source = decrypt_source(folder, env)
            command(["docker", "exec", CONTAINER, "mkdir", "-m", "700", remote])
            for local, name in ((public, "public.pem"), (source, "source.json")):
                command(["docker", "cp", str(local), CONTAINER + ":" + remote + "/" + name])
            raw = source_command(
                [
                    "docker",
                    "exec",
                    CONTAINER,
                    "python",
                    "manage.py",
                    "export_wcu_english_level_evidence",
                    "--actor",
                    actor,
                    "--file",
                    remote + "/source.json",
                    "--sha256",
                    SOURCE_SHA,
                    "--public-key",
                    remote + "/public.pem",
                    "--output",
                    remote + "/snapshot.enc.json",
                ]
            )
            expected = summary(raw)
            cipher = artifact / "snapshot.enc.json"
            command(["docker", "cp", CONTAINER + ":" + remote + "/snapshot.enc.json", str(cipher)])
            private_regular(cipher, MAX_OUTPUT)
            if envelope_digest(cipher) != expected:
                raise ValueError("fixed_english_output_changed")
            manifest = {
                "format": "wcu-english-level-capture/1",
                "head_sha": head,
                "run_id": int(run),
                "run_attempt": int(attempt),
                "source_sha256": SOURCE_SHA,
                "source_cipher_sha256": CIPHER_SHA,
                "encrypted_sha256": expected,
                "file": "snapshot.enc.json",
                "eligible_for_apply": False,
            }
            target = artifact / "capture-manifest.json"
            with os.fdopen(os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as out:
                json.dump(manifest, out, sort_keys=True)
                out.flush()
                os.fsync(out.fileno())
            with cipher.open("rb") as stream:
                os.fsync(stream.fileno())
            fd = os.open(artifact, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
            with open(env["GITHUB_OUTPUT"], "a") as out:
                out.write("artifact_dir=" + str(artifact) + "\n")
            print("english_level_capture: encrypted_sha256=" + expected)
        finally:
            try:
                command(["docker", "exec", CONTAINER, "rm", "-rf", "--", remote])
            except Exception:
                pass


def main():
    os.umask(0o077)
    try:
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_bytes())
        actor = actor_input(event.get("inputs"))
        print("::add-mask::" + actor, flush=True)
        capture(actor, os.environ)
    except Exception as exc:
        fields = exc.fields if isinstance(exc, SourceCaptureFailure) else diagnostics().describe(exc, "input")
        print("english_level_diagnostic: " + diagnostics().render(fields), file=sys.stderr)
        print("fixed_english_evidence_capture_refused", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
