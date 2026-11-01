"""One serialized fixed V2 operation; encrypted evidence awaits independent offline verification."""

import json
import os
import re
import shutil
import sys
from pathlib import Path

import blank_draft_syllabus_restore as fixed
import own_syllabi_package_artifacts as artifacts
from four_cell_history_export import diagnostics
from private_container_source import write_private_source
from reviewed_followup import CONTAINER, PUBLIC_PEM_SHA, ROOT, command, verify_head

PINNED_FILES = artifacts.PINNED_FILES


def inputs(value):
    if not isinstance(value, dict) or not set(value) <= {"actor", "apply", "confirm"}:
        raise ValueError("fixed_package_inputs_required")
    actor = value.get("actor")
    apply = value.get("apply", False)
    if not isinstance(actor, str) or not re.fullmatch(r"[\w.@+-]{1,150}", actor):
        raise ValueError("fixed_actor_required")
    if type(apply) not in (bool, str) or apply not in (True, False, "true", "false"):
        raise ValueError("explicit_apply_required")
    apply = apply is True or apply == "true"
    if value.get("confirm", "") != ("APPLY" if apply else ""):
        raise ValueError("explicit_confirmation_required")
    return actor, apply


def source_pins(head):
    if command(["git", "rev-parse", "HEAD"]).strip() != head:
        raise ValueError("checkout_head_changed")
    result = {}
    for name in PINNED_FILES:
        local = ROOT / name
        if local.is_symlink() or not local.is_file():
            raise ValueError("fixed_source_file_required")
        raw = local.read_bytes()
        # These are UTF-8 tracked files; git output is checked without logging it.
        tracked = command(["git", "show", head + ":" + name]).encode()
        if artifacts.sha(raw) != artifacts.sha(tracked):
            raise ValueError("fixed_package_code_changed")
        result[name] = artifacts.sha(raw)
    return result


def guard(head, pins):
    verify_head(head)
    if any(artifacts.sha((ROOT / name).read_bytes()) != digest for name, digest in pins.items()):
        raise ValueError("package_source_pins_changed")


def operation(actor, remote, head, pins, *, apply=False, baseline=None):
    guard(head, pins)
    args = ["--org", "qku", "--actor", actor, "--file", remote + "/source.json", "--sha256", fixed.SOURCE_SHA]
    if baseline is not None:
        if not isinstance(baseline, str) or not re.fullmatch(fixed.HEX, baseline):
            raise ValueError("fresh_package_baseline_required")
        args += ["--baseline", baseline]
    if apply:
        if baseline is None:
            raise ValueError("fresh_package_baseline_required")
        args += ["--apply"]
    result = fixed.summary(
        fixed.source_command(
            ["docker", "exec", CONTAINER, "python", "manage.py", "recover_blank_draft_syllabi", *args]
        ),
        apply=apply,
        undo=False,
    )
    return result


