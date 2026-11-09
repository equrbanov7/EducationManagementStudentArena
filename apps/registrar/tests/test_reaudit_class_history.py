"""Missing-class review binds deleted-FK history through native live capture and PG."""

import datetime as dt
from unittest.mock import patch

from django.apps import apps
from django.test import TestCase

from apps.registrar.models import Lesson, LessonCorrection, LessonMark
from apps.registrar.reaudit_cells.class_history import fingerprint, from_snapshot, from_tables
from apps.registrar.reaudit_cells.manifest import normalize
from apps.registrar.reaudit_cells.snapshot import capture
from apps.registrar.tests import test_reaudit_cells_20261109 as fixtures
from apps.registrar.tests.test_lab_groups_2026_11_06 import _LabWorld


class ClassHistoryGuardTest(_LabWorld, TestCase):
    setUp = fixtures.CellsRepairTest.setUp
    map = fixtures.CellsRepairTest.map
    call = fixtures.CellsRepairTest.call
    set_sources = fixtures.CellsRepairTest.set_sources

    def reviewed_new_class(self):
        self.source["slot"]["date"] = "2026-10-20"
        self.source["slot"]["end_time"] = None
        self.source.update(class_authority_sha256="8" * 64, group_mask_proven=True)
        self.plan["allow_new_lessons"] = True
        live = capture(organization=self.org, actor=self.owner, plan=self.plan)
        self.source["class_history_sha256"] = fingerprint(
            from_snapshot(live), course=live["offerings"][0], slot=self.source["slot"]
        )
        return live

    def correction(self):
        return LessonCorrection.objects.create(
            organization=self.org,
            lesson=None,
            is_deletion=True,
            old_date=dt.date(2026, 10, 20),
            old_kind="seminar",
            old_hours=2,
            old_time="09:00",
            old_instructor=self.teacher,
            reason="other",
            note="Reviewed deleted-class evidence",
            document="synthetic-history.pdf",
            corrected_by=self.owner,
            corrected_by_name="Fixture",
        )

    def test_unchanged_history_allows_new_class_repeat_and_exact_undo(self):
        self.reviewed_new_class()
        dry = self.call()
        self.assertEqual(dry["counts"]["lessons_create"], 1)
        applied = self.call(apply=True, expected_baseline=dry["baseline"])
        self.assertTrue(Lesson.objects.filter(date="2026-10-20", end_time__isnull=True).exists())
        self.assertEqual(self.call(apply=True)["applied"], 0)
        undo = self.call(undo=applied["receipt"])
        self.call(apply=True, undo=applied["receipt"], expected_baseline=undo["baseline"])
        self.assertFalse(Lesson.objects.filter(date="2026-10-20").exists())
        self.assertEqual(self.call(apply=True, undo=applied["receipt"])["applied"], 0)

    def test_post_plan_deleted_fk_correction_blocks_new_lesson_and_owner_fill(self):
        self.reviewed_new_class()
        self.correction()
        dry = self.call()
        self.assertEqual(dry["counts"].get("lessons_create", 0), 0)
        self.assertEqual(dry["counts"]["hold_missing_lesson_class_history_changed"], 1)
        self.assertEqual(dry["pending"], 0)
        self.assertFalse(Lesson.objects.filter(date="2026-10-20").exists())
        self.assertFalse(LessonMark.objects.exists())

    def test_post_plan_unbound_deleted_lesson_audit_is_detected(self):
        self.reviewed_new_class()
        apps.get_model("audit", "AuditLog").objects.create(
            organization=self.org,
            user=self.owner,
            action="delete",
            resource_type="registrar.lesson",
            resource_id="unknown-deleted-lesson",
            old_values={"date": "2026-10-20", "start_time": "09:00", "kind": "seminar"},
        )
        dry = self.call()
        self.assertEqual(dry["counts"]["hold_missing_lesson_class_history_changed"], 1)
        self.assertEqual(dry["pending"], 0)

    def test_new_reversal_changes_review_fingerprint_even_with_null_lesson(self):
        correction = self.correction()
        self.reviewed_new_class()
        # Existing reviewed history is allowed only by an explicit authority SHA;
        # any later review decision changes that authority.
        apps.get_model("registrar", "CorrectionReversal").objects.create(
            organization=self.org,
            lesson_correction=correction,
            reverted_by=self.owner,
            reverted_by_ref=self.owner.pk,
            reason_code="operator_revert",
            reason_note="Reviewed reversal",
        )
        self.assertEqual(self.call()["counts"]["hold_missing_lesson_class_history_changed"], 1)

    def test_snapshot_and_full_export_use_same_fields_and_deleted_closure(self):
        self.correction()
        live = self.reviewed_new_class()
        tables = {
            label: normalize(list(apps.get_model(label).objects.filter(organization=self.org).values()))
            for label in (
                "registrar.Lesson",
                "registrar.LessonCorrection",
                "registrar.CorrectionReversal",
                "audit.AuditLog",
            )
        }
        course = live["offerings"][0]
        self.assertEqual(
            fingerprint(from_snapshot(live), course=course, slot=self.source["slot"]),
            fingerprint(from_tables(tables), course=course, slot=self.source["slot"]),
        )

    def test_native_capture_matches_export_cutoffs_and_four_audit_prefixes(self):
        from apps.legacy_import.services.reaudit_snapshot import queries

        boundary = dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc)
        with patch("django.utils.timezone.now", return_value=boundary - dt.timedelta(microseconds=1)):
            self.correction()
        with patch("django.utils.timezone.now", return_value=boundary):
            included = self.correction()
        audit = apps.get_model("audit", "AuditLog")
        audit_boundary = boundary - dt.timedelta(hours=4)
        included_audits = []
        for prefix in ("registrar.", "legacy_import.", "workload.", "syllabus.", "exams."):
            with patch("django.utils.timezone.now", return_value=audit_boundary):
                entry = audit.objects.create(
                    organization=self.org,
                    user=self.owner,
                    action="delete",
                    resource_type=prefix + "lesson",
                    resource_id="deleted-class",
                    old_values={"date": "2026-10-20"},
                )
            if prefix != "exams.":
                included_audits.append(str(entry.pk))
        with patch("django.utils.timezone.now", return_value=audit_boundary - dt.timedelta(microseconds=1)):
            audit.objects.create(
                organization=self.org,
                user=self.owner,
                action="delete",
                resource_type="registrar.lesson",
                old_values={"date": "2026-10-20"},
            )
        live = self.reviewed_new_class()
        self.assertEqual([row["id"] for row in live["class_history_corrections"]], [str(included.pk)])
        self.assertEqual({row["id"] for row in live["class_history_audits"]}, set(included_audits))
        with patch.object(queries, "ORG", str(self.org.pk)), patch.object(queries, "PERIOD", str(self.period.pk)):
            tables = {
                label: normalize(
                    list(queries.scoped_query(label, queries.SCHEMAS[label]).values(*queries.SCHEMAS[label]["fields"]))
                )
                for label in (
                    "registrar.Lesson",
                    "registrar.LessonCorrection",
                    "registrar.CorrectionReversal",
                    "audit.AuditLog",
                )
            }
        self.assertEqual(
            fingerprint(from_snapshot(live), course=live["offerings"][0], slot=self.source["slot"]),
            fingerprint(from_tables(tables), course=live["offerings"][0], slot=self.source["slot"]),
        )

    def test_builder_carries_only_the_reviewed_unchanged_history_hash(self):
        from apps.registrar.reaudit_cells.builder import Builder

        self.reviewed_new_class()
        labels = (
            "registrar.CourseOffering",
            "registrar.Enrollment",
            "registrar.Lesson",
            "registrar.LessonMark",
            "registrar.AssessmentComponent",
            "registrar.LessonCorrection",
            "registrar.CorrectionReversal",
            "legacy_import.LegacyEntityMap",
            "legacy_import.LegacyEntityMapVersion",
            "audit.AuditLog",
        )
        current = {
            "tables": {
                label: normalize(list(apps.get_model(label).objects.filter(organization=self.org).values()))
                for label in labels
            }
        }
        authority = {
            "offering_id": str(self.offering.pk),
            "journal_uniqid": "journal-one",
            "slot": self.source["slot"],
            "group_mask_proven": True,
            "class_history_sha256": self.source["class_history_sha256"],
        }
        source = {
            "journals": [
                dict(id=1, uniqid="journal-one", lesson_id=9, teacher_id=8, groups_id="[10]", fake=0, sonra_sil=0)
            ],
            "points": [
                dict(
                    id=11,
                    journal_uniqid="journal-one",
                    month_id="10",
                    day_number="20",
                    student_id=7,
                    point="0",
                    added_date="2026-10-20",
                    sem_muh=0,
                    time="09:00",
                    excusable=0,
                    lab=0,
                    update_counter=0,
                    updated_at=None,
                )
            ],
            "class_authorities": [authority],
        }

        def build():
            return Builder(
                source=source,
                current=current,
                organization_id=str(self.org.pk),
                period_id=str(self.period.pk),
                source_system="fixture",
                source_sha256="5" * 64,
                current_sha256="6" * 64,
            ).build()

        built = build()
        self.assertEqual(built["sources"][0]["class_history_sha256"], authority["class_history_sha256"])
        correction = self.correction()
        current["tables"]["registrar.LessonCorrection"] = normalize(
            list(LessonCorrection.objects.filter(pk=correction.pk).values())
        )
        changed = build()["sources"][0]
        self.assertNotIn("class_history_sha256", changed)
        self.assertEqual(changed["hold_reason"], "reviewed_class_history_changed_or_missing")

    def test_existing_lesson_source_grade_path_does_not_require_class_history(self):
        self.assertNotIn("class_history_sha256", self.source)
        dry = self.call()
        applied = self.call(apply=True, expected_baseline=dry["baseline"])
        self.assertGreater(applied["applied"], 0)
        self.assertEqual(LessonMark.objects.get(lesson=self.lesson, enrollment=self.e1).score, 0)
