"""«Yeni dərs» modalı — sahibin 2026-11-15 dörd istəyi (müəllim kimi, HTTP üzərindən reproduksiya).

1. SAAT: yalnız 1, 2 və «Passiv · 1/2» — 3 / 4 yeni dərsdə yoxdur; köhnə 3–4 saatlıq dərsin saatı dəyişmədən
   redaktəsi xətasızdır; cədvəl slotu 3–4 saat versə də doldurma / aktivləşdirmə 2 saat yazır.
2. DƏRS TİPİ: kilid yoxdur — cədvəldə yalnız mühazirə olsa da müəllim seminar / laboratoriya açır və redaktədə
   dəyişir (MR-000017/018/054, MR-000218: patokun partnyor qrupunda cədvəldə yalnız seminar var idi).
3. KEÇMİŞ TARİX: prod tənzimləmələri ilə (``backdate_since`` yandırılı, ``late_entry_days`` = 14) müəllim — superuser
   deyil, «Data bərpası» söndürülü və yandırılı — 30 gün əvvəlki tarixə dərs açır və xanaya yazır (MR-000206/087);
   modalın tarix seçicisinin ``min``-i başlanğıc tarixidir; yeni sütun «son 20 dərs» pəncərəsindən kənarda qalanda
   jurnal həmin pəncərədə və sütunda açılır; eyni saatda köçürülmüş dərs varsa (MR-000125) jurnal o sütunda açılır.
4. PATOK: eyni müəllim, eyni gün/saat, ayrı jurnallar — hər qrupa dərs + xana; bir jurnalda eyni saatda iki slot
   (MR-000334 / 356: «08:30-un yerinə 13:35 slotu doldurulur») — birinci dərs ikinci slotu «açılıb» saymır.
"""

from __future__ import annotations

import datetime as dt
import re

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.organizations.models import Membership, OrgUnit
from apps.registrar import journal_activation, journal_lesson_prefill, services
from apps.registrar.lesson_share_scope import match_slots
from apps.registrar.models import CourseOffering, Enrollment, Lesson, LessonKind, LessonMark, ScheduleSlot
from apps.registrar.tests.test_journal_rules import _setup_offering
from core.constants import OrgUnitType
from core.rls import bypass_rls

User = get_user_model()
TIME = "08:30|10:00"
RANGE_ERROR = "Dərs saatı 1 ilə 2 arasında olmalıdır."


def _prod_settings(**extra):
    """Prod «Sistem tənzimləmələri» (2026-11-15 oxunub): backdate yandırılı, gecikmiş yazı 14 gün, aktivləşdirmə və
    «cədvəldən kənar» söndürülü. Başlanğıc tarixi testin gününə nisbətən — 60 gün əvvəl (prod: 15.09.2026)."""
    since = timezone.localdate() - dt.timedelta(days=60)
    values = {
        "JOURNAL_BACKDATE_SINCE_ENABLED": True,
        "JOURNAL_BACKDATE_SINCE": since.isoformat(),
        "JOURNAL_LATE_ENTRY_DAYS": 14,
        "JOURNAL_LESSON_ACTIVATION": False,
    }
    values.update(extra)
    return override_settings(**values)


