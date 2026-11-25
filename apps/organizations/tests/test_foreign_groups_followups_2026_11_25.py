"""Əcnəbi qrupları — sahibin 2026-11-25 əlavə istəkləri.

* «Qrup növü» seçimi (adi / əcnəbi) — yadda saxlananda şöbəyə əhatə avtomatik;
* «Tələbə əlavə et» əcnəbi qrupunda bütün universitetdən namizəd (boş axtarışda da); başqa bölmənin tələbəsi yalnız
  «əlavə olaraq» (məcburi köçürmə yox);
* «Qrupu məzun et» — bir əmrlə;
* müəllim eyni saatda iki əcnəbi qrupunda dərs (cədvəl toqquşması deyil), adi qrupla yenə toqquşma.
"""

from __future__ import annotations

import datetime

from django.urls import reverse

from apps.organizations.group_kind import KIND_FOREIGN, foreign_group_ids, is_foreign, kind_of
from apps.organizations.models import Membership, OrgUnit
from apps.organizations.tests.test_foreign_students_office_2026_11_25 import ForeignOfficeBase
from apps.registrar import schedule, schedule_conflicts
from apps.registrar.models import CourseOffering, ScheduleSlot, StudentAcademicRecord
from core.constants import OrgUnitType
from core.rls import bypass_rls


class GroupKindTest(ForeignOfficeBase):
    def post_group(self, **data):
        with bypass_rls():
            return self.client_for(self.owner).post(
                reverse("organizations:group_action", kwargs={"slug": self.org.slug}),
                {"action": "save_group", "specialty": str(self.chair.pk), "course_year": "1", **data},
            )

    def test_name_fallback_and_explicit_kind(self):
        self.assertTrue(is_foreign(self.foreign))
        self.assertEqual(kind_of(self.group1), "")

    def test_saving_a_foreign_kind_group_grants_office_scope(self):
        response = self.post_group(name="Beynəlxalq-1", group_kind=KIND_FOREIGN)
        self.assertEqual(response.status_code, 200, response.content)
        with bypass_rls():
            unit = OrgUnit.objects.get(organization=self.org, name="Beynəlxalq-1")
            self.assertEqual(unit.settings["group_kind"], KIND_FOREIGN)
            self.assertTrue(Membership.objects.filter(user=self.staff, scope_unit=unit, is_active=True).exists())

    def test_regular_group_gives_no_scope(self):
        self.post_group(name="Adi-77", group_kind="")
        with bypass_rls():
            unit = OrgUnit.objects.get(organization=self.org, name="Adi-77")
            self.assertFalse(Membership.objects.filter(scope_unit=unit).exists())


class CandidateTest(ForeignOfficeBase):
    def candidates(self, unit, q=""):
        url = reverse("organizations:group_student_candidates", args=[self.org.slug, unit.pk])
        return self.get_json(self.staff, f"{url}?q={q}")

    def test_foreign_group_lists_students_of_the_whole_university(self):
        body = self.candidates(self.foreign).json()
        texts = " ".join(item["text"] for item in body["results"])
        for username in ("fso_host", "fso_stud", "fso_farst"):
            self.assertIn(username, texts)
        self.assertTrue(all(item["id"].startswith("x:") for item in body["results"]))

    def test_other_faculty_student_only_as_extra(self):
        record = self.record_of(self.far_student)
        with bypass_rls():
            response = self.client_for(self.staff).post(
                reverse("organizations:group_action", kwargs={"slug": self.org.slug}),
                {
                    "action": "add_students",
                    "id": str(self.foreign.pk),
                    "record_ids": f"x:{record.pk}",
                    "other_mode": "transfer",
                },
            )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["error"], "transfer_outside_scope")
        record.refresh_from_db()
        self.assertEqual(record.group_id, self.far_group.pk)


class GraduateTest(ForeignOfficeBase):
    def test_group_graduation_in_one_order(self):
        with bypass_rls():
            response = self.client_for(self.staff).post(
                reverse("accounts:student_group_graduate"),
                {"id": str(self.foreign.pk), "order_number": "99/M", "order_date": "2025-11-20"},
            )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["graduated"], 1)
        self.assertEqual(self.record_of(self.foreign_student).status, "graduated")

    def test_cannot_graduate_ordinary_group(self):
        with bypass_rls():
            response = self.client_for(self.staff).post(
                reverse("accounts:student_group_graduate"),
                {"id": str(self.group1.pk), "order_number": "99/M", "order_date": "2025-11-20"},
            )
        self.assertEqual(response.status_code, 404)
        with bypass_rls():
            self.assertFalse(StudentAcademicRecord.objects.filter(group=self.group1, status="graduated").exists())


class ForeignParallelTest(ForeignOfficeBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            cls.foreign2 = OrgUnit.objects.create(
                organization=cls.org,
                name="02-əcnəbilər2026",
                slug="fso-ecn2b",
                unit_type=OrgUnitType.GROUP,
                parent=cls.chair,
            )
            cls.off1 = CourseOffering.objects.get(organization=cls.org, subject=cls.history, group=cls.foreign)
            cls.off1.instructor = cls.teacher
            cls.off1.save(update_fields=["instructor"])
            cls.off2 = CourseOffering.objects.create(
                organization=cls.org, subject=cls.math, period=cls.period, group=cls.foreign2, instructor=cls.teacher
            )
            ScheduleSlot.objects.create(
                organization=cls.org,
                offering=cls.off1,
                weekday=1,
                start_time=datetime.time(9, 0),
                end_time=datetime.time(10, 20),
                week_type="all",
                kind="lecture",
                room="101",
            )

    def clashes(self, offering):
        with bypass_rls():
            org = type(self.org).objects.get(pk=self.org.pk)
            return schedule.find_conflict(
                organization=org,
                offering=offering,
                weekday=1,
                start_time=datetime.time(9, 0),
                end_time=datetime.time(10, 20),
                week_type="all",
                room="101",
                kind="lecture",
            ), schedule_conflicts.detect(
                organization=org,
                weekday=1,
                start_time=datetime.time(9, 0),
                end_time=datetime.time(10, 20),
                week_type="all",
                room="101",
                group_id=offering.group_id,
                instructor_id=self.teacher.pk,
                period_id=self.period.pk,
                subject_id=offering.subject_id,
                kind="lecture",
                offering_id=offering.pk,
            )

    def test_two_foreign_groups_same_teacher_same_time(self):
        with bypass_rls():
            self.assertEqual(foreign_group_ids(self.org), {str(self.foreign.pk), str(self.foreign2.pk)})
        first, found = self.clashes(self.off2)
        self.assertIsNone(first)
        self.assertEqual(found, [])

    def test_ordinary_group_still_clashes(self):
        with bypass_rls():
            ordinary = CourseOffering.objects.create(
                organization=self.org,
                subject=self.physics,
                period=self.period,
                group=self.group2,
                instructor=self.teacher,
            )
        first, found = self.clashes(ordinary)
        self.assertIsNotNone(first)
        self.assertIn("teacher", {row["kind"] for row in found})
