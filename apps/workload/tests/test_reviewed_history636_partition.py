"""Real PG: preserve genuine 4QB×2h while correcting official course contacts."""

import copy
import uuid
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth import get_user_model
from django.test import TestCase

from ..models import TeacherAssignment
from ..services import reviewed_history636_repair as repair
from ..services import reviewed_history636_spec as spec
from ..services import reviewed_history636_state as state
from ..services import reviewed_two_catalog_schema as schema
from ..services.reviewed_leyla_catalog_graph import bounded, digest
from ..services.sbio235_state import RepairError
from . import test_reviewed_asef_stream as asef_fixture
from .factories import TEACHER_PERMS, activate_member, make_row, make_structure, make_task


class History636PartitionTests(TestCase):
    def setUp(self):
        asef_fixture.ReviewedAsefStreamTests.setUp(self)
        self.other = get_user_model().objects.create_user("history636-other")
        activate_member(self.org, self.other, "teacher", permissions=TEACHER_PERMS, scope_unit=self.stack["chair"])
        self.other.profile.organization = self.org
        self.other.profile.save(update_fields=["organization"])
        TeacherAssignment.objects.filter(row__in=[self.keeper, self.duplicate]).delete()
        self.third = make_row(self.task, {**self.stack, "group": self.children[0]}, lecture_total=15, seminar_total=30)
        # Map one physical row to each journal. The English seminar teacher stays distinct.
        self.rows = [self.keeper, self.duplicate, self.third]
        self.row_groups = [self.stack["group"], self.children[1], self.children[0]]
        for index, row in enumerate(self.rows):
            row.groups.set([self.row_groups[index]])
            type(row).objects.filter(pk=row.pk).update(
                lecture_plan=15,
                lecture_total=0 if index == 1 else 15,
                seminar_plan=30 if index == 2 else 15,
                seminar_total=30 if index == 2 else 15,
                total_hours=[30, 15, 45][index],
                union_count=0 if index == 1 else 1,
            )
            if index != 1:
                TeacherAssignment.objects.create(
                    organization=self.org, row=row, teacher=self.teacher, activity="lecture", hours=15
                )
            TeacherAssignment.objects.create(
                organization=self.org,
                row=row,
                teacher=self.other if index == 2 else self.teacher,
                activity="seminar",
                hours=30 if index == 2 else 15,
            )
        for index, course in enumerate(self.courses):
            type(course).objects.filter(pk=course.pk).update(lesson_hours=[30, 45, 30][index])
        # Four genuine distinct source lessons, two lecture/two seminar, are never merged or deleted.
        course = self.courses[0]
        enrollment = course.enrollments.first()
        Mark = apps.get_model("registrar.LessonMark")
        Mark.objects.filter(enrollment=enrollment).delete()
        apps.get_model("registrar.Lesson").objects.filter(offering=course).delete()
        from django.utils import timezone

        for n in range(4):
            lesson = apps.get_model("registrar.Lesson").objects.create(
                organization=self.org,
                offering=course,
                date=timezone.localdate() - __import__("datetime").timedelta(days=n // 2),
                start_time="13:35" if n % 2 == 0 else "15:15",
                hours=2,
                kind="lecture" if n % 2 == 0 else "seminar",
            )
            Mark.objects.create(organization=self.org, lesson=lesson, enrollment=enrollment, status="absent")
        pin = copy.deepcopy(spec.PINS)
        pin.update(
            organization_id=str(self.org.pk),
            period_id=str(self.stack["period"].pk),
            year=self.task.academic_year,
            subject_id=str(self.stack["subject"].pk),
            task=str(self.task.pk),
            chair=str(self.task.chair_id),
            teacher=self.teacher.pk,
            other_teacher=self.other.pk,
            usernames={str(self.teacher.pk): self.teacher.username, str(self.other.pk): self.other.username},
            groups=[str(g.pk) for g in self.row_groups],
            new_row=str(uuid.uuid4()),
            new_assignment=str(uuid.uuid4()),
        )
        pin["task_chairs"] = {str(self.task.pk): str(self.task.chair_id)}
        pin["group_pins"] = {
            r["id"]: r for r in bounded(apps.get_model("organizations.OrgUnit").objects.filter(pk__in=pin["groups"]))
        }
        pin["rows"] = {
            r["id"]: {k: v for k, v in r.items() if k not in {"created_at", "updated_at"}}
            for r in bounded(type(self.keeper).objects.filter(pk__in=[r.pk for r in self.rows]))
        }
        pin["row_groups"] = {str(r.pk): str(g.pk) for r, g in zip(self.rows, self.row_groups)}
        pin["assignments"] = {
            r["id"]: {k: r[k] for k in ("id", "row_id", "teacher_id", "activity", "hours", "is_hourly_paid")}
            for r in bounded(TeacherAssignment.objects.filter(row__in=self.rows))
        }
        pin["courses"] = {
            r["id"]: {
                k: r[k]
                for k in ("id", "group_id", "instructor_id", "subject_id", "period_id", "lesson_hours", "is_active")
            }
            for r in bounded(type(course).objects.filter(pk__in=[c.pk for c in self.courses]))
        }
        pin["syllabi"] = {
            r["id"]: r for r in bounded(apps.get_model("syllabus.Syllabus").objects.filter(offering__in=self.courses))
        }
        pin["versions"] = {
            str(v.pk): {
                "syllabus_id": str(v.syllabus_id),
                "status": "approved",
                "plan_hours": v.plan_hours,
                "after_plan": {"seminar": 30} if index == 1 else {"lecture": 30, "seminar": 30},
                "body_sha256": digest(list(v.sections.order_by("section_id").values("section_id", "data"))),
            }
            for index, v in enumerate(self.versions)
        }
        for key, value in {
            "PINS": pin,
            "ORG": str(self.org.pk),
            "PERIOD": str(self.stack["period"].pk),
            "SCHEMA": schema.fingerprints(),
        }.items():
            patcher = patch.object(spec, key, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def execute(self, **options):
        return repair.run(
            manifest={"format": spec.FORMAT, "organization_id": spec.ORG, "source": spec.PINS["source"]},
            manifest_sha="a" * 64,
            lines=[164],
            organization=self.org,
            user=self.actor,
            **options,
        )

    def apply(self):
        return self.execute(apply=True, expected_baseline=self.execute()["baseline"])

    def test_apply_repeat_undo_preserve_exact_marks_bodies_and_teachers(self):
        before = state.snapshot(self.org, self.actor)
        marks = list(apps.get_model("registrar.LessonMark").objects.order_by("pk").values())
        result = self.apply()
        after = state.snapshot(self.org, self.actor)
        self.assertEqual(state.protected(before), state.protected(after))
        self.assertEqual(marks, list(apps.get_model("registrar.LessonMark").objects.order_by("pk").values()))
        self.assertEqual(
            sum(TeacherAssignment.objects.filter(teacher=self.teacher).values_list("hours", flat=True)), 90
        )
        self.assertEqual(sum(TeacherAssignment.objects.filter(teacher=self.other).values_list("hours", flat=True)), 30)
        self.assertEqual(set(type(self.courses[0]).objects.values_list("lesson_hours", flat=True)), {60})
        from ..services.offering_rules import merge_hours

        for course in self.courses:
            rows = type(self.keeper).objects.filter(subject=course.subject, period=course.period, groups=course.group)
            self.assertEqual(sum(merge_hours(rows).values()), 60)
        self.assertEqual(self.execute()["status"], "already_applied")
        dry = self.execute(undo=result["receipt"])
        self.execute(undo=result["receipt"], apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(state.snapshot(self.org, self.actor), before)
        self.assertEqual(self.execute(undo=result["receipt"])["status"], "already_undone")

    def test_stale_baseline_rolls_back_all_metadata(self):
        before = state.snapshot(self.org, self.actor)
        with self.assertRaisesMessage(RepairError, "history636_fresh_baseline_required"):
            self.execute(apply=True, expected_baseline="0" * 64)
        self.assertEqual(state.snapshot(self.org, self.actor), before)

    def test_partial_contact_change_fails_closed_without_qb_repair(self):
        type(self.courses[0]).objects.filter(pk=self.courses[0].pk).update(lesson_hours=60)
        with self.assertRaisesMessage(RepairError, "history636_course_changed"):
            self.execute()

    def test_body_change_never_accepted_as_contact_fix(self):
        section = self.versions[0].sections.first()
        section.data = {"foreign_topic": "must not overwrite"}
        section.save(update_fields=["data"])
        with self.assertRaisesMessage(RepairError, "history636_approved_body_changed"):
            self.execute()

    def test_group_swap_and_unknown_assignment_refused(self):
        self.rows[0].groups.set([self.children[0]])
        with self.assertRaisesMessage(RepairError, "history636_group_links_changed"):
            self.execute()

    def test_four_genuine_qb_eight_hours_use_sixty_contact_hours_not_thirty(self):
        from apps.registrar.public import eligibility_rules

        enrollment = self.courses[0].enrollments.first()
        marks = apps.get_model("registrar.LessonMark").objects.filter(enrollment=enrollment, status="absent")
        self.assertEqual(marks.count(), 4)
        hours = sum(marks.values_list("lesson__hours", flat=True))
        self.assertEqual(hours, 8)
        self.assertTrue(eligibility_rules.resolve(absence_hours=hours, lesson_hours=30)["barred"])
        self.apply()
        self.courses[0].refresh_from_db()
        outcome = eligibility_rules.resolve(absence_hours=hours, lesson_hours=self.courses[0].lesson_hours)
        self.assertEqual(outcome["allowed_hours"], 15)
        self.assertFalse(outcome["barred"])
        self.assertFalse(eligibility_rules.resolve(absence_hours=15, lesson_hours=60)["barred"])
        self.assertTrue(eligibility_rules.resolve(absence_hours=16, lesson_hours=60)["barred"])
        self.assertEqual(marks.count(), 4)

    def test_post_write_preservation_failure_rolls_back_new_row_and_all_metadata(self):
        before = state.snapshot(self.org, self.actor)
        protected = state.protected
        calls = 0

        def broken(snapshot):
            nonlocal calls
            calls += 1
            return {**protected(snapshot), "injected_concurrent_delta": calls}

        dry = self.execute()
        with patch.object(state, "protected", side_effect=broken):
            with self.assertRaisesMessage(RepairError, "history636_full_graph_preservation_failed"):
                self.execute(apply=True, expected_baseline=dry["baseline"])
        self.assertEqual(state.snapshot(self.org, self.actor), before)
        self.assertFalse(type(self.keeper).objects.filter(pk=spec.PINS["new_row"]).exists())

    def test_inflight_student_mark_change_requires_fresh_review(self):
        dry = self.execute()
        mark = apps.get_model("registrar.LessonMark").objects.filter(enrollment__offering=self.courses[0]).first()
        mark.status = "excused"
        mark.save(update_fields=["status"])
        with self.assertRaisesMessage(RepairError, "history636_fresh_baseline_required"):
            self.execute(apply=True, expected_baseline=dry["baseline"])
        mark.refresh_from_db()
        self.assertEqual(mark.status, "excused")
        self.assertFalse(type(self.keeper).objects.filter(pk=spec.PINS["new_row"]).exists())

    def test_foreign_english_seminar_task_and_teacher_are_preserved_without_new_membership(self):
        foreign = make_structure(self.org, code="HISTORY-FOREIGN")
        task = make_task(self.org, foreign["chair"], status="amended")
        activate_member(self.org, self.other, "teacher", permissions=TEACHER_PERMS, scope_unit=foreign["chair"])
        type(self.third).objects.filter(pk=self.third.pk).update(task=task)
        spec.PINS["rows"][str(self.third.pk)]["task_id"] = str(task.pk)
        spec.PINS["task_chairs"][str(task.pk)] = str(task.chair_id)
        memberships = list(apps.get_model("organizations.Membership").objects.order_by("pk").values())
        self.apply()
        self.third.refresh_from_db()
        self.assertEqual(self.third.task_id, task.pk)
        self.assertEqual(list(apps.get_model("organizations.Membership").objects.order_by("pk").values()), memberships)
        self.assertEqual(TeacherAssignment.objects.get(row=self.third).teacher_id, self.other.pk)
