"""«Ana səhifə» — tələbə və müəllim kartlarının MƏZMUNU (sahib, 2026-09-25).

Nəyi qoruyur
------------
Sahibin iradı: «davamiyyət kartı — nəyin davamiyyəti, hansı fənnin qayıbı? Heç
aydın deyil».  Köhnə kart bütün fənlərin qayıbını cəmləyib proqramın xam
limitini yazırdı, «son qiymətlər» köhnə arxiv komponentlərini göstərirdi,
başlıq isə köhnəlmiş ``is_current`` bayrağına görə «2025/2026 · Yaz» deyirdi.
Bu fayl yeni müqaviləni sabitləyir:

* dövr TARİXƏ görə seçilir (köhnəlmiş bayraqlı dövr qalib gəlmir), rol adı
  lokallaşdırılır;
* davamiyyət FƏNN-FƏNN: «qayıb X / icazə Y saat», status çipi, riskli fənn
  yuxarıda, fənnin jurnalına dərin keçid;
* cari ballar: giriş balı + Midterm (2026/2027-dən TƏK, 0–20); arxiv
  komponentləri görünmür;
* müəllim: jurnalların TAM sayı, keçirilmiş/plan saatı, `/jurnal/` keçidi, Midterm
  pəncərəsinin vəziyyəti; İmtahan Mərkəzi kartında TƏK «Midterm» sətri;
* sorğu sayı fənn/açılış sayından ASILI DEYİL (1 vs 5 fənn, 1 vs 6 açılış).
"""

from __future__ import annotations

import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import Client, RequestFactory, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar.models import (
    AssessmentComponent,
    ComponentKind,
    ComponentScore,
    CourseOffering,
    Curriculum,
    Enrollment,
    KollokviumWindow,
    Lesson,
    Program,
    ScheduleSlot,
    StudentAcademicRecord,
    Subject,
)
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()

#: Sorğu büdcəsi (yalnız bölmənin öz sorğuları) — brief C: tələbə ≤ 14, müəllim ≤ 18.
STUDENT_QUERY_BUDGET = 14
TEACHER_QUERY_BUDGET = 18

#: `student_many`-nin fənləri: (qayıb saatı, dərs saatı) → 25% limitlə status.
SUBJECT_PLAN = (
    (0, 30),  # ok
    (6, 30),  # near: 6 ≥ 7,5 × 0,75
    (10, 30),  # barred: 10 > 7,5
    (2, 30),  # ok
    (1, 0),  # unknown: dərs saatı təyin olunmayıb, dərs də yoxdur
)


