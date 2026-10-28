"""Fixed 12-row batch: canonical reductions/increases, whole-batch rollback and guarded undo."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.audit.models import AuditLog
from apps.organizations.models import AcademicPeriod, Organization, OrgUnit
from apps.registrar.models import CourseOffering, Enrollment, Lesson, LessonMark, Subject
from apps.workload.models import TeacherAssignment, TeachingTask, TeachingTaskRow
from apps.workload.services import balanced_pairs_repair as repair
from apps.workload.services import balanced_pairs_spec as spec
from apps.workload.services import balanced_pairs_state as state
from core.constants import OrgUnitType
from core.rls import apply_rls_request_context, reset_rls_context

from .factories import TEACHER_PERMS, activate_member, make_structure

User = get_user_model()


@override_settings(RLS_TRANSACTION_SCOPED=True)
class BalancedPairsRepairTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("pairs_admin", "admin@x.test", "pw")
        self.org = Organization.objects.create(
            pk=spec.ORG,
            name="QKU",
            slug="qku",
            owner=self.admin,
            org_type="university",
            status="active",
            is_active=True,
        )
        stack = make_structure(self.org, code="PAIR")
        self.period = AcademicPeriod.objects.create(
            pk=spec.SPECS[0]["period_id"],
            organization=self.org,
            academic_year=spec.YEAR,
            name="Payız 2026",
            start_date="2026-09-01",
            end_date="2027-01-31",
            period_type="semester",
        )
        self.rows, self.offers, self.marks = [], [], []
        for i, item in enumerate(spec.SPECS):
            chair, _ = OrgUnit.objects.get_or_create(
                pk=item["chair_id"],
                defaults=dict(
                    organization=self.org,
                    name=f"Chair{i}",
                    slug=f"chair{i}",
                    unit_type=OrgUnitType.CHAIR,
                    parent=stack["faculty"],
                ),
            )
            task, _ = TeachingTask.objects.get_or_create(
                pk=item["task_id"],
                defaults=dict(organization=self.org, chair=chair, academic_year=spec.YEAR, status="distributed"),
            )
            teacher, _ = User.objects.get_or_create(pk=item["teacher_id"], defaults={"username": f"teacher{i}"})
            activate_member(self.org, teacher, "teacher", permissions=TEACHER_PERMS, scope_unit=chair)
            subject, _ = Subject.objects.get_or_create(
                pk=item["subject_id"],
                defaults=dict(organization=self.org, name=f"Subject{i}", code=f"P{i}"),
            )
            group, _ = OrgUnit.objects.get_or_create(
                pk=item["group_ids"][0],
                defaults=dict(
                    organization=self.org,
                    name=f"Group{i}",
                    slug=f"group{i}",
                    unit_type=OrgUnitType.GROUP,
                    parent=stack["specialty"],
                ),
            )
            row = TeachingTaskRow.objects.create(
                pk=item["id"],
                organization=self.org,
                task=task,
                subject=subject,
                period=self.period,
                season="fall",
                union_count=1,
                subgroup_count=1,
                total_hours=sum(item["before"].values()),
                **{a + "_plan": h for a, h in item["before"].items()},
                **{a + "_total": h for a, h in item["before"].items()},
            )
            row.groups.set([group])
            self.rows.append(row)
            for activity, hours in item["before"].items():
                TeacherAssignment.objects.create(
                    organization=self.org, row=row, teacher=teacher, activity=activity, hours=hours, note="keep note"
                )
            offering = CourseOffering.objects.create(
                organization=self.org,
                subject=subject,
                group=group,
                period=self.period,
                instructor=teacher,
                lesson_hours=sum(item["before"].values()),
            )
            self.offers.append(offering)
            student = User.objects.create_user(f"student{i}")
            activate_member(self.org, student, "student", permissions=["grade.view"], scope_unit=group)
            enrollment = Enrollment.objects.create(organization=self.org, offering=offering, student=student)
            lesson = Lesson.objects.create(
                organization=self.org,
                offering=offering,
                date="2026-10-20",
                kind="seminar",
                hours=2,
                instructor=None,
                created_by=self.admin,
            )
            self.marks.append(
                LessonMark.objects.create(
                    organization=self.org,
                    lesson=lesson,
                    enrollment=enrollment,
                    score=9,
                    status="present",
                    entered_by=self.admin,
                )
            )
        self.unrelated = TeachingTaskRow.objects.create(
            organization=self.org,
            task=self.rows[0].task,
            subject=stack["subject"],
            period=self.period,
            lecture_plan=7,
            lecture_total=7,
            total_hours=7,
        )
        apply_rls_request_context(user_id=self.admin.pk, org_id=self.org.pk, bypass=False)

    def tearDown(self):
        reset_rls_context()

    def run_repair(self, **kwargs):
        return repair.run(organization=self.org, user=self.admin, source_sha256=state.manifest_sha(), **kwargs)

    def baseline(self):
        tasks = list(TeachingTask.objects.filter(pk__in={s["task_id"] for s in spec.SPECS}).order_by("pk"))
        return state.digest(state.snapshot(tasks, state.rows()))

    def apply(self):
        return self.run_repair(apply=True, expected_baseline=self.baseline())

    def academic(self):
        return repair.academic_fingerprint(organization_id=spec.ORG, offerings=self.offers)

    def test_all12_dry_apply_repeat_and_undo_preserve_academic_and_assignment_ids(self):
        initial, academic = self.baseline(), self.academic()
        ids = list(TeacherAssignment.objects.order_by("pk").values_list("pk", flat=True))
        self.assertEqual(self.run_repair()["changed_rows"], 12)
        self.assertEqual(self.baseline(), initial)
        self.assertFalse(AuditLog.objects.filter(resource_type=spec.RESOURCE).exists())
        result = self.apply()
        self.assertEqual(self.academic(), academic)
        self.assertEqual(self.run_repair(apply=True, expected_baseline=initial)["already_done"], 1)
        self.assertEqual(list(TeacherAssignment.objects.order_by("pk").values_list("pk", flat=True)), ids)
        self.assertEqual(CourseOffering.objects.count(), 12)
        for row, item in zip(self.rows, spec.SPECS):
            row.refresh_from_db()
            self.assertEqual(row.lecture_total, item["after"]["lecture"])
        self.run_repair(undo=result["batch"], apply=True, expected_baseline=self.baseline())
        self.assertEqual(self.academic(), academic)
        for row, item in zip(self.rows, spec.SPECS):
            row.refresh_from_db()
            self.assertEqual(row.lecture_total, item["before"]["lecture"])

    def test_all_blocked_reasons_reported_and_no_subset_written(self):
        self.rows[0].subgroup_count = 2
        self.rows[0].save()
        TeacherAssignment.objects.filter(row=self.rows[1], activity="lecture").update(teacher=self.admin)
        before = self.baseline()
        with self.assertRaisesRegex(state.RepairError, "blocked_rows=.*section_shape.*other_teacher"):
            self.apply()
        self.assertEqual(self.baseline(), before)

    def test_foreign_group_and_ing_group_are_never_assumed_equivalent(self):
        self.rows[0].groups.set([self.rows[1].groups.get()])
        with self.assertRaisesRegex(state.RepairError, "fixed_group_mismatch"):
            self.apply()

    def test_live_change_conflict_before_any_write(self):
        old = self.baseline()
        self.unrelated.subject_text = "later change"
        self.unrelated.save()
        with self.assertRaisesRegex(state.RepairError, "baseline_conflict"):
            self.run_repair(apply=True, expected_baseline=old)

    def test_academic_mutation_rolls_back_every_workload_row(self):
        before = self.baseline()
        original = repair.sync_task_offerings

        def tamper(*args, **kwargs):
            LessonMark.objects.filter(pk=self.marks[0].pk).update(score=1)
            return original(*args, **kwargs)

        with patch.object(repair, "sync_task_offerings", side_effect=tamper):
            with self.assertRaisesRegex(state.RepairError, "academic_fingerprint_changed"):
                self.apply()
        self.assertEqual(self.baseline(), before)
        self.marks[0].refresh_from_db()
        self.assertEqual(self.marks[0].score, 9)

    def test_mid_batch_failure_rolls_back_preceding_rows(self):
        initial = self.baseline()
        original = repair._edit

        def fail_third(row, item, actor, **kwargs):
            if item["id"] == spec.SPECS[2]["id"]:
                raise state.RepairError("forced_failure")
            return original(row, item, actor, **kwargs)

        with patch.object(repair, "_edit", side_effect=fail_third):
            with self.assertRaisesRegex(state.RepairError, "forced_failure"):
                self.apply()
        self.assertEqual(self.baseline(), initial)

    def test_undo_rejects_later_load_change_but_preserves_new_marks(self):
        result = self.apply()
        self.marks[0].score = 10
        self.marks[0].save()
        self.run_repair(undo=result["batch"], apply=True, expected_baseline=self.baseline())
        self.marks[0].refresh_from_db()
        self.assertEqual(self.marks[0].score, 10)
        result = self.apply()
        self.unrelated.subject_text = "later"
        self.unrelated.save()
        with self.assertRaisesRegex(state.RepairError, "undo_workload_changed"):
            self.run_repair(undo=result["batch"], apply=True, expected_baseline=self.baseline())

    def test_source_tenant_and_superuser_required(self):
        with self.assertRaisesRegex(state.RepairError, "source_or_tenant"):
            repair.run(organization=self.org, user=self.admin, source_sha256="0" * 64)
        self.admin.is_superuser = False
        with self.assertRaisesRegex(state.RepairError, "active_superadmin"):
            self.run_repair()

    def test_nonbypass_rls_preserves_foreign_rows(self):
        from django.db import connection

        from .factories import make_org

        other = make_org("pairs-hidden")
        stack = make_structure(other, code="HIDDENPAIR")
        foreign = TeachingTaskRow.objects.create(
            organization=other,
            task=TeachingTask.objects.create(organization=other, chair=stack["chair"], academic_year=spec.YEAR),
            subject=stack["subject"],
        )
        with connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            cursor.execute("ALTER TABLE workload_teachingtaskrow ENABLE ROW LEVEL SECURITY")
            cursor.execute("ALTER TABLE workload_teachingtaskrow FORCE ROW LEVEL SECURITY")
            cursor.execute(
                "CREATE POLICY pairs_test_scope ON workload_teachingtaskrow USING (organization_id::text=current_setting('app.current_org_id',true)) WITH CHECK (organization_id::text=current_setting('app.current_org_id',true))"
            )
            cursor.execute("CREATE ROLE pairs_test_role NOLOGIN NOBYPASSRLS")
            cursor.execute("GRANT USAGE ON SCHEMA public TO pairs_test_role")
            cursor.execute("GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO pairs_test_role")
            cursor.execute("GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO pairs_test_role")
            cursor.execute("SET LOCAL ROLE pairs_test_role")
        try:
            apply_rls_request_context(user_id=self.admin.pk, org_id=self.org.pk, bypass=False)
            self.assertFalse(TeachingTaskRow.objects.filter(pk=foreign.pk).exists())
            self.apply()
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE NONE")
            apply_rls_request_context(user_id=self.admin.pk, org_id=self.org.pk, bypass=False)
        self.assertTrue(TeachingTaskRow.objects.filter(pk=foreign.pk).exists())

    def test_unrelated_history_and_distributed_metadata_preserved(self):
        from django.utils import timezone

        from apps.workload.models import TaskRowReview, WorkloadAmendment

        task = self.rows[0].task
        TeachingTask.objects.filter(pk=task.pk).update(distributed_by=self.admin, distributed_at=timezone.now())
        review = TaskRowReview.objects.create(
            organization=self.org, row=self.unrelated, coordinator=self.admin, status="approved", comment="keep"
        )
        amendment = WorkloadAmendment.objects.create(
            organization=self.org,
            task=task,
            target_kind="row",
            target_id=self.unrelated.pk,
            reason="correction",
            note="pending",
        )
        old_review = state.records(TaskRowReview.objects.filter(pk=review.pk))
        old_amendment = state.records(WorkloadAmendment.objects.filter(pk=amendment.pk))
        old_meta = state.records(TeachingTask.objects.filter(pk=task.pk))[0]
        self.apply()
        self.assertEqual(old_review, state.records(TaskRowReview.objects.filter(pk=review.pk)))
        self.assertEqual(old_amendment, state.records(WorkloadAmendment.objects.filter(pk=amendment.pk)))
        task.refresh_from_db()
        self.assertEqual(str(task.distributed_at), old_meta["distributed_at"])
        self.assertEqual(task.distributed_by_id, self.admin.pk)
        self.assertEqual(task.status, "amended")

    def test_command_default_dry_run_is_scoped_and_has_no_identity_output(self):
        from io import StringIO

        from django.core.management import call_command
        from django.core.management.base import CommandError

        out = StringIO()
        initial = self.baseline()
        call_command(
            "repair_balanced_workload_pairs", actor=self.admin.username, source_sha256=state.manifest_sha(), stdout=out
        )
        self.assertIn("balanced_pairs: mode=dry_run", out.getvalue())
        self.assertNotIn("teacher", out.getvalue())
        self.assertEqual(self.baseline(), initial)
        with self.assertRaisesRegex(CommandError, "tenant_slug_mismatch"):
            call_command(
                "repair_balanced_workload_pairs",
                org="other",
                actor=self.admin.username,
                source_sha256=state.manifest_sha(),
            )

    def test_period_lock_drift_invalidates_baseline_then_blocks_fresh_apply(self):
        from django.utils import timezone

        before = self.baseline()
        AcademicPeriod.objects.filter(pk=self.period.pk).update(locked_at=timezone.now())
        with self.assertRaisesRegex(state.RepairError, "baseline_conflict"):
            self.run_repair(apply=True, expected_baseline=before)
        with self.assertRaisesRegex(state.RepairError, "period_locked"):
            self.apply()
