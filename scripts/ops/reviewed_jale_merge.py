"""Fixed pair only; verify deployed HEAD, emit an opaque inventory artifact."""

import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from reviewed_followup import CONTAINER, verify_head

ROOT = Path(__file__).resolve().parents[2]


class NativeRefused(ValueError):
    pass


def safe_failure(stderr):
    """Only fixed native guard literals; never traceback, row contents or PII."""
    if not isinstance(stderr, str) or len(stderr) > 65536:
        return "reviewed_jale_merge_refused"
    match = re.fullmatch(r"CommandError: (jale_merge_[a-z0-9_]{1,100})\n?", stderr)
    known = {"jale_merge_explicit_target_required"}
    source = ROOT / "apps/accounts/services/reviewed_jale_merge.py"
    for node in ast.walk(ast.parse(source.read_text())):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "require"
            and len(node.args) > 1
            and isinstance(node.args[1], ast.Constant)
            and isinstance(node.args[1].value, str)
        ):
            known.add(node.args[1].value)
    return match[1] if match and match[1] in known else "reviewed_jale_merge_refused"


def execute(value, env):
    if not isinstance(value, dict) or not set(value) <= {
        "apply",
        "baseline",
        "confirm",
    }:
        raise ValueError("jale_merge_fixed_inputs")
    apply = value.get("apply", False)
    if type(apply) not in (bool, str) or apply not in (True, False, "true", "false"):
        raise ValueError("jale_merge_apply_type")
    apply = apply is True or apply == "true"
    baseline, confirm = value.get("baseline", ""), value.get("confirm", "")
    if (
        not isinstance(baseline, str)
        or baseline
        and not re.fullmatch(r"[a-f0-9]{64}", baseline)
    ):
        raise ValueError("jale_merge_baseline_type")
    if apply and (not baseline or confirm != "APPLY") or not apply and confirm:
        raise ValueError("jale_merge_fresh_baseline_confirmation")
    for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"):
        if not re.fullmatch(r"[1-9][0-9]*", env.get(key, "")):
            raise ValueError("jale_merge_workflow_required")
    verify_head(env.get("GITHUB_SHA", ""))
    target = f"/tmp/jale-merge-{env['GITHUB_RUN_ID']}-{env['GITHUB_RUN_ATTEMPT']}.json"
    args = [
        "docker",
        "exec",
        CONTAINER,
        "python",
        "manage.py",
        "reviewed_jale_merge",
        "--report",
        target,
    ]
    if apply:
        args += [
            "--apply",
            "--baseline-sha256",
            baseline,
            "--i-know-this-is-production",
            "--reason",
            "MR-000082: owner-verified same-person Jalə alias8388→canonical7730; preserve history",
        ]
    result = subprocess.run(args, capture_output=True, text=True, timeout=180)
    if result.returncode or result.stderr:
        raise NativeRefused(safe_failure(result.stderr))
    try:
        report = subprocess.run(
            ["docker", "exec", CONTAINER, "cat", target],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        if report.stderr or len(report.stdout) > 1000000:
            raise ValueError("jale_merge_report_budget")
        data = json.loads(report.stdout)
        # Native report contains digests, counts, row IDs and hold codes only.
        allowed = {
            "organization",
            "canonical",
            "alias",
            "identity_sha256",
            "references",
            "legacy_maps_sha256",
            "actions",
            "holds",
            "baseline_sha256",
            "eligible",
            "soft_deleted_alias",
            "moved_relations",
        }
        if (
            not isinstance(data, dict)
            or not set(data) <= allowed
            or data.get("canonical") != 7730
        ):
            raise ValueError("jale_merge_report_shape")
        output = Path("jale-merge-report.json")
        output.write_text(
            json.dumps(data, sort_keys=True, ensure_ascii=False), encoding="utf-8"
        )
        output.chmod(0o600)
        print("reviewed_jale_merge report_ready=1 apply=" + str(int(apply)))
    finally:
        subprocess.run(
            ["docker", "exec", CONTAINER, "rm", "-f", target],
            capture_output=True,
            timeout=30,
        )


def main():
    os.umask(0o077)
    try:
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_bytes())
        execute(event.get("inputs"), os.environ)
    except NativeRefused as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception:
        print("reviewed_jale_merge_refused", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
