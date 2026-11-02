"""PG: release only duplicate ownership, preserve capacities, new marks and exact undo."""

import copy
import datetime as dt
import hashlib
import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase

from ..services import reviewed_elshen_vacancy_repair as repair
from ..services import reviewed_elshen_vacancy_spec as spec
from ..services import reviewed_elshen_vacancy_state as state
from ..services import reviewed_two_catalog_schema as schema
from ..services.sbio235_state import RepairError
from .factories import TEACHER_PERMS, activate_member, make_org, make_structure


class ElshenVacancyTests(TestCase):
    def setUp(self):
        self.org = make_org("elshen-vacancy")
        self.actor = self.org.owner
        self.actor.is_superuser = True
        self.actor.save(update_fields=["is_superuser"])
        self.actor.profile.organization = self.org
        self.actor.profile.save(update_fields=["organization"])
        self.stack = make_structure(self.org, code="ELSH")
        self.teacher = get_user_model().objects.create_user("elsen.emrahov", first_name="Elşən", last_name="Əmrahov")
        self.teacher.profile.organization = self.org
        self.teacher.profile.save(update_fields=["organization"])
        activate_member(self.org, self.teacher, "teacher", permissions=TEACHER_PERMS, scope_unit=self.stack["chair"])
        p = copy.deepcopy(spec.PINS)
        p["organization"] = str(self.org.pk)
        p["teacher"] = self.teacher.pk
        for a in p["assignments"].values():
            a["teacher_id"] = self.teacher.pk
        for c in p["courses"].values():
            c["instructor_id"] = self.teacher.pk
        Unit = apps.get_model("organizations.OrgUnit")
        gids = (
            {g for gs in p["groups"].values() for g in gs}
            | {p["bt"], p["eko"]}
            | {c["group_id"] for c in p["courses"].values()}
        )
        for sid in {r["specialty_id"] for r in p["rows"].values() if r["specialty_id"]}:
            Unit.objects.create(
                id=sid, organization=self.org, parent=self.stack["chair"], unit_type="specialty", name=sid, slug=sid
            )
        for gid in gids:
            Unit.objects.create(
                id=gid, organization=self.org, parent=self.stack["chair"], unit_type="group", name=gid, slug=gid
            )
        for sid in {r["subject_id"] for r in p["rows"].values()} | {c["subject_id"] for c in p["courses"].values()}:
            apps.get_model("registrar.Subject").objects.create(id=sid, organization=self.org, name=sid, code=sid[:8])
        apps.get_model("organizations.AcademicPeriod").objects.create(
            id=p["period"],
            organization=self.org,
            name="Fall",
            academic_year="2026/2027",
            period_type="semester",
            start_date="2026-09-01",
            end_date="2027-01-31",
            is_active=True,
            is_current=True,
        )
        for tid in {r["task_id"] for r in p["rows"].values()}:
            apps.get_model("workload.TeachingTask").objects.create(
                id=tid, organization=self.org, chair=self.stack["chair"], academic_year="2026/2027", status="amended"
            )
        for rid, row in p["rows"].items():
            obj = apps.get_model("workload.TeachingTaskRow").objects.create(organization=self.org, **row)
            obj.groups.add(*p["groups"][rid])
        for a in p["assignments"].values():
            apps.get_model("workload.TeacherAssignment").objects.create(
                organization=self.org, assigned_by=self.actor, note="existing attribution", **a
            )
        for c in p["courses"].values():
            apps.get_model("registrar.CourseOffering").objects.create(organization=self.org, **c)
        self.course = apps.get_model("registrar.CourseOffering").objects.get(pk=p["eko_course"])
        student = get_user_model().objects.create_user("elshen-student")
        activate_member(self.org, student, "student", permissions=["course.view"])
        enr = apps.get_model("registrar.Enrollment").objects.create(
            organization=self.org, offering=self.course, student=student
        )
        for n, status in enumerate(("present", "absent", "excused")):
            lesson = apps.get_model("registrar.Lesson").objects.create(
                organization=self.org,
                offering=self.course,
                date=dt.date(2026, 10, 1 + n),
                hours=2,
                kind="seminar",
                instructor=self.teacher,
            )
            apps.get_model("registrar.LessonMark").objects.create(
                organization=self.org,
                lesson=lesson,
                enrollment=enr,
                status=status,
                score=0 if status == "present" else None,
            )
        self.p = p
        self.addCleanup(patch.stopall)
        patch.object(spec, "PINS", p).start()
        patch.object(spec, "ORG", str(self.org.pk)).start()
        patch.object(spec, "SCHEMA", schema.fingerprints()).start()
        from ..management.commands import repair_reviewed_workload_batch as command

        patch.object(command, "ORG", str(self.org.pk)).start()
        self.manifest = {"format": spec.FORMAT, "organization_id": spec.ORG, "source_sha256": p["source_sha256"]}

    def run_case(self, **kwargs):
        return repair.run(
            manifest=self.manifest,
            manifest_sha="a" * 64,
            lines=[7723],
            organization=self.org,
            user=self.actor,
            **kwargs,
        )

    def test_apply_preserves_new_cells_capacity_links_then_repeat_and_exact_undo(self):
        before = state.snapshot(self.org, self.actor)
        dry = self.run_case()
        applied = self.run_case(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(applied["current_teacher_hours"], 540)
        after = state.snapshot(self.org, self.actor)
        self.assertEqual(state.protected(before), state.protected(after))
        self.assertEqual(sum(r["total_hours"] for r in before["rows"]), sum(r["total_hours"] for r in after["rows"]))
        self.assertEqual(18, sum(a["teacher_id"] is None for a in after["assignments"]))
        self.assertEqual(self.run_case()["already_done"], 1)
        undo = self.run_case(apply=True, undo=applied["batch"], expected_baseline=repair.digest(after))
        self.assertEqual(undo["applied"], 1)
        self.assertEqual(repair.digest(state.snapshot(self.org, self.actor)), repair.digest(before))

    def test_fresh_mark_invalidates_dry_baseline_and_no_partial_release(self):
        dry = self.run_case()
        mark = apps.get_model("registrar.LessonMark").objects.filter(organization=self.org, score=0).get()
        mark.score = 9
        mark.save(update_fields=["score"])
        with self.assertRaisesRegex(RepairError, "fresh_baseline_required"):
            self.run_case(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(
            36,
            apps.get_model("workload.TeacherAssignment")
            .objects.filter(organization=self.org, teacher=self.teacher)
            .count(),
        )

    def test_other_teacher_collision_refuses(self):
        aid = self.p["release"][0]
        apps.get_model("workload.TeacherAssignment").objects.filter(pk=aid).update(teacher_id=self.actor.pk)
        with self.assertRaisesRegex(RepairError, "partial_release"):
            self.run_case()

    def test_actual_command_reads_fixed_manifest_and_bounds_guard(self):
        self.org.slug = "qku"
        self.org.save(update_fields=["slug"])
        with TemporaryDirectory() as folder:
            path = Path(folder) / "manifest.json"
            path.write_text(json.dumps(self.manifest))
            path.chmod(0o600)
            out = StringIO()
            call_command(
                "repair_reviewed_workload_batch",
                manifest=str(path),
                manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                lines=[7723],
                actor=self.actor.username,
                org=self.org.slug,
                stdout=out,
            )
            self.assertIn("current_teacher_hours", out.getvalue())
            apps.get_model("workload.TeacherAssignment").objects.filter(pk=self.p["release"][0]).update(hours=1)
            with self.assertRaises(CommandError):
                call_command(
                    "repair_reviewed_workload_batch",
                    manifest=str(path),
                    manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                    lines=[7723],
                    actor=self.actor.username,
                    org=self.org.slug,
                    stdout=StringIO(),
                )

    def test_inflight_mark_corruption_rolls_back_vacancies_owner_and_group_link(self):
        dry = self.run_case()
        before = state.snapshot(self.org, self.actor)
        original = repair.write

        def corrupt(*args):
            original(*args)
            apps.get_model("registrar.LessonMark").objects.filter(organization=self.org, score=0).update(score=10)

        with patch.object(repair, "write", side_effect=corrupt):
            with self.assertRaisesRegex(RepairError, "full_academic_preservation_failed"):
                self.run_case(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(repair.digest(before), repair.digest(state.snapshot(self.org, self.actor)))

    def test_new_source_partition_assignment_requires_rebased_review_not_silent_erase(self):
        row = apps.get_model("workload.TeachingTaskRow").objects.create(
            organization=self.org,
            task_id=next(iter(self.p["rows"].values()))["task_id"],
            period_id=self.p["period"],
            subject_id=self.course.subject_id,
            lecture_plan=15,
            lecture_total=15,
            total_hours=15,
        )
        apps.get_model("workload.TeacherAssignment").objects.create(
            organization=self.org, row=row, teacher=self.teacher, activity="lecture", hours=15, assigned_by=self.actor
        )
        with self.assertRaisesRegex(RepairError, "leyla_row_budget"):
            self.run_case()
