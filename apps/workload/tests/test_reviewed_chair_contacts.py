"""Migrated PostgreSQL: bounded mixed-task correction, immutable history and undo."""

import copy
import json
from contextlib import ExitStack
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from apps.accounts.models import UserProfile
from apps.audit.models import AuditLog
from apps.organizations.models import OrgUnit
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
from apps.syllabus.models import Syllabus, SyllabusSection, SyllabusVersion
from apps.workload.models import TeacherAssignment, TeachingTaskRow
from apps.workload.services.reviewed_chair_contacts import engine, spec, state
from apps.workload.services.sbio235_state import RepairError, digest
from apps.workload.tests.factories import TEACHER_PERMS, activate_member, make_org, make_row, make_structure, make_task
from core.rls import reset_rls_context


class ReviewedChairContactsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("contact-reviewed")
        cls.actor = cls.org.owner
        cls.actor.is_superuser = True
        cls.actor.save()
        cls.stack = make_structure(cls.org, code="CONTACT")
        cls.old = get_user_model().objects.create_user("contact-old", first_name="Teacher", last_name="One")
        cls.new = get_user_model().objects.create_user("contact-new", first_name="Teacher", last_name="Two")
        for teacher in (cls.old, cls.new):
            activate_member(cls.org, teacher, "teacher", permissions=TEACHER_PERMS)
            UserProfile.objects.update_or_create(
                user=teacher, defaults={"organization": cls.org, "patronymic": "Father"}
            )
        cls.groups = [
            cls.stack["group"],
            OrgUnit.objects.create(
                organization=cls.org,
                name="CONTACT-237",
                slug="contact-second",
                unit_type="group",
                parent=cls.stack["specialty"],
            ),
        ]
        second_chair = OrgUnit.objects.create(
            organization=cls.org,
            name="Second chair",
            slug="contact-other-chair",
            unit_type="chair",
            parent=cls.stack["faculty"],
        )
        cls.tasks = [make_task(cls.org, chair, status="distributed") for chair in (cls.stack["chair"], second_chair)]
        common = make_row(cls.tasks[0], cls.stack, lecture_total=30, seminar_total=30)
        common.groups.set(cls.groups)
        common.union_count = 2
        common.save()
        cls.rows = [common]
        for group in cls.groups:
            cls.rows.append(make_row(cls.tasks[1], {**cls.stack, "group": group}, lecture_total=0, seminar_total=60))
        cls.assignments = []
        for row in cls.rows:
            for kind in ("lecture", "seminar"):
                hours = getattr(row, kind + "_total")
                if hours:
                    cls.assignments.append(
                        TeacherAssignment.objects.create(
                            organization=cls.org,
                            row=row,
                            teacher=cls.old,
                            activity=kind,
                            hours=hours,
                            note="  historical note  ",
                            groups_note="",
                            assigned_by=cls.old,
                        )
                    )
        cls.offerings, cls.syllabi = [], []
        curriculum = Curriculum.objects.create(organization=cls.org, program=cls.stack["program"], admission_year=2026)
        for index, group in enumerate(cls.groups):
            offering = CourseOffering.objects.create(
                organization=cls.org,
                subject=cls.stack["subject"],
                period=cls.stack["period"],
                group=group,
                instructor=cls.old,
                lesson_hours=90,
            )
            cls.offerings.append(offering)
            student = get_user_model().objects.create_user(f"contact-student-{index}")
            activate_member(cls.org, student, "student", permissions=["grade.view"])
            StudentAcademicRecord.objects.create(
                organization=cls.org,
                student=student,
                group=group,
                program=cls.stack["program"],
                curriculum=curriculum,
                admission_year=2026,
            )
            enrollment = Enrollment.objects.create(
                organization=cls.org, offering=offering, student=student, absence_hours=16
            )
            lesson = Lesson.objects.create(
                organization=cls.org, offering=offering, date="2026-10-21", kind="seminar", hours=2, instructor=cls.old
            )
            LessonMark.objects.create(
                organization=cls.org, lesson=lesson, enrollment=enrollment, status="present", score=9
            )
            syllabus = Syllabus.objects.create(
                organization=cls.org,
                offering=offering,
                subject=cls.stack["subject"],
                period=cls.stack["period"],
                author=cls.old,
                chair_unit=cls.stack["chair"],
            )
            version = SyllabusVersion.objects.create(
                organization=cls.org,
                syllabus=syllabus,
                status="approved",
                locked_at=timezone.now(),
                approved_by=cls.old,
                plan_hours={"lecture": 30, "seminar": 60},
                completion_percent=100,
            )
            Syllabus.objects.filter(pk=syllabus.pk).update(current_version=version, approved_version=version)
            SyllabusSection.objects.create(
                organization=cls.org,
                version=version,
                section_id="info",
                data={"immutable": "teacher content"},
                updated_by=cls.old,
            )
            cls.syllabi.append(syllabus)
        rows = []
        fields = (
            "lecture_plan",
            "lecture_total",
            "seminar_plan",
            "seminar_total",
            "lab_plan",
            "lab_total",
            "total_hours",
            "union_count",
            "subgroup_count",
        )
        for row in cls.rows:
            old_fields = {f: getattr(row, f) for f in fields}
            new_fields = {
                **old_fields,
                "seminar_plan": 0 if row == common else 30,
                "seminar_total": 0 if row == common else 30,
                "total_hours": 30,
            }
            assignments = []
            for assignment in cls.assignments:
                if assignment.row_id != row.pk:
                    continue
                old = {
                    "teacher_id": cls.old.pk,
                    "hours": assignment.hours,
                    "activity": assignment.activity,
                    "is_hourly_paid": False,
                }
                new = (
                    None
                    if row == common and assignment.activity == "seminar"
                    else {**old, "teacher_id": cls.new.pk if row == common else cls.old.pk, "hours": 30}
                )
                assignments.append({"id": str(assignment.pk), "old": old, "new": new})
            rows.append(
                {
                    "id": str(row.pk),
                    "task_id": str(row.task_id),
                    "subject_id": str(row.subject_id),
                    "period_id": str(row.period_id),
                    "groups": list(map(str, row.groups.values_list("pk", flat=True))),
                    "old": old_fields,
                    "new": new_fields,
                    "assignments": assignments,
                }
            )
        cls.case = {
            "rows": rows,
            "plan_hours": {"lecture": 30, "seminar": 30},
            "offerings": {
                str(offering.pk): {
                    "subject_id": str(offering.subject_id),
                    "period_id": str(offering.period_id),
                    "group_id": str(offering.group_id),
                    "old_owner": cls.old.pk,
                    "new_owner": cls.new.pk,
                    "old_hours": 90,
                    "new_hours": 60,
                }
                for offering in cls.offerings
            },
        }

    def setUp(self):
        patches = ExitStack()
        self.addCleanup(patches.close)
        patches.enter_context(patch.object(spec, "ORG", str(self.org.pk)))
        patches.enter_context(patch.object(spec, "CASES", {"test_course": copy.deepcopy(self.case)}))
        patches.enter_context(
            patch.object(
                spec,
                "GROUP_IDENTITIES",
                {
                    str(g.pk): digest([g.name, g.code, str(g.parent_id), g.settings, g.unit_type, g.is_active])
                    for g in self.groups
                },
            )
        )
        patches.enter_context(patch.object(spec, "TASK_CHAIRS", {str(t.pk): str(t.chair_id) for t in self.tasks}))
        patches.enter_context(
            patch.object(
                spec,
                "TEACHER_IDENTITIES",
                {u.pk: digest([u.first_name, u.last_name, "Father"]) for u in (self.old, self.new)},
            )
        )

    def run_repair(self, **kwargs):
        return engine.run(organization=self.org, user=self.actor, **kwargs)

    def apply(self):
        dry = self.run_repair()
        return self.run_repair(apply=True, expected_baseline=dry["baseline"])

    def test_mixed_task_owner_kind_and_plan_correction_preserves_grade_and_content_then_undo(self):
        before, _ = state.snapshot(self.org, state.selection(""))
        dry = self.run_repair()
        self.assertFalse(dry["applied"])
        self.assertEqual(sum(i["derived_barred_changes"] for i in dry["impact"].values()), 2)
        self.assertEqual(AuditLog.objects.filter(resource_type=state.RESOURCE).count(), 0)
        applied = self.apply()
        for offering in self.offerings:
            offering.refresh_from_db()
            self.assertEqual((offering.instructor_id, offering.lesson_hours), (self.new.pk, 60))
            shares = JournalShare.objects.filter(offering=offering, source="workload", is_active=True)
            self.assertEqual(
                {s.teacher_id: s.kinds for s in shares}, {self.old.pk: ["seminar"], self.new.pk: ["lecture"]}
            )
        after, _ = state.snapshot(self.org, state.selection(""))
        self.assertEqual(before["protected"], after["protected"])
        self.assertEqual([s["author_id"] for s in after["syllabi"]], [self.old.pk] * 2)
        self.assertEqual(len(after["assignments"]), len(before["assignments"]) - 1)
        self.assertEqual(self.run_repair(apply=True)["status"], "already_correct")
        undo = self.run_repair(undo=applied["receipt"])
        self.run_repair(undo=applied["receipt"], apply=True, expected_baseline=undo["baseline"])
        restored, _ = state.snapshot(self.org, state.selection(""))
        self.assertEqual(restored["assignments"], before["assignments"])
        self.assertEqual(restored["shares"], before["shares"])
        for name in ("offerings", "syllabi", "versions", "protected"):
            if name == "offerings":
                for old, new in zip(before[name], restored[name]):
                    self.assertEqual(
                        {k: v for k, v in old.items() if k != "updated_at"},
                        {k: v for k, v in new.items() if k != "updated_at"},
                    )
            else:
                self.assertEqual(before[name], restored[name])
        self.assertEqual(self.run_repair(undo=applied["receipt"], apply=True)["status"], "already_undone")

    def _single_row_case(self, lecture, seminar_plan, seminar_total, new_seminar, new_teacher):
        # Preserve a filled neighboring journal while exactly exercising the
        # imported per-group plan/aggregate discrepancy of the Tarix source.
        TeachingTaskRow.objects.filter(pk__in=[r.pk for r in self.rows[1:]]).delete()
        row = self.rows[0]
        row.groups.set([self.groups[0]])
        for field, value in {
            "union_count": 1,
            "lecture_plan": lecture,
            "lecture_total": lecture,
            "seminar_plan": seminar_plan,
            "seminar_total": seminar_total,
            "total_hours": lecture + seminar_total,
        }.items():
            setattr(row, field, value)
        row.save()
        assignments = list(TeacherAssignment.objects.filter(row=row))
        for assignment in assignments:
            assignment.hours = lecture if assignment.activity == "lecture" else seminar_total
            assignment.save()
        offering = self.offerings[0]
        offering.lesson_hours = lecture + seminar_plan
        offering.save()
        SyllabusVersion.objects.filter(syllabus=self.syllabi[0]).update(
            plan_hours={"lecture": lecture, "seminar": seminar_plan}
        )
        case = copy.deepcopy(self.case)
        pin = case["rows"][0]
        pin["groups"] = [str(self.groups[0].pk)]
        pin["old"] = {k: getattr(row, k) for k in pin["old"]}
        pin["new"] = {
            **pin["old"],
            "seminar_plan": new_seminar,
            "seminar_total": new_seminar,
            "total_hours": lecture + new_seminar,
        }
        pin["assignments"] = []
        for assignment in assignments:
            old = {
                "activity": assignment.activity,
                "hours": assignment.hours,
                "teacher_id": self.old.pk,
                "is_hourly_paid": False,
            }
            new = {**old}
            if assignment.activity == "seminar":
                new.update(hours=new_seminar, teacher_id=new_teacher.pk, is_hourly_paid=new_teacher != self.old)
            pin["assignments"].append({"id": str(assignment.pk), "old": old, "new": new})
        case["rows"] = [pin]
        case["offerings"] = {
            str(offering.pk): {
                **case["offerings"][str(offering.pk)],
                "old_hours": lecture + seminar_plan,
                "new_hours": lecture + new_seminar,
                "new_owner": self.old.pk,
            }
        }
        case["plan_hours"] = {"lecture": lecture, "seminar": new_seminar}
        return case

    def test_actual_europe_per_group_plan_differs_from_already_correct_assignment(self):
        case = self._single_row_case(30, 60, 30, 30, self.old)
        with patch.object(spec, "CASES", {"test_course": case}):
            before, _ = state.snapshot(self.org, state.selection(""))
            self.apply()
            after, _ = state.snapshot(self.org, state.selection(""))
            self.assertEqual(before["assignments"], after["assignments"])
            self.assertEqual(after["offerings"][0]["lesson_hours"], 60)
            self.assertEqual(CourseOffering.objects.get(pk=self.offerings[1].pk).lesson_hours, 90)

    def test_actual_region_hourly_seminar_reassignment_keeps_lecture_owner(self):
        case = self._single_row_case(60, 90, 90, 30, self.new)
        with patch.object(spec, "CASES", {"test_course": case}):
            self.apply()
            self.offerings[0].refresh_from_db()
            self.assertEqual((self.offerings[0].instructor_id, self.offerings[0].lesson_hours), (self.old.pk, 90))
            assignment = TeacherAssignment.objects.get(row=self.rows[0], activity="seminar")
            self.assertEqual(
                (assignment.teacher_id, assignment.hours, assignment.is_hourly_paid), (self.new.pk, 30, True)
            )

    def test_actual_worker_command_dry_apply_and_summary(self):
        self.org.slug = "qku"
        self.org.save(update_fields=["slug"])
        output = StringIO()
        call_command("repair_reviewed_chair_contacts", actor=self.actor.username, stdout=output)
        dry = json.loads(output.getvalue())
        self.assertEqual(dry["status"], "dry_run")
        output = StringIO()
        call_command(
            "repair_reviewed_chair_contacts",
            actor=self.actor.username,
            apply=True,
            expected_baseline=dry["baseline"],
            safe_summary=True,
            stdout=output,
        )
        self.assertRegex(
            output.getvalue(),
            r"^chair_contacts: status=applied applied=1 baseline=[a-f0-9]{64} receipt=[a-f0-9-]{36} attendance_changes=2 barred_changes=2\n$",
        )
        self.assertNotIn("Teacher", output.getvalue())

    def test_baseline_drift_rejects_without_writes(self):
        dry = self.run_repair()
        LessonMark.objects.filter(lesson__offering=self.offerings[0]).update(score=8)
        with self.assertRaisesMessage(RepairError, "baseline_changed"):
            self.run_repair(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(CourseOffering.objects.get(pk=self.offerings[0].pk).instructor_id, self.old.pk)

    def test_undo_rejects_later_grade_change(self):
        result = self.apply()
        LessonMark.objects.filter(lesson__offering=self.offerings[0]).update(score=8)
        with self.assertRaisesMessage(RepairError, "undo_state_changed"):
            self.run_repair(undo=result["receipt"])

    def test_identity_and_unreviewed_row_fail_closed(self):
        get_user_model().objects.filter(pk=self.new.pk).update(last_name="Changed")
        with self.assertRaisesMessage(RepairError, "source_full_teacher_identity_changed"):
            self.run_repair()
        get_user_model().objects.filter(pk=self.new.pk).update(last_name=self.new.last_name)
        make_row(self.tasks[1], self.stack, lecture_total=1, seminar_total=0)
        with self.assertRaisesMessage(RepairError, "unreviewed_sibling_source_row"):
            self.run_repair()

    def test_new_draft_syllabus_blocks_approved_plan_update(self):
        draft = SyllabusVersion.objects.create(organization=self.org, syllabus=self.syllabi[0], major=2)
        Syllabus.objects.filter(pk=self.syllabi[0].pk).update(current_version=draft)
        with self.assertRaisesMessage(RepairError, "current_approved_version_identity_changed"):
            self.run_repair()

    def test_existing_manual_handover_and_teacher_share_are_never_overwritten(self):
        handover = TeachingHandover.objects.create(
            organization=self.org,
            offering=self.offerings[0],
            from_instructor=self.old,
            to_instructor=self.new,
            performed_by=self.actor,
            reason="Later reviewed decision",
        )
        with self.assertRaisesMessage(RepairError, "manual_handover_requires_separate_review"):
            self.run_repair()
        TeachingHandover.objects.filter(pk=handover.pk).update(reverted_at=timezone.now())
        JournalShare.objects.create(
            organization=self.org, offering=self.offerings[0], teacher=self.old, source="manual", kinds=["seminar"]
        )
        with self.assertRaisesMessage(RepairError, "source_teacher_manual_share_requires_separate_review"):
            self.run_repair()

    def test_limited_automatic_share_requires_separate_review(self):
        share = JournalShare.objects.create(
            organization=self.org, offering=self.offerings[0], teacher=self.old, source="workload", kinds=["seminar"]
        )
        share.enrollments.add(Enrollment.objects.get(offering=self.offerings[0]))
        with self.assertRaisesMessage(RepairError, "limited_workload_share_needs_separate_review"):
            self.run_repair()

    def test_unrelated_manual_enrollment_share_is_preserved(self):
        observer = get_user_model().objects.create_user("contact-observer")
        activate_member(self.org, observer, "teacher", permissions=TEACHER_PERMS)
        share = JournalShare.objects.create(
            organization=self.org, offering=self.offerings[0], teacher=observer, source="manual", kinds=["lab"]
        )
        share.enrollments.add(Enrollment.objects.get(offering=self.offerings[0]))
        before = list(share.enrollments.values_list("pk", flat=True))
        result = self.apply()
        share.refresh_from_db()
        self.assertEqual((share.is_active, share.source, share.kinds), (True, "manual", ["lab"]))
        self.assertEqual(list(share.enrollments.values_list("pk", flat=True)), before)
        dry = self.run_repair(undo=result["receipt"])
        self.run_repair(undo=result["receipt"], apply=True, expected_baseline=dry["baseline"])
        self.assertTrue(JournalShare.objects.filter(pk=share.pk, is_active=True).exists())

    def test_new_explicit_syllabus_override_is_not_overwritten(self):
        Syllabus.objects.filter(pk=self.syllabi[0].pk).update(plan_hours_override={"lecture": 15, "seminar": 60})
        with self.assertRaisesMessage(RepairError, "explicit_syllabus_override_requires_separate_review"):
            self.run_repair()

    def test_forbidden_actor_and_selection(self):
        with self.assertRaisesMessage(RepairError, "active_tenant_superadmin_required"):
            engine.run(organization=self.org, user=self.old)
        with self.assertRaisesMessage(RepairError, "fixed_course_selection_invalid"):
            self.run_repair(selection="arbitrary")

    def test_late_failure_rolls_back_canonical_amendments_and_shares(self):
        before, _ = state.snapshot(self.org, state.selection(""))
        dry = self.run_repair()
        with patch.object(engine, "preserved", side_effect=RepairError("test_late_failure")):
            with self.assertRaisesMessage(RepairError, "test_late_failure"):
                self.run_repair(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(state.snapshot(self.org, state.selection(""))[0], before)
        self.assertEqual(AuditLog.objects.filter(resource_type=state.RESOURCE).count(), 0)


class ChairContactCommandTransactionTests(TransactionTestCase):
    def test_rls_always_uses_real_outer_transaction_and_safe_output_in_both_modes(self):
        org = make_org("qku")
        actor = org.owner
        actor.is_superuser = True
        actor.save()

        def inspect(**kwargs):
            self.assertTrue(connection.in_atomic_block)
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT current_setting('app.current_org_id',true),current_setting('app.bypass_rls',true)"
                )
                self.assertEqual(cursor.fetchone(), (str(org.pk), "off"))
            return {"baseline": "a" * 64, "status": "dry_run", "applied": False, "cases": ["az_onomastics"]}

        with (
            patch.object(spec, "ORG", str(org.pk)),
            patch("apps.workload.management.commands.repair_reviewed_chair_contacts.run", side_effect=inspect),
        ):
            for scoped in (False, True):
                with self.settings(RLS_TRANSACTION_SCOPED=scoped):
                    reset_rls_context(local=False)
                    output = StringIO()
                    call_command("repair_reviewed_chair_contacts", actor=actor.username, stdout=output)
                    self.assertEqual(json.loads(output.getvalue())["status"], "dry_run")
                    self.assertNotIn(actor.username, output.getvalue())
                    summary = StringIO()
                    call_command(
                        "repair_reviewed_chair_contacts", actor=actor.username, safe_summary=True, stdout=summary
                    )
                    self.assertRegex(
                        summary.getvalue(),
                        r"^chair_contacts: status=dry_run applied=0 baseline=[a-f0-9]{64} receipt=none attendance_changes=0 barred_changes=0\n$",
                    )
                    self.assertFalse(connection.in_atomic_block)
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT current_setting('app.current_org_id',true)")
                        self.assertNotEqual(cursor.fetchone()[0], str(org.pk))
