"""Perf auditi 2026-09-13 — `registrar` tapıntılarının reqressiya testləri.

* **F-13** `lessons_log.range_totals` dövrün BÜTÜN dərslərini Python-a çəkib
  `note_state` ilə təsnif edirdi → təsnifat SQL-dədir (nəticə eyni), sorğu
  sayı dərs sayından asılı deyil, nəticə 300 s keşlənir.
* **F-14** `/jurnal/` org-geniş görünüşündə `student_count` annotasiyası
  paginasiyadan ƏVVƏL bütün açılışlara tətbiq olunurdu (LEFT JOIN 150k
  enrollment + GROUP BY) → say yalnız səhifənin açılışları üçün hesablanır;
  paginator COUNT-u və səhifə SELECT-i enrollment cədvəlinə toxunmur, şablonun
  oxuduğu `offering.student_count` isə eyni dəyəri verir.
"""

from __future__ import annotations

import datetime as dt

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import lessons_log as service
from apps.registrar import services
from apps.registrar.models import AttendanceStatus, Enrollment, Lesson, LessonKind, LessonMark, Subject
from apps.syllabus.tests.factories import activate_member, make_academic_stack, make_offering, make_org
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()
PASSWORD = "StrongPass123!"

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "pf13-totals"}}


@override_settings(UNIVERSITY_MODE=True)
class RangeTotalsSqlTest(TestCase):
    """F-13."""

    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("pf13-llog")
        cls.stack = make_academic_stack(cls.org, code="PF13L")
        cls.teacher = User.objects.create_user("pf13_llog_teacher", "pf13_llog_teacher@qku.edu.az", PASSWORD)
        cls.student = User.objects.create_user("pf13_llog_student", "pf13_llog_student@qku.edu.az", PASSWORD)
        activate_member(cls.org, cls.teacher, "teacher", permissions=["course.view", "grade.input"])
        activate_member(cls.org, cls.student, "student", permissions=["course.view"], level=10)
        cls.offering = make_offering(cls.org, cls.stack, cls.teacher)
        cls.enrollment = Enrollment.objects.create(organization=cls.org, offering=cls.offering, student=cls.student)
        cls.base_date = dt.date(2025, 10, 6)

    def _lesson(self, *, day_offset: int, hours: int = 2):
        return Lesson.objects.create(
            organization=self.org,
            offering=self.offering,
            date=self.base_date + dt.timedelta(days=day_offset),
            kind=LessonKind.SEMINAR,
            topic=f"Mövzu {day_offset}",
            hours=hours,
            instructor=self.teacher,
        )

    def _mark(self, lesson, *, created_at, status=AttendanceStatus.PRESENT, score=None):
        mark = LessonMark.objects.create(
            organization=self.org, lesson=lesson, enrollment=self.enrollment, status=status, score=score
        )
        LessonMark.objects.filter(pk=mark.pk).update(created_at=created_at)
        return mark

    def _stamp(self, lesson_date, *, days: int, hour: int = 10):
        return timezone.make_aware(dt.datetime.combine(lesson_date + dt.timedelta(days=days), dt.time(hour, 0)))

    def test_sql_classification_matches_note_state(self):
        on_time = self._lesson(day_offset=0)  # xana dərs günü
        self._mark(on_time, created_at=self._stamp(on_time.date, days=0), score=7)
        edge = self._lesson(day_offset=1)  # xana 2 gün sonra — 48 saat həddində, gec DEYİL
        self._mark(edge, created_at=self._stamp(edge.date, days=2, hour=23), status=AttendanceStatus.ABSENT)
        late = self._lesson(day_offset=2)  # xana 3 gün sonra — gec
        self._mark(late, created_at=self._stamp(late.date, days=3, hour=0), status=AttendanceStatus.EXCUSED)
        self._lesson(day_offset=3, hours=4)  # boş jurnal

        lessons = service.scoped_lessons(self.teacher, self.org, supervisor=False)
        # Referans: Python qaydası (`note_state`) — SQL eyni cavabı verməlidir.
        expected = {"empty": 0, "late": 0}
        for lesson in lessons:
            marks = list(lesson.marks.order_by("created_at"))
            state = service.note_state(
                lesson_date=lesson.date,
                marks_count=len(marks),
                first_mark=marks[0].created_at if marks else None,
            )
            if state == service.NOTE_EMPTY:
                expected["empty"] += 1
            elif state == service.NOTE_LATE:
                expected["late"] += 1
        self.assertEqual(expected, {"empty": 1, "late": 1})

        totals = service.range_totals(lessons)
        self.assertEqual(totals["lessons"], 4)
        self.assertEqual(totals["hours"], 10)
        self.assertEqual(totals["empty"], expected["empty"])
        self.assertEqual(totals["late"], expected["late"])
        self.assertEqual((totals["present"], totals["absent"], totals["excused"], totals["graded"]), (1, 1, 1, 1))
        self.assertEqual(totals["attendance_rate"], 33)

    def test_query_count_is_independent_of_lesson_count_and_no_rows_are_fetched(self):
        lessons = service.scoped_lessons(self.teacher, self.org, supervisor=False)
        for offset in range(3):
            lesson = self._lesson(day_offset=offset)
            self._mark(lesson, created_at=self._stamp(lesson.date, days=offset))
        with CaptureQueriesContext(connection) as small:
            small_totals = service.range_totals(lessons)
        for offset in range(3, 33):
            lesson = self._lesson(day_offset=offset)
            if offset % 2:
                self._mark(lesson, created_at=self._stamp(lesson.date, days=offset % 5))
        with CaptureQueriesContext(connection) as large:
            large_totals = service.range_totals(lessons)
        self.assertEqual(small_totals["lessons"], 3)
        self.assertEqual(large_totals["lessons"], 33)
        self.assertEqual(len(small.captured_queries), len(large.captured_queries))
        self.assertLessEqual(len(large.captured_queries), 2)
        # Dərs sətirləri Python-a gəlmir: heç bir sorğu `registrar_lesson.id`
        # siyahısı qaytarmır — yalnız aqreqatlar.
        for query in large.captured_queries:
            self.assertTrue(query["sql"].startswith("SELECT COUNT("), query["sql"][:120])

    @override_settings(CACHES=LOCMEM)
    def test_totals_are_cached_per_query_shape(self):
        cache.clear()
        lessons = service.scoped_lessons(self.teacher, self.org, supervisor=False)
        self._lesson(day_offset=0)
        first = service.range_totals(lessons)
        self.assertEqual(first["lessons"], 1)
        with CaptureQueriesContext(connection) as hit:
            second = service.range_totals(lessons)
        self.assertEqual(len(hit.captured_queries), 0)
        self.assertEqual(second, first)
        # Fərqli süzgəc → fərqli açar → yenidən hesablanır.
        narrowed = lessons.filter(date__gte=self.base_date + dt.timedelta(days=5))
        self.assertNotEqual(service.totals_cache_key(lessons), service.totals_cache_key(narrowed))
        with CaptureQueriesContext(connection) as miss:
            self.assertEqual(service.range_totals(narrowed)["lessons"], 0)
        self.assertGreater(len(miss.captured_queries), 0)
        cache.clear()


