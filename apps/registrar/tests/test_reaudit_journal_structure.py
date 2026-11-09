"""Real PostgreSQL graph/counter/receipt regressions for bounded structural repairs."""

import datetime as dt
import hashlib
import json
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TestCase

from apps.organizations.models import Membership, OrgUnit
from apps.registrar import reaudit_journal_structure as op
from apps.registrar import reaudit_journal_structure_spec as spec
from apps.registrar import reaudit_journal_structure_state as state
from apps.registrar.models import AssessmentScheme, CourseOffering, Enrollment, Lesson, LessonMark, ScheduleSlot
from apps.registrar.tests import test_teacher_journal_visibility as fixtures
from apps.registrar.timetable_inference import load_facts
from apps.workload.models import TeacherAssignment
from core.reviewed_graph import digest


class JournalStructureTests(TestCase):
    setUpTestData = classmethod(fixtures.TeacherJournalVisibilityTests.setUpTestData.__func__)
    offering = fixtures.TeacherJournalVisibilityTests.offering

    def setUp(self):
        self.actor = self.org.owner
        self.actor.profile.organization = self.org
        self.actor.profile.access_state = "active"
        self.actor.profile.save()
        self.course = self.offering(instructor=self.teacher)
        AssessmentScheme.objects.create(organization=self.org, offering=self.course)
        self.student = get_user_model().objects.create_user("structure-synthetic-student")
        Membership.objects.create(
            organization=self.org, user=self.student, role=self.org.roles.get(name="student"), is_active=True
        )
        self.enrollment = Enrollment.objects.create(organization=self.org, offering=self.course, student=self.student)
        self.lessons = []
        for index in range(3):
            lesson = Lesson.objects.create(
                organization=self.org,
                offering=self.course,
                instructor=self.teacher,
                date=dt.date(2026, 10, 5 + index),
                start_time=dt.time(9),
                end_time=dt.time(9, 45),
                kind="seminar",
                hours=2,
            )
            LessonMark.objects.create(
                organization=self.org,
                lesson=lesson,
                enrollment=self.enrollment,
                status="present" if index == 2 else "absent",
                score=0 if index == 2 else None,
            )
            self.lessons.append(lesson)
        Enrollment.objects.filter(pk=self.enrollment.pk).update(absence_hours=4)
        self.authority = b"synthetic reviewed authority; no production data"
        self.authority_sha = hashlib.sha256(self.authority).hexdigest()
        self.registry = {
            "half_pair_cases": self.case_pins(),
            "inactive_cache_enrollment_ids": [str(self.enrollment.pk)],
        }
        for key, value in {
            "ORG": str(self.org.pk),
            "PERIOD": str(self.course.period_id),
            "HALF_AUTHORITY_SHA": self.authority_sha,
        }.items():
            mocked = patch.object(spec, key, value)
            mocked.start()
            self.addCleanup(mocked.stop)
        mocked = patch.object(spec, "scope", side_effect=lambda: self.registry)
        mocked.start()
        self.addCleanup(mocked.stop)

    def case_pins(self):
        cases = []
        for lesson in self.lessons:
            fields = ("id", "offering_id", "date", "start_time", "end_time", "instructor_id", "kind", "topic")
            course_fields = ("id", "subject_id", "group_id", "period_id", "instructor_id", "is_active")
            marks = sorted(
                (
                    str(row.pk),
                    str(row.enrollment_id),
                    row.status,
                    format(Decimal(row.score).normalize(), "f") if row.score is not None else None,
                    row.entered_by_id,
                )
                for row in lesson.marks.all()
            )
            cases.append(
                {
                    "lesson_id": str(lesson.pk),
                    "offering_id": str(self.course.pk),
                    "offering_fields": course_fields,
                    "offering_sha256": digest({k: str(getattr(self.course, k)) for k in course_fields}),
                    "lesson_fields": fields,
                    "lesson_sha256": digest({k: str(getattr(lesson, k)) for k in fields}),
                    "mark_count": len(marks),
                    "marks_sha256": hashlib.sha256(
                        json.dumps(
                            marks, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":")
                        ).encode()
                    ).hexdigest(),
                }
            )
        return cases

    def manifest(self, operation="half_pair"):
        return {
            "format": "reaudit-journal-structure/1",
            "organization_id": str(self.org.pk),
            "period_id": str(self.course.period_id),
            "operation": operation,
            "target_ids": (
                [str(row.pk) for row in self.lessons]
                if operation == "half_pair"
                else [str(self.enrollment.pk)] if operation == "inactive_cache" else [str(self.course.pk)]
            ),
            "authority_sha256": self.authority_sha,
        }

    def execute(self, operation="half_pair", **kwargs):
        return op.run(organization=self.org, actor=self.actor, manifest=self.manifest(operation), **kwargs)

    def apply(self, operation="half_pair"):
        return self.execute(
            operation, apply=True, authority_bytes=self.authority, expected_baseline=self.execute(operation)["baseline"]
        )

    def test_half_pair_formal_apply_repeat_and_undo_preserve_zero_and_marks(self):
        before_marks = list(LessonMark.objects.filter(enrollment=self.enrollment).order_by("pk").values())
        dry = self.execute()
        self.assertEqual((dry["canonical_before"], dry["canonical_after"]), (4, 2))
        self.assertEqual(Lesson.objects.filter(pk__in=[r.pk for r in self.lessons], hours=2).count(), 3)
        result = self.apply()
        self.assertEqual(result["changed"], 3)
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.absence_hours, 2)
        self.assertEqual(
            list(LessonMark.objects.filter(enrollment=self.enrollment).order_by("pk").values()), before_marks
        )
        self.assertEqual(self.execute()["status"], "already_applied")
        preview = self.execute(undo=result["receipt"])
        self.execute(
            apply=True, undo=result["receipt"], expected_baseline=preview["baseline"], authority_bytes=self.authority
        )
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.absence_hours, 4)
        self.assertEqual(self.execute(undo=result["receipt"])["status"], "already_undone")

    def test_source_authority_and_changed_mark_are_not_overridden(self):
        dry = self.execute()
        with self.assertRaisesRegex(ValueError, "source_authority"), transaction.atomic():
            self.execute(apply=True, expected_baseline=dry["baseline"])
        LessonMark.objects.filter(enrollment=self.enrollment, score=0).update(score=1)
        with self.assertRaisesRegex(ValueError, "reviewed_marks_changed"), transaction.atomic():
            self.execute(apply=True, expected_baseline=dry["baseline"], authority_bytes=self.authority)
        self.assertEqual(Lesson.objects.filter(pk__in=[r.pk for r in self.lessons], hours=2).count(), 3)

    def test_teacher_edit_after_apply_blocks_undo(self):
        result = self.apply()
        LessonMark.objects.filter(enrollment=self.enrollment, score=0).update(score=1)
        with self.assertRaisesRegex(ValueError, "post_apply_graph_changed"), transaction.atomic():
            self.execute(undo=result["receipt"])

    def test_counter_cache_requires_inactive_scope_and_receipt_undo(self):
        with self.assertRaisesRegex(ValueError, "cache_target_now_active"), transaction.atomic():
            self.execute("inactive_cache")
        CourseOffering.objects.filter(pk=self.course.pk).update(is_active=False)
        Enrollment.objects.filter(pk=self.enrollment.pk).update(status="suspended", absence_hours=12)
        result = self.apply("inactive_cache")
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.absence_hours, 4)
        self.assertEqual(self.execute("inactive_cache")["changed"], 0)
        preview = self.execute("inactive_cache", undo=result["receipt"])
        self.execute(
            "inactive_cache",
            undo=result["receipt"],
            apply=True,
            authority_bytes=self.authority,
            expected_baseline=preview["baseline"],
        )
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.absence_hours, 12)

    def test_credit_change_after_dry_run_blocks_stale_apply(self):
        dry = self.execute()
        apps.get_model("registrar.AbsenceCredit").objects.create(
            organization=self.org,
            enrollment=self.enrollment,
            hours=1,
            actor=self.actor,
            request_token=uuid4(),
            reason="Synthetic reviewed credit",
            old_absence_hours=4,
            new_absence_hours=3,
        )
        with self.assertRaisesRegex(ValueError, "fresh_baseline"), transaction.atomic():
            self.execute(apply=True, expected_baseline=dry["baseline"], authority_bytes=self.authority)

    def test_canonical_credits_are_kept_on_half_pair_and_undo(self):
        apps.get_model("registrar.AbsenceCredit").objects.create(
            organization=self.org,
            enrollment=self.enrollment,
            hours=3,
            actor=self.actor,
            request_token=uuid4(),
            reason="Synthetic reviewed credit",
            old_absence_hours=4,
            new_absence_hours=1,
        )
        result = self.apply()
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.absence_hours, 0)
        preview = self.execute(undo=result["receipt"])
        self.execute(
            undo=result["receipt"], apply=True, expected_baseline=preview["baseline"], authority_bytes=self.authority
        )
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.absence_hours, 1)
        self.assertEqual(apps.get_model("registrar.AbsenceCredit").objects.count(), 1)

    def test_post_write_guard_rolls_back_all_half_pair_changes(self):
        dry = self.execute()
        original = state.protected
        calls = []

        def altered(*args, **kwargs):
            result = original(*args, **kwargs)
            calls.append(True)
            if len(calls) == 2:
                result["unexpected"] = True
            return result

        with (
            patch.object(state, "protected", side_effect=altered),
            self.assertRaisesRegex(ValueError, "protected_graph"),
        ):
            self.execute(apply=True, expected_baseline=dry["baseline"], authority_bytes=self.authority)
        self.assertEqual(Lesson.objects.filter(pk__in=[r.pk for r in self.lessons], hours=2).count(), 3)
        self.assertEqual(apps.get_model("registrar.LessonCorrection").objects.count(), 0)

    def test_inactive_actor_or_foreign_profile_cannot_run(self):
        self.actor.profile.organization = None
        self.actor.profile.save(update_fields=["organization"])
        with self.assertRaisesRegex(ValueError, "actor_profile"), transaction.atomic():
            self.execute()

    def timetable_lessons(self):
        TeacherAssignment.objects.create(
            organization=self.org, row=self.row, teacher=self.teacher, activity="seminar", hours=30
        )
        Lesson.objects.filter(offering=self.course).delete()
        self.lessons = [
            Lesson.objects.create(
                organization=self.org,
                offering=self.course,
                instructor=self.teacher,
                date=dt.date(2026, 10, day),
                start_time=dt.time(9),
                end_time=dt.time(10, 30),
                kind="seminar",
            )
            for day in (5, 12, 19)
        ]

    def test_split_lessons_cannot_infer_whole_group_timetable(self):
        self.timetable_lessons()
        Lesson.objects.filter(offering=self.course).update(seminar_group=1)
        facts, stats = load_facts(
            organization=self.org,
            period=self.course.period,
            date_from=dt.date(2026, 9, 1),
            date_to=dt.date(2026, 11, 9),
        )
        self.assertEqual(facts, [])
        self.assertEqual(stats["subgroup_not_representable"], 3)
        self.assertEqual(self.execute("timetable")["planned"], 0)

    def test_timetable_additive_apply_repeat_undo_and_manual_slot_preserved(self):
        self.timetable_lessons()
        manual = ScheduleSlot.objects.create(
            organization=self.org,
            offering=self.course,
            weekday=2,
            start_time=dt.time(12),
            end_time=dt.time(13, 30),
            kind="seminar",
            room="A",
        )
        result = self.apply("timetable")
        self.assertEqual(result["changed"], 1)
        self.assertEqual(ScheduleSlot.objects.filter(offering=self.course).count(), 2)
        self.assertEqual(self.execute("timetable")["status"], "already_applied")
        preview = self.execute("timetable", undo=result["receipt"])
        self.execute(
            "timetable",
            undo=result["receipt"],
            apply=True,
            expected_baseline=preview["baseline"],
            authority_bytes=self.authority,
        )
        self.assertEqual(
            list(ScheduleSlot.objects.filter(offering=self.course).values_list("pk", flat=True)), [manual.pk]
        )

    def test_counter_formula_uses_direct_raw_credit_not_predecessor_cache(self):
        enrollments = {
            "a": {"id": "a", "status": "dropped", "superseded_by_id": "b", "absence_hours": 999},
            "b": {"id": "b", "status": "enrolled", "superseded_by_id": None, "absence_hours": 999},
        }
        marks = [
            {"enrollment_id": "a", "lesson_id": "la", "status": "absent"},
            {"enrollment_id": "b", "lesson_id": "lb", "status": "absent"},
        ]
        lessons = {"la": {"id": "la", "hours": 2}, "lb": {"id": "lb", "hours": 2}}
        result = state.counters(
            enrollments, marks, lessons, {"a": 1, "b": 1}, {"operation": "half_pair", "target_ids": ["la", "lb"]}
        )
        self.assertEqual([(row["canonical_before"], row["canonical_after"]) for row in result], [(1, 0), (2, 0)])

    def successor(self):
        group = OrgUnit.objects.create(
            organization=self.org, name="Synthetic successor", slug="structure-next", unit_type="group"
        )
        course = CourseOffering.objects.create(
            organization=self.org,
            subject=self.course.subject,
            group=group,
            period=self.course.period,
            instructor=self.teacher,
        )
        AssessmentScheme.objects.create(organization=self.org, offering=course)
        target = Enrollment.objects.create(organization=self.org, offering=course, student=self.student)
        Enrollment.objects.filter(pk=self.enrollment.pk).update(
            status="dropped", superseded_by=target, absence_hours=99
        )
        lesson = Lesson.objects.create(
            organization=self.org, offering=course, date=dt.date(2026, 10, 8), kind="seminar", hours=2
        )
        LessonMark.objects.create(organization=self.org, lesson=lesson, enrollment=target, status="absent")
        Enrollment.objects.filter(pk=target.pk).update(absence_hours=99)
        return target

    def test_real_carry_and_both_credit_caps_match_native_counter_writer(self):
        target = self.successor()
        for enrollment, available in ((self.enrollment, 4), (target, 5)):
            apps.get_model("registrar.AbsenceCredit").objects.create(
                organization=self.org,
                enrollment=enrollment,
                hours=1,
                actor=self.actor,
                request_token=uuid4(),
                reason="Synthetic reviewed credit",
                old_absence_hours=available,
                new_absence_hours=available - 1,
            )
        dry = self.execute()
        self.assertEqual((dry["canonical_before"], dry["canonical_after"]), (7, 3))
        result = self.apply()
        self.enrollment.refresh_from_db()
        target.refresh_from_db()
        self.assertEqual((self.enrollment.absence_hours, target.absence_hours), (1, 2))
        preview = self.execute(undo=result["receipt"])
        self.execute(
            undo=result["receipt"], apply=True, expected_baseline=preview["baseline"], authority_bytes=self.authority
        )
        self.enrollment.refresh_from_db()
        target.refresh_from_db()
        self.assertEqual((self.enrollment.absence_hours, target.absence_hours), (3, 4))

    def test_inactive_cache_never_refreshes_active_successor(self):
        self.successor()
        CourseOffering.objects.filter(pk=self.course.pk).update(is_active=False)
        with self.assertRaisesRegex(ValueError, "cache_reaches_active_target"), transaction.atomic():
            self.execute("inactive_cache")

    def test_new_teacher_mark_requires_new_review_not_superset_overwrite(self):
        dry = self.execute()
        second = get_user_model().objects.create_user("structure-second-student")
        Membership.objects.create(
            organization=self.org, user=second, role=self.org.roles.get(name="student"), is_active=True
        )
        enrollment = Enrollment.objects.create(organization=self.org, offering=self.course, student=second)
        LessonMark.objects.create(
            organization=self.org, lesson=self.lessons[0], enrollment=enrollment, status="present"
        )
        with self.assertRaisesRegex(ValueError, "reviewed_marks_changed"), transaction.atomic():
            self.execute(apply=True, expected_baseline=dry["baseline"], authority_bytes=self.authority)

    def test_duplicate_diagnostic_is_read_only_and_reports_actual_mask_and_credit_effect(self):
        from apps.registrar import reaudit_journal_structure_diagnostics as diagnostics

        first, second = list(
            LessonMark.objects.filter(enrollment=self.enrollment, status="absent").order_by("lesson_id")
        )
        Lesson.objects.filter(pk=first.lesson_id).update(seminar_group=1)
        Enrollment.objects.filter(pk=self.enrollment.pk).update(seminar_group=2)
        pairs = [
            {
                "kind": "cross_offering",
                "mark_ids": [str(first.pk), str(second.pk)],
                "enrollment_ids": [str(self.enrollment.pk), str(self.enrollment.pk)],
            }
        ]
        with patch.object(diagnostics, "candidate_pairs", return_value=pairs):
            result = diagnostics.inspect(organization=self.org, actor=self.actor)
        facts = result["candidates"][0]["facts"]
        self.assertFalse(facts[0]["lesson_applies_to_enrollment_mask"])
        self.assertEqual(set(facts[0]["hypothetical_effect_if_this_mark_not_absent"].values()), {-2})
        self.assertIs(result["candidates"][0]["eligible_for_apply"], False)
        self.assertEqual(LessonMark.objects.filter(enrollment=self.enrollment, status="absent").count(), 2)

    def test_timetable_changed_teacher_or_clock_after_dry_run_refuses_apply(self):
        self.timetable_lessons()
        dry = self.execute("timetable")
        Lesson.objects.filter(pk=self.lessons[0].pk).update(end_time=dt.time(10, 45))
        with self.assertRaisesRegex(ValueError, "fresh_baseline"), transaction.atomic():
            self.execute("timetable", apply=True, expected_baseline=dry["baseline"], authority_bytes=self.authority)
        self.assertFalse(ScheduleSlot.objects.filter(offering=self.course).exists())

    def test_timetable_changed_foreign_teacher_authorization_changes_reviewed_baseline(self):
        self.timetable_lessons()
        Lesson.objects.filter(offering=self.course).update(instructor=self.other)
        TeacherAssignment.objects.filter(row=self.row, activity="seminar").update(teacher=self.other)
        Membership.objects.filter(organization=self.org, user=self.other).update(is_active=False)
        dry = self.execute("timetable")
        self.assertEqual(dry["planned"], 0)
        Membership.objects.filter(organization=self.org, user=self.other).update(is_active=True)
        self.assertEqual(self.execute("timetable")["planned"], 1)
        with self.assertRaisesRegex(ValueError, "fresh_baseline"), transaction.atomic():
            self.execute("timetable", apply=True, expected_baseline=dry["baseline"], authority_bytes=self.authority)
        self.assertFalse(ScheduleSlot.objects.filter(offering=self.course).exists())

    def test_timetable_other_offering_teacher_change_invalidates_proposal(self):
        self.timetable_lessons()
        group = OrgUnit.objects.create(
            organization=self.org, name="Other schedule group", slug="structure-slot", unit_type="group"
        )
        other = CourseOffering.objects.create(
            organization=self.org,
            subject=self.course.subject,
            group=group,
            period=self.course.period,
            instructor=self.other,
        )
        ScheduleSlot.objects.create(
            organization=self.org,
            offering=other,
            weekday=1,
            start_time=dt.time(9),
            end_time=dt.time(10, 30),
            kind="lecture",
        )
        dry = self.execute("timetable")
        self.assertEqual(dry["planned"], 1)
        CourseOffering.objects.filter(pk=other.pk).update(instructor=self.teacher)
        self.assertEqual(self.execute("timetable")["planned"], 0)
        with self.assertRaisesRegex(ValueError, "fresh_baseline"), transaction.atomic():
            self.execute("timetable", apply=True, expected_baseline=dry["baseline"], authority_bytes=self.authority)
        self.assertFalse(ScheduleSlot.objects.filter(offering=self.course).exists())