@override_settings(UNIVERSITY_MODE=True)
class DashboardContentBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        today = timezone.localdate()
        cls.today = today
        cls.owner = User.objects.create_user("dst_owner", "dst_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="Dst Univ",
                slug="dst-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            speciality = OrgUnit.objects.create(
                organization=cls.org, name="Kompüter elmləri", slug="dst-spec", unit_type=OrgUnitType.SPECIALTY
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org, parent=speciality, name="DST-101", slug="dst-g101", unit_type=OrgUnitType.GROUP
            )
            cls.group_one = OrgUnit.objects.create(
                organization=cls.org, parent=speciality, name="DST-102", slug="dst-g102", unit_type=OrgUnitType.GROUP
            )
            program = Program.objects.create(
                organization=cls.org, specialty_unit=speciality, code="KE", name="Kompüter elmləri"
            )
            curriculum = Curriculum.objects.create(organization=cls.org, program=program, admission_year=2026)
            # Köhnəlmiş BAYRAQLI dövr (sahibin ekranı) + tarixə düşən bayraqsız cari dövr.
            cls.stale = AcademicPeriod.objects.create(
                organization=cls.org,
                name="Yaz",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2025/2026",
                start_date=today - datetime.timedelta(days=250),
                end_date=today - datetime.timedelta(days=100),
                is_current=True,
            )
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2026/2027",
                start_date=today - datetime.timedelta(days=30),
                end_date=today + datetime.timedelta(days=90),
                is_current=False,
            )
            cls.users = {}
            for name, role in (
                ("student_many", "student"),
                ("student_one", "student"),
                ("teacher_many", "teacher"),
                ("teacher_one", "teacher"),
                ("exam_head", "exam_center_head"),
            ):
                user = User.objects.create_user("dst_%s" % name, "dst_%s@qku.edu.az" % name, "pw", first_name="Aysel")
                Membership.objects.create(
                    user=user, organization=cls.org, role=cls.org.roles.get(name=role), is_primary=True, is_active=True
                )
                user.profile.organization = cls.org
                user.profile.save(update_fields=["organization"])
                cls.users[name] = user
            cls.record = StudentAcademicRecord.objects.create(
                organization=cls.org,
                student=cls.users["student_many"],
                program=program,
                curriculum=curriculum,
                group=cls.group,
                admission_year=2026,
            )
            StudentAcademicRecord.objects.create(
                organization=cls.org,
                student=cls.users["student_one"],
                program=program,
                curriculum=curriculum,
                group=cls.group_one,
                admission_year=2026,
            )
            cls.offerings = []
            for index in range(7):
                subject = Subject.objects.create(organization=cls.org, code="DST%s" % index, name="Fənn %s" % index)
                # 7-ci açılış (`student_one`, `teacher_one`) `student_many`-nin «ən ağır» fənni ilə
                # EYNİ formadadır (Midterm balı + boş `lesson_hours`) — müqayisə yalnız SAYI ölçsün.
                lesson_hours = SUBJECT_PLAN[index][1] if index < len(SUBJECT_PLAN) else (30 if index == 5 else 0)
                cls.offerings.append(
                    CourseOffering.objects.create(
                        organization=cls.org,
                        subject=subject,
                        period=cls.period,
                        group=cls.group if index < 6 else cls.group_one,
                        instructor=cls.users["teacher_many"] if index < 6 else cls.users["teacher_one"],
                        lesson_hours=lesson_hours,
                    )
                )
            cls.enrollments = []
            for index, (absence, _hours) in enumerate(SUBJECT_PLAN):
                cls.enrollments.append(
                    Enrollment.objects.create(
                        organization=cls.org,
                        student=cls.users["student_many"],
                        offering=cls.offerings[index],
                        absence_hours=absence,
                    )
                )
            cls.enrollment_one = Enrollment.objects.create(
                organization=cls.org, student=cls.users["student_one"], offering=cls.offerings[6], absence_hours=2
            )
            # Midterm (TƏK, 0–20) — birinci fəndə (və `student_one`-un yeganə fənnində) yazılıb.
            for offering, enrollment in (
                (cls.offerings[0], cls.enrollments[0]),
                (cls.offerings[6], cls.enrollment_one),
            ):
                midterm = AssessmentComponent.objects.create(
                    organization=cls.org,
                    offering=offering,
                    name="Midterm",
                    kind=ComponentKind.KOLLOKVIUM,
                    max_score=20,
                    order=1,
                )
                ComponentScore.objects.create(
                    organization=cls.org, component=midterm, enrollment=enrollment, score=Decimal("15")
                )
            # Köhnə arxiv komponenti — ana səhifədə HEÇ VAXT görünməməlidir.
            archive = AssessmentComponent.objects.create(
                organization=cls.org,
                offering=cls.offerings[1],
                name="Davamiyyət və sərbəst iş (arxiv)",
                kind=ComponentKind.GENERIC,
                max_score=50,
                order=1,
            )
            ComponentScore.objects.create(
                organization=cls.org, component=archive, enrollment=cls.enrollments[1], score=Decimal("9")
            )
            for index, offering in enumerate(cls.offerings):
                for days_ago in (7, 5, 2) if index != 4 else ():  # 4-cü fənn: nə saat, nə dərs → «unknown»
                    Lesson.objects.create(
                        organization=cls.org,
                        offering=offering,
                        date=today - datetime.timedelta(days=days_ago),
                        hours=2,
                    )
                ScheduleSlot.objects.create(
                    organization=cls.org,
                    offering=offering,
                    weekday=today.isoweekday(),
                    start_time=datetime.time(8, 30),
                    end_time=datetime.time(10, 0),
                    room="305",
                )
            KollokviumWindow.objects.create(
                organization=cls.org,
                period=cls.period,
                k_index=0,
                opens_on=today - datetime.timedelta(days=2),
                closes_on=today + datetime.timedelta(days=10),
                is_active=True,
            )

    # ── köməkçilər ────────────────────────────────────────────────────────
    def client_for(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def open_dashboard(self, name):
        response = self.client_for(self.users[name]).get(reverse("accounts:profile"), {"section": "dashboard"})
        self.assertEqual(response.status_code, 200, name)
        return response

    def panel_html(self, name) -> str:
        url = reverse("accounts:profile_section_fragment", kwargs={"section": "dashboard"})
        payload = self.client_for(self.users[name]).get(url).json()
        self.assertTrue(payload["ok"], name)
        return payload["html"]

    @staticmethod
    def widget(response, key):
        widgets = {item["key"]: item for item in response.context["dashboard_section"]["widgets"]}
        return widgets.get(key)

    def count_queries(self, name) -> int:
        """Yalnız ``build_dashboard_section``-un öz sorğuları (qabıq daxil deyil)."""
        from apps.accounts.views._helpers.rbac import _collect_actor_permissions
        from apps.accounts.views.profile._sections.dashboard import build_dashboard_section

        response = self.open_dashboard(name)
        # Təzə obyektlər: müraciət kataloqu org/user obyektinə keşlənir — əvvəlki ölçmə
        # sonrakının sorğusunu «udmasın» (müqayisə ədalətli olsun).
        organization = Organization.objects.get(pk=self.org.pk)
        user = User.objects.get(pk=self.users[name].pk)
        request = RequestFactory().get(reverse("accounts:profile"), {"section": "dashboard"})
        request.user = user
        request.org_permissions = list(_collect_actor_permissions(user, organization)[0])
        with CaptureQueriesContext(connection) as captured:
            build_dashboard_section(
                request,
                {"has_access": False, "widgets": []},
                active_organization=organization,
                allowed_sections=set(response.context["allowed_sections"]),
                active_section="dashboard",
                capabilities=response.context["role_capabilities"],
            )
        return len(captured)


class StudentDashboardContentTest(DashboardContentBase):
    def test_header_uses_the_date_aware_period_and_a_localized_role(self):
        section = self.open_dashboard("student_many").context["dashboard_section"]
        self.assertTrue(section["period_label"].startswith("2026/2027"), section["period_label"])
        self.assertEqual(section["role_label"], "Tələbə")
        self.assertEqual(section["greeting"], "Salam, Aysel")
        self.assertTrue(section["today_label"])

    def test_attendance_is_per_subject_with_risky_subjects_first(self):
        card = self.widget(self.open_dashboard("student_many"), "student-attendance")
        statuses = [row["status"] for row in card["rows"]]
        self.assertEqual(statuses, ["barred", "near", "unknown", "ok", "ok"])
        barred, near = card["rows"][0], card["rows"][1]
        self.assertEqual(barred["title"], "Fənn 2")
        self.assertEqual(barred["value"], "qayıb 10 / icazə 7,5 saat")
        self.assertEqual(barred["bar"], {"value": "7.5", "max": "7.5"})
        self.assertEqual(barred["status_label"], "Limit keçib — imtahana buraxılmır")
        self.assertEqual(near["value"], "qayıb 6 / icazə 7,5 saat")
        self.assertIsNone(card["rows"][2]["bar"])  # dərs saatı yoxdur → zolaq yoxdur
        self.assertEqual(card["tone"], "danger")
        self.assertEqual(
            [(s["label"], s["value"]) for s in card["stats"][:2]], [("Limit keçib", 1), ("Limitə yaxın", 1)]
        )
        self.assertIn("25%-i", card["subtitle"])
        # Fənnin jurnalına dərin keçid — dövr + ÖZ yazılışı.
        self.assertIn("section=my-journal", barred["url"])
        self.assertIn("period=%s" % self.period.pk, barred["url"])
        self.assertIn("subject=%s" % self.enrollments[2].pk, barred["url"])

    def test_scores_card_shows_midterm_and_never_archive_components(self):
        response = self.open_dashboard("student_many")
        card = self.widget(response, "student-grades")
        by_title = {row["title"]: row for row in card["rows"]}
        self.assertEqual(by_title["Fənn 0"]["interim"], [{"label": "Midterm", "text": "15 / 20", "written": True}])
        self.assertEqual(by_title["Fənn 0"]["entry"], "25")  # davamiyyət 10 + midterm 15
        self.assertEqual(by_title["Fənn 3"]["interim"][0]["text"], "hələ yazılmayıb")
        self.assertEqual(card["stats"][1]["value"], "1 / 5")
        html = self.panel_html("student_many")
        self.assertNotIn("arxiv", html)
        self.assertIn("Midterm", html)
        self.assertIn("<progress", html)

    def test_today_card_uses_the_group_schedule(self):
        card = self.widget(self.open_dashboard("student_many"), "student-today")
        self.assertEqual(card["stats"][0]["value"], 6)  # qrupun bu günkü 6 slotu (qrup cədvəli)
        self.assertTrue(card["rows"])  # bu gün qalıbsa bu gün, qalmayıbsa növbəti dərs günü

    def test_panel_markup_is_csp_clean(self):
        html = self.panel_html("student_many")
        self.assertNotIn('style="', html)
        self.assertNotIn("<style", html)
        self.assertNotIn("<script", html)
        self.assertIn("dashboard_cards.css", html)
        self.assertIn('data-dash-widget="student-attendance"', html)

    def test_student_subjects_mirror_the_journal_summary(self):
        """Toplu güzgü ``gradebook.get_student_journal_summary`` ilə EYNİ rəqəmləri verir."""
        from apps.registrar.public import dashboard_data, gradebook

        with bypass_rls():
            mine = dashboard_data.student_subjects(organization=self.org, record=self.record, period=self.period)
            reference = gradebook.get_student_journal_summary(record=self.record, period=self.period, semester_number=1)
        expected = {row["enrollment"].id: row["journal"] for row in reference["subjects"]}
        self.assertEqual(len(mine["rows"]), len(expected))
        for row in mine["rows"]:
            journal = expected[row["enrollment_id"]]
            self.assertEqual(row["entry_score"], journal["entry_score"])
            self.assertEqual(row["absence_hours"], Decimal(journal["absence_hours"]))
            self.assertEqual(row["allowed_hours"], journal["allowed_absence"])
            self.assertEqual(row["eligibility"]["barred"], journal["barred"])

    def test_query_budget_does_not_grow_with_subjects(self):
        one, many = self.count_queries("student_one"), self.count_queries("student_many")
        self.assertEqual(one, many, "1 fənn: %s, 5 fənn: %s sorğu" % (one, many))
        self.assertLessEqual(many, STUDENT_QUERY_BUDGET)


class TeacherDashboardContentTest(DashboardContentBase):
    def test_offerings_card_has_the_real_total_and_journal_links(self):
        card = self.widget(self.open_dashboard("teacher_many"), "teacher-offerings")
        self.assertEqual(card["stats"][0]["value"], 6)
        self.assertEqual(card["total"], 6)
        self.assertEqual(len(card["rows"]), 5)
        self.assertEqual(card["more_count"], 1)
        first = card["rows"][0]
        self.assertEqual(first["value"], "keçirilib 6 / 30 saat")
        self.assertIn("DST-101", first["meta"])
        self.assertEqual(first["url"], reverse("registrar:journal_detail", args=[self.offerings[0].pk]))
        self.assertTrue(card["link"]["external"])
        self.assertEqual(card["link"]["url"], reverse("registrar:journal_list"))

    def test_midterm_window_card_shows_the_open_window(self):
        card = self.widget(self.open_dashboard("teacher_many"), "teacher-midterm")
        self.assertEqual(card["title"], "Midterm — bal yazma")
        self.assertEqual(card["stats"][0]["value"], "Açıqdır")
        deadline = (self.today + datetime.timedelta(days=10)).strftime("%d.%m.%Y")
        self.assertEqual(card["stats"][1]["value"], deadline)
        self.assertIn(deadline, card["notice"])
        self.assertEqual(card["tone"], "success")

    def test_week_count_and_today(self):
        card = self.widget(self.open_dashboard("teacher_many"), "teacher-today")
        self.assertEqual(card["stats"][0]["value"], 6)
        self.assertEqual(card["stats"][2]["value"], 6)  # həftədə hər açılışın bir «all» slotu

    def test_exam_center_widget_shows_a_single_midterm_row(self):
        card = self.widget(self.open_dashboard("exam_head"), "kollokvium-windows")
        self.assertEqual(card["title"], "Midterm pəncərəsi")
        self.assertEqual([row["title"] for row in card["rows"]], ["Midterm"])
        self.assertIn("açıqdır", card["rows"][0]["meta"])

    def test_external_journal_link_is_not_an_spa_link(self):
        html = self.panel_html("teacher_many")
        self.assertIn('href="%s" target="_blank"' % reverse("registrar:journal_list"), html)
        self.assertNotIn('data-section="my-journal"', html)

    def test_query_budget_does_not_grow_with_offerings(self):
        one, many = self.count_queries("teacher_one"), self.count_queries("teacher_many")
        self.assertEqual(one, many, "1 açılış: %s, 6 açılış: %s sorğu" % (one, many))
        self.assertLessEqual(many, TEACHER_QUERY_BUDGET)


class ApplicationsCardTest(DashboardContentBase):
    def test_card_shows_open_and_waiting_counts(self):
        from apps.applications.models import Application, ApplicationKind, ApplicationUnit
        from apps.applications.public import ApplicationStatus, seed_catalog

        with bypass_rls():
            seed_catalog(self.org)
            kind = ApplicationKind.objects.filter(organization=self.org).first()
            unit = ApplicationUnit.objects.filter(organization=self.org).first()
            for number, status in enumerate(
                (ApplicationStatus.WAITING_INFO, ApplicationStatus.SUBMITTED, ApplicationStatus.CLOSED), start=1
            ):
                Application.objects.create(
                    organization=self.org,
                    number="DST-%s" % number,
                    kind=kind,
                    subject="Arayış sorğusu",
                    body="Mətn " * 5,
                    created_by=self.users["student_many"],
                    sender_family="student",
                    status=status,
                    current_unit=unit,
                )
        card = self.widget(self.open_dashboard("student_many"), "applications")
        self.assertEqual([(s["label"], s["value"]) for s in card["stats"]], [("Açıq", 2), ("Cavabınızı gözləyən", 1)])
        self.assertEqual(card["tone"], "warning")


class PeriodAndLessonDayUnitTest(TestCase):
    """Bazasız: dövr seçimi + «növbəti dərs günü» (paritet, həftə keçidi, dövr sonu)."""

    class P:
        def __init__(self, start, end, current=False):
            self.start_date, self.end_date, self.is_current = start, end, current

    class S:
        def __init__(self, weekday, hour, week_type="all"):
            self.weekday, self.week_type = weekday, week_type
            self.start_time, self.end_time = datetime.time(hour, 0), datetime.time(hour + 1, 30)

    def test_period_containing_today_beats_a_stale_flag(self):
        from apps.registrar.public import dashboard_data

        today = datetime.date(2026, 9, 25)
        stale = self.P(datetime.date(2026, 2, 15), datetime.date(2026, 6, 30), current=True)
        autumn = self.P(datetime.date(2026, 9, 15), datetime.date(2027, 1, 31))
        self.assertIs(dashboard_data.pick_current_period([stale, autumn], today=today), autumn)
        # Tətil aralığı: yaxın GƏLƏCƏK dövr köhnəlmiş bayraqdan üstündür…
        self.assertIs(dashboard_data.pick_current_period([stale, autumn], today=datetime.date(2026, 9, 5)), autumn)
        # …gələcək dövr yoxdursa bayraq, o da yoxdursa ən son başlayan.
        summer = self.P(datetime.date(2026, 7, 1), datetime.date(2026, 8, 31))
        self.assertIs(dashboard_data.pick_current_period([stale, summer], today=datetime.date(2026, 9, 5)), stale)
        stale.is_current = False
        self.assertIs(dashboard_data.pick_current_period([stale, summer], today=datetime.date(2026, 9, 5)), summer)
        self.assertIsNone(dashboard_data.pick_current_period([], today=today))

    def test_next_lesson_day_wraps_into_next_week(self):
        """Cümə günü «növbəti» bazar ertəsidir (əvvəl «yoxdur» yazılırdı)."""
        from apps.registrar.public import dashboard_data

        friday = datetime.date(2026, 9, 25)
        period = self.P(datetime.date(2026, 9, 1), datetime.date(2026, 12, 31))
        day, slots = dashboard_data.next_lesson_day([self.S(1, 9), self.S(1, 12)], period=period, today=friday)
        self.assertEqual(day, datetime.date(2026, 9, 28))
        self.assertEqual([slot.start_time.hour for slot in slots], [9, 12])

    def test_next_lesson_day_respects_week_parity_and_period_end(self):
        from apps.registrar.public import dashboard_data

        period = self.P(datetime.date(2026, 9, 1), datetime.date(2026, 12, 31))
        friday = datetime.date(2026, 9, 25)  # 4-cü həftə (alt/even); növbəti bazar ertəsi 5-ci (üst/odd)
        self.assertEqual(dashboard_data.week_parity(period, friday), "even")
        even_monday = [self.S(1, 9, week_type="even")]
        day, _slots = dashboard_data.next_lesson_day(even_monday, period=period, today=friday)
        self.assertEqual(day, datetime.date(2026, 10, 5))  # 29.09 üst həftədir → bir həftə sonra
        short = self.P(datetime.date(2026, 9, 1), datetime.date(2026, 9, 27))
        self.assertEqual(dashboard_data.next_lesson_day(even_monday, period=short, today=friday), (None, []))
        self.assertEqual(dashboard_data.lessons_on([self.S(5, 9)], datetime.date(2027, 1, 8), period=period), [])

    def test_lesson_card_shows_the_next_day_once_today_is_over(self):
        from apps.accounts.views.profile._sections import dashboard_lessons

        class Offering:
            subject = type("Subj", (), {"name": "Riyaziyyat"})()
            group = None

        class Slot(self.S):
            offering = Offering()
            room = "305"

            def get_kind_display(self):
                return "Mühazirə"

        period = self.P(datetime.date(2026, 9, 1), datetime.date(2026, 12, 31))
        friday = datetime.date(2026, 9, 25)
        slots = [Slot(5, 9), Slot(1, 11)]
        morning = dashboard_lessons.build(
            slots, period=period, today=friday, now=datetime.time(9, 15), with_group=False
        )
        self.assertTrue(morning["caption"].startswith("Bu gün"))
        self.assertTrue(morning["rows"][0]["is_now"])
        self.assertEqual(morning["stats"][1]["note"], "indi gedir")
        evening = dashboard_lessons.build(
            slots, period=period, today=friday, now=datetime.time(19, 0), with_group=False
        )
        self.assertTrue(evening["caption"].startswith("Növbəti dərs günü"))
        self.assertEqual(evening["rows"][0]["time"], "11:00–12:30")
        self.assertEqual(evening["stats"][0]["value"], 1)  # bu günün dərsi sayılır, siyahı isə bazar ertəsidir
        self.assertIn("Mühazirə · aud. 305", evening["rows"][0]["meta"])
