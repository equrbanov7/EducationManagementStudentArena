"""2026-10-13 (gecə) — vaxtla məhdud nəzarətçi növbəsi, monitor keşi/ETag, nəzarətçi qeydi,
eyni-anda-iki-səhifə / IP dəyişməsi siqnalları və sual sırasının qarışdırılması.

Sahib: «nəzarətçinin təyin olunması, təyin olunandan sonra onun da müəyyən accessləri
olması kabinetində, amma imtahan sessiyası ya da gün bitəndə onun itməsi».
"""

from datetime import datetime, time, timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.audit.models import AuditLog
from apps.exams.models import (
    Exam,
    ExamAttempt,
    ExamQuestion,
    ExamQuestionOption,
    ExamRoom,
    ExamRoomSession,
    ExamSupervisionConfig,
    InvigilatorDuty,
    ProctoringLog,
)
from apps.exams.services.final_center import supervision_scope, user_supervises_final_sessions
from apps.exams.services.final_center.duties import (
    BAKU_TZ,
    DUTY_STATUS_ACTIVE,
    DUTY_STATUS_EXPIRED,
    DUTY_STATUS_REVOKED,
    DUTY_STATUS_UPCOMING,
    duty_status,
)
from apps.exams.services.final_center.duty_admin import DutyError, parse_duty_window
from apps.exams.services.supervision.heartbeat import _cache as heartbeat_cache
from apps.exams.services.supervision.heartbeat import record_heartbeat
from apps.exams.services.supervision.risk import attempts_risk
from apps.exams.tests.test_exam_center_policy import PASSWORD, _assign_user_to_org
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


def _baku_noon(days=0):
    """Bu gün (Bakı) 12:00 — gün sərhədinə düşməyən sabit an."""
    today = timezone.now().astimezone(BAKU_TZ).date() + timedelta(days=days)
    return datetime.combine(today, time(12, 0), tzinfo=BAKU_TZ)


