"""Real PG: source535 course/load relink, unchanged542cells and reuse of an existing approval."""

import copy
import datetime as dt
from contextlib import ExitStack
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.registrar.models import AssessmentScheme, CourseOffering, Enrollment, Lesson, LessonMark, Subject
from apps.syllabus.public import content_fingerprints, import_migrated_version, syllabus_for_offering
from apps.workload.models import TeacherAssignment, TeachingTask
from apps.workload.services import reviewed_ilahe_subject_repair as repair
from apps.workload.services import reviewed_ilahe_subject_spec as spec
from apps.workload.services import reviewed_ilahe_subject_state as state
from apps.workload.services.reviewed_leyla_catalog_graph import RepairError, bounded, digest, graph, normal
from apps.workload.tests.factories import TEACHER_PERMS, activate_member, make_org, make_row, make_structure, make_task
from core.rls import journal_unlock

User = get_user_model()


class ReviewedIlaheSubjectTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("ilahe-rebind")
        cls.actor = cls.org.owner
        cls.actor.is_superuser = True
        cls.actor.save(update_fields=["is_superuser"])
        cls.teacher = User.objects.create_user("ilahe-fixed-teacher")
        activate_member(cls.org, cls.teacher, "teacher", permissions=TEACHER_PERMS)
        apps.get_model("accounts.UserProfile").objects.filter(user_id__in=[cls.actor.pk, cls.teacher.pk]).update(
            organization=cls.org, access_state="active", is_deleted=False, deleted_at=None, blocked_at=None
        )
        cls.stack = make_structure(cls.org, code="IS")
        cls.old_subject = Subject.objects.create(organization=cls.org, code="IS536", name="Part2 historical")
        cls.new_subject = cls.stack["subject"]
        group2 = apps.get_model("organizations.OrgUnit").objects.create(
            organization=cls.org, name="336T2", slug="ilahe-sibling", unit_type="group", parent=cls.stack["specialty"]
        )
        cls.task = make_task(cls.org, cls.stack["chair"], status="amended")
        cls.rows = [
            make_row(cls.task, cls.stack, lecture_total=0, seminar_total=75),
            make_row(cls.task, cls.stack, lecture_total=0, seminar_total=75),
        ]
        cls.rows[0].subject = cls.old_subject
        cls.rows[0].save(update_fields=["subject"])
        cls.rows[1].groups.set([group2])
        cls.courses, cls.enrs = [], []
        for index, (subject, group, count, lessons) in enumerate(
            ((cls.old_subject, cls.stack["group"], 15, 18), (cls.new_subject, group2, 16, 17))
        ):
            offering = CourseOffering.objects.create(
                organization=cls.org,
                subject=subject,
                group=group,
                period=cls.stack["period"],
                instructor=cls.teacher,
                lesson_hours=75,
            )
            cls.courses.append(offering)
            AssessmentScheme.objects.create(organization=cls.org, offering=offering)
            roster = []
            for student_index in range(count):
                student = User.objects.create_user(f"ilahe-student-{index}-{student_index}")
                activate_member(cls.org, student, "student", permissions=["course.view", "grade.view"])
                roster.append(Enrollment.objects.create(organization=cls.org, offering=offering, student=student))
            cls.enrs.extend(roster)
            marks = []
            for lesson_index in range(lessons):
                lesson = Lesson.objects.create(
                    organization=cls.org,
                    offering=offering,
                    date=dt.date(2026, 9, 1) + dt.timedelta(days=lesson_index),
                    kind="seminar",
                    start_time="15:15:00",
                    hours=2,
                    topic="Keep current actual topic",
                )
                for student_index, enrollment in enumerate(roster):
                    marks.append(
                        LessonMark(
                            organization=cls.org,
                            lesson=lesson,
                            enrollment=enrollment,
                            status="excused" if student_index == 1 else "absent" if student_index == 2 else "present",
                            score=Decimal("0") if student_index == 0 else None,
                        )
                    )
            LessonMark.objects.bulk_create(marks)
            TeacherAssignment.objects.create(
                organization=cls.org, row=cls.rows[index], teacher=cls.teacher, activity="seminar", hours=75
            )
        cls.source, cls.approved = import_migrated_version(
            organization=cls.org,
            subject=cls.new_subject,
            offering=cls.courses[1],
            period=cls.stack["period"],
            author=cls.teacher,
            approved_at=timezone.now(),
            section_data={
                "desc": {"description": "Own exact8668 first part"},
                "week": {"rows": [{"topic": "First part", "practical": 75}]},
            },
        )
        cls.old_fallback, cls.old_version = import_migrated_version(
            organization=cls.org,
            subject=cls.old_subject,
            author=cls.teacher,
            approved_at=timezone.now(),
            section_data={
                "desc": {"description": "Preserve old6117 second part"},
                "week": {"rows": [{"topic": "Second part", "practical": 60}]},
            },
        )
        cls.generic, cls.generic_version = import_migrated_version(
            organization=cls.org,
            subject=cls.new_subject,
            author=cls.teacher,
            approved_at=timezone.now(),
            section_data={"desc": {"description": "Preserve independent generic535 approved body"}},
        )
        apps.get_model("registrar.SubgroupPlacementEvent").objects.create(
            organization=cls.org,
            kind="place",
            offering=cls.courses[1],
            enrollment=cls.enrs[-1],
            student=cls.enrs[-1].student,
            source_group=cls.stack["group"],
            target_group=group2,
            reason="Preserve actual placement evidence",
            actor=cls.actor,
        )
        TeachingTask.objects.filter(pk=cls.task.pk).update(status="amended")

    def setUp(self):
        self.patches = ExitStack()
        self.addCleanup(self.patches.close)
        courses = self.courses
        syllabi = [self.source, self.old_fallback, self.generic]
        versions = [self.approved, self.old_version, self.generic_version]
        pins = {
            "ORG": str(self.org.pk),
            "TEACHER": self.teacher.pk,
            "PERIOD": str(self.stack["period"].pk),
            "TASK": str(self.task.pk),
            "CHAIR": str(self.stack["chair"].pk),
            "TARGET": str(courses[0].pk),
            "ROW": str(self.rows[0].pk),
            "OLD_SUBJECT": str(self.old_subject.pk),
            "NEW_SUBJECT": str(self.new_subject.pk),
            "SOURCE_SYLLABUS": str(self.source.pk),
            "SOURCE_VERSION": str(self.approved.pk),
            "SOURCE_BODY_SHA": content_fingerprints(
                {section.section_id: section.data for section in self.approved.sections.all()}
            )["canonical_body_sha256"],
            "OFFERINGS": {
                str(course.pk): normal(
                    {
                        key: getattr(course, key)
                        for key in ("subject_id", "period_id", "group_id", "instructor_id", "lesson_hours", "is_active")
                    }
                )
                for course in courses
            },
            "ROWS": {
                str(row.pk): normal(
                    {
                        field.attname: getattr(row, field.attname)
                        for field in type(row)._meta.concrete_fields
                        if field.is_relation
                    }
                )
                for row in self.rows
            },
            "SYLLABI": {
                str(syl.pk): {
                    "version_id": str(version.pk),
                    "subject_id": str(syl.subject_id),
                    "offering_id": str(syl.offering_id) if syl.offering_id else None,
                    "period_id": str(syl.period_id) if syl.period_id else None,
                }
                for syl, version in zip(syllabi, versions)
            },
            "BRIDGE": [],
        }
        for key, value in pins.items():
            self.patches.enter_context(patch.object(spec, key, copy.deepcopy(value)))
        rows = graph(
            spec.ORG,
            {
                "registrar.CourseOffering": set(spec.OFFERINGS),
                "workload.TeachingTaskRow": set(spec.ROWS),
                "syllabus.Syllabus": set(spec.SYLLABI),
            },
        )
        self.patches.enter_context(
            patch.object(
                spec,
                "GRAPH_PINS",
                {label: {"count": len(values), "sha256": digest(values)} for label, values in rows.items()},
            )
        )

    def run_repair(self, **kwargs):
        return repair.run(organization=self.org, actor=self.actor, **kwargs)

    def apply(self):
        dry = self.run_repair()
        return self.run_repair(apply=True, expected_baseline=dry["baseline"])

    def test_apply_repeat_and_undo_preserve_542_cells_old6117_generic_approval_and_event(self):
        before = state.snapshot(self.org)
        versions = apps.get_model("syllabus.SyllabusVersion").objects.count()
        marks = digest(bounded(LessonMark._base_manager.all()))
        result = self.apply()
        self.assertEqual(result["status"], "applied")
        self.courses[0].refresh_from_db()
        self.rows[0].refresh_from_db()
        self.assertEqual(self.courses[0].subject_id, self.new_subject.pk)
        self.assertEqual(self.rows[0].subject_id, self.new_subject.pk)
        selected = syllabus_for_offering(
            organization=self.org,
            offering_id=self.courses[0].pk,
            subject_id=self.new_subject.pk,
            period_id=self.stack["period"].pk,
            instructor_id=self.teacher.pk,
        )
        self.assertEqual(selected.pk, self.source.pk)
        self.assertEqual(apps.get_model("syllabus.SyllabusVersion").objects.count(), versions)
        self.assertEqual(digest(bounded(LessonMark._base_manager.all())), marks)
        self.assertEqual(LessonMark.objects.count(), 542)
        self.assertEqual(Lesson.objects.filter(offering=self.courses[0]).count(), 18)
        self.assertEqual(Enrollment.objects.filter(offering=self.courses[0]).count(), 15)
        self.assertEqual(apps.get_model("registrar.SubgroupPlacementEvent").objects.count(), 1)
        self.assertEqual(self.run_repair()["status"], "already_applied")
        dry = self.run_repair(undo=result["receipt"])
        self.run_repair(undo=result["receipt"], apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(repair._protected(before), repair._protected(state.snapshot(self.org)))
        self.assertEqual(self.run_repair()["status"], "already_undone")
        self.old_fallback.refresh_from_db()
        self.assertEqual(self.old_fallback.approved_version_id, self.old_version.pk)

    def test_wrong_fallback_cannot_substitute_the_exact_8668_body(self):
        wrong = content_fingerprints({section.section_id: section.data for section in self.old_version.sections.all()})[
            "canonical_body_sha256"
        ]
        with patch.object(spec, "SOURCE_BODY_SHA", wrong), self.assertRaisesRegex(RepairError, "8668_body_changed"):
            self.run_repair()
        self.assertFalse(apps.get_model("syllabus.SyllabusShare").objects.exists())

    def test_new_human_draft_is_preserved_and_blocks_correction(self):
        draft = apps.get_model("syllabus.SyllabusVersion").objects.create(
            organization=self.org, syllabus=self.source, major=1, minor=1, status="draft", created_by=self.teacher
        )
        type(self.source).objects.filter(pk=self.source.pk).update(current_version=draft)
        with self.assertRaisesRegex(RepairError, "human_draft"):
            self.run_repair()
        draft.refresh_from_db()
        self.assertEqual(draft.status, "draft")
        self.assertFalse(apps.get_model("syllabus.SyllabusShare").objects.exists())

    def test_share_refusal_rolls_back_both_subject_links_amendment_and_task(self):
        before = state.snapshot(self.org)
        dry = self.run_repair()
        with (
            patch.object(repair, "link_legacy_share", return_value="taken"),
            self.assertRaisesRegex(RepairError, "share_refused"),
        ):
            self.run_repair(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(before, state.snapshot(self.org))

    def test_later_grade_zero_edit_blocks_undo_and_is_kept(self):
        result = self.apply()
        mark = LessonMark.objects.filter(score=0).first()
        with journal_unlock():
            LessonMark.objects.filter(pk=mark.pk).update(score=5)
        with self.assertRaisesRegex(RepairError, "protected_content_changed"):
            self.run_repair(undo=result["receipt"])
        mark.refresh_from_db()
        self.assertEqual(mark.score, 5)
        self.assertEqual(apps.get_model("syllabus.SyllabusShare").objects.count(), 1)

    def test_new_canonical_course_or_stale_baseline_is_held_before_writes(self):
        dry = self.run_repair()
        with self.assertRaisesRegex(RepairError, "fresh_baseline"):
            self.run_repair(apply=True, expected_baseline="0" * 64)
        group = apps.get_model("organizations.OrgUnit").objects.create(
            organization=self.org, name="Other", slug="ilahe-extra", unit_type="group"
        )
        CourseOffering.objects.create(
            organization=self.org,
            subject=self.new_subject,
            period=self.stack["period"],
            group=group,
            instructor=self.teacher,
        )
        with self.assertRaisesRegex(RepairError, "cohort_conflict"):
            self.run_repair(apply=True, expected_baseline=dry["baseline"])
        self.assertFalse(apps.get_model("syllabus.SyllabusShare").objects.exists())

    def test_foreign_superadmin_cannot_access_or_modify_the_repair(self):
        foreign = make_org("ilahe-foreign")
        actor = foreign.owner
        actor.is_superuser = True
        actor.save(update_fields=["is_superuser"])
        with self.assertRaisesRegex(RepairError, "actor_tenant"):
            repair.run(organization=self.org, actor=actor, apply=True)

    def test_actual_cli_dry_and_safe_failure_in_both_rls_modes(self):
        for scoped in (False, True):
            with override_settings(RLS_TRANSACTION_SCOPED=scoped):
                output = StringIO()
                call_command("repair_reviewed_ilahe_subject", actor=self.actor.username, stdout=output)
                self.assertIn("status=dry_run", output.getvalue())
                with (
                    patch.object(repair, "run", side_effect=RuntimeError("PRIVATE_GRADE_BODY")),
                    self.assertRaisesRegex(CommandError, "snapshot_or_rebind_failed"),
                ):
                    call_command("repair_reviewed_ilahe_subject", actor=self.actor.username, stdout=StringIO())
