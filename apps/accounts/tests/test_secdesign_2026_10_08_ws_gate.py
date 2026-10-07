"""Təhlükəsizlik dizaynı 2026-10-08 — WebSocket qoşulmaları admin 2FA + şəbəkə zonası qapısından keçir.

Audit 2026-10-07 «Dizayn riskləri»: WS consumer-ləri ``AdminOTPGateMiddleware`` və
``NetworkZoneMiddleware``-dən keçmirdi. İndi ``config.asgi``-də ``WebSocketAccessGate``
HTTP-nin EYNİ funksiyalarını çağırır; rədd ``accept()``-dən əvvəl xüsusi kodla olur.
Tələbə/anonim oyunçu istənilən zonadan qoşulmağa davam edir.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.backends.db import SessionStore
from django.test import Client, SimpleTestCase, TestCase, TransactionTestCase, override_settings

from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator

from apps.accounts.ws_gate import (
    WS_CLOSE_ADMIN_2FA,
    WS_CLOSE_NETWORK_ZONE,
    NeedsDatabase,
    ScopeRequest,
    evaluate_ws_access,
)
from apps.audit.models import AuditLog
from apps.exams.tests.test_final_center_consumers import TEST_CHANNEL_LAYERS, FinalCenterConsumerAuthTests
from apps.live_exam.auth import PLAYER_COOKIE_NAME, build_player_token
from apps.live_exam.consumer_support import scope_ip
from apps.live_exam.models import LivePlayer
from apps.live_exam.tests.lx_sec_support import make_exam, make_org, make_session, make_teacher, reset_rate_limits
from config.asgi import application
from core.access_facts import ACCESS_FACTS_SESSION_KEY
from core.admin_auth import ADMIN_2FA_VERIFIED_USER_SESSION_KEY

User = get_user_model()

ORIGIN = (b"origin", b"http://testserver")
EXT = b"85.132.1.1"
INT = b"10.0.2.50"
ZONE = {"NETWORK_ZONE_ENFORCED": True, "INTERNAL_NETWORKS": ["10.0.0.0/8", "127.0.0.0/8"]}


def _connect(path, headers):
    async def scenario():
        communicator = WebsocketCommunicator(application, path, headers=headers)
        connected, code = await communicator.connect()
        if connected:
            await communicator.disconnect()
        else:
            await communicator.wait()
        return connected, code

    return async_to_sync(scenario)()


@override_settings(CHANNEL_LAYERS=TEST_CHANNEL_LAYERS)
class WebSocketZoneAndTwoFactorGateTests(TransactionTestCase):
    """Final mərkəzi kanalları — eyni fikstur ``test_final_center_consumers``-dən."""

    setUp = FinalCenterConsumerAuthTests.setUp
    _session_headers = FinalCenterConsumerAuthTests._session_headers

    def _headers(self, username, ip, *extra):
        return [*self._session_headers(username), (b"x-forwarded-for", ip), *extra]

    def _room(self):
        return f"/ws/exams/final/room/{self.session.pk}/"

    def _wait(self):
        return f"/ws/exams/final/wait/{self.ticket.pk}/"

    # ── şəbəkə zonası ──────────────────────────────────────────────────────

    @override_settings(**ZONE)
    def test_superadmin_socket_from_outside_is_closed_before_accept_and_audited(self):
        User.objects.filter(pk=self.center.pk).update(is_superuser=True)

        connected, code = _connect(self._room(), self._headers("fcc_center", EXT))

        self.assertFalse(connected)
        self.assertEqual(code, WS_CLOSE_NETWORK_ZONE)
        row = AuditLog.objects.filter(resource_type="network_zone_deny").latest("id")
        self.assertEqual(row.reason, "network_zone: superadmin_internal_only")
        self.assertEqual(row.resource_id, EXT.decode())
        self.assertEqual(row.resource_repr, self._room())

    @override_settings(**ZONE)
    def test_superadmin_socket_inside_still_works(self):
        User.objects.filter(pk=self.center.pk).update(is_superuser=True)
        self.assertEqual(_connect(self._room(), self._headers("fcc_center", INT))[0], True)

    @override_settings(**ZONE, NETWORK_ZONE_STAFF_INTERNAL_ONLY=True)
    def test_staff_rule_applies_to_sockets(self):
        connected, code = _connect(self._room(), self._headers("fcc_center", EXT))
        self.assertFalse(connected)
        self.assertEqual(code, WS_CLOSE_NETWORK_ZONE)
        self.assertTrue(
            AuditLog.objects.filter(
                resource_type="network_zone_deny", reason="network_zone: staff_internal_only"
            ).exists()
        )
        self.assertTrue(_connect(self._room(), self._headers("fcc_center", INT))[0])

    @override_settings(**ZONE)
    def test_staff_socket_outside_follows_the_default_off_staff_rule(self):
        self.assertTrue(_connect(self._room(), self._headers("fcc_center", EXT))[0])

    @override_settings(**ZONE, NETWORK_ZONE_STAFF_INTERNAL_ONLY=True)
    def test_student_waiting_room_socket_works_from_the_internet(self):
        self.assertTrue(_connect(self._wait(), self._headers("fcc_student", EXT))[0])

    @override_settings(**ZONE, NETWORK_ZONE_TRUST_HEADER=False)
    def test_client_sent_forwarded_for_and_zone_header_do_not_make_a_socket_internal(self):
        User.objects.filter(pk=self.center.pk).update(is_superuser=True)
        headers = [
            *self._session_headers("fcc_center"),
            # Müştəri sola «daxili» İP yazır; etibarlı proxy real İP-ni SAĞA əlavə edir.
            (b"x-forwarded-for", INT + b", " + EXT),
            (b"x-ems-zone", b"internal"),
        ]
        connected, code = _connect(self._room(), headers)
        self.assertFalse(connected)
        self.assertEqual(code, WS_CLOSE_NETWORK_ZONE)

    @override_settings(**ZONE)
    def test_view_as_session_is_judged_by_the_real_account(self):
        User.objects.filter(pk=self.center.pk).update(is_superuser=True)
        client = Client()
        client.login(username="fcc_center", password="StrongPass123!")
        session = client.session
        session["view_as_state"] = {"target_id": self.student.pk, "org_id": str(self.org.pk), "mode": "full"}
        session.save()
        cookie = client.cookies[settings.SESSION_COOKIE_NAME].value
        headers = [ORIGIN, (b"cookie", f"{settings.SESSION_COOKIE_NAME}={cookie}".encode()), (b"x-forwarded-for", EXT)]

        connected, code = _connect(self._room(), headers)

        self.assertFalse(connected)
        self.assertEqual(code, WS_CLOSE_NETWORK_ZONE)

    # ── admin 2FA ──────────────────────────────────────────────────────────

    @override_settings(ADMIN_2FA_REQUIRED=True)
    def test_admin_session_without_verified_otp_cannot_open_a_socket(self):
        User.objects.filter(pk=self.center.pk).update(is_staff=True)

        connected, code = _connect(self._room(), self._headers("fcc_center", INT))

        self.assertFalse(connected)
        self.assertEqual(code, WS_CLOSE_ADMIN_2FA)
        self.assertTrue(
            AuditLog.objects.filter(resource_type="admin_2fa_ws_deny", resource_id=str(self.center.pk)).exists()
        )

    @override_settings(ADMIN_2FA_REQUIRED=True)
    def test_admin_session_with_verified_otp_opens_the_socket(self):
        User.objects.filter(pk=self.center.pk).update(is_staff=True)
        client = Client()
        client.login(username="fcc_center", password="StrongPass123!")
        session = client.session
        session[ADMIN_2FA_VERIFIED_USER_SESSION_KEY] = str(self.center.pk)
        session.save()
        cookie = client.cookies[settings.SESSION_COOKIE_NAME].value
        headers = [ORIGIN, (b"cookie", f"{settings.SESSION_COOKIE_NAME}={cookie}".encode()), (b"x-forwarded-for", INT)]

        self.assertTrue(_connect(self._room(), headers)[0])

    @override_settings(ADMIN_2FA_REQUIRED=True, **ZONE, NETWORK_ZONE_STAFF_INTERNAL_ONLY=True)
    def test_student_socket_is_untouched_by_admin_2fa(self):
        self.assertTrue(_connect(self._wait(), self._headers("fcc_student", EXT))[0])


@override_settings(CHANNEL_LAYERS=TEST_CHANNEL_LAYERS, **ZONE, NETWORK_ZONE_STAFF_INTERNAL_ONLY=True)
class LiveExamSocketsFromTheInternetTests(TransactionTestCase):
    def setUp(self):
        reset_rate_limits()
        owner = User.objects.create_user("wsg_owner", "wsg_owner@example.com", "StrongPass123!")
        self.org = make_org("WSG Org", owner)
        self.host = make_teacher("wsg_host", self.org)
        self.exam = make_exam(self.host, self.org, "wsg-exam")
        self.session = make_session(self.exam, self.host)
        self.player = LivePlayer.objects.create(session=self.session, nickname="Anon", client_id="wsg-1")

    def test_anonymous_pin_player_connects_from_outside(self):
        token = build_player_token(pin=self.session.pin, player_id=self.player.id, client_id=self.player.client_id)
        headers = [ORIGIN, (b"cookie", f"{PLAYER_COOKIE_NAME}={token}".encode()), (b"x-forwarded-for", EXT)]
        for path in (f"/ws/live/{self.session.pin}/lobby/", f"/ws/live/{self.session.pin}/play/"):
            self.assertTrue(_connect(path, headers)[0], path)

    def test_teacher_host_connects_from_outside(self):
        client = Client()
        client.force_login(self.host)
        cookie = client.cookies[settings.SESSION_COOKIE_NAME].value
        headers = [ORIGIN, (b"cookie", f"{settings.SESSION_COOKIE_NAME}={cookie}".encode()), (b"x-forwarded-for", EXT)]
        self.assertTrue(_connect(f"/ws/live/{self.session.pin}/play/", headers)[0])


class GateCostTests(TestCase):
    """Qoşulma başına əlavə DB sorğusu yoxdur — faktlar sessiyadan oxunur."""

    def setUp(self):
        self.student = User.objects.create_user("wsg_cost", "wsg_cost@example.com", "StrongPass123!")

    def _scope(self, user, session, ip=EXT):
        return {
            "type": "websocket",
            "path": "/ws/exams/final/wait/1/",
            "headers": [(b"x-forwarded-for", ip)],
            "client": ("172.18.0.5", 50000),
            "user": user,
            "session": session,
        }

    @override_settings(ADMIN_2FA_REQUIRED=True, **ZONE, NETWORK_ZONE_STAFF_INTERNAL_ONLY=True)
    def test_cached_facts_mean_zero_queries(self):
        session = SessionStore()
        session[ACCESS_FACTS_SESSION_KEY] = {"uid": self.student.pk, "sa": False, "kind": "student"}
        request = ScopeRequest(self._scope(self.student, session))
        with self.assertNumQueries(0):
            self.assertIsNone(evaluate_ws_access(request, allow_db=False))

    @override_settings(ADMIN_2FA_REQUIRED=True, **ZONE)
    def test_anonymous_socket_is_decided_in_memory(self):
        request = ScopeRequest(self._scope(AnonymousUser(), SessionStore()))
        with self.assertNumQueries(0):
            self.assertIsNone(evaluate_ws_access(request, allow_db=False))

    @override_settings(ADMIN_2FA_REQUIRED=True)
    def test_missing_fact_falls_back_to_the_database(self):
        request = ScopeRequest(self._scope(self.student, SessionStore()))
        with self.assertRaises(NeedsDatabase):
            evaluate_ws_access(request, allow_db=False)
        self.assertIsNone(evaluate_ws_access(request, allow_db=True))

    @override_settings(ADMIN_2FA_REQUIRED=True)
    def test_facts_of_another_account_are_ignored(self):
        session = SessionStore()
        session[ACCESS_FACTS_SESSION_KEY] = {"uid": self.student.pk + 1, "sa": False, "kind": "student"}
        request = ScopeRequest(self._scope(self.student, session))
        with self.assertRaises(NeedsDatabase):
            evaluate_ws_access(request, allow_db=False)

    @override_settings(**ZONE, NETWORK_ZONE_STAFF_INTERNAL_ONLY=True)
    def test_http_gate_remembers_the_facts_the_socket_reads(self):
        client = Client()
        client.force_login(self.student)
        client.get("/", REMOTE_ADDR=EXT.decode())
        facts = client.session.get(ACCESS_FACTS_SESSION_KEY)
        self.assertEqual(facts, {"uid": self.student.pk, "sa": False, "kind": "student"})

    @override_settings(ADMIN_2FA_REQUIRED=True)
    def test_admin_2fa_gate_remembers_the_superadmin_fact(self):
        client = Client()
        client.force_login(self.student)
        client.get("/")
        self.assertEqual(client.session.get(ACCESS_FACTS_SESSION_KEY), {"uid": self.student.pk, "sa": False})


class ScopeClientIpTests(SimpleTestCase):
    def test_live_exam_rate_limit_ip_uses_trusted_proxy_semantics(self):
        scope = {"client": ("172.18.0.5", 1), "headers": [(b"x-forwarded-for", b"6.6.6.6, 85.132.1.1")]}
        self.assertEqual(scope_ip(scope), "85.132.1.1")
        self.assertEqual(scope_ip({"client": ("172.18.0.5", 1), "headers": []}), "172.18.0.5")
        self.assertEqual(scope_ip({"headers": []}), "unknown")
