"""Fixed repeated sections: unchanged per-journal units and no academic/access changes."""

from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.audit.models import AuditLog
from apps.organizations.models import AcademicPeriod, Organization, OrgUnit
from apps.registrar.models import CourseOffering, Enrollment, Lesson, LessonMark, Subject
from apps.workload.models import TeacherAssignment, TeachingTask, TeachingTaskRow
from apps.workload.services import repeated_sections_repair as repair
from apps.workload.services import repeated_sections_spec as spec
from apps.workload.services.repeated_sections_state import BatchState, RepairError, digest
from core.constants import OrgUnitType
from core.rls import apply_rls_request_context, reset_rls_context

from .factories import TEACHER_PERMS, activate_member, make_structure

User = get_user_model()


@override_settings(RLS_TRANSACTION_SCOPED=True)
class RepeatedSectionsTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser("section_admin", "admin@example.test", "pw")
        self.org = Organization.objects.create(
            pk=spec.ORG,
            name="QKU",
            slug="qku",
            owner=self.admin,
            org_type="university",
            status="active",
            is_active=True,
        )
        stack = make_structure(self.org, code="SECTION")
        self.rows, self.offers, self.marks = [], [], []
        for i, item in enumerate(spec.SPECS):
            chair = OrgUnit.objects.create(
                pk=item["chair_id"],
                organization=self.org,
                name=f"Chair{i}",
                slug=f"chair{i}",
                unit_type=OrgUnitType.CHAIR,
                parent=stack["faculty"],
            )
            task = TeachingTask.objects.create(
                pk=item["task_id"],
                organization=self.org,
                chair=chair,
                academic_year=spec.YEAR,
                status="distributed",
            )
            period = AcademicPeriod.objects.create(
                pk=item["period_id"],
                organization=self.org,
                academic_year=spec.YEAR,
                name=item["season"],
                start_date="2026-09-01" if item["season"] == "fall" else "2027-02-01",
                end_date="2027-01-31" if item["season"] == "fall" else "2027-06-30",
                period_type="semester",
            )
            teacher = User.objects.create_user(pk=item["teacher_id"], username=f"section_teacher{i}")
            activate_member(self.org, teacher, "teacher", permissions=TEACHER_PERMS, scope_unit=chair)
            subject = Subject.objects.create(
                pk=item["subject_id"], organization=self.org, name=f"Subject{i}", code=f"S{i}"
            )
            count = item["before_count"]
            row = TeachingTaskRow.objects.create(
                pk=item["id"],
                organization=self.org,
                task=task,
                subject=subject,
                period=period,
                season=item["season"],
                union_count=1,
                subgroup_count=count,
                lecture_plan=15,
                lecture_total=15,
                seminar_plan=15,
                seminar_total=15 * count,
                total_hours=15 * (1 + count),
            )
            self.rows.append(row)
            for activity, aid in item["assignment_ids"].items():
                TeacherAssignment.objects.create(
                    pk=aid,
                    organization=self.org,
                    row=row,
                    teacher=teacher,
                    activity=activity,
                    hours=15 * (count if activity == "seminar" else 1),
                    note="original note",
                )
            for j, gid in enumerate(item["group_ids"]):
                group = OrgUnit.objects.create(
                    pk=gid,
                    organization=self.org,
                    name=f"Group{i}-{j}",
                    slug=f"group{i}-{j}",
                    unit_type=OrgUnitType.GROUP,
                    parent=stack["specialty"],
                )
                row.groups.add(group)
                offering = CourseOffering.objects.create(
                    pk=next(oid for oid, group_id in item["offering_groups"].items() if group_id == gid),
                    organization=self.org,
                    subject=subject,
                    group=group,
                    period=period,
                    instructor=teacher,
                    lesson_hours=30,
                )
                self.offers.append(offering)
                student = User.objects.create_user(f"section_student{i}_{j}")
                activate_member(self.org, student, "student", permissions=["grade.view"], scope_unit=group)
                enrollment = Enrollment.objects.create(organization=self.org, offering=offering, student=student)
                lesson = Lesson.objects.create(
                    organization=self.org,
                    offering=offering,
                    date="2026-10-20" if item["season"] == "fall" else "2027-02-20",
                    kind="seminar",
                    hours=2,
                    instructor=teacher,
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
            period=self.rows[0].period,
            lecture_plan=7,
            lecture_total=7,
            total_hours=7,
        )
        apply_rls_request_context(user_id=self.admin.pk, org_id=self.org.pk, bypass=False)

    def tearDown(self):
        reset_rls_context()

    def state(self, items=None):
        return BatchState(tuple(items or spec.SPECS))

    def baseline(self, items=None):
        state = self.state(items)
        tasks = list(TeachingTask.objects.filter(pk__in={s["task_id"] for s in state.items}).order_by("pk"))
        return digest(state.snapshot(tasks, state.rows()))

    def run_repair(self, items=None, **kwargs):
        state = self.state(items)
        return repair.run(
            organization=self.org,
            user=self.admin,
            source_sha256=state.manifest_sha(),
            row_ids=[s["id"] for s in state.items],
            **kwargs,
        )

    def apply(self, items=None):
        return self.run_repair(items, apply=True, expected_baseline=self.baseline(items))

    def test_dry_apply_repeat_undo_preserve_journal_units_academic_and_access(self):
        before = self.baseline()
        academic = repair.academic_fingerprint(organization_id=spec.ORG, offerings=self.offers)
        access = repair._teacher_access(spec.SPECS)
        ids = list(TeacherAssignment.objects.order_by("pk").values_list("pk", flat=True))
        self.assertEqual(self.run_repair()["changed_rows"], 2)
        self.assertEqual(self.baseline(), before)
        self.assertFalse(AuditLog.objects.filter(resource_type=spec.RESOURCE).exists())
        result = self.apply()
        self.assertEqual(self.run_repair(apply=True, expected_baseline=before)["already_done"], 1)
        for row, item in zip(self.rows, spec.SPECS):
            row.refresh_from_db()
            self.assertEqual(
                (row.lecture_plan, row.seminar_plan, row.subgroup_count, row.seminar_total),
                (15, 15, item["after_count"], 15 * item["after_count"]),
            )
        self.assertEqual(repair.academic_fingerprint(organization_id=spec.ORG, offerings=self.offers), academic)
        self.assertEqual(repair._teacher_access(spec.SPECS), access)
        self.assertEqual(list(TeacherAssignment.objects.order_by("pk").values_list("pk", flat=True)), ids)
        self.assertEqual(list(CourseOffering.objects.values_list("lesson_hours", flat=True)), [30] * 5)
        self.run_repair(undo=result["batch"], apply=True, expected_baseline=self.baseline())
        for row, item in zip(self.rows, spec.SPECS):
            row.refresh_from_db()
            self.assertEqual(row.subgroup_count, item["before_count"])

    def test_subset_does_not_repair_other_allowlisted_task(self):
        self.apply(spec.SPECS[:1])
        self.rows[1].refresh_from_db()
        self.assertEqual(self.rows[1].subgroup_count, spec.SPECS[1]["before_count"])
        self.assertEqual(AuditLog.objects.filter(resource_type=spec.RESOURCE).count(), 1)

    def test_hold_row_not_allowlisted(self):
        with self.assertRaisesRegex(RepairError, "row_not_allowlisted"):
            repair.run(organization=self.org, user=self.admin, source_sha256="0" * 64, row_ids=[str(self.unrelated.pk)])

    def test_group_or_english_alias_never_inferred(self):
        self.rows[0].groups.set([self.rows[1].groups.first()])
        with self.assertRaisesRegex(RepairError, "fixed_group_mismatch"):
            self.apply()

    def test_owner_plan_unit_assignment_and_union_drift_fail_closed(self):
        for field, value, error in [("union_count", 2, "section_shape"), ("seminar_plan", 30, "unit_or_total")]:
            original = getattr(self.rows[0], field)
            setattr(self.rows[0], field, value)
            self.rows[0].save()
            with self.assertRaisesRegex(RepairError, error):
                self.apply()
            setattr(self.rows[0], field, original)
            self.rows[0].save()
        offering = self.offers[0]
        offering.instructor_id = spec.SPECS[1]["teacher_id"]
        offering.save(update_fields=["instructor"])
        with self.assertRaisesRegex(RepairError, "journal_owner"):
            self.apply()

    def test_same_teacher_recreated_assignment_id_rejected(self):
        a = self.rows[0].assignments.get(activity="seminar")
        a.delete()
        TeacherAssignment.objects.create(
            organization=self.org,
            row=self.rows[0],
            teacher_id=spec.SPECS[0]["teacher_id"],
            activity="seminar",
            hours=15,
        )
        with self.assertRaisesRegex(RepairError, "assignment_identity"):
            self.apply()

    def test_live_change_invalidates_baseline(self):
        before = self.baseline()
        self.unrelated.subject_text = "new history"
        self.unrelated.save()
        with self.assertRaisesRegex(RepairError, "baseline_conflict"):
            self.run_repair(apply=True, expected_baseline=before)

    def test_late_failure_rolls_back_prior_row(self):
        before = self.baseline()
        original = repair._edit

        def fail_second(row, item, actor, **kwargs):
            if item["id"] == spec.SPECS[1]["id"]:
                raise RepairError("late_failure")
            return original(row, item, actor, **kwargs)

        with patch.object(repair, "_edit", side_effect=fail_second):
            with self.assertRaisesRegex(RepairError, "late_failure"):
                self.apply()
        self.assertEqual(self.baseline(), before)

    def test_academic_tampering_rolls_back_whole_batch(self):
        before = self.baseline()
        original = repair.sync_task_offerings

        def tamper(*args, **kwargs):
            LessonMark.objects.filter(pk=self.marks[0].pk).update(score=1)
            return original(*args, **kwargs)

        with patch.object(repair, "sync_task_offerings", side_effect=tamper):
            with self.assertRaisesRegex(RepairError, "academic_fingerprint_changed"):
                self.apply()
        self.assertEqual(self.baseline(), before)
        self.marks[0].refresh_from_db()
        self.assertEqual(self.marks[0].score, 9)

    def test_access_tampering_rolls_back(self):
        from apps.organizations.models import Membership

        original = repair.sync_task_offerings
        before = self.baseline()

        def tamper(*args, **kwargs):
            Membership.objects.filter(user_id=spec.SPECS[0]["teacher_id"]).update(is_active=False)
            return original(*args, **kwargs)

        with patch.object(repair, "sync_task_offerings", side_effect=tamper):
            with self.assertRaisesRegex(RepairError, "outside_offering_or_access_changed"):
                self.apply()
        self.assertEqual(self.baseline(), before)

    def test_new_grade_survives_undo_but_workload_drift_blocks_undo(self):
        result = self.apply()
        self.marks[0].score = 10
        self.marks[0].save()
        self.run_repair(undo=result["batch"], apply=True, expected_baseline=self.baseline())
        self.marks[0].refresh_from_db()
        self.assertEqual(self.marks[0].score, 10)
        result = self.apply()
        self.unrelated.subject_text = "later"
        self.unrelated.save()
        with self.assertRaisesRegex(RepairError, "undo_workload_changed"):
            self.run_repair(undo=result["batch"], apply=True, expected_baseline=self.baseline())

    def test_source_hash_and_active_superadmin_required(self):
        with self.assertRaisesRegex(RepairError, "source_or_tenant"):
            repair.run(organization=self.org, user=self.admin, source_sha256="0" * 64)
        self.admin.is_superuser = False
        with self.assertRaisesRegex(RepairError, "active_superadmin"):
            self.run_repair()

    def test_command_scoped_default_dryrun_has_no_identity_output(self):
        out = StringIO()
        before = self.baseline()
        call_command(
            "repair_repeated_sections_workload",
            actor=self.admin.username,
            source_sha256=self.state().manifest_sha(),
            stdout=out,
        )
        self.assertIn("repeated_sections: mode=dry_run", out.getvalue())
        self.assertNotIn("teacher", out.getvalue())
        self.assertEqual(self.baseline(), before)

    def test_real_nonbypass_rls_isolates_foreign_workload(self):
        from django.db import connection

        from .factories import make_org

        other = make_org("section_hidden")
        stack = make_structure(other, code="HIDDENSECTION")
        foreign = TeachingTaskRow.objects.create(
            organization=other,
            subject=stack["subject"],
            task=TeachingTask.objects.create(organization=other, chair=stack["chair"], academic_year=spec.YEAR),
        )
        with connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            cursor.execute("ALTER TABLE workload_teachingtaskrow ENABLE ROW LEVEL SECURITY")
            cursor.execute("ALTER TABLE workload_teachingtaskrow FORCE ROW LEVEL SECURITY")
            cursor.execute(
                "CREATE POLICY sections_scope ON workload_teachingtaskrow USING (organization_id::text=current_setting('app.current_org_id',true)) WITH CHECK (organization_id::text=current_setting('app.current_org_id',true))"
            )
            cursor.execute("CREATE ROLE sections_test_role NOLOGIN NOBYPASSRLS")
            cursor.execute("GRANT USAGE ON SCHEMA public TO sections_test_role")
            cursor.execute("GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO sections_test_role")
            cursor.execute("GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO sections_test_role")
            cursor.execute("SET LOCAL ROLE sections_test_role")
        try:
            apply_rls_request_context(user_id=self.admin.pk, org_id=self.org.pk, bypass=False)
            self.assertFalse(TeachingTaskRow.objects.filter(pk=foreign.pk).exists())
            self.apply()
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL ROLE NONE")
            apply_rls_request_context(user_id=self.admin.pk, org_id=self.org.pk, bypass=False)
        self.assertTrue(TeachingTaskRow.objects.filter(pk=foreign.pk).exists())

    def test_wrong_offering_plan_rejects_before_any_workload_write(self):
        CourseOffering.objects.filter(pk=self.offers[0].pk).update(lesson_hours=45)
        before = self.baseline()
        with self.assertRaisesRegex(RepairError, "journal_owner_or_unit_plan_mismatch"):
            self.apply()
        self.assertEqual(self.baseline(), before)