class _DutyBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("idt_owner", "idt_owner@test.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="IDT University",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        cls.head = User.objects.create_user("idt_head", "idt_head@test.az", PASSWORD)
        _assign_user_to_org(cls.head, cls.org, ProfileRole.MEMBER, "exam_center_head")
        cls.staff = User.objects.create_user("idt_staff", "idt_staff@test.az", PASSWORD)
        _assign_user_to_org(cls.staff, cls.org, ProfileRole.MEMBER, "exam_center_staff")
        cls.invig = User.objects.create_user("idt_invig", "idt_invig@test.az", PASSWORD)
        _assign_user_to_org(cls.invig, cls.org, ProfileRole.TEACHER, "teacher")
        cls.other = User.objects.create_user("idt_other", "idt_other@test.az", PASSWORD)
        _assign_user_to_org(cls.other, cls.org, ProfileRole.TEACHER, "teacher")
        cls.student = User.objects.create_user("idt_student", "idt_student@test.az", PASSWORD)
        _assign_user_to_org(cls.student, cls.org, ProfileRole.STUDENT, "student")
        cls.room = ExamRoom.objects.create(organization=cls.org, name="Zal D", code="ZD", capacity=30)
        cls.room2 = ExamRoom.objects.create(organization=cls.org, name="Zal E", code="ZE", capacity=30)
        cls.exam = Exam.objects.create(
            title="IDT Exam", author=cls.owner, organization=cls.org, exam_type="test", is_active=True
        )

    def setUp(self):
        heartbeat_cache().clear()

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _duty(self, *, user=None, room=None, start=None, minutes=120, **extra):
        start = start or timezone.now()
        return InvigilatorDuty.objects.create(
            organization=self.org,
            room=room or self.room,
            user=user or self.invig,
            starts_at=start,
            ends_at=start + timedelta(minutes=minutes),
            **extra,
        )

    def _live_session(self, room=None, state="active"):
        now = timezone.now()
        return ExamRoomSession.objects.create(
            organization=self.org,
            room=room or self.room,
            scheduled_start=now - timedelta(minutes=10),
            scheduled_end=now + timedelta(hours=1),
            state=state,
            created_by=self.head,
        )


class DutyWindowTests(_DutyBase):
    def test_status_follows_the_window(self):
        start = _baku_noon()
        duty = self._duty(start=start, minutes=90)
        self.assertEqual(duty_status(duty, now=start - timedelta(minutes=31), room_is_live=False), DUTY_STATUS_UPCOMING)
        self.assertEqual(duty_status(duty, now=start - timedelta(minutes=29), room_is_live=False), DUTY_STATUS_ACTIVE)
        self.assertEqual(duty_status(duty, now=start + timedelta(minutes=100), room_is_live=False), DUTY_STATUS_ACTIVE)
        # Son + 15 dəq. keçib, zalda canlı imtahan yoxdur → bağlanır («sessiya bitəndə itsin»).
        late = start + timedelta(minutes=110)
        self.assertEqual(duty_status(duty, now=late, room_is_live=False), DUTY_STATUS_EXPIRED)
        # İmtahan uzanıb (canlı oturum var) → gün sonuna qədər açıq.
        self.assertEqual(duty_status(duty, now=late, room_is_live=True), DUTY_STATUS_ACTIVE)
        # Gün bitdi → canlı oturum olsa belə bağlıdır.
        next_day = start + timedelta(hours=13)
        self.assertEqual(duty_status(duty, now=next_day, room_is_live=True), DUTY_STATUS_EXPIRED)

    def test_revoked_duty_is_closed(self):
        duty = self._duty(revoked_at=timezone.now())
        self.assertEqual(duty_status(duty), DUTY_STATUS_REVOKED)
        self.assertTrue(supervision_scope(self.invig, organization_id=self.org.pk).is_empty)

    def test_scope_and_nav_flag_follow_active_duty(self):
        self.assertFalse(user_supervises_final_sessions(self.invig))
        self._duty(start=timezone.now())
        self.assertTrue(user_supervises_final_sessions(self.invig))
        scope = supervision_scope(self.invig, organization_id=self.org.pk)
        self.assertTrue(scope.allows_room(self.room.pk))
        self.assertFalse(scope.allows_room(self.room2.pk))

    def test_expired_duty_gives_nothing(self):
        # Növbə 1 saat əvvəl bitib (son + 15 dəq. çoxdan keçib), canlı oturum yoxdur. Növbə bir Bakı günü
        # içində qalmalıdır — gecə yarısını kəsirsə hər ikisi bir saat geri çəkilir (CI 00:29 Bakı).
        end = timezone.now() - timedelta(hours=1)
        start = end - timedelta(minutes=30)
        if start.astimezone(BAKU_TZ).date() != end.astimezone(BAKU_TZ).date():
            start -= timedelta(hours=1)
        self._duty(start=start, minutes=30)
        self.assertTrue(supervision_scope(self.invig, organization_id=self.org.pk).is_empty)

    def test_legacy_room_m2m_only_works_while_room_is_live(self):
        self.room.invigilators.add(self.other)
        self.assertTrue(supervision_scope(self.other, organization_id=self.org.pk).is_empty)
        session = self._live_session()
        self.assertTrue(supervision_scope(self.other, organization_id=self.org.pk).allows_room(self.room.pk))
        session.state = "ended"
        session.save(update_fields=["state"])
        self.assertTrue(supervision_scope(self.other, organization_id=self.org.pk).is_empty)

    def test_parse_window_rejects_bad_input(self):
        today = timezone.now().astimezone(BAKU_TZ).date()
        with self.assertRaises(DutyError):
            parse_duty_window((today - timedelta(days=1)).isoformat(), "09:00", "12:00")
        with self.assertRaises(DutyError):
            parse_duty_window((today + timedelta(days=1)).isoformat(), "12:00", "09:00")
        with self.assertRaises(DutyError):
            parse_duty_window((today + timedelta(days=365)).isoformat(), "09:00", "12:00")
        with self.assertRaises(DutyError):
            parse_duty_window("not-a-date", "09:00", "12:00")
        starts, ends = parse_duty_window((today + timedelta(days=1)).isoformat(), "09:00", "12:30")
        self.assertEqual(starts.astimezone(BAKU_TZ).hour, 9)
        self.assertEqual((ends - starts), timedelta(hours=3, minutes=30))


class DutyEnforcementTests(_DutyBase):
    def test_room_monitor_and_snapshot_need_active_duty(self):
        monitor = reverse("exams:exam_center_room_monitor", args=[self.room.pk])
        snapshot = reverse("exams:exam_center_room_snapshot", args=[self.room.pk])
        client = self._client(self.invig)
        self.assertEqual(client.get(monitor).status_code, 403)
        duty = self._duty()
        response = client.get(monitor)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "fxc-duty-strip")
        self.assertEqual(client.get(snapshot).status_code, 200)
        # Rəhbər ləğv etdi → növbəti sorğu DƏRHAL 403 (polling dayanır).
        duty.revoked_at = timezone.now()
        duty.save(update_fields=["revoked_at"])
        self.assertEqual(client.get(snapshot).status_code, 403)

    def test_duty_in_one_room_does_not_open_another(self):
        self._duty(room=self.room)
        client = self._client(self.invig)
        self.assertEqual(client.get(reverse("exams:exam_center_room_monitor", args=[self.room2.pk])).status_code, 403)
        self.assertEqual(client.get(reverse("exams:exam_center_room_snapshot", args=[self.room2.pk])).status_code, 403)

    def test_room_list_shows_only_duty_rooms_with_strip(self):
        self._duty(room=self.room)
        response = self._client(self.invig).get(reverse("exams:exam_center_room_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Zal D")
        self.assertNotContains(response, "Zal E")
        self.assertEqual(len(response.context["my_duties"]), 1)

    def test_snapshot_etag_returns_304_when_unchanged(self):
        client = self._client(self.head)
        url = reverse("exams:exam_center_room_snapshot", args=[self.room.pk])
        first = client.get(url)
        self.assertEqual(first.status_code, 200)
        etag = first["ETag"]
        self.assertTrue(etag)
        second = client.get(url, HTTP_IF_NONE_MATCH=etag)
        self.assertEqual(second.status_code, 304)
        self.assertEqual(second.content, b"")
        fresh = client.get(url + "?fresh=1")
        self.assertEqual(fresh.status_code, 200)


class DutyAdminEndpointTests(_DutyBase):
    def _form(self, **extra):
        tomorrow = (timezone.now().astimezone(BAKU_TZ).date() + timedelta(days=1)).isoformat()
        data = {"duty_date": tomorrow, "start_time": "09:00", "end_time": "12:00", "invigilators": [self.invig.pk]}
        data.update(extra)
        return data

    def test_head_creates_duty_with_audit(self):
        url = reverse("exams:exam_center_room_duty_create", args=[self.room.pk])
        response = self._client(self.head).post(url, self._form())
        self.assertEqual(response.status_code, 302)
        duty = InvigilatorDuty.objects.get(room=self.room, user=self.invig)
        self.assertEqual(duty.assigned_by, self.head)
        self.assertTrue(
            AuditLog.objects.filter(reason="final_room_invigilator_duty_created", resource_id=str(duty.pk)).exists()
        )
        # Təkrar POST (idempotent) ikinci sətir yaratmır.
        self._client(self.head).post(url, self._form())
        self.assertEqual(InvigilatorDuty.objects.filter(room=self.room, user=self.invig).count(), 1)

    def test_staff_and_teacher_cannot_assign(self):
        url = reverse("exams:exam_center_room_duty_create", args=[self.room.pk])
        self._duty(user=self.other)  # müəllim-nəzarətçi səthə girə bilir, amma təyin edə bilməz
        self.assertEqual(self._client(self.staff).post(url, self._form()).status_code, 403)
        self.assertEqual(self._client(self.other).post(url, self._form()).status_code, 403)
        self.assertFalse(InvigilatorDuty.objects.filter(user=self.invig).exists())

    def test_student_cannot_be_invigilator(self):
        url = reverse("exams:exam_center_room_duty_create", args=[self.room.pk])
        self._client(self.head).post(url, self._form(invigilators=[self.student.pk]))
        self.assertFalse(InvigilatorDuty.objects.filter(user=self.student).exists())

    def test_revoke_closes_access(self):
        duty = self._duty()
        url = reverse("exams:exam_center_room_duty_revoke", args=[self.room.pk, duty.pk])
        self.assertEqual(self._client(self.head).post(url).status_code, 302)
        duty.refresh_from_db()
        self.assertIsNotNone(duty.revoked_at)
        self.assertTrue(supervision_scope(self.invig, organization_id=self.org.pk).is_empty)
        self.assertTrue(AuditLog.objects.filter(reason="final_room_invigilator_duty_revoked").exists())

    def test_revoke_other_room_duty_is_404(self):
        duty = self._duty(room=self.room2)
        url = reverse("exams:exam_center_room_duty_revoke", args=[self.room.pk, duty.pk])
        self.assertEqual(self._client(self.head).post(url).status_code, 404)


class InvigilatorNoteTests(_DutyBase):
    def setUp(self):
        super().setUp()
        self.attempt = ExamAttempt.objects.create(user=self.student, exam=self.exam, status="in_progress")
        self.attempt.room = self.room
        self.attempt.save(update_fields=["room"])

    def _url(self, room, attempt):
        return reverse("exams:exam_center_attempt_note", args=[room.pk, attempt.pk])

    def test_duty_invigilator_writes_note_without_raising_risk(self):
        self._duty()
        response = self._client(self.invig).post(self._url(self.room, self.attempt), {"text": "Telefona baxırdı"})
        self.assertEqual(response.status_code, 200)
        log = ProctoringLog.objects.get(exam_attempt=self.attempt)
        self.assertEqual(log.details["kind"], "invigilator_note")
        risk = attempts_risk([self.attempt.pk])[self.attempt.pk]
        self.assertEqual(risk["score"], 0)
        self.assertEqual(risk["signals"], 0)

    def test_note_requires_duty_and_room_scope(self):
        self.assertEqual(
            self._client(self.invig).post(self._url(self.room, self.attempt), {"text": "x"}).status_code, 403
        )
        self._duty(room=self.room2)
        # Başqa zalın növbəsi ilə bu zalın cəhdinə qeyd yazmaq olmaz.
        self.assertEqual(
            self._client(self.invig).post(self._url(self.room, self.attempt), {"text": "x"}).status_code, 403
        )
        # Cəhd həmin zalda deyil → 404.
        self.assertEqual(
            self._client(self.invig).post(self._url(self.room2, self.attempt), {"text": "x"}).status_code, 404
        )


class HeartbeatConcurrencyTests(_DutyBase):
    def test_interleaved_pages_are_concurrent_but_reload_is_not(self):
        attempt_id = 990001
        self.assertFalse(record_heartbeat(attempt_id, {"cid": "pageAAAA01"}, now=1000.0)["concurrent"])
        # Reload: köhnə səhifə susur, yeni səhifə gəlir — səhv-müsbət yoxdur.
        self.assertFalse(record_heartbeat(attempt_id, {"cid": "pageBBBB02"}, now=1010.0)["concurrent"])
        self.assertFalse(record_heartbeat(attempt_id, {"cid": "pageBBBB02"}, now=1040.0)["concurrent"])
        # Köhnə səhifə yenidən danışır (A → B → A) — iki səhifə eyni anda açıqdır.
        self.assertTrue(record_heartbeat(attempt_id, {"cid": "pageAAAA01"}, now=1050.0)["concurrent"])

    def test_ip_change_is_reported(self):
        attempt_id = 990002
        self.assertIsNone(record_heartbeat(attempt_id, {}, now=1.0, ip="10.0.0.5")["ip_change"])
        self.assertIsNone(record_heartbeat(attempt_id, {}, now=31.0, ip="10.0.0.5")["ip_change"])
        self.assertEqual(
            record_heartbeat(attempt_id, {}, now=61.0, ip="10.0.9.9")["ip_change"], ("10.0.0.5", "10.0.9.9")
        )

    def test_heartbeat_api_logs_concurrent_session_signal(self):
        ExamSupervisionConfig.objects.create(exam=self.exam, enabled=True)
        attempt = ExamAttempt.objects.create(user=self.student, exam=self.exam, status="in_progress")
        client = self._client(self.student)
        url = reverse("exams:supervision_heartbeat", args=[attempt.pk])
        # Yalnız heartbeat modulunun saatı (qlobal ``time.time`` deyil — logging/rate-limit toxunulmaz).
        with mock.patch("apps.exams.services.supervision.heartbeat.time") as fake_time:
            fake_time.time.side_effect = [100.0, 110.0, 120.0]
            for cid in ("tabAAAAAAA1", "tabBBBBBBB2", "tabAAAAAAA1"):
                response = client.post(url, data={"state": {"cid": cid}}, content_type="application/json")
                self.assertEqual(response.status_code, 200)
        self.assertTrue(ProctoringLog.objects.filter(exam_attempt=attempt, details__kind="concurrent_session").exists())


class QuestionOrderShuffleTests(_DutyBase):
    def test_all_questions_path_shuffles_order(self):
        from apps.exams.services.randomizer import generate_random_questions_for_attempt

        exam = Exam.objects.create(
            title="IDT Order",
            author=self.owner,
            organization=self.org,
            exam_type="test",
            is_active=True,
            random_question_count=0,
        )
        for index in range(6):
            question = ExamQuestion.objects.create(exam=exam, order=index, text=f"S{index}")
            ExamQuestionOption.objects.create(question=question, label="A", text="a", is_correct=True)
        attempt = ExamAttempt.objects.create(user=self.student, exam=exam, status="in_progress")
        with mock.patch("apps.exams.services.randomizer.random.shuffle", side_effect=lambda seq: seq.reverse()) as shuf:
            generate_random_questions_for_attempt(attempt)
        self.assertTrue(shuf.called)
        self.assertEqual(attempt.answers.count(), 6)
