import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/ops"))
spec = importlib.util.spec_from_file_location("nezife_host", ROOT / "scripts/ops/reviewed_nezife_label.py")
host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(host)


def valid():
    return dict(status="dry_run", applied=False, count=1, baseline="a" * 64, receipt=None)


def test_exact_safe_summary():
    assert host.summary(host.PREFIX + json.dumps(valid()), apply=False, undo="").startswith(host.PREFIX)


@pytest.mark.parametrize(
    "change",
    [
        {"count": 2},
        {"count": True},
        {"status": "applied"},
        {"applied": True},
        {"receipt": "secret"},
        {"baseline": "wrong"},
        {"private": "student"},
    ],
)
def test_false_or_private_summary_refused(change):
    with pytest.raises(ValueError):
        host.summary(host.PREFIX + json.dumps({**valid(), **change}), apply=False, undo="")


def test_scope_workflow_has_no_arbitrary_targets():
    text = (ROOT / ".github/workflows/reviewed-nezife-label.yml").read_text()
    assert "production-deploy" in text
    assert "lesson_id:" not in text and "teacher_id:" not in text


def test_exact_production_source_scope():
    import ast

    tree = ast.parse((ROOT / "apps/registrar/reviewed_nezife_label.py").read_text())
    names = {"ORG", "PERIOD", "OFFERING", "GROUP", "SUBJECT", "TEACHER", "LESSON", "SLOT", "ROOM", "REASON"}
    fixed = {
        n.targets[0].id: ast.literal_eval(n.value)
        for n in tree.body
        if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and n.targets[0].id in names
    }
    assert fixed == dict(
        ORG="526cfa63-4f80-4bba-a7a7-61c8fbb3d918",
        PERIOD="a4f88744-8d49-4772-84ef-c28a96c3b372",
        OFFERING="3326514c-9fe5-4bc0-8167-3f949fa9a054",
        GROUP="0a1783b0-1f13-41ff-bbeb-51652b68b70d",
        SUBJECT="86f4817f-802b-43ec-9774-ec7f869a35ad",
        TEACHER=8420,
        LESSON="6a2f801f-a770-48c2-aa3c-73043c461865",
        SLOT="c7b0d9bc-03fa-4398-a676-4a9747b73b1d",
        ROOM=379,
        REASON="Cədvələ aiddir bu dərs",
    )


def native_diagnostic():
    spec = importlib.util.spec_from_file_location(
        "nezife_native_diagnostic", ROOT / "apps/registrar/reviewed_nezife_diagnostic.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_closed_guard_inventory_matches_existing_native_require_literals():
    import ast

    tree = ast.parse((ROOT / "apps/registrar/reviewed_nezife_label.py").read_text())
    actual = {
        n.args[1].value
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "require"
        and len(n.args) > 1
        and isinstance(n.args[1], ast.Constant)
    }
    assert native_diagnostic().SAFE_GUARDS == actual
    assert host.SAFE_GUARDS == actual | {"nezife_label_refused"}
    for guard in actual:
        assert native_diagnostic().native_failure(ValueError(guard)) == guard
        assert host.safe_failure("CommandError: " + guard + "\n") == guard


@pytest.mark.parametrize(
    "stderr",
    [
        "CommandError: nezife_new_unreviewed_guard\n",
        "CommandError: nezife_course_changed private-name\n",
        "CommandError: nezife_course_changed\nprivate-account",
        "CommandError: nezife_course_changed\n\n",
        "Traceback: private-fin-or-password",
        "CommandError: nezife_" + "x" * 257,
        "\x1b[31mCommandError: nezife_course_changed\x1b[0m",
    ],
)
def test_host_does_not_emit_unknown_multiline_or_private_refusals(stderr):
    assert host.safe_failure(stderr) == "reviewed_nezife_label_refused"


@pytest.mark.parametrize(
    "exc",
    [
        ValueError("private-student"),
        ValueError("nezife_course_changed", "private-extra"),
        RuntimeError("nezife_course_changed"),
        ValueError("nezife_lesson_changed\nprivate-data"),
    ],
)
def test_native_unknown_exception_redacted(exc):
    assert native_diagnostic().native_failure(exc) == "nezife_label_refused"


def test_native_failure_with_stdout_never_leaks_guard_or_private_text(monkeypatch, capsys):
    from types import SimpleNamespace

    monkeypatch.setattr(host, "inputs", lambda value: ("private-actor", [], False, ""))
    monkeypatch.setattr(host, "verify_head", lambda head: None)
    monkeypatch.setattr(
        host.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1, stdout="private-student-content", stderr="CommandError: nezife_lesson_changed\n"
        ),
    )
    with pytest.raises(host.Refused, match="^reviewed_nezife_label_refused$"):
        host.execute({}, {"GITHUB_RUN_ID": "1", "GITHUB_RUN_ATTEMPT": "1"})
    captured = capsys.readouterr()
    assert "private-student-content" not in captured.out + captured.err
    assert "nezife_lesson_changed" not in captured.out + captured.err


def test_safe_guard_main_single_line_and_failure_exit(monkeypatch, tmp_path, capsys):
    event = tmp_path / "event.json"
    event.write_text('{"inputs": {}}')
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))

    def refuse(*args, **kwargs):
        raise host.Refused("nezife_unreceipted_clear")

    monkeypatch.setattr(host, "execute", refuse)
    assert host.main() == 2
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == "nezife_unreceipted_clear\n"
    assert len(output.err.encode()) <= 256
