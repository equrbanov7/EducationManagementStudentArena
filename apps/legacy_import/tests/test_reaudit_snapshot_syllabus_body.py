"""Real PostgreSQL body projection; metadata/history, pending work and donor closure remain."""

import datetime as dt
import hashlib
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

from django.apps import apps
from django.db import connection
from django.test import TestCase
from django.utils import timezone

from apps.legacy_import.services.reaudit_snapshot import queries
from apps.legacy_import.services.reaudit_snapshot.syllabus_body import POLICY
from apps.registrar.tests.test_lab_groups_2026_11_06 import _LabWorld
from core.rls import bypass_rls


class SyllabusBodySnapshotTest(_LabWorld, TestCase):
    def setUp(self):
        self.scope = bypass_rls()
        self.scope.__enter__()
        self.addCleanup(self.scope.__exit__, None, None, None)
        self.assertEqual(connection.vendor, "postgresql")

    def make(self, label, **fields):
        return apps.get_model(label).objects.create(organization=self.org, **fields)

    def dossier(self, *, subject=None, **fields):
        return self.make("syllabus.Syllabus", subject=subject or self.offering.subject, **fields)

    def version(self, dossier, status="draft", **fields):
        if status == "approved":
            fields.update(locked_at=timezone.now(), approval_source="migration")
        if status in {"revision", "rejected"}:
            fields["decision_reason"] = "Synthetic pending review"
        version = self.make("syllabus.SyllabusVersion", syllabus=dossier, status=status, **fields)
        self.make("syllabus.SyllabusSection", version=version, section_id="desc", data={"body": "Əsl Unicode 😀"})
        self.make("syllabus.SyllabusReview", version=version, decision="submit")
        return version

    def exported(self, label):
        with patch.object(queries, "ORG", str(self.org.pk)), patch.object(queries, "PERIOD", str(self.period.pk)):
            return list(queries.scoped_query(label, queries.SCHEMAS[label]).values(*queries.SCHEMAS[label]["fields"]))

    def body_versions(self):
        sections = self.exported("syllabus.SyllabusSection")
        reviews = self.exported("syllabus.SyllabusReview")
        self.assertLessEqual({r["version_id"] for r in sections}, {r["version_id"] for r in reviews})
        self.assertTrue(all(r["data"] == {"body": "Əsl Unicode 😀"} for r in sections))
        return {r["version_id"] for r in sections}

    def previous_period(self):
        return self.make(
            "organizations.AcademicPeriod",
            name="Previous",
            period_type="semester",
            academic_year="2025/2026",
            start_date=dt.date(2025, 9, 15),
            end_date=dt.date(2026, 1, 15),
        )

    def test_unrelated_old_bodies_omitted_but_all_metadata_and_versions_retained(self):
        old_subject = self.make("registrar.Subject", code="OLD", name="Unrelated")
        old = self.dossier(subject=old_subject, period=self.previous_period())
        old_version = self.version(old)
        live = self.dossier(offering=self.offering, period=self.period, author=self.teacher)
        live_version = self.version(live)
        self.assertEqual(self.body_versions(), {live_version.pk})
        self.assertEqual({r["id"] for r in self.exported("syllabus.Syllabus")}, {old.pk, live.pk})
        self.assertEqual(
            {r["id"] for r in self.exported("syllabus.SyllabusVersion")}, {old_version.pk, live_version.pk}
        )

    def test_inactive_current_offering_and_period_fallback_are_roots(self):
        self.offering.is_active = False
        self.offering.save(update_fields=["is_active"])
        bound = self.dossier(offering=self.offering, author=self.teacher)
        fallback = self.dossier(period=self.period, author=self.owner)
        expected = {self.version(bound).pk, self.version(fallback).pk}
        self.assertEqual(self.body_versions(), expected)

    def test_all_nonarchived_states_and_archived_pointers_preserved(self):
        expected = set()
        for major, status in enumerate(("draft", "submitted", "review", "revision", "approved", "rejected"), 1):
            subject = self.make("registrar.Subject", code=f"STATE{major}", name=status)
            dossier = self.dossier(subject=subject, period=self.period)
            expected.add(self.version(dossier, status, major=major).pk)
        dossier = self.dossier(offering=self.offering)
        archived_pointer = self.version(dossier, "archived", major=7)
        self.version(dossier, "archived", major=8)
        dossier.current_version = archived_pointer
        dossier.save(update_fields=["current_version"])
        self.assertEqual(self.body_versions(), expected | {archived_pointer.pk})

    def test_old_author_fallback_and_recursive_source_version_donors_preserved(self):
        old = self.previous_period()
        unrelated_subject = self.make("registrar.Subject", code="LINEAGE", name="Lineage")
        ancestor = self.dossier(subject=unrelated_subject, period=old)
        oldest = self.version(ancestor, "archived")
        parent = self.dossier(period=old, author=self.owner)
        intermediate = self.version(parent, "archived", source_version=oldest)
        current = self.dossier(offering=self.offering, period=self.period, author=self.teacher)
        selected = self.version(current, source_version=intermediate)
        base = self.dossier(author=self.teacher)
        fallback = self.version(base)
        self.assertEqual(self.body_versions(), {selected.pk, intermediate.pk, oldest.pk, fallback.pk})

    def test_reused_parent_and_share_candidates_retained(self):
        parent = self.dossier(author=self.owner)
        donor = self.version(parent, "archived")
        parent.approved_version = donor
        parent.save(update_fields=["approved_version"])
        current = self.dossier(offering=self.offering, period=self.period, reused_from=parent)
        child = self.version(current)
        self.make("syllabus.SyllabusShare", syllabus=parent, offering=self.offering)
        self.assertEqual(self.body_versions(), {donor.pk, child.pk})

    def test_cyclic_source_metadata_terminates_without_dropping_referenced_archive(self):
        dossier = self.dossier(offering=self.offering)
        first = self.version(dossier)
        second = self.version(dossier, "archived", major=2, source_version=first)
        apps.get_model("syllabus.SyllabusVersion").objects.filter(pk=first.pk).update(source_version=second)
        self.assertEqual(self.body_versions(), {first.pk, second.pk})

    def test_foreign_bodies_cannot_enter_projection(self):
        other = apps.get_model("organizations.Organization").objects.create(
            name="Foreign", slug="foreign-body", owner=self.owner
        )
        subject = apps.get_model("registrar.Subject").objects.create(organization=other, code="X", name="Foreign")
        dossier = apps.get_model("syllabus.Syllabus").objects.create(organization=other, subject=subject)
        version = apps.get_model("syllabus.SyllabusVersion").objects.create(organization=other, syllabus=dossier)
        apps.get_model("syllabus.SyllabusSection").objects.create(
            organization=other, version=version, section_id="desc"
        )
        self.assertEqual(self.body_versions(), set())


