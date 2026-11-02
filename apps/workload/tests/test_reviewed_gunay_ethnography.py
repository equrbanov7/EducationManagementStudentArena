"""Real PostgreSQL preservation, identity, stale guards and exact-PK rollback."""

import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.workload.services import reviewed_gunay_ethnography_repair as repair
from apps.workload.services import reviewed_gunay_ethnography_spec as spec
from apps.workload.services import reviewed_gunay_ethnography_state as state
from apps.workload.services.reviewed_leyla_catalog_graph import RepairError, digest

from .factories import TEACHER_PERMS, activate_member, make_org, make_row, make_structure, make_task


class GunayEthnographyTests(TestCase):
    def setUp(self):
        self.org = make_org("gunay-ethno")
        self.actor = self.org.owner
        self.actor.is_superuser = True
        self.actor.save(update_fields=["is_superuser"])
        self.actor.profile.organization = self.org
        self.actor.profile.save(update_fields=["organization"])
        self.stack = make_structure(self.org, code="GUNAY")
        self.teacher = get_user_model().objects.create_user("gunay-ethno-teacher")
        activate_member(self.org, self.teacher, "teacher", permissions=TEACHER_PERMS, scope_unit=self.stack["chair"])
        self.teacher.profile.organization = self.org
        self.teacher.profile.save(update_fields=["organization"])
        self.task = make_task(self.org, self.stack["chair"], status="amended")
        group_model = apps.get_model("organizations.OrgUnit")
        second = group_model.objects.create(
            organization=self.org,
            parent=self.stack["specialty"],
            unit_type="group",
            name="536 TB2",
            slug="ethno-second",
        )
        self.groups = [self.stack["group"], second]
        self.rows = []
        for groups, amounts in ((self.groups, (20, 10)), ([self.groups[0]], (10, 5)), ([self.groups[1]], (10, 5))):
            row = make_row(
                self.task, {**self.stack, "group": groups[0]}, lecture_total=amounts[0], seminar_total=amounts[1]
            )
            row.groups.set(groups)
            type(row).objects.filter(pk=row.pk).update(
                lecture_plan=amounts[0], seminar_plan=amounts[1], total_hours=sum(amounts), credits="4", credits_value=4
            )
            row.refresh_from_db()
            self.rows.append(row)
            for kind, hours in zip(("lecture", "seminar"), amounts):
                apps.get_model("workload.TeacherAssignment").objects.create(
                    organization=self.org,
                    row=row,
                    teacher=self.teacher,
                    activity=kind,
                    hours=hours,
                    note="Keep original ID on undo",
                )
        self.courses = []
        for i, group in enumerate(self.groups):
            course = apps.get_model("registrar.CourseOffering").objects.create(
                organization=self.org,
                subject=self.stack["subject"],
                period=self.stack["period"],
                group=group,
                instructor=self.teacher,
                lesson_hours=30,
            )
            self.courses.append(course)
            student = get_user_model().objects.create_user("ethno-student" + str(i))
            activate_member(self.org, student, "student", permissions=["course.view"])
            enrollment = apps.get_model("registrar.Enrollment").objects.create(
                organization=self.org, offering=course, student=student
            )
            for kind, status, score in (
                ("lecture", "present", 0),
                ("seminar", "absent", None),
                ("seminar", "excused", None),
            ):
                lesson = apps.get_model("registrar.Lesson").objects.create(
                    organization=self.org,
                    offering=course,
                    date=timezone.localdate(),
                    hours=2,
                    kind=kind,
                    instructor=self.teacher,
                )
                apps.get_model("registrar.LessonMark").objects.create(
                    organization=self.org, lesson=lesson, enrollment=enrollment, status=status, score=score
                )
            syllabus = apps.get_model("syllabus.Syllabus").objects.create(
                organization=self.org,
                subject=course.subject,
                offering=course,
                period=course.period,
                author=self.teacher,
            )
            version = apps.get_model("syllabus.SyllabusVersion").objects.create(
                organization=self.org,
                syllabus=syllabus,
                applies_to_period=course.period,
                status="approved",
                approved_by=self.actor,
                approved_at=timezone.now(),
                locked_at=timezone.now(),
                plan_hours={"lecture": 30, "seminar": 15},
            )
            apps.get_model("syllabus.SyllabusSection").objects.create(
                organization=self.org,
                version=version,
                section_id="week",
                data={"rows": [{"topic": "Exact own ethnography source", "lecture": 30, "seminar": 15}]},
            )
            type(syllabus).objects.filter(pk=syllabus.pk).update(current_version=version, approved_version=version)
        row_fields = (
            "subject_id",
            "period_id",
            "task_id",
            "lecture_plan",
            "lecture_total",
            "seminar_plan",
            "seminar_total",
            "total_hours",
            "credits",
            "credits_value",
        )
        assignment_fields = ("row_id", "teacher_id", "activity", "hours", "is_hourly_paid")
        course_fields = ("subject_id", "period_id", "group_id", "instructor_id", "lesson_hours", "is_active")

        def pins(objects, fields):
            return {
                str(obj.pk): {
                    key: (
                        str(getattr(obj, key))
                        if key.endswith("_id")
                        and getattr(obj, key) is not None
                        and key not in {"teacher_id", "instructor_id"}
                        else getattr(obj, key)
                    )
                    for key in fields
                }
                for obj in objects
            }

        assignments = list(apps.get_model("workload.TeacherAssignment").objects.filter(row__in=self.rows))
        removed = [
            str(a.pk)
            for a in assignments
            if (a.row_id == self.rows[0].pk and a.activity == "seminar")
            or (a.row_id != self.rows[0].pk and a.activity == "lecture")
        ]
        self.pin = {
            "organization_id": str(self.org.pk),
            "teacher": self.teacher.pk,
            "chair": str(self.stack["chair"].pk),
            "period_id": str(self.stack["period"].pk),
            "subject": str(self.stack["subject"].pk),
            "source_sha256": "a" * 64,
            "rows": pins(self.rows, row_fields),
            "groups": {str(r.pk): list(map(str, r.groups.values_list("pk", flat=True))) for r in self.rows},
            "assignments": pins(assignments, assignment_fields),
            "courses": pins(self.courses, course_fields),
            "removed": removed,
            "after_hours": {
                str(a.pk): 30 if a.activity == "lecture" else 15 for a in assignments if str(a.pk) not in removed
            },
            "row_after": {
                str(r.pk): {
                    "lecture_plan": 30 if i == 0 else 0,
                    "lecture_total": 30 if i == 0 else 0,
                    "seminar_plan": 0 if i == 0 else 15,
                    "seminar_total": 0 if i == 0 else 15,
                    "total_hours": 30 if i == 0 else 15,
                }
                for i, r in enumerate(self.rows)
            },
        }
        self.patch_pin = patch.object(spec, "PINS", self.pin)
        self.patch_org = patch.object(spec, "ORG", str(self.org.pk))
        self.patch_pin.start()
        self.patch_org.start()
        self.addCleanup(self.patch_pin.stop)
        self.addCleanup(self.patch_org.stop)

    def run_repair(self, **kwargs):
        return repair.run(organization=self.org, actor=self.actor, **kwargs)

    def test_apply_idempotence_full_academic_preservation_and_exact_pk_undo(self):
        before = state.snapshot(self.org)
        dry = self.run_repair()
        self.assertEqual(digest(before), dry["baseline"])
        applied = self.run_repair(apply=True, expected_baseline=dry["baseline"])
        after = state.snapshot(self.org)
        self.assertTrue(after["corrected"])
        self.assertEqual(digest(state.protected(before)), digest(state.protected(after)))
        self.assertEqual([45, 45], sorted(c["lesson_hours"] for c in after["courses"]))
        self.assertEqual(60, sum(a["hours"] for a in after["assignments"]))
        self.assertEqual("already_applied", self.run_repair()["status"])
        undone = self.run_repair(apply=True, expected_baseline=self.run_repair()["baseline"], undo=applied["receipt"])
        self.assertEqual("undone", undone["status"])
        self.assertEqual(digest(before), digest(state.snapshot(self.org)))
        self.assertEqual("already_undone", self.run_repair(undo=applied["receipt"])["status"])

    def test_stale_cell_and_undo_guard(self):
        dry = self.run_repair()
        mark = apps.get_model("registrar.LessonMark").objects.filter(score=0).first()
        type(mark).objects.filter(pk=mark.pk).update(score=1)
        with self.assertRaisesRegex(RepairError, "fresh_baseline"):
            self.run_repair(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(6, apps.get_model("workload.TeacherAssignment").objects.filter(row__in=self.rows).count())

    def test_other_teacher_assignment_and_partial_state_refused(self):
        obj = apps.get_model("workload.TeacherAssignment").objects.filter(row=self.rows[0], activity="lecture").get()
        type(obj).objects.filter(pk=obj.pk).update(hours=19)
        with self.assertRaisesRegex(RepairError, "assignment_identity"):
            self.run_repair()

    def test_non_superadmin_or_wrong_tenant_refused(self):
        with self.assertRaisesRegex(RepairError, "superadmin"):
            repair.run(organization=self.org, actor=self.teacher)
        other = make_org("ethno-other")
        with self.assertRaisesRegex(RepairError, "organization_changed"):
            repair.run(organization=other, actor=self.actor)

    def test_late_failure_rolls_back_all_workload_changes(self):
        dry = self.run_repair()
        original = state.protected
        calls = 0

        def sabotage(value):
            nonlocal calls
            calls += 1
            found = deepcopy(original(value))
            if calls == 2:
                found["tampered"] = True
            return found

        with (
            patch.object(state, "protected", side_effect=sabotage),
            self.assertRaisesRegex(RepairError, "academic_graph_changed"),
        ):
            self.run_repair(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(dry["baseline"], self.run_repair()["baseline"])

    def test_first_apply_undo_and_repeat_native_results_pass_strict_host_parser(self):
        ops = Path(__file__).resolve().parents[3] / "scripts/ops"
        sys.path.insert(0, str(ops))
        loader = importlib.util.spec_from_file_location(
            "gunay_host_baseline_contract", ops / "reviewed_gunay_ethnography.py"
        )
        host = importlib.util.module_from_spec(loader)
        loader.loader.exec_module(host)

        def parse(value, **kwargs):
            return host.summary(host.PREFIX + json.dumps(value), **kwargs)

        before = state.snapshot(self.org)
        dry = self.run_repair()
        applied = self.run_repair(apply=True, expected_baseline=dry["baseline"])
        parse(applied, apply=True, undo="", baseline=dry["baseline"])
        self.assertEqual(applied["baseline"], dry["baseline"])
        after = state.snapshot(self.org)
        repeat = self.run_repair()
        parse(repeat, apply=False, undo="")
        self.assertEqual(repeat["baseline"], digest(after))
        self.assertEqual(repeat["receipt"], applied["receipt"])
        self.assertNotEqual(repeat["baseline"], applied["baseline"])
        audit = apps.get_model("audit.AuditLog").objects.get(
            resource_type=spec.RESOURCE, resource_id=applied["receipt"]
        )
        self.assertEqual(audit.old_values["before_sha256"], digest(before))
        self.assertEqual(audit.new_values["after_sha256"], digest(after))
        self.assertEqual(audit.new_values["protected_sha256"], digest(state.protected(after)))
        self.assertEqual(state.protected(before), state.protected(after))
        undone = self.run_repair(apply=True, expected_baseline=repeat["baseline"], undo=applied["receipt"])
        parse(undone, apply=True, undo=applied["receipt"], baseline=repeat["baseline"])
        self.assertEqual(undone["baseline"], digest(after))
        repeated_undo = self.run_repair(undo=applied["receipt"])
        parse(repeated_undo, apply=False, undo=applied["receipt"])
        self.assertEqual(repeated_undo["baseline"], digest(before))
        self.assertEqual(repeated_undo["receipt"], applied["receipt"])
