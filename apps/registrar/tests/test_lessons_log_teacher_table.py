"""«Keçilmiş dərslər» → «Cədvəl formasında bax» (sahib 2026-11-11) + tənbəl uclar + səhifələmə.

Nəyi qoruyur
------------
1. **Patok bir dəfə sayılır.** İki qrupa eyni tarix + saatda keçilən mühazirə BİR sətirdir («234 İT, 234 K»),
   8 dərs = 16 saat (qrup başına təkrar sayılmır).
2. **Bölünmüş seminar ayrı sətirlərdir** (fərqli saat → patok deyil), laboratoriya alt qrupları öz sətrində.
3. **Cəmlər**: ümumi, növ üzrə və tədris dili (bölmə) üzrə — az / ing.
4. **«Ətraflı bax»** ucu sətrin dərslərini (tarix, gün, saat, mövzu, iştirak) verir.
5. **Excel**: «İcmal» + «Dərslər» vərəqləri; formula-bənzər mövzu neytrallaşdırılır.
6. **Əhatə**: əhatədən kənar nəzarətçi və başqa müəllim 403 alır; müəllim öz cədvəlini görür.
7. **Süzgəc patokun adını qısaltmır** («Qrup: 234 K» → sətir yenə «234 İT, 234 K»).
8. **Səhifənin sorğu büdcəsi**: ilk cavab xana cədvəlinə yalnız səhifə aqreqatı üçün toxunur, cədvəl slotlarını
   oxumur; ağır hesab tənbəl ucdadır. Gün siyahısı səhifələnir (gün bölünmür).
"""

from __future__ import annotations

import datetime as dt
from io import BytesIO

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.organizations.models import OrgUnit
from apps.registrar import lessons_log_teacher_table as table_service
from apps.registrar.models import (
    AttendanceStatus,
    CourseOffering,
    Enrollment,
    Lesson,
    LessonKind,
    LessonMark,
    Subject,
)
from apps.syllabus.tests.factories import activate_member, make_academic_stack, make_org
from core.constants import OrgUnitType, RoleScopeType
from core.rls import bypass_rls

User = get_user_model()

PASSWORD = "StrongPass123!"
TEACHER_PERMS = ["course.view", "grade.input", "syllabus.edit"]
SUPERVISOR_PERMS = ["course.view", "journal.roster", "unit.view"]
WINDOW = {"ll_range": "custom", "ll_from": "2025-09-01", "ll_to": "2026-01-31"}
FORMULA_TOPIC = '=HYPERLINK("http://x")'


