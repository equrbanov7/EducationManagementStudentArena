"""Sahib 2026-09-30 — canlı imtahana QR ilə qoşulma HƏR giriş vəziyyətində işləyir.

QR linki (``build_join_url``) → PIN səhifəsi → qoşulma səhifəsi → ``join_enter`` (CSRF ilə) →
gözləmə otağı. Qonaq, daxil olmuş tələbə/müəllim/heyət/superadmin və ilk girişi (e-poçt kodu +
öz parolu) hələ bitirməmiş tələbə — hamısı qoşulur. Sonuncu əvvəl ``/accounts/set-password/``-ə
atılırdı; kabinet isə onun üçün əvvəlki kimi bağlı qalır.
"""

from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from apps.live_exam.models import LivePlayer
from apps.live_exam.transport import build_join_url

from .lx_sec_support import (
    login_client,
    make_exam,
    make_org,
    make_session,
    make_student,
    make_teacher,
    make_user,
    reset_rate_limits,
)

User = get_user_model()


class QrJoinLoginStatesTest(TestCase):
    def setUp(self):
        reset_rate_limits()
        owner = User.objects.create_user("qr_owner", "qr_owner@example.com", "StrongPass123!")
        self.org = make_org("QR Org", owner)
        self.host = make_teacher("qr_host", self.org)
        self.exam = make_exam(self.host, self.org, "qr-exam")
        self.session = make_session(self.exam, self.host)
        qr_url = build_join_url(RequestFactory().get("/"), self.session)
        self.qr_path = qr_url.split("testserver", 1)[-1]

    def _join_via_qr(self, client, nickname):
        page = client.get(self.qr_path, follow=True)
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.request["PATH_INFO"], reverse("liveExam:join_page", kwargs={"pin": self.session.pin}))
        enter = client.post(
            reverse("liveExam:join_enter", kwargs={"pin": self.session.pin}),
            {"nickname": nickname, "avatar_key": "avatar_1", "accessory_key": "accessory_none"},
            HTTP_X_CSRFTOKEN=client.cookies["csrftoken"].value,
        )
        self.assertEqual(enter.status_code, 200, enter.content)
        self.assertTrue(enter.json()["ok"])
        wait = client.get(reverse("liveExam:wait_room", kwargs={"pin": self.session.pin}))
        self.assertEqual(wait.status_code, 200)

    def test_every_login_state_can_join(self):
        first_login = make_student("qr_first_login", self.org)
        first_login.profile.password_change_required = True
        first_login.profile.save(update_fields=["password_change_required", "updated_at"])
        staff = make_user("qr_staff", self.org, profile_role="staff", role_name="ikt_rehber", level=95)
        superuser = User.objects.create_superuser("qr_root", "qr_root@example.com", "StrongPass123!")
        root_client = Client(enforce_csrf_checks=True)
        root_client.force_login(superuser)
        clients = {
            "Qonaq": Client(enforce_csrf_checks=True),
            "Tələbə": login_client(make_student("qr_student", self.org), self.org, enforce_csrf_checks=True),
            "İlk giriş": login_client(first_login, self.org, enforce_csrf_checks=True),
            "Müəllim": login_client(make_teacher("qr_teacher", self.org), self.org, enforce_csrf_checks=True),
            "Heyət": login_client(staff, self.org, enforce_csrf_checks=True),
            "Admin": root_client,
        }
        for nickname, client in clients.items():
            with self.subTest(state=nickname):
                self._join_via_qr(client, nickname)
        self.assertEqual(LivePlayer.objects.filter(session=self.session).count(), len(clients))

    def test_first_login_student_still_locked_out_of_cabinet_and_hosting(self):
        student = make_student("qr_locked", self.org)
        student.profile.password_change_required = True
        student.profile.save(update_fields=["password_change_required", "updated_at"])
        client = login_client(student, self.org)

        set_password = reverse("accounts:set_initial_password")
        self.assertEqual(client.get(reverse("accounts:profile"))["Location"], set_password)
        self.assertEqual(
            client.get(reverse("liveExam:host_lobby", kwargs={"pin": self.session.pin}))["Location"], set_password
        )
