"""Bounded core capture: explicit subset contract, pinned schema digest, undeclared omissions."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

from apps.legacy_import.services import reaudit_snapshot
from apps.legacy_import.services.reaudit_snapshot import queries
from apps.legacy_import.services.reaudit_snapshot.queries import (
    CORE_SCHEMAS,
    ORG,
    PERIOD,
    SCHEMAS,
    schema_digest,
    schemas_for,
    scoped_query,
)

CORE_LABELS = {
    "organizations.AcademicPeriod",
    "organizations.OrgUnit",
    "registrar.Subject",
    "auth.User",
    "accounts.UserProfile",
    "registrar.CourseOffering",
    "registrar.Enrollment",
    "registrar.Lesson",
    "registrar.AssessmentComponent",
    "registrar.LessonMark",
    "registrar.JournalCorrection",
    "registrar.LessonCorrection",
    "registrar.CorrectionReversal",
    "registrar.LanguageLevelCohort",
    "syllabus.Syllabus",
    "syllabus.SyllabusVersion",
    "syllabus.SyllabusShare",
    "workload.TeachingTask",
    "workload.TeachingTaskRow",
    "workload.TeacherAssignment",
    "workload.TeachingTaskRow_groups",
    "legacy_import.LegacyMigrationRun",
    "legacy_import.LegacyEntityMap",
    "legacy_import.LegacyEntityMapVersion",
    "audit.AuditLog",
}
CREATION_RESOURCES = [
    "registrar.legacy_cells_fill",
    "registrar.subgroup_journal_merge",
    "registrar.subgroup_parent_retire",
]


def script(name):
    path = Path(__file__).resolve().parents[3] / "scripts/ops" / name
    spec = importlib.util.spec_from_file_location("core_scope_" + name.replace(".", "_"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_core_schema_is_an_explicit_bounded_subset_of_the_full_contract():
    assert set(CORE_SCHEMAS) == CORE_LABELS
    assert not {"syllabus.SyllabusSection", "registrar.LegacyGradeFact", "exams.ExamAnswer"} & set(CORE_SCHEMAS)
    for label, spec in CORE_SCHEMAS.items():
        full = SCHEMAS[label]
        assert spec["fields"] == full["fields"], label
        assert spec["org_path"] == full["org_path"], label
        assert "exam_path" not in spec and "body_policy" not in spec, label
        expected_period = "offering__period_id" if label == "registrar.Enrollment" else full["period_path"]
        assert spec["period_path"] == expected_period, label
        expected_filters = dict(full["filters"])
        if label == "audit.AuditLog":
            expected_filters["resource_type__in"] = CREATION_RESOURCES
        assert spec["filters"] == expected_filters, label
        extra = set(spec) - set(full)
        if label.startswith("legacy_import.LegacyEntityMap"):
            assert extra == {"route_scope"} and spec["route_scope"] == queries.CORE_MAP_ROUTE_SCOPE
        else:
            assert not extra, label


def test_scope_digests_and_lookup_are_fixed():
    assert schema_digest() == schema_digest("full") != schema_digest("core")
    assert schema_digest("core") == hashlib.sha256(queries.CORE_SCHEMA_FILE.read_bytes()).hexdigest()
    assert schemas_for("core") is CORE_SCHEMAS and schemas_for("full") is SCHEMAS
    for call in (lambda: schemas_for("cells"), lambda: schema_digest("cells")):
        with pytest.raises(ValueError, match="fixed_capture_scope"):
            call()
    with pytest.raises(ValueError, match="fixed_schema"):
        scoped_query("registrar.Enrollment", SCHEMAS["registrar.Enrollment"], "core")
    with pytest.raises(ValueError, match="fixed_capture_scope"):
        scoped_query("registrar.Enrollment", CORE_SCHEMAS["registrar.Enrollment"], "cells")


def test_core_contracts_resolve_with_fixed_tenant_and_without_cell_map_routes(monkeypatch):
    from django.apps import apps

    manager = type(apps.get_model("audit", "AuditLog").objects)
    monkeypatch.setattr(manager, "_missing_fields_cache", {"default": frozenset()})
    for label, spec in CORE_SCHEMAS.items():
        query = scoped_query(label, spec, "core").order_by("pk").values(*spec["fields"])
        sql, params = query.query.sql_with_params()
        values = {str(value) for value in params}
        assert "SELECT" in sql and ORG in values, label
        if spec["period_path"]:
            assert PERIOD in values, label
        if label.startswith("legacy_import.LegacyEntityMap"):
            assert "registrar.courseoffering" in values
            assert not {"registrar.lessonmark", "registrar.lesson", "registrar.enrollment"} & values
        if label == "audit.AuditLog":
            assert set(CREATION_RESOURCES) <= values
    full_sql, full_params = (
        scoped_query("legacy_import.LegacyEntityMap", SCHEMAS["legacy_import.LegacyEntityMap"])
        .values("id")
        .query.sql_with_params()
    )
    assert "registrar.lessonmark" in {str(value) for value in full_params}


def test_capture_refuses_unknown_scope_before_any_database_work(tmp_path):
    with pytest.raises(ValueError, match="fixed_capture_scope_required"):
        reaudit_snapshot.capture("operator", tmp_path / "missing.pem", tmp_path, scope="cells")


@pytest.mark.django_db(transaction=True)
def test_core_capture_declares_scope_and_byte_totals_without_omitted_tables(tmp_path, monkeypatch):
    from django.contrib.auth import get_user_model
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from apps.organizations.models import Organization
    from apps.registrar.models import Program, Subject
    from core.rls import bypass_rls

    with bypass_rls():
        actor = get_user_model().objects.create_superuser("core-snapshot-operator", password="synthetic")
        org = Organization.objects.create(
            id=ORG, name="Synthetic core", slug="synthetic-core", owner=actor, status="active", is_active=True
        )
        actor.profile.organization = org
        actor.profile.save(update_fields=["organization"])
        Program.objects.create(organization=org, code="SYNTH-OMIT", name="Not a core table")
        subject = Subject.objects.create(organization=org, code="SYNTH-CORE", name="Core subject")
    tmp_path.chmod(0o700)
    public = tmp_path.parent / "synthetic-core-public.pem"
    public.write_text("synthetic")
    monkeypatch.setattr(reaudit_snapshot, "encrypt_export", lambda payload, *args, **kwargs: {"synthetic": payload})
    with CaptureQueriesContext(connection) as queries_made:
        result = reaudit_snapshot.capture(actor.username, public, tmp_path, scope="core")
    assert result["tables"] == len(CORE_SCHEMAS)
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["scope"] == "core" and manifest["complete"] and manifest["read_only"]
    assert manifest["schema_sha256"] == schema_digest("core")
    assert set(manifest["tables"]) == CORE_LABELS
    assert "registrar.Program" not in manifest["tables"]
    assert all(type(table["bytes"]) is int and table["bytes"] >= 0 for table in manifest["tables"].values())
    assert manifest["total_bytes"] == sum(table["bytes"] for table in manifest["tables"].values()) > 0
    payload = json.loads((tmp_path / "registrar.subject-0000.enc.json").read_text())["synthetic"]
    assert payload["scope"] == "core" and [row["id"] for row in payload["rows"]] == [str(subject.pk)]
    assert manifest["tables"]["registrar.Subject"]["bytes"] == len(reaudit_snapshot.encode(payload))
    assert not (tmp_path / "registrar.program-0000.enc.json").exists()
    assert not [q for q in queries_made if q["sql"].lstrip().upper().startswith(("INSERT ", "UPDATE ", "DELETE "))]


def core_manifest():
    return {
        "format": "qku-reaudit-state/1",
        "scope": "core",
        "schema_sha256": schema_digest("core"),
        "tables": {label: {"fields": spec["fields"], "rows": 0, "bytes": 0} for label, spec in CORE_SCHEMAS.items()},
    }


def test_decoder_pins_core_schema_and_refuses_silent_table_omission():
    module = script("decode_reaudit_snapshot.py")
    assert module.verify_scope(core_manifest()) == "core"
    assert module.verify_scope({"schema_sha256": schema_digest(), "tables": {}}) == "full"
    with pytest.raises(ValueError, match="core_schema_changed"):
        module.verify_scope({**core_manifest(), "schema_sha256": schema_digest("full")})
    missing = core_manifest()
    del missing["tables"]["registrar.LessonMark"]
    with pytest.raises(ValueError, match="core_table_set_changed"):
        module.verify_scope(missing)
    extra = core_manifest()
    extra["tables"]["registrar.Program"] = {"fields": [], "rows": 0, "bytes": 0}
    with pytest.raises(ValueError, match="core_table_set_changed"):
        module.verify_scope(extra)
    with pytest.raises(ValueError, match="capture_scope_unknown"):
        module.verify_scope({**core_manifest(), "scope": "cells"})
    # A core manifest carries no syllabus body projection; the body contract stays compatible.
    module.verify_body_projection(copy.deepcopy(core_manifest()))


def test_transport_threads_capture_scope_and_refuses_mismatch(tmp_path):
    module = script("reaudit_snapshot.py")
    base = {"scope": "reaudit", "actor": "operator", "deployed_head": "a" * 40}
    assert module.inputs(base) == ("operator", "a" * 40, "full")
    assert module.inputs({**base, "capture_scope": "core"})[2] == "core"
    with pytest.raises(ValueError, match="capture_scope_required"):
        module.inputs({**base, "capture_scope": "cells"})
    manifest = {"format": "qku-reaudit-state/1", "complete": True, "scope": "full", "shards": [], "tables": {}}
    manifest["total_rows"] = 0
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    assert module.verify_artifact(tmp_path, "full") == manifest
    with pytest.raises(ValueError, match="capture_scope_changed"):
        module.verify_artifact(tmp_path, "core")


def test_builder_exposes_owner_present_policy_for_phased_restoration():
    from apps.registrar.reaudit_cells.builder import Builder

    offering = {
        "id": "o1",
        "organization_id": ORG,
        "period_id": PERIOD,
        "is_active": True,
        "subject_id": "s",
        "instructor_id": 1,
        "group_id": "g",
        "lesson_hours": 30,
    }
    current = {
        "tables": {
            "registrar.CourseOffering": [offering],
            "legacy_import.LegacyEntityMap": [],
            "legacy_import.LegacyEntityMapVersion": [],
            "registrar.Lesson": [],
            "registrar.Enrollment": [],
            "registrar.LessonMark": [],
            "registrar.AssessmentComponent": [],
            "audit.AuditLog": [],
        }
    }
    source = {"journals": [], "points": []}
    kwargs = dict(
        source=source,
        current=current,
        organization_id=ORG,
        period_id=PERIOD,
        source_system="fixture",
        source_sha256="5" * 64,
        current_sha256="6" * 64,
    )
    assert Builder(**kwargs).build()["owner_present_policy"] == "applicable_blank_without_grade_hold"
    assert Builder(owner_present_policy="disabled", **kwargs).build()["owner_present_policy"] == "disabled"
