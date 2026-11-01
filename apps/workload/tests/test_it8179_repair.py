"""Migrated PostgreSQL: source-only load deduplication never touches journal history."""

import io
from contextlib import ExitStack
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection, transaction
from django.test import TestCase, TransactionTestCase, override_settings

from apps.organizations.models import OrgUnit
from apps.registrar.models import CourseOffering, Enrollment, Lesson, LessonMark, ScheduleSlot
from apps.workload.models import TeacherAssignment, WorkloadAmendment
from apps.workload.services import it8179_repair as service
from apps.workload.tests import test_scoped_snapshot as fixtures
from apps.workload.tests.factories import make_row


class It8179MergeTests(TestCase):
    setUp = fixtures.ScopedSnapshotTests.setUp

    def prepare(self):
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        self.state = service.state
        fixtures.activate_member(self.org, self.actor, "student")
        self.task.status = "distributed"
        self.task.save()
        self.keep = self.row
        self.other_group = OrgUnit.objects.create(
            organization=self.org, unit_type="group", name="K test", slug="k-test", parent=self.stack["specialty"]
        )
        self.remove = make_row(self.task, self.stack, lecture_total=45, seminar_total=45)
        self.remove.groups.set([self.other_group])
        self.offerings = []
        self.marks = []
        for i, (row, group) in enumerate(((self.keep, self.stack["group"]), (self.remove, self.other_group))):
            type(row).objects.filter(pk=row.pk).update(
                lecture_plan=45, lecture_total=45, seminar_plan=45, seminar_total=45, total_hours=90, credits="7"
            )
            for kind in ("lecture", "seminar"):
                TeacherAssignment.objects.create(
                    organization=self.org, row=row, teacher=self.teacher, activity=kind, hours=45
                )
            offering = CourseOffering.objects.create(
                organization=self.org,
                subject=self.stack["subject"],
                period=self.stack["period"],
                group=group,
                instructor=self.teacher,
                lesson_hours=90,
            )
            enrollment = Enrollment.objects.create(organization=self.org, offering=offering, student=self.actor)
            lesson = Lesson.objects.create(
                organization=self.org, offering=offering, date="2026-10-12", start_time=f"{10+i}:00", kind="lecture"
            )
            mark = LessonMark.objects.create(
                organization=self.org, lesson=lesson, enrollment=enrollment, status="excused", score=None
            )
            ScheduleSlot.all_objects.create(
                organization=self.org,
                offering=offering,
                weekday=i + 1,
                start_time="10:00",
                end_time="11:30",
                kind="lecture",
                created_by=self.teacher,
            )
            self.offerings.append(offering)
            self.marks.append(mark)
        for key, value in {
            "TASK": str(self.task.pk),
            "CHAIR": str(self.task.chair_id),
            "SUBJECT": str(self.stack["subject"].pk),
            "PERIOD": str(self.stack["period"].pk),
            "TEACHER": self.teacher.pk,
            "KEEP": str(self.keep.pk),
            "REMOVE": str(self.remove.pk),
            "IT_GROUP": str(self.stack["group"].pk),
            "K_GROUP": str(self.other_group.pk),
            "OFFERINGS": tuple(str(o.pk) for o in self.offerings),
        }.items():
            self.patches.enter_context(patch.object(self.state, key, value))

    def call(self, **kwargs):
        return service.repair_it8179_load(
            organization=self.org, user=self.actor, source_sha256=self.state.SOURCE_SHA, **kwargs
        )

    def test_dry_apply_repeat_and_exact_identity_undo(self):
        self.prepare()
        before = self.state.capture()
        dry = self.call()
        self.assertEqual(self.state.digest(before), self.state.digest(self.state.capture()))
        self.assertEqual(dry["contact_hours_after"], 90)
        self.call(apply=True, expected_baseline=dry["baseline"])
        after = self.state.capture()
        self.assertEqual(before["academic"], after["academic"])
        self.assertEqual(self.state.protected(before), self.state.protected(after))
        self.assertEqual(self.keep.groups.count(), 2)
        self.assertFalse(type(self.remove).objects.filter(pk=self.remove.pk).exists())
        self.assertEqual(TeacherAssignment.objects.filter(row=self.keep).count(), 2)
        self.assertEqual(self.call()["already_present"], 1)
        undo = self.call(undo=True)
        self.call(undo=True, apply=True, expected_baseline=undo["baseline"])
        restored = self.state.capture()
        self.assertEqual(before["academic"], restored["academic"])
        self.assertEqual(before["workload"], restored["workload"])
        self.assertGreater(WorkloadAmendment.objects.filter(task=self.task).count(), 0)
        with self.assertRaisesRegex(service.MergeError, "undone"):
            self.call()

    def test_failure_after_first_row_write_rolls_back_everything(self):
        self.prepare()
        before = self.state.capture()
        dry = self.call()
        with patch.object(service, "delete_row_amended", side_effect=ValueError("forced deletion failure")):
            with self.assertRaisesRegex(ValueError, "forced"):
                self.call(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(before, self.state.capture())
        self.assertFalse(WorkloadAmendment.objects.filter(task=self.task).exists())

    def test_baseline_guards_full_mark_cell_and_unrelated_row_changes(self):
        self.prepare()
        dry = self.call()
        LessonMark.objects.filter(pk=self.marks[0].pk).update(status="absent")
        with self.assertRaisesRegex(service.MergeError, "baseline_changed"):
            self.call(apply=True, expected_baseline=dry["baseline"])
        with self.assertRaisesRegex(service.MergeError, "baseline_required"):
            self.call(apply=True)

    def test_changed_owner_contact_credit_and_noncontact_hours_refuse(self):
        self.prepare()
        for fields in ({"credits": "8"}, {"seminar_total": 90}, {"union_count": 2}, {"consult_hours": 1}):
            before = self.state.capture()
            with self.subTest(fields=fields):
                with self.captureOnCommitCallbacks(), self.assertRaisesRegex(service.MergeError, "contact_credit"):
                    with transaction.atomic():
                        type(self.keep).objects.filter(pk=self.keep.pk).update(**fields)
                        self.call()
                self.assertEqual(before, self.state.capture())
        TeacherAssignment.objects.filter(row=self.remove, activity="lecture").update(hours=44)
        with self.assertRaisesRegex(service.MergeError, "assignments_changed"):
            self.call()

    def test_prior_amendment_never_deleted_or_bypassed(self):
        self.prepare()
        from apps.workload.services.row_edit import save_row_amended
        from apps.workload.services.scoping import resolve_actor

        save_row_amended(
            task=self.task,
            actor=resolve_actor(self.actor, self.org),
            row=self.remove,
            data={},
            sync_offerings=False,
            amend={"reason": "correction", "note": "Later reviewed source"},
        )
        before = self.state.capture()
        with self.assertRaisesRegex(service.MergeError, "prior_amendment"):
            self.call()
        self.assertEqual(before, self.state.capture())

    def test_review_history_on_removed_row_blocks_and_keep_review_is_preserved(self):
        self.prepare()
        from apps.workload.models import TaskRowReview

        review = TaskRowReview.objects.create(
            organization=self.org, row=self.keep, coordinator=self.actor, status="reviewed"
        )
        before = self.state.capture()
        self.call(apply=True, expected_baseline=self.call()["baseline"])
        after = self.state.capture()
        self.assertEqual(before["workload"]["workload.TaskRowReview"], after["workload"]["workload.TaskRowReview"])
        review.refresh_from_db()
        self.assertEqual(review.row_id, self.keep.pk)
        undo = self.call(undo=True)
        self.call(undo=True, apply=True, expected_baseline=undo["baseline"])

    def test_removed_row_review_blocks_before_any_mutation(self):
        self.prepare()
        from apps.workload.models import TaskRowReview

        TaskRowReview.objects.create(organization=self.org, row=self.remove, coordinator=self.actor, status="reviewed")
        before = self.state.capture()
        with self.assertRaisesRegex(service.MergeError, "history_taskrowreview"):
            self.call()
        self.assertEqual(before, self.state.capture())

    def test_undo_refuses_post_repair_journal_change(self):
        self.prepare()
        self.call(apply=True, expected_baseline=self.call()["baseline"])
        LessonMark.objects.filter(pk=self.marks[0].pk).update(status="absent")
        with self.assertRaisesRegex(service.MergeError, "live_state_changed"):
            self.call(undo=True)

    def test_foreign_scope_and_source_digest_refuse(self):
        self.prepare()
        with self.assertRaisesRegex(service.MergeError, "fixed_active_tenant"):
            service.repair_it8179_load(organization=self.foreign, user=self.actor, source_sha256=self.state.SOURCE_SHA)
        with self.assertRaisesRegex(service.MergeError, "source_required"):
            service.repair_it8179_load(organization=self.org, user=self.actor, source_sha256="0" * 64)


class It8179CommandScopeTests(TransactionTestCase):
    setUp = fixtures.ScopedSnapshotTests.setUp
    prepare = It8179MergeTests.prepare

    def test_command_rls_context_is_in_real_transaction_both_modes(self):
        self.prepare()
        from core.rls import apply_rls_request_context

        original = apply_rls_request_context
        for scoped in (False, True):
            observed = []

            def context(observed=observed, **kwargs):
                self.assertTrue(connection.in_atomic_block)
                original(**kwargs)
                with connection.cursor() as cursor:
                    cursor.execute("SELECT current_setting('app.current_org_id',true)")
                    observed.append(cursor.fetchone())

            with (
                override_settings(RLS_TRANSACTION_SCOPED=scoped),
                patch.object(self.state, "load_source", return_value=self.state.SOURCE_SHA),
                patch("core.rls.apply_rls_request_context", side_effect=context),
            ):
                output = io.StringIO()
                call_command(
                    "repair_it8179_load",
                    org=self.org.slug,
                    actor=self.actor.username,
                    file="pinned.docx",
                    sha256=self.state.SOURCE_SHA,
                    stdout=output,
                )
                self.assertIn("contact_hours_after=90", output.getvalue())
                self.assertEqual(observed, [(str(self.org.pk),)])
                with self.assertRaisesRegex(CommandError, "baseline_required"):
                    call_command(
                        "repair_it8179_load",
                        org=self.org.slug,
                        actor=self.actor.username,
                        file="pinned.docx",
                        sha256=self.state.SOURCE_SHA,
                        apply=True,
                        stdout=io.StringIO(),
                    )


class It8179SourceTests(TestCase):
    def source(self, cells):
        import hashlib
        import tempfile
        import zipfile
        from pathlib import Path
        from xml.sax.saxutils import escape

        ns = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        row = (
            "<w:tr>"
            + "".join(
                "<w:tc>"
                + "".join(f"<w:p><w:r><w:t>{escape(p)}</w:t></w:r></w:p>" for p in cell.split("\n"))
                + "</w:tc>"
                for cell in cells
            )
            + "</w:tr>"
        )
        document = (
            f'<w:document xmlns:w="{ns}"><w:body><w:tbl>' + "<w:tr/>" * 83 + row + "</w:tbl></w:body></w:document>"
        )
        handle = tempfile.NamedTemporaryFile(suffix=".docx")
        self.addCleanup(handle.close)
        with zipfile.ZipFile(handle.name, "w") as archive:
            archive.writestr("word/document.xml", document)
        sha = hashlib.sha256(Path(handle.name).read_bytes()).hexdigest()
        return handle.name, sha

    def cells(self):
        cells = [""] * 26
        for i, value in {
            1: service.state.GROUP_TEXT,
            2: "Kompüterlərdə modelləşdirmə",
            3: "8",
            4: "45",
            5: "45",
            10: "90",
            23: "90",
            25: "90",
        }.items():
            cells[i] = value
        return cells

    def test_full_bytes_and_exact_contact_cells_required(self):
        from pathlib import Path

        path, sha = self.source(self.cells())
        with patch.object(service.state, "SOURCE_SHA", sha):
            self.assertEqual(service.state.load_source(path, sha), sha)
            Path(path).write_bytes(Path(path).read_bytes() + b"changed")
            with self.assertRaisesRegex(service.MergeError, "docx_changed"):
                service.state.load_source(path, sha)
        for index, value in ((5, "45+45"), (6, "1"), (1, "another group"), (10, "180")):
            cells = self.cells()
            cells[index] = value
            path, sha = self.source(cells)
            with self.subTest(index=index), patch.object(service.state, "SOURCE_SHA", sha):
                with self.assertRaisesRegex(service.MergeError, "row84_geometry"):
                    service.state.load_source(path, sha)

    def test_unpinned_source_and_nonprivate_file_refuse(self):
        from pathlib import Path

        path, sha = self.source(self.cells())
        with self.assertRaisesRegex(service.MergeError, "sha_required"):
            service.state.load_source(path, sha)
        Path(path).chmod(0o644)
        with patch.object(service.state, "SOURCE_SHA", sha):
            with self.assertRaisesRegex(service.MergeError, "private_regular"):
                service.state.load_source(path, sha)
