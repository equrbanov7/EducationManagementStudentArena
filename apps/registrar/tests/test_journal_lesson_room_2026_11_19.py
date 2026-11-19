"""Jurnal dərs xanasında OTAQ — saat aralığının yanında, yalnız əməkdaşa (sahib 2026-11-19).

Sahib: «dərs xanasını vurub açanda … keçən dəfə dərs saatını əlavə etmişdik — yanında hansı otaqda dərs keçib, o da
görünsün». Mənbə sırası: dərsin öz otağı (``Lesson.room``) → həmin gün + saatın cədvəl slotu → heç nə (boşluq).
Görünürlük saat ilə EYNİDİR (``journal_lesson_timing.show_lesson_timing``): jurnalın öz müəllimi görmür.
"""

from __future__ import annotations

import datetime
from io import BytesIO

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import journal_lesson_timing as timing
from apps.registrar.models import CourseOffering, Enrollment, Lesson, LessonKind, ScheduleSlot, Subject
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()

#: 2026-10-05 / 12 / 19 — bazar ertəsi (həftə günü 1); 2026-10-07 — çərşənbə.
MONDAY = datetime.date(2026, 10, 5)


class JournalLessonRoomTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("jr_owner", "jr_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="JR Univ",
                slug="jr-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            faculty = OrgUnit.objects.create(
                organization=cls.org, name="Fakültə", slug="jr-f", unit_type=OrgUnitType.FACULTY
            )
            cls.chair_unit = OrgUnit.objects.create(
                organization=cls.org, name="Kafedra", slug="jr-c", unit_type=OrgUnitType.CHAIR, parent=faculty
            )
            group = OrgUnit.objects.create(
                organization=cls.org, name="G1", slug="jr-g", unit_type=OrgUnitType.GROUP, parent=cls.chair_unit
            )
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="Payız 2026",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2026/2027",
                start_date=datetime.date(2026, 9, 1),
                end_date=datetime.date(2027, 1, 31),
                is_current=True,
            )
            cls.teacher = User.objects.create_user("jr_teacher", "jr_teacher@qku.edu.az", "pw")
            cls.chair = User.objects.create_user("jr_chair", "jr_chair@qku.edu.az", "pw")
            cls.student = User.objects.create_user("jr_student", "jr_student@qku.edu.az", "pw")
            for user, role, unit in (
                (cls.teacher, "teacher", cls.chair_unit),
                (cls.chair, "chair_head", cls.chair_unit),
                (cls.student, "student", group),
            ):
                Membership.objects.create(
                    user=user,
                    organization=cls.org,
                    role=cls.org.roles.get(name=role),
                    scope_unit=unit,
                    is_primary=True,
                    is_active=True,
                )
            subject = Subject.objects.create(organization=cls.org, code="JR101", name="Alqoritmlər")
            cls.offering = CourseOffering.objects.create(
                organization=cls.org,
                subject=subject,
                period=cls.period,
                group=group,
                instructor=cls.teacher,
                lesson_hours=30,
            )
            Enrollment.objects.create(
                organization=cls.org, student=cls.student, offering=cls.offering, status="enrolled"
            )
            cls.registry_room = cls.org.exam_rooms.create(name="305", code="R-305", building="Baş korpus")
            cls.slot_room = cls.org.exam_rooms.create(name="210", code="R-210", building="2-ci korpus")
            # Cədvəl: bazar ertəsi 10:10 mühazirə — reyestrdəki «210»; 13:35 seminar — reyestrdə olmayan mətn.
            for start, end, kind, room in (
                (datetime.time(10, 10), datetime.time(11, 40), "lecture", "210"),
                (datetime.time(13, 35), datetime.time(15, 5), "seminar", "Zal B"),
            ):
                ScheduleSlot.objects.create(
                    organization=cls.org,
                    offering=cls.offering,
                    weekday=1,
                    start_time=start,
                    end_time=end,
                    kind=kind,
                    room=room,
                )
            cls.own_room = cls._lesson(MONDAY, datetime.time(10, 10), LessonKind.LECTURE, room=cls.registry_room)
            cls.from_slot = cls._lesson(MONDAY + datetime.timedelta(days=7), datetime.time(10, 10), LessonKind.LECTURE)
            cls.slot_text = cls._lesson(MONDAY + datetime.timedelta(days=14), datetime.time(13, 35), LessonKind.SEMINAR)
            # Çərşənbə — cədvəldə slot yoxdur, dərsdə otaq yoxdur → heç nə göstərilmir.
            cls.no_room = cls._lesson(MONDAY + datetime.timedelta(days=2), datetime.time(8, 30), LessonKind.LECTURE)

    @classmethod
    def _lesson(cls, date, start, kind, room=None):
        end = (datetime.datetime.combine(date, start) + datetime.timedelta(minutes=90)).time()
        return Lesson.objects.create(
            organization=cls.org,
            offering=cls.offering,
            date=date,
            kind=kind,
            hours=2,
            start_time=start,
            end_time=end,
            instructor=cls.teacher,
            created_by=cls.teacher,
            room=room,
        )

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _lessons(self):
        return list(Lesson.objects.filter(offering=self.offering).order_by("date", "created_at"))

    # ── Mənbə sırası ─────────────────────────────────────────────────────────

    def test_room_source_priority(self):
        rooms = timing.lesson_room_map(self.offering, self._lessons())
        self.assertEqual(rooms[self.own_room.pk], {"name": "305", "label": "305 (Baş korpus)", "from_slot": False})
        # Dərsdə otaq yoxdur → cədvəl slotunun mətni reyestrdə TƏK otağa uyğun gəlir → onun etiketi.
        self.assertEqual(rooms[self.from_slot.pk], {"name": "210", "label": "210 (2-ci korpus)", "from_slot": True})
        # Reyestrdə olmayan slot mətni cədvəldə yazıldığı kimi.
        self.assertEqual(rooms[self.slot_text.pk], {"name": "Zal B", "label": "Zal B", "from_slot": True})
        # Nə dərsdə, nə cədvəldə → açar yoxdur (UI-da boşluq, «—» yox).
        self.assertNotIn(self.no_room.pk, rooms)

    def test_own_room_wins_over_slot_room(self):
        """Dərsin öz otağı cədvəl slotundakından fərqlidirsə DƏRSİNKİ göstərilir (faktiki keçirilən yer)."""
        rooms = timing.lesson_room_map(self.offering, self._lessons())
        self.assertEqual(rooms[self.own_room.pk]["name"], "305")  # slotda «210» yazılıb

    def test_rooms_resolve_without_n_plus_one(self):
        """Bütün səhifənin otaqları: slotlar (memo) + TƏK otaq sorğusu — dərs sayından asılı deyil."""
        with bypass_rls():
            for week in range(3, 9):
                self._lesson(MONDAY + datetime.timedelta(days=7 * week), datetime.time(10, 10), LessonKind.LECTURE)
            lessons = self._lessons()
        offering = CourseOffering.objects.select_related("organization", "period").get(pk=self.offering.pk)
        with CaptureQueriesContext(connection) as queries:
            rooms = timing.lesson_room_map(offering, lessons)
        self.assertLessEqual(len(queries), 2, [q["sql"][:120] for q in queries])
        self.assertEqual(len(rooms), len(lessons) - 1)  # yalnız çərşənbə dərsi otaqsızdır

    def test_inactive_registry_room_is_not_guessed_from_slot_text(self):
        """Slot mətni yalnız AKTİV reyestr otağına bağlanır; deaktiv otaqda mətn olduğu kimi qalır."""
        with bypass_rls():
            self.org.exam_rooms.filter(pk=self.slot_room.pk).update(is_active=False)
        rooms = timing.lesson_room_map(self.offering, self._lessons())
        self.assertEqual(rooms[self.from_slot.pk], {"name": "210", "label": "210", "from_slot": True})

    # ── Jurnal səhifəsi ──────────────────────────────────────────────────────

    def test_staff_sees_room_next_to_time_and_in_day_popup(self):
        html = self._client(self.chair).get(reverse("registrar:journal_detail", args=[self.offering.id]) + "?lw=0")
        self.assertEqual(html.status_code, 200)
        body = html.content.decode()
        self.assertIn("data-jd-th-room", body)
        self.assertIn('data-room="305 (Baş korpus)"', body)
        self.assertIn('data-room="210 (2-ci korpus) · cədvəl üzrə"', body)
        self.assertIn('data-room="Zal B · cədvəl üzrə"', body)
        self.assertIn('data-room=""', body)  # otaqsız dərs — pəncərədə sətir gizli qalır
        self.assertIn("data-jd-day-room-row", body)
        self.assertEqual(body.count("data-jd-th-room "), 3)  # dörd dərsdən üçündə otaq var
        self.assertIn("jd2-th-room--slot", body)

    def test_journal_teacher_sees_no_room(self):
        body = (
            self._client(self.teacher)
            .get(reverse("registrar:journal_detail", args=[self.offering.id]) + "?lw=0")
            .content.decode()
        )
        self.assertNotIn("data-jd-th-room", body)
        self.assertNotIn("data-room=", body)
        self.assertNotIn("data-jd-day-room", body)

    # ── xlsx ─────────────────────────────────────────────────────────────────

    def test_staff_xlsx_has_room_column_and_header_line(self):
        from openpyxl import load_workbook

        response = self._client(self.chair).get(reverse("registrar:journal_xlsx", args=[self.offering.id]))
        self.assertEqual(response.status_code, 200)
        workbook = load_workbook(BytesIO(response.content))
        sheet = workbook["Dərslər"]
        header = [cell.value for cell in sheet[1]]
        self.assertEqual(header.index("Otaq"), header.index("Dərs saatı") + 1)  # saatın yanında
        by_date = {
            row[header.index("Tarix")]: row[header.index("Otaq")]
            for row in sheet.iter_rows(min_row=2, values_only=True)
        }
        self.assertEqual(by_date["05.10.2026"], "305 (Baş korpus)")
        self.assertEqual(by_date["12.10.2026"], "210 (2-ci korpus) (cədvəl üzrə)")
        self.assertEqual(by_date["19.10.2026"], "Zal B (cədvəl üzrə)")
        self.assertFalse(by_date["07.10.2026"])
        head = [str(cell.value or "") for cell in workbook.worksheets[0][4]]
        self.assertTrue(any("10:10–11:40" in text and "305" in text for text in head), head)

    def test_teacher_xlsx_has_no_room(self):
        from openpyxl import load_workbook

        response = self._client(self.teacher).get(reverse("registrar:journal_xlsx", args=[self.offering.id]))
        workbook = load_workbook(BytesIO(response.content))
        self.assertNotIn("Dərslər", workbook.sheetnames)
        texts = "\n".join(str(c.value) for ws in workbook.worksheets for row in ws.iter_rows() for c in row if c.value)
        self.assertNotIn("Baş korpus", texts)
        self.assertNotIn("Zal B", texts)