@override_settings(UNIVERSITY_MODE=True)
class TeacherTableTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            cls.org = make_org("ltt-univ")
            period = make_academic_stack(cls.org, code="LTT101")["period"]

            def unit(name, unit_type, parent=None, **settings):
                return OrgUnit.objects.create(
                    organization=cls.org,
                    name=name,
                    slug=f"ltt-{len(name)}-{abs(hash(name)) % 10**8}",
                    unit_type=unit_type,
                    parent=parent,
                    settings=settings,
                )

            cls.f1 = unit("Mühəndislik fakültəsi", OrgUnitType.FACULTY)
            cls.f2 = unit("İqtisadiyyat fakültəsi", OrgUnitType.FACULTY)
            cls.g_k = unit("234 K", OrgUnitType.GROUP, cls.f1, language_sector="az")
            cls.g_it = unit("234 İT", OrgUnitType.GROUP, cls.f1, language_sector="az")
            cls.g_en = unit("234 E", OrgUnitType.GROUP, cls.f1, sector="en")  # köhnə açar + ləqəb → «ing»
            cls.g_x = unit("500 X", OrgUnitType.GROUP, cls.f2, language_sector="az")

            cls.teacher = User.objects.create_user("ltt_teacher", "ltt_teacher@qku.edu.az", PASSWORD)
            cls.teacher.first_name, cls.teacher.last_name = "Aynur", "Məmmədova"
            cls.teacher.save(update_fields=["first_name", "last_name"])
            cls.other = User.objects.create_user("ltt_other", "ltt_other@qku.edu.az", PASSWORD)
            cls.rim = User.objects.create_user("ltt_rim", "ltt_rim@qku.edu.az", PASSWORD)
            cls.dean2 = User.objects.create_user("ltt_dean2", "ltt_dean2@qku.edu.az", PASSWORD)
            cls.student = User.objects.create_user("ltt_student", "ltt_student@qku.edu.az", PASSWORD)
            activate_member(cls.org, cls.teacher, "teacher", permissions=TEACHER_PERMS)
            activate_member(cls.org, cls.other, "teacher", permissions=TEACHER_PERMS)
            activate_member(cls.org, cls.student, "student", permissions=["course.view"], level=10)
            activate_member(
                cls.org,
                cls.rim,
                "rim_head",
                permissions=SUPERVISOR_PERMS,
                level=90,
                scope_type=RoleScopeType.ORGANIZATION,
            )
            activate_member(
                cls.org,
                cls.dean2,
                "dean",
                permissions=SUPERVISOR_PERMS,
                level=70,
                scope_type=RoleScopeType.UNIT,
                scope_unit=cls.f2,
            )
            for user, role in (
                (cls.teacher, "teacher"),
                (cls.other, "teacher"),
                (cls.rim, "rim_head"),
                (cls.dean2, "dean"),
                (cls.student, "student"),
            ):
                profile = user.profile
                profile.role = role
                profile.save(update_fields=["role"])

            prog = Subject.objects.create(organization=cls.org, code="LTT-P", name="Proqramlaşdırma")
            algo = Subject.objects.create(organization=cls.org, code="LTT-A", name="Alqoritmlər")

            def offering(subject, group, teacher):
                return CourseOffering.objects.create(
                    organization=cls.org,
                    subject=subject,
                    period=period,
                    group=group,
                    instructor=teacher,
                    lesson_hours=60,
                )

            cls.o_k = offering(prog, cls.g_k, cls.teacher)
            cls.o_it = offering(prog, cls.g_it, cls.teacher)
            cls.o_en = offering(algo, cls.g_en, cls.teacher)
            cls.o_x = offering(prog, cls.g_x, cls.other)

            def lesson(offering_, day, kind, start, **extra):
                return Lesson.objects.create(
                    organization=cls.org,
                    offering=offering_,
                    date=day,
                    kind=kind,
                    hours=2,
                    start_time=start,
                    end_time=(dt.datetime.combine(day, start) + dt.timedelta(minutes=80)).time() if start else None,
                    topic=extra.pop("topic", f"Mövzu {day:%d.%m}"),
                    instructor=cls.teacher if offering_ is not cls.o_x else cls.other,
                    created_by=cls.teacher,
                    **extra,
                )

            first = dt.date(2025, 9, 8)  # bazar ertəsi
            cls.lecture_days = [first + dt.timedelta(days=7 * week) for week in range(8)]
            cls.patok_lessons = []
            for index, day in enumerate(cls.lecture_days):
                # PATOK mühazirə: iki jurnalda iki sətir, eyni tarix + saat → BİR dərs.
                topic = FORMULA_TOPIC if index == 0 else f"Mühazirə {index + 1}"
                cls.patok_lessons.append(lesson(cls.o_k, day, LessonKind.LECTURE, dt.time(9, 0), topic=topic))
                cls.patok_lessons.append(lesson(cls.o_it, day, LessonKind.LECTURE, dt.time(9, 0), topic=topic))
            for day in cls.lecture_days[:7]:
                # Seminar qrup başına AYRI keçilir (fərqli saat) → iki sətir.
                lesson(cls.o_k, day, LessonKind.SEMINAR, dt.time(11, 0))
                lesson(cls.o_it, day, LessonKind.SEMINAR, dt.time(13, 0))
            for day in cls.lecture_days[:2]:
                lesson(cls.o_k, day + dt.timedelta(days=1), LessonKind.LAB, dt.time(9, 0), lab_group=1)
                lesson(cls.o_k, day + dt.timedelta(days=1), LessonKind.LAB, dt.time(11, 0), lab_group=2)
            for day in cls.lecture_days[:3]:
                lesson(cls.o_en, day + dt.timedelta(days=2), LessonKind.LECTURE, dt.time(9, 0))
            # Başqa müəllimin (başqa fakültə) dərsi — cədvələ DÜŞMƏMƏLİDİR.
            lesson(cls.o_x, first, LessonKind.LECTURE, dt.time(9, 0))

            enrollment_k = Enrollment.objects.create(organization=cls.org, student=cls.student, offering=cls.o_k)
            enrollment_it = Enrollment.objects.create(organization=cls.org, student=cls.student, offering=cls.o_it)
            LessonMark.objects.create(
                organization=cls.org,
                lesson=cls.patok_lessons[0],
                enrollment=enrollment_k,
                status=AttendanceStatus.PRESENT,
                entered_by=cls.teacher,
            )
            LessonMark.objects.create(
                organization=cls.org,
                lesson=cls.patok_lessons[1],
                enrollment=enrollment_it,
                status=AttendanceStatus.ABSENT,
                entered_by=cls.teacher,
            )

    # ── köməkçilər ──────────────────────────────────────────────────────────

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _get(self, user, name, **params):
        return self._client(user).get(reverse(name), dict(WINDOW, **params))

    def _table(self, user=None, **params):
        params.setdefault("ll_teacher", str(self.teacher.pk))
        response = self._get(user or self.rim, "registrar:lessons_log_teacher_table", **params)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    @staticmethod
    def _row(payload, groups, kind):
        return next(row for row in payload["rows"] if row["groups"] == groups and row["kind"] == kind)

    # ── 1–2. Sətirlər ───────────────────────────────────────────────────────

    def test_patok_lecture_is_one_row_counted_once_with_joined_group_names(self):
        payload = self._table()
        row = self._row(payload, "234 İT, 234 K", "lecture")
        self.assertEqual((row["lessons"], row["hours"]), (8, 16))
        self.assertEqual(row["text"], "16 saat (8 dərs)")
        self.assertTrue(row["is_joint"])
        self.assertEqual(row["subject"], "Proqramlaşdırma")
        self.assertEqual(payload["teacher"]["name"], "Aynur Məmmədova")
        # Patokun qrupları ayrıca mühazirə sətri kimi TƏKRAR görünmür.
        lecture_groups = sorted(r["groups"] for r in payload["rows"] if r["kind"] == "lecture")
        self.assertEqual(lecture_groups, ["234 E", "234 İT, 234 K"])

    def test_split_seminars_and_lab_subgroups_are_separate_rows(self):
        payload = self._table()
        for groups in ("234 K", "234 İT"):
            row = self._row(payload, groups, "seminar")
            self.assertEqual((row["lessons"], row["hours"], row["text"]), (7, 14, "14 saat (7 dərs)"))
            self.assertFalse(row["is_joint"])
        for groups in ("234 K · Lab-1", "234 K · Lab-2"):
            self.assertEqual(self._row(payload, groups, "lab")["lessons"], 2)

    def test_lessons_at_different_times_are_not_a_patok(self):
        events = table_service.load_events(
            Lesson.objects.filter(offering__in=[self.o_k, self.o_it], kind=LessonKind.SEMINAR)
        )
        self.assertEqual(len(events), 14)
        self.assertTrue(all(len(event["lessons"]) == 1 for event in events))

    def test_untimed_lecture_joins_but_untimed_seminar_does_not(self):
        day = dt.date(2025, 12, 1)
        common = {"organization": self.org, "date": day, "hours": 2, "instructor": self.teacher}
        for kind in (LessonKind.LECTURE, LessonKind.SEMINAR):
            Lesson.objects.create(offering=self.o_k, kind=kind, **common)
            Lesson.objects.create(offering=self.o_it, kind=kind, **common)
        events = table_service.load_events(Lesson.objects.filter(date=day))
        sizes = sorted((str(event["kind"]), len(event["lessons"])) for event in events)
        self.assertEqual(sizes, [("lecture", 2), ("seminar", 1), ("seminar", 1)])

    # ── 3. Cəmlər ───────────────────────────────────────────────────────────

    def test_totals_by_kind_and_by_sector(self):
        totals = self._table()["totals"]
        self.assertEqual((totals["lessons"], totals["hours"], totals["text"]), (29, 58, "58 saat (29 dərs)"))
        by_kind = {item["key"]: (item["lessons"], item["hours"]) for item in totals["by_kind"]}
        self.assertEqual(by_kind, {"lecture": (11, 22), "seminar": (14, 28), "lab": (4, 8)})
        self.assertEqual([item["key"] for item in totals["by_kind"]], ["lecture", "seminar", "lab"])
        by_sector = {item["key"]: (item["lessons"], item["hours"]) for item in totals["by_sector"]}
        self.assertEqual(by_sector, {"az": (26, 52), "ing": (3, 6)})
        self.assertEqual(totals["by_sector"][1]["text"], "6 saat (3 dərs)")

    def test_mixed_az_ing_patok_counts_as_ing(self):
        """Sahib 2026-11-11: az + ing qrupların birgə patoku İngilis bölməsinə sayılır."""
        from types import SimpleNamespace
        from unittest import mock

        def lesson(lang):
            return SimpleNamespace(offering=SimpleNamespace(group_id=1, group=lang))

        with mock.patch("apps.registrar.syllabus_carry.group_language", side_effect=lambda group: group):
            self.assertEqual(table_service._event_sector({"lessons": [lesson("az"), lesson("ing")]}), "ing")
            self.assertEqual(table_service._event_sector({"lessons": [lesson("az"), lesson("az")]}), "az")
            self.assertEqual(
                table_service._event_sector({"lessons": [lesson("az"), lesson("rus")]}), table_service.SECTOR_MIXED
            )

    def test_group_filter_keeps_the_full_patok_name(self):
        payload = self._table(ll_group="234 K")
        row = self._row(payload, "234 İT, 234 K", "lecture")
        self.assertEqual(row["lessons"], 8)
        # Süzgəcə uyğun gəlməyən sətirlər (234 İT-nin öz seminarı, ingilis qrupu) düşür.
        self.assertFalse([r for r in payload["rows"] if r["groups"] in ("234 İT", "234 E")])
        self.assertEqual(self._table(ll_kind="lab")["totals"]["lessons"], 4)

    # ── 4. Təfərrüat ────────────────────────────────────────────────────────

    def test_detail_endpoint_lists_the_rows_lessons(self):
        key = self._row(self._table(), "234 İT, 234 K", "lecture")["key"]
        response = self._get(
            self.rim, "registrar:lessons_log_teacher_lessons", ll_teacher=str(self.teacher.pk), row=key
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["row"]["groups"], "234 İT, 234 K")
        lessons = payload["lessons"]
        self.assertEqual(len(lessons), 8)
        self.assertEqual([item["date"] for item in lessons], [day.isoformat() for day in self.lecture_days])
        first = lessons[0]
        self.assertEqual((first["date_text"], first["time"], first["hours"]), ("08.09.2025", "09:00 – 10:20", 2))
        self.assertTrue(first["weekday"])
        self.assertEqual(first["topic"], FORMULA_TOPIC)  # iki jurnalda eyni mövzu bir dəfə yazılır
        # İştirak iki qrupun cəmidir: 1 iştirak / 2 qeyd.
        self.assertEqual((first["present"], first["marked"], first["attendance"]), (1, 2, "1 / 2"))

    def test_detail_endpoint_rejects_an_unknown_row(self):
        response = self._get(
            self.rim, "registrar:lessons_log_teacher_lessons", ll_teacher=str(self.teacher.pk), row="nope"
        )
        self.assertEqual(response.status_code, 404)

    # ── 5. Excel ────────────────────────────────────────────────────────────

    def test_xlsx_has_summary_and_detail_sheets_and_neutralises_formulas(self):
        from openpyxl import load_workbook

        response = self._get(self.rim, "registrar:lessons_log_teacher_xlsx", ll_teacher=str(self.teacher.pk))
        self.assertEqual(response.status_code, 200)
        self.assertIn("spreadsheetml", response["Content-Type"])
        self.assertIn(".xlsx", response["Content-Disposition"])
        workbook = load_workbook(BytesIO(response.content))
        self.assertEqual(workbook.sheetnames, ["İcmal", "Dərslər"])
        summary = [[cell for cell in row] for row in workbook["İcmal"].iter_rows(values_only=True)]
        flat = [value for row in summary for value in row if value is not None]
        self.assertIn("Aynur Məmmədova", flat)
        self.assertIn("234 İT, 234 K", flat)
        self.assertIn("16 saat (8 dərs)", flat)
        self.assertIn("58 saat (29 dərs)", flat)
        self.assertIn("İngilis bölməsi", flat)
        details = list(workbook["Dərslər"].iter_rows(values_only=True))
        self.assertEqual(len(details), 1 + 29)  # başlıq + hər BİRGƏ dərs bir sətir
        topics = [row[8] for row in details[1:]]
        self.assertIn("'" + FORMULA_TOPIC, topics)
        self.assertNotIn(FORMULA_TOPIC, topics)
        for sheet in workbook.worksheets:
            for row in sheet.iter_rows():
                for cell in row:
                    self.assertNotEqual(cell.data_type, "f")

    # ── 6. Əhatə ────────────────────────────────────────────────────────────

    def test_supervisor_outside_scope_is_denied(self):
        for name in (
            "registrar:lessons_log_teacher_table",
            "registrar:lessons_log_teacher_lessons",
            "registrar:lessons_log_teacher_xlsx",
        ):
            response = self._get(self.dean2, name, ll_teacher=str(self.teacher.pk))
            self.assertEqual(response.status_code, 403, name)
            self.assertEqual(response.json()["error"], "teacher_out_of_scope")
        # Öz əhatəsindəki müəllimi görür.
        own = self._get(self.dean2, "registrar:lessons_log_teacher_table", ll_teacher=str(self.other.pk))
        self.assertEqual(own.status_code, 200)
        self.assertEqual([row["groups"] for row in own.json()["rows"]], ["500 X"])

    def test_plain_teacher_cannot_open_another_teachers_table(self):
        response = self._get(self.other, "registrar:lessons_log_teacher_table", ll_teacher=str(self.teacher.pk))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "teacher_filter_forbidden")

    def test_teacher_sees_own_table_without_the_param(self):
        response = self._get(self.teacher, "registrar:lessons_log_teacher_table")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["totals"]["lessons"], 29)

    def test_supervisor_must_pick_a_teacher_and_anonymous_is_redirected(self):
        self.assertEqual(self._get(self.rim, "registrar:lessons_log_teacher_table", ll_teacher="").status_code, 400)
        self.assertEqual(self._get(self.rim, "registrar:lessons_log_teacher_table", ll_teacher="x'y").status_code, 400)
        self.assertEqual(Client().get(reverse("registrar:lessons_log_teacher_table"), WINDOW).status_code, 302)

    def test_table_query_count_is_constant(self):
        client = self._client(self.rim)
        url = reverse("registrar:lessons_log_teacher_table")
        params = dict(WINDOW, ll_teacher=str(self.teacher.pk))
        client.get(url, params)  # isinmə
        with CaptureQueriesContext(connection) as before:
            client.get(url, params)
        for day in self.lecture_days:
            Lesson.objects.create(
                organization=self.org,
                offering=self.o_en,
                date=day + dt.timedelta(days=3),
                kind=LessonKind.SEMINAR,
                hours=2,
                start_time=dt.time(15, 0),
                instructor=self.teacher,
            )
        with CaptureQueriesContext(connection) as after:
            payload = client.get(url, params).json()
        self.assertEqual(payload["totals"]["lessons"], 37)
        self.assertLessEqual(len(after.captured_queries), len(before.captured_queries))

    # ── 8. Bölmə: düymə, tənbəl hesab, səhifələmə, sorğu büdcəsi ─────────────

    def _fragment(self, user, **params):
        url = reverse("accounts:profile_section_fragment", kwargs={"section": "lessons-log"})
        return self._client(user).get(url, dict(WINDOW, **params))

    @staticmethod
    def _html(response) -> str:
        """Fraqment JSON zərfindədir (`{"html": …}`); tam səhifə cavabında birbaşa mətn."""
        if response.get("Content-Type", "").startswith("application/json"):
            return response.json()["html"]
        return response.content.decode()

    def test_button_shows_only_when_a_teacher_is_selected(self):
        plain = self._fragment(self.rim)
        self.assertFalse(plain.context["lessons_log_section"]["teacher_table"]["show"])
        self.assertNotIn("data-llog-table-open", self._html(plain))
        picked = self._fragment(self.rim, ll_teacher=str(self.teacher.pk))
        section = picked.context["lessons_log_section"]
        self.assertTrue(section["teacher_table"]["show"])
        html = self._html(picked)
        self.assertIn("data-llog-table-open", html)
        self.assertIn("Cədvəl formasında bax", html)
        self.assertIn("Excel kimi yüklə", html)
        self.assertIn("ll_teacher=%s" % self.teacher.pk, section["teacher_table"]["table_url"])
        # Müəllim öz cədvəlini filtr seçmədən açır.
        self.assertTrue(self._fragment(self.teacher).context["lessons_log_section"]["teacher_table"]["show"])

    def test_secondary_filters_are_collapsed_until_used(self):
        section = self._fragment(self.rim).context["lessons_log_section"]
        fields = {field["name"]: field for field in section["filters"]["fields"]}
        self.assertFalse(fields["ll_q"]["secondary"])
        self.assertFalse(fields["ll_teacher"]["secondary"])
        self.assertTrue(fields["ll_kind"]["secondary"])
        self.assertTrue(fields["ll_from"]["secondary"])
        html = self._html(self._fragment(self.rim))
        self.assertIn("Daha çox süzgəc", html)
        used = self._fragment(self.rim, ll_kind="lab").context["lessons_log_section"]["filters"]
        self.assertTrue(used["more_open"])
        self.assertEqual(used["more_count"], 1)

    def test_day_list_is_paginated_and_day_heads_show_full_day_totals(self):
        section = self._fragment(self.rim).context["lessons_log_section"]
        self.assertEqual(section["totals"]["lessons"], 38)
        rows = section["rows"]
        self.assertEqual(len(rows), section["page_size"])
        self.assertTrue(section["has_more"])
        self.assertEqual(section["next_offset"], section["page_size"])
        for day in section["days"]:
            self.assertGreaterEqual(day["lessons"], len(day["rows"]))
        client = self._client(self.rim)
        total, offset, pages, html = len(rows), section["next_offset"], 0, ""
        while offset is not None and pages < 10:
            payload = client.get(section["rows_url"], {"ll_offset": offset}).json()
            self.assertTrue(payload["ok"])
            self.assertGreater(payload["count"], 0)
            self.assertEqual(payload["html"].count("<tr class="), payload["count"])
            html += payload["html"]
            total += payload["count"]
            pages += 1
            offset = payload["next_offset"]
        self.assertEqual(pages, 1)
        self.assertEqual(total, 38)  # heç bir dərs itmir və təkrarlanmır
        # Gün başlığı günün TAM cəmidir: 08.09-da patokun 2 jurnal sətri + 2 seminar + başqa müəllimin dərsi = 5.
        self.assertIn('data-llog-day="2025-09-08"', html)
        self.assertIn("5 dərs", html)
        self.assertEqual(client.get(section["rows_url"], {"ll_offset": "zzz"}).json()["count"], 30)

    def test_initial_page_load_defers_the_heavy_work(self):
        client = self._client(self.rim)
        url = reverse("accounts:profile_section_fragment", kwargs={"section": "lessons-log"})
        client.get(url, WINDOW)  # isinmə (sessiya / icazə keşi)
        with CaptureQueriesContext(connection) as captured:
            response = client.get(url, WINDOW)
        section = response.context["lessons_log_section"]
        self.assertTrue(section["insights_pending"])
        self.assertEqual(
            [tile["key"] for tile in section["kpi_tiles"]], ["lessons", "hours", "attendance", "empty", "late"]
        )
        self.assertEqual(section["kpi_tiles"][0]["value"], 38)
        self.assertEqual(section["kpi_tiles"][2]["tone"], "skeleton")
        sql = [query["sql"] for query in captured.captured_queries]
        # Xana cədvəli YALNIZ səhifədəki dərslərin aqreqatı üçün oxunur (dövr üzrə ağır aqreqat yoxdur) …
        self.assertEqual(sum('FROM "registrar_lessonmark"' in text for text in sql), 1)
        self.assertFalse([text for text in sql if 'JOIN "registrar_lessonmark"' in text])
        # … cədvəl slotlarının SƏTİRLƏRİ də oxunmur («qeydə alınmayıb» tutuşdurması tənbəl ucdadır).
        self.assertFalse([text for text in sql if text.startswith('SELECT "registrar_scheduleslot".')])
        self.assertLessEqual(len(sql), PAGE_QUERY_BUDGET, "Bölmənin ilk cavabı sorğu büdcəsini aşdı")

    def test_practical_label_does_not_query_per_row(self):
        """«Praktiki məşğələ» etiketi: bayraqlı, kafedrası boş fənnin seminarları sətir başına sorğu etmir
        (prod surətində 90 sətirlik səhifədə 65 əlavə sorğu idi — `design_practical_scope.prime`)."""
        from apps.registrar import lessons_log as service

        CourseOffering.objects.filter(pk__in=[self.o_k.pk, self.o_it.pk]).update(seminar_is_practical=True)
        seminars = Lesson.objects.filter(kind=LessonKind.SEMINAR, offering__in=[self.o_k, self.o_it])
        with CaptureQueriesContext(connection) as few:
            self.assertEqual(len(service.build_rows(seminars, limit=2)), 2)
        with CaptureQueriesContext(connection) as many:
            rows = service.build_rows(seminars, limit=14)
        self.assertEqual(len(rows), 14)
        self.assertEqual({row["kind_label"] for row in rows}, {"Seminar"})  # kafedra «praktiki» siyahısında deyil
        self.assertLessEqual(len(many.captured_queries), len(few.captured_queries))

    def test_insights_endpoint_returns_the_deferred_numbers(self):
        section = self._fragment(self.rim).context["lessons_log_section"]
        response = self._client(self.rim).get(section["insights_url"])
        self.assertEqual(response.status_code, 200)
        tiles = {tile["key"]: tile for tile in response.json()["kpi"]}
        self.assertEqual(tiles["lessons"]["value"], "38")
        self.assertEqual(tiles["attendance"]["value"], "50%")
        self.assertEqual(tiles["empty"]["value"], "36")
        self.assertEqual(tiles["empty"]["tone"], "danger")
        self.assertIn("unrecorded_html", response.json())
        # Müəllim yalnız ÖZ dərslərinin rəqəmini alır (əhatə bölmə ilə eynidir).
        own = self._client(self.other).get(reverse("accounts:lessons_log_insights"), WINDOW).json()
        self.assertEqual({tile["key"]: tile["value"] for tile in own["kpi"]}["lessons"], "1")


#: Bölmə fraqmentinin (qabıq + bölmə) ilk cavabının sorğu tavanı — ölçülmüş dəyər + kiçik ehtiyat.
PAGE_QUERY_BUDGET = 33
