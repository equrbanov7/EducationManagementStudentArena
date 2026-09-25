"""«Keçilmiş dərslər» → «Cədvəldə var, qeydə alınmayıb» sayğacı + «cədvəldən kənar» nişanı (UNEC P1-1)."""

import datetime as dt

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.registrar import lessons_log as service
from apps.registrar.models import CourseOffering, Lesson, LessonKind, ScheduleSlot, SlotKind, Subject, WeekType
from apps.syllabus.tests.factories import activate_member, make_academic_stack, make_offering, make_org
from core.constants import RoleScopeType
from core.rls import bypass_rls

User = get_user_model()

PASSWORD = "StrongPass123!"
TEACHER_PERMS = ["course.view", "grade.input", "syllabus.edit"]
CHAIR_PERMS = ["course.view", "journal.roster", "unit.view"]

# Dövr 2025-09-01 (B.e.) başlayır → 1-ci həftə ÜST; 06.10 — 6-cı həftə (ALT), 13.10 — 7-ci (ÜST).
WINDOW = {"start": dt.date(2025, 10, 6), "end": dt.date(2025, 10, 19)}
TODAY = dt.date(2025, 10, 20)
AUGUST = timezone.make_aware(dt.datetime(2025, 8, 1, 12, 0))


@override_settings(UNIVERSITY_MODE=True)
class UnrecordedSlotsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            cls.org = make_org("llu-univ")
            cls.stack = make_academic_stack(cls.org, code="LLU101")
            cls.teacher = User.objects.create_user("llu_teacher", "llu_teacher@qku.edu.az", PASSWORD)
            cls.other = User.objects.create_user("llu_other", "llu_other@qku.edu.az", PASSWORD)
            cls.chair = User.objects.create_user("llu_chair", "llu_chair@qku.edu.az", PASSWORD)
            activate_member(cls.org, cls.teacher, "teacher", permissions=TEACHER_PERMS)
            activate_member(cls.org, cls.other, "teacher", permissions=TEACHER_PERMS)
            activate_member(
                cls.org,
                cls.chair,
                "chair_head",
                permissions=CHAIR_PERMS,
                level=70,
                scope_type=RoleScopeType.ORGANIZATION,
            )
            for user, role in ((cls.teacher, "teacher"), (cls.other, "teacher"), (cls.chair, "chair_head")):
                profile = user.profile
                profile.role = role
                profile.save(update_fields=["role"])
            cls.offering = make_offering(cls.org, cls.stack, cls.teacher)
            other_subject = Subject.objects.create(organization=cls.org, code="LLU202", name="Başqa fənn")
            cls.other_offering = CourseOffering.objects.create(
                organization=cls.org,
                subject=other_subject,
                period=cls.stack["period"],
                group=cls.stack["group"],
                instructor=cls.other,
                lesson_hours=60,
            )

            def slot(offering, weekday, start, kind=SlotKind.LECTURE, **extra):
                end = (dt.datetime.combine(dt.date.min, start) + dt.timedelta(minutes=80)).time()
                data = {"organization": cls.org, "offering": offering, "weekday": weekday, "kind": kind}
                data.update(extra)
                return ScheduleSlot.all_objects.create(start_time=start, end_time=end, **data)

            slot(cls.offering, 1, dt.time(9, 0))  # hər B.e.
            slot(cls.offering, 3, dt.time(10, 10), SlotKind.SEMINAR, week_type=WeekType.ODD)  # yalnız ÜST Ç.
            slot(cls.offering, 2, dt.time(9, 0), is_parked=True)  # parklanıb — sayılmır
            slot(cls.offering, 4, dt.time(9, 0), is_deleted=True)  # yumşaq silinib — sayılmır
            slot(cls.other_offering, 5, dt.time(11, 50))  # başqa müəllim — yalnız nəzarətçiyə
            # Cədvəl semestrdən ƏVVƏL daxil edilib (sayğac hər günü həmin gün qüvvədə olan cədvələ görə yoxlayır).
            ScheduleSlot.all_objects.filter(organization=cls.org).update(created_at=AUGUST)

            def lesson(day, start, kind=LessonKind.LECTURE, offering=None, reason=""):
                return Lesson.objects.create(
                    organization=cls.org,
                    offering=offering or cls.offering,
                    date=day,
                    kind=kind,
                    hours=2,
                    start_time=start,
                    off_schedule_reason=reason,
                )

            lesson(dt.date(2025, 10, 6), dt.time(9, 0))  # tam uyğun
            # 13.10: başqa saata yazılıb — yenə «keçirilib» sayılır (yalançı həyəcan yox).
            cls.off_lesson = lesson(dt.date(2025, 10, 13), dt.time(13, 35), reason="Əvəzetmə dərsi")
            # 08.10 ALT həftədir → ÜST slotu həmin gün yoxdur; 15.10 ÜST → seminar yazılmayıb (1 çatışmır).

    def setUp(self):
        cache.clear()

    def _count(self, user, *, supervisor, **kwargs):
        with bypass_rls():
            return service.unrecorded_slots(
                user, self.org, supervisor=supervisor, window=kwargs.pop("window", WINDOW), today=TODAY, **kwargs
            )

    def test_teacher_sees_only_the_missing_odd_week_seminar(self):
        result = self._count(self.teacher, supervisor=False)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["slots"], 2)  # parklanmış və silinmiş slot əhatədə deyil
        (item,) = result["items"]
        self.assertEqual(item["date"], dt.date(2025, 10, 15))
        self.assertEqual(item["start"], dt.time(10, 10))
        self.assertEqual(item["kind"], SlotKind.SEMINAR)
        self.assertEqual(item["journal_url"], reverse("registrar:journal_detail", args=[self.offering.pk]))

    def test_supervisor_sees_every_teacher_and_filters_apply(self):
        result = self._count(self.chair, supervisor=True)
        self.assertEqual(result["count"], 3)  # + başqa müəllimin 10.10 və 17.10 cümə slotları
        self.assertEqual({item["teacher"] for item in result["items"]}, {"llu_teacher", "llu_other"})
        only_other = self._count(self.chair, supervisor=True, filters={"teacher": str(self.other.pk)})
        self.assertEqual(only_other["count"], 2)
        seminars = self._count(self.chair, supervisor=True, filters={"kind": SlotKind.SEMINAR})
        self.assertEqual(seminars["count"], 1)
        # Adi müəllimin «teacher» parametri səssiz keçilir (bölmə ilə eyni qayda).
        ignored = self._count(self.teacher, supervisor=False, filters={"teacher": str(self.other.pk)})
        self.assertEqual(ignored["count"], 1)

    def test_today_and_future_are_not_counted(self):
        # Pəncərə sonu bu gündən sonradırsa belə son gün DÜNƏNDİR; 20.10 (B.e.) hələ açıla bilər.
        wide = {"start": WINDOW["start"], "end": dt.date(2025, 10, 31)}
        self.assertEqual(self._count(self.teacher, supervisor=False, window=wide)["end"], dt.date(2025, 10, 19))
        empty = self._count(self.teacher, supervisor=False, window={"start": TODAY, "end": TODAY})
        self.assertEqual(empty["count"], 0)

    def test_republished_timetable_is_judged_per_date(self):
        """Köhnə slot silinib, yenisi yaradılıb (cədvəl yenidən dərc olunub) — hər gün öz cədvəlinə görə."""
        with bypass_rls():
            subject = Subject.objects.create(organization=self.org, code="LLU303", name="Üçüncü fənn")
            offering = CourseOffering.objects.create(
                organization=self.org,
                subject=subject,
                period=self.stack["period"],
                group=self.stack["group"],
                instructor=self.teacher,
                lesson_hours=60,
            )
            republished = timezone.make_aware(dt.datetime(2025, 10, 10, 12, 0))
            common = {"organization": self.org, "offering": offering, "start_time": dt.time(15, 15)}
            old = ScheduleSlot.all_objects.create(
                weekday=1, end_time=dt.time(16, 35), is_deleted=True, deleted_at=republished, **common
            )
            new = ScheduleSlot.all_objects.create(weekday=2, end_time=dt.time(16, 35), **common)
            ScheduleSlot.all_objects.filter(pk=old.pk).update(created_at=AUGUST)
            ScheduleSlot.all_objects.filter(pk=new.pk).update(created_at=republished)
        result = self._count(self.teacher, supervisor=False, filters={"offering": str(offering.pk)})
        # Köhnə B.e. slotu yalnız 06.10-da qüvvədə idi; yeni Ç.a. slotu 10.10-dan — 07.10 sayılmır, 14.10 sayılır.
        self.assertEqual(
            sorted(item["date"] for item in result["items"]), [dt.date(2025, 10, 6), dt.date(2025, 10, 14)]
        )

    def test_recording_the_lesson_clears_the_slot(self):
        with bypass_rls():
            Lesson.objects.create(
                organization=self.org,
                offering=self.offering,
                date=dt.date(2025, 10, 15),
                kind=LessonKind.SEMINAR,
                hours=2,
                start_time=dt.time(10, 10),
            )
        self.assertEqual(self._count(self.teacher, supervisor=False)["count"], 0)

    @override_settings(
        CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "llu"}}
    )
    def test_query_count_is_flat_and_result_is_cached(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        def real(ctx):
            # `bypass_rls()` öz `set_config`/`current_setting` sətirlərini yazır — onlar sayılmır.
            return [q["sql"] for q in ctx.captured_queries if "app.bypass_rls" not in q["sql"]]

        with CaptureQueriesContext(connection) as first:
            self._count(self.teacher, supervisor=False)
        self.assertEqual(len(real(first)), 2)  # slotlar + dərs cütləri
        with CaptureQueriesContext(connection) as second:
            self._count(self.teacher, supervisor=False)
        self.assertEqual(real(second), [])  # keşdən

    def test_rows_flag_off_schedule_lessons_and_csv_carries_the_reason(self):
        with bypass_rls():
            rows = service.build_rows(Lesson.objects.filter(offering=self.offering))
        by_id = {row["id"]: row for row in rows}
        self.assertTrue(by_id[str(self.off_lesson.pk)]["off_schedule"])
        self.assertEqual(by_id[str(self.off_lesson.pk)]["off_schedule_reason"], "Əvəzetmə dərsi")
        csv_lines = service.csv_rows(rows)
        self.assertEqual(len(csv_lines[0]), len(csv_lines[1]))
        self.assertIn("Əvəzetmə dərsi", [cell for line in csv_lines for cell in line])

    def test_section_renders_the_card_and_the_badge(self):
        client = Client()
        client.force_login(self.teacher)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        url = reverse("accounts:profile_section_fragment", kwargs={"section": "lessons-log"})
        response = client.get(url, {"ll_range": "custom", "ll_from": "2025-09-01", "ll_to": "2026-01-31"})
        self.assertEqual(response.status_code, 200)
        unrecorded = response.context["lessons_log_section"]["unrecorded"]
        self.assertGreaterEqual(unrecorded["count"], 1)
        html = response.json()["html"] if response.get("Content-Type", "").startswith("application/json") else ""
        html = html or response.content.decode()
        self.assertIn("llog-unrec", html)
        self.assertIn("Cədvəldə var, qeydə alınmayıb", html)
        self.assertIn("llog-offsched", html)
