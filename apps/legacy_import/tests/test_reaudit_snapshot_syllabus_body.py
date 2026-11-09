"""Native PostgreSQL metadata projection excludes body bytes before transfer."""

import copy
import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

import pytest

from apps.legacy_import.services import reaudit_snapshot as export
from apps.legacy_import.services.reaudit_snapshot import queries
from apps.registrar.tests.test_lab_groups_2026_11_06 import _LabWorld
from core.rls import bypass_rls

LABEL = "syllabus.SyllabusSection"
POLICY = "metadata-only-bodies-deferred-to-native-connected-batches/1"


class SyllabusBodySnapshotTest(_LabWorld, TestCase):
    def setUp(self):
        self.scope = bypass_rls()
        self.scope.__enter__()
        self.addCleanup(self.scope.__exit__, None, None, None)
        self.assertEqual(connection.vendor, "postgresql")

    def make(self, label, **fields):
        return apps.get_model(label).objects.create(organization=self.org, **fields)

    def dossier(self, **fields):
        return self.make("syllabus.Syllabus", subject=self.offering.subject, **fields)

    def version(self, dossier, status="draft", **fields):
        version = self.make("syllabus.SyllabusVersion", syllabus=dossier, status=status, **fields)
        self.make("syllabus.SyllabusSection", version=version, section_id="desc", data={"body": "Əsl Unicode 😀"})
        self.make("syllabus.SyllabusReview", version=version, decision="submit")
        return version

    def exported(self, label):
        with patch.object(queries, "ORG", str(self.org.pk)), patch.object(queries, "PERIOD", str(self.period.pk)):
            return list(queries.scoped_query(label, queries.SCHEMAS[label]).values(*queries.SCHEMAS[label]["fields"]))

    def test_every_historical_current_inactive_and_archived_metadata_row_is_retained(self):
        previous = self.make(
            "organizations.AcademicPeriod",
            name="Previous",
            period_type="semester",
            academic_year="2025/2026",
            start_date=dt.date(2025, 9, 15),
            end_date=dt.date(2026, 1, 15),
        )
        old = self.dossier(period=previous)
        old_version = self.version(old, "archived")
        live = self.dossier(offering=self.offering, period=self.period, author=self.teacher)
        live_version = self.version(live)
        inactive = self.dossier(author=self.owner, is_active=False)
        inactive_version = self.version(inactive, "archived")
        wanted = {old_version.pk, live_version.pk, inactive_version.pk}
        sections = self.exported(LABEL)
        self.assertEqual({r["version_id"] for r in sections}, wanted)
        self.assertEqual({r["version_id"] for r in self.exported("syllabus.SyllabusReview")}, wanted)
        self.assertEqual({r["id"] for r in self.exported("syllabus.SyllabusVersion")}, wanted)
        self.assertEqual({r["id"] for r in self.exported("syllabus.Syllabus")}, {old.pk, live.pk, inactive.pk})
        self.assertTrue(all("data" not in row for row in sections))
        self.assertEqual(
            list(apps.get_model(LABEL).objects.order_by("pk").values_list("data", flat=True)),
            [{"body": "Əsl Unicode 😀"}] * 3,
        )

    def test_foreign_metadata_is_excluded_without_mutating_body(self):
        other = apps.get_model("organizations.Organization").objects.create(
            name="Foreign", slug="foreign-body", owner=self.owner
        )
        subject = apps.get_model("registrar.Subject").objects.create(organization=other, code="X", name="Foreign")
        dossier = apps.get_model("syllabus.Syllabus").objects.create(organization=other, subject=subject)
        version = apps.get_model("syllabus.SyllabusVersion").objects.create(organization=other, syllabus=dossier)
        section = apps.get_model(LABEL).objects.create(
            organization=other, version=version, section_id="desc", data={"body": "foreign private body"}
        )
        self.assertEqual(self.exported(LABEL), [])
        section.refresh_from_db()
        self.assertEqual(section.data, {"body": "foreign private body"})

    def test_actual_sql_projection_selects_every_metadata_column_but_never_data(self):
        dossier = self.dossier(offering=self.offering)
        self.version(dossier)
        with CaptureQueriesContext(connection) as captured:
            values = self.exported(LABEL)
        selects = [q["sql"] for q in captured if 'FROM "syllabus_syllabussection"' in q["sql"]]
        self.assertEqual(len(selects), 1)
        self.assertNotIn('"data"', selects[0])
        all_columns = {field.attname for field in apps.get_model(LABEL)._meta.concrete_fields}
        self.assertEqual(set(values[0]), all_columns - {"data"})


