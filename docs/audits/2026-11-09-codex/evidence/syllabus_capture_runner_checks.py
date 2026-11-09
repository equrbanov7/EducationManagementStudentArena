"""Offline dispatch guard checks; no GitHub request or production operation."""

import base64
import contextlib
import importlib
import io
import json
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

runner = importlib.import_module("capture_syllabus_packs")


def rejected(function, reason):
    try:
        function()
    except RuntimeError as error:
        assert str(error) == reason
    else:
        raise AssertionError("expected refusal")


def run():
    checks = {}
    with tempfile.TemporaryDirectory(prefix="syllabus-runner-check-") as raw:
        folder = Path(raw)
        with (
            patch.object(runner, "HERE", folder),
            patch.object(runner, "api", side_effect=AssertionError("network called")),
        ):
            with contextlib.redirect_stdout(io.StringIO()):
                runner.main(["--private-dir", str(folder)])
            assert json.loads((folder / "syllabus_capture_plan.json").read_text())["dispatch_enabled"] is False
        checks["default_plan_never_calls_network"] = True
        rejected(lambda: runner.require_journal_queue_done(folder), "journal_queue_state_missing")
        state = {f"journal-pack-{i:03}": {"state": "complete"} for i in range(1, 20)}
        state["journal-pack-019"]["state"] = "running"
        runner.save(folder / "pack-dispatches.json", state)
        rejected(lambda: runner.require_journal_queue_done(folder), "journal_queue_not_complete")
        state["journal-pack-019"]["state"] = "complete"
        runner.save(folder / "pack-dispatches.json", state)
        runner.require_journal_queue_done(folder)
        checks["journal_queue_guard"] = True
        dispatches = []

        def uncertain_api(path, payload=None):
            if payload is not None:
                dispatches.append(path)
                raise RuntimeError("simulated_uncertain_post")
            if path == "git/ref/heads/main":
                return {"object": {"sha": runner.HEAD}}
            return {"workflow_runs": []}

        current = {}
        with (
            patch.object(runner, "api", side_effect=uncertain_api),
            patch.object(runner, "require_production_queue_idle"),
        ):
            rejected(
                lambda: runner.process(runner.PRIORITY[0], current, folder, "fake-actor", b"fake-key"),
                "simulated_uncertain_post",
            )
        persisted = json.loads((folder / runner.STATE_FILE).read_text())
        assert persisted[runner.PRIORITY[0]]["state"] == "dispatch_intent"
        assert len(dispatches) == 1
        checks["intent_durable_before_uncertain_post"] = True
        with patch.object(runner, "api", side_effect=uncertain_api), patch.object(runner.time, "sleep"):
            rejected(
                lambda: runner.process(runner.PRIORITY[0], persisted, folder, "fake-actor", b"fake-key"),
                "unresolved_dispatch_never_repeat_post",
            )
        assert len(dispatches) == 1
        checks["uncertain_post_never_retried"] = True
        base = {
            "head_sha": runner.HEAD,
            "head_branch": "main",
            "event": "workflow_dispatch",
            "display_title": f"Syllabus content: {runner.PRIORITY[0]}",
        }
        assert runner.matches(base, runner.PRIORITY[0])
        assert not runner.matches({**base, "head_sha": "0" * 40}, runner.PRIORITY[0])
        assert not runner.matches({**base, "display_title": "Syllabus content: syllabus-pack-008"}, runner.PRIORITY[0])
        checks["exact_head_and_pack_run_identity"] = True
        with patch.object(runner, "runs", return_value=[{**base, "id": 10}, {**base, "id": 11}]):
            rejected(
                lambda: runner.resolve_run(
                    persisted[runner.PRIORITY[0]], persisted, folder / runner.STATE_FILE, runner.PRIORITY[0]
                ),
                "ambiguous_dispatch_requires_read_only_review",
            )
        checks["ambiguous_run_refused"] = True
        rejected(lambda: runner.plan(["syllabus-pack-001"]), "reviewed_pack_selection_required")
        checks["only_reviewed_pack_selection"] = True
        historical = {
            "id": runner.HISTORICAL_CI_RUN,
            "head_sha": runner.HISTORICAL_CI_HEAD,
            "head_branch": "Develop",
            "event": "push",
            "status": "queued",
            "path": ".github/workflows/ci.yml",
        }
        workflow = {
            "concurrency": {"group": "${{ github.workflow }}-${{ github.ref }}", "cancel-in-progress": True},
            "jobs": {
                "deploy-production": {
                    "if": "github.event_name == 'push' && github.ref == 'refs/heads/main'",
                    "needs": "ci-success",
                    "concurrency": {"group": "production-deploy", "cancel-in-progress": False},
                }
            },
        }
        fixture_raw = json.dumps(workflow).encode()
        fixture_content = {"encoding": "base64", "content": base64.b64encode(fixture_raw).decode()}
        remote_reads = []

        def historical_api(path, payload=None):
            assert payload is None, "queue exception must never write"
            remote_reads.append(path)
            if path.startswith("contents/"):
                assert path.endswith("?ref=" + runner.HISTORICAL_CI_HEAD)
                return fixture_content
            if path.startswith("actions/runs/34748949558/jobs"):
                return {"total_count": 0, "jobs": []}
            return {"workflow_runs": [historical] if "status=queued" in path else []}

        with (
            patch.object(runner, "api", side_effect=historical_api),
            patch.object(runner, "HISTORICAL_CI_SHA256", runner.sha(fixture_raw)),
        ):
            runner.require_production_queue_idle()
            checks["exact_historical_main_only_workflow_allowed"] = True
            for field, value in {
                "id": 1,
                "head_sha": runner.HEAD,
                "head_branch": "main",
                "event": "workflow_dispatch",
                "status": "in_progress",
                "path": ".github/workflows/prod-data-ops.yml",
            }.items():
                before = len(remote_reads)
                assert not runner.historical_develop_ci_cannot_deploy({**historical, field: value})
                assert len(remote_reads) == before
            checks["exception_never_generalizes_run_branch_sha_event_status_path"] = True
            with patch.object(runner, "HISTORICAL_CI_SHA256", "0" * 64):
                assert not runner.historical_develop_ci_cannot_deploy(historical)
            checks["historical_workflow_digest_required"] = True
            unsafe = json.loads(json.dumps(workflow))
            unsafe["jobs"]["deploy-production"]["if"] = "github.event_name == 'push'"
            unsafe_raw = json.dumps(unsafe).encode()
            with (
                patch.object(runner, "HISTORICAL_CI_SHA256", runner.sha(unsafe_raw)),
                patch.object(
                    runner,
                    "api",
                    return_value={"encoding": "base64", "content": base64.b64encode(unsafe_raw).decode()},
                ),
            ):
                assert not runner.historical_develop_ci_cannot_deploy(historical)
            checks["historical_deploy_condition_must_be_main_only"] = True
            with patch.object(runner, "api", return_value={"workflow_runs": [{**historical, "head_branch": "main"}]}):
                rejected(runner.require_production_queue_idle, "production_mutex_queue_busy")
            checks["main_ci_still_blocks"] = True
            with patch.object(
                runner,
                "api",
                return_value={"workflow_runs": [{**historical, "path": ".github/workflows/prod-data-ops.yml"}]},
            ):
                rejected(runner.require_production_queue_idle, "production_mutex_queue_busy")
            checks["other_production_workflow_still_blocks"] = True
            with patch.object(runner, "api", side_effect=[fixture_content, {"total_count": 1, "jobs": [{"id": 1}]}]):
                assert not runner.historical_develop_ci_cannot_deploy(historical)
            checks["historical_jobs_must_remain_empty"] = True
    with tempfile.TemporaryDirectory(prefix="syllabus-git-check-") as raw:
        folder = Path(raw)

        def git(*args):
            return subprocess.run(["git", *args], cwd=folder, check=True, capture_output=True, text=True).stdout.strip()

        git("init", "--quiet")
        git("config", "user.name", "Audit fixture")
        git("config", "user.email", "audit@example.invalid")
        (folder / "apps").mkdir()
        application = folder / "apps" / "native.py"
        application.write_text("unchanged\n")
        git("add", ".")
        git("commit", "--quiet", "--no-gpg-sign", "-m", "fixture baseline")
        baseline = git("rev-parse", "HEAD")
        audit = folder / runner.AUDIT_PREFIX
        audit.mkdir(parents=True)
        (audit / "report.md").write_text("report\n")
        git("add", ".")
        git("commit", "--quiet", "--no-gpg-sign", "-m", "audit checkpoint")
        assert git("rev-parse", "HEAD") != baseline
        (audit / "untracked-report.json").write_text("{}\n")
        with patch.object(runner, "ROOT", folder), patch.object(runner, "HEAD", baseline):
            runner.require_application_tree_unchanged()
            checks["docs_checkpoint_and_untracked_audit_allowed"] = True
            application.write_text("working tree modification\n")
            rejected(runner.require_application_tree_unchanged, "local_application_tree_changed")
            checks["unstaged_app_change_refused"] = True
            git("add", "apps/native.py")
            rejected(runner.require_application_tree_unchanged, "local_application_tree_changed")
            checks["staged_app_change_refused"] = True
            git("reset", "--hard", "HEAD")
            (folder / "apps" / "untracked.py").write_text("new app code\n")
            rejected(runner.require_application_tree_unchanged, "local_application_tree_changed")
            checks["untracked_app_code_refused"] = True
    result = {"network_calls": 0, "production_dispatches": 0, "all_passed": all(checks.values()), "checks": checks}
    (Path(__file__).parent / "syllabus_capture_runner_validation.json").write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n"
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    run()
