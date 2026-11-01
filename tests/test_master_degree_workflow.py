"""Real shell dispatch boundaries for the fixed Master metadata operation."""

import importlib.util
import json
import os
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def run_args(script="master_degree_args.sh", **changes):
    env = {
        **os.environ,
        "ORG": "qku",
        "YEAR": "2026/2027",
        "GITHUB_RUN_ID": "42",
        "BATCH": "",
        "ROW_SUBJECT": "",
        "ROW_GROUP": "",
        "ROSTER_TAG": "",
        "APPLY": "false",
        **changes,
    }
    return subprocess.run(
        [
            "bash",
            "-c",
            "set -euo pipefail\n"
            "superadmin_actor() { printf admin; }\n"
            "match() { [[ $1 != *$'\\n'* && $1 != *$'\\r'* ]] && printf '%s' \"$1\" | grep -Eq -- \"$2\"; }\n"
            f"source scripts/ops/{script}\n"
            "printf '%s\\n' \"${args[@]}\"",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def test_dry_default_and_fresh_baseline_required_for_apply():
    dry = run_args()
    assert dry.returncode == 0, dry.stderr
    assert "--safe-summary" in dry.stdout
    assert run_args(APPLY="true").returncode != 0
    applied = run_args(APPLY="true", BATCH="a" * 64)
    assert applied.returncode == 0, applied.stderr
    assert "--expected-baseline\n" + "a" * 64 in applied.stdout


def test_undo_selector_is_exact_receipt_and_does_not_relax_baseline():
    receipt = "11111111-2222-3333-4444-555555555555"
    assert run_args(APPLY="true", ROW_SUBJECT=receipt).returncode != 0
    undo = run_args(APPLY="true", BATCH="b" * 64, ROW_SUBJECT=receipt)
    assert undo.returncode == 0, undo.stderr
    assert "--undo\n" + receipt in undo.stdout


def test_multiline_shell_and_unused_source_arguments_fail_closed():
    for changes in (
        {"BATCH": "a" * 64 + "\n"},
        {"ROW_SUBJECT": "$(id)"},
        {"ROW_GROUP": "all"},
        {"ROSTER_TAG": "unreviewed"},
    ):
        assert run_args(**changes).returncode != 0


def test_it8179_source_dispatch_requires_source_and_fresh_baseline():
    def run(**changes):
        env = {
            **os.environ,
            "BATCH": "a" * 64,
            "ROW_SUBJECT": "",
            "ROW_GROUP": "",
            "APPLY": "false",
            "ORG": "qku",
            "GITHUB_RUN_ID": "42",
            **changes,
        }
        return subprocess.run(
            [
                "bash",
                "-c",
                "set -euo pipefail\nsuperadmin_actor() { printf admin; }\nmatch() { [[ $1 != *$'\\n'* && $1 != *$'\\r'* ]] && printf '%s' \"$1\" | grep -Eq -- \"$2\"; }\nsource scripts/ops/it8179_args.sh\nprintf '%s\\n' \"${args[@]}\"",
            ],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
        )

    dry = run()
    assert dry.returncode == 0, dry.stderr
    assert "/tmp/it8179_source_42.docx" in dry.stdout
    assert run(APPLY="true").returncode != 0
    assert run(APPLY="true", ROW_SUBJECT="b" * 64).returncode == 0
    assert run(BATCH="a" * 64 + "\n").returncode != 0
    assert run(ROW_GROUP="unreviewed").returncode != 0


def test_chair_case_selection_and_undo_remain_bounded():
    dry = run_args("chair_contacts_args.sh", ROW_GROUP="az_morphology,tarix_europe")
    assert dry.returncode == 0, dry.stderr
    assert "--selection\naz_morphology,tarix_europe" in dry.stdout
    assert run_args("chair_contacts_args.sh", APPLY="true").returncode != 0
    assert run_args("chair_contacts_args.sh", ROW_GROUP="other_chair").returncode != 0
    assert run_args("chair_contacts_args.sh", ROW_GROUP="tarix_region\n").returncode != 0
    assert (
        run_args(
            "chair_contacts_args.sh",
            APPLY="true",
            BATCH="b" * 64,
            ROW_SUBJECT="11111111-2222-3333-4444-555555555555",
            ROW_GROUP="tarix_region",
        ).returncode
        == 0
    )


SOURCE_SHA = "209dfa543720f11421a5aab910318e193e49799b2cf98b8fc27f5ed885fb5b16"
RECEIPT = "11111111-2222-3333-4444-555555555555"


def test_biostat_fixed_source_dry_apply_undo_and_invalid_selector_arguments():
    def run(**changes):
        return run_args(
            "biostat_share_args.sh",
            BATCH=changes.pop("BATCH", SOURCE_SHA),
            ROSTER_TAG=changes.pop("ROSTER_TAG", "biostat-kind-share-20261101"),
            **changes,
        )

    dry = run()
    assert dry.returncode == 0, dry.stderr
    assert "/tmp/biostat_source_42.xlsx" in dry.stdout
    assert "--sha256\n" + SOURCE_SHA in dry.stdout
    assert run(APPLY="true").returncode != 0
    assert run(APPLY="true", ROW_SUBJECT="b" * 64).returncode == 0
    undo = run(APPLY="true", ROW_SUBJECT="b" * 64, ROW_GROUP="undo")
    assert undo.returncode == 0, undo.stderr
    assert "--undo" in undo.stdout
    for changes in (
        {"BATCH": "a" * 64},
        {"BATCH": SOURCE_SHA + "\n"},
        {"ROW_SUBJECT": "$(id)"},
        {"ROSTER_TAG": "biostat-kind-share-20261101\r"},
        {"ROW_GROUP": "all"},
        {"ORG": "foreign"},
        {"YEAR": "2025/2026"},
    ):
        assert run(**changes).returncode != 0


def test_mr34_fixed_scope_dry_apply_and_undo_use_correct_command_flags():
    assert run_args("mr34_teacher_args.sh").returncode == 0
    assert run_args("mr34_teacher_args.sh", APPLY="true").returncode != 0
    applied = run_args("mr34_teacher_args.sh", APPLY="true", BATCH="a" * 64)
    assert applied.returncode == 0, applied.stderr
    assert "--expected-baseline\n" + "a" * 64 in applied.stdout
    assert "--safe-summary" not in applied.stdout
    undo = run_args("mr34_teacher_args.sh", APPLY="true", BATCH="a" * 64, ROW_SUBJECT=RECEIPT)
    assert undo.returncode == 0, undo.stderr
    assert "--undo\n" + RECEIPT in undo.stdout
    for changes in (
        {"ROSTER_TAG": "unreviewed"},
        {"ROW_GROUP": "all"},
        {"BATCH": "a" * 64 + "\n"},
        {"ROW_SUBJECT": "$(id)"},
        {"ROW_SUBJECT": RECEIPT + "\r"},
        {"ORG": "foreign"},
    ):
        assert run_args("mr34_teacher_args.sh", **changes).returncode != 0


def _workflow():
    return yaml.safe_load((ROOT / ".github/workflows/prod-data-ops.yml").read_text())


def _real_workflow_run(tmp_path, command, output, **changes):
    job = _workflow()["jobs"]["run"]
    script = next(step["run"] for step in job["steps"] if step["name"] == "🧰 Run")
    record = tmp_path / "actual-args.txt"
    env = {
        **os.environ,
        **{key: "" for key in job["env"]},
        "ORG": "qku",
        "YEAR": "2026/2027",
        "APPLY": "false",
        "COMMAND": command,
        "GITHUB_RUN_ID": "42",
        "RUNNER_TEMP": str(tmp_path),
        "GITHUB_STEP_SUMMARY": str(tmp_path / "step-summary.txt"),
        "APP_CONTAINER": "fixture-app",
        "BACKUP_CONTAINER": "fixture-backup",
        "ARGUMENT_RECORD": str(record),
        "FIXTURE_COMMAND_OUTPUT": output,
        "FIXTURE_COMMAND_STATUS": "0",
        **changes,
    }
    fake = r"""
    docker() {
      case "$*" in
        *'manage.py shell '*) printf 'fixture_admin\n' ;;
        *'/backup.sh'*) return 0 ;;
        *"manage.py $COMMAND "*) printf '%s\n' "$@" > "$ARGUMENT_RECORD"; printf '%s\n' "$FIXTURE_COMMAND_OUTPUT"; return "$FIXTURE_COMMAND_STATUS" ;;
        *) echo unexpected_fake_docker_call >&2; return 91 ;;
      esac
    }
    """
    result = subprocess.run(["bash", "-c", fake + script], cwd=ROOT, env=env, capture_output=True, text=True)
    return result, record.read_text().splitlines() if record.exists() else []


def test_actual_biostat_workflow_branch_dry_apply_and_undo(tmp_path):
    output = (
        "biostat_kind_share: mode=dry_run already_present=0 baseline="
        + "b" * 64
        + " owner_unchanged=1 roster=2 seminar_hours=15 shares_to_create=1"
    )
    common = {"BATCH": SOURCE_SHA, "ROSTER_TAG": "biostat-kind-share-20261101"}
    dry, args = _real_workflow_run(tmp_path, "repair_biostat_seminar_share", output, **common)
    assert dry.returncode == 0, dry.stderr
    assert "--apply" not in args
    assert "/tmp/biostat_source_42.xlsx" in args
    for row_group in ("", "undo"):
        applied, args = _real_workflow_run(
            tmp_path,
            "repair_biostat_seminar_share",
            output.replace("mode=dry_run", "mode=apply"),
            APPLY="true",
            ROW_SUBJECT="b" * 64,
            ROW_GROUP=row_group,
            **common,
        )
        assert applied.returncode == 0, applied.stderr
        assert "--apply" in args and "--baseline" in args
        assert ("--undo" in args) == bool(row_group)
    assert not (tmp_path / "out.log").exists()
    assert not (tmp_path / "summary.log").exists()


def test_actual_mr34_workflow_branch_dry_apply_undo_and_safe_json_summary(tmp_path):
    payload = {
        "status": "dry_run",
        "baseline": "a" * 64,
        "applied": False,
        "receipt": None,
        "assignments": 5,
        "hours": 135,
    }
    dry, args = _real_workflow_run(tmp_path, "repair_mr34_teacher_load", json.dumps(payload))
    assert dry.returncode == 0, dry.stderr
    assert "mr34_teacher_load: status=dry_run applied=0" in dry.stdout
    assert "--apply" not in args
    for undo in (False, True):
        current = {
            **payload,
            "status": "undone" if undo else "applied",
            "applied": True,
            "receipt": RECEIPT,
            "after_baseline": "b" * 64,
        }
        result, args = _real_workflow_run(
            tmp_path,
            "repair_mr34_teacher_load",
            json.dumps(current),
            APPLY="true",
            BATCH="a" * 64,
            ROW_SUBJECT=RECEIPT if undo else "",
        )
        assert result.returncode == 0, result.stderr
        assert "--expected-baseline" in args and "--apply" in args
        assert ("--undo" in args) == undo
    for status in ("already_canonical", "already_undone"):
        repeated = {
            "status": status,
            "baseline": "a" * 64,
            "applied": False,
            "receipt": RECEIPT if status == "already_undone" else None,
        }
        result, _args = _real_workflow_run(
            tmp_path,
            "repair_mr34_teacher_load",
            json.dumps(repeated),
            ROW_SUBJECT=RECEIPT if status == "already_undone" else "",
        )
        assert result.returncode == 0, result.stderr
        assert "status=" + status in result.stdout
    assert not (tmp_path / "out.log").exists()
    assert not (tmp_path / "summary.log").exists()


def test_actual_new_workflow_branches_reject_injection_before_command(tmp_path):
    for command, changes in (
        (
            "repair_biostat_seminar_share",
            {
                "BATCH": SOURCE_SHA,
                "ROSTER_TAG": "biostat-kind-share-20261101",
                "ROW_SUBJECT": "$(touch SHOULD_NOT_EXIST)",
            },
        ),
        ("repair_mr34_teacher_load", {"BATCH": "a" * 64 + "\n"}),
        ("repair_mr34_teacher_load", {"ROW_SUBJECT": "11111111; id"}),
    ):
        result, args = _real_workflow_run(tmp_path, command, "", **changes)
        assert result.returncode != 0
        assert args == []
    assert not (ROOT / "SHOULD_NOT_EXIST").exists()


def test_actual_output_branch_hides_raw_errors_and_rejects_pii_json(tmp_path):
    result, _args = _real_workflow_run(
        tmp_path,
        "repair_mr34_teacher_load",
        "PRIVATE_NAME_SENTINEL\nCommandError: mr34_baseline_changed",
        FIXTURE_COMMAND_STATUS="1",
    )
    assert result.returncode == 1
    assert "CommandError: mr34_baseline_changed" in result.stdout
    assert "PRIVATE_NAME_SENTINEL" not in result.stdout + result.stderr
    bad = {
        "status": "dry_run",
        "baseline": "a" * 64,
        "applied": False,
        "receipt": None,
        "assignments": 5,
        "hours": 135,
        "note": "PRIVATE_NOTE_SENTINEL",
    }
    result, _args = _real_workflow_run(tmp_path, "repair_mr34_teacher_load", json.dumps(bad))
    assert result.returncode != 0
    assert "PRIVATE_NOTE_SENTINEL" not in result.stdout + result.stderr
    assert not (tmp_path / "out.log").exists()


def test_new_choices_checkout_download_cleanup_and_fixed_source_asset():
    workflow = _workflow()
    job = workflow["jobs"]["run"]
    trigger = workflow.get("on", workflow.get(True))
    options = trigger["workflow_dispatch"]["inputs"]["command"]["options"]
    checkout = next(s for s in job["steps"] if "Checkout" in s["name"])
    download = next(s for s in job["steps"] if "reviewed_source_asset.sh" in s.get("run", ""))
    cleanup = next(s for s in job["steps"] if "rm -f /tmp/staff_roster" in s.get("run", ""))
    for name in ("repair_biostat_seminar_share", "repair_mr34_teacher_load"):
        assert name in options and name in checkout["if"] and name in cleanup["if"]
    assert "repair_biostat_seminar_share" in download["if"]
    assert "repair_mr34_teacher_load" not in download["if"]
    assert "biostat_source_*.xlsx" in cleanup["run"]
    assert "confirm == 'APPLY'" in job["if"]
    env = {
        **os.environ,
        "COMMAND": "repair_biostat_seminar_share",
        "ROSTER_TAG": "biostat-kind-share-20261101",
        "BATCH": SOURCE_SHA,
        "GITHUB_RUN_ID": "42",
    }
    shell = "set -euo pipefail; match() { [[ $1 != *$'\\n'* && $1 != *$'\\r'* ]] && [[ $1 =~ $2 ]]; }; source scripts/ops/reviewed_source_asset.sh; printf '%s\\n' \"$asset\" \"$target\""
    result = subprocess.run(["bash", "-c", shell], cwd=ROOT, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == ["biostat.xlsx.enc", "/tmp/biostat_source_42.xlsx"]
    for changes in (
        {"BATCH": "a" * 64},
        {"ROSTER_TAG": "biostat-kind-share-x\n"},
        {"COMMAND": "repair_mr34_teacher_load"},
    ):
        assert (
            subprocess.run(["bash", "-c", shell], cwd=ROOT, env={**env, **changes}, capture_output=True).returncode != 0
        )


def test_mr34_summary_status_shapes_reject_unknown_values_and_bool_counts():
    path = ROOT / "scripts/ops/mr34_teacher_summary.py"
    spec = importlib.util.spec_from_file_location("mr34_summary_fixture", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    import pytest

    for status in ("already_canonical", "already_undone"):
        payload = {
            "status": status,
            "baseline": "a" * 64,
            "applied": False,
            "receipt": RECEIPT if status == "already_undone" else None,
        }
        assert "status=" + status in module.summary(json.dumps(payload))
    payload = {
        "status": "dry_run",
        "baseline": "a" * 64,
        "applied": False,
        "receipt": None,
        "assignments": 5,
        "hours": 135,
    }
    for changes in (
        {"status": "PRIVATE_NAME"},
        {"baseline": "a" * 64 + "\n"},
        {"assignments": True},
        {"hours": 136},
        {"receipt": "$(id)"},
        {"email": "PRIVATE_CONTACT"},
    ):
        with pytest.raises((ValueError, TypeError)):
            module.summary(json.dumps({**payload, **changes}))


def test_actual_biostat_output_never_logs_unknown_numeric_private_fields(tmp_path):
    output = "biostat_kind_share: mode=dry_run baseline=" + "a" * 64 + " owner_unchanged=1 phone=999999"
    result, _args = _real_workflow_run(
        tmp_path, "repair_biostat_seminar_share", output, BATCH=SOURCE_SHA, ROSTER_TAG="biostat-kind-share-20261101"
    )
    assert result.returncode != 0
    assert "999999" not in result.stdout + result.stderr
    assert not (tmp_path / "out.log").exists()
