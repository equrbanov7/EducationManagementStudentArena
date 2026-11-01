"""Real PG: exact NULL instructor repair enables history without future load grants."""

import copy
import datetime
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TestCase

from apps.legacy_import.models import LegacyEntityMap
from apps.legacy_import.services import reviewed_anar_authorship as repair
from apps.legacy_import.services import reviewed_anar_state as state
from apps.legacy_import.services.ledger import create_run, start_run
from apps.organizations.models import OrgUnit
from apps.registrar import teacher_journal_list
from apps.registrar.models import CourseOffering, Enrollment, Lesson, LessonMark
from apps.registrar.tests import test_teacher_journal_visibility as fixtures
from apps.workload.models import TeacherAssignment


class ReviewedAnarAuthorshipTests(TestCase):
    setUpTestData = classmethod(fixtures.TeacherJournalVisibilityTests.setUpTestData.__func__)
    offering = fixtures.TeacherJournalVisibilityTests.offering

    def setUp(self):
        self.teacher.first_name, self.teacher.last_name = "Anar", "Vəliyev"
        self.teacher.save(update_fields=["first_name", "last_name"])
        profile = self.teacher.profile
        profile.patronymic = "Cümşüd"
        profile.organization = self.org
        profile.access_state = "active"
        profile.save(update_fields=["patronymic", "organization", "access_state"])
        self.first = self.offering(instructor=self.teacher)
        group = OrgUnit.objects.create(
            organization=self.org,
            parent=self.stack["group"].parent,
            name="Other fixed physical group",
            unit_type="group",
            settings=self.stack["group"].settings,
        )
        self.second = self.offering(instructor=self.teacher, stack={**self.stack, "group": group})
        CourseOffering.objects.filter(pk__in=[self.first.pk, self.second.pk]).update(lesson_hours=75)
        self.enrollments = []
        self.lessons = []
        for course in [self.first, self.second]:
            course.period.refresh_from_db()
            enrollment = Enrollment.objects.create(organization=self.org, offering=course, student=self.other)
            self.enrollments.append(enrollment)
            for index in range(14):
                lesson = Lesson.objects.create(
                    organization=self.org,
                    offering=course,
                    date=course.period.start_date + datetime.timedelta(days=index),
                    start_time="09:00",
                    kind="lecture" if index < 8 else "seminar",
                    hours=2,
                    is_legacy_synthesised=True,
                )
                self.lessons.append(lesson)
                LessonMark.objects.create(
                    organization=self.org,
                    lesson=lesson,
                    enrollment=enrollment,
                    status="present",
                    score=0 if index == 13 else None,
                )
        self.patchers = [
            patch.object(state, key, value)
            for key, value in {
                "ORG": str(self.org.pk),
                "PERIOD": str(self.first.period_id),
                "SUBJECT": str(self.first.subject_id),
                "TEACHER": self.teacher.pk,
                "OFFERINGS": {str(c.pk): str(c.group_id) for c in [self.first, self.second]},
            }.items()
        ]
        for patcher in self.patchers:
            patcher.start()
            self.addCleanup(patcher.stop)
        with transaction.atomic():
            lesson_rows = state.rows(Lesson.objects.filter(pk__in=[r.pk for r in self.lessons]))
            marks = state.rows(LessonMark.objects.filter(lesson__in=self.lessons))
        self.pins = copy.deepcopy(state.PINS)
        run = create_run(
            actor=self.org.owner,
            authorize=lambda **kw: True,
            organization=self.org,
            source_system="myedu_mariadb",
            snapshot_sha256="a" * 64,
            snapshot_size_bytes=1,
            source_row_count=2,
            schema_version="fixture",
            transform_version="fixture",
            mode="rehearsal",
        )
        run = start_run(run_id=run.pk, actor=self.org.owner, authorize=lambda **kw: True)
        self.pins["bridge"] = []
        self.bridge = []
        for legacy, course in [("788", self.first), ("816", self.second)]:
            row = LegacyEntityMap.objects.create(
                organization=self.org,
                source_system="myedu_mariadb",
                entity_type="group_unit",
                legacy_pk=legacy,
                source_row_hash="b" * 64,
                transform_version="fixture",
                target_model_label="organizations.orgunit",
                target_pk=str(course.group_id),
                created_run=run,
                state="migrated",
            )
            self.bridge.append(row)
            self.pins["bridge"].append(
                {
                    key: getattr(row, key)
                    for key in [
                        "entity_type",
                        "legacy_pk",
                        "target_model_label",
                        "target_pk",
                        "state",
                        "source_row_hash",
                        "transform_version",
                    ]
                }
            )
        fields = next(iter(state.PINS["lessons"].values()))["fields"].keys()
        self.pins["lessons"] = {r["id"]: {"fields": {k: r[k] for k in fields}} for r in lesson_rows}
        self.pins.update(marks_count=len(marks))
        with transaction.atomic():
            self.pins["marks_sha256"] = state.digest(
                state.raw_projection(LessonMark.objects.filter(lesson__in=self.lessons), self.pins["mark_fields"])
            )
            self.pins["lessons_sha256"] = state.digest(
                state.raw_projection(
                    Lesson.objects.filter(pk__in=[r.pk for r in self.lessons]), self.pins["lesson_fields"]
                )
            )
        patcher = patch.object(state, "PINS", self.pins)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.assertEqual(self.execute()["count"], 28)

    def execute(self, **options):
        return repair.run(organization=self.org, actor=self.org.owner, **options)

    def apply(self):
        return self.execute(apply=True, expected_baseline=self.execute()["baseline"])

    def assert_hold(self):
        with self.assertRaises(state.RepairError), transaction.atomic():
            self.execute()
        self.assertFalse(Lesson.objects.filter(pk__in=[r.pk for r in self.lessons], instructor__isnull=False).exists())

    def projected(self):
        return teacher_journal_list.own_visible_queryset(
            CourseOffering.objects.filter(pk__in=[self.first.pk, self.second.pk]), self.teacher, self.org
        )

    def test_native_apply_repeat_undo_only_instructor_full_rows(self):
        with transaction.atomic():
            before = state.snapshot()
        dry = self.execute()
        self.assertEqual(dry["count"], 28)
        self.assertEqual(self.projected().count(), 0)
        result = self.apply()
        self.assertEqual(result["status"], "applied")
        self.assertEqual(Lesson.objects.filter(instructor=self.teacher, pk__in=self.pins["lessons"]).count(), 28)
        self.assertFalse(Lesson.objects.filter(pk__in=self.pins["lessons"], created_by__isnull=False).exists())
        self.assertFalse(
            LessonMark.objects.filter(lesson_id__in=self.pins["lessons"], entered_by__isnull=False).exists()
        )
        self.assertEqual(self.execute()["count"], 0)
        self.assertEqual(self.execute(apply=True)["status"], "already_applied")
        rows = list(self.projected())
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(not row.journal_is_current_load for row in rows))
        teacher_journal_list.attach(self.teacher, rows)
        self.assertEqual([(r.journal_own_lessons, r.journal_own_hours) for r in rows], [(14, 28), (14, 28)])
        undo_dry = self.execute(undo=result["receipt"])
        self.assertFalse(undo_dry["applied"])
        self.execute(undo=result["receipt"], apply=True, expected_baseline=undo_dry["baseline"])
        with transaction.atomic():
            self.assertEqual(state.snapshot(), before)
        self.assertEqual(self.execute(undo=result["receipt"])["status"], "already_undone")

    def test_stale_baseline_rejected(self):
        baseline = self.execute()["baseline"]
        Enrollment.objects.filter(pk=self.enrollments[0].pk).update(status="withdrawn")
        with self.assertRaisesRegex(state.RepairError, "fresh_baseline"), transaction.atomic():
            self.execute(apply=True, expected_baseline=baseline)

    def test_changed_cell_even_old_zero_is_held(self):
        mark = LessonMark.objects.filter(score=0).first()
        LessonMark.objects.filter(pk=mark.pk).update(score=1)
        self.assert_hold()

    def test_changed_source_lesson_topic_is_held(self):
        Lesson.objects.filter(pk=self.lessons[0].pk).update(topic="Human authored change")
        self.assert_hold()

    def test_extra_or_missing_source_lesson_is_held(self):
        Lesson.objects.create(
            organization=self.org, offering=self.first, date=self.first.period.end_date, kind="seminar"
        )
        self.assert_hold()

    def test_other_instructor_is_never_overwritten(self):
        Lesson.objects.filter(pk=self.lessons[0].pk).update(instructor=self.other)
        with self.assertRaises(state.RepairError), transaction.atomic():
            self.execute()
        self.assertEqual(Lesson.objects.get(pk=self.lessons[0].pk).instructor_id, self.other.pk)

    def test_creator_unknown_stays_unknown_and_named_creator_holds(self):
        Lesson.objects.filter(pk=self.lessons[0].pk).update(created_by=self.other)
        self.assert_hold()

    def test_positive_other_teacher_share_holds(self):
        TeacherAssignment.objects.create(
            organization=self.org, row=self.row, teacher=self.other, activity="lecture", hours=1
        )
        self.assert_hold()

    def test_current_owner_changed_holds(self):
        CourseOffering.objects.filter(pk=self.second.pk).update(instructor=self.other)
        self.assert_hold()

    def test_teacher_name_changed_holds(self):
        get_user_model().objects.filter(pk=self.teacher.pk).update(first_name="Different")
        self.assert_hold()

    def test_undo_after_new_cell_change_holds(self):
        result = self.apply()
        LessonMark.objects.filter(lesson=self.lessons[0]).update(status="absent")
        with self.assertRaises(state.RepairError), transaction.atomic():
            self.execute(undo=result["receipt"], apply=True, expected_baseline="stale")
        self.assertEqual(Lesson.objects.filter(instructor=self.teacher).count(), 28)

    def test_protected_graph_failure_rolls_back(self):
        baseline = self.execute()["baseline"]
        real = repair.protected
        calls = [0]

        def changed(value):
            calls[0] += 1
            result = real(value)
            if calls[0] == 2:
                result["unknown_new_mutation"] = True
            return result

        with (
            patch.object(repair, "protected", side_effect=changed),
            self.assertRaisesRegex(state.RepairError, "preservation"),
            transaction.atomic(),
        ):
            self.execute(apply=True, expected_baseline=baseline)
        self.assertFalse(Lesson.objects.filter(pk__in=self.pins["lessons"], instructor__isnull=False).exists())

    def test_existing_current_load_and_bi_history_remain_separate(self):
        TeacherAssignment.objects.create(
            organization=self.org, row=self.row, teacher=self.teacher, activity="lecture", hours=30
        )
        self.assertEqual(self.projected().count(), 1)
        assignments_before = list(TeacherAssignment.objects.order_by("pk").values())
        self.apply()
        found = {row.pk: row for row in self.projected()}
        self.assertTrue(found[self.first.pk].journal_is_current_load)
        self.assertFalse(found[self.second.pk].journal_is_current_load)
        self.assertEqual(list(TeacherAssignment.objects.order_by("pk").values()), assignments_before)

    def test_partial_existing_instructor_cannot_be_adopted(self):
        Lesson.objects.filter(pk=self.lessons[0].pk).update(instructor=self.teacher)
        with self.assertRaisesRegex(state.RepairError, "partial_authorship"), transaction.atomic():
            self.execute()

    def test_named_cell_author_even_same_teacher_requires_exact_review(self):
        LessonMark.objects.filter(lesson=self.lessons[0]).update(entered_by=self.teacher)
        self.assert_hold()

    def test_inactive_actor_is_refused(self):
        get_user_model().objects.filter(pk=self.org.owner_id).update(is_active=False)
        self.assert_hold()

    def test_exact_source_group_anchor_hash_is_mandatory(self):
        self.pins["bridge"][0]["source_row_hash"] = "c" * 64
        with self.assertRaisesRegex(state.RepairError, "source_group_bridge_changed"), transaction.atomic():
            self.execute()

    def test_raw_codec_is_explicit_but_native_graph_keeps_microseconds(self):
        lesson = self.lessons[0]
        instant = datetime.datetime(2026, 10, 1, 8, 0, 0, 123456, tzinfo=datetime.timezone.utc)
        LessonMark.objects.filter(lesson=lesson).update(created_at=instant, updated_at=instant)
        with transaction.atomic():
            raw = state.raw_projection(LessonMark.objects.filter(lesson=lesson), self.pins["mark_fields"])[0]
            full = state.rows(LessonMark.objects.filter(lesson=lesson))[0]
        self.assertEqual(raw["updated_at"], "2026-10-01T08:00:00.123Z")
        self.assertEqual(full["updated_at"], "2026-10-01T08:00:00.123456+00:00")
        zero = LessonMark.objects.filter(score=0).first()
        with transaction.atomic():
            raw_zero = state.raw_projection(LessonMark.objects.filter(pk=zero.pk), self.pins["mark_fields"])[0]
        self.assertEqual(raw_zero["score"], "0.00")

    def test_submillisecond_change_still_invalidates_native_fresh_baseline(self):
        marker = LessonMark.objects.filter(lesson=self.lessons[0]).first()
        first = datetime.datetime(2026, 10, 1, 8, 0, 0, 123456, tzinfo=datetime.timezone.utc)
        LessonMark.objects.filter(pk=marker.pk).update(updated_at=first)
        with transaction.atomic():
            self.pins["marks_sha256"] = state.digest(
                state.raw_projection(LessonMark.objects.filter(lesson__in=self.lessons), self.pins["mark_fields"])
            )
        baseline = self.execute()["baseline"]
        LessonMark.objects.filter(pk=marker.pk).update(updated_at=first.replace(microsecond=123457))
        with self.assertRaisesRegex(state.RepairError, "fresh_baseline"), transaction.atomic():
            self.execute(apply=True, expected_baseline=baseline)