class _Base(TestCase):
    prefix = "lmb"

    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            _setup_offering(cls, cls.prefix)
            # Dövr testin gününü əhatə etsin (keçmiş tarix semestr başlanğıcından əvvələ düşməsin).
            today = timezone.localdate()
            type(cls.period).objects.filter(pk=cls.period.pk).update(
                start_date=today - dt.timedelta(days=90), end_date=today + dt.timedelta(days=60)
            )

    def client_for(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def url(self, offering=None):
        return reverse("registrar:journal_detail", args=[(offering or self.offering).id])

    def add(self, offering=None, *, day=None, kind="lecture", hours="2", time=TIME, follow=True, **extra):
        data = {
            "action": "add_lesson",
            "lesson_date": (day or timezone.localdate()).isoformat(),
            "lesson_kind": kind,
            "lesson_hours": hours,
            "lesson_time": time,
        }
        data.update(extra)
        return self.client_for(self.teacher).post(self.url(offering), data, follow=follow)

    def autosave(self, lesson, enrollment, status="absent", offering=None):
        return self.client_for(self.teacher).post(
            self.url(offering), {f"att__{lesson.pk}__{enrollment.pk}": status, "autosave": "1"}
        )

    def lessons(self, offering=None, **filters):
        with bypass_rls():
            return list(Lesson.objects.filter(offering=offering or self.offering, **filters).order_by("date"))

    def lesson(self, *, day=None, hours=2, kind="lecture", start="08:30", end="10:00"):
        with bypass_rls():
            return Lesson.objects.create(
                organization=self.org,
                offering=self.offering,
                date=day or timezone.localdate(),
                kind=kind,
                hours=hours,
                start_time=dt.time.fromisoformat(start),
                end_time=dt.time.fromisoformat(end),
                instructor=self.teacher,
                created_by=self.teacher,
            )

    def slot(self, offering=None, *, start=(8, 30), end=(10, 0), kind="lecture"):
        with bypass_rls():
            return ScheduleSlot.objects.create(
                organization=self.org,
                offering=offering or self.offering,
                weekday=timezone.localdate().isoweekday(),
                start_time=dt.time(*start),
                end_time=dt.time(*end),
                kind=kind,
            )

    def prefill(self, clock):
        with bypass_rls():
            offering = CourseOffering.objects.select_related("period", "organization", "subject").get(
                pk=self.offering.pk
            )
            now = timezone.make_aware(dt.datetime.combine(timezone.localdate(), clock))
            return journal_lesson_prefill.build(offering, {"can_edit": True}, now=now)

    @staticmethod
    def messages(response):
        return [str(message) for message in response.context["messages"]] if response.context else []


# ── 1. SAAT ──────────────────────────────────────────────────────────────────


class HoursChoiceTest(_Base):
    prefix = "lmh"

    def test_modal_shows_only_one_two_and_passive_one_two(self):
        html = self.client_for(self.teacher).get(self.url()).content.decode()
        select = re.search(r'<select name="lesson_hours".*?</select>', html, re.S).group(0)
        options = re.findall(r"<option [^>]*>", select)
        visible = [re.search(r'value="([^"]+)"', opt).group(1) for opt in options if " hidden" not in opt]
        legacy = [re.search(r'value="([^"]+)"', opt).group(1) for opt in options if "data-jd-hours-legacy" in opt]
        self.assertEqual(visible, ["1", "2", "p1", "p2"])
        self.assertEqual(legacy, ["3", "4", "p3", "p4"])  # gizli — yalnız köhnə dərsin redaktəsi üçün (JS)
        self.assertIn("registrar/js/journal_lesson_hours.js", html)

    def test_new_lesson_accepts_one_and_two_refuses_three_and_four(self):
        for hours in ("3", "4", "p3", "p4"):
            with self.subTest(hours=hours):
                self.assertIn(RANGE_ERROR, self.messages(self.add(hours=hours)))
        self.assertEqual(self.lessons(), [])
        self.add(hours="1")
        self.add(hours="p2", time="10:10|11:40")
        self.assertEqual(sorted((x.hours, x.is_passive) for x in self.lessons()), [(1, False), (2, True)])

    def test_editing_an_old_four_hour_lesson_without_changing_hours_works(self):
        old = self.lesson(hours=4, end="11:40")
        url = reverse("registrar:journal_lesson_action", args=[self.offering.id, old.id])
        data = {
            "action": "update_lesson",
            "lesson_date": old.date.isoformat(),
            "lesson_kind": "lecture",
            "lesson_hours": "4",
            "lesson_time": "08:30|11:40",
            "lesson_topic": "Yeni mövzu",
        }
        resp = self.client_for(self.teacher).post(url, data, follow=True)
        self.assertIn("Dərs yeniləndi.", self.messages(resp))
        old.refresh_from_db()
        self.assertEqual((old.hours, old.topic), (4, "Yeni mövzu"))
        # Saatı başqa 3/4-ə dəyişmək olmaz (yalnız 1..2).
        resp = self.client_for(self.teacher).post(url, {**data, "lesson_hours": "3"}, follow=True)
        self.assertIn(RANGE_ERROR, self.messages(resp))
        old.refresh_from_db()
        self.assertEqual(old.hours, 4)

    def test_long_timetable_slot_prefills_and_activates_two_hours(self):
        slot = self.slot(end=(11, 40))  # 190 dəqiqə → slot_hours 4
        self.assertEqual(journal_activation.slot_hours(slot), 4)
        self.assertEqual(journal_activation.lesson_hours_for_slot(slot), 2)
        data = self.prefill(dt.time(9, 0))
        self.assertEqual((data["slot_id"], data["hours"]), (str(slot.pk), 2))
        with _prod_settings(JOURNAL_LESSON_ACTIVATION=True):
            self.client_for(self.teacher).post(
                reverse("registrar:journal_activate_slot", args=[self.offering.id, slot.pk])
            )
        self.assertEqual([x.hours for x in self.lessons()], [2])


# ── 2. DƏRS TİPİ ─────────────────────────────────────────────────────────────


class KindUnlockedTest(_Base):
    prefix = "lmk"

    def setUp(self):
        self.slot(kind="lecture")  # cədvəldə YALNIZ mühazirə — əvvəl tip «Mühazirə 🔒» idi

    def test_modal_has_an_open_select_with_the_timetable_kind_preselected(self):
        html = self.client_for(self.teacher).get(self.url()).content.decode()
        self.assertNotIn("data-jd-lesson-kind-locked", html)
        self.assertNotIn('<input type="hidden" name="lesson_kind"', html)
        select = re.search(r'<select name="lesson_kind".*?</select>', html, re.S).group(0)
        self.assertRegex(select, r'<option value="lecture" selected>')
        self.assertIn('value="seminar"', select)
        self.assertIn('value="lab"', select)

    def test_teacher_adds_seminar_and_lab_although_timetable_has_only_lecture(self):
        with _prod_settings():
            self.add(kind="seminar", time="10:10|11:40")
            self.add(kind="lab", time="11:50|13:20")
            self.add(kind="seminar", day=timezone.localdate() - dt.timedelta(days=20))  # MR-000018: keçmiş seminar
        self.assertEqual(sorted(x.kind for x in self.lessons()), ["lab", "seminar", "seminar"])

    def test_teacher_changes_kind_while_editing(self):
        self.add()
        (lesson,) = self.lessons()
        url = reverse("registrar:journal_lesson_action", args=[self.offering.id, lesson.id])
        data = {
            "action": "update_lesson",
            "lesson_date": lesson.date.isoformat(),
            "lesson_kind": "seminar",
            "lesson_hours": "2",
            "lesson_time": TIME,
        }
        resp = self.client_for(self.teacher).post(url, data, follow=True)
        self.assertIn("Dərs yeniləndi.", self.messages(resp))
        lesson.refresh_from_db()
        self.assertEqual(lesson.kind, LessonKind.SEMINAR)

    def test_unknown_kind_is_still_refused(self):
        self.assertIn("Dərs tipi düzgün seçilməyib.", self.messages(self.add(kind="exam")))
        self.assertEqual(self.lessons(), [])


# ── 3. KEÇMİŞ TARİX ──────────────────────────────────────────────────────────


class BackdateAsTeacherTest(_Base):
    prefix = "lmd"

    @staticmethod
    def old_day():
        return timezone.localdate() - dt.timedelta(days=30)

    def _write_thirty_days_back(self):
        page = self.client_for(self.teacher).get(self.url())
        self.assertEqual(page.status_code, 200)
        self.assertIn("Dərs əlavə edildi.", self.messages(self.add(day=self.old_day())))
        (lesson,) = self.lessons(date=self.old_day())
        saved = self.autosave(lesson, self.enrollment)
        self.assertEqual((saved.status_code, saved.json()["written"]), (200, 1))
        with bypass_rls():
            self.assertEqual(LessonMark.objects.get(lesson=lesson).status, "absent")
        return page

    def test_teacher_without_data_recovery_writes_thirty_days_back(self):
        self.assertFalse(self.teacher.is_superuser)
        with _prod_settings(JOURNAL_TEACHER_FULL_EDIT=False):
            page = self._write_thirty_days_back()
        since = (timezone.localdate() - dt.timedelta(days=60)).isoformat()
        self.assertContains(page, f'data-ems-dt-min="{since}"')
        self.assertContains(page, f'data-ems-dt-max="{timezone.localdate().isoformat()}"')

    def test_teacher_with_data_recovery_on_writes_without_a_reason(self):
        with _prod_settings(JOURNAL_TEACHER_FULL_EDIT=True):
            self._write_thirty_days_back()

    def test_old_lesson_outside_the_twenty_column_window_is_shown_after_adding(self):
        today = timezone.localdate()
        for days in range(21):  # yeni dərslər — «son 20 dərs» pəncərəsini doldurur
            self.lesson(day=today - dt.timedelta(days=days))
        with _prod_settings():
            resp = self.add(day=self.old_day(), follow=False)
        (lesson,) = self.lessons(date=self.old_day())
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp["Location"].endswith(f"?lo=21#jd-lesson-{lesson.pk}"), resp["Location"])
        page = self.client_for(self.teacher).get(self.url(), {"lo": 21})
        self.assertContains(page, f'id="jd-lesson-{lesson.pk}"')
        self.assertNotContains(self.client_for(self.teacher).get(self.url()), f'id="jd-lesson-{lesson.pk}"')

    def test_same_slot_lesson_opens_the_existing_column(self):
        # MR-000125: köçürülmüş dərs həmin gün + saatda artıq var — «əlavə edə bilmirəm» yox, sütuna keçid.
        existing = self.lesson(day=self.old_day())
        with _prod_settings():
            resp = self.add(day=self.old_day(), follow=False)
        self.assertTrue(resp["Location"].endswith(f"#jd-lesson-{existing.pk}"), resp["Location"])
        self.assertEqual(len(self.lessons(date=self.old_day())), 1)

    def test_future_and_before_since_are_still_refused(self):
        with _prod_settings():
            future = self.add(day=timezone.localdate() + dt.timedelta(days=1))
            older = self.add(day=timezone.localdate() - dt.timedelta(days=61))
        self.assertIn("Gələcək tarixə dərs əlavə etmək olmaz.", self.messages(future))
        self.assertTrue(any("tarixindən əvvəl ola bilməz" in m for m in self.messages(older)), self.messages(older))
        self.assertEqual(self.lessons(), [])


