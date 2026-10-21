"""Sərt zal rejimi — yalnız qeydli zal kompüterləri (sahib 2026-10-21).

Sahib: «Hansı kompüterlərin MAC ünvanlarını əlavə edəcəyəmsə, ancaq onlardan midterm və final səhifəsinə girmək
mümkün olsun; digər halda xəbərdarlıq mesajı göstərilsin. Sistem tənzimləmələrindən açmadığım müddətcə heç kim
kənar kompüterlə o səhifəni belə aça bilməsin.»

* Açar ``exam.hall_computer_check`` YANDIRILIB (defolt): /exams/final/, /exams/midterm/ (GET + POST), gözləmə
  otağı və state/begin/cancel yalnız AKTİV qeydli ``ExamRoomComputer``-dən (IP rejimi / MAC rejimi — ARP saxta);
  qeydsiz kompüter → 403 xəbərdarlıq (forma YOX) + bu kompüterin öz ünvanı; qeydli kompüter yoxdursa da bloklanır.
* Söndürülüb: universitet şəbəkəsindəki istənilən kompüter formanı görür; kənar şəbəkə yenə bloklanır.
* Sınaq keç (müəllif) qapıdan keçmir.
"""

from __future__ import annotations

from unittest import mock

from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.exams.models import ExamAttempt, FinalExamTicket
from apps.exams.services import exam_center_gate
from apps.exams.services.exam_center_gate import client_address_diagnostic
from apps.exams.tests.test_audit_2026_09_13_exam_integrity import LOCMEM_CACHE, _make_people, _student_client
from apps.exams.tests.test_examaccess_2026_10_13 import NETWORK_ON, _make_official, _set_student_pin
from apps.exams.tests.test_midterm_center_2026_10_20 import (
    CENTER_ON,
    FINAL_PIN,
    MIDTERM_PIN,
    PC1_IP,
    _CenterFixture,
)

UNREGISTERED_IP = "10.2.2.77"
WARNING = "Bu kompüter imtahan zalı kompüteri kimi qeydiyyatdan keçməyib"
STRICT = {"EXAM_HALL_COMPUTER_CHECK": True, **CENTER_ON, **NETWORK_ON}
OFF = {"EXAM_HALL_COMPUTER_CHECK": False, **CENTER_ON, **NETWORK_ON}
ENTRY_URLS = ("exams:final_exam_entry", "exams:midterm_exam_entry")


def _mac(value):
    return mock.patch.object(exam_center_gate, "resolve_client_mac", return_value=value)


@override_settings(CACHES=LOCMEM_CACHE, **STRICT)
class StrictHallComputerTests(_CenterFixture, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls._build("hs1021")

    def _assert_blocked(self, response):
        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, "exams/student/hall_computer_blocked.html")
        self.assertContains(response, WARNING, status_code=403)
        self.assertNotContains(response, 'name="pin"', status_code=403)
        self.assertNotContains(response, 'name="username"', status_code=403)

    def test_unregistered_computer_sees_warning_with_its_own_address_and_no_form(self):
        for url_name in ENTRY_URLS:
            response = Client().get(reverse(url_name), REMOTE_ADDR=UNREGISTERED_IP)
            self._assert_blocked(response)
            self.assertContains(response, f"data-fexc-client-ip>{UNREGISTERED_IP}</code>", status_code=403)
            self.assertContains(response, "data-fexc-client-mac>oxunmadı</code>", status_code=403)
            self.assertContains(response, "language-switcher--floating", status_code=403)

    def test_unregistered_computer_cannot_post_a_login(self):
        client = Client()
        response = client.post(
            reverse("exams:midterm_exam_entry"),
            {"username": self.student.username, "pin": MIDTERM_PIN},
            REMOTE_ADDR=UNREGISTERED_IP,
        )
        self._assert_blocked(response)
        self.assertNotIn("_auth_user_id", client.session)
        self.assertFalse(FinalExamTicket.objects.filter(exam=self.midterm, student=self.student).exists())

    def test_registered_computer_ip_mode_gets_the_form(self):
        for url_name in ENTRY_URLS:
            response = Client().get(reverse(url_name), REMOTE_ADDR=PC1_IP)
            self.assertEqual(response.status_code, 200, url_name)
            self.assertContains(response, 'name="pin"')

    def test_registered_computer_mac_mode_gets_the_form_and_unknown_mac_is_shown(self):
        with override_settings(EXAM_CLIENT_MAC_RESOLUTION="arp_agent"):
            with _mac(self.pc1.mac_address):
                ok = Client().get(reverse("exams:final_exam_entry"), REMOTE_ADDR=UNREGISTERED_IP)
            self.assertEqual(ok.status_code, 200)  # MAC rejimində IP əhəmiyyətsizdir
            with _mac("DE:AD:BE:EF:00:01"):
                blocked = Client().get(reverse("exams:final_exam_entry"), REMOTE_ADDR=PC1_IP)
        self._assert_blocked(blocked)
        self.assertContains(blocked, "data-fexc-client-mac>DE:AD:BE:EF:00:01</code>", status_code=403)

    def test_inactive_computer_does_not_count(self):
        self.pc1.is_active = False
        self.pc1.save(update_fields=["is_active"])
        self._assert_blocked(Client().get(reverse("exams:final_exam_entry"), REMOTE_ADDR=PC1_IP))

    def test_waiting_room_and_state_are_blocked_from_another_computer(self):
        client, response = self._login("exams:midterm_exam_entry", MIDTERM_PIN)
        self.assertEqual(response.status_code, 302)
        confirm = self._enter_waiting(client)
        waiting_url = confirm["Location"]
        self.assertEqual(client.get(waiting_url, REMOTE_ADDR=PC1_IP).status_code, 200)
        self._assert_blocked(client.get(waiting_url, REMOTE_ADDR=UNREGISTERED_IP))
        ticket = FinalExamTicket.objects.get(exam=self.midterm, student=self.student)
        state = client.get(
            reverse("exams:final_ticket_state", args=[ticket.pk]),
            REMOTE_ADDR=UNREGISTERED_IP,
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(state.status_code, 403)
        self.assertTrue(state.json()["hall_computer_blocked"])
        begin = client.post(
            reverse("exams:final_exam_begin", args=[ticket.pk]),
            REMOTE_ADDR=UNREGISTERED_IP,
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",  # waiting_room.js fetch başlığı
        )
        self.assertEqual(begin.status_code, 403)
        self.assertTrue(begin.json()["hall_computer_blocked"])
        self.assertFalse(ExamAttempt.objects.filter(user=self.student, exam=self.midterm).exists())

    def test_external_network_is_still_the_network_page(self):
        response = Client().get(reverse("exams:final_exam_entry"), REMOTE_ADDR="85.132.9.11")
        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, "exams/student/exam_network_blocked.html")

    def test_teacher_trial_run_is_unaffected(self):
        teacher = _student_client(self.teacher.username, self.org)
        url = reverse("exams:start_exam", kwargs={"slug": self.final.slug}) + "?trial=1"
        response = teacher.post(url, {"trial": "1"}, REMOTE_ADDR=UNREGISTERED_IP)
        self.assertEqual(response.status_code, 302, getattr(response, "content", b"")[:300])
        self.assertTrue(ExamAttempt.objects.get(user=self.teacher, exam=self.final).is_trial)