def execute(value, env):
    actor, apply = inputs(value)
    print("::add-mask::" + actor, flush=True)
    directory = artifacts.folder(env)
    head = env["GITHUB_SHA"]
    verify_head(head)
    pins = source_pins(head)
    directory.mkdir(mode=0o700)
    private = directory.with_name(directory.name + "-private")
    quarantine = directory.with_name(directory.name + "-quarantine")
    remote = f"/tmp/wcu-blank-draft-syllabus-{env['GITHUB_RUN_ID']}-{env['GITHUB_RUN_ATTEMPT']}"
    manifest = {
        "format": "own-syllabi-v2-package/1",
        "head_sha": head,
        "run_id": int(env["GITHUB_RUN_ID"]),
        "run_attempt": int(env["GITHUB_RUN_ATTEMPT"]),
        "source_sha256": fixed.SOURCE_SHA,
        "cipher_sha256": fixed.CIPHER_SHA,
        "source_pins": pins,
        "apply": apply,
        "status": "in_progress",
        "complete": False,
        "events": [],
        "chain_sha256": "0" * 64,
    }
    artifacts.save(manifest, directory)
    try:
        private.mkdir(mode=0o700)
        quarantine.mkdir(mode=0o700)
        target = fixed.source(private, env)
        # Keep the plaintext source outside the artifact tree and verify again before transfer.
        if artifacts.sha(target.read_bytes()) != fixed.SOURCE_SHA:
            raise ValueError("fixed_syllabus_plaintext_changed")
        public = ROOT / "scripts/data/wcu_workload_export_public.pem"
        if artifacts.sha(public.read_bytes()) != PUBLIC_PEM_SHA:
            raise ValueError("fixed_public_key_required")
        command(["docker", "exec", CONTAINER, "mkdir", "-m", "700", remote])
        write_private_source(target, remote + "/source.json", fixed.SOURCE_SHA, container=CONTAINER)
        command(["docker", "cp", str(public), CONTAINER + ":" + remote + "/public.pem"])
        for label in artifacts.CAPTURES:
            guard(head, pins)
            artifacts.capture(label, "pre", actor, remote, directory, manifest)
        dry = operation(actor, remote, head, pins)
        artifacts.append(manifest, {"phase": "dry", "result": dry}, directory)
        if dry["status"] != "dry_run" or dry["receipt"] is not None:
            raise ValueError("fresh_unapplied_two_case_state_required")
        applied = None
        if apply:
            applied = operation(actor, remote, head, pins, apply=True, baseline=dry["baseline"])
            # Persist the receipt BEFORE subsequent validation, so a failure never hides a write.
            artifacts.append(manifest, {"phase": "apply", "result": applied}, directory)
            if applied["baseline"] != dry["baseline"]:
                raise ValueError("package_baseline_changed")
            if applied["status"] != "applied" or applied["versions_created"] != 2:
                raise ValueError("two_own_versions_required")
        repeated = operation(actor, remote, head, pins)
        artifacts.append(manifest, {"phase": "repeat-dry", "result": repeated}, directory)
        if apply:
            if repeated["status"] != "already_present" or repeated["receipt"] != applied["receipt"]:
                raise ValueError("repeat_dry_same_receipt_required")
            done = operation(actor, remote, head, pins, apply=True, baseline=repeated["baseline"])
            artifacts.append(manifest, {"phase": "repeat-apply", "result": done}, directory)
            if done["baseline"] != repeated["baseline"]:
                raise ValueError("package_baseline_changed")
            if (
                done["status"] != "already_present"
                or done["receipt"] != applied["receipt"]
                or done["versions_created"] != 0
            ):
                raise ValueError("repeat_zero_write_required")
        elif repeated != dry:
            raise ValueError("readonly_baseline_changed")
        for label in artifacts.CAPTURES:
            guard(head, pins)
            artifacts.capture(label, "post", actor, remote, directory, manifest)
        guard(head, pins)
        manifest.update(status=("applied" if apply else "dry_run") + "_PENDING_INDEPENDENT_VERIFICATION", complete=True)
        artifacts.save(manifest, directory)
        artifacts.validate(directory, head, require_complete=True)
        print("own_syllabi_package: " + manifest["status"] + " chain_sha256=" + manifest["chain_sha256"])
        return manifest
    except Exception:
        manifest.update(status="failed", complete=False)
        artifacts.append(manifest, {"phase": "failed", "error": "package_refused"}, directory)
        raise
    finally:
        try:
            command(["docker", "exec", CONTAINER, "rm", "-rf", "--", remote])
        except Exception:
            pass
        shutil.rmtree(private, ignore_errors=True)
        shutil.rmtree(quarantine, ignore_errors=True)


def finalize(env):
    value = artifacts.validate(artifacts.folder(env), env["GITHUB_SHA"])
    if value["source_pins"] != source_pins(env["GITHUB_SHA"]):
        raise ValueError("package_source_pins_changed")
    if value["run_id"] != int(env["GITHUB_RUN_ID"]) or value["run_attempt"] != int(env["GITHUB_RUN_ATTEMPT"]):
        raise ValueError("package_run_changed")
    with open(env["GITHUB_OUTPUT"], "a") as out:
        out.write("artifact_ready=true\n")
    print(
        "own_syllabi_package_manifest_sha256="
        + artifacts.sha((artifacts.folder(env) / "package-manifest.json").read_bytes())
    )


def main():
    os.umask(0o077)
    try:
        if sys.argv[1:] == ["--finalize"]:
            finalize(os.environ)
        elif sys.argv[1:]:
            raise ValueError("fixed_package_mode_required")
        else:
            event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_bytes())
            execute(event.get("inputs"), os.environ)
    except Exception as exc:
        fields = exc.fields if isinstance(exc, fixed.SourceCommandFailure) else diagnostics().describe(exc, "capture")
        print("own_syllabi_package_diagnostic: " + diagnostics().render(fields), file=sys.stderr)
        print("own_syllabi_package_refused_inspect_receipts_no_automatic_retry", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
