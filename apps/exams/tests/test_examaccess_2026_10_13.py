"""Gecə auditi 2026-10-13 (examaccess) — final/midterm giriş zənciri regresiyaları.

Sahibin sözü: «qrupa ya da fərdi imtahan təyin etmə, pin kodun görünməsi, onu götürüb imtahanı
başlatma ... ancaq universitet şəbəkəsinə qoşulu olarkən ... MAC ünvan ... tələbəyə yeni pin
verilməsi, bir kompdan qalxıb digər kompa keçərkən yeni pin veriləndə olduğu yerdən davam
etməsi, köhnə pin etibarsızlığı ... bir gündə ancaq 1 fəndən imtahan».

* ``NetworkGateTests`` — final/midterm yalnız daxili zonadan (``EXAM_FINAL_INTERNAL_ONLY``):
  start, kabinet kod yolu, ``/exams/final/``, take səhifəsi, autosave, heartbeat; ayar sönük /
  quiz / sınaq cəhdi azaddır; etibarlı ``X-EMS-Zone`` başlığı.
* ``CabinetPinReentryTests`` — kabinet (fərdi) PIN-i ilə başqa kompüterdən davam artıq mümkün
  DEYİL (əvvəl giriş cəhdin kompüterini köçürürdü və cihaz qapısı «eyni zal kompüteri» sayırdı);
  nəzarətçinin yeni PIN-i ilə eyni cəhd, eyni cavablar, eyni taymer davam edir; köhnə PIN və
  köhnə kompüterin sessiyası dərhal etibarsızdır.
* ``OfficialDayRuleTests`` — bilet axını da «gündə bir final» qaydasına tabedir; yoxlama
  tələbə sətri kilidi altındadır.
* ``SubgroupPinProvisionTests`` — ana qrupa təyin olunmuş final/midterm alt qrup tələbəsinə də
  PIN verir; sonradan qrupa düşən tələbənin PIN-i kabinetdə yaradılır.
"""

from __future__ import annotations

import json
from datetime import timedelta

from django.contrib.auth.hashers import make_password
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import pgettext

from apps.accounts.models import ProfileRole
from apps.audit.models import AuditLog
from apps.exams.domain.final_center import (
    ROOM_SESSION_STATE_ACTIVE,
    TICKET_STATUS_ACTIVE,
    TICKET_STATUS_ASSIGNED,
    TICKET_STATUS_WAITING,
)
from apps.exams.models import (
    ExamAnswer,
    ExamAttempt,
    ExamRoom,
    ExamRoomComputer,
    ExamRoomSession,
    ExamStudentPin,
    FinalAttemptDevice,
    FinalExamTicket,
    StudentExamAttemptGrant,
)
from apps.exams.services.final_center import (
    TicketStateError,
    begin_attempt_for_ticket,
    enter_waiting,
    start_room,
)
from apps.exams.services.final_center.pins import _fernet
from apps.exams.services.final_center.reentry import REASON_OTHER_COMPUTER, REASON_STALE_PIN
from apps.exams.services.official_start import OfficialStartBlocked
from apps.exams.tests.option_token_utils import option_value
from apps.exams.tests.test_audit_2026_09_13_exam_integrity import (
    LOCMEM_CACHE,
    PASSWORD,
    User,
    _make_people,
    _make_quiz,
    _student_client,
)
from apps.exams.tests.test_exam_center_policy import _assign_user_to_org
from apps.exams.tests.test_subgroup_exam_assignment import _SubgroupFixture

INTERNAL_IP = "10.20.30.41"
EXTERNAL_IP = "85.132.9.9"
NETWORK_ON = {
    "EXAM_FINAL_INTERNAL_ONLY": True,
    "INTERNAL_NETWORKS": ["10.0.0.0/8"],
    "NETWORK_ZONE_TRUST_HEADER": False,
}


def _make_official(org, teacher, title, kind="final", n_questions=2):
    exam = _make_quiz(org, teacher, n_questions=n_questions, title=title)
    exam.exam_type_extended = kind
    exam.save(update_fields=["exam_type_extended"])
    return exam


