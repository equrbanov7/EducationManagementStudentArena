"""Real fixed-ID repair: academic authors/content stay identical; concurrent load fails closed."""

from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.audit.models import AuditLog
from apps.organizations.models import AcademicPeriod, Organization, OrgUnit
from apps.registrar.models import CourseOffering, Enrollment, Lesson, LessonMark, Subject
from apps.syllabus.models import Syllabus, SyllabusSection, SyllabusVersion
from apps.workload.constants import TaskStatus
from apps.workload.models import TeacherAssignment, TeachingTask, TeachingTaskRow
from apps.workload.services import sbio235_repair as repair
from apps.workload.services import sbio235_state as state
from apps.workload.services.scoping import WorkloadDenied
from core.constants import OrgUnitType
from core.rls import apply_rls_request_context, reset_rls_context

from .factories import TEACHER_PERMS, activate_member, make_org, make_structure

User = get_user_model()


@override_settings(RLS_TRANSACTION_SCOPED=True)
class Sbio235RepairTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("sbio_admin", "admin@x.test", "pw")
        self.teacher = User.objects.create_user(pk=state.TEACHER, username="rena", password="pw")
        self.org = Organization.objects.create(
            pk=state.ORG,
            name="QKU",
            slug="qku",
            owner=self.admin,
            org_type="university",
            status="active",
            is_active=True,
        )
        self.stack = make_structure(self.org, code="SB")
        self.period = AcademicPeriod.objects.create(
            pk=state.PERIOD,
            organization=self.org,
            academic_year=state.YEAR,
            name="Payız2026",
            start_date="2026-09-01",
            end_date="2027-01-31",
            period_type="semester",
            is_current=True,
        )
        self.subject = Subject.objects.create(
            pk=state.SUBJECT, organization=self.org, name="İnformatika", code="QKU-170"
        )
        self.parent = OrgUnit.objects.create(
            pk=state.PARENT,
            organization=self.org,
            name="235 SBİO",
            slug="sbio",
            unit_type=OrgUnitType.GROUP,
            parent=self.stack["specialty"],
        )
        self.groups = [
            OrgUnit.objects.create(
                pk=pk,
                organization=self.org,
                name=f"235 SBİO-{i+1}",
                slug=f"sbio-{i+1}",
                unit_type=OrgUnitType.GROUP,
                parent=self.stack["specialty"],
                settings={"parent_group": state.PARENT},
            )
            for i, pk in enumerate(state.CHILDREN)
        ]
        activate_member(self.org, self.teacher, "teacher", permissions=TEACHER_PERMS, scope_unit=self.stack["chair"])
        self.task = TeachingTask.objects.create(
            pk=state.TASK,
            organization=self.org,
            chair=self.stack["chair"],
            academic_year=state.YEAR,
            status=TaskStatus.AMENDED,
        )
        self.rows = []
        self.offers = []
        self.marks = []
        for i, (pk, m, s) in enumerate([(state.ANCHOR, 30, 30), (state.DUPLICATE, 33, 12)]):
            row = TeachingTaskRow.objects.create(
                pk=pk,
                organization=self.org,
                task=self.task,
                period=self.period,
                subject=self.subject,
                season="fall",
                lecture_plan=m,
                lecture_total=m,
                seminar_plan=15 if i == 0 else s,
                seminar_total=s,
                total_hours=m + s,
                union_count=1,
                subgroup_count=2 if i == 0 else 1,
            )
            row.groups.set([self.groups[i]])
            self.rows.append(row)
            for act, h in [("lecture", m), ("seminar", s)]:
                TeacherAssignment.objects.create(
                    organization=self.org, row=row, teacher=self.teacher, activity=act, hours=h
                )
            o = CourseOffering.objects.create(
                pk=state.OFFERINGS[i],
                organization=self.org,
                subject=self.subject,
                period=self.period,
                group=self.groups[i],
                instructor=self.teacher,
                lesson_hours=45,
            )
            self.offers.append(o)
            student = User.objects.create_user(f"student{i}", password="pw")
            activate_member(self.org, student, "student", permissions=["grade.view"], scope_unit=self.groups[i])
            en = Enrollment.objects.create(organization=self.org, student=student, offering=o)
            lesson = Lesson.objects.create(
                organization=self.org,
                offering=o,
                date="2026-10-20",
                kind="seminar",
                hours=2,
                instructor=self.teacher if i else None,
                created_by=self.admin,
                topic="source topic",
            )
            self.marks.append(
                LessonMark.objects.create(
                    organization=self.org,
                    lesson=lesson,
                    enrollment=en,
                    score=9,
                    entered_by=self.admin,
                    status="present",
                )
            )
            sy = Syllabus.objects.create(
                organization=self.org, subject=self.subject, period=self.period, offering=o, author=self.teacher
            )
            v = SyllabusVersion.objects.create(
                organization=self.org, syllabus=sy, plan_hours={"lecture": 30, "seminar": 15}
            )
            SyllabusSection.objects.create(
                organization=self.org, version=v, section_id="week", data={"rows": [{"topic": "old"}]}
            )
        # Başqa hazır load sətri üçün açılış YOXDUR: bounded confirm onu yaratmamalıdır.
        self.unrelated = TeachingTaskRow.objects.create(
            organization=self.org,
            task=self.task,
            subject=self.stack["subject"],
            period=self.period,
            season="fall",
            lecture_total=10,
            lecture_plan=10,
            total_hours=10,
        )
        self.unrelated.groups.set([self.stack["group"]])
        TeacherAssignment.objects.create(
            organization=self.org, row=self.unrelated, teacher=self.teacher, activity="lecture", hours=10
        )
        apply_rls_request_context(user_id=self.admin.pk, org_id=self.org.pk, bypass=False)

    def tearDown(self):
        reset_rls_context()

    def run_repair(self, **kw):
        args = dict(organization=self.org, user=self.admin, source_sha256=state.SOURCE_SHA)
        args.update(kw)
        return repair.run(**args)

    def apply(self):
        before = repair.baseline(self.task)
        return self.run_repair(apply=True, expected_baseline=before)

    def test_dry_apply_repeat_undo_preserve_full_academic_fingerprint(self):
        before = state.footprint()
        initial = repair.baseline(self.task)
        preview = self.run_repair()
        self.assertEqual(preview["merged_rows"], 1)
        self.assertEqual(initial, repair.baseline(self.task))
        self.assertFalse(AuditLog.objects.filter(resource_type=state.RESOURCE).exists())
        result = self.apply()
        self.assertEqual(state.footprint(), before)
        self.assertFalse(TeachingTaskRow.objects.filter(pk=state.DUPLICATE).exists())
        self.assertEqual(
            {str(pk) for pk in self.rows[0].groups.values_list("pk", flat=True)}, {str(g.pk) for g in self.groups}
        )
        self.assertEqual(CourseOffering.objects.count(), 2)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.AMENDED)
        self.assertIsNone(self.task.distributed_at)
        again = self.run_repair(apply=True, expected_baseline=initial)
        self.assertEqual(again["already_applied"], 1)
        out = self.run_repair(apply=True, undo=result["batch"], expected_baseline=repair.baseline(self.task))
        self.assertEqual(out["restored_rows"], 1)
        self.assertEqual(state.footprint(), before)
        self.assertEqual(TeachingTaskRow.objects.get(pk=state.DUPLICATE).lecture_total, 33)
        again = self.run_repair(apply=True, undo=result["batch"], expected_baseline=repair.baseline(self.task))
        self.assertEqual(again["already_undone"], 1)

    def test_baseline_and_wrong_source_fail_without_writes(self):
        for kw in [{"expected_baseline": "0" * 64, "apply": True}, {"source_sha256": "0" * 64}, {"apply": True}]:
            with self.assertRaises(state.RepairError):
                self.run_repair(**kw)
        self.assertTrue(TeachingTaskRow.objects.filter(pk=state.DUPLICATE).exists())

    def test_distributed_task_opens_amendment_preserving_distribution_header(self):
        from django.utils import timezone

        stamped = timezone.now()
        TeachingTask.objects.filter(pk=self.task.pk).update(
            status=TaskStatus.DISTRIBUTED, distributed_at=stamped, distributed_by=self.admin, revision=3
        )
        self.task.refresh_from_db()
        initial = repair.baseline(self.task)
        academic = state.footprint()
        self.run_repair()
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.DISTRIBUTED)
        self.assertEqual(repair.baseline(self.task), initial)
        result = self.run_repair(apply=True, expected_baseline=initial)
        self.task.refresh_from_db()
        self.assertEqual(self.task.status, TaskStatus.AMENDED)
        self.assertEqual(self.task.distributed_at, stamped)
        self.assertEqual(self.task.distributed_by_id, self.admin.pk)
        self.assertEqual(self.task.revision, 3)
        self.assertEqual(state.footprint(), academic)
        self.assertEqual(self.run_repair()["already_applied"], 1)
        self.run_repair(apply=True, undo=result["batch"], expected_baseline=repair.baseline(self.task))
        self.assertEqual(state.footprint(), academic)
        self.task.refresh_from_db()
        self.assertEqual(self.task.distributed_at, stamped)
        self.assertEqual(self.task.distributed_by_id, self.admin.pk)
        self.assertEqual(self.task.revision, 3)

    def test_draft_task_is_not_accepted_as_distribution_repair(self):
        TeachingTask.objects.filter(pk=self.task.pk).update(status=TaskStatus.DRAFT)
        with self.assertRaises(WorkloadDenied):
            self.run_repair()
        self.assertTrue(TeachingTaskRow.objects.filter(pk=state.DUPLICATE).exists())

    def test_status_regression_during_sync_rolls_back(self):
        real = repair._sync

        def change_status(*args, **kwargs):
            real(*args, **kwargs)
            TeachingTask.objects.filter(pk=self.task.pk).update(status=TaskStatus.DISTRIBUTED)

        with patch.object(repair, "_sync", side_effect=change_status):
            with self.assertRaisesMessage(state.RepairError, "task_status_mismatch"):
                self.apply()
        self.assertTrue(TeachingTaskRow.objects.filter(pk=state.DUPLICATE).exists())

    def test_wrong_owner_and_child_parent_fail(self):
        CourseOffering.objects.filter(pk=state.OFFERINGS[0]).update(instructor=None)
        with self.assertRaisesMessage(state.RepairError, "offering_mismatch"):
            self.run_repair()
        CourseOffering.objects.filter(pk=state.OFFERINGS[0]).update(instructor=self.teacher)
        OrgUnit.objects.filter(pk=state.CHILDREN[1]).update(settings={"parent_group": "other"})
        with self.assertRaisesMessage(state.RepairError, "group_parent_mismatch"):
            self.run_repair()

    def test_undo_refuses_later_workload_edit_atomically(self):
        result = self.apply()
        TeacherAssignment.objects.filter(row_id=state.ANCHOR, activity="seminar").update(
            groups_note="later authored change"
        )
        with self.assertRaisesMessage(state.RepairError, "undo_workload_changed"):
            self.run_repair(apply=True, undo=result["batch"], expected_baseline=repair.baseline(self.task))
        self.assertFalse(TeachingTaskRow.objects.filter(pk=state.DUPLICATE).exists())

    def test_undo_preserves_marks_written_after_apply(self):
        result = self.apply()
        LessonMark.objects.filter(pk=self.marks[0].pk).update(score=10)
        before = state.footprint()
        self.run_repair(apply=True, undo=result["batch"], expected_baseline=repair.baseline(self.task))
        self.assertEqual(before, state.footprint())

    def test_changed_syllabus_or_mark_during_repair_rolls_back_everything(self):
        real = repair._sync

        def bad(*args, **kwargs):
            result = real(*args, **kwargs)
            LessonMark.objects.filter(pk=self.marks[0].pk).update(score=7)
            return result

        before = repair.baseline(self.task)
        with patch.object(repair, "_sync", side_effect=bad):
            with self.assertRaisesMessage(state.RepairError, "academic_fingerprint_changed"):
                self.apply()
        self.assertEqual(before, repair.baseline(self.task))
        self.marks[0].refresh_from_db()
        self.assertEqual(self.marks[0].score, 9)

    def test_other_offering_or_workload_mutation_rolls_back(self):
        real = repair._sync

        def bad(*args, **kwargs):
            result = real(*args, **kwargs)
            TeachingTaskRow.objects.filter(pk=self.unrelated.pk).update(note="outside")
            return result

        with patch.object(repair, "_sync", side_effect=bad):
            with self.assertRaisesMessage(state.RepairError, "outside_scope_changed"):
                self.apply()
        self.unrelated.refresh_from_db()
        self.assertEqual(self.unrelated.note, "")

    def test_non_superadmin_and_foreign_tenant_are_denied(self):
        with self.assertRaisesMessage(state.RepairError, "active_superadmin_required"):
            self.run_repair(user=self.teacher)
        other = make_org("other-sbio")
        with self.assertRaisesMessage(state.RepairError, "source_or_tenant_mismatch"):
            self.run_repair(organization=other)

    def test_command_scopes_rls_and_outputs_no_identity(self):
        out = StringIO()
        call_command("repair_sbio235_workload", actor=self.admin.username, source_sha256=state.SOURCE_SHA, stdout=out)
        self.assertIn("sbio_repair: mode=dry_run", out.getvalue())
        self.assertNotIn("rena", out.getvalue())
        with self.assertRaisesMessage(CommandError, "tenant_slug_mismatch"):
            call_command(
                "repair_sbio235_workload", org="other", actor=self.admin.username, source_sha256=state.SOURCE_SHA
            )

    def test_real_nonbypass_rls_hides_foreign_rows_and_fixed_command_still_works(self):
        from django.db import connection

        other = make_org("hidden-sbio")
        st = make_structure(other, code="HIDDEN")
        foreign = TeachingTaskRow.objects.create(
            organization=other,
            task=TeachingTask.objects.create(organization=other, chair=st["chair"], academic_year=state.YEAR),
            subject=st["subject"],
        )
        with connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            cursor.execute("ALTER TABLE workload_teachingtaskrow ENABLE ROW LEVEL SECURITY")
            cursor.execute("ALTER TABLE workload_teachingtaskrow FORCE ROW LEVEL SECURITY")
            cursor.execute(
                "CREATE POLICY sbio_test_scope ON workload_teachingtaskrow USING (organization_id::text=current_setting('app.current_org_id',true)) WITH CHECK (organization_id::text=current_setting('app.current_org_id',true))"
            )
            cursor.execute("CREATE ROLE sbio235_test_role NOLOGIN NOBYPASSRLS")
            cursor.execute("GRANT USAGE ON SCHEMA public TO sbio235_test_role")
            cursor.execute("GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO sbio235_test_role")
            cursor.execute("GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO sbio235_test_role")
            cursor.execute("SET LOCAL ROLE sbio235_test_role")
        try:
            apply_rls_request_context(user_id=self.admin.pk, org_id=self.org.pk, bypass=False)
            self.assertFalse(TeachingTaskRow.objects.filter(pk=foreign.pk).exists())
            self.apply()
            self.assertFalse(TeachingTaskRow.objects.filter(pk=state.DUPLICATE).exists())
            self.assertEqual(CourseOffering.objects.filter(organization=self.org).count(), 2)
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE NONE")
            apply_rls_request_context(user_id=self.admin.pk, org_id=self.org.pk, bypass=False)
        self.assertTrue(TeachingTaskRow.objects.filter(pk=foreign.pk).exists())

    def test_unrelated_amendment_review_and_distribution_metadata_are_preserved(self):
        from django.utils import timezone

        from apps.workload.models import TaskRowReview, WorkloadAmendment

        TeachingTask.objects.filter(pk=self.task.pk).update(distributed_at=timezone.now(), distributed_by=self.admin)
        amendment = WorkloadAmendment.objects.create(
            organization=self.org,
            task=self.task,
            target_kind="row",
            target_id=self.unrelated.pk,
            reason="correction",
            note="Unrelated pending change",
            new_values={"pending": True},
        )
        review = TaskRowReview.objects.create(
            organization=self.org,
            row=self.unrelated,
            coordinator=self.admin,
            status="approved",
            comment="Keep original review",
        )
        old_a = state.records(WorkloadAmendment.objects.filter(pk=amendment.pk))
        old_r = state.records(TaskRowReview.objects.filter(pk=review.pk))
        header = state.task_header()
        result = self.apply()
        self.assertEqual(header, state.task_header())
        self.assertEqual(old_a, state.records(WorkloadAmendment.objects.filter(pk=amendment.pk)))
        self.assertEqual(old_r, state.records(TaskRowReview.objects.filter(pk=review.pk)))
        self.run_repair(apply=True, undo=result["batch"], expected_baseline=repair.baseline(self.task))
        self.assertEqual(header, state.task_header())
        self.assertEqual(old_a, state.records(WorkloadAmendment.objects.filter(pk=amendment.pk)))
        self.assertEqual(old_r, state.records(TaskRowReview.objects.filter(pk=review.pk)))

    def test_unrelated_review_mutation_during_apply_rolls_back(self):
        from apps.workload.models import TaskRowReview

        review = TaskRowReview.objects.create(
            organization=self.org,
            row=self.unrelated,
            coordinator=self.admin,
            status="approved",
            comment="Original authored review",
        )
        real = repair._sync

        def bad(*args, **kwargs):
            real(*args, **kwargs)
            TaskRowReview.objects.filter(pk=review.pk).update(comment="tampered")

        with patch.object(repair, "_sync", side_effect=bad):
            with self.assertRaisesMessage(state.RepairError, "workflow_history_changed"):
                self.apply()
        review.refresh_from_db()
        self.assertEqual(review.comment, "Original authored review")
