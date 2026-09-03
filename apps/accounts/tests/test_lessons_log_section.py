"""Ekran 21 «Keçilmiş dərslər» + README §8/2 jurnal siyasəti.

Nəyi qoruyur
------------
1. **Rol qapısı.** Müəllim bölməni GÖRÜR və fraqmenti 200 alır; TƏLƏBƏ 403 alır
   (menyuda da yoxdur). Nəzarətçi (`journal.roster`) ayrıca açardan girir.
2. **Əhatə (README §8/8).** Müəllim YALNIZ öz dərslərini görür — başqa
   müəllimin dərsi sətirlərdə YOXDUR; `teacher` filtri ona təsir etmir və CSV
   ixracında **403** verir.
3. **Qeyd statusu.** `on_time` / `late` (48 saat) / `empty` düzgün hesablanır.
4. **Sillabus əhatəsi.** Yalnız APPROVED versiyanın mövzuları planlaşdırılmış
   sayılır; keçilən mövzular faizi verir.
5. **Siyasət açarı `journal.require_approved_syllabus`** — HƏR İKİ rejim:
   SÖNDÜRÜLÜ (default) → dərs açılır; AÇIQ + təsdiqlənmiş sillabus yox →
   servis `SyllabusGateError`, jurnal POST-u **403 + səbəb kodu**, görünüş
   read-only.
6. **Sorğu büdcəsi.** Bölmə fraqmenti sabit sayda sorğu ilə qurulur (N+1 yox).
"""

from __future__ import annotations

import datetime as dt

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.organizations.models import Organization, OrgUnit
from apps.registrar import gradebook, journal_policy
from apps.registrar import lessons_log as service
from apps.registrar.models import (
    AttendanceStatus,
    CourseOffering,
    Enrollment,
    Lesson,
    LessonKind,
    LessonMark,
    Subject,
)
from apps.syllabus.tests.factories import activate_member, make_academic_stack, make_offering, make_org
from core.constants import OrgUnitType, RoleScopeType
from core.rls import bypass_rls

User = get_user_model()

PASSWORD = "StrongPass123!"
SECTION = "lessons-log"

TEACHER_PERMS = ["course.view", "grade.input", "syllabus.edit"]
CHAIR_PERMS = ["course.view", "journal.roster", "unit.view"]