@override_settings(CACHES=LOCMEM_CACHE, **STRICT)
class StrictHallNoComputersTests(TestCase):
    """Sərt rejim: org-da (sistemdə) HEÇ qeydli kompüter yoxdursa da heç kim daxil ola bilmir."""

    @classmethod
    def setUpTestData(cls):
        cls.org, cls.teacher, cls.student = _make_people("hs1021none")
        cls.final = _make_official(cls.org, cls.teacher, "HS Final")
        cls.final.allowed_users.add(cls.student)

    def test_zero_registered_computers_blocks_entry_and_login(self):
        _set_student_pin(self.final, self.student, FINAL_PIN)
        page = Client().get(reverse("exams:final_exam_entry"), REMOTE_ADDR=PC1_IP)
        self.assertEqual(page.status_code, 403)
        self.assertContains(page, WARNING, status_code=403)
        login = Client().post(
            reverse("exams:final_exam_entry"), {"username": self.student.username, "pin": FINAL_PIN}, REMOTE_ADDR=PC1_IP
        )
        self.assertEqual(login.status_code, 403)
        self.assertFalse(ExamAttempt.objects.filter(user=self.student, exam=self.final).exists())

    def test_key_off_opens_the_form_on_the_university_network(self):
        with override_settings(EXAM_HALL_COMPUTER_CHECK=False):
            page = Client().get(reverse("exams:final_exam_entry"), REMOTE_ADDR=UNREGISTERED_IP)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'name="pin"')


@override_settings(CACHES=LOCMEM_CACHE, **OFF)
class HallComputerKeyOffTests(_CenterFixture, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls._build("hs1021off")

    def test_any_internal_computer_gets_the_form(self):
        for url_name in ENTRY_URLS:
            response = Client().get(reverse(url_name), REMOTE_ADDR=UNREGISTERED_IP)
            self.assertEqual(response.status_code, 200, url_name)
            self.assertContains(response, 'name="pin"')

    def test_external_network_still_blocked(self):
        response = Client().get(reverse("exams:final_exam_entry"), REMOTE_ADDR="85.132.9.11")
        self.assertEqual(response.status_code, 403)
        self.assertTemplateUsed(response, "exams/student/exam_network_blocked.html")


class ClientAddressDiagnosticTests(TestCase):
    def test_only_the_clients_own_private_address_is_shown(self):
        rf = RequestFactory()
        self.assertEqual(client_address_diagnostic(rf.get("/", REMOTE_ADDR="10.7.0.5")), {"ip": "10.7.0.5", "mac": ""})
        # Publik ünvan göstərilmir (server/proxy və ya kənar ünvan sızmasın).
        with override_settings(INTERNAL_NETWORKS=["10.0.0.0/8"]):
            self.assertEqual(client_address_diagnostic(rf.get("/", REMOTE_ADDR="85.132.9.11"))["ip"], "")
            self.assertEqual(client_address_diagnostic(rf.get("/", REMOTE_ADDR="192.168.4.20"))["ip"], "192.168.4.20")

    @override_settings(EXAM_CLIENT_MAC_RESOLUTION="arp_agent")
    def test_mac_is_read_once_per_request(self):
        request = RequestFactory().get("/", REMOTE_ADDR="10.7.0.5")
        with mock.patch.object(exam_center_gate, "_lookup_client_mac", return_value="AA:BB:CC:00:11:22") as lookup:
            self.assertEqual(exam_center_gate.resolve_client_mac(request), "AA:BB:CC:00:11:22")
            self.assertEqual(client_address_diagnostic(request)["mac"], "AA:BB:CC:00:11:22")
        self.assertEqual(lookup.call_count, 1)
