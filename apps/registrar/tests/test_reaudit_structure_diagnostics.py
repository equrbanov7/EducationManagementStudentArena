"""Safe failure metadata only; original SQL failure survives RLS cleanup errors."""

import ast
import io
import json
from pathlib import Path
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import OperationalError, connection
from django.test import override_settings

import pytest

from apps.registrar import reaudit_structure_diagnostics as diagnostics
from apps.registrar.management.commands import repair_reaudit_journal_structure as command
from core.rls import bypass_rls


def test_fixed_model_table_pairs_match_registry_without_requiring_all_future_models():
    for label, table in diagnostics.MODEL_TABLES.items():
        assert apps.get_model(label)._meta.db_table == table


def test_every_existing_structure_refusal_is_preserved():
    folder = Path(__file__).resolve().parents[1]
    paths = [
        *folder.glob("reaudit_journal_structure*.py"),
        folder / "management/commands/repair_reaudit_journal_structure.py",
    ]
    for path in paths:
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if (
                    node.value.startswith("structure_")
                    and node.value != "structure_"
                    and node.value.replace("_", "").isalpha()
                ):
                    assert node.value in diagnostics.CODES


def test_sql_and_parameter_contents_never_enter_diagnostic():
    trace = diagnostics.QueryTrace()
    trace.phase, trace.operation = "repair", "half_pair"
    secret = "PRIVATE_STUDENT_SCORE_CREDENTIAL"
    trace(lambda *args: None, 'SELECT * FROM "registrar_lesson" WHERE topic=%s', [secret], False, {})
    payload = trace.capture(ValueError(secret))
    assert payload["model"] == "registrar.Lesson"
    assert payload["table"] == "registrar_lesson"
    assert payload["code"] == "structure_refused"
    assert secret not in json.dumps(payload)
    assert not {"sql", "params", "message"}.intersection(payload)
    assert not hasattr(trace, "sql") and not hasattr(trace, "params")


def test_unknown_table_and_exception_class_are_not_rendered():
    secret_exception = type("PRIVATE_ACTOR_FIN", (Exception,), {})
    trace = diagnostics.QueryTrace()
    trace(lambda *args: None, "SELECT * FROM private_secret_table", [], False, {})
    payload = trace.capture(secret_exception("private payload"))
    assert payload["model"] is None and payload["table"] is None
    assert payload["exception"] == "Exception"
    assert "private" not in json.dumps(payload).lower()


def test_pg_sqlstate_and_first_failure_survive_cleanup():
    class DriverError(Exception):
        pgcode = "57014"

    original = OperationalError("private statement timeout details")
    original.__cause__ = DriverError("SQL and parameters must stay private")
    trace = diagnostics.QueryTrace()
    trace.phase, trace.operation = "repair", "half_pair"

    def failure(*args):
        raise original

    with pytest.raises(OperationalError):
        trace(failure, 'SELECT * FROM "registrar_lessonmark"', [], False, {})
    payload = trace.capture(original)
    trace.phase = "reset_rls"
    trace(lambda *args: None, "SELECT set_config(%s,%s,true)", ["secret", "secret"], False, {})
    assert trace.capture(RuntimeError("cleanup private failure")) == payload
    assert (payload["sqlstate"], payload["model"], payload["phase"]) == ("57014", "registrar.LessonMark", "repair")


def test_handled_sql_failure_does_not_override_later_domain_refusal():
    trace = diagnostics.QueryTrace()
    try:
        trace(lambda *args: (_ for _ in ()).throw(OperationalError("handled")), "SELECT 1", [], False, {})
    except OperationalError:
        pass
    assert trace.capture(ValueError("structure_family_budget"))["code"] == "structure_family_budget"


@pytest.mark.parametrize(
    "change",
    [
        {"unexpected": "private"},
        {"model": "private"},
        {"table": "private"},
        {"phase": "private"},
        {"operation": "private"},
        {"exception": "private"},
        {"sqlstate": "57014 private"},
        {"code": "structure_private_student_name"},
    ],
)
def test_host_validator_rejects_unrecognized_fields_and_values(change):
    payload = diagnostics.QueryTrace().capture(ValueError("structure_scope_changed"))
    with pytest.raises(ValueError, match="structure_diagnostic_invalid"):
        diagnostics.validate({**payload, **change})


@pytest.mark.django_db(transaction=True)
@override_settings(RLS_TRANSACTION_SCOPED=True)
def test_real_pg_command_failure_reports_original_select_and_rolls_back():
    with bypass_rls():
        actor = get_user_model().objects.create_superuser("structure-diagnostic-operator", password="test-only")
        organization = apps.get_model("organizations.Organization").objects.create(
            name="Diagnostic test",
            slug="structure-diagnostic-test",
            owner=actor,
            org_type="university",
            status="active",
            is_active=True,
        )
    manifest = {"operation": "half_pair"}
    stderr, stdout = io.StringIO(), io.StringIO()

    def failing_select(**kwargs):
        with connection.cursor() as cursor:
            cursor.execute('SELECT id FROM "registrar_lesson" WHERE private_missing_column=%s', ["PRIVATE_VALUE"])

    with (
        patch.object(command.spec, "private_bytes", return_value=b"{}"),
        patch.object(command.spec, "validate", return_value=manifest),
        patch.object(command.spec, "ORG", str(organization.pk)),
        patch.object(command.repair, "run", side_effect=failing_select),
        pytest.raises(CommandError, match="^structure_refused$"),
    ):
        call_command(
            "repair_reaudit_journal_structure",
            actor=actor.username,
            file="unused",
            file_sha256="a" * 64,
            stdout=stdout,
            stderr=stderr,
        )
    lines = stderr.getvalue().splitlines()
    assert len(lines) == 1 and lines[0].startswith(diagnostics.PREFIX)
    payload = diagnostics.validate(json.loads(lines[0][len(diagnostics.PREFIX) :]))
    assert (payload["phase"], payload["model"], payload["exception"], payload["sqlstate"]) == (
        "repair",
        "registrar.Lesson",
        "ProgrammingError",
        "42703",
    )
    assert "PRIVATE_VALUE" not in stderr.getvalue() and actor.username not in stderr.getvalue()
    assert not stdout.getvalue()
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
        assert cursor.fetchone() == (1,)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "code,expected",
    [("structure_scope_changed", "structure_scope_changed"), ("structure_private_student_name", "structure_refused")],
)
def test_command_preserves_only_exact_known_codes(code, expected):
    stderr = io.StringIO()
    with (
        patch.object(command.spec, "private_bytes", side_effect=ValueError(code)),
        pytest.raises(CommandError) as caught,
    ):
        call_command(
            "repair_reaudit_journal_structure",
            actor="private-actor",
            file="unused",
            file_sha256="a" * 64,
            stderr=stderr,
        )
    assert str(caught.value) == expected
    payload = diagnostics.validate(json.loads(stderr.getvalue().strip()[len(diagnostics.PREFIX) :]))
    assert payload["code"] == expected and payload["phase"] == "manifest"
    assert "private_student_name" not in stderr.getvalue()
