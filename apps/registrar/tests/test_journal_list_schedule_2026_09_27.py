"""Jurnal siyahısı cədvəl sırası + dərs modalında otaq yaddaşı (sahib 2026-09-27).

1. Dərs cədvəli varsa hazırda gedən / ən yaxın dərsin jurnalı siyahının ən yuxarısındadır,
   sıra gün və saata görə dəyişir; cədvəlsiz açılışlar əvvəlki sıra ilə sonda qalır.
2. Müəllim bir dəfə otaq seçibsə, eyni növ + həftə günü üçün yeni dərsdə o otaq defolt olur.
"""

import datetime
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import journal_list_schedule as jls
from apps.registrar import lesson_rooms, services
from apps.registrar.models import CourseOffering, Lesson, LessonKind, ScheduleSlot, SlotKind, Subject
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()

# 2024-10-02 — Çərşənbə (isoweekday 3), 10:30.
NOW = timezone.make_aware(datetime.datetime(2024, 10, 2, 10, 30))


def _t(value):
    return datetime.time.fromisoformat(value)


class _Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("js_owner", "js_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="JS Univ",
                slug="js-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org, name="G1", slug="js-g1", unit_type=OrgUnitType.GROUP
            )
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="2024/2025 Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2024/2025",
                start_date="2024-09-01",
                end_date="2025-01-31",
                is_current=True,
            )
            cls.teacher = User.objects.create_user("js_teacher", "js_teacher@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.teacher,
                organization=cls.org,
                role=cls.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )
            cls.offerings = {}
            for code in ("A100", "B200", "C300", "D400"):
                subject = Subject.objects.create(organization=cls.org, code=code, name=f"Fənn {code}")
                offering = services.get_or_create_offering(
                    organization=cls.org, subject=subject, period=cls.period, group=cls.group
                )
                offering.instructor = cls.teacher
                offering.save(update_fields=["instructor"])
                cls.offerings[code] = offering

    @classmethod
    def _slot(cls, code, weekday, start, end, kind=SlotKind.LECTURE, **extra):
        with bypass_rls():
            return ScheduleSlot.objects.create(
                organization=cls.org,
                offering=cls.offerings[code],
                weekday=weekday,
                start_time=_t(start),
                end_time=_t(end),
                kind=kind,
                **extra,
            )


class JournalListScheduleOrderTest(_Base):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls._slot("A100", 4, "09:00", "10:20")  # sabah (cümə axşamı)
        cls._slot("B200", 3, "10:10", "11:30", kind=SlotKind.SEMINAR)  # İNDİ gedir
        cls._slot("C300", 3, "13:40", "15:00")  # bu gün, sonra
        # D400 — cədvəlsiz.

    def _occurrences(self, **kwargs):
        qs = CourseOffering.objects.filter(pk__in=[o.pk for o in self.offerings.values()])
        return jls.next_occurrences(qs, self.teacher.pk, now=NOW, **kwargs)

    def test_rank_now_then_today_then_tomorrow(self):
        occ = self._occurrences()
        ids = jls.ranked_ids(occ)
        codes = [next(c for c, o in self.offerings.items() if o.pk == pk) for pk in ids]
        self.assertEqual(codes, ["B200", "C300", "A100"])
        self.assertEqual(occ[self.offerings["B200"].pk]["state"], "now")
        self.assertEqual(occ[self.offerings["C300"].pk]["state"], "today")
        self.assertEqual(occ[self.offerings["A100"].pk]["state"], "tomorrow")
        self.assertNotIn(self.offerings["D400"].pk, occ)

    def test_ended_lesson_moves_to_next_week_after_grace(self):
        later = NOW + datetime.timedelta(hours=1, minutes=35)  # 12:05 — B200 11:30-da bitib (+30 dəq. keçib)
        qs = CourseOffering.objects.filter(pk=self.offerings["B200"].pk)
        occ = jls.next_occurrences(qs, self.teacher.pk, now=later)
        self.assertEqual(occ[self.offerings["B200"].pk]["day"], datetime.date(2024, 10, 9))
        self.assertEqual(occ[self.offerings["B200"].pk]["state"], "later")

    def test_kind_filter_only_counts_that_kind(self):
        occ = self._occurrences(kind=SlotKind.SEMINAR)
        self.assertEqual(list(occ), [self.offerings["B200"].pk])

    def test_other_teachers_slot_is_ignored(self):
        other = User.objects.create_user("js_other", "js_other@qku.edu.az", "pw")
        with bypass_rls():
            Membership.objects.create(
                user=other, organization=self.org, role=self.org.roles.get(name="teacher"), is_active=True
            )
        self._slot("D400", 3, "10:10", "11:30", instructor=other)
        occ = self._occurrences()
        self.assertNotIn(self.offerings["D400"].pk, occ)

    def test_list_page_orders_by_schedule_and_shows_badge(self):
        client = Client()
        client.force_login(self.teacher)
        with mock.patch("django.utils.timezone.now", return_value=NOW):
            response = client.get(reverse("registrar:journal_list"), {"year": "", "season": ""}, HTTP_HOST="testserver")
        self.assertEqual(response.status_code, 200)
        codes = [o.subject.code for o in response.context["offerings"]]
        self.assertEqual(codes, ["B200", "C300", "A100", "D400"])
        self.assertContains(response, "jl-row--now")
        self.assertContains(response, "jl-next--today")


class LessonRoomMemoryTest(_Base):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            cls.room_a = cls.org.exam_rooms.create(name="101", code="R101", building="Korpus A", is_active=True)
            cls.room_b = cls.org.exam_rooms.create(name="202", code="R202", building="Korpus B", is_active=True)
            cls.room_off = cls.org.exam_rooms.create(name="303", code="R303", building="Korpus B", is_active=False)
            offering = cls.offerings["A100"]
            for day, kind, room in (
                (datetime.date(2024, 9, 23), LessonKind.LECTURE, cls.room_a),  # B.e.
                (datetime.date(2024, 9, 30), LessonKind.LECTURE, cls.room_b),  # B.e. — daha yeni
                (datetime.date(2024, 9, 25), LessonKind.SEMINAR, cls.room_a),  # Çərşənbə
                (datetime.date(2024, 10, 2), LessonKind.SEMINAR, cls.room_off),  # deaktiv otaq — sayılmır
            ):
                Lesson.objects.create(organization=cls.org, offering=offering, date=day, kind=kind, room=room)

    def test_latest_room_per_kind_and_weekday(self):
        memory = lesson_rooms.remembered_rooms(self.offerings["A100"])
        self.assertEqual(memory["lecture|1"], str(self.room_b.pk))
        self.assertEqual(memory["seminar|3"], str(self.room_a.pk))
        self.assertEqual(memory["lecture"], str(self.room_b.pk))
        self.assertEqual(memory["seminar"], str(self.room_a.pk))
        self.assertNotIn(str(self.room_off.pk), memory.values())

    def test_remembered_room_for_activation(self):
        offering = self.offerings["A100"]
        self.assertEqual(lesson_rooms.remembered_room(offering, "lecture", datetime.date(2024, 10, 7)), self.room_b)
        self.assertIsNone(lesson_rooms.remembered_room(offering, "lecture", datetime.date(2024, 10, 8)))

    def test_empty_for_offering_without_rooms(self):
        self.assertEqual(lesson_rooms.remembered_rooms(self.offerings["D400"]), {})
