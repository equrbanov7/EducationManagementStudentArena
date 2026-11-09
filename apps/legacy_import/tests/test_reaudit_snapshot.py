"""Fixed tenant/period contracts and encrypted export transport boundaries."""

import importlib.util
import json
from pathlib import Path

import pytest

from apps.legacy_import.services import reaudit_snapshot
from apps.legacy_import.services.reaudit_snapshot.queries import ORG, PERIOD, SCHEMAS, scoped_query


def transport():
    path = Path(__file__).resolve().parents[3] / "scripts/ops/reaudit_snapshot.py"
    spec = importlib.util.spec_from_file_location("snapshot_transport_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_all_contracts_resolve_without_expanding_tenant(monkeypatch):
    from django.apps import apps

    manager = type(apps.get_model("audit", "AuditLog").objects)
    monkeypatch.setattr(manager, "_missing_fields_cache", {"default": frozenset()})
    for label, spec in SCHEMAS.items():
        query = scoped_query(label, spec).order_by("pk").values(*spec["fields"])
        sql, params = query.query.sql_with_params()
        assert "SELECT" in sql
        assert ORG in {str(value) for value in params}
        if spec["period_path"]:
            assert PERIOD in {str(value) for value in params}


def test_credentials_and_question_content_are_excluded():
    assert "password" not in SCHEMAS["auth.User"]["fields"]
    assert "access_code" not in SCHEMAS["exams.Exam"]["fields"]
    assert "text" not in SCHEMAS["exams.ExamQuestion"]["fields"]
    assert "ip_address" not in SCHEMAS["audit.AuditLog"]["fields"]


def test_schema_cannot_be_substituted():
    with pytest.raises(ValueError, match="fixed_schema"):
        scoped_query("auth.User", {"fields": ["password"]})


def test_export_files_cannot_overwrite_existing_data(tmp_path):
    path = tmp_path / "cipher.json"
    reaudit_snapshot.save_new(path, {"encrypted": True})
    assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        reaudit_snapshot.save_new(path, {"encrypted": False})
    assert json.loads(path.read_text()) == {"encrypted": True}


@pytest.mark.parametrize(
    "bad", [{}, {"scope": "logs"}, {"scope": "reaudit", "actor": "x;id", "deployed_head": "a" * 40}]
)
def test_transport_rejects_invalid_inputs(bad):
    with pytest.raises(ValueError):
        transport().inputs(bad)


def test_transport_rejects_partial_capture(tmp_path):
    (tmp_path / "manifest.json").write_text(json.dumps({"format": "qku-reaudit-state/1", "complete": False}))
    with pytest.raises(ValueError, match="complete_snapshot"):
        transport().verify_artifact(tmp_path)


def test_transport_verifies_zero_row_tables_and_no_extra_file(tmp_path):
    manifest = {
        "format": "qku-reaudit-state/1",
        "complete": True,
        "shards": [],
        "tables": {"auth.User": {"rows": 0}},
        "total_rows": 0,
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    assert transport().verify_artifact(tmp_path) == manifest
    (tmp_path / "plaintext.json").write_text("[]")
    with pytest.raises(ValueError, match="unexpected_artifact"):
        transport().verify_artifact(tmp_path)


@pytest.mark.django_db(transaction=True)
def test_capture_database_readonly_even_if_internal_query_attempts_write(tmp_path, monkeypatch):
    from django.db import DatabaseError, connection

    assert connection.vendor == "postgresql"
    tmp_path.chmod(0o700)
    public = tmp_path.parent / "public.pem"
    public.write_text("test")
    monkeypatch.setattr(reaudit_snapshot, "encrypt_export", lambda *args, **kwargs: {})

    def illegal_write(username):
        with connection.cursor() as cursor:
            cursor.execute("CREATE TABLE reaudit_readonly_violation (id integer)")

    monkeypatch.setattr(reaudit_snapshot, "validate_actor", illegal_write)
    with pytest.raises(DatabaseError, match="read-only"):
        reaudit_snapshot.capture("operator", public, tmp_path)
    assert not (tmp_path / "manifest.json").exists()
    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass('reaudit_readonly_violation')")
        assert cursor.fetchone()[0] is None


@pytest.mark.django_db(transaction=True)
def test_capture_paginates_without_dropping_or_repeating_rows(tmp_path, monkeypatch):
    from django.contrib.auth import get_user_model

    users = get_user_model()
    created = [users.objects.create(username=f"snapshot-synthetic-{i}") for i in range(3)]
    tmp_path.chmod(0o700)
    public = tmp_path.parent / "synthetic-public.pem"
    public.write_text("synthetic")
    monkeypatch.setattr(reaudit_snapshot, "encrypt_export", lambda payload, *args, **kwargs: {"synthetic": payload})
    monkeypatch.setattr(reaudit_snapshot, "validate_actor", lambda _: created[0].pk)
    monkeypatch.setattr(reaudit_snapshot, "SCHEMAS", {"auth.User": {"fields": ["id", "username"]}})
    monkeypatch.setattr(
        reaudit_snapshot, "scoped_query", lambda *_: users.objects.filter(pk__in=[u.pk for u in created])
    )
    monkeypatch.setattr(reaudit_snapshot, "CHUNK_ROWS", 2)
    result = reaudit_snapshot.capture("operator", public, tmp_path)
    assert result["rows"] == 3 and result["shards"] == 2
    rows = []
    for path in sorted(tmp_path.glob("*.enc.json")):
        rows.extend(json.loads(path.read_text())["synthetic"]["rows"])
    assert [row["id"] for row in rows] == sorted(user.pk for user in created)


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("pooled", [False, True])
def test_complete_capture_executes_all_schemas_with_fixed_tenant(tmp_path, monkeypatch, settings, pooled):
    from django.contrib.auth import get_user_model
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from apps.organizations.models import Organization
    from apps.registrar.models import Program
    from core.rls import bypass_rls

    settings.RLS_TRANSACTION_SCOPED = pooled
    with bypass_rls():
        actor = get_user_model().objects.create_superuser("full-snapshot-operator", password="synthetic")
        org = Organization.objects.create(
            id=ORG, name="Synthetic capture", slug="synthetic-capture", owner=actor, status="active", is_active=True
        )
        actor.profile.organization = org
        actor.profile.save(update_fields=["organization"])
        foreign = Organization.objects.create(
            name="Synthetic foreign", slug="synthetic-foreign", owner=actor, status="active", is_active=True
        )
        kept = Program.objects.create(organization=org, code="SYNTH-KEEP", name="Synthetic")
        Program.objects.create(organization=foreign, code="SYNTH-EXCLUDE", name="Synthetic foreign")
    tmp_path.chmod(0o700)
    public = tmp_path.parent / "synthetic-full-public.pem"
    public.write_text("synthetic")
    monkeypatch.setattr(reaudit_snapshot, "encrypt_export", lambda payload, *args, **kwargs: {"synthetic": payload})
    with CaptureQueriesContext(connection) as queries:
        result = reaudit_snapshot.capture(actor.username, public, tmp_path)
    assert result["tables"] == len(SCHEMAS)
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["complete"] and manifest["read_only"]
    rows = json.loads((tmp_path / "registrar.program-0000.enc.json").read_text())["synthetic"]["rows"]
    assert [row["id"] for row in rows] == [str(kept.pk)]
    assert not [q for q in queries if q["sql"].lstrip().upper().startswith(("INSERT ", "UPDATE ", "DELETE "))]
