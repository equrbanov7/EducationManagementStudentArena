"""Əvvəl yazılmış i/e, q/b və bal yalnız RİM-dədir (sahib 2026-11-27).

Sahib: «əvvəlki tarixdə yazılmış i/e-ni, balı ancaq və ancaq RİM rəhbəri və RİM işçisi dəyişə bilər. Müəllim əvvəlki
günə dərs əlavə edərsə 15 dəqiqə ərzində nə yazsa odur — q/b və bal; i/e 24 saat aktiv qalsın, sonra dəyişmək olmasın.
Əlavə olunandan sonra dəyişmək mümkün olmasın, baxış icazəsi olanlar da edə bilməsin.»

* «Data bərpası» açıq olsa da müəllim kilidli xananı (1 günü keçmiş i/e, 15 dəqiqəni keçmiş q/b / bal) dəyişə və
  təmizləyə bilmir; keçmiş günə açdığı dərsin BOŞ xanasına yazır və yazdığı öz pəncərəsində qalır;
* RİM rəhbəri həmin xananı səbəblə dəyişir;
* kilidli xanası olan dərsi müəllim silə, növünü / tarixini dəyişə bilmir (mövzu sərbəstdir);
* profilə baxış (view-as) altında jurnala yazı bağlıdır.
"""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.organizations.models import Membership
from apps.registrar import gradebook, journal_full_edit
from apps.registrar.models import AttendanceStatus, Lesson, LessonKind, LessonMark
from apps.registrar.tests.test_journal_rules import _setup_offering
from core.rls import bypass_rls

User = get_user_model()
TODAY = timezone.localdate
TIME = "08:30|10:00"
PROD = override_settings(
    JOURNAL_TEACHER_FULL_EDIT=True,
    JOURNAL_BACKDATE_SINCE_ENABLED=True,
    JOURNAL_BACKDATE_SINCE=(timezone.localdate() - timedelta(days=60)).isoformat(),
    JOURNAL_LATE_ENTRY_DAYS=14,
    JOURNAL_LESSON_ACTIVATION=False,
)


def _age(mark, minutes):
    LessonMark.objects.filter(pk=mark.pk).update(created_at=timezone.now() - timedelta(minutes=minutes))


