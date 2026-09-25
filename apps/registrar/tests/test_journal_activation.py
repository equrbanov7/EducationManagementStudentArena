"""«Dərsi aktivləşdir» (UNEC müqayisəsi P1-1, 2026-09-25): bu günün cədvəl zolağı, slotdan dərs,
cədvəldən kənar dərsin səbəbi — bütün mövcud jurnal qaydaları (bu gün, saat həddi, sillabus qapısı,
dublikat, kilid) slot yolunda da qüvvədədir."""

import datetime

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.exams.models import ExamRoom
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import gradebook, journal_activation, schedule, services
from apps.registrar.models import Enrollment, Lesson, LessonKind, ScheduleSlot, SlotKind, Subject, WeekType
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


def _other(parity):
    return WeekType.EVEN if parity == WeekType.ODD else WeekType.ODD


class JournalActivationTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.today = timezone.localdate()
        monday = cls.today - datetime.timedelta(days=cls.today.weekday())
        cls.owner = User.objects.create_user("ja_owner", "ja_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="JA Univ",
                slug="ja-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org, name="G1", slug="ja-g1", unit_type=OrgUnitType.GROUP
            )
            cls.period = AcademicPeriod.objects.create(
                organization=cls.org,
                name="Cari semestr",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2026/2027",
                start_date=monday - datetime.timedelta(days=14),
                end_date=cls.today + datetime.timedelta(days=90),
                is_current=True,
            )
            cls.parity = schedule.week_parity(cls.period, monday)
            cls.subject = Subject.objects.create(organization=cls.org, code="JA101", name="Verilənlər bazası")
            cls.other_subject = Subject.objects.create(organization=cls.org, code="JA102", name="Şəbəkələr")
            cls.teacher = User.objects.create_user(
                "ja_teacher", "ja_teacher@qku.edu.az", "pw", first_name="Leyla", last_name="Quliyeva"
            )
            cls.other_teacher = User.objects.create_user("ja_other", "ja_other@qku.edu.az", "pw")
            cls.student = User.objects.create_user("ja_student", "ja_student@qku.edu.az", "pw")
            for user in (cls.teacher, cls.other_teacher):
                Membership.objects.create(
                    user=user,
                    organization=cls.org,
                    role=cls.org.roles.get(name="teacher"),
                    is_primary=True,
                    is_active=True,
                )
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
            cls.offering.lesson_hours = 60
            cls.offering.save(update_fields=["instructor", "lesson_hours"])
            cls.plain = services.get_or_create_offering(
                organization=cls.org, subject=cls.other_subject, period=cls.period, group=cls.group
            )
            cls.plain.instructor = cls.teacher
            cls.plain.save(update_fields=["instructor"])
            Enrollment.objects.create(organization=cls.org, student=cls.student, offering=cls.offering)
            Enrollment.objects.create(organization=cls.org, student=cls.student, offering=cls.plain)
            cls.room = ExamRoom.objects.create(organization=cls.org, name="305", code="A305", building="A", capacity=30)
            weekday = cls.today.isoweekday()

            def slot(**kwargs):
                data = {"organization": cls.org, "offering": cls.offering, "weekday": weekday, "room": ""}
                data.update(kwargs)
                return ScheduleSlot.objects.create(**data)

            cls.seminar = slot(
                start_time=datetime.time(10, 10),
                end_time=datetime.time(11, 40),
                kind=SlotKind.SEMINAR,
                room="305",
                week_type=cls.parity,
            )
            cls.lecture = slot(start_time=datetime.time(8, 30), end_time=datetime.time(10, 0), kind=SlotKind.LECTURE)
            # Bu gün keçirilməyən slotlar — zolağa DÜŞMƏMƏLİDİR:
            cls.wrong_parity = slot(
                start_time=datetime.time(11, 50),
                end_time=datetime.time(13, 20),
                kind=SlotKind.LAB,
                week_type=_other(cls.parity),
            )
            cls.parked = slot(start_time=datetime.time(13, 35), end_time=datetime.time(15, 5), is_parked=True)
            cls.other_day = slot(
                weekday=weekday % 7 + 1, start_time=datetime.time(15, 15), end_time=datetime.time(16, 45)
            )

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _activate(self, user, slot):
        url = reverse("registrar:journal_activate_slot", args=[self.offering.id, slot.id])
        return self._client(user).post(url)

    def _journal(self, user, offering=None):
        return self._client(user).get(reverse("registrar:journal_detail", args=[(offering or self.offering).id]))

    def _lessons(self, offering=None):
        with bypass_rls():
            return list(Lesson.objects.filter(offering=offering or self.offering).order_by("start_time"))

    # ── Zolaq ────────────────────────────────────────────────────────────────

    def test_strip_lists_only_todays_slots(self):
        resp = self._journal(self.teacher)
        self.assertEqual(resp.status_code, 200)
        strip = resp.context["today_strip"]
        self.assertEqual([item["slot_id"] for item in strip["items"]], [str(self.lecture.id), str(self.seminar.id)])
        seminar = strip["items"][1]
        self.assertEqual(seminar["room"], "305")
        self.assertEqual(seminar["teacher"], "Leyla Quliyeva")
        self.assertEqual(seminar["lesson_id"], "")
        self.assertTrue(strip["can_activate"])
        self.assertContains(resp, reverse("registrar:journal_activate_slot", args=[self.offering.id, self.seminar.id]))
        self.assertContains(resp, "data-jd-activate-form")
        self.assertContains(resp, "registrar/js/journal_activation.js")

    def test_strip_is_hidden_without_timetable_and_on_other_tabs(self):
        self.assertNotIn("today_strip", self._journal(self.teacher, self.plain).context)
        other_tab = self._client(self.teacher).get(
            reverse("registrar:journal_detail", args=[self.offering.id]), {"jt": "yekun"}
        )
        self.assertNotIn("today_strip", other_tab.context)

    def test_locked_journal_strip_is_read_only(self):
        with bypass_rls():
            gradebook.ensure_assessment_scheme(offering=self.offering)
            from apps.registrar.models import ApprovalStatus, AssessmentScheme

            AssessmentScheme.objects.filter(offering=self.offering).update(
                is_published=True, approval_status=ApprovalStatus.APPROVED
            )
        page = self._journal(self.teacher)
        self.assertFalse(page.context["today_strip"]["can_activate"])
        self.assertNotContains(page, "data-jd-activate-form")
        self.assertContains(page, "Aktivləşdirilməyib")

    # ── «Aktivləşdir» ────────────────────────────────────────────────────────

    def test_activation_copies_time_kind_room_and_teacher(self):
        resp = self._activate(self.teacher, self.seminar)
        self.assertEqual(resp.status_code, 302)
        (lesson,) = self._lessons()
        self.assertEqual(lesson.date, self.today)
        self.assertEqual(lesson.kind, LessonKind.SEMINAR)
        self.assertEqual((lesson.start_time, lesson.end_time), (datetime.time(10, 10), datetime.time(11, 40)))
        self.assertEqual(lesson.hours, 2)
        self.assertEqual(lesson.room_id, self.room.id)
        self.assertEqual(lesson.instructor_id, self.teacher.id)
        self.assertEqual(lesson.off_schedule_reason, "")
        self.assertTrue(resp["Location"].endswith(f"#jd-lesson-{lesson.id}"))

    def test_second_activation_does_not_duplicate_and_strip_links_the_column(self):
        self._activate(self.teacher, self.seminar)
        resp = self._activate(self.teacher, self.seminar)
        self.assertEqual(resp.status_code, 302)
        (lesson,) = self._lessons()
        self.assertTrue(resp["Location"].endswith(f"#jd-lesson-{lesson.id}"))
        page = self._journal(self.teacher)
        seminar = page.context["today_strip"]["items"][1]
        self.assertEqual(seminar["lesson_id"], str(lesson.id))
        self.assertEqual(seminar["state"], "done")
        self.assertContains(page, f'id="jd-lesson-{lesson.id}"')
        self.assertContains(page, f"#jd-lesson-{lesson.id}")

    def test_slot_not_held_today_is_refused(self):
        for slot in (self.other_day, self.wrong_parity):
            self._activate(self.teacher, slot)
        self.assertEqual(self._lessons(), [])

    def test_parked_slot_and_foreign_actors_get_404(self):
        self.assertEqual(self._activate(self.teacher, self.parked).status_code, 404)
        self.assertEqual(self._activate(self.other_teacher, self.seminar).status_code, 404)
        self.assertEqual(self._activate(self.student, self.seminar).status_code, 404)
        self.assertEqual(
            self._client(self.teacher)
            .get(reverse("registrar:journal_activate_slot", args=[self.offering.id, self.seminar.id]))
            .status_code,
            405,
        )
        self.assertEqual(self._lessons(), [])

    def test_hours_cap_still_applies(self):
        with bypass_rls():
            self.offering.lesson_hours = 2
            self.offering.save(update_fields=["lesson_hours"])
            gradebook.create_lesson(
                offering=self.offering,
                date=self.today,
                kind=LessonKind.LECTURE,
                start_time=datetime.time(18, 40),
                end_time=datetime.time(20, 0),
            )
        resp = self._client(self.teacher).post(
            reverse("registrar:journal_activate_slot", args=[self.offering.id, self.seminar.id]), follow=True
        )
        self.assertContains(resp, "dərs saatı həddi")
        self.assertEqual(len(self._lessons()), 1)

    def test_syllabus_gate_still_applies(self):
        with bypass_rls():
            self.org.settings = {"journal": {"require_approved_syllabus": True}}
            self.org.save(update_fields=["settings"])
        resp = self._activate(self.teacher, self.seminar)
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.content.decode(), "no_approved_syllabus")
        self.assertEqual(self._lessons(), [])

    def test_published_journal_refuses_activation(self):
        with bypass_rls():
            gradebook.ensure_assessment_scheme(offering=self.offering)
            from apps.registrar.models import ApprovalStatus, AssessmentScheme

            AssessmentScheme.objects.filter(offering=self.offering).update(
                is_published=True, approval_status=ApprovalStatus.APPROVED
            )
        self._activate(self.teacher, self.seminar)
        self.assertEqual(self._lessons(), [])

    def test_service_slot_path_validates_the_date(self):
        with bypass_rls():
            with self.assertRaises(gradebook.LessonRuleError):
                gradebook.create_lesson(offering=self.offering, date=self.today, slot=self.other_day)
            with self.assertRaises(gradebook.LessonRuleError):
                gradebook.create_lesson(offering=self.plain, date=self.today, slot=self.seminar)

    # ── «+ Yeni dərs»: cədvəldən kənar dərsin səbəbi ────────────────────────

    def _add(self, offering, time, reason=None):
        payload = {
            "action": "add_lesson",
            "lesson_date": self.today.isoformat(),
            "lesson_kind": "lecture",
            "lesson_hours": "2",
            "lesson_time": time,
        }
        if reason is not None:
            payload["off_schedule_reason"] = reason
        return self._client(self.teacher).post(
            reverse("registrar:journal_detail", args=[offering.id]), payload, follow=True
        )

    def test_off_schedule_lesson_requires_a_reason(self):
        resp = self._add(self.offering, "13:35|15:05", reason="  ")
        self.assertContains(resp, "cədvəldən kənar dərs üçün səbəbi yazın")
        self.assertEqual(self._lessons(), [])
        self._add(self.offering, "13:35|15:05", reason="Əvəzetmə — xəstə müəllimin yerinə")
        (lesson,) = self._lessons()
        self.assertEqual(lesson.off_schedule_reason, "Əvəzetmə — xəstə müəllimin yerinə")
        with bypass_rls():
            log = AuditLog.objects.filter(resource_type="registrar.grade.mark", resource_id=str(self.offering.id)).get()
        self.assertIn("cədvəldən kənar dərs açıldı", log.changes[0]["new"])

    def test_lesson_matching_a_slot_needs_no_reason(self):
        self._add(self.offering, "08:30|10:00", reason="səhvən yazılmış səbəb")
        (lesson,) = self._lessons()
        self.assertEqual(lesson.off_schedule_reason, "")

    def test_offering_without_timetable_is_unchanged(self):
        self._add(self.plain, "13:35|15:05")
        (lesson,) = self._lessons(self.plain)
        self.assertEqual(lesson.off_schedule_reason, "")

    def test_modal_gets_the_slot_pattern(self):
        resp = self._journal(self.teacher)
        self.assertContains(resp, 'id="jdSlotPattern"')
        self.assertContains(resp, "data-jd-offsched")
        pattern = resp.context["lesson_slot_pattern"]
        self.assertIn({"weekday": self.today.isoweekday(), "week_type": WeekType.ALL, "start": "08:30"}, pattern)
        self.assertNotIn("13:35", [item["start"] for item in pattern])  # parklanmış slot

    # ── Köməkçilər ───────────────────────────────────────────────────────────

    def test_next_topic_follows_the_plan_per_kind(self):
        rows = [
            {"title": "Giriş", "kinds": ["lecture", "seminar"]},
            {"title": "SQL", "kinds": ["lecture", "seminar"]},
            {"title": "Normallaşdırma", "kinds": ["lecture"]},
        ]
        covered = {"Giriş": {"lecture"}}
        self.assertEqual(journal_activation.next_topic(rows, covered, "lecture"), "SQL")
        self.assertEqual(journal_activation.next_topic(rows, covered, "seminar"), "Giriş")
        self.assertEqual(journal_activation.next_topic(rows, covered, "lab"), "")
        # Növsüz mənbə (LMS kursu): hər hansı növdə keçilmiş mövzu «keçilib».
        loose = [{"title": "Giriş", "kinds": []}, {"title": "SQL", "kinds": []}]
        self.assertEqual(journal_activation.next_topic(loose, covered, "seminar"), "SQL")

    def test_slot_hours_from_duration(self):
        def hours(start, end):
            return journal_activation.slot_hours(ScheduleSlot(start_time=start, end_time=end))

        self.assertEqual(hours(datetime.time(8, 30), datetime.time(10, 0)), 2)
        self.assertEqual(hours(datetime.time(18, 40), datetime.time(20, 0)), 2)
        self.assertEqual(hours(datetime.time(9, 0), datetime.time(9, 45)), 1)
        self.assertEqual(hours(datetime.time(9, 0), datetime.time(8, 0)), gradebook.DEFAULT_LESSON_HOURS)

    # ── Ana səhifə: «Jurnalı aç» ─────────────────────────────────────────────

    def test_teacher_dashboard_rows_link_to_the_journal(self):
        from apps.accounts.views.profile._sections import dashboard_lessons

        with bypass_rls():
            slots = schedule.get_teacher_schedule(organization=self.org, teacher=self.teacher, period=self.period)
        teacher_card = dashboard_lessons.build(
            slots, period=self.period, today=self.today, now=None, with_group=True, journal_links=True
        )
        url = reverse("registrar:journal_detail", args=[self.offering.id])
        self.assertTrue(teacher_card["rows"])
        self.assertTrue(all(row["url"] == url for row in teacher_card["rows"]))
        # Tələbə kartı (və keçid istənməyəndə) sətirlərdə keçid yoxdur.
        student_card = dashboard_lessons.build(slots, period=self.period, today=self.today, now=None, with_group=False)
        self.assertTrue(all("url" not in row for row in student_card["rows"]))

    def test_every_tab_renders_with_a_timetable(self):
        client = self._client(self.teacher)
        url = reverse("registrar:journal_detail", args=[self.offering.id])
        for tab in ("grid", "kollokvium", "kurs-isi", "serbest", "yekun"):
            resp = client.get(url, {"jt": tab})
            self.assertEqual(resp.status_code, 200, tab)
            self.assertContains(resp, "data-jhist-open", msg_prefix=tab)  # tarixçə düyməsi hər tabda
            self.assertContains(resp, 'id="jdSlotPattern"', msg_prefix=tab)  # «+ Yeni dərs» modalı hər tabda
