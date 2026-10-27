"""«Data bərpası» rejimi — ``journal.teacher_full_edit`` (sahib 2026-10-27).

Sahib: «Bütün müəllimlərə access ver … köhnə tarixdə dəyişiklik etmək olsun: əlavə etmək, hər şey etmək, gün
silmək, mövzunu edit etmək. Dəyişikliyin səbəbi soruşulsun sadəcə, heç bir təqdimat və s. olmadan … Sistem
tənzimləməsində bunu söndürüb-yandırmaq olsun.»

* SÖNÜLÜ (defolt) — bütün köhnə qapılar: köhnə tarixə dərs yox, pəncərəsi bitmiş dərs silinmir, bağlı jurnala yazı yox,
  «clear» nəzərə alınmır;
* AÇIQ — müəllim səbəb ilə keçmiş tarixə dərs açır, dərsi xanaları ilə silir, mövzunu dəyişir, bağlı jurnalda
  kilidli xananı dəyişir/təmizləyir; səbəbsiz → rədd (avtomatik yadda saxlama 409 ``reason_required``); hər əməl
  ``registrar.grade.full-edit`` audit sətrinə səbəb + köhnə/yeni dəyərlə düşür;
* QORUNUR — bölünmüş jurnalın əhatəsi, başqa müəllimin jurnalı, üzrlü xana, imtahan (Midterm) pəncərəsi;
* açarın dəyişməsi «Sistem tənzimləmələri» auditinə düşür.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import RuntimeSetting
from apps.accounts.services import runtime_settings_admin
from apps.audit.models import AuditLog
from apps.registrar import gradebook, journal_extras, journal_policy
from apps.registrar.models import (
    ApprovalStatus,
    AssessmentScheme,
    AttendanceStatus,
    JournalShare,
    Lesson,
    LessonKind,
    LessonMark,
)
from apps.registrar.tests.test_journal_rules import _setup_offering
from core import runtime_settings as rs
from core.rls import bypass_rls, journal_unlock
from core.runtime_settings_journal_full_edit import KEY_TEACHER_FULL_EDIT

User = get_user_model()
TODAY = timezone.localdate
ON = override_settings(JOURNAL_TEACHER_FULL_EDIT=True)
LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "full-edit"}}
FULL_EDIT_KIND = "registrar.grade.full-edit"
TIME = "08:30|10:00"


def _age_mark(mark, minutes):
    LessonMark.objects.filter(pk=mark.pk).update(created_at=timezone.now() - timedelta(minutes=minutes))


def _age_lesson(lesson, days=1):
    Lesson.objects.filter(pk=lesson.pk).update(created_at=timezone.now() - timedelta(days=days))


class _Base(TestCase):
    prefix = "jfe"

    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            _setup_offering(cls, cls.prefix)
            # Yazma pəncərəsindən (7 gün) köhnə, redaktə pəncərəsi (120 dəq.) bitmiş seminar.
            cls.old = gradebook.create_lesson(
                offering=cls.offering,
                date=TODAY() - timedelta(days=20),
                kind=LessonKind.SEMINAR,
                start_time="08:30",
                end_time="10:00",
                topic="Köhnə mövzu",
                created_by=cls.teacher,
                allow_past=True,
            )
            _age_lesson(cls.old, days=20)
            gradebook.save_marks(
                offering=cls.offering,
                entries=[
                    {"lesson_id": cls.old.id, "enrollment_id": cls.enrollment.id, "status": "absent", "score": ""}
                ],
                by_user=cls.teacher,
                enforce_day=False,
            )
            _age_mark(LessonMark.objects.get(lesson=cls.old), 60 * 24 * 20)

    def setUp(self):
        self.old.refresh_from_db()

    def _client(self, user=None):
        client = Client()
        client.force_login(user or self.teacher)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _detail(self):
        return reverse("registrar:journal_detail", args=[self.offering.id])

    def _lesson_url(self, lesson=None):
        return reverse("registrar:journal_lesson_action", args=[self.offering.id, (lesson or self.old).id])

    def _mark(self, lesson=None):
        with bypass_rls():
            return LessonMark.objects.filter(lesson=lesson or self.old, enrollment=self.enrollment).first()

    def _full_edit_rows(self):
        with bypass_rls():
            return list(AuditLog.objects.filter(resource_type=FULL_EDIT_KIND, resource_id=str(self.offering.pk)))

    def _add(self, client, date, **extra):
        data = {"action": "add_lesson", "lesson_date": date.isoformat(), "lesson_kind": "lecture", "lesson_time": TIME}
        data.update(extra)
        return client.post(self._detail(), data)

    def _cell(self, client, status, lesson=None, **extra):
        lesson = lesson or self.old
        data = {
            "action": "save_marks",
            "autosave": "1",
            f"att__{lesson.id}__{self.enrollment.id}": status,
            f"score__{lesson.id}__{self.enrollment.id}": "",
        }
        data.update(extra)
        return client.post(self._detail(), data)

    def _close_journal(self):
        with bypass_rls():
            AssessmentScheme.objects.filter(offering=self.offering).update(
                is_published=True, approval_status=ApprovalStatus.APPROVED
            )


class OffKeepsEveryGateTest(_Base):
    prefix = "jfeoff"

    def test_setting_defaults_off(self):
        self.assertFalse(journal_policy.teacher_full_edit_enabled(self.org))
        spec = rs.SPECS[KEY_TEACHER_FULL_EDIT]
        self.assertEqual((spec.group, spec.kind, spec.default()), ("journal", "bool", False))

    def test_past_lesson_beyond_window_refused_even_with_reason(self):
        client = self._client()
        self._add(client, TODAY() - timedelta(days=30), full_edit_reason="bərpa üçün")
        with bypass_rls():
            self.assertFalse(Lesson.objects.filter(offering=self.offering, date=TODAY() - timedelta(days=30)).exists())

    def test_old_lesson_delete_refused(self):
        self._client().post(self._lesson_url(), {"action": "update_lesson", "do_delete": "1", "full_edit_reason": "x"})
        with bypass_rls():
            self.assertTrue(Lesson.objects.filter(pk=self.old.pk).exists())

    def test_locked_cell_and_clear_ignored(self):
        client = self._client()
        resp = self._cell(client, "present", full_edit_reason="bərpa üçün")
        self.assertEqual((resp.status_code, resp.json()["code"]), (409, "mark_locked"))
        resp = self._cell(client, "clear", full_edit_reason="bərpa üçün")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._mark().status, AttendanceStatus.ABSENT)
        self.assertEqual(self._full_edit_rows(), [])

    def test_page_has_no_banner(self):
        html = self._client().get(self._detail()).content.decode()
        self.assertNotIn("data-jd-fe-banner", html)
        self.assertNotIn('name="full_edit_reason"', html)


@ON
class OnLessonsTest(_Base):
    prefix = "jfeon"

    def test_add_past_lesson_beyond_window_needs_reason_and_is_audited(self):
        client = self._client()
        day = TODAY() - timedelta(days=30)
        self._add(client, day)
        with bypass_rls():
            self.assertFalse(Lesson.objects.filter(offering=self.offering, date=day).exists())
        self._add(client, day, full_edit_reason="  köhnə   sistem  ", lesson_topic="Bərpa olunan mövzu")
        with bypass_rls():
            lesson = Lesson.objects.get(offering=self.offering, date=day)
        self.assertEqual(lesson.topic, "Bərpa olunan mövzu")
        rows = self._full_edit_rows()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].new_values["reason"], "köhnə sistem")
        self.assertEqual(rows[0].new_values["action"], "lesson-add")
        self.assertEqual(rows[0].user_id, self.teacher.pk)

    def test_date_bounds_still_apply(self):
        client = self._client()
        for day in (TODAY() + timedelta(days=1), self.period.start_date - timedelta(days=1)):
            self._add(client, day, full_edit_reason="bərpa üçün")
            with bypass_rls():
                self.assertFalse(Lesson.objects.filter(offering=self.offering, date=day).exists())

    def test_reason_shorter_than_minimum_is_refused(self):
        self._add(self._client(), TODAY() - timedelta(days=30), full_edit_reason=" a ")
        with bypass_rls():
            self.assertFalse(Lesson.objects.filter(offering=self.offering, date=TODAY() - timedelta(days=30)).exists())

    def test_delete_lesson_with_marks(self):
        client = self._client()
        client.post(self._lesson_url(), {"action": "update_lesson", "do_delete": "1"})
        with bypass_rls():
            self.assertTrue(Lesson.objects.filter(pk=self.old.pk).exists())
        client.post(self._lesson_url(), {"action": "update_lesson", "do_delete": "1", "full_edit_reason": "səhv gün"})
        with bypass_rls():
            self.assertFalse(Lesson.objects.filter(pk=self.old.pk).exists())
            self.assertFalse(LessonMark.objects.filter(lesson_id=self.old.pk).exists())
            self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.absence_hours, 0)
        row = self._full_edit_rows()[0]
        self.assertEqual(row.new_values["action"], "lesson-delete")
        self.assertIn("qb", [change["old"] for change in row.changes])

    def test_edit_topic_of_old_lesson(self):
        data = {
            "action": "update_lesson",
            "lesson_date": self.old.date.isoformat(),
            "lesson_kind": "seminar",
            "lesson_topic": "Düzgün mövzu",
            "lesson_hours": "2",
            "lesson_time": TIME,
        }
        client = self._client()
        client.post(self._lesson_url(), data)
        self.old.refresh_from_db()
        self.assertEqual(self.old.topic, "Köhnə mövzu")
        client.post(self._lesson_url(), {**data, "full_edit_reason": "mövzu səhv idi"})
        self.old.refresh_from_db()
        self.assertEqual(self.old.topic, "Düzgün mövzu")
        changes = self._full_edit_rows()[0].changes
        topic = [change for change in changes if change["item"].endswith("dərs mövzu")]
        self.assertEqual((topic[0]["old"], topic[0]["new"]), ("Köhnə mövzu", "Düzgün mövzu"))

    def test_add_and_delete_in_closed_journal(self):
        self._close_journal()
        client = self._client()
        self._add(client, TODAY(), full_edit_reason="bağlı jurnal bərpası")
        with bypass_rls():
            self.assertTrue(Lesson.objects.filter(offering=self.offering, date=TODAY()).exists())


@ON
class OnMarksTest(_Base):
    prefix = "jfemk"

    def test_locked_cell_needs_reason_then_writes_with_audit(self):
        client = self._client()
        resp = self._cell(client, "present")
        self.assertEqual((resp.status_code, resp.json()["code"]), (409, "reason_required"))
        self.assertEqual(self._mark().status, AttendanceStatus.ABSENT)
        resp = self._cell(client, "present", full_edit_reason="köçmə xətası")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["written"], 1)
        self.assertEqual(self._mark().status, AttendanceStatus.PRESENT)
        row = self._full_edit_rows()[0]
        self.assertEqual((row.changes[0]["old"], row.changes[0]["new"]), ("qb", "iə"))
        self.assertIn("köçmə xətası", row.reason)

    def test_edit_and_clear_cell_in_closed_journal(self):
        self._close_journal()
        client = self._client()
        resp = self._cell(client, "present", full_edit_reason="bağlı jurnal")
        self.assertEqual(resp.json()["written"], 1)
        self.assertEqual(self._mark().status, AttendanceStatus.PRESENT)
        self.assertEqual(self._cell(client, "clear").json()["code"], "reason_required")
        resp = self._cell(client, "clear", full_edit_reason="bağlı jurnal")
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(self._mark())

    def test_new_mark_on_old_lesson_and_service_level(self):
        with bypass_rls():
            LessonMark.objects.filter(lesson=self.old).delete()
            entry = {"lesson_id": self.old.id, "enrollment_id": self.enrollment.id, "status": "present", "score": "7"}
            kwargs = {"offering": self.offering, "entries": [entry], "by_user": self.teacher, "report": True}
            self.assertEqual(gradebook.save_marks(**kwargs)["blocked"], 1)  # adi qayda: 7 gündən köhnə
            self.assertEqual(gradebook.save_marks(**kwargs, full_edit=True)["reason_required"], 1)
            result = gradebook.save_marks(**kwargs, full_edit=True, full_reason="bərpa")
        self.assertEqual(result, {"written": 1, "rejected": 0})
        self.assertEqual(self._mark().score, Decimal("7"))

    def test_unchanged_resend_needs_no_reason(self):
        self._close_journal()
        resp = self._cell(self._client(), "absent")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._full_edit_rows(), [])

    def test_excused_cell_stays_locked(self):
        with bypass_rls(), transaction.atomic(), journal_unlock():
            LessonMark.objects.filter(lesson=self.old).update(status=AttendanceStatus.EXCUSED)
        resp = self._cell(self._client(), "present", full_edit_reason="bərpa üçün")
        self.assertEqual((resp.status_code, resp.json()["code"]), (409, "mark_locked"))
        self.assertEqual(self._mark().status, AttendanceStatus.EXCUSED)

    def test_page_shows_banner_and_unlocked_cell(self):
        self._close_journal()
        html = self._client().get(self._detail()).content.decode()
        self.assertIn("data-jd-fe-banner", html)
        self.assertIn("Data bərpası rejimi: keçmiş tarixli dəyişikliklər səbəb ilə açıqdır", html)
        self.assertIn(f'name="att__{self.old.id}__{self.enrollment.id}"', html)
        self.assertIn('name="full_edit_reason"', html)
        self.assertIn('data-lesson-fe="1"', html)
        self.assertNotIn('data-jd-lock="time"', html)


@ON
class OnStillProtectedTest(_Base):
    prefix = "jfeprot"

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        from apps.organizations.models import Membership

        with bypass_rls():
            cls.seminarist = User.objects.create_user("jfeprot_sem", "jfeprot_sem@qku.edu.az", "pw")
            cls.stranger = User.objects.create_user("jfeprot_str", "jfeprot_str@qku.edu.az", "pw")
            for user in (cls.seminarist, cls.stranger):
                Membership.objects.create(
                    user=user, organization=cls.org, role=cls.org.roles.get(name="teacher"), is_active=True
                )
            share = JournalShare.objects.create(
                organization=cls.org, offering=cls.offering, teacher=cls.seminarist, kinds=["seminar"]
            )
            share.enrollments.set([cls.enrollment])
            cls.lecture = gradebook.create_lesson(
                offering=cls.offering,
                date=TODAY() - timedelta(days=15),
                kind=LessonKind.LECTURE,
                start_time="10:10",
                end_time="11:40",
                created_by=cls.teacher,
                allow_past=True,
            )
            _age_lesson(cls.lecture, days=15)

    def test_share_teacher_limited_to_own_kinds(self):
        client = self._client(self.seminarist)
        resp = client.post(
            self._lesson_url(self.lecture), {"action": "update_lesson", "do_delete": "1", "full_edit_reason": "bərpa"}
        )
        self.assertEqual(resp.status_code, 403)
        resp = self._cell(client, "absent", lesson=self.lecture, full_edit_reason="bərpa üçün")
        self.assertEqual(resp.status_code, 403)
        with bypass_rls():
            self.assertTrue(Lesson.objects.filter(pk=self.lecture.pk).exists())
        # Öz növündə (seminar) — səbəb ilə keçir.
        resp = self._cell(client, "present", full_edit_reason="bərpa üçün")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._mark().status, AttendanceStatus.PRESENT)

    def test_other_teacher_journal_closed(self):
        client = self._client(self.stranger)
        self.assertEqual(client.get(self._detail()).status_code, 404)
        self.assertEqual(self._cell(client, "present", full_edit_reason="bərpa üçün").status_code, 404)
        resp = client.post(self._lesson_url(), {"action": "update_lesson", "do_delete": "1", "full_edit_reason": "x"})
        self.assertEqual(resp.status_code, 404)
        with bypass_rls():
            self.assertTrue(Lesson.objects.filter(pk=self.old.pk).exists())
        self.assertEqual(self._mark().status, AttendanceStatus.ABSENT)

    def test_exam_window_scores_not_opened(self):
        with bypass_rls():
            component = list(journal_extras.ensure_kollokviums(self.offering))[0]
        resp = self._client().post(
            reverse("registrar:journal_kollokvium_save", args=[self.offering.id]),
            {f"kscore__{component.id}__{self.enrollment.id}": "15", "autosave": "1", "full_edit_reason": "bərpa"},
        )
        self.assertEqual((resp.status_code, resp.json()["code"]), (409, "window_closed"))


@override_settings(RUNTIME_SETTINGS_ENABLED=True, CACHES=LOCMEM)
class ToggleTest(TestCase):
    def test_toggle_is_audited_and_read_by_policy(self):
        rs.invalidate()
        try:
            actor = User.objects.create_user("jfe_actor", "jfe_actor@qku.edu.az", "pw")
            self.assertFalse(journal_policy.teacher_full_edit_enabled())
            fields = {f["key"]: f for group in runtime_settings_admin.describe() for f in group["fields"]}
            self.assertEqual(fields[KEY_TEACHER_FULL_EDIT]["kind"], "bool")
            runtime_settings_admin.save_values(actor=actor, data={KEY_TEACHER_FULL_EDIT: "1"})
            self.assertIs(RuntimeSetting.objects.get(key=KEY_TEACHER_FULL_EDIT).value, True)
            self.assertTrue(journal_policy.teacher_full_edit_enabled())
            row = AuditLog.objects.filter(resource_type="core.runtime_settings").latest("created_at")
            self.assertEqual(row.changes["changed"][0]["key"], KEY_TEACHER_FULL_EDIT)
            self.assertEqual((row.changes["changed"][0]["old"], row.changes["changed"][0]["new"]), (False, True))
            runtime_settings_admin.save_values(actor=actor, data={KEY_TEACHER_FULL_EDIT: "0"})
            self.assertFalse(RuntimeSetting.objects.filter(key=KEY_TEACHER_FULL_EDIT).exists())
            self.assertFalse(journal_policy.teacher_full_edit_enabled())
        finally:
            rs.invalidate()
