"""Synthetic source identities only; full-grid repair, preservation, receipt and undo."""

import copy
import datetime as dt
import uuid

from django.apps import apps
from django.db import connection, transaction
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.registrar.models import JournalCorrection, Lesson, LessonMark
from apps.registrar.reaudit_cells.builder import Builder
from apps.registrar.reaudit_cells.manifest import FORMAT, RepairError, digest, normalize
from apps.registrar.reaudit_cells.planning import Planner
from apps.registrar.reaudit_cells.service import run
from apps.registrar.reaudit_cells.snapshot import capture
from apps.registrar.reaudit_cells.source_rows import rows
from apps.registrar.tests.test_lab_groups_2026_11_06 import _LabWorld
from core.rls import bypass_rls, journal_unlock


class SourceWinnerTest(SimpleTestCase):
    def point(self, **overrides):
        return dict(
            id=1,
            journal_uniqid="j",
            month_id="10",
            day_number="21",
            student_id=7,
            point="0",
            added_date="2026-10-21",
            sem_muh=0,
            time="09:00",
            excusable=0,
            lab=0,
            update_counter=0,
            updated_at=None,
            **overrides,
        )

    def test_zero_cutoff_and_component_not_attendance(self):
        points = [
            self.point(),
            {**self.point(), "id": 2, "day_number": "22"},
            {**self.point(), "id": 3, "month_id": "k1", "day_number": "1"},
            {**self.point(), "id": 4, "month_id": "pa", "point": "7"},
        ]
        result = list(rows({"points": points}))
        self.assertEqual(
            [(r["id"], r["kind"], r["score"]) for r in result],
            [("1", "grade", "0"), ("3", "component", "0"), ("4", "component", "7")],
        )
        self.assertEqual(result[1]["component_code"], "k1")

    def test_winner_is_update_sequence_not_maximum_grade(self):
        first = self.point()
        second = {**first, "id": 2, "point": "9"}
        third = {**first, "id": 3, "point": "0", "update_counter": 1}
        self.assertEqual([(r["id"], r["score"]) for r in rows({"points": [first, second, third]})], [("3", "0")])


