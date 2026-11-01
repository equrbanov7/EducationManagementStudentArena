"""PostgreSQL preservation, real released policy, drift and fixed source authority."""

import copy
import hashlib
import json
import tempfile
import uuid
from datetime import timedelta
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.core.serializers.json import DjangoJSONEncoder
from django.test import TransactionTestCase
from django.utils import timezone

from apps.legacy_import.services import reviewed_solmaz_recovery as repair
from apps.legacy_import.services import reviewed_solmaz_spec as spec
from apps.legacy_import.services.delta.syllabi import document_for
from apps.legacy_import.services.rehearsal_syllabus_targets import build_section_data
from apps.legacy_import.tests.test_workload_syllabi import plan
from apps.syllabus.public import content_fingerprints
from apps.workload.public import reviewed_catalog_graph as e
from apps.workload.public import reviewed_catalog_schema
from apps.workload.tests import test_chair_cells_export as fixture
from apps.workload.tests.factories import activate_member


class SolmazRecoveryTests(TransactionTestCase):
    new_offering = fixture.ChairCellsExportTests.new_offering

    def setUp(self):
        fixture.ChairCellsExportTests.setUp(self)
        e.model("accounts.UserProfile").objects.filter(user=self.actor).update(organization=self.org)
        self.teacher = e.model("auth.User").objects.create_user(id=spec.TEACHER, username="fixed-source-author")
        e.model("accounts.UserProfile").objects.filter(user=self.teacher).update(organization=self.org)
        activate_member(
            self.org,
            self.teacher,
            "source-author",
            permissions=["grade.input", "grade.view", "course.view", "syllabus.edit"],
        )
        pins = copy.deepcopy(spec.PINS)
        self.pins_patch = patch.object(spec, "PINS", pins)
        self.pins_patch.start()
        self.addCleanup(self.pins_patch.stop)
        self.groups = {}
        for index, (gid, old) in enumerate(pins["groups"].items()):
            group = e.model("organizations.OrgUnit").objects.create(
                id=gid,
                organization=self.org,
                name=old["name"],
                code=old["code"],
                slug=f"fixed-group-{index}",
                unit_type="group",
                parent=self.stack["specialty"],
                settings=old["settings"],
            )
            self.groups[gid] = group
            pins["groups"][gid] = {k: e.normal(getattr(group, k)) for k in old}
        for sid, old in pins["subjects"].items():
            subject = e.model("registrar.Subject").objects.create(
                id=sid, organization=self.org, code=old["code"], name=old["name"], chair_unit=self.stack["chair"]
            )
            pins["subjects"][sid] = {k: e.normal(getattr(subject, k)) for k in old}
        task = e.model("workload.TeachingTask").objects.create(
            id=pins["task"]["id"],
            organization=self.org,
            chair=self.stack["chair"],
            academic_year="2026/2027",
            status="amended",
        )
        pins["task"] = {k: e.normal(getattr(task, k)) for k in pins["task"]}
        for rid, old in pins["rows"].items():
            row = e.model("workload.TeachingTaskRow").objects.create(organization=self.org, **old)
            row.groups.add(self.groups[pins["row_groups"][rid]])
        for old in pins["assignments"]:
            e.model("workload.TeacherAssignment").objects.create(organization=self.org, **old)
        self.courses = {}
        for cid, old in pins["courses"].items():
            self.courses[cid] = e.model("registrar.CourseOffering").objects.create(organization=self.org, **old)
        source = plan()["source"]
        source.update(id=8355, teacher_id=22, lesson_id=187, ders_saati=60)
        source["week"] = [{**source["week"][0], "id": 10000 + i, "muh_saat": "2", "sem_saat": "2"} for i in range(15)]
        self.sections, _ = build_section_data(document_for(source))
        pins["source_digest"] = hashlib.sha256(
            json.dumps(source, sort_keys=True, default=str, separators=(",", ":")).encode()
        ).hexdigest()
        pins["source_canonical_body"] = pins["donor_body_sha256"] = content_fingerprints(self.sections)[
            "canonical_body_sha256"
        ]
        for sid, old in pins["syllabi"].items():
            syllabus = e.model("syllabus.Syllabus").objects.create(
                id=sid,
                organization=self.org,
                subject_id=old["subject_id"],
                period_id=old["period_id"],
                offering_id=old["offering_id"],
                author=self.teacher,
            )
            vid = spec.DRAFT if sid == spec.SOURCE_SYLLABUS else spec.DONOR_VERSION
            approved = sid == spec.DONOR
            version = e.model("syllabus.SyllabusVersion").objects.create(
                id=vid,
                organization=self.org,
                syllabus=syllabus,
                major=1,
                minor=0,
                status="approved" if approved else "draft",
                approval_source="migration" if approved else "human",
                approved_at=timezone.now() if approved else None,
                locked_at=timezone.now().replace(microsecond=653123) if approved else None,
                plan_hours={"lecture": 15, "seminar": 30} if approved else {"lecture": 30, "seminar": 30},
            )
            for key, data in self.sections.items():
                e.model("syllabus.SyllabusSection").objects.create(
                    organization=self.org,
                    version=version,
                    section_id=key,
                    data=data if approved else {"original_human_body": "unchanged"},
                )
            syllabus.current_version = version
            syllabus.approved_version = version if approved else None
            syllabus.save(update_fields=["current_version", "approved_version"])
            pins["syllabi"][sid] = {k: e.normal(getattr(syllabus, k)) for k in old}
            pins["versions"][vid] = {k: e.normal(getattr(version, k)) for k in pins["versions"][vid]}
            if version.locked_at:
                pins["versions"][vid]["locked_at"] = DjangoJSONEncoder().default(version.locked_at)
        run = e.model("legacy_import.LegacyMigrationRun").objects.create(
            organization=self.org,
            source_system="myedu_mariadb",
            snapshot_sha256="a" * 64,
            snapshot_size_bytes=1,
            schema_version="v1",
            transform_version="v1",
            mode="profile",
        )
        e.model("legacy_import.LegacyMigrationRun").objects.filter(pk=run.pk).update(
            status="running", started_at=timezone.now()
        )
        links = (
            [
                ("worker", 22, "auth.user", str(spec.TEACHER)),
                ("worker_materialisation", 22, "auth.user", str(spec.TEACHER)),
            ]
            + [("lesson_subject", a, "registrar.subject", b) for a, b in spec.SUBJECT_SOURCES.items()]
            + [("group_unit", a, "organizations.orgunit", b) for a, b in spec.GROUP_SOURCES.items()]
        )
        for entity, legacy, label, target in links:
            e.model("legacy_import.LegacyEntityMap").objects.create(
                organization=self.org,
                source_system="myedu_mariadb",
                entity_type=entity,
                legacy_pk=str(legacy),
                target_model_label=label,
                target_pk=target,
                state="migrated",
                source_row_hash="b" * 64,
                created_run=run,
                transform_version="v1",
            )
        pins["bridges"] = [
            {k: r[k] for k in pins["bridges"][0]}
            for r in e.bounded(
                e.model("legacy_import.LegacyEntityMap").objects.filter(organization=self.org), lock=False
            )
        ]
        self.marks = []
        for course, status, score in zip(
            self.courses.values(), ("present", "present", "absent", "excused"), (0, None, None, None)
        ):
            enrollment = e.model("registrar.Enrollment").objects.create(
                organization=self.org, offering=course, student=self.student
            )
            lesson = e.model("registrar.Lesson").objects.create(
                organization=self.org, offering=course, date="2026-10-21", kind="seminar", created_by=self.actor
            )
            self.marks.append(
                e.model("registrar.LessonMark").objects.create(
                    organization=self.org,
                    lesson=lesson,
                    enrollment=enrollment,
                    status=status,
                    score=score,
                    entered_by=self.teacher,
                )
            )
        pins["schema"] = reviewed_catalog_schema.fingerprints()
        packet = {
            "format": "reviewed-solmaz-own-source/1",
            "organization_id": spec.ORG,
            "source": source,
            "source_approval_asserted": False,
            "current_authority": "explicit_reviewed_own_source_restoration",
            "source_subject_alias": [187, 2078],
            "official_source_sha256": pins["source_official_sha256"],
        }
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "source.json"
        self.path.write_text(json.dumps(packet))
        pins["source_packet_sha256"] = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.sha = pins["source_packet_sha256"]

    def run_repair(self, **kwargs):
        return repair.run(self.org, self.actor, self.path, self.sha, **kwargs)

    def apply(self):
        dry = self.run_repair()
        return self.run_repair(apply=True, expected_baseline=dry["baseline"])

    def test_dry_read_only_then_apply_repeat_and_undo_preserve_every_original(self):
        original_marks = list(e.model("registrar.LessonMark").objects.order_by("pk").values())
        original_sections = list(e.model("syllabus.SyllabusSection").objects.order_by("pk").values())
        counts = {
            label: e.model(label).objects.count()
            for label in ("audit.AuditLog", "syllabus.SyllabusVersion", "syllabus.SyllabusShare")
        }
        dry = self.run_repair()
        self.assertEqual(dry["teacher_hours"], 180)
        self.assertEqual(counts, {label: e.model(label).objects.count() for label in counts})
        result = self.run_repair(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual((result["new_source_versions"], result["new_shares"], result["teacher_hours"]), (1, 2, 165))
        self.assertEqual(self.run_repair()["status"], "already_applied")
        self.assertEqual(self.run_repair(apply=True)["status"], "already_applied")
        self.assertEqual(original_marks, list(e.model("registrar.LessonMark").objects.order_by("pk").values()))
        old_ids = [r["id"] for r in original_sections]
        self.assertEqual(
            original_sections,
            list(e.model("syllabus.SyllabusSection").objects.filter(pk__in=old_ids).order_by("pk").values()),
        )
        undone = self.run_repair(apply=True, undo=result["receipt"], expected_baseline=self.run_repair()["baseline"])
        self.assertEqual(undone["teacher_hours"], 180)
        self.assertEqual(self.run_repair(undo=result["receipt"])["status"], "already_undone")
        self.assertEqual(e.model("syllabus.SyllabusVersion").objects.filter(status="archived").count(), 1)
        self.assertEqual(e.model("syllabus.SyllabusShare").objects.count(), 0)
        self.assertEqual(original_marks, list(e.model("registrar.LessonMark").objects.order_by("pk").values()))

    def test_fresh_baseline_required_and_stale_metadata_rejected(self):
        with self.assertRaisesRegex(e.RepairError, "fresh_baseline"):
            self.run_repair(apply=True)
        dry = self.run_repair()
        self.marks[0].score = 1
        self.marks[0].save(update_fields=["score"])
        with self.assertRaisesRegex(e.RepairError, "fresh_baseline"):
            self.run_repair(apply=True, expected_baseline=dry["baseline"])

    def test_late_human_draft_edit_blocks_repeat_and_undo(self):
        result = self.apply()
        section = e.model("syllabus.SyllabusSection").objects.filter(version_id=spec.DRAFT).first()
        section.data = {"new_teacher_body": "retain"}
        section.save(update_fields=["data"])
        for kwargs in ({}, {"undo": result["receipt"], "apply": True}):
            with self.assertRaisesRegex(e.RepairError, "receipt_current_graph_drift"):
                self.run_repair(**kwargs)

    def test_new_human_target_syllabus_is_never_overwritten(self):
        target = self.courses[next(iter(spec.SHARES))]
        e.model("syllabus.Syllabus").objects.create(
            organization=self.org, subject=target.subject, period=target.period, offering=target, author=self.teacher
        )
        with self.assertRaisesRegex(e.RepairError, "budget|syllabi_changed"):
            self.run_repair()

    def test_nonreleased_actual_status_blocks(self):
        e.model("workload.TeachingTask").objects.filter(pk=spec.PINS["task"]["id"]).update(status="draft")
        with self.assertRaisesRegex(e.RepairError, "released_official_task"):
            self.run_repair()

    def test_wrong_namespace_or_missing_source_map_blocks(self):
        for pin in spec.PINS["bridges"]:
            if pin["entity_type"] == "group_unit" and pin["legacy_pk"] == "738":
                pin["entity_type"] = "group"
        with self.assertRaisesRegex(e.RepairError, "typed_source_identity"):
            self.run_repair()

    def test_new_credit_or_mark_after_apply_blocks_undo(self):
        result = self.apply()
        self.marks[2].status = "excused"
        self.marks[2].save(update_fields=["status"])
        with self.assertRaisesRegex(e.RepairError, "receipt_current_graph_drift"):
            self.run_repair(undo=result["receipt"], apply=True)

    def test_packet_mutation_and_body_replacement_refused(self):
        self.path.write_text(self.path.read_text() + " ")
        with self.assertRaisesRegex(e.RepairError, "source_packet_changed"):
            self.run_repair()

    def test_full_reverse_schema_guard_and_wrong_donor_block(self):
        with patch.object(reviewed_catalog_schema, "fingerprints", return_value={}):
            with self.assertRaisesRegex(e.RepairError, "unreviewed_relation_schema"):
                self.run_repair()
        section = (
            e.model("syllabus.SyllabusSection").objects.filter(version_id=spec.DONOR_VERSION, section_id="week").first()
        )
        section.data = {"rows": []}
        section.save(update_fields=["data"])
        with self.assertRaisesRegex(e.RepairError, "own_donor_body_changed"):
            self.run_repair()

    def new_credit(self, reverses=None):
        return e.model("registrar.AbsenceCredit").objects.create(
            organization=self.org,
            enrollment=self.marks[2].enrollment,
            hours=2,
            reason="Existing formal excusal evidence",
            actor=self.actor,
            request_token=uuid.uuid4(),
            reverses=reverses,
            old_absence_hours=0 if reverses else 2,
            new_absence_hours=2 if reverses else 0,
        )

    def test_current_formal_credit_preserved_and_new_credit_blocks_undo(self):
        credit = self.new_credit()
        original = list(e.model("registrar.AbsenceCredit").objects.values())
        result = self.apply()
        self.assertEqual(original, list(e.model("registrar.AbsenceCredit").objects.values()))
        self.new_credit(reverses=credit)
        with self.assertRaisesRegex(e.RepairError, "receipt_current_graph_drift"):
            self.run_repair(undo=result["receipt"], apply=True)

    def test_late_share_refusal_rolls_back_all_metadata_source_and_audits(self):
        labels = (
            "workload.TeachingTaskRow",
            "workload.TeacherAssignment",
            "registrar.CourseOffering",
            "syllabus.Syllabus",
            "syllabus.SyllabusVersion",
            "syllabus.SyllabusSection",
            "audit.AuditLog",
        )
        original = {label: list(e.model(label)._base_manager.order_by("pk").values()) for label in labels}
        dry = self.run_repair()
        with patch.object(repair, "link_legacy_share", return_value="has_own"):
            with self.assertRaisesRegex(e.RepairError, "own_source_share_refused"):
                self.run_repair(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(
            original, {label: list(e.model(label)._base_manager.order_by("pk").values()) for label in labels}
        )

    def test_default_cli_no_writes_no_source_or_grade_body_output(self):
        out = StringIO()
        count = e.model("audit.AuditLog").objects.count()
        call_command(
            "repair_reviewed_solmaz_catalog",
            actor=self.actor.username,
            manifest=str(self.path),
            manifest_sha256=self.sha,
            stdout=out,
        )
        self.assertIn("status=dry_run", out.getvalue())
        self.assertNotIn("original_human_body", out.getvalue())
        self.assertNotIn("score=", out.getvalue())
        self.assertEqual(count, e.model("audit.AuditLog").objects.count())

    def test_distributed_task_requires_existing_official_amendment(self):
        e.model("workload.TeachingTask").objects.filter(pk=spec.PINS["task"]["id"]).update(status="distributed")
        with self.assertRaisesRegex(e.RepairError, "official_amendment_required"):
            self.run_repair()

    def test_new_imported_body_edit_preserved_by_refusing_undo(self):
        result = self.apply()
        version = e.model("syllabus.SyllabusVersion").objects.exclude(pk__in=spec.PINS["versions"]).get()
        section = version.sections.get(section_id="week")
        section.data = {"rows": [{"topic": "Later retained author correction", "lecture": 60}]}
        section.save(update_fields=["data"])
        with self.assertRaisesRegex(e.RepairError, "created_own_source_changed"):
            self.run_repair(undo=result["receipt"], apply=True)
        self.assertTrue(e.model("syllabus.SyllabusShare").objects.exists())
        version.refresh_from_db()
        self.assertEqual(version.status, "approved")

    def test_same_bytes_pin_cannot_authorize_another_source_subject_alias(self):
        package = json.loads(self.path.read_bytes())
        package["source_subject_alias"] = [187, 2075]
        self.path.write_text(json.dumps(package))
        self.sha = spec.PINS["source_packet_sha256"] = hashlib.sha256(self.path.read_bytes()).hexdigest()
        with self.assertRaisesRegex(e.RepairError, "source_authority_changed"):
            self.run_repair()

    def test_source_symlink_or_oversized_file_refused_before_read(self):
        link = self.path.with_name("link.json")
        link.symlink_to(self.path)
        with self.assertRaisesRegex(e.RepairError, "regular_bounded_source"):
            repair.load(link, self.sha)
        large = self.path.with_name("large.json")
        with large.open("wb") as stream:
            stream.truncate(2000001)
        with patch.object(Path, "read_bytes", side_effect=AssertionError("unbounded read")):
            with self.assertRaisesRegex(e.RepairError, "regular_bounded_source"):
                repair.load(large, self.sha)

    def test_submillisecond_original_approval_drift_blocks_undo(self):
        result = self.apply()
        version = e.model("syllabus.SyllabusVersion").objects.get(pk=spec.DONOR_VERSION)
        e.model("syllabus.SyllabusVersion").objects.filter(pk=version.pk).update(
            locked_at=version.locked_at + timedelta(microseconds=1)
        )
        with self.assertRaisesRegex(e.RepairError, "receipt_current_graph_drift"):
            self.run_repair(undo=result["receipt"], apply=True)
