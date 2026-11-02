"""Closed host protocol and sealed fixed bank/public workflow boundary."""

import importlib.util
import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/ops"))
SPEC = importlib.util.spec_from_file_location("own_base_host", ROOT / "scripts/ops/own_base_syllabus_bank.py")
host = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(host)


@pytest.fixture(autouse=True)
def _rls_bypass_for_tests():
    yield


def payload():
    return dict(
        status="dry_run",
        baseline="a" * 64,
        receipt=None,
        cases=5,
        versions_created=0,
        shares_created=0,
        skip_approved=0,
        skip_existing=0,
        ready=5,
        protected_graph="b" * 64,
    )


def test_dry_closed_summary_and_fixed_counts():
    value = payload()
    assert host.summary(json.dumps(value), apply=False, undo="") == value
    for key, bad in (
        ("cases", 6),
        ("versions_created", 5),
        ("shares_created", 2),
        ("ready", 4),
        ("receipt", "private-name"),
        ("baseline", "not-a-hash"),
    ):
        changed = dict(value, **{key: bad})
        with pytest.raises(ValueError):
            host.summary(json.dumps(changed), apply=False, undo="")


def test_apply_status_never_accepted_by_dry_and_no_free_text_fields():
    value = dict(
        payload(),
        status="applied",
        receipt="00000000-0000-0000-0000-000000000001",
        versions_created=4,
        shares_created=1,
    )
    assert host.summary(json.dumps(value), apply=True, undo="")["cases"] == 5
    with pytest.raises(ValueError):
        host.summary(json.dumps(value), apply=False, undo="")
    with pytest.raises(ValueError):
        host.summary(json.dumps(dict(value, source_body="private")), apply=True, undo="")
    with pytest.raises(ValueError):
        host.summary(json.dumps(value)[:-1] + ',"cases":5}', apply=True, undo="")


def test_fixed_cipher_transport_and_command():
    workflow = (ROOT / ".github/workflows/own-base-syllabus-bank.yml").read_text()
    runner = (ROOT / "scripts/ops/own_base_syllabus_bank.py").read_text()
    assert "cancel-in-progress: false" in workflow and "group: production-deploy" in workflow
    assert "persist-credentials: false" in workflow and "environment: production" in workflow
    assert "scripts/ops/own_base_syllabus_bank.py" in workflow
    assert "recover_own_base_syllabi" in runner
    assert "verify_head(" in runner and "write_private_source(" in runner
    assert "own-base-five.json.enc" in runner and "200000" in runner
    assert "if: always()" in workflow and "reviewed-ownbase-" in workflow
    assert host.safe_failure("CommandError: ownbase_academic_graph_changed\n") == "ownbase_academic_graph_changed"
    assert host.safe_failure("private teacher name") == "ownbase_command_refused"


def test_fixed_subbatches_never_accept_arbitrary_course_scope():
    for batch, cases in (("ordinary", 2), ("design", 3)):
        value = dict(payload(), cases=cases, ready=cases)
        assert host.summary(json.dumps(value), apply=False, undo="", batch=batch)["cases"] == cases
    with pytest.raises(ValueError):
        host.summary(json.dumps(payload()), apply=False, undo="", batch="custom-course")
