"""Real PG: teacher-authoritative522h, all surplus vacancies and LAB history retained."""

import copy
import datetime as dt
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.test import TestCase
from django.utils import timezone

from ..services import reviewed_kamile_load as repair
from ..services import reviewed_kamile_spec as spec
from ..services import reviewed_kamile_state as state
from ..services import reviewed_two_catalog_schema as schema
from ..services.sbio235_state import RepairError
from .factories import TEACHER_PERMS, activate_member, make_org, make_row, make_structure


class KamileSource522Tests(TestCase):
    def setUp(self):
        self.org = make_org("kamile522")
        self.actor = self.org.owner
        self.actor.is_superuser = True
        self.actor.save(update_fields=["is_superuser"])
        self.actor.profile.organization = self.org
        self.actor.profile.save(update_fields=["organization"])
        self.stack = make_structure(self.org, code="KAMIL")
        self.teacher = get_user_model().objects.create_user(
            "kamile.murvetova2", first_name="Kamilə", last_name="Mürvətova"
        )
        self.teacher.profile.organization = self.org
        self.teacher.profile.patronymic = "Habil"
        self.teacher.profile.save(update_fields=["organization", "patronymic"])
        activate_member(self.org, self.teacher, "teacher", permissions=TEACHER_PERMS, scope_unit=self.stack["chair"])

        def rebind(value):
            if isinstance(value, dict):
                return {k: rebind(v) for k, v in value.items()}
            if isinstance(value, list):
                return [rebind(v) for v in value]
            return self.teacher.pk if type(value) is int and value == 8429 else value

        p = rebind(copy.deepcopy(spec.PINS))
        p["organization_id"] = str(self.org.pk)
        Unit = apps.get_model("organizations.OrgUnit")
        for sid in {g["parent_id"] for g in p["groups"].values()}:
            Unit.objects.create(
                id=sid,
                organization=self.org,
                parent=self.stack["chair"],
                unit_type="specialty",
                name="Source specialty" + sid[:4],
                slug="source-" + sid,
            )
        for gid, g in p["groups"].items():
            Unit.objects.create(
                id=gid,
                organization=self.org,
                parent_id=g["parent_id"],
                unit_type="group",
                name=g["name"],
                code=g["code"],
                slug="source-" + gid,
                settings={**g["settings"], "legacy": {"untouched": True}},
            )
        for sid, s in p["subjects"].items():
            apps.get_model("registrar.Subject").objects.create(
                id=sid, organization=self.org, name=s["name"], code=s["code"], ects=5
            )
        Period = apps.get_model("organizations.AcademicPeriod")
        for season, pid in {r["season"]: r["period_id"] for r in p["rows"].values()}.items():
            Period.objects.create(
                id=pid,
                organization=self.org,
                name="Source " + season,
                academic_year=p["year"],
                period_type="semester",
                start_date="2026-09-01" if season == "fall" else "2027-02-01",
                end_date="2027-01-31" if season == "fall" else "2027-07-01",
                is_active=True,
                is_current=season == "fall",
            )
        for t in p["tasks"].values():
            t["chair_id"] = str(self.stack["chair"].pk)
            apps.get_model("workload.TeachingTask").objects.create(organization=self.org, **t)
        for rid, r in p["rows"].items():
            row = apps.get_model("workload.TeachingTaskRow").objects.create(organization=self.org, **r)
            row.groups.add(*p["row_groups"][rid])
        for a in p["assignments_before"].values():
            apps.get_model("workload.TeacherAssignment").objects.create(
                organization=self.org, note="  preserve exact original spacing  ", assigned_by=self.actor, **a
            )
        for cid, c in p["courses"].items():
            course = apps.get_model("registrar.CourseOffering").objects.create(organization=self.org, **c)
            student = get_user_model().objects.create_user("kamile-student-" + cid[:8])
            activate_member(self.org, student, "student", permissions=["course.view"])
            enrollment = apps.get_model("registrar.Enrollment").objects.create(
                organization=self.org, offering=course, student=student
            )
            # Recorded LAB remains LAB even where future teaching assignment becomes seminar.
            for n, status in enumerate(("present", "absent", "excused")):
                lesson = apps.get_model("registrar.Lesson").objects.create(
                    organization=self.org,
                    offering=course,
                    date=dt.date(2026, 10, 1 + n),
                    hours=2,
                    kind="lab",
                    instructor=self.teacher,
                )
                apps.get_model("registrar.LessonMark").objects.create(
                    organization=self.org,
                    lesson=lesson,
                    enrollment=enrollment,
                    status=status,
                    score=0 if status == "present" else None,
                )
        for sid, s in p["syllabi"].items():
            pointer = {k: s[k] for k in ("current_version_id", "approved_version_id")}
            row = {k: v for k, v in s.items() if k not in pointer}
            syl = apps.get_model("syllabus.Syllabus").objects.create(organization=self.org, **row)
            version = apps.get_model("syllabus.SyllabusVersion").objects.create(
                id=pointer["current_version_id"],
                organization=self.org,
                syllabus=syl,
                applies_to_period_id=s["period_id"],
                status="approved",
                approved_by=self.actor,
                approved_at=timezone.now(),
                locked_at=timezone.now(),
                plan_hours={"lecture": 30, "lab": 30},
            )
            apps.get_model("syllabus.SyllabusSection").objects.create(
                organization=self.org,
                version=version,
                section_id="week",
                data={"rows": [{"topic": "Original approved body", "lab": 30}]},
            )
            type(syl).objects.filter(pk=sid).update(**pointer)
        for key, value in {"PINS": p, "ORG": str(self.org.pk), "SCHEMA": schema.fingerprints()}.items():
            patcher = patch.object(spec, key, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def execute(self, **kw):
        return repair.run(
            manifest={"format": spec.FORMAT, "organization_id": spec.ORG, "source_sha256": spec.PINS["source_sha256"]},
            manifest_sha="a" * 64,
            lines=[8429],
            organization=self.org,
            user=self.actor,
            **kw,
        )

    def apply(self):
        return self.execute(apply=True, expected_baseline=self.execute()["baseline"])

    def test_exact_source522_vacancies_all_bodies_grades_and_lab_history_and_undo(self):
        before = state.snapshot(self.org, self.actor)
        result = self.apply()
        after = state.snapshot(self.org, self.actor)
        self.assertEqual(result["current_teacher_hours"], 522)
        self.assertEqual(state.protected(before), state.protected(after))
        Assignment = apps.get_model("workload.TeacherAssignment")
        own = Assignment.objects.filter(teacher=self.teacher)
        self.assertEqual(own.count(), 18)
        self.assertEqual(sum(own.values_list("hours", flat=True)), 522)
        self.assertEqual(sum(own.filter(row__season="fall").values_list("hours", flat=True)), 297)
        self.assertEqual(sum(own.filter(row__season="spring").values_list("hours", flat=True)), 225)
        vacant = Assignment.objects.filter(teacher=None)
        self.assertEqual(vacant.count(), 12)
        self.assertEqual(sum(vacant.values_list("hours", flat=True)), 273)
        self.assertEqual(Assignment.objects.count(), 30)
        self.assertEqual(apps.get_model("registrar.CourseOffering").objects.count(), 13)
        self.assertEqual(apps.get_model("registrar.Lesson").objects.filter(kind="lab").count(), 39)
        self.assertEqual(apps.get_model("registrar.LessonMark").objects.count(), 39)
        self.assertEqual(apps.get_model("workload.TeachingTaskRow").objects.count(), 13)
        from apps.registrar.public import teacher_journal_list

        visible = teacher_journal_list.own_visible_queryset(
            apps.get_model("registrar.CourseOffering").objects.all(), self.teacher, self.org
        )
        self.assertEqual(visible.filter(journal_is_current_load=True).count(), 9)
        self.assertEqual(visible.count(), 13)
        self.assertTrue(visible.get(pk="a71524e7-abae-49ff-89a5-7bece805ffc7").journal_is_current_load)
        self.assertEqual(self.execute()["batch"], result["batch"])
        undo = self.execute(undo=result["batch"])
        self.execute(undo=result["batch"], apply=True, expected_baseline=undo["baseline"])
        self.assertEqual(state.snapshot(self.org, self.actor), before)
        self.assertEqual(self.execute(undo=result["batch"])["current_teacher_hours"], 735)

    def test_stale_qb_change_refuses_without_overwriting_correction(self):
        dry = self.execute()
        mark = apps.get_model("registrar.LessonMark").objects.filter(status="absent").first()
        mark.status = "excused"
        mark.score = None
        mark.save(update_fields=["status", "score"])
        with self.assertRaisesMessage(RepairError, "kamile_fresh_baseline_required"):
            self.execute(apply=True, expected_baseline=dry["baseline"])
        mark.refresh_from_db()
        self.assertEqual(mark.status, "excused")
        self.assertEqual(apps.get_model("workload.TeacherAssignment").objects.filter(teacher=self.teacher).count(), 26)

    def test_other_teacher_allocation_is_not_reassigned_or_deleted(self):
        a = apps.get_model("workload.TeacherAssignment").objects.filter(teacher=self.teacher).first()
        other = get_user_model().objects.create_user("other-kamile-protected")
        a.teacher = other
        a.save(update_fields=["teacher"])
        with self.assertRaisesMessage(RepairError, "kamile_assignment_changed"):
            self.execute()
        a.refresh_from_db()
        self.assertEqual(a.teacher_id, other.pk)

    def test_wrong_sector_and_unexpected_annual_allocation_refuse(self):
        gid = next(iter(spec.PINS["groups"]))
        group = apps.get_model("organizations.OrgUnit").objects.get(pk=gid)
        group.settings = {**group.settings, "sector": "WRONG"}
        group.save(update_fields=["settings"])
        with self.assertRaisesMessage(RepairError, "kamile_group_identity_changed"):
            self.execute()

    def test_post_write_syllabus_corruption_rolls_back_every_vacancy_and_owner(self):
        before = state.snapshot(self.org, self.actor)
        dry = self.execute()
        write = repair.write

        def corrupted(*args):
            write(*args)
            section = apps.get_model("syllabus.SyllabusSection").objects.first()
            section.data = {"wrong": "must roll back"}
            section.save(update_fields=["data"])

        with patch.object(repair, "write", side_effect=corrupted):
            with self.assertRaisesMessage(RepairError, "kamile_full_academic_preservation_failed"):
                self.execute(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(state.snapshot(self.org, self.actor), before)

    def test_real_command_private_manifest_closed_host_summary_and_safe_guard(self):
        import hashlib
        import json

        from ..management.commands import repair_reviewed_workload_batch as command

        self.org.slug = "qku"
        self.org.save(update_fields=["slug"])
        with TemporaryDirectory() as directory:
            path = Path(directory) / "source.json"
            raw = json.dumps(
                {"format": spec.FORMAT, "organization_id": spec.ORG, "source_sha256": spec.PINS["source_sha256"]}
            ).encode()
            path.write_bytes(raw)
            path.chmod(0o600)
            with patch.object(command, "ORG", spec.ORG):
                out = StringIO()
                call_command(
                    "repair_reviewed_workload_batch",
                    actor=self.actor.username,
                    manifest=str(path),
                    manifest_sha256=hashlib.sha256(raw).hexdigest(),
                    lines=[8429],
                    stdout=out,
                )
                self.assertRegex(
                    out.getvalue(), r"^reviewed_source: mode=dry_run( (baseline=[a-f0-9]{64}|[a-z_]+=[0-9]+))+\n$"
                )
                self.assertIn("current_teacher_hours=735", out.getvalue())
                self.assertIn("source_teacher_hours=522", out.getvalue())
                with self.assertRaisesMessage(CommandError, "manifest_sha256_mismatch"):
                    call_command(
                        "repair_reviewed_workload_batch",
                        actor=self.actor.username,
                        manifest=str(path),
                        manifest_sha256="0" * 64,
                        lines=[8429],
                        stdout=StringIO(),
                    )
                group = apps.get_model("organizations.OrgUnit").objects.get(pk=next(iter(spec.PINS["groups"])))
                group.settings = {**group.settings, "sector": "wrong"}
                group.save(update_fields=["settings"])
                with self.assertRaisesMessage(CommandError, "kamile_group_identity_changed"):
                    call_command(
                        "repair_reviewed_workload_batch",
                        actor=self.actor.username,
                        manifest=str(path),
                        manifest_sha256=hashlib.sha256(raw).hexdigest(),
                        lines=[8429],
                        stdout=StringIO(),
                    )

    def test_unexpected_visible_annual_allocation_is_not_blindly_vacated(self):
        task = apps.get_model("workload.TeachingTask").objects.get(pk=next(iter(spec.PINS["tasks"])))
        row = make_row(task, self.stack)
        extra = apps.get_model("workload.TeacherAssignment").objects.create(
            organization=self.org, row=row, teacher=self.teacher, activity="lecture", hours=15
        )
        with self.assertRaisesMessage(RepairError, "kamile_annual_inventory_changed"):
            self.execute()
        extra.refresh_from_db()
        self.assertEqual(extra.teacher_id, self.teacher.pk)
        self.assertEqual(extra.hours, 15)