def decoder():
    path = Path(__file__).resolve().parents[3] / "scripts/ops/decode_reaudit_snapshot.py"
    spec = importlib.util.spec_from_file_location("metadata_body_decoder", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def manifest():
    spec = queries.SCHEMAS[LABEL]
    return {
        "schema_sha256": queries.schema_digest(),
        "tables": {
            LABEL: {
                key: copy.deepcopy(spec[key])
                for key in ("fields", "body_policy", "body_complete", "excluded_body_fields")
            }
        },
    }


def test_projection_fingerprint_declares_only_the_missing_body_field():
    raw = queries.SCHEMA_FILE.read_bytes()
    schema = json.loads(raw)
    assert queries.SYLLABUS_BODY_POLICY == POLICY
    assert {label for label, spec in schema.items() if spec.get("body_policy")} == {LABEL}
    section = schema[LABEL]
    assert section["body_policy"] == POLICY
    assert section["body_complete"] is False
    assert section["excluded_body_fields"] == ["data"]
    assert "data" not in section["fields"]
    assert section["period_path"] == "" and section["filters"] == {}
    assert "body_policy" not in schema["syllabus.SyllabusReview"]
    assert hashlib.sha256(raw).hexdigest() == queries.schema_digest()
    del section["body_complete"]
    assert hashlib.sha256(json.dumps(schema).encode()).hexdigest() != queries.schema_digest()


@pytest.mark.parametrize(
    "key,value",
    [
        ("body_policy", "other"),
        ("body_complete", True),
        ("body_complete", 0),
        ("excluded_body_fields", []),
        ("excluded_body_fields", ["data", "revision"]),
        ("fields", ["id"]),
    ],
)
def test_decoder_refuses_changed_or_misleading_metadata_contract(key, value):
    candidate = manifest()
    candidate["tables"][LABEL][key] = value
    with pytest.raises(ValueError, match="projection_changed"):
        decoder().verify_body_projection(candidate)


@pytest.mark.parametrize("key", ["body_policy", "body_complete", "excluded_body_fields", "fields"])
def test_decoder_refuses_missing_projection_contract(key):
    candidate = manifest()
    del candidate["tables"][LABEL][key]
    with pytest.raises(ValueError, match="projection_(required|changed)"):
        decoder().verify_body_projection(candidate)


def test_decoder_accepts_explicit_metadata_only_and_keeps_historical_schema_compatibility():
    module = decoder()
    candidate = manifest()
    module.verify_body_projection(candidate)
    with pytest.raises(ValueError, match="projection_changed"):
        module.verify_body_projection({**candidate, "schema_sha256": "0" * 64})
    module.verify_body_projection({"schema_sha256": "0" * 64, "tables": {}})


@pytest.mark.django_db(transaction=True)
def test_100k_body_captures_under_4k_cap_without_transferring_or_mutating_body(tmp_path, monkeypatch):
    assert connection.vendor == "postgresql"
    body = {"synthetic_private_body": "x" * (100 * 1024)}
    with bypass_rls():
        actor = get_user_model().objects.create_user("synthetic-metadata-operator", is_superuser=True)
        organization = apps.get_model("organizations.Organization").objects.create(
            id=export.ORG,
            name="Synthetic metadata",
            slug="synthetic-metadata",
            owner=actor,
            is_active=True,
            status="active",
        )
        subject = apps.get_model("registrar.Subject").objects.create(
            organization=organization, code="META", name="Synthetic metadata subject"
        )
        dossier = apps.get_model("syllabus.Syllabus").objects.create(organization=organization, subject=subject)
        version = apps.get_model("syllabus.SyllabusVersion").objects.create(organization=organization, syllabus=dossier)
        section = apps.get_model(LABEL).objects.create(
            organization=organization, version=version, section_id="desc", data=body
        )
    key = tmp_path / "synthetic-public.pem"
    key.write_text("synthetic encryption recipient")
    output = tmp_path / "capture"
    output.mkdir(mode=0o700)
    monkeypatch.setattr(export, "SCHEMAS", {LABEL: queries.SCHEMAS[LABEL]})
    monkeypatch.setattr(export, "MAX_TOTAL_BYTES", 4096)
    monkeypatch.setattr(export, "MAX_CHUNK_BYTES", 4096)
    monkeypatch.setattr(export, "encrypt_export", lambda payload, *args, **kwargs: {"synthetic": payload})
    with CaptureQueriesContext(connection) as captured:
        result = export.capture(actor.username, key, output)
    assert result["rows"] == result["shards"] == 1
    recorded = json.loads((output / "manifest.json").read_bytes())
    assert recorded["complete"] is True and recorded["read_only"] is True
    table = recorded["tables"][LABEL]
    assert table["body_complete"] is False
    assert table["body_policy"] == POLICY and table["excluded_body_fields"] == ["data"]
    payload = json.loads(next(output.glob("*.enc.json")).read_bytes())["synthetic"]
    assert len(export.encode(payload)) <= 4096
    assert payload["actor_id"] == actor.pk
    assert payload["rows"][0]["id"] == str(section.pk)
    assert "data" not in payload["rows"][0]
    assert "synthetic_private_body" not in json.dumps(payload)
    section_selects = [q["sql"] for q in captured if 'FROM "syllabus_syllabussection"' in q["sql"]]
    assert section_selects and all('"data"' not in sql for sql in section_selects)
    assert not any(q["sql"].lstrip().upper().startswith(("INSERT ", "UPDATE ", "DELETE ")) for q in captured)
    with bypass_rls():
        assert apps.get_model(LABEL).objects.get(pk=section.pk).data == body
