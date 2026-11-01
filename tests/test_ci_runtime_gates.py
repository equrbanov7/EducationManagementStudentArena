"""Prod test qapıları qalır, əlavə Python uyğunluğu deploy-u gözlətmir."""

from pathlib import Path

import yaml

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"


def _workflow(name):
    return yaml.safe_load((WORKFLOWS / name).read_text())


def test_compatibility_is_scheduled_and_manual_without_deploy_permissions():
    compat = _workflow("python-311-compat.yml")
    triggers = compat.get("on", compat.get(True))
    assert set(triggers) == {"schedule", "workflow_dispatch"}
    assert triggers["schedule"]
    assert compat["permissions"] == {"contents": "read"}
    assert set(compat["jobs"]) == {"compatibility"}
    job = compat["jobs"]["compatibility"]
    assert job["uses"] == "./.github/workflows/_unit-tests.yml"
    assert job["with"] == {"python-version": "3.11", "coverage": True}


def test_prod_suite_and_isolation_still_block_merge_and_deploy():
    jobs = _workflow("ci.yml")["jobs"]
    needs = set(jobs["ci-success"]["needs"])
    assert "unit-tests-311" not in jobs
    assert "unit-tests-311" not in needs
    assert {
        "lint",
        "unit-tests-312",
        "coverage-combine",
        "rls-txn-pool",
        "js-tests",
        "build",
        "security",
        "secret-scan",
        "docker-build",
        "container-scan",
        "prod-smoke",
        "e2e-smoke",
    } <= needs
    assert jobs["unit-tests-312"]["strategy"]["matrix"]["shard"] == [str(i) for i in range(1, 9)]
    assert jobs["unit-tests-312"]["with"]["python-version"] == "3.12"
    for name in needs:
        assert not jobs[name].get("continue-on-error", False), name
    deploy = jobs["deploy-production"]
    assert deploy["needs"] == "ci-success"
    assert "needs.ci-success.result == 'success'" in deploy["if"]


def test_pr_keeps_coverage_when_compatibility_suite_moves_out():
    jobs = _workflow("ci.yml")["jobs"]
    assert "github.event_name == 'pull_request'" in jobs["unit-tests-312"]["with"]["coverage-data"]
    assert "github.event_name == 'pull_request'" in jobs["coverage-combine"]["if"]
    gate = jobs["ci-success"]["steps"][0]
    assert "github.event_name == 'pull_request'" in gate["env"]["COVERAGE_GATE_REQUIRED"]
    assert "coverage xml --fail-under=68" in str(jobs["coverage-combine"])


def test_duration_cache_stays_inside_checkout_to_preserve_nodeid_namespace():
    steps = _workflow("_unit-tests.yml")["jobs"]["unit-tests"]["steps"]
    run = next(step["run"] for step in steps if "durations_file=" in step.get("run", ""))
    assert 'durations_file="$PWD/test_durations.shard-${SHARD}.json"' in run
    assert 'durations_file="$RUNNER_TEMP/' not in run
    assert '--durations-path "$durations_file" --store-durations --clean-durations' in run
    upload = next(step for step in steps if step.get("name") == "⏱️ Upload shard test durations")
    assert upload["with"]["path"] == "${{ github.workspace }}/test_durations.shard-${{ inputs.shard }}.json"
    assert '--splits "$SHARDS" --group "$SHARD" --splitting-algorithm least_duration' in run
    assert "--ignore=tests/e2e" in run


def test_xml_coverage_gate_rejects_low_coverage_and_preserves_report(tmp_path):
    """Exercise the real coverage CLI: XML must fail closed at the same 68% gate."""
    import subprocess
    import sys
    import xml.etree.ElementTree as ET

    program = tmp_path / "sample.py"
    program.write_text(
        "import os\nif os.environ.get('NEVER_COVERED'):\n    a = 1\n    b = 2\n    c = 3\n    d = 4\nelse:\n    value = 2\n"
    )
    config = tmp_path / ".coveragerc"
    config.write_text("[run]\nbranch = True\n")
    prefix = [sys.executable, "-m", "coverage"]
    measured = subprocess.run(
        [*prefix, "run", f"--rcfile={config}", str(program)], cwd=tmp_path, capture_output=True, text=True
    )
    assert measured.returncode == 0, measured.stderr
    gate = subprocess.run(
        [*prefix, "xml", f"--rcfile={config}", "--fail-under=68", "-o", "coverage.xml"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert gate.returncode == 2, gate.stdout + gate.stderr
    report = ET.parse(tmp_path / "coverage.xml").getroot()
    assert float(report.attrib["line-rate"]) < 0.68
    # The same XML command accepts a fully exercised program.
    program.write_text("value = 2\n")
    subprocess.run([*prefix, "run", f"--rcfile={config}", str(program)], cwd=tmp_path, check=True)
    gate = subprocess.run(
        [*prefix, "xml", f"--rcfile={config}", "--fail-under=68", "-o", "coverage.xml"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert gate.returncode == 0, gate.stdout + gate.stderr
