"""«Passiv» dərs — dərs saatı seçimində «Passiv · N» (sahib 2026-11-14).

* modalda «SAAT» seçimi 1..4 + «Passiv · N» (``p<N>``); köhnə «İntensiv tədris: passiv saat» qutusu yoxdur;
* passiv dərs «Keçirilmiş X / Y», saat həddi (#6), qayıb məxrəci, mühasibat / yük sayğaclarına düşmür;
* qridde sütun rənglidir (``is-passive``), xana yazılmır (server də rədd edir); qeydli dərs passiv olmur;
* «Keçilmiş dərslər»: nişan + ayrıca cəm (gün, KPI, müəllim cədvəli, CSV / XLSX);
* köhnə ``PassiveHour`` sətri miqrasiya ilə passiv dərsə çevrilir.
"""

from __future__ import annotations

import datetime
import importlib
from io import BytesIO
from types import SimpleNamespace

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import (
    exam_eligibility,
    gradebook,
    journal_extras,
    lessons_log,
    lessons_log_pages,
    lessons_log_teacher_table,
    lessons_log_teacher_xlsx,
    passive_lessons,
    services,
)
from apps.registrar.models import Enrollment, Lesson, LessonMark, PassiveHour, Subject
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()
TIME = "08:30|10:00"


class PassiveLessonBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("pl_owner", "pl_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="PL Univ",
                slug="pl-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org, name="PL1", slug="pl-g1", unit_type=OrgUnitType.GROUP
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
            cls.subject = Subject.objects.create(organization=cls.org, code="PL101", name="Passiv fənn")
            cls.teacher = User.objects.create_user(
                "pl_teacher", "pl_teacher@qku.edu.az", "pw", first_name="Günay", last_name="Həsənova"
            )
            Membership.objects.create(
                user=cls.teacher,
                organization=cls.org,
                role=cls.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )
            cls.student = User.objects.create_user("pl_student", "pl_student@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.student,
                organization=cls.org,
                role=cls.org.roles.get(name="student"),
                is_primary=True,
                is_active=True,
            )
            cls.offering = services.get_or_create_offering(
                organization=cls.org, subject=cls.subject, period=cls.period, group=cls.group
            )
            cls.offering.instructor = cls.teacher
            cls.offering.lesson_hours = 4
            cls.offering.save(update_fields=["instructor", "lesson_hours"])
            cls.enrollment = Enrollment.objects.create(organization=cls.org, student=cls.student, offering=cls.offering)

    def client_for(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def post_lesson(self, hours, *, kind="lecture", time=TIME):
        return self.client_for(self.teacher).post(
            reverse("registrar:journal_detail", args=[self.offering.id]),
            {
                "action": "add_lesson",
                "lesson_date": timezone.localdate().isoformat(),
                "lesson_kind": kind,
                "lesson_hours": hours,
                "lesson_time": time,
            },
        )

    def lesson(self, *, passive=False, hours=2, day=None, **extra):
        with bypass_rls():
            return Lesson.objects.create(
                organization=self.org,
                offering=self.offering,
                date=day or datetime.date(2024, 10, 7),
                kind=extra.pop("kind", "lecture"),
                hours=hours,
                instructor=self.teacher,
                created_by=self.teacher,
                is_passive=passive,
                **extra,
            )

    def fresh(self):
        with bypass_rls():
            return (
                type(self.offering).objects.select_related("organization", "period", "subject").get(pk=self.offering.pk)
            )


class ParseTest(TestCase):
    def test_hours_choice(self):
        cases = {
            "": (None, False, True),
            "2": (2, False, True),
            "p2": (2, True, True),
            "P1": (1, True, True),
            "p": (None, True, False),
            "p0": (None, True, False),
            "0": (None, False, False),
            "-5": (None, False, False),
            "abc": (None, False, False),
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(passive_lessons.parse_hours_choice(raw), expected)


class CreateAndCountTest(PassiveLessonBase):
    def test_passive_lesson_created_and_excluded_from_held_and_cap(self):
        self.assertEqual(self.post_lesson("2").status_code, 302)
        # Hədd 4 saat: 2 adi + 2 passiv + 2 passiv — passivlər həddə düşmür, hamısı açılır.
        self.post_lesson("p2", time="10:10|11:40")
        self.post_lesson("p2", time="11:50|13:20")
        with bypass_rls():
            lessons = list(Lesson.objects.filter(offering=self.offering).order_by("start_time"))
        self.assertEqual([(lesson.hours, lesson.is_passive) for lesson in lessons], [(2, False), (2, True), (2, True)])
        summary = journal_extras.journal_teaching_summary(self.fresh())
        self.assertEqual((summary["held_total"], summary["scheduled_total"]), (2, 2))
        self.assertEqual(summary["passive_total"], 4)
        self.assertEqual(summary["remaining"], 2)
        # Adi dərs isə həddi yoxlayır: 2 + 2 = 4 açılır, növbəti 2 rədd olunur.
        self.post_lesson("2", time="13:35|15:05")
        self.post_lesson("2", time="15:15|16:45")
        with bypass_rls():
            self.assertEqual(Lesson.objects.filter(offering=self.offering, is_passive=False).count(), 2)

    def test_denominator_fallback_ignores_passive(self):
        with bypass_rls():
            type(self.offering).objects.filter(pk=self.offering.pk).update(lesson_hours=0)
        self.lesson(hours=2)
        self.lesson(hours=4, passive=True, day=datetime.date(2024, 10, 8))
        offering = self.fresh()
        with bypass_rls():
            lessons = list(offering.lessons.all())
            self.assertEqual(exam_eligibility.lesson_hours_for(offering, lessons), 2)
            self.assertEqual(exam_eligibility.lesson_hours_map([offering.pk]).get(offering.pk), 2)
            self.assertEqual(exam_eligibility.lesson_hours_for(offering), 2)

    def test_marks_are_not_written_to_passive_lesson(self):
        lesson = self.lesson(passive=True, day=timezone.localdate())
        with bypass_rls():
            written = gradebook.save_marks(
                offering=self.fresh(),
                entries=[{"lesson_id": str(lesson.pk), "enrollment_id": str(self.enrollment.pk), "status": "absent"}],
                by_user=self.teacher,
                enforce_day=False,
            )
            self.assertEqual(written, 0)
            self.assertFalse(LessonMark.objects.filter(lesson=lesson).exists())

    def test_lesson_with_marks_cannot_become_passive(self):
        lesson = self.lesson(day=timezone.localdate())
        with bypass_rls():
            LessonMark.objects.create(organization=self.org, lesson=lesson, enrollment=self.enrollment)
            with self.assertRaises(gradebook.LessonRuleError):
                gradebook.update_lesson(lesson=lesson, passive=True, allow_locked=True, by_user=self.teacher)
            lesson.refresh_from_db()
            self.assertFalse(lesson.is_passive)

    def test_update_toggles_passive_and_back_checks_cap(self):
        normal = self.lesson(hours=4, day=timezone.localdate())
        passive = self.lesson(hours=2, passive=True, day=timezone.localdate(), start_time=datetime.time(10, 15))
        with bypass_rls():
            # Hədd (4) dolub — passivi adi dərsə qaytarmaq olmaz.
            with self.assertRaises(gradebook.LessonRuleError):
                gradebook.update_lesson(lesson=passive, passive=False, allow_locked=True, by_user=self.teacher)
            self.assertTrue(gradebook.update_lesson(lesson=normal, passive=True, allow_locked=True))
            normal.refresh_from_db()
            self.assertTrue(normal.is_passive)
            passive.refresh_from_db()
            self.assertTrue(gradebook.update_lesson(lesson=passive, passive=False, allow_locked=True))
            passive.refresh_from_db()
            self.assertFalse(passive.is_passive)

    def test_update_view_posts_passive_choice(self):
        lesson = self.lesson(day=timezone.localdate(), start_time=datetime.time(8, 30), end_time=datetime.time(10, 0))
        url = reverse("registrar:journal_lesson_action", args=[self.offering.id, lesson.id])
        self.client_for(self.teacher).post(url, {"action": "update_lesson", "lesson_hours": "p2", "lesson_time": TIME})
        with bypass_rls():
            lesson.refresh_from_db()
        self.assertTrue(lesson.is_passive)
        self.client_for(self.teacher).post(url, {"action": "update_lesson", "lesson_hours": "2", "lesson_time": TIME})
        with bypass_rls():
            lesson.refresh_from_db()
        self.assertFalse(lesson.is_passive)


class PageTest(PassiveLessonBase):
    def test_modal_option_grid_colour_and_no_old_box(self):
        lesson = self.lesson(passive=True, hours=2, day=timezone.localdate())
        self.lesson(hours=2, day=timezone.localdate(), start_time=datetime.time(10, 15))
        response = self.client_for(self.teacher).get(reverse("registrar:journal_detail", args=[self.offering.id]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["passive_lessons_available"])
        self.assertContains(response, 'value="p1"')
        self.assertContains(response, 'value="p2"')
        self.assertContains(response, "registrar/css/journal_passive_lessons.css")
        self.assertContains(response, "jd2-th-passive")
        self.assertContains(response, "jd2-ro--passive")
        self.assertContains(response, 'data-lesson-hours="p2"')
        self.assertContains(response, "jd2-teach-passive")
        self.assertNotContains(response, "jd2-passive-switch")
        self.assertNotContains(response, "İntensiv tədris: passiv saat")
        html = response.content.decode()
        self.assertIn(f'id="jd-lesson-{lesson.id}"', html)
        header = html.split(f'id="jd-lesson-{lesson.id}"')[0].rsplit("<th", 1)[1]
        self.assertIn("is-passive", header)
        self.assertEqual(response.context["teaching_summary"]["passive_total"], 2)


class LessonsLogTest(PassiveLessonBase):
    def qs(self):
        return Lesson.objects.filter(offering=self.offering)

    def test_rows_totals_and_exports_separate_passive(self):
        day = datetime.date(2024, 10, 7)
        self.lesson(hours=2, day=day, start_time=datetime.time(8, 30))
        self.lesson(hours=2, passive=True, day=day, start_time=datetime.time(10, 15), topic="Müstəqil iş")
        with bypass_rls():
            rows = lessons_log.build_rows(self.qs())
            passive_row = next(row for row in rows if row["is_passive"])
            self.assertEqual(passive_row["note"], lessons_log.NOTE_PASSIVE)
            self.assertEqual(
                lessons_log.quick_totals(self.qs()),
                {"lessons": 1, "hours": 2, "passive_lessons": 1, "passive_hours": 2},
            )
            totals = lessons_log.range_totals(self.qs())
            self.assertEqual((totals["lessons"], totals["hours"], totals["passive_hours"]), (1, 2, 2))
            self.assertEqual(totals["empty"], 1)  # yalnız adi dərs «boş» sayılır
            self.assertEqual(
                lessons_log_pages.day_totals(self.qs(), [day]), {day: {"lessons": 1, "hours": 2, "passive_hours": 2}}
            )
            csv = lessons_log.csv_rows(rows)
            passive_col = csv[0].index("Passiv")
            self.assertEqual(sorted(line[passive_col] for line in csv[1:]), ["", "Bəli"])

            events = lessons_log_teacher_table.load_events(self.qs())
            table = lessons_log_teacher_table.summarise(events)
            self.assertEqual((table["totals"]["hours"], table["totals"]["passive_hours"]), (2, 2))
            self.assertEqual(len(table["rows"]), 2)
            self.assertIn("Passiv", next(row["kind_label"] for row in table["rows"] if row["passive"]))
            details = lessons_log_teacher_table.event_details(table["rows"])
            self.assertEqual(sorted(item["passive"] for item in details), [False, True])
            content = lessons_log_teacher_xlsx.build_xlsx(
                teacher_name="Həsənova", window={"start": day, "end": day}, table=table, details=details
            )
        from openpyxl import load_workbook

        book = load_workbook(BytesIO(content))
        summary_values = [cell for row in book.worksheets[0].iter_rows(values_only=True) for cell in row]
        self.assertIn("Passiv saat (cəmə daxil deyil)", summary_values)
        lesson_rows = list(book.worksheets[1].iter_rows(values_only=True))
        self.assertIn("Passiv", lesson_rows[0])

    def test_day_grouping_and_kpi_note(self):
        from apps.accounts.views.profile._sections.lessons_log import _group_by_day, _kpi_tiles

        day = datetime.date(2024, 10, 7)
        rows = [
            {"date": day, "hours": 2, "is_passive": False},
            {"date": day, "hours": 2, "is_passive": True},
        ]
        bucket = _group_by_day(rows)[0]
        self.assertEqual((bucket["lessons"], bucket["hours"], bucket["passive_hours"]), (1, 2, 2))
        tiles = _kpi_tiles({"lessons": 1, "hours": 2, "passive_hours": 2}, pending=True)
        self.assertIn("passiv 2 saat", tiles[1]["note"])


class LegacyConversionTest(PassiveLessonBase):
    def test_old_passive_hours_become_passive_lessons(self):
        with bypass_rls():
            PassiveHour.objects.create(
                organization=self.org,
                offering=self.offering,
                date=datetime.date(2024, 10, 9),
                hours=3,
                note="Mənbə təhlili",
                created_by=self.teacher,
            )
            migration = importlib.import_module("apps.registrar.migrations.0124_lesson_is_passive")
            editor = SimpleNamespace(connection=connection, execute=lambda *args, **kwargs: None)
            migration.convert_passive_hours(django_apps, editor)
            migration.convert_passive_hours(django_apps, editor)  # idempotent
            lesson = Lesson.objects.get(offering=self.offering)
        self.assertEqual(
            (lesson.date, lesson.hours, lesson.topic, lesson.is_passive, lesson.instructor_id),
            (datetime.date(2024, 10, 9), 3, "Mənbə təhlili", True, self.teacher.pk),
        )
        summary = journal_extras.journal_teaching_summary(self.fresh())
        self.assertEqual((summary["held_total"], summary["passive_total"]), (0, 3))
        with bypass_rls():
            migration.revert_passive_hours(django_apps, editor)
            self.assertFalse(Lesson.objects.filter(offering=self.offering).exists())
            self.assertTrue(PassiveHour.objects.filter(offering=self.offering).exists())