# ── 4. PATOK ─────────────────────────────────────────────────────────────────


class PatokSameTimeTest(_Base):
    """Eyni müəllim, eyni fənn, eyni saat — iki qrupun AYRI jurnalı (MR-000218: B-nin cədvəlində yalnız seminar)."""

    prefix = "lmp"

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        with bypass_rls():
            cls.group_b = OrgUnit.objects.create(
                organization=cls.org,
                name="JR-102",
                slug="lmp-jr102",
                unit_type=OrgUnitType.GROUP,
                parent=cls.group.parent,
            )
            cls.offering_b = services.get_or_create_offering(
                organization=cls.org, subject=cls.subject, period=cls.period, group=cls.group_b
            )
            cls.offering_b.instructor = cls.teacher
            cls.offering_b.lesson_hours = 60
            cls.offering_b.save(update_fields=["instructor", "lesson_hours"])
            student = User.objects.create_user("lmp_sb", "lmp_sb@qku.edu.az", "pw")
            Membership.objects.create(
                user=student,
                organization=cls.org,
                role=cls.org.roles.get(name="student"),
                is_primary=True,
                is_active=True,
            )
            cls.enrollment_b = Enrollment.objects.create(organization=cls.org, student=student, offering=cls.offering_b)

    def setUp(self):
        self.slot(self.offering, kind="lecture")
        self.slot(self.offering_b, kind="seminar")

    def _pairs(self):
        return ((self.offering, self.enrollment), (self.offering_b, self.enrollment_b))

    def test_teacher_opens_and_marks_the_same_time_lecture_in_every_group(self):
        with _prod_settings():
            for offering, enrollment in self._pairs():
                self.assertIn("Dərs əlavə edildi.", self.messages(self.add(offering)))
                (lesson,) = self.lessons(offering)
                self.assertEqual((lesson.kind, lesson.start_time), (LessonKind.LECTURE, dt.time(8, 30)))
                self.assertEqual(self.autosave(lesson, enrollment, offering=offering).json()["written"], 1)

    def test_same_time_patok_thirty_days_back(self):
        day = timezone.localdate() - dt.timedelta(days=30)
        with _prod_settings():
            for offering, enrollment in self._pairs():
                self.add(offering, day=day)
                (lesson,) = self.lessons(offering, date=day)
                self.assertEqual(self.autosave(lesson, enrollment, offering=offering).json()["written"], 1)

    def test_activation_opens_both_groups_at_the_same_time(self):
        with _prod_settings(JOURNAL_LESSON_ACTIVATION=True):
            for offering, _enrollment in self._pairs():
                with bypass_rls():
                    slot = ScheduleSlot.objects.get(offering=offering)
                self.client_for(self.teacher).post(
                    reverse("registrar:journal_activate_slot", args=[offering.id, slot.pk])
                )
                self.assertEqual(len(self.lessons(offering)), 1)


