"""Only a trusted main deployment, the daily schedule or an operator may run cache maintenance."""

from pathlib import Path

import yaml

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"


def test_build_cache_policy_runs_on_main_after_a_successful_deploy():
    ci = yaml.safe_load((WORKFLOWS / "ci.yml").read_text())
    job = ci["jobs"]["maintain-build-cache"]
    assert job["needs"] == "deploy-production"
    assert "github.event_name == 'push'" in job["if"]
    assert "github.ref == 'refs/heads/main'" in job["if"]
    assert "needs.deploy-production.result == 'success'" in job["if"]
    assert job["uses"] == "./.github/workflows/prod-build-cache.yml"


def test_scheduled_cache_maintenance_defaults_to_budget_and_fetches_reviewed_code():
    workflow = yaml.safe_load((WORKFLOWS / "prod-build-cache.yml").read_text())
    events = workflow[True]  # PyYAML loads the GitHub Actions 'on' key as a YAML 1.1 boolean.
    mode = events["workflow_dispatch"]["inputs"]["mode"]
    assert mode["default"] == "budget" and mode["options"] == ["budget", "clear-unused"]
    assert events["schedule"] == [{"cron": "17,47 * * * *"}] and "workflow_call" in events
    assert workflow["permissions"] == {"contents": "read"}
    job = workflow["jobs"]["maintain"]
    assert "github.ref == 'refs/heads/main'" in job["if"]
    assert job["environment"] == "production" and job["runs-on"] == ["self-hosted"]
    step = job["steps"][0]
    assert step["env"]["CACHE_MODE"] == "${{ inputs.mode || 'budget' }}"
    assert "ref=${GITHUB_SHA}" in step["run"] and 'bash "$script" "$CACHE_MODE"' in step["run"]