def _set_student_pin(exam, student, raw_pin):
    """Siqnalın yaratdığı təsadüfi PIN-i bilinən dəyərlə əvəz et (sətir unikaldır)."""
    values = {"pin_hash": make_password(raw_pin), "pin_cipher": _fernet().encrypt(raw_pin.encode()).decode()}
    row, _ = ExamStudentPin.objects.update_or_create(exam=exam, student=student, defaults=values)
    return row


# ─────────────────────────────────────────────────────────────────────────────
# 3. Şəbəkə qapısı
# ─────────────────────────────────────────────────────────────────────────────


@override_settings(CACHES=LOCMEM_CACHE, **NETWORK_ON)
class NetworkGateTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org, cls.teacher, cls.student = _make_people("nw1013")
        cls.final = _make_official(cls.org, cls.teacher, "NW1013 Final")
        cls.midterm = _make_official(cls.org, cls.teacher, "NW1013 Midterm", kind="midterm")
        cls.quiz = _make_quiz(cls.org, cls.teacher, n_questions=1, title="NW1013 Quiz")
        # 2026-10-21 sərt zal rejimi: daxili şəbəkədəki giriş səhifəsi yalnız qeydli zal kompüterindən açılır.
        room = ExamRoom.objects.create(organization=cls.org, name="NW Zal", code="NWZ", capacity=10)
        ExamRoomComputer.objects.create(
            organization=cls.org, room=room, label="PC-1", seat_number=1, mac_address="AA:BB:CC:13:10:01",
            ip_address=INTERNAL_IP,
        )  # fmt: skip

    def setUp(self):
        from django.core.cache import cache

        cache.clear()  # audit throttle açarı (istifadəçi×imtahan) testlər arasında daşınmasın
        self.client = _student_client("nw1013_student", self.org)

    def _attempt(self, exam, **extra):
        attempt = ExamAttempt.objects.create(user=self.student, exam=exam, status="in_progress", **extra)
        for question in exam.questions.order_by("order"):
            ExamAnswer.objects.create(attempt=attempt, question=question)
        return attempt

    def _autosave(self, attempt, ip):
        question = attempt.exam.questions.order_by("order").first()
        return self.client.post(
            reverse("exams:take_exam", kwargs={"slug": attempt.exam.slug, "attempt_id": attempt.id}),
            {
                "submit_action": "autosave",
                "changed_questions[]": [str(question.id)],
                f"q_{question.id}": option_value(attempt, question.options.get(label="A")),
                "marked_question_ids": "[]",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            REMOTE_ADDR=ip,
        )

    def test_start_exam_for_midterm_and_final_is_refused_from_external_network(self):
        for exam in (self.midterm, self.final):
            response = self.client.get(reverse("exams:start_exam", kwargs={"slug": exam.slug}), REMOTE_ADDR=EXTERNAL_IP)
            self.assertEqual(response.status_code, 403, exam.title)
            self.assertTemplateUsed(response, "exams/student/exam_network_blocked.html")
            self.assertContains(response, "universitet şəbəkəsindən", status_code=403)
        self.assertFalse(ExamAttempt.objects.filter(user=self.student).exists())
        denial = AuditLog.objects.filter(reason__startswith="exam_network_external")
        self.assertTrue(denial.exists())
        self.assertEqual(denial.first().action, "deny")

    def test_cabinet_pin_path_for_midterm_is_refused_from_external_network_before_pin_check(self):
        _set_student_pin(self.midterm, self.student, "11223344")
        response = self.client.post(
            reverse("exams:exam_code_check"),
            {"exam_slug": self.midterm.slug, "access_code": "11223344"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            REMOTE_ADDR=EXTERNAL_IP,
        )
        self.assertEqual(response.status_code, 403)
        self.assertIn("universitet şəbəkəsindən", response.json()["error"])
        self.assertFalse(ExamAttempt.objects.filter(user=self.student, exam=self.midterm).exists())

    def test_cabinet_pin_path_for_midterm_works_from_internal_network(self):
        self.midterm.allowed_users.add(self.student)
        self.midterm.is_public = False
        self.midterm.save(update_fields=["is_public"])
        _set_student_pin(self.midterm, self.student, "11223344")
        response = self.client.post(
            reverse("exams:exam_code_check"),
            {"exam_slug": self.midterm.slug, "access_code": "11223344"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            REMOTE_ADDR=INTERNAL_IP,
        )
        self.assertEqual(response.status_code, 200, response.content[:300])
        self.assertTrue(ExamAttempt.objects.filter(user=self.student, exam=self.midterm).exists())

    def test_final_entry_page_is_internal_only(self):
        anonymous = Client()
        blocked = anonymous.get(reverse("exams:final_exam_entry"), REMOTE_ADDR=EXTERNAL_IP)
        self.assertEqual(blocked.status_code, 403)
        self.assertTemplateUsed(blocked, "exams/student/exam_network_blocked.html")
        login = anonymous.post(
            reverse("exams:final_exam_entry"), {"username": "nw1013_student", "pin": "1"}, REMOTE_ADDR=EXTERNAL_IP
        )
        self.assertEqual(login.status_code, 403)
        self.assertNotIn("_auth_user_id", anonymous.session)
        self.assertEqual(anonymous.get(reverse("exams:final_exam_entry"), REMOTE_ADDR=INTERNAL_IP).status_code, 200)

    def test_running_final_attempt_cannot_be_opened_or_written_from_external_network(self):
        attempt = self._attempt(self.final)
        take_url = reverse("exams:take_exam", kwargs={"slug": self.final.slug, "attempt_id": attempt.id})

        page = self.client.get(take_url, REMOTE_ADDR=EXTERNAL_IP)
        self.assertEqual(page.status_code, 403)
        self.assertNotContains(page, "Sual 1", status_code=403)
        autosave = self._autosave(attempt, EXTERNAL_IP)
        self.assertEqual(autosave.status_code, 403)
        self.assertTrue(autosave.json()["network_blocked"])
        first = ExamAnswer.objects.filter(attempt=attempt).order_by("question__order").first()
        self.assertIsNone(first.selected_option_ids_snapshot)

        # Daxili şəbəkədən eyni cəhd qaldığı yerdən işləyir.
        self.assertEqual(self.client.get(take_url, REMOTE_ADDR=INTERNAL_IP).status_code, 200)
        self.assertEqual(self._autosave(attempt, INTERNAL_IP).status_code, 200)

    def test_supervision_heartbeat_is_refused_from_external_network(self):
        attempt = self._attempt(self.midterm)
        url = reverse("exams:supervision_heartbeat", kwargs={"attempt_id": attempt.id})
        with self.settings(EXAM_SUPERVISION_ENABLED=True):
            from apps.exams.models import ExamSupervisionConfig

            ExamSupervisionConfig.objects.update_or_create(exam=self.midterm, defaults={"enabled": True})
            response = self.client.post(
                url, data=json.dumps({"state": {}}), content_type="application/json", REMOTE_ADDR=EXTERNAL_IP
            )
            self.assertEqual(response.status_code, 403)
            self.assertTrue(response.json()["network_blocked"])
            ok = self.client.post(
                url, data=json.dumps({"state": {}}), content_type="application/json", REMOTE_ADDR=INTERNAL_IP
            )
            self.assertEqual(ok.status_code, 200, ok.content[:200])

    def test_quiz_and_trial_attempts_are_not_restricted(self):
        quiz_attempt = self._attempt(self.quiz)
        url = reverse("exams:take_exam", kwargs={"slug": self.quiz.slug, "attempt_id": quiz_attempt.id})
        self.assertEqual(self.client.get(url, REMOTE_ADDR=EXTERNAL_IP).status_code, 200)

        author = _student_client("nw1013_teacher", self.org)
        trial = ExamAttempt.objects.create(user=self.teacher, exam=self.final, status="in_progress", is_trial=True)
        ExamAnswer.objects.create(attempt=trial, question=self.final.questions.order_by("order").first())
        trial_url = reverse("exams:take_exam", kwargs={"slug": self.final.slug, "attempt_id": trial.id})
        self.assertEqual(author.get(trial_url, REMOTE_ADDR=EXTERNAL_IP).status_code, 200)

    def test_trusted_zone_header_decides_when_enabled(self):
        attempt = self._attempt(self.final)
        url = reverse("exams:take_exam", kwargs={"slug": self.final.slug, "attempt_id": attempt.id})
        with self.settings(NETWORK_ZONE_TRUST_HEADER=True):
            self.assertEqual(self.client.get(url, REMOTE_ADDR=INTERNAL_IP, HTTP_X_EMS_ZONE="external").status_code, 403)
        # Başlığa etibar yoxdursa müştərinin yazdığı «internal» kənar IP-ni daxili etmir.
        self.assertEqual(self.client.get(url, REMOTE_ADDR=EXTERNAL_IP, HTTP_X_EMS_ZONE="internal").status_code, 403)

    # 2026-10-21: sərt zal qapısı da (qeydsiz kompüter → 403) ayrıca açardır — «əvvəlki davranış» ikisi də sönülüdür.
    @override_settings(EXAM_FINAL_INTERNAL_ONLY=False, EXAM_HALL_COMPUTER_CHECK=False)
    def test_setting_off_keeps_previous_behaviour(self):
        attempt = self._attempt(self.final)
        url = reverse("exams:take_exam", kwargs={"slug": self.final.slug, "attempt_id": attempt.id})
        self.assertEqual(self.client.get(url, REMOTE_ADDR=EXTERNAL_IP).status_code, 200)


# ─────────────────────────────────────────────────────────────────────────────
# 5. Kompüter dəyişməsi: yeni PIN, eyni cəhd, köhnə PIN etibarsız
# ─────────────────────────────────────────────────────────────────────────────

CABINET_PIN = "48151623"
PC1_IP = "10.1.1.1"
PC2_IP = "10.1.1.2"


@override_settings(CACHES=LOCMEM_CACHE)
class CabinetPinReentryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org, cls.teacher, cls.student = _make_people("re1013")
        cls.center = User.objects.create_user("re1013_center", "re1013_center@test.az", PASSWORD)
        _assign_user_to_org(cls.center, cls.org, ProfileRole.MEMBER, "exam_center_head")
        cls.exam = _make_official(cls.org, cls.teacher, "RE1013 Final")
        cls.exam.is_public = False
        cls.exam.save(update_fields=["is_public"])
        cls.exam.allowed_users.add(cls.student)
        cls.room = ExamRoom.objects.create(organization=cls.org, name="Zal 1013", code="Z1013", capacity=10)
        cls.pc1 = ExamRoomComputer.objects.create(
            organization=cls.org,
            room=cls.room,
            label="PC-1",
            seat_number=1,
            mac_address="AA:BB:CC:00:10:01",
            ip_address=PC1_IP,
        )
        cls.pc2 = ExamRoomComputer.objects.create(
            organization=cls.org,
            room=cls.room,
            label="PC-2",
            seat_number=2,
            mac_address="AA:BB:CC:00:10:02",
            ip_address=PC2_IP,
        )

    def setUp(self):
        _set_student_pin(self.exam, self.student, CABINET_PIN)

    # ── köməkçilər ──────────────────────────────────────────────────────────

    def _login(self, ip, pin=CABINET_PIN, client=None):
        client = client or Client()
        response = client.post(
            reverse("exams:final_exam_entry"), {"username": self.student.username, "pin": pin}, REMOTE_ADDR=ip
        )
        return client, response

    def _start_at_pc1(self):
        client, response = self._login(PC1_IP)
        self.assertEqual(response.status_code, 302, getattr(response, "content", b"")[:300])
        confirm = client.post(
            reverse("exams:final_exam_entry"),
            {"action": "confirm", "accept_rules": "1", "language": ""},
            REMOTE_ADDR=PC1_IP,
        )
        self.assertEqual(confirm.status_code, 302)
        ticket = FinalExamTicket.objects.get(exam=self.exam, student=self.student)
        start_room(ticket.session, self.center)
        begin = client.post(reverse("exams:final_exam_begin", args=[ticket.pk]), REMOTE_ADDR=PC1_IP)
        self.assertEqual(begin.status_code, 200, begin.content[:300])
        ticket.refresh_from_db()
        attempt = ticket.attempt
        self.take_url = reverse("exams:take_exam", kwargs={"slug": self.exam.slug, "attempt_id": attempt.id})
        self.assertEqual(client.get(self.take_url, REMOTE_ADDR=PC1_IP).status_code, 200)  # cihaz bağlanır
        return client, ticket, attempt

    def _autosave(self, client, attempt, ip):
        question = attempt.answers.order_by("question__order").first().question
        return client.post(
            self.take_url,
            {
                "submit_action": "autosave",
                "changed_questions[]": [str(question.id)],
                f"q_{question.id}": option_value(attempt, question.options.get(label="A")),
                "marked_question_ids": "[]",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            REMOTE_ADDR=ip,
        )

    def _reentry_pin(self, ticket):
        center = Client()
        center.force_login(self.center)
        session = center.session
        session["active_organization"] = self.org.slug
        session.save()
        response = center.post(
            reverse(
                "exams:exam_center_ticket_reentry", kwargs={"session_id": ticket.session_id, "ticket_id": ticket.pk}
            ),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200, response.content[:300])
        return response.json()["pin"]

    # ── testlər ─────────────────────────────────────────────────────────────

    def test_cabinet_pin_on_another_computer_is_refused_and_does_not_move_the_attempt(self):
        pc1, ticket, attempt = self._start_at_pc1()

        _client, response = self._login(PC2_IP)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "başqa kompüterdə davam edir")
        attempt.refresh_from_db()
        self.assertEqual(attempt.room_computer_id, self.pc1.pk, "cəhd yerindən tərpənməməlidir")
        self.assertTrue(AuditLog.objects.filter(reason=REASON_OTHER_COMPUTER, object_id=str(ticket.pk)).exists())
        # Köhnə (qanuni) kompüterin sessiyası toxunulmaz qalır.
        self.assertEqual(self._autosave(pc1, attempt, PC1_IP).status_code, 200)

    def test_cabinet_pin_on_the_same_computer_resumes_after_a_browser_crash(self):
        _pc1, _ticket, attempt = self._start_at_pc1()

        restarted, response = self._login(PC1_IP)  # yeni brauzer, cookie yoxdur

        self.assertEqual(response.status_code, 302)
        follow = restarted.get(reverse("exams:final_exam_entry"), REMOTE_ADDR=PC1_IP)
        self.assertEqual(follow.status_code, 302)
        self.assertIn(f"/attempt/{attempt.pk}/", follow["Location"])
        self.assertEqual(restarted.get(self.take_url, REMOTE_ADDR=PC1_IP).status_code, 200)

    def test_new_pin_moves_the_same_attempt_and_invalidates_the_old_pin_and_old_computer(self):
        pc1, ticket, attempt = self._start_at_pc1()
        self.assertEqual(self._autosave(pc1, attempt, PC1_IP).status_code, 200)
        started_at = attempt.started_at
        answered = attempt.answers.order_by("question__order").first()
        answered.refresh_from_db()
        saved_snapshot = answered.selected_option_ids_snapshot
        self.assertTrue(saved_snapshot)

        new_pin = self._reentry_pin(ticket)

        # Köhnə kompüterin tabı növbəti sorğuda dayanır (yazı + səhifə).
        self.assertEqual(self._autosave(pc1, attempt, PC1_IP).status_code, 403)
        # Köhnə kabinet PIN-i heç bir kompüterdə işləmir.
        for ip in (PC1_IP, PC2_IP):
            _c, refused = self._login(ip)
            self.assertEqual(refused.status_code, 200)
            self.assertContains(refused, "köhnə PIN artıq etibarsızdır")
        self.assertEqual(AuditLog.objects.filter(reason=REASON_STALE_PIN, object_id=str(ticket.pk)).count(), 2)

        # Yeni PIN → eyni cəhd, eyni cavablar, taymer sıfırlanmır.
        pc2, response = self._login(PC2_IP, pin=new_pin)
        self.assertEqual(response.status_code, 302)
        route = pc2.get(reverse("exams:final_exam_entry"), REMOTE_ADDR=PC2_IP)
        self.assertIn(f"/attempt/{attempt.pk}/", route["Location"])
        page = pc2.get(self.take_url, REMOTE_ADDR=PC2_IP)
        self.assertEqual(page.status_code, 200)
        restored = page.context["answers_by_qid"][answered.question_id]
        self.assertTrue(restored["selected_option_ids"])

        attempt.refresh_from_db()
        self.assertEqual(attempt.started_at, started_at)
        self.assertEqual(attempt.status, "in_progress")
        self.assertEqual(attempt.room_computer_id, self.pc2.pk)
        self.assertEqual(ExamAttempt.objects.filter(user=self.student, exam=self.exam).count(), 1)
        binding = FinalAttemptDevice.objects.get(attempt=attempt)
        self.assertIsNone(binding.change_approved_at, "təsdiq köçürmədə sərf olunmalıdır")

        # Yeni PIN birdəfəlikdir; köhnə kompüter cəhdi aça bilmir.
        _dup, duplicate = self._login(PC1_IP, pin=new_pin)
        self.assertEqual(duplicate.status_code, 200)
        self.assertEqual(pc1.get(self.take_url, REMOTE_ADDR=PC1_IP).status_code, 302)

        reasons = set(AuditLog.objects.filter(object_id=str(ticket.pk)).values_list("reason", flat=True))
        self.assertIn("final_reentry_pin_issued", reasons)
        self.assertIn("final_pin_regenerated", reasons)


# ─────────────────────────────────────────────────────────────────────────────
# 6. Gündə bir final
# ─────────────────────────────────────────────────────────────────────────────


@override_settings(CACHES=LOCMEM_CACHE)
class OfficialDayRuleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org, cls.teacher, cls.student = _make_people("dr1013")
        cls.final_a = _make_official(cls.org, cls.teacher, "DR1013 Final A")
        cls.final_b = _make_official(cls.org, cls.teacher, "DR1013 Final B")
        cls.midterm = _make_official(cls.org, cls.teacher, "DR1013 Midterm", kind="midterm")
        cls.quiz = _make_quiz(cls.org, cls.teacher, n_questions=1, title="DR1013 Quiz")
        cls.room = ExamRoom.objects.create(organization=cls.org, name="Zal DR", code="ZDR", capacity=10)

    def _finish_today(self, exam):
        # Gecə yarısı sərhədi (CI 00:29 Bakı): «30 dəq əvvəl» dünənə düşməsin — Bakı gününün içində qalır.
        now = timezone.now()
        day_start = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
        finished_at = now - min(timedelta(minutes=30), (now - day_start) / 2)
        return ExamAttempt.objects.create(user=self.student, exam=exam, status="submitted", finished_at=finished_at)

    def _ticket(self, exam, status=TICKET_STATUS_WAITING):
        now = timezone.now()
        session = ExamRoomSession.objects.create(
            organization=self.org,
            room=self.room,
            state=ROOM_SESSION_STATE_ACTIVE,
            scheduled_start=now - timedelta(minutes=5),
            scheduled_end=now + timedelta(hours=2),
        )
        return FinalExamTicket.objects.create(
            organization=self.org, session=session, exam=exam, student=self.student, status=status
        )

    def test_ticket_flow_refuses_a_second_final_on_the_same_day(self):
        self._finish_today(self.final_a)
        ticket = self._ticket(self.final_b)

        with self.assertRaises(TicketStateError) as ctx:
            begin_attempt_for_ticket(ticket)

        self.assertEqual(str(ctx.exception), pgettext("exams.model.access", "already_examined_today"))
        self.assertFalse(ExamAttempt.objects.filter(user=self.student, exam=self.final_b).exists())
        ticket.refresh_from_db()
        self.assertEqual(ticket.status, TICKET_STATUS_WAITING)

    def test_waiting_room_entry_explains_the_rule_early(self):
        self._finish_today(self.final_a)
        ticket = self._ticket(self.final_b, status=TICKET_STATUS_ASSIGNED)
        ExamRoomSession.objects.filter(pk=ticket.session_id).update(state="entry_open")
        ticket.refresh_from_db()
        with self.assertRaises(TicketStateError):
            enter_waiting(ticket, language="")

    def test_exam_center_second_chance_grant_is_the_audited_override(self):
        self._finish_today(self.final_a)
        StudentExamAttemptGrant.objects.create(exam=self.final_b, student=self.student, extra_attempts=1)
        attempt = begin_attempt_for_ticket(self._ticket(self.final_b))
        self.assertEqual(attempt.exam_id, self.final_b.pk)

    def test_create_path_checks_the_rule_under_a_student_row_lock(self):
        from apps.exams.services.attempts import _create_attempt_or_get_active

        self._finish_today(self.final_a)
        with CaptureQueriesContext(connection) as ctx, self.assertRaises(OfficialStartBlocked):
            _create_attempt_or_get_active(self.final_b, self.student)
        locks = [q["sql"] for q in ctx.captured_queries if "FOR UPDATE" in q["sql"] and "auth_user" in q["sql"]]
        self.assertEqual(len(locks), 1, locks)

        # Midterm də «rəsmi» sayılır (2026-07 qaydası: gündə bir final/midterm).
        with self.assertRaises(OfficialStartBlocked):
            _create_attempt_or_get_active(self.midterm, self.student)

        # Quiz və sınaq cəhdi toxunulmur — kilid də alınmır.
        with CaptureQueriesContext(connection) as quiz_ctx:
            attempt, created = _create_attempt_or_get_active(self.quiz, self.student)
        self.assertTrue(created)
        self.assertFalse(any("FOR UPDATE" in q["sql"] and "auth_user" in q["sql"] for q in quiz_ctx.captured_queries))

    def test_other_final_in_progress_blocks_a_parallel_start(self):
        from apps.exams.services.attempts import _create_attempt_or_get_active

        ExamAttempt.objects.create(user=self.student, exam=self.final_a, status="in_progress")
        with self.assertRaises(OfficialStartBlocked):
            _create_attempt_or_get_active(self.final_b, self.student)

    def test_continuation_of_the_same_final_is_not_blocked(self):
        attempt = ExamAttempt.objects.create(user=self.student, exam=self.final_a, status="in_progress")
        ticket = self._ticket(self.final_a, status=TICKET_STATUS_ACTIVE)
        ticket.attempt = attempt
        ticket.save(update_fields=["attempt"])
        self.assertEqual(begin_attempt_for_ticket(ticket).pk, attempt.pk)


# ─────────────────────────────────────────────────────────────────────────────
# 1. Təyinat: alt qrup + sonradan qrupa düşən tələbə
# ─────────────────────────────────────────────────────────────────────────────


class SubgroupPinProvisionTests(_SubgroupFixture):
    def test_parent_group_assignment_gives_subgroup_students_a_pin(self):
        exam = self._exam(exam_type_extended="midterm", title="W4U Midterm")
        exam.allowed_units.add(self.parent_group)  # m2m siqnalı PIN-ləri provizion edir
        self.assertTrue(ExamStudentPin.objects.filter(exam=exam, student=self.sub_student).exists())
        self.assertFalse(ExamStudentPin.objects.filter(exam=exam, student=self.student).exists())

    def test_cabinet_creates_a_missing_pin_for_a_late_joiner(self):
        from apps.exams.services.student_pins import student_visible_pin

        exam = self._exam(exam_type_extended="final", title="W4U Final")
        exam.allowed_units.add(self.parent_group)
        ExamStudentPin.objects.filter(exam=exam, student=self.sub_student).delete()  # «sonradan gəlib»

        self.assertIsNone(student_visible_pin(exam, self.sub_student))
        pin = student_visible_pin(exam, self.sub_student, provision_missing=True)

        self.assertTrue(pin and pin.isdigit())
        self.assertEqual(student_visible_pin(exam, self.sub_student), pin, "PIN sabit qalmalıdır")
