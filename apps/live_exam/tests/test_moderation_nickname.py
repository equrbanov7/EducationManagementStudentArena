"""Canlı imtahan ləqəbi — nalayiq ad filtri (sahib 2026-09-30, WP MOD).

* qoşulma (``join_enter``) və gözləmə otağında ad dəyişmə (``wait_room_profile``)
  nalayiq ləqəbi 400 ilə rədd edir, oyunçu yaranmır / ad dəyişmir, cavab sözü
  TƏKRARLAMIR;
* hər rədd audit jurnalına sessiyanın TƏŞKİLATI ilə yazılır: anonim oyunçu üçün
  IP + ``live_client_id``, daxil olmuş tələbə üçün istifadəçi;
* real adlar keçir; eyni klientin təkrar cəhdləri kilidlənir (429), başqa
  klient (eyni sinif IP-si) qoşula bilir;
* dəyişməyən ad (yalnız avatar dəyişikliyi) yoxlanmır.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.live_exam.auth import LIVE_CLIENT_ID_COOKIE_NAME
from apps.live_exam.models import LivePlayer
from core.moderation.enforcement import PROFANITY_RESOURCE_TYPE, rate_limited_message, rejection_message

from .lx_sec_support import (
    login_client,
    make_exam,
    make_org,
    make_session,
    make_student,
    make_teacher,
    player_client,
    reset_rate_limits,
)

User = get_user_model()
CLASS_IP = "10.20.30.40"


def _rows():
    return AuditLog.objects.filter(resource_type=PROFANITY_RESOURCE_TYPE).order_by("created_at")


class _Base(TestCase):
    def setUp(self):
        reset_rate_limits()
        owner = User.objects.create_user("mod_lx_owner", "mod_lx_owner@example.com", "StrongPass123!")
        self.org = make_org("MOD Live Org", owner)
        self.host = make_teacher("mod_lx_host", self.org)
        self.exam = make_exam(self.host, self.org, "mod-live-exam")
        self.session = make_session(self.exam, self.host)
        self.join_url = reverse("liveExam:join_enter", kwargs={"pin": self.session.pin})
        self.profile_url = reverse("liveExam:wait_room_profile", kwargs={"pin": self.session.pin})

    def _join(self, nickname, client_id, client=None):
        client = client or Client(REMOTE_ADDR=CLASS_IP)
        client.cookies[LIVE_CLIENT_ID_COOKIE_NAME] = client_id
        data = {"nickname": nickname, "avatar_key": "avatar_1", "accessory_key": "accessory_none"}
        return client.post(self.join_url, data)


class JoinNicknameModerationTest(_Base):
    def test_profane_nickname_is_rejected_and_logged_with_client_and_ip(self):
        response = self._join("S1kt1r Ali", "mod-cid-1")
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["message"], rejection_message())
        self.assertNotIn("kt", payload["message"].lower())
        self.assertFalse(LivePlayer.objects.filter(session=self.session).exists())

        row = _rows().get()
        self.assertIsNone(row.user_id)
        self.assertEqual(row.ip_address, CLASS_IP)
        self.assertEqual(row.organization_id, self.org.pk)
        self.assertEqual(row.resource_repr, "live_exam.join.nickname")
        values = row.new_values
        self.assertEqual(values["live_client_id"], "mod-cid-1")
        self.assertEqual(values["live_session_id"], self.session.pk)
        self.assertEqual(values["value_masked"], "S***** ***")
        self.assertEqual(values["view"], "liveExam:join_enter")
        self.assertTrue(values["anonymous"])

    def test_each_language_is_rejected(self):
        for index, nickname in enumerate(("amcıq", "orospu", "fuck boy", "сука", "blyat")):
            with self.subTest(nickname=nickname):
                self.assertEqual(self._join(nickname, f"mod-lang-{index}").status_code, 400)
        self.assertEqual(_rows().count(), 5)

    def test_real_names_join_normally(self):
        for index, nickname in enumerate(("Səmədov Pənah", "Abbasov", "Amina", "Nigar-2", "Ceyhun 07")):
            with self.subTest(nickname=nickname):
                self.assertEqual(self._join(nickname, f"mod-real-{index}").status_code, 200)
        self.assertEqual(LivePlayer.objects.filter(session=self.session).count(), 5)
        self.assertFalse(_rows().exists())

    def test_logged_in_student_is_recorded_as_the_actor(self):
        student = make_student("mod_lx_student", self.org)
        client = login_client(student, self.org, REMOTE_ADDR=CLASS_IP)
        response = self._join("pizdec", "mod-cid-student", client=client)
        self.assertEqual(response.status_code, 400)
        row = _rows().get()
        self.assertEqual(row.user_id, student.pk)
        self.assertFalse(row.new_values["anonymous"])

    def test_repeated_attempts_lock_the_client_but_not_the_class(self):
        for index in range(5):
            self.assertEqual(self._join(f"siktir{index}", "mod-spammer").status_code, 400)
        locked = self._join("siktir9", "mod-spammer")
        self.assertEqual(locked.status_code, 429)
        self.assertEqual(locked.json()["message"], rate_limited_message())
        self.assertTrue(locked.headers.get("Retry-After"))
        # 2026-09-30 (M6): kilid altında da təmiz adla qoşulmaq olur.
        self.assertEqual(self._join("Kamran", "mod-spammer").status_code, 200)
        # Eyni sinif IP-si, başqa cihaz — qoşulur.
        self.assertEqual(self._join("Leyla", "mod-classmate").status_code, 200)
        self.assertEqual(_rows().count(), 5)


class WaitRoomRenameModerationTest(_Base):
    def test_profane_rename_is_rejected_and_logged(self):
        player, client = player_client(self.session, "Leyla", "mod-wait-cid", REMOTE_ADDR=CLASS_IP)
        response = client.post(
            self.profile_url, {"nickname": "qəhbə", "avatar_key": "avatar_1", "accessory_key": "cap"}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["message"], rejection_message())
        player.refresh_from_db()
        self.assertEqual(player.nickname, "Leyla")

        row = _rows().get()
        self.assertEqual(row.resource_repr, "live_exam.wait.nickname")
        self.assertEqual(row.ip_address, CLASS_IP)
        self.assertEqual(row.new_values["live_client_id"], "mod-wait-cid")
        self.assertEqual(row.organization_id, self.org.pk)

    def test_clean_rename_and_unchanged_name_pass(self):
        player, client = player_client(self.session, "Leyla", "mod-wait-ok", REMOTE_ADDR=CLASS_IP)
        response = client.post(
            self.profile_url, {"nickname": "Leyla", "avatar_key": "avatar_2", "accessory_key": "cap"}
        )
        self.assertEqual(response.status_code, 200)
        response = client.post(self.profile_url, {"nickname": "Leyla Quliyeva", "avatar_key": "avatar_2"})
        self.assertEqual(response.status_code, 200)
        player.refresh_from_db()
        self.assertEqual(player.nickname, "Leyla Quliyeva")
        self.assertFalse(_rows().exists())