class JournalListStudentCountTest(TestCase):
    """F-14."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("pf14_owner", "pf14_owner@qku.edu.az", PASSWORD)
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="PF14 Univ",
                slug="pf14-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.faculty = OrgUnit.objects.create(
                organization=cls.org, name="PF14 Fakültə", slug="pf14-fac", unit_type=OrgUnitType.FACULTY
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org, name="PF14-A", slug="pf14-g-a", unit_type=OrgUnitType.GROUP, parent=cls.faculty
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
            cls.admin = User.objects.create_user("pf14_admin", "pf14_admin@qku.edu.az", PASSWORD, is_superuser=True)
            cls.teacher = User.objects.create_user("pf14_teacher", "pf14_teacher@qku.edu.az", PASSWORD)
            Membership.objects.create(
                user=cls.teacher,
                organization=cls.org,
                role=cls.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )
            cls.students = []
            for index in range(4):
                student = User.objects.create_user(f"pf14_st{index}", f"pf14_st{index}@qku.edu.az", PASSWORD)
                Membership.objects.create(
                    user=student,
                    organization=cls.org,
                    role=cls.org.roles.get(name="student"),
                    is_primary=True,
                    is_active=True,
                )
                cls.students.append(student)
            cls.offerings = []
            for index in range(3):
                subject = Subject.objects.create(organization=cls.org, code=f"PF14-{index}", name=f"PF14 fənn {index}")
                offering = services.get_or_create_offering(
                    organization=cls.org, subject=subject, period=cls.period, group=cls.group
                )
                offering.instructor = cls.teacher
                offering.save(update_fields=["instructor"])
                cls.offerings.append(offering)
            # 0-cı açılış: 3 aktiv + 1 çıxarılmış; 1-ci: 1 aktiv; 2-ci: heç kim.
            for student in cls.students[:3]:
                Enrollment.objects.create(organization=cls.org, offering=cls.offerings[0], student=student)
            dropped = Enrollment.objects.create(
                organization=cls.org, offering=cls.offerings[0], student=cls.students[3]
            )
            Enrollment.objects.filter(pk=dropped.pk).update(status=Enrollment.Status.DROPPED)
            Enrollment.objects.create(organization=cls.org, offering=cls.offerings[1], student=cls.students[0])

    def _client(self):
        client = Client()
        client.force_login(self.admin)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def test_counts_are_correct_and_pagination_queries_avoid_the_enrollment_join(self):
        client = self._client()
        client.get(reverse("registrar:journal_list"), {"year": "2024/2025"})  # isinmə
        with CaptureQueriesContext(connection) as ctx:
            response = client.get(reverse("registrar:journal_list"), {"year": "2024/2025"})
        self.assertEqual(response.status_code, 200)
        counts = {offering.pk: offering.student_count for offering in response.context["offerings"]}
        self.assertEqual(
            counts,
            {self.offerings[0].pk: 3, self.offerings[1].pk: 1, self.offerings[2].pk: 0},
        )
        self.assertContains(response, "<b>3</b>")
        # Paginator COUNT-u və səhifə SELECT-i enrollment cədvəlinə JOIN etmir.
        offering_queries = [
            q["sql"]
            for q in ctx.captured_queries
            if 'FROM "registrar_courseoffering"' in q["sql"]
            and ('"registrar_courseoffering"."created_at"' in q["sql"] or q["sql"].startswith("SELECT COUNT(*)"))
        ]
        self.assertTrue(offering_queries)
        for sql in offering_queries:
            self.assertNotIn('JOIN "registrar_enrollment"', sql, sql[:200])
        # Tələbə sayı TƏK toplu sorğu ilə gəlir (səhifənin açılışları üçün).
        count_queries = [
            q["sql"]
            for q in ctx.captured_queries
            if q["sql"].startswith('SELECT "registrar_enrollment"."offering_id" AS "offering_id", COUNT(')
        ]
        self.assertEqual(len(count_queries), 1)
