"""Expose fixed capture context without ever publishing native stderr or SQL."""

import json
from types import SimpleNamespace

import pytest

from apps.legacy_import.tests.test_reaudit_snapshot import transport


def diagnostic(**changes):
    return {
        "format": "reaudit-snapshot-error/1",
        "model": "legacy_import.LegacyEntityMap",
        "operation": "count",
        "page": None,
        "code": "snapshot_unexpected_failure",
        "exception": "OperationalError",
        "sqlstate": "57014",
        **changes,
    }


def result(module, monkeypatch, payload):
    marker = module.ERROR_PREFIX + json.dumps(payload)
    stderr = "PRIVATE SQL and actor must never be echoed\n" + marker + "\nCommandError: reaudit_snapshot_failed\n"
    monkeypatch.setattr(
        module.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr=stderr)
    )


def test_known_native_failure_exposes_only_validated_context(monkeypatch):
    module = transport()
    result(module, monkeypatch, diagnostic())
    with pytest.raises(module.NativeSnapshotError) as failure:
        module.native_command(["synthetic"])
    assert failure.value.diagnostic == diagnostic()
    output = module.failure_message(failure.value)
    assert "57014" in output and "legacy_import.LegacyEntityMap" in output
    assert "PRIVATE" not in output and "actor" not in output and "SQL" not in output
    assert str(failure.value) == "snapshot_native_failed"


@pytest.mark.parametrize(
    "changes",
    [
        {"model": "private_unknown_table"},
        {"operation": "SELECT private"},
        {"page": -1},
        {"page": True},
        {"code": "private_value"},
        {"exception": "PrivateStudentName"},
        {"sqlstate": "private"},
        {"extra": "private"},
    ],
)
def test_invalid_diagnostics_are_never_echoed(monkeypatch, changes):
    module = transport()
    result(module, monkeypatch, diagnostic(**changes))
    with pytest.raises(ValueError, match="snapshot_safe_diagnostic_invalid") as failure:
        module.native_command(["synthetic"])
    assert module.failure_message(failure.value) == "reaudit_capture_refused:ValueError"


@pytest.mark.parametrize("kind", ["missing", "duplicate", "oversize", "malformed"])
def test_untrusted_native_stderr_cannot_be_used_as_a_diagnostic(monkeypatch, kind):
    module = transport()
    marker = module.ERROR_PREFIX + json.dumps(diagnostic())
    stderr = {
        "missing": "PRIVATE SQL/row/path/actor",
        "duplicate": marker + "\n" + marker,
        "oversize": marker + "\n" + "PRIVATE" * 50000,
        "malformed": module.ERROR_PREFIX + "{PRIVATE}",
    }[kind]
    monkeypatch.setattr(
        module.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr=stderr)
    )
    with pytest.raises(ValueError) as failure:
        module.native_command(["synthetic"])
    assert module.failure_message(failure.value) == "reaudit_capture_refused:ValueError"


def test_success_keeps_native_summary_and_drops_stderr(monkeypatch):
    module = transport()
    monkeypatch.setattr(
        module.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="summary", stderr="PRIVATE"),
    )
    assert module.native_command(["synthetic"]) == "summary"