@override_settings(UNIVERSITY_MODE=True)
class LessonsLogSectionTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("llog-univ")
        cls.stack = make_academic_stack(cls.org, code="LLG101")
        cls.teacher = User.objects.create_user("llog_teacher", "llog_teacher@qku.edu.az", PASSWORD)
        cls.other_teacher = User.objects.create_user("llog_other", "llog_other@qku.edu.az", PASSWORD)
        cls.chair = User.objects.create_user("llog_chair", "llog_chair@qku.edu.az", PASSWORD)
        cls.student = User.objects.create_user("llog_student", "llog_student@qku.edu.az", PASSWORD)

        activate_member(cls.org, cls.teacher, "teacher", permissions=TEACHER_PERMS)
        activate_member(cls.org, cls.other_teacher, "teacher", permissions=TEACHER_PERMS)
        activate_member(
            cls.org,
            cls.chair,
            "chair_head",
            permissions=CHAIR_PERMS,
            level=70,
            scope_type=RoleScopeType.ORGANIZATION,
        )
        activate_member(cls.org, cls.student, "student", permissions=["course.view"], level=10)
        for user, role in (
            (cls.teacher, "teacher"),
            (cls.other_teacher, "teacher"),
            (cls.chair, "chair_head"),
            (cls.student, "student"),
        ):
            profile = user.profile
            profile.role = role
            profile.save(update_fields=["role"])

        cls.offering = make_offering(cls.org, cls.stack, cls.teacher)
        # İkinci açılış EYNİ semestrdədir (bölmə cari dövrə görə süzür), amma
        # `uniq_offering_subject_period_group` üçün AYRI fənn və qrupdadır.
        cls.other_subject = Subject.objects.create(organization=cls.org, code="LLG202", name="İkinci fənn")
        cls.other_group = OrgUnit.objects.create(
            organization=cls.org, name="LLG202-qrup", slug="llog-univ-llg202-group", unit_type=OrgUnitType.GROUP
        )
        cls.other_offering = CourseOffering.objects.create(
            organization=cls.org,
            subject=cls.other_subject,
            period=cls.stack["period"],
            group=cls.other_group,
            instructor=cls.other_teacher,
            lesson_hours=60,
        )

        # Dərs tarixləri SEMESTRİN İÇİNDƏ olmalıdır (bölmə cari dövrə görə süzür).
        cls.window_from = dt.date(2025, 10, 1)
        cls.window_to = dt.date(2025, 10, 31)
        today = dt.date(2025, 10, 20)
        cls.today = today
        # 1) vaxtında yazılmış dərs (xanalar dərs günü yazılıb)
        cls.lesson_ok = Lesson.objects.create(
            organization=cls.org,
            offering=cls.offering,
            date=today - dt.timedelta(days=3),
            kind=LessonKind.SEMINAR,
            topic="Yığın və növbə strukturları",
            hours=2,
            start_time=dt.time(9, 0),
            end_time=dt.time(10, 20),
            instructor=cls.teacher,
        )
        # 2) jurnalı boş dərs (heç bir xana yoxdur)
        cls.lesson_empty = Lesson.objects.create(
            organization=cls.org,
            offering=cls.offering,
            date=today - dt.timedelta(days=2),
            kind=LessonKind.LECTURE,
            topic="",
            hours=2,
            instructor=cls.teacher,
        )
        # 3) başqa müəllimin dərsi — müəllimin siyahısına DÜŞMƏMƏLİDİR
        cls.lesson_other = Lesson.objects.create(
            organization=cls.org,
            offering=cls.other_offering,
            date=today - dt.timedelta(days=1),
            kind=LessonKind.LECTURE,
            topic="Başqa müəllimin mövzusu",
            hours=2,
            instructor=cls.other_teacher,
        )

        student_record_enrollment = Enrollment.objects.create(
            organization=cls.org, offering=cls.offering, student=cls.student
        )
        cls.enrollment = student_record_enrollment
        LessonMark.objects.create(
            organization=cls.org,
            lesson=cls.lesson_ok,
            enrollment=cls.enrollment,
            status=AttendanceStatus.PRESENT,
            score=8,
        )

    # ── köməkçilər ──────────────────────────────────────────────────────────

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _fragment(self, user, **params):
        url = reverse("accounts:profile_section_fragment", kwargs={"section": SECTION})
        query = {"ll_range": "custom", "ll_from": "2025-09-01", "ll_to": "2026-01-31"}
        query.update(params)
        return self._client(user).get(url, query)

    def _sections(self, user):
        response = self._client(user).get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        return set(response.context["allowed_sections"])

    # ── 1. Rol qapısı ───────────────────────────────────────────────────────

    def test_teacher_sees_section_and_gets_200(self):
        self.assertIn(SECTION, self._sections(self.teacher))
        self.assertEqual(self._fragment(self.teacher).status_code, 200)

    def test_student_is_denied(self):
        self.assertNotIn(SECTION, self._sections(self.student))
        self.assertEqual(self._fragment(self.student).status_code, 403)

    def test_supervisor_with_journal_roster_gets_200(self):
        self.assertIn(SECTION, self._sections(self.chair))
        self.assertEqual(self._fragment(self.chair).status_code, 200)

    # ── 2. Əhatə ────────────────────────────────────────────────────────────

    def test_teacher_only_sees_own_lessons(self):
        response = self._fragment(self.teacher)
        rows = response.context["lessons_log_section"]["rows"]
        ids = {row["id"] for row in rows}
        self.assertIn(str(self.lesson_ok.id), ids)
        self.assertIn(str(self.lesson_empty.id), ids)
        self.assertNotIn(str(self.lesson_other.id), ids)

    def test_teacher_filter_is_ignored_for_a_plain_teacher(self):
        response = self._fragment(self.teacher, ll_teacher=str(self.other_teacher.id))
        section = response.context["lessons_log_section"]
        self.assertFalse(section["is_supervisor"])
        ids = {row["id"] for row in section["rows"]}
        self.assertNotIn(str(self.lesson_other.id), ids)
        self.assertIn(str(self.lesson_ok.id), ids)

    def test_supervisor_sees_every_teacher_and_can_filter(self):
        response = self._fragment(self.chair)
        section = response.context["lessons_log_section"]
        self.assertTrue(section["is_supervisor"])
        ids = {row["id"] for row in section["rows"]}
        self.assertIn(str(self.lesson_other.id), ids)

        filtered = self._fragment(self.chair, ll_teacher=str(self.other_teacher.id))
        filtered_ids = {row["id"] for row in filtered.context["lessons_log_section"]["rows"]}
        self.assertEqual(filtered_ids, {str(self.lesson_other.id)})

    def test_csv_export_rejects_teacher_filter_for_a_plain_teacher(self):
        url = reverse("registrar:lessons_log_csv")
        response = self._client(self.teacher).get(url, {"ll_teacher": str(self.other_teacher.id)})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.content.decode(), "teacher_filter_forbidden")

    def test_csv_export_returns_own_rows(self):
        url = reverse("registrar:lessons_log_csv")
        response = self._client(self.teacher).get(
            url, {"ll_range": "custom", "ll_from": "2025-09-01", "ll_to": "2026-01-31"}
        )
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn("Yığın və növbə strukturları", body)
        self.assertNotIn("Başqa müəllimin mövzusu", body)

    # ── 3. Qeyd statusu ─────────────────────────────────────────────────────

    def test_note_state_on_time_late_and_empty(self):
        lesson_date = dt.date(2026, 3, 2)
        self.assertEqual(service.note_state(lesson_date=lesson_date, marks_count=0, first_mark=None), "empty")
        on_time = timezone.make_aware(dt.datetime(2026, 3, 3, 10, 0))
        self.assertEqual(service.note_state(lesson_date=lesson_date, marks_count=1, first_mark=on_time), "on_time")
        late = timezone.make_aware(dt.datetime(2026, 3, 6, 10, 0))
        self.assertEqual(service.note_state(lesson_date=lesson_date, marks_count=1, first_mark=late), "late")

    def test_totals_count_empty_journals(self):
        lessons = service.scoped_lessons(self.teacher, self.org, supervisor=False)
        totals = service.range_totals(lessons)
        self.assertEqual(totals["lessons"], 2)
        self.assertEqual(totals["empty"], 1)
        self.assertEqual(totals["hours"], 4)
        self.assertEqual(totals["attendance_rate"], 100)

    # ── 4. Sillabus mövzu əhatəsi ───────────────────────────────────────────

    def test_coverage_is_zero_without_an_approved_syllabus(self):
        stats = service.coverage_for_offering(self.offering, held_topics={"Yığın və növbə strukturları"})
        self.assertFalse(stats["has_syllabus"])
        self.assertEqual(stats["planned"], 0)
        self.assertEqual(stats["percent"], 0)

    def test_coverage_counts_held_topics_from_the_approved_version(self):
        planned = ["Alfa mövzu", "Beta mövzu", "Qamma mövzu", "Delta mövzu"]
        with mock_approved_topics(planned):
            stats = service.coverage_for_offering(self.offering, held_topics={"alfa mövzu", "Beta mövzu"})
        self.assertTrue(stats["has_syllabus"])
        self.assertEqual(stats["planned"], 4)
        self.assertEqual(stats["covered"], 2)
        self.assertEqual(stats["percent"], 50)
        self.assertEqual(stats["remaining"], ["Qamma mövzu", "Delta mövzu"])

    # ── 6. Sorğu büdcəsi ────────────────────────────────────────────────────

    def test_query_count_does_not_grow_with_the_number_of_lessons(self):
        """N+1 QORUYUCUSU — sorğu sayı SƏTİR SAYINDAN asılı olmamalıdır.

        Mütləq rəqəm kabinet qabığının özündən (sidebar, badge sayğacları,
        icazə həlli) asılıdır və zamanla dəyişir; MƏNALI invariant sətir
        artımına REAKSİYA VERMƏMƏKDİR.
        """
        from django.db import connection

        client = self._client(self.teacher)
        url = reverse("accounts:profile_section_fragment", kwargs={"section": SECTION})
        params = {"ll_range": "custom", "ll_from": "2025-09-01", "ll_to": "2026-01-31"}
        client.get(url, params)  # isinmə (sessiya / icazə keşi)

        with CaptureQueriesContext(connection) as before:
            self.assertEqual(client.get(url, params).status_code, 200)

        for index in range(12):
            lesson = Lesson.objects.create(
                organization=self.org,
                offering=self.offering,
                date=self.window_from + dt.timedelta(days=index),
                kind=LessonKind.SEMINAR,
                topic="Mövzu %s" % index,
                hours=2,
                instructor=self.teacher,
            )
            LessonMark.objects.create(
                organization=self.org,
                lesson=lesson,
                enrollment=self.enrollment,
                status=AttendanceStatus.PRESENT,
            )

        with CaptureQueriesContext(connection) as after:
            response = client.get(url, params)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["lessons_log_section"]["rows"]), 14)
        self.assertLessEqual(
            len(after.captured_queries),
            len(before.captured_queries),
            "Sətir sayı artanda sorğu sayı da artdı — N+1",
        )


