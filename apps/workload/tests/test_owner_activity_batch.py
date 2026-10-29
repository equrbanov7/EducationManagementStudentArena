"""Fixed allowlist owner-activity batches: selection, created IDs, isolation and reversible history."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar.models import CourseOffering, Enrollment, Lesson, LessonMark, Subject
from apps.syllabus.models import Syllabus, SyllabusSection, SyllabusVersion
from apps.workload.models import TeacherAssignment, TeachingTask, TeachingTaskRow
from apps.workload.services import owner_activity_batch as repair
from apps.workload.services import owner_activity_spec as spec
from apps.workload.services import owner_activity_state as state
from core.constants import OrgUnitType
from core.rls import apply_rls_request_context, reset_rls_context

from .factories import TEACHER_PERMS, activate_member, make_structure

User = get_user_model()


class OwnerActivitySelectionTests(SimpleTestCase):
    def test_fixed_allowlist_and_explicit_selection(self):
        self.assertEqual(len(spec.SPECS), 22)
        excluded = {
            "52debb1c-189f-4e93-b34c-56e313c3d457",
            "be8e8251-977c-468d-b7d8-23a5e2196bf5",
            "a9c3d1a1-b225-4e8c-aeac-9ab98e84b0a8",
        }
        self.assertFalse({s["id"] for s in spec.SPECS} & excluded)
        for kwargs in (
            {},
            {"row_ids": ["bad"]},
            {"chair_ids": ["00000000-0000-0000-0000-000000000000"]},
            {"row_ids": [spec.SPECS[0]["id"]] * 2},
        ):
            with self.assertRaises(state.RepairError):
                state.select(**kwargs)
        with self.assertRaises(state.RepairError):
            state.select(row_ids=[spec.SPECS[0]["id"]], chair_ids=[spec.SPECS[0]["chair_id"]])

    def test_chair_selection_only_expands_to_fixed_rows_and_digest_binds_rows(self):
        chair = spec.SPECS[0]["chair_id"]
        scope = state.select(chair_ids=[chair])
        self.assertEqual(scope.row_ids, {s["id"] for s in spec.SPECS if s["chair_id"] == chair})
        self.assertEqual(scope.selection_sha, state.select(row_ids=sorted(scope.row_ids)).selection_sha)
        self.assertNotEqual(scope.selection_sha, state.select(row_ids=[spec.SPECS[0]["id"]]).selection_sha)


@override_settings(RLS_TRANSACTION_SCOPED=True)
class OwnerActivityBatchTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("owneract_admin", "admin@x.test", "pw")
        self.org = Organization.objects.create(
            pk=spec.ORG,
            name="QKU",
            slug="qku",
            owner=self.admin,
            org_type="university",
            status="active",
            is_active=True,
        )
        stack = make_structure(self.org, code="OWNERACT")
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
            activate_member(self.org, teacher, "teacher", permissions=TEACHER_PERMS, scope_unit=None)
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

        syllabus = Syllabus.objects.create(
            organization=self.org,
            subject=self.rows[0].subject,
            period=self.period,
            offering=self.offers[0],
            author=self.offers[0].instructor,
        )
        version = SyllabusVersion.objects.create(
            organization=self.org,
            syllabus=syllabus,
            plan_hours={"lecture": 45},
            status="approved",
            locked_at=timezone.now(),
            approved_at=timezone.now(),
            approved_by=self.admin,
        )
        SyllabusSection.objects.create(
            organization=self.org,
            version=version,
            section_id="week",
            data={"rows": [{"topic": "retain original source"}]},
        )

    def tearDown(self):
        reset_rls_context()

    def scope(self, row_ids=None, chair_ids=()):
        return state.select(
            row_ids=row_ids if row_ids is not None else [s["id"] for s in spec.SPECS], chair_ids=chair_ids
        )

    def run_repair(self, row_ids=None, chair_ids=(), **kwargs):
        return repair.run(
            organization=self.org,
            user=self.admin,
            source_sha256=state.manifest_sha(),
            row_ids=row_ids if row_ids is not None else (() if chair_ids else [s["id"] for s in spec.SPECS]),
            chair_ids=chair_ids,
            **kwargs,
        )

    def baseline(self, row_ids=None, chair_ids=()):
        scope = state.select(chair_ids=chair_ids) if chair_ids else self.scope(row_ids)
        return scope.baseline(scope.snapshot())

    def apply(self, row_ids=None, chair_ids=()):
        return self.run_repair(
            row_ids=row_ids, chair_ids=chair_ids, apply=True, expected_baseline=self.baseline(row_ids, chair_ids)
        )

    def academic(self):
        return repair.academic_fingerprint(organization_id=spec.ORG, offerings=self.offers)

    def test_all22_dry_apply_repeat_undo_preserve_original_ids_and_academic_contents(self):
        original = self.baseline()
        academic = self.academic()
        ids = set(TeacherAssignment.objects.values_list("pk", flat=True))
        self.assertEqual(self.run_repair()["created_assignments"], 22)
        self.assertEqual(self.baseline(), original)
        self.assertFalse(AuditLog.objects.filter(resource_type=spec.RESOURCE).exists())
        result = self.apply()
        self.assertEqual(result["changed_rows"], 22)
        self.assertEqual(self.academic(), academic)
        self.assertTrue(ids <= set(TeacherAssignment.objects.values_list("pk", flat=True)))
        self.assertEqual(self.run_repair(apply=True, expected_baseline=original)["already_done"], 1)
        self.assertEqual(CourseOffering.objects.count(), 22)
        receipt = AuditLog.objects.filter(resource_type=spec.RESOURCE).last().new_values
        self.assertEqual(sum(len(v) for v in receipt["created_assignment_ids"].values()), 22)
        self.run_repair(undo=result["batch"], apply=True, expected_baseline=self.baseline())
        self.assertEqual(set(TeacherAssignment.objects.values_list("pk", flat=True)), ids)
        self.assertEqual(self.academic(), academic)
        self.assertEqual(
            self.run_repair(undo=result["batch"], apply=True, expected_baseline=self.baseline())["already_done"], 1
        )

    def test_explicit_chair_subset_changes_only_its_allowlisted_rows(self):
        chair = spec.SPECS[2]["chair_id"]
        selected = {s["id"] for s in spec.SPECS if s["chair_id"] == chair}
        before = {
            str(r.pk): state.workload_records(TeachingTaskRow.objects.filter(pk=r.pk))[0]
            for r in self.rows
            if str(r.pk) not in selected
        }
        result = self.apply(chair_ids=[chair])
        self.assertEqual(result["changed_rows"], len(selected))
        for rid, old in before.items():
            self.assertEqual(state.workload_records(TeachingTaskRow.objects.filter(pk=rid))[0], old)
        self.run_repair(
            chair_ids=[chair], undo=result["batch"], apply=True, expected_baseline=self.baseline(chair_ids=[chair])
        )

    def test_baseline_cannot_be_reused_for_different_selection(self):
        first = [spec.SPECS[0]["id"]]
        second = [spec.SPECS[1]["id"]]
        with self.assertRaisesRegex(state.RepairError, "baseline_conflict"):
            self.run_repair(row_ids=second, apply=True, expected_baseline=self.baseline(first))
        result = self.apply(row_ids=first)
        with self.assertRaisesRegex(state.RepairError, "receipt_source_or_selection_mismatch"):
            self.run_repair(row_ids=second, undo=result["batch"], apply=True, expected_baseline=self.baseline(second))

    def test_complete_subset_rolls_back_on_one_blocked_owner(self):
        CourseOffering.objects.filter(pk=self.offers[0].pk).update(instructor=self.offers[2].instructor)
        before = self.baseline()
        with self.assertRaisesRegex(state.RepairError, "existing_owner_or_journal_plan_mismatch"):
            self.apply()
        self.assertEqual(self.baseline(), before)

    def test_fresh_plan_group_sector_and_source_guards(self):
        first = [spec.SPECS[0]["id"]]
        old = self.baseline(first)
        self.rows[0].subgroup_count = 2
        self.rows[0].save()
        with self.assertRaisesRegex(state.RepairError, "baseline_conflict"):
            self.run_repair(row_ids=first, apply=True, expected_baseline=old)
        with self.assertRaisesRegex(state.RepairError, "section_shape"):
            self.apply(first)
        self.rows[0].subgroup_count = 1
        self.rows[0].save()
        self.rows[0].groups.set([self.rows[3].groups.get()])
        with self.assertRaisesRegex(state.RepairError, "fixed_physical_group"):
            self.apply(first)
        with self.assertRaisesRegex(state.RepairError, "source_or_tenant"):
            repair.run(organization=self.org, user=self.admin, source_sha256="0" * 64, row_ids=first)

    def test_new_membership_is_blocked_before_assignment_creation(self):
        first = [spec.SPECS[0]["id"]]
        Membership.objects.filter(user_id=spec.SPECS[0]["teacher_id"], organization=self.org).update(
            scope_unit=self.rows[2].task.chair
        )
        before = Membership.objects.count()
        with self.assertRaisesRegex(state.RepairError, "existing_chair_membership_required"):
            self.apply(first)
        self.assertEqual(Membership.objects.count(), before)
        self.assertEqual(TeacherAssignment.objects.filter(row=self.rows[0]).count(), 1)

    def test_mid_batch_exception_rolls_back_new_assignments_and_prior_hours(self):
        before = self.baseline()
        real = repair._edit
        target = sorted(s["id"] for s in spec.SPECS)[2]

        def fail(row, item, actor, **kwargs):
            if item["id"] == target:
                raise state.RepairError("forced_mid_batch_failure")
            return real(row, item, actor, **kwargs)

        with patch.object(repair, "_edit", side_effect=fail):
            with self.assertRaisesRegex(state.RepairError, "forced_mid_batch_failure"):
                self.apply()
        self.assertEqual(self.baseline(), before)

    def test_academic_mutation_causes_whole_subset_rollback(self):
        before = self.baseline()
        real = repair.sync_task_offerings

        def tamper(*args, **kwargs):
            LessonMark.objects.filter(pk=self.marks[0].pk).update(score=1)
            return real(*args, **kwargs)

        with patch.object(repair, "sync_task_offerings", side_effect=tamper):
            with self.assertRaisesRegex(state.RepairError, "academic_fingerprint_changed"):
                self.apply()
        self.assertEqual(self.baseline(), before)
        self.marks[0].refresh_from_db()
        self.assertEqual(self.marks[0].score, 9)

    def test_undo_preserves_later_marks_but_refuses_later_workload(self):
        first = [spec.SPECS[0]["id"]]
        result = self.apply(first)
        self.marks[0].score = 10
        self.marks[0].save()
        self.run_repair(row_ids=first, undo=result["batch"], apply=True, expected_baseline=self.baseline(first))
        self.marks[0].refresh_from_db()
        self.assertEqual(self.marks[0].score, 10)
        result = self.apply(first)
        self.unrelated.subject_text = "later"
        self.unrelated.save()
        with self.assertRaisesRegex(state.RepairError, "undo_workload_changed"):
            self.run_repair(row_ids=first, undo=result["batch"], apply=True, expected_baseline=self.baseline(first))

    def test_undo_refuses_later_created_assignment_metadata_change(self):
        first = [spec.SPECS[0]["id"]]
        result = self.apply(first)
        TeacherAssignment.objects.filter(row=self.rows[0], activity="seminar").update(note="later authored note")
        with self.assertRaisesRegex(state.RepairError, "undo_workload_changed"):
            self.run_repair(row_ids=first, undo=result["batch"], apply=True, expected_baseline=self.baseline(first))

    def test_other_teacher_assignment_and_non_superuser_are_blocked(self):
        TeacherAssignment.objects.filter(row=self.rows[0]).update(teacher=self.offers[2].instructor)
        with self.assertRaisesRegex(state.RepairError, "teacher_or_activity_assignment_mismatch"):
            self.apply([spec.SPECS[0]["id"]])
        self.admin.is_superuser = False
        with self.assertRaisesRegex(state.RepairError, "active_superadmin_required"):
            self.run_repair()

    def test_command_scope_and_output_does_not_include_identity(self):
        from io import StringIO

        from django.core.management import call_command
        from django.core.management.base import CommandError

        out = StringIO()
        first = [spec.SPECS[0]["id"]]
        before = self.baseline(first)
        call_command(
            "repair_owner_activity_batch",
            rows=first[0],
            actor=self.admin.username,
            source_sha256=state.manifest_sha(),
            stdout=out,
        )
        self.assertIn("owner_activity: mode=dry_run", out.getvalue())
        self.assertNotIn("teacher", out.getvalue())
        self.assertEqual(self.baseline(first), before)
        with self.assertRaisesRegex(CommandError, "selection_outside_fixed_allowlist"):
            call_command(
                "repair_owner_activity_batch",
                rows="00000000-0000-0000-0000-000000000000",
                actor=self.admin.username,
                source_sha256=state.manifest_sha(),
            )

    def test_nonbypass_rls_hides_foreign_rows_and_subset_succeeds(self):
        from django.db import connection

        from .factories import make_org

        other = make_org("owneract-hidden")
        stack = make_structure(other, code="OWNERHIDDEN")
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
                "CREATE POLICY owneract_scope ON workload_teachingtaskrow USING (organization_id::text=current_setting('app.current_org_id',true)) WITH CHECK (organization_id::text=current_setting('app.current_org_id',true))"
            )
            cursor.execute("CREATE ROLE owneract_test_role NOLOGIN NOBYPASSRLS")
            cursor.execute("GRANT USAGE ON SCHEMA public TO owneract_test_role")
            cursor.execute("GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO owneract_test_role")
            cursor.execute("GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO owneract_test_role")
            cursor.execute("SET LOCAL ROLE owneract_test_role")
        try:
            apply_rls_request_context(user_id=self.admin.pk, org_id=self.org.pk, bypass=False)
            self.assertFalse(TeachingTaskRow.objects.filter(pk=foreign.pk).exists())
            self.apply([spec.SPECS[0]["id"]])
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE NONE")
            apply_rls_request_context(user_id=self.admin.pk, org_id=self.org.pk, bypass=False)
        self.assertTrue(TeachingTaskRow.objects.filter(pk=foreign.pk).exists())

    def test_role_permission_mutation_rolls_back(self):
        from apps.organizations.models import Role

        real = repair.sync_task_offerings

        def tamper(*args, **kwargs):
            Role.objects.filter(organization=self.org, name="teacher").update(permissions=["*"])
            return real(*args, **kwargs)

        before = Role.objects.get(organization=self.org, name="teacher").permissions
        with patch.object(repair, "sync_task_offerings", side_effect=tamper):
            with self.assertRaisesRegex(state.RepairError, "outside_workload_or_access_changed"):
                self.apply([spec.SPECS[0]["id"]])
        self.assertEqual(Role.objects.get(organization=self.org, name="teacher").permissions, before)

    def test_period_metadata_change_conflicts_with_preview(self):
        from django.utils import timezone

        first = [spec.SPECS[0]["id"]]
        before = self.baseline(first)
        AcademicPeriod.objects.filter(pk=self.period.pk).update(locked_at=timezone.now())
        with self.assertRaisesRegex(state.RepairError, "baseline_conflict"):
            self.run_repair(row_ids=first, apply=True, expected_baseline=before)
