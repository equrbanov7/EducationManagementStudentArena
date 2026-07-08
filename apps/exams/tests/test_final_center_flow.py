"""
Final imtahan mərkəzi — inteqrasiya + təhlükəsizlik testləri.

Axın: PIN girişi → gate (dil + qaydalar) → gözləmə otağı → sinxron start →
attempt → otaq sonu. Həmçinin: idempotent start/son, tələbə çıxarma,
tenant izolyasiyası və icazə yoxlamaları.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ProfileRole
from apps.exams.domain.final_center import (
    ROOM_SESSION_STATE_ACTIVE,
    ROOM_SESSION_STATE_ENDED,
    TICKET_STATUS_ABSENT,
    TICKET_STATUS_ACTIVE,
    TICKET_STATUS_ASSIGNED,
    TICKET_STATUS_COMPLETED,
    TICKET_STATUS_REMOVED,
    TICKET_STATUS_WAITING,
)
from apps.exams.models import (
    Exam,
    ExamQuestion,
    ExamQuestionOption,
    ExamRoom,
    ExamRoomComputer,
    ExamRoomSession,
    FinalExamTicket,
)
from apps.exams.services.final_center import (
    RoomSessionStateError,
    TicketStateError,
    begin_attempt_for_ticket,
    end_room,
    enter_waiting,
    open_entry,
    remove_student,
    session_monitor_snapshot,
    set_ticket_pin,
    start_room,
    student_cancel_waiting,
    validate_session_plan,
)
from apps.exams.tests.test_exam_center_policy import PASSWORD, _assign_user_to_org
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


class _FlowBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("fcf_owner", "fcf_owner@test.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="FCF University",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        cls.center = User.objects.create_user("fcf_center", "fcf_center@test.az", PASSWORD)
        _assign_user_to_org(cls.center, cls.org, ProfileRole.MEMBER, "exam_center")
        cls.invigilator = User.objects.create_user("fcf_invig", "fcf_invig@test.az", PASSWORD)
        _assign_user_to_org(cls.invigilator, cls.org, ProfileRole.TEACHER, "teacher")
        cls.teacher = User.objects.create_user("fcf_teacher", "fcf_teacher@test.az", PASSWORD)
        _assign_user_to_org(cls.teacher, cls.org, ProfileRole.TEACHER, "teacher")
        cls.student = User.objects.create_user("fcf_student", "fcf_student@test.az", PASSWORD)
        _assign_user_to_org(cls.student, cls.org, ProfileRole.STUDENT, "student")
        cls.student2 = User.objects.create_user("fcf_student2", "fcf_student2@test.az", PASSWORD)
        _assign_user_to_org(cls.student2, cls.org, ProfileRole.STUDENT, "student")

        _now = timezone.now()
        cls.exam = Exam.objects.create(
            title="FCF Final",
            author=cls.center,
            organization=cls.org,
            exam_type="test",
            exam_type_extended="final",
            is_active=True,
            total_duration_minutes=60,
            random_question_count=1,
            start_datetime=_now + timedelta(minutes=5),
            end_datetime=_now + timedelta(hours=2),
        )
        question = ExamQuestion.objects.create(exam=cls.exam, order=1, text="Final sualı")
        ExamQuestionOption.objects.create(question=question, label="A", text="Cavab", is_correct=True)

        cls.room = ExamRoom.objects.create(
            organization=cls.org, name="Zal A", code="ZA", capacity=25, created_by=cls.center
        )
        # Kompüter IP → zal həlli üçün (oturum sisteminin ləğvi): test client IP
        # 127.0.0.1-dir, ona görə zala həmin IP-li kompüter qeyd edilir.
        cls.computer = ExamRoomComputer.objects.create(
            organization=cls.org,
            room=cls.room,
            label="PC-LOCAL",
            seat_number=10,  # test-lərin əlavə etdiyi seat 1 ilə toqquşmasın
            mac_address="AA:BB:CC:DD:EE:0A",
            ip_address="127.0.0.1",
            created_by=cls.center,
        )

    def setUp(self):
        now = timezone.now()
        self.session = ExamRoomSession.objects.create(
            organization=self.org,
            room=self.room,
            invigilator=self.invigilator,
            scheduled_start=now + timedelta(minutes=5),
            scheduled_end=now + timedelta(hours=2),
            created_by=self.center,
        )
        self.ticket = FinalExamTicket.objects.create(
            organization=self.org,
            session=self.session,
            exam=self.exam,
            student=self.student,
        )
        self.raw_pin = set_ticket_pin(self.ticket, self.center)
        open_entry(self.session, self.center)
        self.session.refresh_from_db()

    def tearDown(self):
        # Növbəti test üçün oturum/biletləri təmizlə (unique exam+student).
        FinalExamTicket.objects.all().delete()
        ExamRoomSession.objects.all().delete()

    def _client_for(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _entry_client(self):
        """PIN girişindən keçmiş tələbə client-i."""
        client = Client()
        response = client.post(
            reverse("exams:final_exam_entry"),
            {"username": self.student.username, "pin": self.raw_pin},
        )
        return client, response


class EntryValidationTests(_FlowBase):
    def test_valid_entry_logs_student_in_and_redirects_to_self(self):
        # PRG: uğurlu PIN girişi eyni səhifəyə yönləndirir; modal GET-də açılır.
        client, response = self._entry_client()
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("exams:final_exam_entry"))
        self.assertEqual(int(client.session["_auth_user_id"]), self.student.pk)
        self.assertEqual(client.session["final_exam_ticket_id"], self.ticket.pk)

    def test_modal_shown_on_get_after_pin_validation(self):
        client, _ = self._entry_client()
        response = client.get(reverse("exams:final_exam_entry"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["show_gate_modal"])
        self.assertEqual(response.context["ticket"].pk, self.ticket.pk)
        self.assertContains(response, "İmtahan qaydaları")

    def test_login_page_renders_pin_form_for_anonymous(self):
        response = Client().get(reverse("exams:final_exam_entry"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="pin"', html=False)
        self.assertFalse(response.context["show_gate_modal"])

    def test_wrong_pin_returns_generic_error(self):
        client = Client()
        response = client.post(
            reverse("exams:final_exam_entry"),
            {"username": self.student.username, "pin": "99999999"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", client.session)

    def test_unknown_user_gets_same_generic_error_as_wrong_pin(self):
        """User enumeration qorunması: mövcud olmayan istifadəçi eyni cavabı alır."""
        client = Client()
        response_unknown = client.post(
            reverse("exams:final_exam_entry"),
            {"username": "yoxdur_bele_user", "pin": "12345678"},
        )
        response_wrong = Client().post(
            reverse("exams:final_exam_entry"),
            {"username": self.student.username, "pin": "00000000"},
        )
        self.assertEqual(response_unknown.status_code, 200)
        self.assertEqual(response_wrong.status_code, 200)
        self.assertEqual(
            response_unknown.context["error_message"],
            response_wrong.context["error_message"],
        )

    def test_pin_of_one_student_cannot_be_used_by_another_username(self):
        client = Client()
        response = client.post(
            reverse("exams:final_exam_entry"),
            {"username": self.student2.username, "pin": self.raw_pin},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", client.session)

    def test_entry_rejected_when_no_open_room_sitting(self):
        # Oturum sisteminin ləğvi: PIN yoxlaması zaldan asılı deyil (validate_entry
        # uğur verir), amma zalda AÇIQ oturum yoxdursa view giriş vermir (login
        # olunmur) — tələbə nəzarətçinin oturumu açmasını gözləyir.
        ExamRoomSession.objects.all().delete()
        client = Client()
        response = client.post(
            reverse("exams:final_exam_entry"),
            {"username": self.student.username, "pin": self.raw_pin},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", client.session)

    def test_get_without_pin_validation_shows_login_not_modal(self):
        """PIN yoxlamasından keçməmiş istifadəçi login formunu görür (modal yox)."""
        client = self._client_for(self.student)
        response = client.get(reverse("exams:final_exam_entry"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["show_gate_modal"])

    def test_waiting_of_foreign_ticket_is_404(self):
        client, _ = self._entry_client()
        foreign = FinalExamTicket.objects.create(
            organization=self.org, session=self.session, exam=self.exam, student=self.student2
        )
        response = client.get(reverse("exams:final_exam_waiting", args=[foreign.pk]))
        self.assertEqual(response.status_code, 404)


class _FakeRequest:
    """validate_entry üçün minimal request (rate-limit açarları)."""

    META = {"REMOTE_ADDR": "127.0.0.1"}
    session = {}


class GateAndWaitingTests(_FlowBase):
    def test_modal_confirm_moves_ticket_to_waiting(self):
        client, _ = self._entry_client()
        response = client.post(
            reverse("exams:final_exam_entry"),
            {"action": "confirm", "accept_rules": "1", "language": ""},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("exams:final_exam_waiting", args=[self.ticket.pk]))
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, TICKET_STATUS_WAITING)
        self.assertIsNotNone(self.ticket.rules_accepted_at)

    def test_modal_without_rules_confirmation_stays(self):
        client, _ = self._entry_client()
        response = client.post(reverse("exams:final_exam_entry"), {"action": "confirm", "language": ""})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["show_gate_modal"])
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, TICKET_STATUS_ASSIGNED)


class MultilingualModalTests(_FlowBase):
    """Çoxdilli imtahanda modal dil seçimi məcburidir və seçilən dil saxlanır."""

    def _make_multilingual(self):
        from apps.exams.models import ExamQuestion, ExamQuestionOption
        from apps.exams.services.language_variants import create_variant

        for code in ("az", "en"):
            variant = create_variant(self.exam, code, display_name=code.upper(), is_active=True)
            question = ExamQuestion.objects.create(
                exam=self.exam, language=code, language_variant=variant, order=10, text=f"Q-{code}", is_active=True
            )
            ExamQuestionOption.objects.create(question=question, label="A", text="opt", is_correct=True)

    def test_modal_lists_language_options(self):
        self._make_multilingual()
        client, _ = self._entry_client()
        response = client.get(reverse("exams:final_exam_entry"))
        self.assertEqual(response.status_code, 200)
        codes = {opt["language"] for opt in response.context["language_options"]}
        self.assertEqual(codes, {"az", "en"})
        self.assertContains(response, 'name="language"', html=False)

    def test_confirm_stores_selected_language_and_display(self):
        self._make_multilingual()
        client, _ = self._entry_client()
        response = client.post(
            reverse("exams:final_exam_entry"),
            {"action": "confirm", "accept_rules": "1", "language": "en"},
        )
        self.assertEqual(response.status_code, 302)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, TICKET_STATUS_WAITING)
        self.assertEqual(self.ticket.language, "en")
        # get_language_display düzgün ada həll olunur (choices əlavə edildi).
        self.assertEqual(self.ticket.get_language_display(), "English")

    def test_confirm_without_language_rejected_for_multilingual(self):
        self._make_multilingual()
        client, _ = self._entry_client()
        response = client.post(
            reverse("exams:final_exam_entry"),
            {"action": "confirm", "accept_rules": "1", "language": ""},
        )
        # Dil seçilmədən modal açıq qalır (server tərəfli məcburilik).
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["show_gate_modal"])
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, TICKET_STATUS_ASSIGNED)

    def test_modal_back_logs_out_and_returns_to_login(self):
        client, _ = self._entry_client()
        response = client.post(reverse("exams:final_exam_entry"), {"action": "back"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], reverse("exams:final_exam_entry"))
        self.assertNotIn("_auth_user_id", client.session)
        self.assertNotIn("final_exam_ticket_id", client.session)

    def test_student_cancel_waiting_returns_to_assigned_without_attempt(self):
        enter_waiting(self.ticket, language="")
        self.assertTrue(student_cancel_waiting(self.ticket))
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, TICKET_STATUS_ASSIGNED)
        self.assertIsNone(self.ticket.attempt_id)

    def test_begin_rejected_before_room_start(self):
        enter_waiting(self.ticket, language="")
        with self.assertRaises(TicketStateError):
            begin_attempt_for_ticket(self.ticket)


class RoomLifecycleTests(_FlowBase):
    def test_start_room_is_idempotent(self):
        self.assertTrue(start_room(self.session, self.invigilator))
        self.session.refresh_from_db()
        self.assertEqual(self.session.state, ROOM_SESSION_STATE_ACTIVE)
        self.assertIsNotNone(self.session.started_at)
        # Təkrar start (təkrar klik / ikinci nəzarətçi) təsirsizdir.
        self.assertFalse(start_room(self.session, self.center))

    def test_start_too_early_requires_override(self):
        ExamRoomSession.objects.filter(pk=self.session.pk).update(
            scheduled_start=timezone.now() + timedelta(hours=3),
            scheduled_end=timezone.now() + timedelta(hours=5),
        )
        self.session.refresh_from_db()
        with self.assertRaises(RoomSessionStateError):
            start_room(self.session, self.center)
        self.assertTrue(start_room(self.session, self.center, override=True))

    def test_synchronized_start_then_begin_creates_attempt(self):
        enter_waiting(self.ticket, language="")
        start_room(self.session, self.invigilator)
        self.session.refresh_from_db()
        attempt = begin_attempt_for_ticket(self.ticket)
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, TICKET_STATUS_ACTIVE)
        self.assertEqual(self.ticket.attempt_id, attempt.pk)
        self.assertEqual(attempt.status, "in_progress")
        self.assertTrue(attempt.answers.exists())
        # Təkrar begin eyni attempt-i qaytarır (dublikat yaranmır).
        self.assertEqual(begin_attempt_for_ticket(self.ticket).pk, attempt.pk)

    def test_pin_is_revoked_and_reentry_blocked_after_begin(self):
        # İmtahan başladıqdan sonra PIN birdəfəlikdir — təkrar giriş bloklanır.
        enter_waiting(self.ticket, language="")
        start_room(self.session, self.invigilator)
        self.session.refresh_from_db()
        begin_attempt_for_ticket(self.ticket)
        self.ticket.refresh_from_db()
        self.assertIsNotNone(self.ticket.pin_revoked_at)
        self.assertFalse(self.ticket.has_valid_pin)
        # Eyni PIN ilə təkrar giriş cəhdi → daxil olmur.
        fresh = Client()
        fresh.post(reverse("exams:final_exam_entry"), {"username": self.student.username, "pin": self.raw_pin})
        self.assertNotIn("_auth_user_id", fresh.session)

    def test_invigilator_reentry_issues_new_pin_and_resumes_same_attempt(self):
        # Brauzer çökmə / bağlantı kəsilməsi bərpası: nəzarətçi yeni PIN verir,
        # tələbə həmin PIN ilə daxil olub EYNİ cəhdə (olduğu yerə) davam edir.
        enter_waiting(self.ticket, language="")
        start_room(self.session, self.invigilator)
        self.session.refresh_from_db()
        attempt = begin_attempt_for_ticket(self.ticket)
        self.ticket.refresh_from_db()
        self.assertFalse(self.ticket.has_valid_pin)  # başlanğıcda PIN ölüb

        client = self._client_for(self.invigilator)
        resp = client.post(reverse("exams:exam_center_ticket_reentry", args=[self.session.pk, self.ticket.pk]))
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        new_pin = data["pin"]

        self.ticket.refresh_from_db()
        self.assertTrue(self.ticket.has_valid_pin)  # yeni PIN etibarlı
        self.assertEqual(self.ticket.status, TICKET_STATUS_ACTIVE)  # status dəyişmir
        self.assertEqual(self.ticket.attempt_id, attempt.pk)  # cəhd qorunur

        # Tələbə YENİ PIN ilə daxil olur → aktiv cəhdə (take_exam) yönlənir.
        student_client = Client()
        r1 = student_client.post(reverse("exams:final_exam_entry"), {"username": self.student.username, "pin": new_pin})
        self.assertEqual(r1.status_code, 302)
        self.assertEqual(int(student_client.session["_auth_user_id"]), self.student.pk)
        r2 = student_client.get(reverse("exams:final_exam_entry"))
        self.assertEqual(r2.status_code, 302)
        self.assertIn(f"/attempt/{attempt.pk}/", r2["Location"])

    def test_begin_endpoint_via_http(self):
        client, _ = self._entry_client()
        client.post(reverse("exams:final_exam_entry"), {"action": "confirm", "accept_rules": "1", "language": ""})
        start_room(self.session, self.invigilator)
        response = client.post(reverse("exams:final_exam_begin", args=[self.ticket.pk]))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.ticket.refresh_from_db()
        self.assertIn(str(self.ticket.attempt_id), data["redirect_url"])

    def test_end_room_finalizes_attempts_and_tickets(self):
        enter_waiting(self.ticket, language="")
        start_room(self.session, self.invigilator)
        self.session.refresh_from_db()
        attempt = begin_attempt_for_ticket(self.ticket)

        absent_ticket = FinalExamTicket.objects.create(
            organization=self.org, session=self.session, exam=self.exam, student=self.student2
        )

        self.assertTrue(end_room(self.session, self.invigilator))
        self.session.refresh_from_db()
        self.assertEqual(self.session.state, ROOM_SESSION_STATE_ENDED)

        attempt.refresh_from_db()
        self.assertEqual(attempt.status, "submitted")
        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, TICKET_STATUS_COMPLETED)
        absent_ticket.refresh_from_db()
        self.assertEqual(absent_ticket.status, TICKET_STATUS_ABSENT)
        # PIN şifrəli nüsxələri silinib.
        self.assertEqual(self.ticket.pin_cipher, "")
        # İdempotent: təkrar son təsirsizdir.
        self.assertFalse(end_room(self.session, self.center))

    def test_concurrent_sessions_in_room_allowed(self):
        # Bir zalda üst-üstə düşən oturumlar İCAZƏLİDİR — zal aqreqasiyası
        # ssenarisi. Oturum sisteminin ləğvindən sonra tutum planda yoxlanmır
        # (tələbələr giriş anında IP → zal ilə dinamik qoşulur).
        try:
            validate_session_plan(
                room=self.room,
                scheduled_start=self.session.scheduled_start + timedelta(minutes=30),
                scheduled_end=self.session.scheduled_end + timedelta(minutes=30),
            )
        except RoomSessionStateError:
            self.fail("Eyni zalda paralel oturum icazəli olmalıdır.")

    def test_session_plan_rejects_end_before_start(self):
        with self.assertRaises(RoomSessionStateError):
            validate_session_plan(
                room=self.room,
                scheduled_start=self.session.scheduled_start,
                scheduled_end=self.session.scheduled_start - timedelta(minutes=10),
            )


class RemoveStudentTests(_FlowBase):
    def test_remove_requires_reason(self):
        enter_waiting(self.ticket, language="")
        with self.assertRaises(TicketStateError):
            remove_student(self.ticket, self.invigilator, action="removed", reason="  ")

    def test_remove_active_student_stops_attempt_and_revokes_pin(self):
        enter_waiting(self.ticket, language="")
        start_room(self.session, self.invigilator)
        self.session.refresh_from_db()
        attempt = begin_attempt_for_ticket(self.ticket)

        self.assertTrue(remove_student(self.ticket, self.invigilator, action="removed", reason="Qayda pozuntusu"))
        self.ticket.refresh_from_db()
        attempt.refresh_from_db()
        self.assertEqual(self.ticket.status, TICKET_STATUS_REMOVED)
        self.assertEqual(self.ticket.removal_reason, "Qayda pozuntusu")
        self.assertEqual(attempt.status, "submitted")
        self.assertIsNotNone(self.ticket.pin_revoked_at)

    def test_suspend_locks_attempt_but_keeps_ticket_active(self):
        enter_waiting(self.ticket, language="")
        start_room(self.session, self.invigilator)
        self.session.refresh_from_db()
        attempt = begin_attempt_for_ticket(self.ticket)

        self.assertTrue(remove_student(self.ticket, self.invigilator, action="suspended", reason="Şübhəli davranış"))
        self.ticket.refresh_from_db()
        attempt.refresh_from_db()
        self.assertEqual(self.ticket.status, TICKET_STATUS_ACTIVE)
        self.assertEqual(attempt.supervision_status, "locked")
        self.assertEqual(attempt.status, "in_progress")


class PermissionAndTenantTests(_FlowBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.other_owner = User.objects.create_user("fcf_owner2", "fcf_owner2@test.az", PASSWORD)
        cls.other_org = Organization.objects.create(
            name="Başqa Universitet",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.other_owner,
            status="active",
            is_active=True,
        )
        cls.other_center = User.objects.create_user("fcf_center2", "fcf_center2@test.az", PASSWORD)
        _assign_user_to_org(cls.other_center, cls.other_org, ProfileRole.MEMBER, "exam_center")

    def _other_org_client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.other_org.slug
        session.save()
        return client

    def test_monitor_denied_for_unassigned_teacher(self):
        client = self._client_for(self.teacher)
        response = client.get(reverse("exams:exam_center_session_monitor", args=[self.session.pk]))
        self.assertEqual(response.status_code, 403)

    def test_monitor_allowed_for_assigned_invigilator(self):
        client = self._client_for(self.invigilator)
        response = client.get(reverse("exams:exam_center_session_monitor", args=[self.session.pk]))
        self.assertEqual(response.status_code, 200)

    def test_room_management_denied_for_invigilator(self):
        # Zal/kompüter idarəsi artıq yalnız superadmin bölməsindədir; nəzarətçi
        # (müəllim) və hətta imtahan mərkəzi (bayraqsız) ora daxil ola bilməz.
        client = self._client_for(self.invigilator)
        response = client.get(reverse("accounts:superadmin_exam_rooms"))
        self.assertEqual(response.status_code, 403)

    def test_room_management_denied_for_exam_center_without_flag(self):
        client = self._client_for(self.center)
        response = client.get(reverse("accounts:superadmin_exam_rooms"))
        self.assertEqual(response.status_code, 403)

    def test_session_list_hides_manage_buttons_for_invigilator(self):
        # Nəzarətçi 403 alacağı idarə düymələrini (Yeni oturum / Hesabatlar /
        # Yeni zal) görməməlidir. Zallar hub-ı (room_list) isə onun GİRİŞ
        # səhifəsidir — breadcrumb ilə əlçatandır, ona görə gizlədilmir.
        client = self._client_for(self.invigilator)
        response = client.get(reverse("exams:exam_center_session_list"))
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["can_manage"])
        self.assertNotContains(response, reverse("exams:exam_center_session_create"))
        self.assertNotContains(response, reverse("exams:exam_center_reports"))

    def test_session_list_shows_manage_buttons_for_center(self):
        client = self._client_for(self.center)
        response = client.get(reverse("exams:exam_center_session_list"))
        self.assertTrue(response.context["can_manage"])
        self.assertContains(response, reverse("exams:exam_center_room_list"))

    def test_room_list_shows_only_assigned_rooms_for_invigilator(self):
        # İmtahan Nəzarət Sisteminin girişi: nəzarətçi YALNIZ təyin olunduğu
        # oturumun zalını görür; başqa nəzarətçinin zalı siyahıda görünmür.
        # Kart zaldakı canlı oturumu çip kimi göstərir (imtahandan asılı deyil).
        other_room = ExamRoom.objects.create(
            organization=self.org, name="Zal B", code="ZB", capacity=20, created_by=self.center
        )
        now = timezone.now()
        ExamRoomSession.objects.create(
            organization=self.org,
            room=other_room,
            invigilator=self.teacher,
            scheduled_start=now + timedelta(minutes=5),
            scheduled_end=now + timedelta(hours=2),
            created_by=self.center,
        )
        response = self._client_for(self.invigilator).get(reverse("exams:exam_center_room_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Zal A")
        self.assertNotContains(response, "Zal B")
        # Zal A-da giriş açıq (canlı) oturum var → oturum çipi görünür.
        self.assertContains(response, "fxc-room-exam-chip")

    def test_room_list_shows_all_rooms_for_center(self):
        ExamRoom.objects.create(organization=self.org, name="Zal B", code="ZB", capacity=20, created_by=self.center)
        response = self._client_for(self.center).get(reverse("exams:exam_center_room_list"))
        self.assertContains(response, "Zal A")
        self.assertContains(response, "Zal B")

    def test_history_access_control(self):
        # Nəzarətçi (müəllim) tarixçəni GÖRMÜR; imtahan mərkəzi rəhbəri GÖRÜR.
        url = reverse("exams:exam_center_session_history", args=[self.session.pk])
        self.assertEqual(self._client_for(self.invigilator).get(url).status_code, 403)
        self.assertEqual(self._client_for(self.center).get(url).status_code, 200)

    def test_session_history_records_operations(self):
        from apps.exams.services.final_center import session_history, set_seat

        set_seat(self.ticket, 7, self.center)  # final_seat_changed audit
        events = session_history(self.session)
        codes = {e["code"] for e in events}
        self.assertIn("final_room_entry_opened", codes)  # setUp open_entry
        self.assertIn("final_seat_changed", codes)
        seat_ev = next(e for e in events if e["code"] == "final_seat_changed")
        self.assertIn("→", seat_ev["detail"])  # köhnə → yeni kompüter

    def test_ticket_snapshot_no_attempt(self):
        client = self._client_for(self.invigilator)
        response = client.get(reverse("exams:exam_center_ticket_snapshot", args=[self.session.pk, self.ticket.pk]))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["has_attempt"])
        self.assertEqual(data["ticket_status"], TICKET_STATUS_ASSIGNED)

    def test_ticket_snapshot_with_active_attempt(self):
        enter_waiting(self.ticket, language="")
        start_room(self.session, self.invigilator)
        self.session.refresh_from_db()
        begin_attempt_for_ticket(self.ticket)
        client = self._client_for(self.invigilator)
        response = client.get(reverse("exams:exam_center_ticket_snapshot", args=[self.session.pk, self.ticket.pk]))
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["has_attempt"])
        self.assertIn("answers", data)
        self.assertIn("total_questions", data)

    def test_ticket_snapshot_cross_tenant_404(self):
        client = self._other_org_client(self.other_center)
        response = client.get(reverse("exams:exam_center_ticket_snapshot", args=[self.session.pk, self.ticket.pk]))
        self.assertEqual(response.status_code, 404)

    def test_room_monitor_aggregates_live_sessions(self):
        # Eyni zalda ikinci imtahan/oturum → zal monitoru hər ikisini birləşdirir.
        exam2 = Exam.objects.create(
            title="FCF Final 2",
            author=self.center,
            organization=self.org,
            exam_type="test",
            exam_type_extended="final",
            is_active=True,
            random_question_count=1,
        )
        session2 = ExamRoomSession.objects.create(
            organization=self.org,
            room=self.room,
            invigilator=self.invigilator,
            scheduled_start=timezone.now() + timedelta(minutes=5),
            scheduled_end=timezone.now() + timedelta(hours=2),
        )
        open_entry(session2, self.center)
        FinalExamTicket.objects.create(organization=self.org, session=session2, exam=exam2, student=self.student2)

        client = self._client_for(self.invigilator)
        response = client.get(reverse("exams:exam_center_room_monitor", args=[self.room.pk]))
        self.assertEqual(response.status_code, 200)
        snap = response.context["snapshot"]
        self.assertEqual(len(snap["sessions"]), 2)
        self.assertEqual(snap["counts"]["total"], 2)
        self.assertEqual({row["exam_title"] for row in snap["students"]}, {"FCF Final", "FCF Final 2"})

    def test_completed_result_hidden_after_timeout_but_counted(self):
        from apps.exams.services.final_center import room_monitor_snapshot
        from apps.exams.services.final_center.monitor import FINAL_RESULT_VISIBLE_SECONDS

        self.ticket.status = TICKET_STATUS_COMPLETED
        self.ticket.seat_number = 5
        self.ticket.completed_at = timezone.now() - timedelta(seconds=FINAL_RESULT_VISIBLE_SECONDS + 60)
        self.ticket.save(update_fields=["status", "seat_number", "completed_at"])
        snap = room_monitor_snapshot(self.room)
        # Sayğac saxlanır, amma köhnə nəticə xəritədən (grid) düşür.
        self.assertEqual(snap["counts"]["completed"], 1)
        self.assertNotIn(self.ticket.pk, [r["ticket_id"] for r in snap["students"]])

    def test_recent_completed_result_still_visible(self):
        from apps.exams.services.final_center import room_monitor_snapshot

        self.ticket.status = TICKET_STATUS_COMPLETED
        self.ticket.seat_number = 5
        self.ticket.completed_at = timezone.now() - timedelta(seconds=10)
        self.ticket.save(update_fields=["status", "seat_number", "completed_at"])
        snap = room_monitor_snapshot(self.room)
        self.assertIn(self.ticket.pk, [r["ticket_id"] for r in snap["students"]])

    def test_seat_reuse_hides_old_completed_immediately(self):
        from apps.exams.services.final_center import room_monitor_snapshot

        # Köhnə bitmiş bilet seat 7-də (təzə bitib); başqa oturumda EYNI seat-də
        # yeni aktiv tələbə → köhnə nəticə dərhal gizlənir, yeni tələbə görünür.
        self.ticket.status = TICKET_STATUS_COMPLETED
        self.ticket.seat_number = 7
        self.ticket.completed_at = timezone.now()
        self.ticket.save(update_fields=["status", "seat_number", "completed_at"])
        exam2 = Exam.objects.create(
            title="FCF Final 2",
            author=self.center,
            organization=self.org,
            exam_type="test",
            exam_type_extended="final",
            is_active=True,
            random_question_count=1,
        )
        session2 = ExamRoomSession.objects.create(
            organization=self.org,
            room=self.room,
            invigilator=self.invigilator,
            scheduled_start=timezone.now() + timedelta(minutes=5),
            scheduled_end=timezone.now() + timedelta(hours=2),
        )
        open_entry(session2, self.center)
        new_ticket = FinalExamTicket.objects.create(
            organization=self.org,
            session=session2,
            exam=exam2,
            student=self.student2,
            status=TICKET_STATUS_ACTIVE,
            seat_number=7,
        )
        snap = room_monitor_snapshot(self.room)
        ids = [r["ticket_id"] for r in snap["students"]]
        self.assertIn(new_ticket.pk, ids)
        self.assertNotIn(self.ticket.pk, ids)

    def test_room_start_all_time_window_error_is_graceful(self):
        # Vaxt pəncərəsindən kənar (çox tez) oturum → 500 YOX, 409 + xəta mesajı.
        self.session.scheduled_start = timezone.now() + timedelta(hours=1)
        self.session.save(update_fields=["scheduled_start"])
        client = self._client_for(self.invigilator)
        response = client.post(
            reverse("exams:exam_center_room_start_all", args=[self.room.pk]),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 409)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertIn("error", data)
        self.session.refresh_from_db()
        self.assertEqual(self.session.state, "entry_open")

    def test_ticket_resume_with_extra_chance_flag(self):
        from apps.exams.models import SupervisionIncident
        from apps.exams.services.supervision import teacher_lock_attempt

        enter_waiting(self.ticket, language="")
        start_room(self.session, self.invigilator)
        self.session.refresh_from_db()
        attempt = begin_attempt_for_ticket(self.ticket)
        teacher_lock_attempt(attempt, self.invigilator)
        client = self._client_for(self.invigilator)
        response = client.post(
            reverse("exams:exam_center_ticket_resume", args=[self.session.pk, self.ticket.pk]),
            {"grant_extra_chance": "1"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        # grant_extra_chance bayrağı ötürülür → "teacher_granted_chance" hadisəsi.
        self.assertTrue(
            SupervisionIncident.objects.filter(attempt=attempt, event_type="teacher_granted_chance").exists()
        )

    def test_room_start_all_starts_every_live_session(self):
        # Bir zalda iki paralel oturum → "hamısını başlat" hər ikisini aktiv edir
        # (oturum imtahandan asılı deyil).
        session2 = ExamRoomSession.objects.create(
            organization=self.org,
            room=self.room,
            invigilator=self.invigilator,
            scheduled_start=timezone.now() + timedelta(minutes=5),
            scheduled_end=timezone.now() + timedelta(hours=2),
        )
        open_entry(session2, self.center)
        client = self._client_for(self.invigilator)
        response = client.post(reverse("exams:exam_center_room_start_all", args=[self.room.pk]))
        self.assertEqual(response.status_code, 302)
        self.session.refresh_from_db()
        session2.refresh_from_db()
        self.assertEqual(self.session.state, ROOM_SESSION_STATE_ACTIVE)
        self.assertEqual(session2.state, ROOM_SESSION_STATE_ACTIVE)

    def test_ticket_resume_restores_locked_attempt(self):
        from apps.exams.services.supervision import teacher_lock_attempt

        enter_waiting(self.ticket, language="")
        start_room(self.session, self.invigilator)
        self.session.refresh_from_db()
        attempt = begin_attempt_for_ticket(self.ticket)
        teacher_lock_attempt(attempt, self.invigilator)
        client = self._client_for(self.invigilator)
        response = client.post(reverse("exams:exam_center_ticket_resume", args=[self.session.pk, self.ticket.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        attempt.refresh_from_db()
        self.assertEqual(attempt.supervision_status, "resumed")

    def test_cross_tenant_session_access_is_404(self):
        """Başqa təşkilatın imtahan mərkəzi bu oturumu görə bilməz (IDOR)."""
        client = self._other_org_client(self.other_center)
        response = client.get(reverse("exams:exam_center_session_monitor", args=[self.session.pk]))
        self.assertEqual(response.status_code, 404)

    def test_start_endpoint_denied_for_student(self):
        client = self._client_for(self.student)
        response = client.post(reverse("exams:exam_center_session_start", args=[self.session.pk]))
        self.assertEqual(response.status_code, 403)

    def test_snapshot_contains_compact_rows_only(self):
        enter_waiting(self.ticket, language="")
        snapshot = session_monitor_snapshot(self.session)
        self.assertEqual(snapshot["counts"]["waiting"], 1)
        row = snapshot["students"][0]
        # Kompakt sxem: cavab/sual məzmunu, PIN dəyəri YOXDUR.
        self.assertNotIn("pin", {k.split("_")[0] for k in row if k not in ("pin_issued", "pin_locked")})
        self.assertIn("status", row)
        self.assertIn("connected", row)


class CenterPageRenderTests(_FlowBase):
    """İmtahan mərkəzi səhifələrinin render smoke-testləri (şablon xətaları)."""

    def test_room_list_renders(self):
        response = self._client_for(self.center).get(reverse("exams:exam_center_room_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Zal A")

    def test_room_create_via_superadmin(self):
        # Zal yaratma artıq superadmin bölməsindədir (accounts:superadmin_exam_rooms).
        superadmin = User.objects.create_superuser("fcf_super", "fcf_super@test.az", PASSWORD)
        client = self._client_for(superadmin)
        response = client.post(
            reverse("accounts:superadmin_exam_rooms"),
            {
                "action": "create_room",
                "organization_id": self.org.id,
                "name": "Yeni zal",
                "code": "yz1",
                "building": "",
                "floor": "",
                "capacity": 10,
                "computer_count": 10,
                "notes": "",
                "is_active": "on",
                "next": reverse("accounts:profile") + "?section=superadmin-exam-rooms",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(ExamRoom.objects.filter(organization=self.org, code="YZ1").exists())

    def test_room_monitor_renders_with_computers_and_invigilator_panel(self):
        from apps.exams.services.final_center import add_computer

        add_computer(room=self.room, label="PC-01", mac="AA:BB:CC:DD:EE:01", ip_address="10.0.0.11", seat_number=1)
        response = self._client_for(self.center).get(reverse("exams:exam_center_room_monitor", args=[self.room.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "PC-01")
        self.assertContains(response, "AA:BB:CC:DD:EE:01")
        # İmtahan mərkəzi üçün nəzarətçi təyin paneli görünür.
        self.assertContains(response, reverse("exams:exam_center_room_assign_invigilators", args=[self.room.pk]))

    def test_assign_room_invigilators(self):
        client = self._client_for(self.center)
        response = client.post(
            reverse("exams:exam_center_room_assign_invigilators", args=[self.room.pk]),
            {"invigilators": [self.teacher.pk]},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.room.invigilators.filter(pk=self.teacher.pk).exists())

    def test_session_list_renders(self):
        response = self._client_for(self.center).get(reverse("exams:exam_center_session_list"))
        self.assertEqual(response.status_code, 200)
        # Oturum siyahısı imtahandan yox, ZALDAN asılıdır — zal adı görünür.
        self.assertContains(response, "Zal A")

    def test_session_detail_renders_with_tickets(self):
        response = self._client_for(self.center).get(
            reverse("exams:exam_center_session_detail", args=[self.session.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.student.username)

    def test_session_create_form_renders(self):
        response = self._client_for(self.center).get(reverse("exams:exam_center_session_create"))
        self.assertEqual(response.status_code, 200)

    def test_reports_render_both_tabs(self):
        client = self._client_for(self.center)
        self.assertEqual(client.get(reverse("exams:exam_center_reports")).status_code, 200)
        self.assertEqual(client.get(reverse("exams:exam_center_reports"), {"tab": "tickets"}).status_code, 200)

    def test_reports_csv_export(self):
        response = self._client_for(self.center).get(
            reverse("exams:exam_center_reports"), {"tab": "sessions", "export": "csv"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])

    def test_snapshot_endpoint_returns_json(self):
        response = self._client_for(self.invigilator).get(
            reverse("exams:exam_center_session_snapshot", args=[self.session.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("counts", response.json())

    def test_final_login_page_renders_form(self):
        response = Client().get(reverse("exams:final_exam_entry"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Final imtahan girişi")
        self.assertContains(response, 'name="pin"', html=False)
        # İmtahan siyahısı GÖSTƏRİLMİR — yalnız login.
        self.assertNotContains(response, "Final imtahan biletlərim")

    def test_waiting_page_renders_after_modal_confirm(self):
        client, _ = self._entry_client()
        client.post(reverse("exams:final_exam_entry"), {"action": "confirm", "accept_rules": "1", "language": ""})
        response = client.get(reverse("exams:final_exam_waiting", args=[self.ticket.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "fexc-waiting-root")