def mock_approved_topics(topics):
    """`_approved_week_topics` üçün kontekst-menecer (sillabus qatı simulyasiyası).

    Sillabusun tam dosyesini qurmaq bu testin mövzusu DEYİL — burada yoxlanan
    ƏHATƏ RİYAZİYYATIDIR. Sillabus zəncirinin özü `apps/syllabus` testlərindədir.
    """
    from unittest import mock

    return mock.patch.object(service, "_approved_week_topics", return_value=list(topics))


@override_settings(UNIVERSITY_MODE=True)
class JournalSyllabusPolicyTest(TestCase):
    """README §8/2 — «təsdiqlənmiş sillabus olmadan jurnal bloklanır» AÇARI."""

    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("llog-policy")
        cls.stack = make_academic_stack(cls.org, code="POL101")
        cls.teacher = User.objects.create_user("pol_teacher", "pol_teacher@qku.edu.az", PASSWORD)
        activate_member(cls.org, cls.teacher, "teacher", permissions=TEACHER_PERMS)
        profile = cls.teacher.profile
        profile.role = "teacher"
        profile.save(update_fields=["role"])
        cls.offering = make_offering(cls.org, cls.stack, cls.teacher)

    def _set_policy(self, enabled: bool):
        with bypass_rls():
            organization = Organization.objects.get(pk=self.org.pk)
            settings = dict(organization.settings or {})
            settings["journal"] = {journal_policy.REQUIRE_APPROVED_SYLLABUS: enabled}
            organization.settings = settings
            organization.save(update_fields=["settings"])
        self.offering.refresh_from_db()
        self.offering.organization.refresh_from_db()

    # ── siyasət SÖNDÜRÜLÜ (default) ─────────────────────────────────────────

    def test_default_is_off_and_lesson_creation_works(self):
        self.assertFalse(journal_policy.require_approved_syllabus(self.org))
        gate = journal_policy.syllabus_gate(self.offering)
        self.assertFalse(gate["enforced"])
        self.assertFalse(gate["locked"])
        lesson = gradebook.create_lesson(
            offering=self.offering,
            date=timezone.localdate(),
            kind=LessonKind.LECTURE,
            topic="Sərbəst mətn mövzusu",
        )
        self.assertIsNotNone(lesson.pk)

    # ── siyasət AÇIQ ────────────────────────────────────────────────────────

    def test_enabled_policy_locks_lesson_creation_with_a_reason_code(self):
        self._set_policy(True)
        offering = type(self.offering).objects.select_related("organization").get(pk=self.offering.pk)
        gate = journal_policy.syllabus_gate(offering)
        self.assertTrue(gate["enforced"])
        self.assertTrue(gate["locked"])
        self.assertEqual(gate["reason_code"], journal_policy.REASON_NO_APPROVED_SYLLABUS)

        with self.assertRaises(journal_policy.SyllabusGateError) as raised:
            gradebook.create_lesson(offering=offering, date=timezone.localdate(), kind=LessonKind.LECTURE)
        self.assertEqual(raised.exception.reason_code, journal_policy.REASON_NO_APPROVED_SYLLABUS)

    def test_enabled_policy_returns_403_from_the_journal_post(self):
        self._set_policy(True)
        client = Client()
        client.force_login(self.teacher)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        response = client.post(
            reverse("registrar:journal_detail", args=[self.offering.pk]),
            {"action": "add_lesson", "lesson_date": timezone.localdate().isoformat()},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.content.decode(), journal_policy.REASON_NO_APPROVED_SYLLABUS)

    def test_enabled_policy_makes_the_journal_read_only(self):
        self._set_policy(True)
        client = Client()
        client.force_login(self.teacher)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        response = client.get(reverse("registrar:journal_detail", args=[self.offering.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["can_edit"])
        self.assertTrue(response.context["syllabus_gate"]["locked"])
