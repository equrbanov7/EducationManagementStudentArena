"""Migrated PG: exact seminar grant, immutable owner/history, READ ONLY dry and undo."""

import hashlib
import io
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TransactionTestCase, override_settings

from openpyxl import Workbook, load_workbook

from apps.registrar.journal_access import is_direct_editor
from apps.registrar.journal_shares import forget, journal_scope
from apps.registrar.models import (
    CourseOffering,
    Curriculum,
    Enrollment,
    JournalShare,
    Lesson,
    LessonMark,
    StudentAcademicRecord,
    TeachingHandover,
)
from apps.workload.constants import TaskStatus
from apps.workload.models import TeacherAssignment
from apps.workload.services import reviewed_kind_share_repair as service
from apps.workload.services import reviewed_kind_share_source as spec
from apps.workload.services import reviewed_kind_share_state as state
from apps.workload.services.sbio235_state import RepairError
from apps.workload.tests.factories import (
    TEACHER_PERMS,
    activate_member,
    make_org,
    make_row,
    make_structure,
    make_task,
)

User = get_user_model()


class ReviewedKindShareRepairTests(TransactionTestCase):
    def setUp(self):
        self.org = make_org("biostat-reviewed")
        self.actor = User.objects.create_superuser("biostat-operator", password="PRIVATE_AUTH_SENTINEL")
        self.actor.set_active_organization_context(self.org)
        self.stack = make_structure(self.org, code="BIOREVIEW")
        self.stack["group"].name = "236 BİO"
        self.stack["group"].save(update_fields=["name"])
        self.task = make_task(self.org, self.stack["chair"], status=TaskStatus.AMENDED)
        self.row = make_row(self.task, self.stack, lecture_total=30, seminar_total=15)
        self.owner = User.objects.create_user("biostat-existing-owner")
        self.teacher = User.objects.create_user("biostat-source-teacher", first_name="Aytac", last_name="Proof")
        self.teacher.profile.patronymic = "Parent"
        self.teacher.profile.save(update_fields=["patronymic"])
        for teacher in (self.owner, self.teacher):
            activate_member(self.org, teacher, "teacher", permissions=TEACHER_PERMS)
        self.assignments = {}
        for teacher, kind, hours in (
            (self.owner, "lecture", 30),
            (self.teacher, "seminar", 15),
        ):
            assignment = TeacherAssignment.objects.create(
                organization=self.org,
                row=self.row,
                teacher=teacher,
                activity=kind,
                hours=hours,
            )
            self.assignments[str(assignment.id)] = (teacher.id, kind, hours)
        self.offering = CourseOffering.objects.create(
            organization=self.org,
            subject=self.stack["subject"],
            period=self.stack["period"],
            group=self.stack["group"],
            instructor=self.owner,
            lesson_hours=45,
        )
        curriculum = Curriculum.objects.create(
            organization=self.org, program=self.stack["program"], admission_year=2026
        )
        self.enrollments = []
        for index in range(2):
            student = User.objects.create_user(f"biostat-student-{index}")
            activate_member(self.org, student, "student", permissions=["course.view"])
            StudentAcademicRecord.objects.create(
                organization=self.org,
                student=student,
                program=self.stack["program"],
                curriculum=curriculum,
                group=self.stack["group"],
                admission_year=2026,
            )
            self.enrollments.append(
                Enrollment.objects.create(organization=self.org, student=student, offering=self.offering)
            )
        self.lesson = Lesson.objects.create(
            organization=self.org,
            offering=self.offering,
            date="2026-10-20",
            kind="seminar",
        )
        self.mark = LessonMark.objects.create(
            organization=self.org,
            lesson=self.lesson,
            enrollment=self.enrollments[0],
            status="excused",
            score=7,
            entered_by=self.owner,
        )
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.source = Path(self.temp.name) / "source.xlsx"
        book = Workbook()
        sheet = book.active
        sheet.title = "Dərs yükü"
        for cell, value in {
            "A98": "Proof Aytac Parent qızı",
            "B101": "236 BT,236 BİO",
            "C101": self.stack["subject"].name,
            "H101": 15,
        }.items():
            sheet[cell] = value
        book.save(self.source)
        book.close()
        self.source.chmod(0o600)
        self.source_sha = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.pins = dict(
            ORG=str(self.org.id),
            PERIOD=str(self.offering.period_id),
            OFFERING=str(self.offering.id),
            SUBJECT=str(self.offering.subject_id),
            GROUP=str(self.offering.group_id),
            ROW=str(self.row.id),
            TASK=str(self.task.id),
            TEACHER=self.teacher.id,
            OWNER=self.owner.id,
            ASSIGNMENTS=self.assignments,
            SOURCE_SHA=self.source_sha,
            TEACHER_NAME_SHA=spec.text_sha("Proof Aytac Parent"),
            CELL_HASHES={
                "A98": spec.text_sha("Proof Aytac Parent qızı"),
                "B101": spec.text_sha("236 BT,236 BİO"),
                "C101": spec.text_sha(self.stack["subject"].name),
            },
        )
        self.patch = patch.multiple(spec, **self.pins)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def run_repair(self, **kwargs):
        return service.repair(
            organization=self.org,
            actor=self.actor,
            source_sha256=spec.SOURCE_SHA,
            **kwargs,
        )

    def apply(self):
        dry = self.run_repair()
        return self.run_repair(apply=True, expected_baseline=dry["baseline"])

    def test_dry_then_apply_narrow_kind_explicit_roster_and_unchanged_cells_owner(self):
        _, _, _, before = state.capture(organization=self.org)
        self.assertTrue(journal_scope(self.owner, self.offering).allows_kind("seminar"))
        dry = self.run_repair()
        self.assertFalse(JournalShare.objects.exists())
        self.assertFalse(is_direct_editor(self.teacher, self.offering))
        self.run_repair(apply=True, expected_baseline=dry["baseline"])
        share = JournalShare.objects.get(teacher=self.teacher, offering=self.offering)
        self.assertEqual(share.source, "workload")
        self.assertEqual(share.kinds, ["seminar"])
        self.assertEqual(
            set(share.enrollments.values_list("pk", flat=True)),
            {e.pk for e in self.enrollments},
        )
        forget(self.offering)
        scope = journal_scope(self.teacher, self.offering)
        self.assertTrue(is_direct_editor(self.teacher, self.offering))
        self.assertFalse(scope.allows_kind("lecture"))
        self.assertFalse(scope.allows_kind("lab"))
        self.assertFalse(scope.can_manage_scores)
        self.assertTrue(journal_scope(self.owner, self.offering).full)
        self.assertTrue(journal_scope(self.owner, self.offering).allows_kind("seminar"))
        _, _, _, after = state.capture(organization=self.org)
        self.assertEqual(before["protected"], after["protected"])
        self.mark.refresh_from_db()
        self.assertEqual(
            (self.mark.status, self.mark.score, self.mark.entered_by_id),
            ("excused", 7, self.owner.id),
        )
        self.offering.refresh_from_db()
        self.assertEqual(
            (self.offering.instructor_id, self.offering.lesson_hours),
            (self.owner.id, 45),
        )

    def test_repeat_and_strict_undo_restore_all_original_ids(self):
        _, _, _, before = state.capture(organization=self.org)
        self.apply()
        again = self.run_repair()
        self.assertEqual(again["already_present"], 1)
        self.assertEqual(JournalShare.objects.count(), 1)
        dry = self.run_repair(undo=True)
        self.run_repair(undo=True, apply=True, expected_baseline=dry["baseline"])
        _, _, _, after = state.capture(organization=self.org)
        self.assertEqual(before, after)
        self.assertEqual(set(Lesson.objects.values_list("pk", flat=True)), {self.lesson.pk})
        self.assertEqual(set(LessonMark.objects.values_list("pk", flat=True)), {self.mark.pk})

    def test_changed_cell_baseline_and_undo_drift_refuse(self):
        dry = self.run_repair()
        LessonMark.objects.filter(pk=self.mark.pk).update(score=8)
        with self.assertRaisesRegex(RepairError, "baseline_changed"):
            self.run_repair(apply=True, expected_baseline=dry["baseline"])
        self.apply()
        LessonMark.objects.filter(pk=self.mark.pk).update(score=9)
        with self.assertRaisesRegex(RepairError, "undo_receipt_or_live_graph_changed"):
            self.run_repair(undo=True)

    def test_manual_scope_handover_and_owner_restriction_refuse(self):
        share = JournalShare.objects.create(
            organization=self.org,
            offering=self.offering,
            teacher=self.teacher,
            kinds=["lab"],
            source="manual",
        )
        with self.assertRaisesRegex(RepairError, "manual_or_legacy"):
            self.run_repair()
        share.delete()
        owner_share = JournalShare.objects.create(
            organization=self.org,
            offering=self.offering,
            teacher=self.owner,
            kinds=["lecture"],
            source="workload",
        )
        with self.assertRaisesRegex(RepairError, "owner_access_would_change"):
            self.run_repair()
        self.assertFalse(JournalShare.objects.filter(teacher=self.teacher).exists())
        owner_share.delete()
        TeachingHandover.objects.create(
            organization=self.org,
            offering=self.offering,
            from_instructor=self.owner,
            to_instructor=self.teacher,
            performed_by=self.actor,
            reason="Reviewed fixture",
        )
        with self.assertRaisesRegex(RepairError, "handover"):
            self.run_repair()

    def test_source_section_english_group_and_roster_drift_refuse(self):
        assignment = TeacherAssignment.objects.get(teacher=self.teacher, row=self.row)
        assignment.groups_note = "unknown section"
        assignment.save(update_fields=["groups_note"])
        with self.assertRaisesRegex(RepairError, "assignment_or_section"):
            self.run_repair()
        assignment.groups_note = ""
        assignment.save(update_fields=["groups_note"])
        self.stack["group"].settings = {"language": "en"}
        self.stack["group"].save(update_fields=["settings"])
        with self.assertRaisesRegex(RepairError, "physical_group_identity"):
            self.run_repair()
        self.stack["group"].settings = {}
        self.stack["group"].save(update_fields=["settings"])
        StudentAcademicRecord.objects.filter(student_id=self.enrollments[0].student_id).update(is_active=False)
        with self.assertRaisesRegex(RepairError, "student_geometry"):
            self.run_repair()

    def test_accidental_protected_write_rolls_back_grant_and_mark(self):
        original = service.create_reviewed_workload_share

        def corrupt(**kwargs):
            grant = original(**kwargs)
            LessonMark.objects.filter(pk=self.mark.pk).update(score=1)
            return grant

        dry = self.run_repair()
        with (
            patch.object(service, "create_reviewed_workload_share", side_effect=corrupt),
            self.assertRaisesRegex(RepairError, "protected_academic"),
        ):
            self.run_repair(apply=True, expected_baseline=dry["baseline"])
        self.assertFalse(JournalShare.objects.exists())
        self.mark.refresh_from_db()
        self.assertEqual(self.mark.score, 7)

    def test_official_source_full_bytes_teacher_anchor_and_geometry(self):
        self.assertEqual(spec.load_source(self.source, self.source_sha), self.source_sha)
        book = load_workbook(self.source)
        book["Dərs yükü"]["H101"] = 30
        book.save(self.source)
        book.close()
        changed = hashlib.sha256(self.source.read_bytes()).hexdigest()
        with patch.object(spec, "SOURCE_SHA", changed), self.assertRaisesRegex(RepairError, "geometry_changed"):
            spec.load_source(self.source, changed)
        with self.assertRaisesRegex(RepairError, "official_xlsx_changed"):
            spec.load_source(self.source, self.source_sha)

    def test_command_real_rls_readonly_dry_both_pooling_modes_and_required_baseline(
        self,
    ):
        original = service.repair
        for scoped in (False, True):

            def verify(**kwargs):
                self.assertTrue(connection.in_atomic_block)
                with connection.cursor() as cursor:
                    cursor.execute("SHOW transaction_read_only")
                    self.assertEqual(cursor.fetchone()[0], "on")
                    cursor.execute("SELECT current_setting('app.current_org_id',true)")
                    self.assertEqual(cursor.fetchone()[0], str(self.org.id))
                    cursor.execute("SET LOCAL ROLE rls_app_role")
                    cursor.execute("SELECT rolbypassrls,rolsuper FROM pg_roles WHERE rolname=current_user")
                    self.assertEqual(cursor.fetchone(), (False, False))
                return original(**kwargs)

            log = io.StringIO()
            with (
                override_settings(RLS_TRANSACTION_SCOPED=scoped),
                patch(
                    "apps.workload.management.commands.repair_biostat_seminar_share.repair",
                    side_effect=verify,
                ),
            ):
                call_command(
                    "repair_biostat_seminar_share",
                    org=self.org.slug,
                    actor=self.actor.username,
                    file=str(self.source),
                    sha256=self.source_sha,
                    stdout=log,
                )
            self.assertIn("mode=dry_run", log.getvalue())
            self.assertFalse(JournalShare.objects.exists())
            self.assertNotIn(self.teacher.username, log.getvalue())
        with self.assertRaisesMessage(CommandError, "fresh_baseline_required"):
            call_command(
                "repair_biostat_seminar_share",
                org=self.org.slug,
                actor=self.actor.username,
                file=str(self.source),
                sha256=self.source_sha,
                apply=True,
                stdout=io.StringIO(),
            )

    def test_future_enrollment_is_not_automatically_granted(self):
        self.apply()
        student = User.objects.create_user("future-biostat-student")
        activate_member(self.org, student, "student", permissions=["course.view"])
        existing = StudentAcademicRecord.objects.get(student_id=self.enrollments[0].student_id)
        StudentAcademicRecord.objects.create(
            organization=self.org,
            student=student,
            program=existing.program,
            curriculum=existing.curriculum,
            group=self.stack["group"],
            admission_year=2026,
        )
        new = Enrollment.objects.create(organization=self.org, student=student, offering=self.offering)
        forget(self.offering)
        self.assertFalse(journal_scope(self.teacher, self.offering).allows_enrollment(new.id))
        with self.assertRaisesRegex(RepairError, "existing_teacher_share_requires_review"):
            self.run_repair()

    def test_inactive_old_share_ids_and_roster_survive_apply_undo(self):
        old = JournalShare.objects.create(
            organization=self.org,
            offering=self.offering,
            teacher=self.teacher,
            kinds=["lab"],
            source="legacy",
            is_active=False,
        )
        old.enrollments.add(self.enrollments[0])
        original = state.records(JournalShare.objects.filter(pk=old.pk))
        students = state.records(JournalShare.enrollments.through.objects.filter(journalshare_id=old.pk))
        self.apply()
        self.assertNotEqual(JournalShare.objects.get(is_active=True, teacher=self.teacher).pk, old.pk)
        dry = self.run_repair(undo=True)
        self.run_repair(undo=True, apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(original, state.records(JournalShare.objects.filter(pk=old.pk)))
        self.assertEqual(
            students,
            state.records(JournalShare.enrollments.through.objects.filter(journalshare_id=old.pk)),
        )

    def test_manual_deactivation_of_repair_grant_is_not_resurrected(self):
        self.apply()
        JournalShare.objects.filter(teacher=self.teacher, is_active=True).update(is_active=False)
        with self.assertRaisesRegex(RepairError, "deactivated_requires_review"):
            self.run_repair()
        self.assertFalse(JournalShare.objects.filter(teacher=self.teacher, is_active=True).exists())

    def test_command_readonly_enforcement_rolls_back_accidental_write_both_modes(self):
        def bad(**kwargs):
            LessonMark.objects.filter(pk=self.mark.pk).update(score=1)

        for scoped in (False, True):
            with (
                override_settings(RLS_TRANSACTION_SCOPED=scoped),
                patch(
                    "apps.workload.management.commands.repair_biostat_seminar_share.repair",
                    side_effect=bad,
                ),
            ):
                with self.assertRaisesMessage(CommandError, "biostat_share_scope_conflict"):
                    call_command(
                        "repair_biostat_seminar_share",
                        org=self.org.slug,
                        actor=self.actor.username,
                        file=str(self.source),
                        sha256=self.source_sha,
                        stdout=io.StringIO(),
                    )
            self.mark.refresh_from_db()
            self.assertEqual(self.mark.score, 7)

    def test_command_apply_and_undo_real_nonbypass_role_both_modes(self):
        original = service.repair
        for scoped in (False, True):
            dry = self.run_repair()

            def verify(**kwargs):
                with connection.cursor() as cursor:
                    cursor.execute("SHOW transaction_read_only")
                    self.assertEqual(cursor.fetchone()[0], "off")
                    cursor.execute("SET LOCAL ROLE rls_app_role")
                    cursor.execute("SELECT current_setting('app.current_org_id',true)")
                    self.assertEqual(cursor.fetchone()[0], str(self.org.id))
                return original(**kwargs)

            with (
                override_settings(RLS_TRANSACTION_SCOPED=scoped),
                patch(
                    "apps.workload.management.commands.repair_biostat_seminar_share.repair",
                    side_effect=verify,
                ),
            ):
                call_command(
                    "repair_biostat_seminar_share",
                    org=self.org.slug,
                    actor=self.actor.username,
                    file=str(self.source),
                    sha256=self.source_sha,
                    baseline=dry["baseline"],
                    apply=True,
                    stdout=io.StringIO(),
                )
            self.assertEqual(
                JournalShare.objects.filter(is_active=True, teacher=self.teacher).count(),
                1,
            )
            undo = self.run_repair(undo=True)
            with (
                override_settings(RLS_TRANSACTION_SCOPED=scoped),
                patch(
                    "apps.workload.management.commands.repair_biostat_seminar_share.repair",
                    side_effect=verify,
                ),
            ):
                call_command(
                    "repair_biostat_seminar_share",
                    org=self.org.slug,
                    actor=self.actor.username,
                    file=str(self.source),
                    sha256=self.source_sha,
                    baseline=undo["baseline"],
                    apply=True,
                    undo=True,
                    stdout=io.StringIO(),
                )
            self.assertFalse(JournalShare.objects.filter(teacher=self.teacher).exists())

    def test_teacher_gender_suffix_is_normalized_but_literal_surname_is_not_fuzzy(self):
        self.teacher.profile.patronymic = "Parent qızı"
        self.teacher.profile.save(update_fields=["patronymic"])
        self.assertEqual(self.run_repair()["shares_to_create"], 1)
        User.objects.filter(pk=self.teacher.pk).update(last_name="Different literal surname")
        with self.assertRaisesRegex(RepairError, "teacher_account_identity_changed"):
            self.run_repair()

    def test_public_api_invalidates_callers_cached_scope(self):
        from apps.registrar.public import create_reviewed_workload_share

        self.assertFalse(is_direct_editor(self.teacher, self.offering))
        create_reviewed_workload_share(
            offering=self.offering,
            teacher=self.teacher,
            enrollment_ids=[e.id for e in self.enrollments],
            kinds=["seminar"],
            actor=self.actor,
            source_sha256=spec.SOURCE_SHA,
            batch="kindshare-123456abcdef",
        )
        self.assertTrue(is_direct_editor(self.teacher, self.offering))
        self.assertEqual(journal_scope(self.teacher, self.offering).kinds, {"seminar"})

    def test_public_api_foreign_selected_actor_and_foreign_course_refused_under_bypass(self):
        from django.core.exceptions import ValidationError

        from apps.registrar.public import create_reviewed_workload_share, undo_reviewed_workload_share
        from core.rls import bypass_rls

        foreign = make_org("foreign-reviewed-share")
        outsider = User.objects.create_superuser("foreign-reviewed-operator", password="fixture")
        outsider.set_active_organization_context(foreign)
        args = dict(
            offering=self.offering,
            teacher=self.teacher,
            enrollment_ids=[e.id for e in self.enrollments],
            kinds=["seminar"],
            source_sha256=spec.SOURCE_SHA,
            batch="kindshare-123456abcdef",
        )
        with bypass_rls(), self.assertRaisesRegex(ValidationError, "actor_tenant_context_required"):
            create_reviewed_workload_share(actor=outsider, **args)
        self.assertFalse(JournalShare.objects.exists())
        foreign_stack = make_structure(foreign, code="FOREIGN_REVIEW")
        foreign_course = CourseOffering.objects.create(
            organization=foreign,
            subject=foreign_stack["subject"],
            period=foreign_stack["period"],
            group=foreign_stack["group"],
        )
        with bypass_rls(), self.assertRaisesRegex(ValidationError, "actor_tenant_context_required"):
            create_reviewed_workload_share(actor=self.actor, **{**args, "offering": foreign_course})
        # Explicit selected-tenant global-superadmin policy; no membership invented.
        self.assertFalse(self.org.memberships.filter(user=self.actor).exists())
        self.apply()
        share = JournalShare.objects.get(teacher=self.teacher, is_active=True)
        _, _, _, current = state.capture(organization=self.org)
        expected = state.created_share_state(current, share.id)
        with bypass_rls(), self.assertRaisesRegex(ValidationError, "actor_tenant_context_required"):
            undo_reviewed_workload_share(
                share_id=share.id, offering=self.offering, actor=outsider, batch=share.batch, expected_state=expected
            )
        self.assertTrue(JournalShare.objects.filter(pk=share.pk, is_active=True).exists())
        self.actor.set_active_organization_context(foreign)
        with bypass_rls(), self.assertRaisesRegex(ValidationError, "actor_tenant_context_required"):
            create_reviewed_workload_share(actor=self.actor, **args)

    def test_public_api_rejects_live_superuser_revocation_despite_cached_actor(self):
        from django.core.exceptions import ValidationError

        from apps.registrar.public import create_reviewed_workload_share

        User.objects.filter(pk=self.actor.pk).update(is_superuser=False)
        with self.assertRaisesRegex(ValidationError, "active_superadmin_required"):
            create_reviewed_workload_share(
                offering=self.offering,
                teacher=self.teacher,
                enrollment_ids=[e.id for e in self.enrollments],
                kinds=["seminar"],
                actor=self.actor,
                source_sha256=spec.SOURCE_SHA,
                batch="kindshare-123456abcdef",
            )
        self.assertFalse(JournalShare.objects.exists())

    def test_fixed_catalog_course_name_must_still_match_official_source(self):
        type(self.stack["subject"]).objects.filter(pk=self.offering.subject_id).update(name="Different course")
        with self.assertRaisesRegex(RepairError, "official_course_identity_changed"):
            self.run_repair()
        self.assertFalse(JournalShare.objects.exists())

    def test_existing_explicit_other_kind_ownership_cannot_bypass_new_seminar_scope(self):
        from django.core.exceptions import ValidationError

        from apps.registrar.public import create_reviewed_workload_share

        Lesson.objects.create(
            organization=self.org, offering=self.offering, date="2026-10-22", kind="lecture", instructor=self.teacher
        )
        with self.assertRaisesRegex(RepairError, "unreviewed_owned_lesson_kind"):
            self.run_repair()
        with self.assertRaisesRegex(ValidationError, "unreviewed_owned_lesson_kind"):
            create_reviewed_workload_share(
                offering=self.offering,
                teacher=self.teacher,
                enrollment_ids=[e.id for e in self.enrollments],
                kinds=["seminar"],
                actor=self.actor,
                source_sha256=spec.SOURCE_SHA,
                batch="kindshare-123456abcdef",
            )
        self.assertFalse(JournalShare.objects.exists())
