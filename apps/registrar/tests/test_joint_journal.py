"""Joint contact-kind selection and real, all-or-nothing physical writes."""

import datetime
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.organizations.models import OrgUnit
from apps.registrar import gradebook, joint_journal
from apps.registrar.models import CourseOffering, Enrollment, JournalShare, Lesson, LessonMark, ScheduleSlot
from apps.registrar.page_contexts import journal_list_context
from apps.workload.constants import TaskStatus
from apps.workload.models import TeacherAssignment
from apps.workload.tests.factories import TEACHER_PERMS, activate_member, make_org, make_row, make_structure, make_task

User = get_user_model()


class JointJournalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("joint-kind")
        cls.stack = make_structure(cls.org, code="235IT")
        cls.teacher = User.objects.create_user("joint-teacher")
        activate_member(cls.org, cls.teacher, "teacher", permissions=TEACHER_PERMS)
        cls.task = make_task(cls.org, cls.stack["chair"], status=TaskStatus.AMENDED)
        cls.row = make_row(cls.task, cls.stack, lecture_total=30, seminar_total=30)
        cls.group2 = OrgUnit.objects.create(
            organization=cls.org,
            name="235IT-2",
            slug="joint-kind-group2",
            unit_type="group",
            parent=cls.stack["specialty"],
        )
        cls.row.groups.add(cls.group2)
        for kind in ("lecture", "seminar"):
            TeacherAssignment.objects.create(
                organization=cls.org, row=cls.row, teacher=cls.teacher, activity=kind, hours=30
            )
        cls.offerings, cls.enrollments = [], []
        for index, group in enumerate((cls.stack["group"], cls.group2)):
            offering = CourseOffering.objects.create(
                organization=cls.org,
                subject=cls.stack["subject"],
                period=cls.stack["period"],
                group=group,
                instructor=cls.teacher,
                lesson_hours=60,
            )
            cls.offerings.append(offering)
            student = User.objects.create_user(f"joint-student-{index}")
            activate_member(cls.org, student, "student", permissions=[])
            cls.enrollments.append(Enrollment.objects.create(organization=cls.org, offering=offering, student=student))
            for kind in ("lecture", "seminar"):
                ScheduleSlot.objects.create(
                    organization=cls.org,
                    offering=offering,
                    kind=kind,
                    weekday=timezone.localdate().isoweekday(),
                    start_time=datetime.time(8 if kind == "lecture" else 10 + index, 30),
                    end_time=datetime.time(10 if kind == "lecture" else 12 + index),
                )

    def select(self):
        return joint_journal.selections(organization=self.org, user=self.teacher)

    def args(self, kind="lecture"):
        return dict(organization=self.org, user=self.teacher, source_row_id=self.row.pk, kind=kind)

    def lessons(self, kind="lecture"):
        return [
            Lesson.objects.create(
                organization=self.org,
                offering=offering,
                instructor=self.teacher,
                date=timezone.localdate(),
                kind=kind,
                hours=2,
            )
            for offering in self.offerings
        ]

    def entries(self, lessons, *, score=""):
        return [
            {"lesson_id": lesson.pk, "enrollment_id": enrollment.pk, "status": "present", "score": score}
            for lesson, enrollment in zip(lessons, self.enrollments)
        ]

    def test_lecture_joint_and_seminars_separate_then_joint_per_kind(self):
        (joint,) = self.select()
        self.assertEqual(joint.kind, "lecture")
        self.assertEqual(joint.offering_ids, frozenset(o.pk for o in self.offerings))
        ScheduleSlot.objects.filter(kind="seminar").update(start_time="10:30", end_time="12:00")
        self.assertEqual({item.kind for item in self.select()}, {"lecture", "seminar"})

    def test_official_15_times_two_seminars_stay_separate_even_with_identical_schedule(self):
        ScheduleSlot.objects.filter(kind="seminar").update(start_time="10:30", end_time="12:00")
        self.row.seminar_plan = 15
        self.row.subgroup_count = 2
        self.row.save(update_fields=["seminar_plan", "subgroup_count"])
        self.assertEqual({item.kind for item in self.select()}, {"lecture"})
        self.assertEqual(len(self.context()["offerings"]), 3)
        seminars = self.context(kind="seminar")["offerings"]
        self.assertEqual({entry.pk for entry in seminars}, {offering.pk for offering in self.offerings})
        self.assertTrue(all(getattr(entry, "joint_selection", None) is None for entry in seminars))
        with self.assertRaises(PermissionDenied):
            joint_journal.resolve(**self.args("seminar"))
        self.assertEqual(Enrollment.objects.count(), 2)

    def test_one_full_15_hour_contact_per_kind_can_join(self):
        ScheduleSlot.objects.filter(kind="seminar").update(start_time="10:30", end_time="12:00")
        TeacherAssignment.objects.filter(row=self.row, activity="seminar").update(hours=15)
        self.row.seminar_plan = self.row.seminar_total = 15
        self.row.total_hours = 45
        self.row.save(update_fields=["seminar_plan", "seminar_total", "total_hours"])
        self.assertEqual({item.kind for item in self.select()}, {"lecture", "seminar"})
        self.assertEqual(len(self.context(kind="seminar")["offerings"]), 1)

    def test_inconsistent_kind_multiplier_total_or_missing_explicit_plan_does_not_join(self):
        self.row.union_count = 2
        self.row.save(update_fields=["union_count"])
        self.assertEqual(self.select(), [])
        self.row.union_count = 1
        self.row.lecture_plan = 15  # total remains 30: two contacts, despite multiplier=1
        self.row.save(update_fields=["union_count", "lecture_plan"])
        self.assertEqual(self.select(), [])
        self.row.lecture_plan = 0  # per_group_hours fallback is not explicit joint proof
        self.row.save(update_fields=["lecture_plan"])
        self.assertEqual(self.select(), [])

    def test_partial_kind_allocation_never_creates_joint_whole_roster(self):
        TeacherAssignment.objects.filter(row=self.row, activity="lecture").update(hours=15)
        self.assertEqual(self.select(), [])
        with self.assertRaises(PermissionDenied):
            joint_journal.resolve(**self.args())

    def test_full_roster_preserves_both_physical_enrollment_ids(self):
        rows = joint_journal.roster(**self.args())
        self.assertEqual({row.pk for row in rows}, {enrollment.pk for enrollment in self.enrollments})
        self.assertEqual({row.offering_id for row in rows}, {offering.pk for offering in self.offerings})

    def test_no_same_name_or_schedule_only_authority(self):
        self.row.groups.remove(self.group2)
        self.assertEqual(self.select(), [])

    def test_draft_and_subgroup_notes_never_combine(self):
        for update in ({"groups_note": "yarımqrup 1"}, {"groups_note": self.group2.name}):
            TeacherAssignment.objects.filter(row=self.row, activity="lecture").update(**update)
            self.assertEqual(self.select(), [])
        TeacherAssignment.objects.filter(row=self.row, activity="lecture").update(groups_note="")
        self.task.status = TaskStatus.DRAFT
        self.task.save(update_fields=["status"])
        self.assertEqual(self.select(), [])

    def test_level_roster_partition_blocks_even_owner_expanded_scope(self):
        share = JournalShare.objects.create(
            organization=self.org, offering=self.offerings[0], teacher=self.teacher, kinds=["lecture"]
        )
        share.enrollments.add(self.enrollments[0])
        self.assertEqual(self.select(), [])

    def test_missing_parked_or_extra_separate_schedule_never_combines(self):
        slot = ScheduleSlot.objects.get(offering=self.offerings[1], kind="lecture")
        slot.is_parked = True
        slot.save(update_fields=["is_parked"])
        self.assertEqual(self.select(), [])

    def test_mark_write_reaches_both_rosters_and_preserves_history(self):
        historical = Lesson.objects.create(
            organization=self.org,
            offering=self.offerings[0],
            date=timezone.localdate() - datetime.timedelta(days=30),
            kind="lecture",
            hours=14,
            instructor=self.teacher,
        )
        original_ids = {e.pk for e in self.enrollments}
        lessons = self.lessons()
        entries = self.entries(lessons)
        self.assertEqual(joint_journal.save_marks(**self.args(), entries=entries)["written"], 2)
        self.assertEqual(set(LessonMark.objects.values_list("enrollment_id", flat=True)), original_ids)
        historical.refresh_from_db()
        self.assertEqual(historical.hours, 14)
        self.assertEqual(Lesson.objects.count(), 3)
        joint_journal.save_marks(**self.args(), entries=entries)
        self.assertEqual(LessonMark.objects.count(), 2)

    def test_invalid_second_score_rolls_back_first_real_write(self):
        ScheduleSlot.objects.filter(kind="seminar").update(start_time="10:30", end_time="12:00")
        entries = self.entries(self.lessons("seminar"), score="8")
        last = joint_journal.resolve(**self.args("seminar")).offerings[-1]
        index = next(i for i, enrollment in enumerate(self.enrollments) if enrollment.offering_id == last.pk)
        entries[index]["score"] = "11"
        with self.assertRaises(joint_journal.JointJournalError):
            joint_journal.save_marks(**self.args("seminar"), entries=entries)
        self.assertFalse(LessonMark.objects.exists())
        entries[index]["score"] = "9"
        self.assertEqual(joint_journal.save_marks(**self.args("seminar"), entries=entries)["written"], 2)
        self.assertEqual(set(LessonMark.objects.values_list("score", flat=True)), {Decimal(8), Decimal(9)})

    def test_cross_pair_and_wrong_kind_fail_without_writes(self):
        lessons = self.lessons()
        entries = self.entries(lessons)
        entries[1]["enrollment_id"] = self.enrollments[0].pk
        with self.assertRaises(joint_journal.JointJournalError):
            joint_journal.save_marks(**self.args(), entries=entries)
        entries = self.entries(self.lessons("seminar"))
        with self.assertRaises(joint_journal.JointJournalError):
            joint_journal.save_marks(**self.args(), entries=entries)
        self.assertFalse(LessonMark.objects.exists())

    def test_revoked_membership_and_foreign_tenant_are_rechecked(self):
        from apps.organizations.models import Membership

        self.assertEqual(len(self.select()), 1)
        Membership.objects.filter(organization=self.org, user=self.teacher).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            joint_journal.save_marks(**self.args(), entries=[])
        with self.assertRaises(PermissionDenied):
            joint_journal.roster(**{**self.args(), "organization": make_org("joint-other")})

    def test_second_lesson_failure_rolls_back_first_canonical_creation(self):
        slot = ScheduleSlot.objects.get(offering=self.offerings[0], kind="lecture")
        original = gradebook.create_lesson
        calls = []

        def create(**fields):
            calls.append(fields["offering"].pk)
            if len(calls) == 2:
                raise gradebook.LessonRuleError("second member rejected")
            return original(**fields)

        with patch.object(gradebook, "create_lesson", side_effect=create):
            with self.assertRaises(gradebook.LessonRuleError):
                joint_journal.create_lessons(
                    **self.args(),
                    date=timezone.localdate(),
                    topic="Joint topic",
                    slot_signature=joint_journal._signature(slot),
                )
        self.assertEqual(len(calls), 2)
        self.assertFalse(Lesson.objects.exists())

    def test_single_create_action_creates_each_real_lesson_without_moving_ids(self):
        slot = ScheduleSlot.objects.get(offering=self.offerings[0], kind="lecture")
        created = joint_journal.create_lessons(
            **self.args(), date=timezone.localdate(), topic="Joint topic", slot_signature=joint_journal._signature(slot)
        )
        self.assertEqual({lesson.offering_id for lesson in created}, {o.pk for o in self.offerings})
        self.assertEqual({lesson.instructor_id for lesson in created}, {self.teacher.pk})

    def context(self, **params):
        request = RequestFactory().get("/jurnal/", {"year": "", **params})
        request.user, request.organization = self.teacher, self.org
        return journal_list_context(self.teacher, request)

    def _client(self):
        client = Client()
        client.force_login(self.teacher)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def test_list_has_one_joint_lecture_and_two_separate_seminars(self):
        entries = self.context()["offerings"]
        self.assertEqual(len(entries), 3)
        joint = [entry for entry in entries if getattr(entry, "joint_selection", None)]
        self.assertEqual(len(joint), 1)
        self.assertEqual(joint[0].journal_entry_kind, "lecture")
        self.assertEqual(joint[0].student_count, 2)
        self.assertIn(self.group2.name, joint[0].journal_group_name)
        seminars = [entry for entry in entries if entry.journal_entry_kind == "seminar"]
        self.assertEqual({entry.pk for entry in seminars}, {offering.pk for offering in self.offerings})
        self.assertTrue(all("?kind=seminar" in entry.journal_entry_url for entry in seminars))
        self.assertEqual(len(self.context(kind="lecture")["offerings"]), 1)
        self.assertEqual(len(self.context(kind="seminar")["offerings"]), 2)

    def test_joint_seminar_list_and_single_http_form_writes_both_students(self):
        ScheduleSlot.objects.filter(kind="seminar").update(start_time="10:30", end_time="12:00")
        self.assertEqual(len(self.context()["offerings"]), 2)
        self.assertEqual(len(self.context(kind="seminar")["offerings"]), 1)
        lessons = self.lessons("seminar")
        client = self._client()
        url = reverse("registrar:joint_journal", args=[self.row.pk, "seminar"])
        response = client.get(url)
        self.assertEqual(response.status_code, 200)
        for lesson, enrollment in zip(lessons, self.enrollments):
            self.assertContains(response, f"att__{lesson.pk}__{enrollment.pk}")
        data = {"action": "save_marks"}
        for entry in self.entries(lessons, score="8"):
            lesson_id, enrollment_id = entry["lesson_id"], entry["enrollment_id"]
            # Entering a score also records presence, as in the ordinary grid.
            data[f"att__{lesson_id}__{enrollment_id}"] = ""
            data[f"score__{lesson_id}__{enrollment_id}"] = "8"
        response = client.post(url, data)
        self.assertRedirects(response, url)
        self.assertEqual(LessonMark.objects.count(), 2)

    def test_single_http_add_creates_both_lessons_and_bad_slot_is_safe(self):
        client = self._client()
        url = reverse("registrar:joint_journal", args=[self.row.pk, "lecture"])
        slot = ScheduleSlot.objects.get(offering=self.offerings[0], kind="lecture")
        response = client.post(
            url, {"action": "add_lesson", "date": timezone.localdate(), "topic": "Shared", "slot_id": slot.pk}
        )
        self.assertRedirects(response, url)
        self.assertEqual(Lesson.objects.count(), 2)
        response = client.post(url, {"action": "add_lesson", "slot_id": "bad"})
        self.assertRedirects(response, url)
        self.assertEqual(Lesson.objects.count(), 2)

    def test_locked_second_member_cell_rolls_back_new_first_member_mark(self):
        lessons = self.lessons()
        last = joint_journal.resolve(**self.args()).offerings[-1]
        index = next(i for i, enrollment in enumerate(self.enrollments) if enrollment.offering_id == last.pk)
        locked = LessonMark.objects.create(
            organization=self.org,
            lesson=lessons[index],
            enrollment=self.enrollments[index],
            status="absent",
            entered_by=None,
        )
        with self.assertRaises(joint_journal.JointJournalError):
            joint_journal.save_marks(**self.args(), entries=self.entries(lessons))
        self.assertEqual(list(LessonMark.objects.values_list("pk", flat=True)), [locked.pk])
        locked.refresh_from_db()
        self.assertEqual(locked.status, "absent")

    def test_journal_lock_refuses_entire_joint_write_and_disables_http_grid(self):
        lessons = self.lessons()
        scheme = gradebook.ensure_assessment_scheme(offering=self.offerings[-1])
        scheme.is_published, scheme.approval_status = True, "approved"
        scheme.save(update_fields=["is_published", "approval_status"])
        with self.assertRaises(joint_journal.JointJournalError):
            joint_journal.save_marks(**self.args(), entries=self.entries(lessons))
        self.assertFalse(LessonMark.objects.exists())
        response = self._client().get(reverse("registrar:joint_journal", args=[self.row.pk, "lecture"]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "yalnız oxunur")
        self.assertNotContains(response, 'name="att__')

    def test_duplicate_historical_sessions_keep_distinct_lesson_cells(self):
        from apps.registrar.joint_journal_views import _grid

        first = self.lessons()
        duplicate = self.lessons()
        columns, rows = _grid(joint_journal.resolve(**self.args()), self.teacher)
        self.assertEqual(len(columns), 4)
        cell_ids = {cell["lesson"].pk for row in rows for cell in row["cells"] if cell}
        self.assertEqual(cell_ids, {lesson.pk for lesson in first + duplicate})

    def test_slot_teacher_override_and_mixed_sector_never_combine(self):
        other = User.objects.create_user("joint-other-teacher")
        activate_member(self.org, other, "teacher", permissions=TEACHER_PERMS)
        ScheduleSlot.objects.filter(offering=self.offerings[1], kind="lecture").update(instructor=other)
        self.assertEqual(self.select(), [])
        ScheduleSlot.objects.filter(offering=self.offerings[1], kind="lecture").update(instructor=None)
        OrgUnit.objects.filter(pk=self.stack["group"].pk).update(settings={"sector": "az"})
        OrgUnit.objects.filter(pk=self.group2.pk).update(settings={"sector": "en"})
        self.assertEqual(self.select(), [])

    def test_rooms_follow_joint_timetable_rule_but_conflicting_rooms_do_not_merge(self):
        ScheduleSlot.objects.filter(offering=self.offerings[0], kind="lecture").update(room="101")
        self.assertEqual(len(self.select()), 1)  # another member's blank room is compatible
        ScheduleSlot.objects.filter(offering=self.offerings[1], kind="lecture").update(room="102")
        self.assertEqual(self.select(), [])

    def test_excused_status_is_read_only_and_unchanged_full_save_preserves_it(self):
        ScheduleSlot.objects.filter(kind="seminar").update(start_time="10:30", end_time="12:00")
        lessons = self.lessons("seminar")
        excused = LessonMark.objects.create(
            organization=self.org,
            lesson=lessons[0],
            enrollment=self.enrollments[0],
            status="excused",
            score=7,
            entered_by=self.teacher,
        )
        client = self._client()
        url = reverse("registrar:joint_journal", args=[self.row.pk, "seminar"])
        response = client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, f'name="att__{lessons[0].pk}__{self.enrollments[0].pk}"')
        self.assertNotContains(response, f'name="score__{lessons[0].pk}__{self.enrollments[0].pk}"')
        response = client.post(
            url,
            {
                "action": "save_marks",
                f"att__{lessons[1].pk}__{self.enrollments[1].pk}": "present",
                f"score__{lessons[1].pk}__{self.enrollments[1].pk}": "8",
            },
        )
        self.assertRedirects(response, url)
        excused.refresh_from_db()
        self.assertEqual((excused.status, excused.score), ("excused", Decimal(7)))
        with self.assertRaises(joint_journal.JointJournalError):
            joint_journal.save_marks(**self.args("seminar"), entries=self.entries(lessons, score="8"))
        excused.refresh_from_db()
        self.assertEqual((excused.status, excused.score), ("excused", Decimal(7)))

    def test_more_than_window_duplicate_sessions_never_align_by_member_ordinal(self):
        from apps.registrar.joint_journal_views import _grid

        for _ in range(14):
            self.lessons()
        columns, rows = _grid(joint_journal.resolve(**self.args()), self.teacher)
        self.assertEqual(len(columns), 12)
        # Every duplicate is its own real Lesson column; no physical member's
        # nth historical lesson is silently paired with another member's nth.
        for index in range(len(columns)):
            self.assertEqual(sum(row["cells"][index] is not None for row in rows), 1)