def test_body_projection_is_in_schema_fingerprint_and_only_affects_section_bodies():
    raw = queries.SCHEMA_FILE.read_bytes()
    schema = json.loads(raw)
    projected = {label for label, spec in schema.items() if spec.get("body_policy")}
    assert projected == {"syllabus.SyllabusSection"}
    assert all(schema[label]["body_policy"] == POLICY for label in projected)
    assert hashlib.sha256(raw).hexdigest() == queries.schema_digest()
    for label in projected:
        schema[label].pop("body_policy")
    assert hashlib.sha256(json.dumps(schema).encode()).hexdigest() != queries.schema_digest()


def test_decoder_rejects_missing_or_mislabelled_projected_body_policy():
    import pytest

    path = Path(__file__).resolve().parents[3] / "scripts/ops/decode_reaudit_snapshot.py"
    spec = importlib.util.spec_from_file_location("body_projection_decoder", path)
    decoder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(decoder)
    tables = {label: {"body_policy": POLICY} for label in ("syllabus.SyllabusSection",)}
    manifest = {"schema_sha256": queries.schema_digest(), "tables": tables}
    decoder.verify_body_projection(manifest)
    with pytest.raises(ValueError, match="projection_required"):
        decoder.verify_body_projection({**manifest, "tables": {}})
    with pytest.raises(ValueError, match="projection_changed"):
        decoder.verify_body_projection({**manifest, "schema_sha256": "0" * 64})
    with pytest.raises(ValueError, match="projection_changed"):
        decoder.verify_body_projection({**manifest, "tables": {"syllabus.SyllabusSection": {"body_policy": "other"}}})
    # Old captures with the old schema remain explicitly universal-body artifacts.
    decoder.verify_body_projection({"schema_sha256": "0" * 64, "tables": {}})
