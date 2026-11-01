"""Fixed host source, strict command summary and no caller-selected journal scope."""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/ops"))


def load():
    spec = importlib.util.spec_from_file_location(
        "half_pair_host_test", ROOT / "scripts/ops/reviewed_half_pair_hours.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def value(status="dry_run", undo=False):
    changed = status in {"applied", "undone"}
    repeated = status in {"already_present", "already_undone"}
    result = dict(
        status=status,
        baseline="a" * 64,
        preview_sha256="b" * 64,
        receipt=None if status == "dry_run" and not undo else "11111111-1111-4111-8111-111111111111",
        planned_lessons=0 if repeated else 3,
        preserved_marks=70,
        raw_qb_count_delta=0,
        raw_own_hours_delta=0 if repeated else 16 if undo else -16,
        lessons_changed=3 if changed else 0,
        marks_changed=0,
        credits_changed=0,
        cached_before=220,
        derived_before=210,
        derived_after=203,
        stale_before=3,
    )
    if changed:
        result["after_baseline"] = "c" * 64
    return result


def raw(result):
    return "reviewed_half_pair_hours: " + json.dumps(result)


@pytest.mark.parametrize(
    "status,apply,undo",
    [
        ("dry_run", False, False),
        ("applied", True, False),
        ("already_present", False, False),
        ("already_present", True, False),
        ("dry_run", False, True),
        ("undone", True, True),
        ("already_undone", False, True),
        ("already_undone", True, True),
    ],
)
def test_forward_and_undo_fixed_contract_preserves_credit_aware_cache(status, apply, undo):
    result = value(status, undo)
    assert load().summary(raw(result), apply=apply, undo=undo) == result
    # Canonical effective delta need not equal the own raw-hours delta.
    assert result["derived_after"] - result["derived_before"] != result["raw_own_hours_delta"]


@pytest.mark.parametrize(
    "key,changed",
    [
        ("planned_lessons", 2),
        ("preserved_marks", 69),
        ("raw_qb_count_delta", -1),
        ("raw_own_hours_delta", -15),
        ("marks_changed", 1),
        ("credits_changed", 1),
        ("baseline", "wrong"),
        ("cached_before", True),
        ("receipt", None),
    ],
)
def test_unknown_counts_and_grade_or_credit_changes_are_rejected(key, changed):
    result = value("applied")
    result[key] = changed
    with pytest.raises(ValueError):
        load().summary(raw(result), apply=True, undo=False)


def test_extra_output_unknown_keys_and_mode_mismatch_rejected():
    host = load()
    for result in (raw(value()) + "\nextra", raw({**value(), "offering_id": "anything"})):
        with pytest.raises(ValueError):
            host.summary(result, apply=False, undo=False)
    with pytest.raises(ValueError):
        host.summary(raw(value("applied")), apply=False, undo=False)


def test_no_runtime_source_or_scope_selector_inputs():
    host = load()
    for key in ("file", "sha256", "offering", "teacher", "source_tag", "hours"):
        with pytest.raises(ValueError):
            host.inputs({"actor": "superadmin", key: "untrusted"})


def test_source_failure_cleans_private_folder_without_any_management_command(tmp_path, monkeypatch):
    host = load()
    commands = []
    monkeypatch.setattr(host, "verify_head", lambda head: None)
    monkeypatch.setattr(host, "command", lambda argv: commands.append(argv))
    monkeypatch.setattr(host, "source", lambda *a: (_ for _ in ()).throw(ValueError("release_asset_missing")))
    env = {"GITHUB_RUN_ID": "1", "GITHUB_RUN_ATTEMPT": "1", "GITHUB_SHA": "a" * 40, "RUNNER_TEMP": str(tmp_path)}
    with pytest.raises(ValueError):
        host.execute({"actor": "superadmin", "apply": False}, env)
    assert not (tmp_path / "half-pair-hours-1-1").exists()
    assert not any("manage.py" in argv for argv in commands)


def test_workflow_and_encrypted_source_pins_are_fixed():
    host = load()
    workflow = (ROOT / ".github/workflows/reviewed-half-pair-hours.yml").read_text()
    assert "group: production-deploy" in workflow
    assert "cancel-in-progress: false" in workflow
    assert "github.token" in workflow and "STAFF_PLAN_KEY" in workflow
    assert "reviewed_half_pair_hours.py" in workflow
    assert host.SOURCE_SHA == "127a1dbe67fcc2f1e5aa9756988032cd6d3b0c36ef8d3be934ee5d79cc4ec96a"
    assert host.CIPHER_SHA == "9aaec2b11e70c6d8fb28632cd0f9ce904b5a3d2ab8d2a6911fc70b823962e698"