class SameJournalTwoSlotsTest(_Base):
    """MR-000334 / 356: bir jurnalda eyni saatda iki slot — birinci dərs açılandan sonra modal 13:35 slotunu yox,
    ikinci 08:30 slotunu doldurur; zolaq / «Aktivləşdir» ikincini «açılıb» saymır."""

    prefix = "lms"

    def test_second_same_time_slot_stays_open(self):
        lecture = self.slot(kind="lecture")
        lab = self.slot(kind="lab")
        self.slot(start=(13, 35), end=(15, 5), kind="lecture")
        self.lesson(kind="lecture")  # 08:30 mühazirəsi açılıb
        data = self.prefill(dt.time(9, 0))
        self.assertEqual((data["slot_id"], data["time"]), (str(lab.pk), TIME))  # əvvəl: 13:35 slotu
        self.assertNotIn(str(lecture.pk), data["slots"])

    def test_match_slots_pairs_one_lesson_with_one_slot(self):
        first, second = self.slot(kind="lab"), self.slot(kind="lab")
        lab = self.lesson(kind="lab")
        self.assertEqual(match_slots([first, second], [lab]), {first.pk: lab})
        # Növü dəyişdirilmiş dərs də (eyni saat) öz slotunu bağlayır; başqa saatın dərsi bağlamır.
        seminar = self.lesson(kind="seminar")
        later = self.lesson(kind="lab", start="13:35", end="15:05")
        self.assertEqual(match_slots([first, second], [lab, seminar, later]), {first.pk: lab, second.pk: seminar})