@PROD
class PastMarksRimOnlyTest(TestCase):
    prefix = "pmr"

    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            _setup_offering(cls, cls.prefix)
            type(cls.period).objects.filter(pk=cls.period.pk).update(
                start_date=TODAY() - timedelta(days=90), end_date=TODAY() + timedelta(days=60)
            )
            cls.rim = User.objects.create_user(f"{cls.prefix}_rim", f"{cls.prefix}_rim@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.rim, organization=cls.org, role=cls.org.roles.get(name="ikt_rehber"), is_active=True
            )
            cls.lesson = gradebook.create_lesson(
                offering=cls.offering,
                date=TODAY() - timedelta(days=3),
                kind=LessonKind.SEMINAR,
                start_time="08:30",
                end_time="10:00",
                topic="Keçmiş gün",
                created_by=cls.teacher,
                allow_past=True,
            )
            Lesson.objects.filter(pk=cls.lesson.pk).update(created_at=timezone.now() - timedelta(days=3))

    def client_for(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def url(self):
        return reverse("registrar:journal_detail", args=[self.offering.id])

    def cell(self, user, status, score="", reason="bərpa"):
        data = {
            "action": "save_marks",
            "autosave": "1",
            f"att__{self.lesson.id}__{self.enrollment.id}": status,
            f"score__{self.lesson.id}__{self.enrollment.id}": score,
            "full_edit_reason": reason,
        }
        return self.client_for(user).post(self.url(), data)

    def mark(self):
        with bypass_rls():
            return LessonMark.objects.filter(lesson=self.lesson, enrollment=self.enrollment).first()

    def write(self, status="present", score=None, minutes=0):
        with bypass_rls():
            mark = LessonMark.objects.create(
                organization=self.org,
                lesson=self.lesson,
                enrollment=self.enrollment,
                status=status,
                score=score,
                entered_by=self.teacher,
            )
            _age(mark, minutes)
        return mark

    # ── müəllim ──────────────────────────────────────────────────────────

    def test_teacher_writes_empty_cell_of_past_lesson_then_it_freezes(self):
        resp = self.cell(self.teacher, "absent")
        self.assertEqual((resp.status_code, resp.json()["written"]), (200, 1))
        self.assertEqual(self.mark().status, AttendanceStatus.ABSENT)
        with bypass_rls():
            _age(self.mark(), 16)  # q/b 15 dəqiqədən sonra donur
        resp = self.cell(self.teacher, "present")
        self.assertEqual((resp.status_code, resp.json()["code"]), (409, "mark_locked"))
        self.assertEqual(self.mark().status, AttendanceStatus.ABSENT)

    def test_teacher_changes_own_ie_within_one_day(self):
        self.write(minutes=60 * 5)
        resp = self.cell(self.teacher, "absent")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.mark().status, AttendanceStatus.ABSENT)

    def test_teacher_cannot_change_or_clear_ie_older_than_one_day_even_in_full_edit(self):
        self.write(minutes=60 * 25)
        for status in ("absent", "clear"):
            resp = self.cell(self.teacher, status)
            self.assertEqual((resp.status_code, resp.json()["code"]), (409, "mark_locked"), status)
        self.assertEqual(self.mark().status, AttendanceStatus.PRESENT)

    def test_teacher_cannot_change_old_score(self):
        self.write(score=7, minutes=20)
        resp = self.cell(self.teacher, "present", score="9")
        self.assertEqual((resp.status_code, resp.json()["code"]), (409, "mark_locked"))
        self.assertEqual(self.mark().score, 7)

    def test_grid_keeps_locked_cell_read_only_for_teacher(self):
        self.write(minutes=60 * 25)
        html = self.client_for(self.teacher).get(self.url()).content.decode()
        self.assertIn("data-jd-fe-banner", html)
        self.assertNotIn(f'name="att__{self.lesson.id}__{self.enrollment.id}"', html)
        rim_html = self.client_for(self.rim).get(self.url()).content.decode()
        self.assertIn(f'name="att__{self.lesson.id}__{self.enrollment.id}"', rim_html)

    # ── RİM ──────────────────────────────────────────────────────────────

    def test_rim_changes_and_clears_old_marks(self):
        self.write(minutes=60 * 25)
        resp = self.cell(self.rim, "absent", reason="təqdimat əsasında")
        self.assertEqual((resp.status_code, resp.json()["written"]), (200, 1))
        self.assertEqual(self.mark().status, AttendanceStatus.ABSENT)
        resp = self.cell(self.rim, "clear", reason="təqdimat əsasında")
        self.assertEqual(resp.status_code, 200)
        self.assertIsNone(self.mark())

    def test_override_actors(self):
        # RİM rəhbəri rolu sorğu kontekstində həll olunur — onu yuxarıdakı HTTP testləri yoxlayır.
        with bypass_rls():
            self.assertTrue(journal_full_edit.rim_override(self.owner, self.offering))
            self.assertFalse(journal_full_edit.rim_override(self.teacher, self.offering))

    # ── dərs sətri ───────────────────────────────────────────────────────

    def lesson_post(self, user, **data):
        url = reverse("registrar:journal_lesson_action", args=[self.offering.id, self.lesson.id])
        base = {
            "action": "update_lesson",
            "lesson_date": self.lesson.date.isoformat(),
            "lesson_kind": "seminar",
            "lesson_hours": "2",
            "lesson_time": TIME,
            "full_edit_reason": "bərpa",
        }
        base.update(data)
        return self.client_for(user).post(url, base, follow=True)

    def test_teacher_cannot_delete_or_rekind_lesson_with_locked_marks(self):
        self.write(minutes=60 * 25)
        resp = self.lesson_post(self.teacher, do_delete="1")
        self.assertIn("RİM-ə müraciət", " ".join(str(m) for m in resp.context["messages"]))
        self.lesson_post(self.teacher, lesson_kind="lab")
        self.lesson_post(self.teacher, lesson_date=(self.lesson.date - timedelta(days=1)).isoformat())
        self.lesson.refresh_from_db()
        self.assertEqual((self.lesson.kind, self.lesson.date), ("seminar", TODAY() - timedelta(days=3)))
        self.lesson_post(self.teacher, lesson_topic="Düzgün mövzu")
        self.lesson.refresh_from_db()
        self.assertEqual(self.lesson.topic, "Düzgün mövzu")
        self.assertIsNotNone(self.mark())

    def test_teacher_may_rekind_lesson_whose_marks_are_still_open(self):
        self.write(minutes=5)
        self.lesson_post(self.teacher, lesson_kind="lab")
        self.lesson.refresh_from_db()
        self.assertEqual(self.lesson.kind, "lab")

    def test_rim_deletes_lesson_with_locked_marks(self):
        self.write(minutes=60 * 25)
        self.lesson_post(self.rim, do_delete="1")
        with bypass_rls():
            self.assertFalse(Lesson.objects.filter(pk=self.lesson.pk).exists())

    # ── profilə baxış ────────────────────────────────────────────────────

    def test_view_as_cannot_write_journal(self):
        client = self.client_for(self.owner)
        start = client.post(reverse("accounts:view_as_start"), {"user_id": self.teacher.pk, "org": self.org.pk})
        self.assertEqual(start.status_code, 302)
        page = client.get(self.url())
        self.assertNotIn("data-jd-fe-banner", page.content.decode())
        resp = client.post(
            self.url(),
            {"action": "save_marks", "autosave": "1", f"att__{self.lesson.id}__{self.enrollment.id}": "absent"},
        )
        self.assertIn(resp.status_code, (302, 403))
        self.assertIsNone(self.mark())