class CellsRepairTest(_LabWorld, TestCase):
    def setUp(self):
        self.scope = bypass_rls()
        self.scope.__enter__()
        self.addCleanup(self.scope.__exit__, None, None, None)
        self.owner.is_superuser = True
        self.owner.save(update_fields=["is_superuser"])
        profile = apps.get_model("accounts", "UserProfile")
        profile.objects.update_or_create(
            user=self.owner,
            defaults={"organization": self.org, "access_state": "active", "is_deleted": False, "blocked_at": None},
        )
        self.period.start_date = dt.date(2026, 9, 15)
        self.period.end_date = dt.date(2027, 1, 15)
        self.period.save(update_fields=["start_date", "end_date"])
        self.lesson = Lesson.objects.create(
            organization=self.org,
            offering=self.offering,
            date=dt.date(2026, 10, 21),
            kind="seminar",
            hours=2,
            start_time=dt.time(9),
            end_time=dt.time(10, 20),
            instructor=self.teacher,
        )
        now = timezone.now()
        self.import_run = apps.get_model("legacy_import", "LegacyMigrationRun").objects.create(
            organization=self.org,
            source_system="fixture",
            snapshot_sha256="1" * 64,
            snapshot_size_bytes=1,
            schema_version="v1",
            transform_version="v1",
            mode="cutover",
        )
        type(self.import_run).objects.filter(pk=self.import_run.pk).update(status="running", started_at=timezone.now())
        self.map("student", "7", "auth.user", self.e1.student_id)
        self.map("worker", "8", "auth.user", self.teacher.pk)
        self.map("lesson_subject", "9", "registrar.subject", self.offering.subject_id)
        self.map("group_unit", "10", "organizations.orgunit", self.group.pk)
        self.markmap = self.map("journal_marks", "journal-one", "registrar.courseoffering", self.offering.pk)
        type(self.import_run).objects.filter(pk=self.import_run.pk).update(
            status="succeeded", finished_at=now + dt.timedelta(days=1)
        )
        self.import_run.refresh_from_db()
        self.plan = {
            "format": FORMAT,
            "organization_id": str(self.org.pk),
            "period_id": str(self.period.pk),
            "source_system": "fixture",
            "source_sha256": "2" * 64,
            "cutoff": "2026-10-21",
            "scope": "entire_active_period",
            "offering_ids": [str(self.offering.pk)],
            "routes": [
                {
                    "key": "one",
                    "offering_id": str(self.offering.pk),
                    "mode": "unique_typed_class",
                    "legacy_subject_id": "9",
                    "legacy_group_id": "10",
                    "legacy_teacher_id": "8",
                }
            ],
            "owner_present_policy": "applicable_blank_without_grade_hold",
            "allow_new_lessons": False,
            "sources": [],
        }
        self.source = {
            "id": "11",
            "kind": "grade",
            "score": "0",
            "route_keys": ["one"],
            "legacy_student_id": "7",
            "legacy_journal_uniqid": "journal-one",
            "slot": {
                "date": "2026-10-21",
                "start_time": "09:00:00",
                "end_time": "10:20:00",
                "kind": "seminar",
                "hours": 2,
                "lab_group": None,
                "seminar_group": None,
                "instructor_id": self.teacher.pk,
            },
        }
        self.set_sources(self.source)

    def map(self, kind, key, label, target):
        return apps.get_model("legacy_import", "LegacyEntityMap").objects.create(
            organization=self.org,
            source_system="fixture",
            entity_type=kind,
            legacy_pk=key,
            source_row_hash="3" * 64,
            transform_version="v1",
            target_model_label=label,
            target_pk=str(target),
            created_run=self.import_run,
            state="migrated",
        )

    def set_sources(self, *sources):
        self.plan["sources"] = list(sources)
        self.plan["source_ids_sha256"] = digest(sorted(row["id"] for row in sources))

    def call(self, **kwargs):
        with transaction.atomic():
            return run(organization=self.org, actor=self.owner, plan=self.plan, **kwargs)

    def test_default_reads_only_zero_then_present_and_repeat_zero_undo(self):
        with CaptureQueriesContext(connection) as sql:
            dry = self.call()
        self.assertFalse(
            any(
                q["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) or "FOR UPDATE" in q["sql"].upper()
                for q in sql
            )
        )
        self.assertEqual(dry["pending"], 3)
        self.assertEqual(LessonMark.objects.count(), 0)
        applied = self.call(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(applied["applied"], 3)
        self.assertEqual(LessonMark.objects.get(enrollment=self.e1).score, 0)
        self.assertEqual(
            LessonMark.objects.exclude(enrollment=self.e1).filter(status="present", score__isnull=True).count(), 2
        )
        self.assertEqual(self.call(apply=True)["applied"], 0)
        preview = self.call(undo=applied["receipt"])
        self.call(apply=True, undo=applied["receipt"], expected_baseline=preview["baseline"])
        self.assertEqual(LessonMark.objects.count(), 0)
        self.assertEqual(self.call(apply=True, undo=applied["receipt"])["applied"], 0)

    def test_later_numeric_and_correction_are_never_overwritten(self):
        mark = LessonMark.objects.create(
            organization=self.org,
            lesson=self.lesson,
            enrollment=self.e1,
            status="present",
            score=9,
            entered_by=self.teacher,
        )
        self.assertEqual(self.call()["pending"], 2)
        mark.refresh_from_db()
        self.assertEqual(mark.score, 9)
        with journal_unlock():
            mark.delete()
        JournalCorrection.objects.create(
            organization=self.org,
            lesson_mark_ref=uuid.uuid4(),
            lesson_ref=self.lesson.pk,
            enrollment_ref=self.e1.pk,
            field="score",
            reason="other",
            note="Synthetic correction",
            document="synthetic.pdf",
            corrected_by=self.owner,
            corrected_by_name="Fixture",
        )
        dry = self.call()
        self.assertEqual(dry["pending"], 2)
        self.assertEqual(dry["counts"]["hold_formal_correction_history_preserved"], 1)

    def test_unknown_unrelated_grade_does_not_block_owner_present(self):
        source = {**self.source, "route_keys": [], "candidate_offering_ids": []}
        self.set_sources(source)
        dry = self.call()
        self.assertEqual(dry["pending"], 3)
        self.assertFalse(dry["complete"])
        source["candidate_offering_ids"] = [str(self.offering.pk)]
        self.assertEqual(self.call()["pending"], 0)

    def test_native_copy_receipt_allows_retained_teacher_but_not_later_edit(self):
        from apps.registrar.reaudit_cells.creation_proof import seal

        mark = LessonMark.objects.create(
            organization=self.org, lesson=self.lesson, enrollment=self.e1, status="present", entered_by=self.teacher
        )
        log = apps.get_model("audit", "AuditLog").objects.create(
            organization=self.org,
            user=self.owner,
            action="update",
            resource_type="registrar.subgroup_journal_merge",
            changes={"manifest": {"marks_created": [str(mark.pk)]}},
        )
        row = normalize(LessonMark.objects.filter(pk=mark.pk).values().get())
        audit = normalize(apps.get_model("audit", "AuditLog").objects.filter(pk=log.pk).values().get())
        self.source["import_proof"] = {
            "audit_id": str(log.pk),
            "audit_sha256": seal(audit),
            "capture_sha256": "4" * 64,
            "mark_sha256": digest(row),
        }
        dry = self.call()
        self.assertEqual(dry["counts"]["marks_restore"], 1)
        applied = self.call(apply=True, expected_baseline=dry["baseline"])
        mark.refresh_from_db()
        self.assertEqual((mark.score, mark.entered_by_id), (0, self.teacher.pk))
        undo = self.call(undo=applied["receipt"])
        self.call(apply=True, undo=applied["receipt"], expected_baseline=undo["baseline"])
        with journal_unlock():
            LessonMark.objects.filter(pk=mark.pk).update(updated_at=timezone.now())
        row = normalize(LessonMark.objects.filter(pk=mark.pk).values().get())
        self.source["import_proof"]["mark_sha256"] = digest(row)
        self.assertEqual(self.call()["pending"], 2)

    def test_stale_baseline_or_wrong_tenant_refused(self):
        dry = self.call()
        LessonMark.objects.create(
            organization=self.org, lesson=self.lesson, enrollment=self.e0, status="present", entered_by=self.teacher
        )
        with self.assertRaisesRegex(RepairError, "fresh_baseline_required"):
            self.call(apply=True, expected_baseline=dry["baseline"])
        self.plan["organization_id"] = str(uuid.uuid4())
        with self.assertRaisesRegex(RepairError, "tenant_mismatch"):
            self.call()

    def test_imported_attendance_grade_restores_and_exact_undo(self):
        mark = LessonMark.objects.create(
            organization=self.org, lesson=self.lesson, enrollment=self.e1, status="present"
        )
        row = normalize(LessonMark.objects.filter(pk=mark.pk).values().get())
        self.source["import_proof"] = {
            "map_id": str(self.markmap.pk),
            "capture_sha256": "4" * 64,
            "mark_sha256": digest(row),
        }
        dry = self.call()
        self.assertEqual(dry["counts"]["marks_restore"], 1)
        applied = self.call(apply=True, expected_baseline=dry["baseline"])
        mark.refresh_from_db()
        self.assertEqual(mark.score, 0)
        undo = self.call(undo=applied["receipt"])
        self.call(apply=True, undo=applied["receipt"], expected_baseline=undo["baseline"])
        mark.refresh_from_db()
        self.assertIsNone(mark.score)
        self.assertEqual(normalize(LessonMark.objects.filter(pk=mark.pk).values().get()), row)

    def test_changed_import_or_human_undo_target_preserved(self):
        mark = LessonMark.objects.create(
            organization=self.org, lesson=self.lesson, enrollment=self.e1, status="present", entered_by=self.teacher
        )
        row = normalize(LessonMark.objects.filter(pk=mark.pk).values().get())
        self.source["import_proof"] = {
            "map_id": str(self.markmap.pk),
            "capture_sha256": "4" * 64,
            "mark_sha256": digest(row),
        }
        self.assertEqual(self.call()["pending"], 2)
        with journal_unlock():
            mark.delete()
        dry = self.call()
        applied = self.call(apply=True, expected_baseline=dry["baseline"])
        with journal_unlock():
            LessonMark.objects.filter(enrollment=self.e1).update(score=7, entered_by=self.teacher)
        with self.assertRaisesRegex(RepairError, "receipt_objects_changed"):
            self.call(undo=applied["receipt"])

    def test_exact_mask_and_conflicting_sources_hold(self):
        self.lesson.kind, self.lesson.lab_group = "lab", 2
        self.lesson.save(update_fields=["kind", "lab_group"])
        self.source["slot"].update(kind="lab", lab_group=2)
        dry = self.call()
        self.assertEqual(dry["pending"], 1)
        self.assertEqual(dry["counts"]["source_other_group_mask"], 1)
        self.lesson.kind, self.lesson.lab_group = "seminar", None
        self.lesson.save(update_fields=["kind", "lab_group"])
        self.source["slot"].update(kind="seminar", lab_group=None)
        self.set_sources(self.source, {**self.source, "id": "12", "score": "5"}, {**self.source, "id": "13"})
        self.assertEqual(self.call()["pending"], 0)

    def test_builder_uses_full_capture_and_exact_typed_route(self):
        labels = [
            "registrar.CourseOffering",
            "legacy_import.LegacyEntityMap",
            "legacy_import.LegacyEntityMapVersion",
            "registrar.Lesson",
            "registrar.Enrollment",
            "registrar.LessonMark",
            "registrar.AssessmentComponent",
            "audit.AuditLog",
        ]
        current = {
            "tables": {
                label: normalize(list(apps.get_model(label).objects.filter(organization=self.org).values()))
                for label in labels
            }
        }
        source = {
            "journals": [
                {
                    "id": 1,
                    "uniqid": "journal-one",
                    "lesson_id": 9,
                    "teacher_id": 8,
                    "groups_id": "[10]",
                    "fake": 0,
                    "sonra_sil": 0,
                }
            ],
            "points": [
                {
                    "id": 11,
                    "journal_uniqid": "journal-one",
                    "month_id": "10",
                    "day_number": "21",
                    "student_id": 7,
                    "point": "0",
                    "added_date": "2026-10-21",
                    "sem_muh": 0,
                    "time": "09:00",
                    "excusable": 0,
                    "lab": 0,
                    "update_counter": 0,
                    "updated_at": None,
                }
            ],
        }
        plan = Builder(
            source=source,
            current=current,
            organization_id=str(self.org.pk),
            period_id=str(self.period.pk),
            source_system="fixture",
            source_sha256="5" * 64,
            current_sha256="6" * 64,
        ).build()
        self.assertEqual(plan["sources"][0]["score"], "0")
        self.assertEqual(plan["sources"][0]["slot"]["hours"], 2)
        self.assertEqual(plan["offering_ids"], [str(self.offering.pk)])
        self.assertEqual(
            Planner(plan, capture(organization=self.org, actor=self.owner, plan=plan)).build()["counts"][
                "marks_create"
            ],
            3,
        )
        changed = copy.deepcopy(current)
        changed["tables"]["registrar.CourseOffering"][0]["organization_id"] = str(uuid.uuid4())
        with self.assertRaisesRegex(RepairError, "cross_tenant_capture_row"):
            Builder(
                source=source,
                current=changed,
                organization_id=str(self.org.pk),
                period_id=str(self.period.pk),
                source_system="fixture",
                source_sha256="5" * 64,
                current_sha256="6" * 64,
            )

    def test_imported_qb_to_present_or_excused_updates_counter_and_undo(self):
        from apps.registrar.gradebook_marks import recompute_absence_hours_many

        self.set_sources({**self.source, "kind": "attendance", "score": None, "status": "excused", "certain": True})
        mark = LessonMark.objects.create(organization=self.org, lesson=self.lesson, enrollment=self.e1, status="absent")
        recompute_absence_hours_many([self.e1])
        row = normalize(LessonMark.objects.filter(pk=mark.pk).values().get())
        self.plan["sources"][0]["import_proof"] = {
            "map_id": str(self.markmap.pk),
            "capture_sha256": "4" * 64,
            "mark_sha256": digest(row),
        }
        dry = self.call()
        self.assertEqual(dry["counts"]["marks_restore"], 1)
        applied = self.call(apply=True, expected_baseline=dry["baseline"])
        mark.refresh_from_db()
        self.e1.refresh_from_db()
        self.assertEqual((mark.status, mark.score, self.e1.absence_hours), ("excused", None, 0))
        undo = self.call(undo=applied["receipt"])
        self.call(apply=True, undo=applied["receipt"], expected_baseline=undo["baseline"])
        mark.refresh_from_db()
        self.e1.refresh_from_db()
        self.assertEqual((mark.status, self.e1.absence_hours), ("absent", 2))

    def test_known_component_zero_unknown_semantics_and_existing_exam_protected(self):
        component_model = apps.get_model("registrar", "AssessmentComponent")
        score_model = apps.get_model("registrar", "ComponentScore")
        component = component_model.objects.create(
            organization=self.org, offering=self.offering, name="Kollokvium 1", kind="kollokvium", order=1, max_score=10
        )
        source = {
            **self.source,
            "kind": "component",
            "component_id": str(component.pk),
            "component_code": "k1",
            "added_date": "2026-10-21",
        }
        self.plan["owner_present_policy"] = "disabled"
        self.set_sources(source)
        dry = self.call()
        self.assertEqual(dry["pending"], 1)
        applied = self.call(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(score_model.objects.get(component=component).score, 0)
        self.assertEqual(self.call(apply=True)["applied"], 0)
        undo = self.call(undo=applied["receipt"])
        self.call(apply=True, undo=applied["receipt"], expected_baseline=undo["baseline"])
        source["component_code"] = "unknown"
        self.assertEqual(self.call()["pending"], 0)
        source["component_code"] = "k1"
        score_model.objects.create(
            organization=self.org,
            component=component,
            enrollment=self.e1,
            score=8,
            exam_source={"attempt_id": "synthetic"},
        )
        self.assertEqual(self.call()["pending"], 0)
        self.assertEqual(score_model.objects.get(component=component).score, 8)

    def test_new_lesson_requires_full_authority_and_creates_full_applicable_grid(self):
        self.source["slot"]["date"] = "2026-10-20"
        self.source["slot"]["end_time"] = None
        self.assertEqual(self.call()["pending"], 0)
        self.plan["allow_new_lessons"] = True
        self.source.update(class_authority_sha256="8" * 64, group_mask_proven=True)
        from apps.registrar.reaudit_cells.class_history import fingerprint, from_snapshot

        snapshot = capture(organization=self.org, actor=self.owner, plan=self.plan)
        self.source["class_history_sha256"] = fingerprint(
            from_snapshot(snapshot), course=snapshot["offerings"][0], slot=self.source["slot"]
        )
        dry = self.call()
        self.assertEqual(dry["counts"]["lessons_create"], 1)
        self.assertEqual(dry["counts"]["marks_create"], 6)
        applied = self.call(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(self.call(apply=True)["applied"], 0)
        undo = self.call(undo=applied["receipt"])
        self.call(apply=True, undo=applied["receipt"], expected_baseline=undo["baseline"])
        self.assertEqual(Lesson.objects.count(), 1)


class CellsCommandTransactionTest(_LabWorld, TransactionTestCase):
    map = CellsRepairTest.map
    set_sources = CellsRepairTest.set_sources

    def setUp(self):
        self.setUpTestData()
        CellsRepairTest.setUp(self)

    @override_settings(RLS_TRANSACTION_SCOPED=True)
    def test_pooled_command_starts_one_real_readonly_transaction(self):
        import hashlib
        import io
        import json
        import os
        import tempfile
        from unittest.mock import patch

        from django.core.management import call_command

        from apps.registrar.management.commands import repair_audit_cells_20261109 as command

        original = command.run
        observed = []

        def checked(**kwargs):
            with connection.cursor() as cursor:
                cursor.execute("SHOW transaction_read_only")
                observed.append(cursor.fetchone()[0])
            return original(**kwargs)

        with tempfile.NamedTemporaryFile(mode="wb") as handle:
            os.chmod(handle.name, 0o600)
            raw = json.dumps(self.plan).encode()
            handle.write(raw)
            handle.flush()
            with patch.object(command, "run", side_effect=checked), CaptureQueriesContext(connection) as sql:
                output = io.StringIO()
                call_command(
                    "repair_audit_cells_20261109",
                    "--org",
                    self.org.slug,
                    "--actor",
                    self.owner.username,
                    "--file",
                    handle.name,
                    "--sha256",
                    hashlib.sha256(raw).hexdigest(),
                    stdout=output,
                )
        self.assertEqual(observed, ["on"])
        self.assertFalse(
            any(
                q["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")) or "FOR UPDATE" in q["sql"].upper()
                for q in sql
            )
        )
        self.assertEqual(LessonMark.objects.count(), 0)


class CanonicalMapTest(SimpleTestCase):
    def test_reviewed_latest_version_replaces_base_and_invalid_draft_refuses(self):
        from apps.registrar.reaudit_cells.ledger import effective_maps

        base = dict(
            id="map",
            organization_id="org",
            created_run_id="run1",
            source_row_hash="1" * 64,
            transform_version="v1",
            target_model_label="auth.user",
            target_pk="old",
            state="migrated",
            reconciliation_status="verified",
        )
        initial = dict(base, id="v1", entity_map_id="map", version_number=1, supersedes_id=None, recorded_run_id="run1")
        newer = dict(
            initial,
            id="v2",
            target_pk="new",
            version_number=2,
            supersedes_id="v1",
            approved_issue_id="issue",
            reviewed_by_id=1,
            reviewed_at="2026-11-09",
            review_reason_code="verified",
            review_evidence_digest="2" * 64,
            applied_by_id=2,
        )
        self.assertEqual(effective_maps([base], [initial, newer])[0]["target_pk"], "new")
        self.assertEqual(effective_maps([base], [initial])[0]["target_pk"], "old")
        self.assertEqual(
            effective_maps([base], [initial, dict(newer, target_pk="", target_model_label="", state="quarantined")]), []
        )
        with self.assertRaisesRegex(RepairError, "unapplied_or_unreviewed"):
            effective_maps([base], [initial, dict(newer, applied_by_id=None)])
        with self.assertRaisesRegex(RepairError, "chain_invalid"):
            effective_maps([base], [newer])
