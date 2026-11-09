"""Public operation logs contain only the native fixed diagnostic contract."""

import importlib.util
import json
from pathlib import Path

import pytest


@pytest.fixture
def operation(monkeypatch):
    ops = Path(__file__).resolve().parents[1] / "scripts/ops"
    monkeypatch.syspath_prepend(str(ops))
    spec = importlib.util.spec_from_file_location("structure_error_transport_test", ops / "reaudit_remediation.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def payload(**changes):
    return {
        "format": "reaudit-structure-error/1",
        "phase": "repair",
        "operation": "half_pair",
        "model": "registrar.Lesson",
        "table": "registrar_lesson",
        "exception": "OperationalError",
        "sqlstate": "57014",
        "code": "structure_refused",
        **changes,
    }


def marker(value):
    return "reaudit_structure_error: " + json.dumps(value)


def test_only_validated_context_is_forwarded(operation, capsys):
    raw = "PRIVATE SQL and actor\n" + marker(payload()) + "\nCommandError: structure_refused\n"
    assert operation.emit_structure_diagnostic(raw) is True
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == marker(payload()).split(": ", 1)[0] + ": " + json.dumps(payload(), sort_keys=True) + "\n"
    assert "PRIVATE" not in captured.err


@pytest.mark.parametrize(
    "changes",
    [
        {"phase": "private"},
        {"operation": "private"},
        {"model": "registrar.PrivateStudentName"},
        {"table": "auth_user"},
        {"exception": "PrivateStudentName"},
        {"sqlstate": "private"},
        {"code": "private"},
        {"extra": "private"},
    ],
)
def test_invalid_context_never_reaches_public_logs(operation, capsys, changes):
    with pytest.raises(ValueError, match="structure_safe_diagnostic_invalid"):
        operation.emit_structure_diagnostic(marker(payload(**changes)))
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


@pytest.mark.parametrize("kind", ["duplicate", "oversize", "malformed"])
def test_broken_or_ambiguous_marker_is_not_printed(operation, capsys, kind):
    line = marker(payload())
    raw = {
        "duplicate": line + "\n" + line,
        "oversize": line + "\n" + "PRIVATE" * 50000,
        "malformed": "reaudit_structure_error: {PRIVATE}",
    }[kind]
    with pytest.raises(ValueError):
        operation.emit_structure_diagnostic(raw)
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""


def test_existing_refusal_without_diagnostics_is_left_to_existing_handler(operation, capsys):
    assert operation.emit_structure_diagnostic("CommandError: structure_half_pair_identity_changed") is False
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""
