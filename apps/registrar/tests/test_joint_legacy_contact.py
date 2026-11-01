"""Imported all-zero plans, merged rosters and truthful per-kind teaching counts."""

import datetime
from decimal import Decimal

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.template.loader import render_to_string
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.organizations.models import OrgUnit
from apps.registrar import gradebook, joint_journal
from apps.registrar.joint_journal_records import summaries
from apps.registrar.joint_journal_views import _grid
from apps.registrar.models import CourseOffering, Enrollment, Lesson, LessonMark, ScheduleSlot
from apps.workload.models import TeacherAssignment
from apps.workload.tests.factories import activate_member

from . import test_joint_journal as fixture

User = get_user_model()


@override_settings(REGISTRAR_JOINT_JOURNAL_UI_ENABLED=True)
class LegacyJointContactTests(TestCase):
    select = fixture.JointJournalTests.select
    args = fixture.JointJournalTests.args
    context = fixture.JointJournalTests.context
    _client = fixture.JointJournalTests._client
    lessons = fixture.JointJournalTests.lessons

    @classmethod
    def setUpTestData(cls):
        fixture.JointJournalTests.setUpTestData.__func__(cls)
        activate_member(
            cls.org,
            cls.org.owner,
            "joint-test-corrector",
            permissions=["grade.input", "journal.teacher_full_edit", "journal.correct", "course.view"],
        )
        cls.row.lecture_plan = cls.row.seminar_plan = cls.row.lab_plan = 0
        cls.row.seminar_total = 15
        cls.row.total_hours = 45
        cls.row.student_count = 40
        cls.row.save()
        TeacherAssignment.objects.filter(row=cls.row, activity="seminar").update(hours=15)
        for index, offering in enumerate(cls.offerings):
            offering.group.name = f"235 İT-{index + 1} az"
            offering.group.settings = {"sector": "az", "degree_level": "bachelor", "education_form": "full_time"}
            offering.group.save(update_fields=["name", "settings"])
            for n in range(18):
                student = User.objects.create_user(f"legacy-joint-{index}-{n}")
                activate_member(cls.org, student, "student", permissions=[])
                Enrollment.objects.create(organization=cls.org, offering=offering, student=student)
        ScheduleSlot.objects.filter(kind="lecture").update(
            weekday=3, start_time="16:55", end_time="18:25", week_type="odd", room="32"
        )
        ScheduleSlot.objects.filter(kind="seminar").update(
            weekday=4, start_time="15:15", end_time="16:45", week_type="odd", room="22"
        )
        ScheduleSlot.objects.create(
            organization=cls.org,
            offering=cls.offerings[0],
            kind="seminar",
            weekday=4,
            start_time="16:55",
            end_time="18:25",
            week_type="odd",
            room="22",
        )

    def summary(self):
        joint = joint_journal.resolve(**self.args())
        return summaries([joint], self.teacher)[joint.source_row_id, joint.kind]

    def test_zero_plan_full_allocation_lecture_one38_roster_seminars_separate(self):
        (joint,) = self.select()
        self.assertEqual(joint.kind, "lecture")
        self.assertEqual(len(joint_journal.roster(**self.args())), 38)
        entries = self.context()["offerings"]
        self.assertEqual(len(entries), 3)
        (merged,) = [entry for entry in entries if entry.joint_selection]
        self.assertEqual(merged.student_count, 38)
        self.assertIn("235 İT-1 az", merged.journal_group_name)
        self.assertIn("235 İT-2 az", merged.journal_group_name)
        response = self._client().get(reverse("registrar:joint_journal", args=[self.row.pk, "lecture"]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["rows"]), 38)
        self.assertContains(response, "joint-grid-scroll")
        self.assertEqual(len([entry for entry in entries if entry.journal_entry_kind == "seminar"]), 2)

    def test_english_same_slot_not_in_official_pair_and_mixed_sector_rejected(self):
        group = OrgUnit.objects.create(
            organization=self.org,
            name="235 İT ing",
            slug="legacy-joint-en",
            unit_type="group",
            parent=self.stack["specialty"],
            settings={"sector": "en", "degree_level": "bachelor", "education_form": "full_time"},
        )
        english = CourseOffering.objects.create(
            organization=self.org,
            subject=self.stack["subject"],
            period=self.stack["period"],
            group=group,
            instructor=self.teacher,
            lesson_hours=45,
        )
        ScheduleSlot.objects.create(
            organization=self.org,
            offering=english,
            kind="lecture",
            weekday=3,
            start_time="16:55",
            end_time="18:25",
            week_type="odd",
            room="32",
        )
        self.assertNotIn(english.pk, self.select()[0].offering_ids)
        self.row.groups.add(group)
        self.assertEqual(self.select(), [])

    def test_partial_teacher_split_multiplier_mixed_plan_and_bad_totals_hold(self):
        assignment = TeacherAssignment.objects.get(row=self.row, activity="lecture")
        assignment.hours = 15
        assignment.save(update_fields=["hours"])
        self.assertEqual(self.select(), [])

        assignment.hours = 30
        assignment.save(update_fields=["hours"])
        self.row.union_count = 2
        self.row.save(update_fields=["union_count"])
        self.assertEqual(self.select(), [])
        self.row.union_count = 1
        self.row.seminar_plan = 15
        self.row.save(update_fields=["union_count", "seminar_plan"])
        self.assertEqual(self.select(), [])
        self.row.seminar_plan = 0
        self.row.total_hours = 1
        self.row.save(update_fields=["seminar_plan", "total_hours"])
        self.assertEqual(self.select(), [])

    def test_missing_sector_or_explicit_english_name_with_wrong_az_metadata_holds(self):
        second = self.offerings[1].group
        original = dict(second.settings)
        for settings in ({}, {"sector": ""}, {"sector": "az", "language_sector": "en"}):
            second.settings = settings
            second.save(update_fields=["settings"])
            self.assertEqual(self.select(), [])
        second.settings = original
        second.name = "235 İT ing"
        second.save(update_fields=["settings", "name"])
        self.assertEqual(self.select(), [])
        second.name = "235İTing"
        second.save(update_fields=["name"])
        self.assertEqual(self.select(), [])
        second.name = "235 İT-2 az"
        second.settings = {}
        second.save(update_fields=["settings", "name"])
        first = self.offerings[0].group
        first.settings = {}
        first.save(update_fields=["settings"])
        self.assertEqual(self.select(), [])

    def test_same_schedule_seminar_joins_only_if_one_whole_contact(self):
        ScheduleSlot.objects.filter(offering=self.offerings[0], kind="seminar", start_time="16:55").delete()
        self.assertEqual({joint.kind for joint in self.select()}, {"lecture", "seminar"})
        self.row.subgroup_count = 2
        self.row.seminar_total = 30
        self.row.total_hours = 60
        self.row.save(update_fields=["subgroup_count", "seminar_total", "total_hours"])
        TeacherAssignment.objects.filter(row=self.row, activity="seminar").update(hours=30)
        self.assertEqual({joint.kind for joint in self.select()}, {"lecture"})

    def test_common_anonymous_core5_plus_owned1_excludes_extra5_from_primary(self):
        own = self.lessons()
        for count, offering in zip((10, 5), self.offerings):
            for n in range(count):
                Lesson.objects.create(
                    organization=self.org,
                    offering=offering,
                    kind="lecture",
                    hours=2,
                    date=timezone.localdate() - datetime.timedelta(days=n + 1),
                )
        Lesson.objects.create(
            organization=self.org,
            offering=self.offerings[0],
            instructor=self.teacher,
            date=timezone.localdate(),
            kind="seminar",
            hours=3,
        )
        before = list(Lesson.objects.order_by("pk").values())
        record = self.summary()
        self.assertEqual((record["own_lessons"], record["own_hours"]), (1, 2))
        self.assertEqual((record["common_lessons"], record["common_hours"]), (6, 12))
        self.assertEqual(
            [(r["group"].pk, r["anonymous_lessons"], r["anonymous_hours"]) for r in record["history"]],
            [(self.offerings[0].group_id, 5, 10)],
        )
        entries = self.context()["offerings"]
        (merged,) = [entry for entry in entries if entry.joint_selection]
        self.assertEqual((merged.journal_own_lessons, merged.journal_own_hours), (1, 2))
        self.assertEqual((merged.journal_common_lessons, merged.journal_common_hours), (6, 12))
        card = render_to_string("registrar/partials/_journal_teacher_record.html", {"offering": merged})
        self.assertIn("Birgə qeydə alınmış dərslər: 6 dərs / 12 saat", card)
        self.assertIn("Adınıza keçirilmiş birgə dərslər: 1 dərs / 2 saat", card)
        response = self._client().get(reverse("registrar:joint_journal", args=[self.row.pk, "lecture"]))
        self.assertContains(response, "Birgə qeydə alınmış dərslər: 6 dərs / 12 saat")
        self.assertContains(response, "Adınıza keçirilmiş birgə dərslər: 1 dərs / 2 saat")
        seminars = {entry.pk: entry for entry in entries if entry.journal_entry_kind == "seminar"}
        self.assertEqual(seminars[self.offerings[0].pk].journal_own_hours, 3)
        self.assertEqual(seminars[self.offerings[1].pk].journal_own_hours, 0)
        self.assertEqual(before, list(Lesson.objects.order_by("pk").values()))
        self.assertEqual(
            set(Lesson.objects.filter(pk__in=[x.pk for x in own]).values_list("instructor_id", flat=True)),
            {self.teacher.pk},
        )

    def test_same_date_different_topic_hours_or_duplicate_never_become_one_session(self):
        lessons = self.lessons()
        second = lessons[1]
        for field, value in (("topic", "A different lesson"), ("hours", 3)):
            original = getattr(second, field)
            setattr(second, field, value)
            second.save(update_fields=[field])
            record = self.summary()
            self.assertEqual(record["common_lessons"], 0)
            self.assertEqual(record["own_lessons"], 0)
            self.assertEqual(sum(row["separate_own_lessons"] for row in record["history"]), 2)
            columns, rows = _grid(joint_journal.resolve(**self.args()), self.teacher)
            self.assertEqual(len(columns), 2)
            self.assertTrue(all(sum(row["cells"][i] is not None for row in rows) == 19 for i in range(2)))
            setattr(second, field, original)
            second.save(update_fields=[field])
        Lesson.objects.create(
            organization=self.org,
            offering=self.offerings[0],
            instructor=self.teacher,
            date=timezone.localdate(),
            kind="lecture",
            hours=2,
        )
        self.assertEqual(self.summary()["own_lessons"], 0)

    def test_anonymous_duplicate_or_different_room_keeps_physical_history(self):
        first, second = self.lessons()
        Lesson.objects.filter(pk__in=[first.pk, second.pk]).update(instructor=None)
        room = apps.get_model("exams", "ExamRoom").objects.create(organization=self.org, name="Room", code="room")
        second.room = room
        second.save(update_fields=["room"])
        record = self.summary()
        self.assertEqual(record["common_lessons"], 0)
        self.assertEqual(sum(r["anonymous_lessons"] for r in record["history"]), 2)
        second.room = None
        second.save(update_fields=["room"])
        self.assertEqual(self.summary()["common_lessons"], 1)
        first.refresh_from_db()
        first.pk = None
        first.save()
        record = self.summary()
        self.assertEqual((record["common_lessons"], record["own_lessons"]), (0, 0))
        self.assertEqual(sum(r["anonymous_lessons"] for r in record["history"]), 3)

    def test_common_seminar_uses_stored_four_hours_without_source_guess(self):
        for day in (1, 2):
            for offering in self.offerings:
                Lesson.objects.create(
                    organization=self.org,
                    offering=offering,
                    kind="seminar",
                    hours=2,
                    date=timezone.localdate() - datetime.timedelta(days=day),
                )
        joint = joint_journal.JointJournal(self.row.pk, "seminar", tuple(self.offerings))
        record = summaries([joint], self.teacher)[joint.source_row_id, joint.kind]
        self.assertEqual((record["common_lessons"], record["common_hours"], record["own_lessons"]), (2, 4, 0))
        self.assertEqual(record["history"], [])

    def test_unsupported_lecture_zero_and_number_never_become_empty_in_joint_or_normal(self):
        lessons = self.lessons()
        marks = [
            LessonMark.objects.create(
                organization=self.org,
                lesson=lesson,
                enrollment=enrollment,
                status="present",
                score=value,
                entered_by=self.teacher,
            )
            for lesson, enrollment, value in zip(lessons, self.enrollments, (0, 7))
        ]
        before = list(LessonMark.objects.order_by("pk").values())
        columns, rows = _grid(joint_journal.resolve(**self.args()), self.teacher)
        self.assertEqual(len(columns), 1)
        self.assertFalse(any(cell["writable"] for row in rows for cell in row["cells"] if cell and cell["mark"]))
        for mark in marks:
            journal = gradebook.get_offering_journal(offering=mark.lesson.offering)
            cell = next(
                cell for row in journal["rows"] for cell in row["cells"] if cell["mark"] and cell["mark"].pk == mark.pk
            )
            self.assertFalse(cell["writable"])
            self.assertEqual(cell["lock_reason"], "unsupported_score")
            # Real lecture forms omit score inputs. Whole-form unchanged saves are no-ops.
            report = gradebook.save_marks(
                offering=mark.lesson.offering,
                by_user=self.teacher,
                report=True,
                entries=[dict(lesson_id=mark.lesson_id, enrollment_id=mark.enrollment_id, status="present", score="")],
            )
            self.assertEqual(report["written"], 0)
            changed = gradebook.save_marks(
                offering=mark.lesson.offering,
                by_user=self.teacher,
                report=True,
                entries=[dict(lesson_id=mark.lesson_id, enrollment_id=mark.enrollment_id, status="absent", score="")],
            )
            self.assertEqual(changed["locked"], 1)
        with self.assertRaises(joint_journal.JointJournalError):
            joint_journal.save_marks(
                **self.args(),
                entries=[
                    dict(lesson_id=marks[0].lesson_id, enrollment_id=marks[0].enrollment_id, status="present", score="")
                ],
            )
        self.assertEqual(before, list(LessonMark.objects.order_by("pk").values()))
        self.assertEqual(set(LessonMark.objects.values_list("score", flat=True)), {Decimal(0), Decimal(7)})

    def test_legacy_number_rim_full_edit_still_requires_reason_and_existing_audit(self):
        lesson = self.lessons()[0]
        mark = LessonMark.objects.create(
            organization=self.org,
            lesson=lesson,
            enrollment=self.enrollments[0],
            status="present",
            score=0,
            entered_by=self.teacher,
        )
        rejected = gradebook.save_marks(
            offering=lesson.offering,
            by_user=self.org.owner,
            entries=[dict(lesson_id=lesson.pk, enrollment_id=mark.enrollment_id, status="present", score="invalid")],
            full_edit=True,
            full_reason="Reviewed source requires retaining the stored number",
            report=True,
        )
        self.assertEqual(rejected["rejected"], 1)
        mark.refresh_from_db()
        self.assertEqual(mark.score, Decimal(0))
        entries = [dict(lesson_id=lesson.pk, enrollment_id=mark.enrollment_id, status="absent", score="")]
        no_reason = gradebook.save_marks(
            offering=lesson.offering, by_user=self.org.owner, entries=entries, full_edit=True, report=True
        )
        self.assertEqual(no_reason["reason_required"], 1)
        mark.refresh_from_db()
        self.assertEqual(mark.score, Decimal(0))
        written = gradebook.save_marks(
            offering=lesson.offering,
            by_user=self.org.owner,
            entries=entries,
            full_edit=True,
            full_reason="Reviewed attendance correction with supporting source",
            report=True,
        )
        self.assertEqual(written["written"], 1)
        mark.refresh_from_db()
        self.assertEqual((mark.status, mark.score), ("absent", None))

    def test_blank_unknown_does_not_create_presence_or_absence(self):
        self.lessons()
        response = self._client().post(
            reverse("registrar:joint_journal", args=[self.row.pk, "lecture"]),
            {"action": "save_marks"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(LessonMark.objects.exists())
        with self.assertRaises(PermissionDenied):
            joint_journal.resolve(**self.args("seminar"))
