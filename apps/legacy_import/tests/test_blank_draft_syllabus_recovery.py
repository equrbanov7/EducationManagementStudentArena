"""Append beside a pinned empty human draft; full atomic and late-undo safety."""

import copy
import hashlib
import io
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from apps.legacy_import.services import blank_draft_syllabus_recovery as recovery
from apps.legacy_import.services import blank_draft_syllabus_spec as spec
from apps.legacy_import.services.delta.syllabi import document_for
from apps.legacy_import.services.rehearsal_syllabus_targets import build_section_data
from apps.legacy_import.tests.test_workload_syllabi import plan
from apps.registrar.syllabus_notice import journal_syllabus_notice
from apps.syllabus.public import (
    content_fingerprints,
    offering_syllabus_state,
    resolve_actor,
    section_data_map,
    services,
)
from apps.workload.tests import test_chair_cells_export as fixture
from apps.workload.tests.factories import activate_member, make_org, make_task


class BlankDraftBase(TransactionTestCase):
    new_offering = fixture.ChairCellsExportTests.new_offering

    def setUp(self):
        fixture.ChairCellsExportTests.setUp(self)
        model = recovery.core.model
        model("accounts.UserProfile").objects.filter(user=self.actor).update(organization=self.org)
        activate_member(
            self.org, self.actor, "blank-source-owner", permissions=["grade.input", "syllabus.edit", "course.view"]
        )
        self.offering.instructor = self.actor
        self.offering.lesson_hours = 30
        self.offering.save(update_fields=["instructor", "lesson_hours"])
        group = self.offering.group
        group.settings = {"sector": "az", "degree_level": "bachelor", "education_form": "full_time"}
        group.save(update_fields=["settings"])
        self.syllabus, self.draft = services.create_draft(
            organization=self.org,
            subject=self.offering.subject,
            period=self.offering.period,
            offering=self.offering,
            author=self.actor,
            actor=resolve_actor(self.actor, self.org),
            plan_hours={"lecture": 15, "seminar": 15, "lab": 0},
        )
        # The pinned October draft predates automatic author-name seeding.
        info = self.draft.sections.get(section_id="info")
        info.data["teacher"] = ""
        info.save(update_fields=["data"])
        task = make_task(self.org, chair=self.stack["chair"], status="approved")
        self.row = model("workload.TeachingTaskRow").objects.create(
            organization=self.org,
            task=task,
            subject=self.offering.subject,
            period=self.offering.period,
            row_kind="teaching",
            season="fall",
            lecture_plan=0,
            lecture_total=15,
            seminar_plan=0,
            seminar_total=15,
            subgroup_count=1,
            union_count=1,
            degree_level="bachelor",
        )
        self.row.groups.add(group)
        assignments = []
        for kind in ("lecture", "seminar"):
            a = model("workload.TeacherAssignment").objects.create(
                organization=self.org, row=self.row, teacher=self.actor, activity=kind, hours=15
            )
            assignments.append(
                {
                    "id": str(a.pk),
                    "row_id": str(self.row.pk),
                    "teacher_id": self.actor.pk,
                    "activity": kind,
                    "hours": 15,
                    "is_hourly_paid": False,
                }
            )
        run = model("legacy_import.LegacyMigrationRun").objects.create(
            organization=self.org,
            source_system="myedu_mariadb",
            snapshot_sha256="a" * 64,
            snapshot_size_bytes=1,
            schema_version="v1",
            transform_version="v1",
            mode="profile",
        )
        model("legacy_import.LegacyMigrationRun").objects.filter(pk=run.pk).update(
            status="running", started_at=timezone.now()
        )
        for entity, legacy, label, target in (
            ("worker", 867, "auth.user", str(self.actor.pk)),
            ("lesson_subject", 14, "registrar.subject", str(self.offering.subject_id)),
        ):
            model("legacy_import.LegacyEntityMap").objects.create(
                organization=self.org,
                source_system="myedu_mariadb",
                entity_type=entity,
                legacy_pk=str(legacy),
                target_model_label=label,
                target_pk=target,
                source_row_hash="a" * 64,
                created_run=run,
                state="migrated",
                transform_version="v1",
            )
        source = plan()["source"]
        source.update(id=7474, teacher_id=867, lesson_id=14)
        sections, codes = build_section_data(document_for(source))
        base = copy.deepcopy(spec.ROWS[0])
        base.update(
            offering_id=str(self.offering.pk),
            subject_id=str(self.offering.subject_id),
            subject_code=self.offering.subject.code,
            period_id=str(self.offering.period_id),
            group_id=str(group.pk),
            author_id=self.actor.pk,
            source_digest=recovery.core.digest(source),
            uniqid=source["uniqid"],
            source_canonical_body=content_fingerprints(sections)["canonical_body_sha256"],
            hours=30,
            contact_hours=(15, 15, 0, 0),
            topics=8,
            selfwork_rows=1,
            selfwork_topics=len(sections["self"]["topics"]),
            syllabus_id=str(self.syllabus.pk),
            syllabus_sha256=recovery.core.metadata_digest(self.syllabus),
            draft_id=str(self.draft.pk),
            draft_sha256=recovery.core.metadata_digest(self.draft),
            section_pins=[
                {"id": str(s.pk), "section_id": s.section_id, "record_sha256": recovery.core.metadata_digest(s)}
                for s in self.draft.sections.all()
            ],
            row_id=str(self.row.pk),
            task_id=str(task.pk),
            row_group_ids=[str(group.pk)],
            row_fields={k: getattr(self.row, k) for k in base["row_fields"]},
            assignments=sorted(assignments, key=lambda x: x["id"]),
            education_form="full_time",
        )
        package = {
            "format": "blank-draft-own-syllabi/1",
            "organization_id": str(self.org.pk),
            "legacy_source_approval_asserted": False,
            "current_approval_authority": "explicit_user_reviewed_own_source_recovery",
            "unique_sources": {"7474": source},
            "selected_targets": [base["offering_id"]],
        }
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.file = Path(self.tmp.name) / "source.json"
        self.file.write_text(json.dumps(package))
        self.sha = hashlib.sha256(self.file.read_bytes()).hexdigest()
        base["packet_sha256"] = self.sha
        self.pin = base
        patched = patch.object(spec, "ROWS", (base,))
        patched.start()
        self.addCleanup(patched.stop)
        self.original = self.old_rows()

    def old_rows(self):
        model = recovery.core.model
        self.syllabus.refresh_from_db()
        return {
            "draft": list(model("syllabus.SyllabusVersion").objects.filter(pk=self.draft.pk).values()),
            "sections": list(
                model("syllabus.SyllabusSection").objects.filter(version=self.draft).order_by("pk").values()
            ),
            "lessons": list(model("registrar.Lesson").objects.filter(offering=self.offering).values()),
            "marks": list(model("registrar.LessonMark").objects.filter(lesson__offering=self.offering).values()),
            "enrollments": list(model("registrar.Enrollment").objects.filter(offering=self.offering).values()),
        }

    def run_cmd(self, *, apply=False, baseline="", undo=""):
        out = io.StringIO()
        kwargs = dict(
            org=self.org.slug, actor=self.actor.username, apply=apply, baseline=baseline, undo=undo, stdout=out
        )
        if not undo:
            kwargs.update(file=str(self.file), sha256=self.sha)
        call_command("recover_blank_draft_syllabi", **kwargs)
        return json.loads(out.getvalue())

    def apply_once(self):
        dry = self.run_cmd()
        return self.run_cmd(apply=True, baseline=dry["baseline"])

    def test_dry_actual_transaction_scope_and_no_writes(self):
        observed = []
        original = recovery.state.capture

        def capture(*args, **kwargs):
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT current_setting('app.current_org_id'),current_setting('app.bypass_rls'),current_setting('app.current_user_id')"
                )
                observed.append(cursor.fetchone())
            self.assertTrue(connection.in_atomic_block)
            return original(*args, **kwargs)

        with (
            patch.object(recovery.state, "capture", side_effect=capture),
            patch.object(recovery, "import_migrated_version", side_effect=AssertionError("dry_must_not_write")),
        ):
            result = self.run_cmd()
        self.assertEqual(result["status"], "dry_run")
        self.assertEqual(observed, [(str(self.org.pk), "off", str(self.actor.pk))])
        self.assertEqual(self.old_rows(), self.original)
        self.assertEqual(self.syllabus.versions.count(), 1)

    def test_apply_repeat_and_exact_original_draft_rows_preserved(self):
        result = self.apply_once()
        self.assertEqual(result["status"], "applied")
        self.assertEqual(self.old_rows(), self.original)
        self.syllabus.refresh_from_db()
        self.assertEqual(self.syllabus.current_version_id, self.draft.pk)
        self.assertIsNotNone(self.syllabus.approved_version_id)
        approved = self.syllabus.approved_version
        self.assertEqual(approved.status, "approved")
        self.assertEqual(approved.approval_source, "migration")
        self.assertIsNone(approved.approved_by_id)
        self.assertNotEqual(approved.pk, self.draft.pk)
        published = offering_syllabus_state(self.syllabus)
        self.assertEqual(published["approved_version"].pk, approved.pk)
        self.assertEqual(published["version"].pk, self.draft.pk)
        notice = journal_syllabus_notice(self.offering)
        self.assertFalse(notice["show_banner"])
        self.assertEqual(notice["version_label"], approved.label)
        dry = self.run_cmd()
        self.assertEqual(dry["status"], "already_present")
        repeat = self.run_cmd(apply=True, baseline=dry["baseline"])
        self.assertEqual(repeat["receipt"], result["receipt"])
        self.assertEqual(self.syllabus.versions.count(), 2)

    def test_fresh_baseline_required_and_drift_rejected(self):
        with self.assertRaisesRegex(CommandError, "fresh_baseline_required"):
            self.run_cmd(apply=True)
        with self.assertRaisesRegex(CommandError, "fresh_baseline_required"):
            self.run_cmd(apply=True, baseline="0" * 64)
        self.assertEqual(self.old_rows(), self.original)

    def test_source_body_tamper_fails_closed(self):
        packet = json.loads(self.file.read_text())
        packet["unique_sources"]["7474"]["sections"][next(iter(packet["unique_sources"]["7474"]["sections"]))][0][
            1
        ] = "Changed source body"
        self.file.write_text(json.dumps(packet))
        with self.assertRaisesRegex(CommandError, "pinned_source_packet_changed"):
            self.run_cmd()

    def test_new_human_text_or_completed_flag_aborts(self):
        section = self.draft.sections.get(section_id="desc")
        section.data = {"description": "new human work"}
        section.save(update_fields=["data"])
        with self.assertRaisesRegex(CommandError, "human_draft_sections_changed"):
            self.run_cmd()
        self.assertEqual(self.syllabus.versions.count(), 1)

    def test_workload_and_source_mapping_tamper_aborts(self):
        self.row.seminar_total = 16
        self.row.save(update_fields=["seminar_total"])
        with self.assertRaisesRegex(CommandError, "official_source_workload_changed"):
            self.run_cmd()
        self.row.seminar_total = 15
        self.row.save(update_fields=["seminar_total"])
        packet = json.loads(self.file.read_text())
        packet["unique_sources"]["7474"]["teacher_id"] = 868
        self.file.write_text(json.dumps(packet))
        self.sha = hashlib.sha256(self.file.read_bytes()).hexdigest()
        self.pin.update(
            source_author=868,
            packet_sha256=self.sha,
            source_digest=recovery.core.digest(packet["unique_sources"]["7474"]),
        )
        with self.assertRaisesRegex(CommandError, "exact_source_identity_mapping_changed"):
            self.run_cmd()

    def test_undo_archives_only_new_source_and_repeat_preserves_original_ids(self):
        applied = self.apply_once()
        dry = self.run_cmd(undo=applied["receipt"])
        result = self.run_cmd(undo=applied["receipt"], apply=True, baseline=dry["baseline"])
        self.assertEqual(result["status"], "undone")
        self.assertEqual(self.old_rows(), self.original)
        self.syllabus.refresh_from_db()
        self.assertIsNone(self.syllabus.approved_version_id)
        self.assertEqual(self.syllabus.current_version_id, self.draft.pk)
        self.assertEqual(self.syllabus.versions.count(), 2)
        self.assertEqual(self.syllabus.versions.exclude(pk=self.draft.pk).get().status, "archived")
        self.assertEqual(self.run_cmd(undo=applied["receipt"])["status"], "already_undone")

    def test_foreign_actor_and_contradictory_block_or_deletion_flags_refused(self):
        User = recovery.core.model("auth.User")
        foreign = User.objects.create_superuser("foreign_blank_source_admin", password="test")
        org = make_org("foreign-blank-source", owner=foreign)
        recovery.core.model("accounts.UserProfile").objects.filter(user=foreign).update(organization=org)
        actor = self.actor
        self.actor = foreign
        try:
            with patch.object(recovery, "load", side_effect=AssertionError("foreign_actor_must_not_read_source")):
                with self.assertRaisesRegex(CommandError, "active_fixed_tenant_superadmin_required"):
                    self.run_cmd()
        finally:
            self.actor = actor
        for field in ("blocked_at", "deleted_at"):
            profile = recovery.core.model("accounts.UserProfile").objects.filter(user=actor)
            profile.update(**{field: timezone.now()})
            with self.assertRaisesRegex(CommandError, "active_fixed_tenant_superadmin_required"):
                self.run_cmd()
            profile.update(**{field: None})
        self.assertEqual(self.syllabus.versions.count(), 1)

    def test_author_contradictory_block_or_deletion_flags_refused(self):
        author = self.actor
        operator = recovery.core.model("auth.User").objects.create_superuser(
            "separate_source_operator", password="test"
        )
        recovery.core.model("accounts.UserProfile").objects.filter(user=operator).update(organization=self.org)
        self.actor = operator
        try:
            for field in ("blocked_at", "deleted_at"):
                profile = recovery.core.model("accounts.UserProfile").objects.filter(user=author)
                profile.update(**{field: timezone.now()})
                with self.assertRaisesRegex(CommandError, "source_author_inactive_or_deleted"):
                    self.run_cmd()
                profile.update(**{field: None})
        finally:
            self.actor = author
        self.assertEqual(self.syllabus.versions.count(), 1)

    def test_foreign_undo_known_unknown_and_undone_receipts_same_denial(self):
        from uuid import uuid4

        applied = self.apply_once()
        actor = self.actor
        foreign = recovery.core.model("auth.User").objects.create_superuser("foreign_receipt_operator", password="test")
        org = make_org("foreign-receipt-scope", owner=foreign)
        recovery.core.model("accounts.UserProfile").objects.filter(user=foreign).update(organization=org)
        for receipt in (applied["receipt"], str(uuid4())):
            self.actor = foreign
            with self.assertRaisesRegex(CommandError, "active_fixed_tenant_superadmin_required"):
                self.run_cmd(undo=receipt)
        self.actor = actor
        dry = self.run_cmd(undo=applied["receipt"])
        self.run_cmd(undo=applied["receipt"], apply=True, baseline=dry["baseline"])
        self.actor = foreign
        with self.assertRaisesRegex(CommandError, "active_fixed_tenant_superadmin_required"):
            self.run_cmd(undo=applied["receipt"])
        self.actor = actor

    def test_existing_completed_flag_or_late_source_edit_refused(self):
        section = self.draft.sections.get(section_id="desc")
        section.is_complete = True
        section.save(update_fields=["is_complete"])
        with self.assertRaisesRegex(CommandError, "human_draft_sections_changed"):
            self.run_cmd()
        section.is_complete = False
        section.save(update_fields=["is_complete"])
        result = self.apply_once()
        source = self.syllabus.versions.exclude(pk=self.draft.pk).get()
        source_section = source.sections.get(section_id="desc")
        source_section.data = {"description": "new source-version edit"}
        source_section.save(update_fields=["data"])
        with self.assertRaisesRegex(CommandError, "current_post_restore_graph_changed"):
            self.run_cmd(undo=result["receipt"])

    def test_late_new_grade_blocks_undo(self):
        applied = self.apply_once()
        mark = recovery.core.model("registrar.LessonMark").objects.filter(lesson__offering=self.offering).get()
        mark.score = 8
        mark.save(update_fields=["score"])
        with self.assertRaisesRegex(CommandError, "current_post_restore_graph_changed"):
            self.run_cmd(undo=applied["receipt"])
        self.assertEqual(self.syllabus.versions.filter(status="approved").count(), 1)

    def pin_meaningful_draft(self, draft, pin):
        for key, value in (
            ("info", {"teacher": "Synthetic preserved author"}),
            ("desc", {"description": "Unapproved human work must stay untouched"}),
        ):
            section = draft.sections.get(section_id=key)
            section.data = value
            section.save(update_fields=["data"])
        services.recompute_completion(draft)
        draft.refresh_from_db()
        pin.update(
            draft_sha256=recovery.core.metadata_digest(draft),
            expected_nonblank_sections=["desc", "info"],
            section_pins=[
                {"id": str(s.pk), "section_id": s.section_id, "record_sha256": recovery.core.metadata_digest(s)}
                for s in draft.sections.all()
            ],
        )

    def test_compiled_two_nonblank_sections_are_preserved_not_published(self):
        self.pin_meaningful_draft(self.draft, self.pin)
        self.original = self.old_rows()
        self.apply_once()
        self.assertEqual(self.old_rows(), self.original)
        self.syllabus.refresh_from_db()
        self.assertEqual(self.syllabus.current_version_id, self.draft.pk)
        self.assertEqual(self.syllabus.current_version.status, "draft")
        self.assertEqual(self.syllabus.approved_version.approval_source, "migration")
        self.assertNotEqual(self.syllabus.approved_version_id, self.draft.pk)

    def two_cases(self):
        model = recovery.core.model
        group = model("organizations.OrgUnit").objects.create(
            organization=self.org,
            unit_type="group",
            parent=self.stack["specialty"],
            name="Second source fixture",
            slug="second-source-fixture",
            settings=self.offering.group.settings,
        )
        offering = model("registrar.CourseOffering").objects.create(
            organization=self.org,
            subject=self.offering.subject,
            period=self.offering.period,
            group=group,
            instructor=self.actor,
            lesson_hours=30,
        )
        syllabus, draft = services.create_draft(
            organization=self.org,
            subject=offering.subject,
            offering=offering,
            period=offering.period,
            actor=resolve_actor(self.actor, self.org),
            author=self.actor,
            plan_hours={"lecture": 15, "seminar": 15},
        )
        row = model("workload.TeachingTaskRow").objects.create(
            organization=self.org,
            task=self.row.task,
            subject=offering.subject,
            period=offering.period,
            lecture_plan=0,
            lecture_total=15,
            seminar_plan=0,
            seminar_total=15,
            subgroup_count=1,
            union_count=1,
            row_kind="teaching",
            season="fall",
            degree_level="bachelor",
        )
        row.groups.add(group)
        assignments = []
        for kind in ("lecture", "seminar"):
            a = model("workload.TeacherAssignment").objects.create(
                organization=self.org, row=row, teacher=self.actor, activity=kind, hours=15
            )
            assignments.append(
                {
                    "id": str(a.pk),
                    "row_id": str(row.pk),
                    "teacher_id": self.actor.pk,
                    "activity": kind,
                    "hours": 15,
                    "is_hourly_paid": False,
                }
            )
        package = json.loads(self.file.read_text())
        source = copy.deepcopy(package["unique_sources"]["7474"])
        source.update(id=8744, uniqid="synthetic-second-own")
        for week in source["week"]:
            week.update(id=week["id"] + 1000, uniqid=source["uniqid"])
        source["week"][0]["movzu"] = "Distinct second synthetic course topic"
        source["sections"]["sillabus_tesviri_ve_meqsedi"] = [[9999, "Distinct second source academic description"]]
        sections, _ = build_section_data(document_for(source))
        second = copy.deepcopy(self.pin)
        second.update(
            offering_id=str(offering.pk),
            group_id=str(group.pk),
            syllabus_id=str(syllabus.pk),
            syllabus_sha256=recovery.core.metadata_digest(syllabus),
            draft_id=str(draft.pk),
            row_id=str(row.pk),
            row_group_ids=[str(group.pk)],
            assignments=sorted(assignments, key=lambda a: a["id"]),
            source_syllabus=8744,
            uniqid=source["uniqid"],
            source_digest=recovery.core.digest(source),
            source_canonical_body=content_fingerprints(sections)["canonical_body_sha256"],
        )
        self.pin_meaningful_draft(draft, second)
        package["unique_sources"]["8744"] = source
        package["selected_targets"].append(str(offering.pk))
        self.file.write_text(json.dumps(package))
        self.sha = hashlib.sha256(self.file.read_bytes()).hexdigest()
        self.pin["packet_sha256"] = second["packet_sha256"] = self.sha
        scoped = patch.object(spec, "ROWS", (self.pin, second))
        scoped.start()
        self.addCleanup(scoped.stop)
        original = {
            "version": list(model("syllabus.SyllabusVersion").objects.filter(pk=draft.pk).values()),
            "sections": list(model("syllabus.SyllabusSection").objects.filter(version=draft).order_by("pk").values()),
        }
        return syllabus, draft, original

    def test_two_case_apply_preserves_meaningful_draft_and_both_source_contexts(self):
        syllabus, draft, original = self.two_cases()
        result = self.apply_once()
        self.assertEqual(result["cases"], 2)
        self.assertEqual(result["versions_created"], 2)
        self.assertEqual(self.old_rows(), self.original)
        model = recovery.core.model
        self.assertEqual(
            list(model("syllabus.SyllabusVersion").objects.filter(pk=draft.pk).values()), original["version"]
        )
        self.assertEqual(
            list(model("syllabus.SyllabusSection").objects.filter(version=draft).order_by("pk").values()),
            original["sections"],
        )
        syllabus.refresh_from_db()
        self.assertEqual(syllabus.current_version_id, draft.pk)
        self.assertEqual(syllabus.approved_version.status, "approved")
        self.assertNotEqual(spec.ROWS[0]["source_canonical_body"], spec.ROWS[1]["source_canonical_body"])
        for row in spec.ROWS:
            dossier = model("syllabus.Syllabus").objects.get(pk=row["syllabus_id"])
            actual = content_fingerprints(section_data_map(dossier.approved_version))
            self.assertEqual(actual["canonical_body_sha256"], row["source_canonical_body"])

    def test_second_case_failure_atomically_rolls_back_first_case(self):
        syllabus, draft, original = self.two_cases()
        dry = self.run_cmd()
        importer = recovery.import_migrated_version
        calls = []

        def fail_second(**kwargs):
            result = importer(**kwargs)
            calls.append(result)
            if len(calls) == 2:
                raise RuntimeError("synthetic_second_case_failure")
            return result

        with (
            patch.object(recovery, "import_migrated_version", side_effect=fail_second),
            self.assertRaisesRegex(CommandError, "blank_draft_restore_refused"),
        ):
            self.run_cmd(apply=True, baseline=dry["baseline"])
        self.assertEqual(self.old_rows(), self.original)
        self.syllabus.refresh_from_db()
        syllabus.refresh_from_db()
        self.assertIsNone(self.syllabus.approved_version_id)
        self.assertIsNone(syllabus.approved_version_id)
        self.assertEqual(self.syllabus.versions.count(), 1)
        self.assertEqual(syllabus.versions.count(), 1)
        self.assertEqual(
            list(recovery.core.model("syllabus.SyllabusSection").objects.filter(version=draft).order_by("pk").values()),
            original["sections"],
        )

    def test_failure_after_append_rolls_everything_back(self):
        dry = self.run_cmd()
        original = recovery.import_migrated_version

        def fail(**kwargs):
            original(**kwargs)
            raise RuntimeError("synthetic_after_append_failure")

        with (
            patch.object(recovery, "import_migrated_version", side_effect=fail),
            self.assertRaisesRegex(CommandError, "blank_draft_restore_refused"),
        ):
            self.run_cmd(apply=True, baseline=dry["baseline"])
        self.assertEqual(self.old_rows(), self.original)
        self.syllabus.refresh_from_db()
        self.assertIsNone(self.syllabus.approved_version_id)
        self.assertEqual(self.syllabus.versions.count(), 1)


@override_settings(RLS_TRANSACTION_SCOPED=False)
class BlankDraftSessionRLS(BlankDraftBase):
    pass


@override_settings(RLS_TRANSACTION_SCOPED=True)
class BlankDraftTransactionRLS(BlankDraftBase):
    pass
