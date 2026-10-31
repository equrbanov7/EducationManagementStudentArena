"""Exact boş alias: historical data, gizli M2M, baseline və undo qorunması."""

from copy import deepcopy
from io import StringIO
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.organizations import empty_group_alias as repair
from apps.organizations.models import Organization, OrgUnit


def full_legacy_settings(legacy):
    # Actual source/target metadata from the read-only clone, not the export projection.
    return {
        "legacy": {
            "id": legacy,
            "table": "groups",
            "curricula_id": 117,
            "department_id": 11,
            "kollec_or_uni": "University",
            "source_system": "myedu_mariadb",
            "speciality_id": 21,
        },
        "sector": "az",
        "degree_level": "bachelor",
        "admission_year": 2022,
        "education_form": "full_time",
        "language_sector": "az",
    }


class EmptyGroupAliasTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser("empty_admin", "a@x.test", "pw")
        self.org = Organization.objects.create(
            pk=repair.ORG, name="QKU", slug="qku", owner=self.admin, org_type="university"
        )
        parent = OrgUnit.objects.create(
            pk=repair.PARENT, organization=self.org, name="Specialty", slug="specialty", unit_type="specialty"
        )
        self.source = OrgUnit.objects.create(
            pk=repair.SOURCE,
            organization=self.org,
            parent=parent,
            name="132 F",
            slug="source",
            unit_type="group",
            settings=full_legacy_settings(388),
        )
        self.target = OrgUnit.objects.create(
            pk=repair.TARGET,
            organization=self.org,
            parent=parent,
            name="132F",
            slug="target",
            unit_type="group",
            settings=full_legacy_settings(367),
        )
        run = apps.get_model("legacy_import", "LegacyMigrationRun").objects.create(
            organization=self.org,
            source_system="myedu_mariadb",
            snapshot_sha256="a" * 64,
            snapshot_size_bytes=1,
            source_row_count=2,
            schema_version="legacy-v1",
            transform_version="v1",
            mode="rehearsal",
        )
        type(run).objects.filter(pk=run.pk).update(status="running", started_at=timezone.now())
        self.legacy_run = run
        for unit, legacy in ((self.source, "388"), (self.target, "367")):
            apps.get_model("legacy_import", "LegacyEntityMap").objects.create(
                organization=self.org,
                source_system="myedu_mariadb",
                entity_type="group_unit",
                legacy_pk=legacy,
                source_row_hash="b" * 64,
                transform_version="v1",
                target_model_label="organizations.orgunit",
                target_pk=str(unit.pk),
                created_run=run,
                state="migrated",
            )

    def run_repair(self, **kwargs):
        return repair.run(user=self.admin, organization=self.org, **kwargs)

    def test_dry_run_full_snapshot_has_no_mutations(self):
        result = self.run_repair()
        self.assertFalse(result["blocked"])
        self.assertEqual(result["snapshot"]["source"]["id"], repair.SOURCE)
        self.source.refresh_from_db()
        self.assertTrue(self.source.is_active)

    def test_command_summary_contains_only_safe_tokens(self):
        output = StringIO()
        call_command("repair_empty_132f_alias", actor=self.admin.username, summary=True, stdout=output)
        self.assertRegex(
            output.getvalue(),
            r"^empty132f: mode=dry_run baseline=[0-9a-f]{64} blocked=0 applied=0 receipt=none\n$",
        )
        self.assertNotIn("snapshot", output.getvalue())
        self.assertNotIn(repair.SOURCE, output.getvalue())

    def test_child_reference_blocks_and_is_reported(self):
        child = OrgUnit.objects.create(
            organization=self.org, parent=self.source, name="subgroup", slug="subgroup", unit_type="group"
        )
        result = self.run_repair()
        self.assertEqual(result["snapshot"]["references"]["organizations.OrgUnit.parent"], [str(child.pk)])
        with patch.object(repair.connection, "vendor", "postgresql"):
            with self.assertRaisesMessage(repair.RepairError, "source_has_references"):
                self.run_repair(apply=True, expected_baseline=result["baseline"])
        self.source.refresh_from_db()
        self.assertTrue(self.source.is_active)

    def test_automatic_m2m_through_reference_blocks(self):
        task = apps.get_model("workload", "TeachingTask").objects.create(
            organization=self.org, chair_id=repair.PARENT, academic_year="2026/2027"
        )
        row = apps.get_model("workload", "TeachingTaskRow").objects.create(organization=self.org, task=task)
        row.groups.add(self.source)
        result = self.run_repair()
        self.assertTrue(result["blocked"])
        self.assertIn("workload.TeachingTaskRow_groups.orgunit", result["snapshot"]["references"])
        with self.assertRaisesMessage(repair.RepairError, "source_has_references"):
            self.run_repair(apply=True, expected_baseline=result["baseline"])

    def test_apply_undo_preserve_target_and_all_source_fields(self):
        before = self.run_repair()
        with patch.object(repair.connection, "vendor", "postgresql"):
            applied = self.run_repair(apply=True, expected_baseline=before["baseline"])
            self.assertEqual(applied["snapshot"]["target"], before["snapshot"]["target"])
            self.assertFalse(applied["snapshot"]["source"]["is_active"])
            undone = self.run_repair(apply=True, expected_baseline=applied["baseline"], undo=applied["batch"])
        self.assertEqual(undone["snapshot"], before["snapshot"])

    def test_apply_preserves_unrelated_nested_metadata_and_only_changes_two_fields(self):
        source_settings = full_legacy_settings(388)
        source_settings["unrelated"] = {"retain": [1, {"nested": "source"}], "enabled": False}
        source_settings["legacy"]["extra_provenance"] = {"preserve": True}
        target_settings = full_legacy_settings(367)
        target_settings["unrelated"] = {"retain": ["target"], "note": None}
        OrgUnit.objects.filter(pk=self.source.pk).update(settings=source_settings)
        OrgUnit.objects.filter(pk=self.target.pk).update(settings=target_settings)
        before = self.run_repair()
        applied = self.run_repair(apply=True, expected_baseline=before["baseline"])
        expected_source = deepcopy(before["snapshot"]["source"])
        expected_source["is_active"] = False
        expected_source["settings"]["canonical_group"] = repair.TARGET
        self.assertEqual(applied["snapshot"]["source"], expected_source)
        self.assertEqual(applied["snapshot"]["target"], before["snapshot"]["target"])
        undone = self.run_repair(apply=True, expected_baseline=applied["baseline"], undo=applied["batch"])
        self.assertEqual(undone["snapshot"], before["snapshot"])

    def test_projected_settings_and_wrong_source_provenance_are_rejected(self):
        OrgUnit.objects.filter(pk=self.source.pk).update(settings=repair.SETTINGS)
        with self.assertRaisesMessage(repair.RepairError, "source_settings_changed"):
            self.run_repair()
        wrong = full_legacy_settings(388)
        wrong["legacy"]["curricula_id"] = 999
        OrgUnit.objects.filter(pk=self.source.pk).update(settings=wrong)
        with self.assertRaisesMessage(repair.RepairError, "source_settings_changed"):
            self.run_repair()

    def test_stale_baseline_and_invalid_metadata_fail_closed(self):
        result = self.run_repair()
        OrgUnit.objects.filter(pk=self.source.pk).update(code="changed")
        with self.assertRaisesMessage(repair.RepairError, "identity_changed"):
            self.run_repair()
        OrgUnit.objects.filter(pk=self.source.pk).update(code="", head=self.admin)
        with patch.object(repair.connection, "vendor", "postgresql"):
            with self.assertRaisesMessage(repair.RepairError, "baseline_changed"):
                self.run_repair(apply=True, expected_baseline=result["baseline"])

    def test_apply_requires_postgres_and_exact_legacy_mapping(self):
        with patch.object(repair.connection, "vendor", "sqlite"):
            with self.assertRaisesMessage(repair.RepairError, "postgresql_required"):
                self.run_repair(apply=True, expected_baseline=self.run_repair()["baseline"])
        mapping = apps.get_model("legacy_import", "LegacyEntityMap")
        mapping.objects.create(
            organization=self.org,
            source_system="myedu_mariadb",
            entity_type="group_unit",
            legacy_pk="999",
            source_row_hash="c" * 64,
            transform_version="v1",
            target_model_label="organizations.orgunit",
            target_pk=repair.SOURCE,
            created_run=self.legacy_run,
            state="migrated",
        )
        with self.assertRaisesMessage(repair.RepairError, "legacy_identity_changed"):
            self.run_repair()
