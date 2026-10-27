"""Sessiya siyasəti (sahib 2026-10-27): brauzer bağlananda çıxış, «brauzer açıq deyil» limiti, imtahan istisnası,
fon pingi + təzə CSRF, lokallaşdırılmış «sessiya başa çatdı» / CSRF cavabları, hərəkətsiz jurnalın bağlanması açarı.
"""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts import session_policy
from apps.accounts.middleware_center_exam import CENTER_SESSION_KEY
from apps.accounts.models import RuntimeSetting
from apps.organizations.models import Membership, Organization, Role
from core import runtime_settings as rs
from core.constants import OrganizationType, RoleScopeType

User = get_user_model()

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "session-policy"}}
PRESENCE_ON = {"SESSION_PRESENCE_MINUTES": 30}


class _Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("sp_owner", "sp_owner@qku.edu.az", "pw")
        cls.org = Organization.objects.create(
            name="SP Univ", slug="sp-univ", org_type=OrganizationType.UNIVERSITY, owner=cls.owner, status="active"
        )
        cls.teacher = cls._member("sp_teacher", "teacher")
        cls.student = cls._member("sp_student", "student")

    @classmethod
    def _member(cls, username, role_name):
        role, _ = Role.objects.update_or_create(
            organization=cls.org,
            name=role_name,
            defaults={"display_name": role_name, "level": 10, "scope_type": RoleScopeType.ORGANIZATION},
        )
        user = User.objects.create_user(username, f"{username}@qku.edu.az", "pw")
        Membership.objects.create(user=user, organization=cls.org, role=role, is_primary=True, is_active=True)
        return user

    def _client(self, user, **headers):
        client = Client(**headers)
        client.force_login(user)
        return client

    def _age(self, client, key, minutes):
        session = client.session
        session[key] = (timezone.now() - timedelta(minutes=minutes)).isoformat()
        session.save()

    def _session_cookie(self, response):
        return response.cookies.get(settings.SESSION_COOKIE_NAME)


class BrowserCloseScopeTest(_Base):
    def test_staff_session_cookie_dies_with_the_browser(self):
        client = self._client(self.teacher)
        response = client.get(reverse("home"))
        cookie = self._session_cookie(response)
        self.assertIsNotNone(cookie, "staff sessiyası brauzer-bağlanma rejiminə keçəndə kuki yenidən göndərilir")
        self.assertEqual(cookie["max-age"], "")
        self.assertEqual(cookie["expires"], "")
        self.assertTrue(client.session.get_expire_at_browser_close())

    def test_student_session_stays_persistent_by_default(self):
        client = self._client(self.student)
        client.get(reverse("home"))
        self.assertFalse(client.session.get_expire_at_browser_close())
        self.assertEqual(client.session[session_policy.KIND_KEY]["kind"], "student")

    @override_settings(SESSION_BROWSER_CLOSE_SCOPE="all")
    def test_scope_all_includes_students(self):
        client = self._client(self.student)
        client.get(reverse("home"))
        self.assertTrue(client.session.get_expire_at_browser_close())

    def test_switching_off_restores_persistent_cookie_for_existing_sessions(self):
        client = self._client(self.teacher)
        client.get(reverse("home"))
        self.assertTrue(client.session.get_expire_at_browser_close())
        with override_settings(SESSION_BROWSER_CLOSE_SCOPE="off"):
            response = client.get(reverse("home"))
        self.assertFalse(client.session.get_expire_at_browser_close())
        self.assertNotEqual(self._session_cookie(response)["max-age"], "")


@override_settings(RUNTIME_SETTINGS_ENABLED=True, CACHES=LOCMEM)
class RuntimeOverrideTest(_Base):
    def setUp(self):
        RuntimeSetting.objects.all().delete()
        rs.invalidate()

    def tearDown(self):
        rs.invalidate()

    def test_rim_override_of_scope_and_minutes_is_respected(self):
        self.assertEqual(rs.get("session.browser_close_scope"), "staff")
        self.assertEqual(rs.get("journal.idle_close_minutes"), 30)
        RuntimeSetting.objects.create(key="session.browser_close_scope", value="off")
        RuntimeSetting.objects.create(key="session.presence_minutes", value=45)
        RuntimeSetting.objects.create(key="journal.idle_close_minutes", value=0)
        rs.invalidate()
        client = self._client(self.teacher)
        client.get(reverse("home"))
        self.assertFalse(client.session.get_expire_at_browser_close())
        from core import runtime_settings_session

        self.assertEqual(runtime_settings_session.presence_seconds(), 45 * 60)
        self.assertEqual(runtime_settings_session.journal_idle_minutes(), 0)

    def test_invalid_scope_value_falls_back_to_default(self):
        RuntimeSetting.objects.create(key="session.browser_close_scope", value="everyone-please")
        rs.invalidate()
        self.assertEqual(rs.get("session.browser_close_scope"), "staff")


@override_settings(**PRESENCE_ON)
class PresenceTimeoutTest(_Base):
    def test_teacher_logged_out_after_browser_was_gone(self):
        client = self._client(self.teacher)
        client.get(reverse("home"))
        self._age(client, session_policy.SEEN_KEY, 45)
        response = client.get(reverse("home"))
        self.assertFalse(response.wsgi_request.user.is_authenticated)
        self.assertEqual(client.session.get(session_policy.ENDED_KEY), session_policy.REASON_PRESENCE)

    def test_recent_presence_keeps_session(self):
        client = self._client(self.teacher)
        client.get(reverse("home"))
        self._age(client, session_policy.SEEN_KEY, 20)
        response = client.get(reverse("home"))
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_student_not_affected_in_default_scope(self):
        client = self._client(self.student)
        client.get(reverse("home"))
        self._age(client, session_policy.SEEN_KEY, 300)
        response = client.get(reverse("home"))
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    @override_settings(SESSION_BROWSER_CLOSE_SCOPE="all")
    def test_exam_hall_session_is_never_ended(self):
        client = self._client(self.student)
        client.get(reverse("home"))
        session = client.session
        session[CENTER_SESSION_KEY] = 123
        session[session_policy.SEEN_KEY] = (timezone.now() - timedelta(hours=3)).isoformat()
        session["last_activity"] = (timezone.now() - timedelta(days=5)).isoformat()
        session.save()
        response = client.get(reverse("home"))
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    @override_settings(SESSION_BROWSER_CLOSE_SCOPE="all")
    def test_in_progress_exam_attempt_is_never_ended(self):
        from apps.exams.models import Exam, ExamAttempt

        exam = Exam.objects.create(title="SP exam", author=self.teacher, organization=self.org, is_active=True)
        ExamAttempt.objects.create(user=self.student, exam=exam, attempt_number=1, status="in_progress")
        client = self._client(self.student)
        client.get(reverse("home"))
        self._age(client, session_policy.SEEN_KEY, 120)
        response = client.get(reverse("home"))
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    @override_settings(SESSION_BROWSER_CLOSE_SCOPE="all")
    def test_draft_saved_exam_attempt_is_never_ended(self):
        """«Qaralama saxla» cəhdi `draft` edir — imtahan hələ gedir, sessiya bitirilmir."""
        from apps.exams.models import Exam, ExamAttempt

        exam = Exam.objects.create(title="SP draft exam", author=self.teacher, organization=self.org, is_active=True)
        ExamAttempt.objects.create(user=self.student, exam=exam, attempt_number=1, status="draft")
        client = self._client(self.student)
        client.get(reverse("home"))
        self._age(client, session_policy.SEEN_KEY, 120)
        response = client.get(reverse("home"))
        self.assertTrue(response.wsgi_request.user.is_authenticated)

    def test_ajax_request_gets_localized_401_instead_of_raw_error(self):
        client = self._client(self.teacher)
        client.get(reverse("home"))
        self._age(client, session_policy.SEEN_KEY, 45)
        client.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"
        response = client.get(reverse("home"), HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 401)
        payload = response.json()
        self.assertTrue(payload["session_expired"])
        self.assertEqual(payload["reason"], "presence")
        self.assertIn("browser was closed", payload["message"])
        self.assertEqual(payload["login_url"], settings.LOGIN_URL)

    def test_login_page_explains_why_once_in_users_language(self):
        client = self._client(self.teacher)
        client.get(reverse("home"))
        self._age(client, session_policy.SEEN_KEY, 45)
        client.get(reverse("home"))
        page = client.get(reverse("accounts:login")).content.decode()
        self.assertIn("Brauzer bağlandığı və ya kompüter söndüyü üçün", page)
        again = client.get(reverse("accounts:login")).content.decode()
        self.assertNotIn("Brauzer bağlandığı və ya kompüter söndüyü üçün", again)


class IdleTimeoutTest(_Base):
    def test_idle_logout_sets_reason_and_staff_login_shows_it(self):
        client = self._client(self.teacher)
        client.get(reverse("home"))
        self._age(client, "last_activity", 60 * 24 * 5)
        client.get(reverse("home"))
        self.assertEqual(client.session.get(session_policy.ENDED_KEY), session_policy.REASON_IDLE)
        page = client.get(reverse("accounts:staff_login")).content.decode()
        self.assertIn("Uzun müddət heç bir əməliyyat edilmədiyi üçün", page)


@override_settings(**PRESENCE_ON)
class SessionPingTest(_Base):
    def test_anonymous_ping_reports_not_authenticated_with_fresh_token(self):
        response = Client().get(reverse("accounts:session_ping"))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["authenticated"])
        self.assertTrue(payload["csrf_token"])
        self.assertIn("no-cache", response.get("Cache-Control", "") + response.get("Expires", "no-cache"))

    def test_teacher_ping_returns_token_and_heartbeat(self):
        client = self._client(self.teacher)
        payload = client.get(reverse("accounts:session_ping")).json()
        self.assertTrue(payload["authenticated"])
        self.assertTrue(payload["csrf_token"])
        self.assertEqual(payload["presence_seconds"], 30 * 60)
        self.assertEqual(payload["heartbeat_seconds"], 300)

    def test_background_ping_is_presence_but_not_activity(self):
        client = self._client(self.teacher)
        client.get(reverse("home"))
        self._age(client, "last_activity", 10)
        self._age(client, session_policy.SEEN_KEY, 10)
        before = client.session["last_activity"]
        client.get(reverse("accounts:session_ping"), {"active": "0"})
        self.assertEqual(client.session["last_activity"], before)
        seen = session_policy.parse_stamp(client.session[session_policy.SEEN_KEY])
        self.assertLess((timezone.now() - seen).total_seconds(), 60)

        client.get(reverse("accounts:session_ping"), {"active": "1"})
        self.assertNotEqual(client.session["last_activity"], before)

    def test_background_pings_do_not_extend_idle_limit(self):
        client = self._client(self.teacher)
        client.get(reverse("home"))
        self._age(client, "last_activity", 60 * 24 * 5)
        response = client.get(reverse("accounts:session_ping"), {"active": "0"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["reason"], "idle")


class CsrfFailureJsonTest(_Base):
    def test_ajax_csrf_failure_is_json_and_localized(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.teacher)
        client.cookies[settings.LANGUAGE_COOKIE_NAME] = "az"
        response = client.post(reverse("accounts:logout"), HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 403)
        payload = response.json()
        self.assertTrue(payload["csrf_failed"])
        self.assertEqual(payload["message"], "Köhnəlmiş təhlükəsizlik tokeni — səhifə yenilənməlidir.")

    def test_html_csrf_failure_page_follows_language_cookie(self):
        client = Client(enforce_csrf_checks=True)
        client.cookies[settings.LANGUAGE_COOKIE_NAME] = "az"
        response = client.post(reverse("accounts:staff_login"), {"username": "x", "password": "y"})
        self.assertEqual(response.status_code, 403)
        body = response.content.decode()
        self.assertIn("Səhifə köhnəlib", body)
        self.assertNotIn("Page expired", body)


class LanguageCookieTest(TestCase):
    def test_language_choice_survives_browser_restart(self):
        self.assertGreaterEqual(settings.LANGUAGE_COOKIE_AGE, 365 * 24 * 60 * 60)
        response = Client().post(reverse("set_language"), {"language": "ru", "next": "/"})
        cookie = response.cookies[settings.LANGUAGE_COOKIE_NAME]
        self.assertEqual(cookie.value, "ru")
        self.assertNotEqual(cookie["max-age"], "")


class KeepaliveMarkupTest(_Base):
    def _render(self, template, user):
        request = RequestFactory().get("/")
        request.user = user
        client = self._client(user)
        request.session = client.session
        return render_to_string(template, {"request": request}, request=request)

    @override_settings(**PRESENCE_ON)
    def test_partial_renders_ping_config_for_teacher(self):
        html = self._render("partials/_session_keepalive.html", self.teacher)
        self.assertIn('data-ping-url="%s"' % reverse("accounts:session_ping"), html)
        self.assertIn('data-presence="1800"', html)
        self.assertIn('data-heartbeat="300"', html)
        self.assertIn("js/core/session_keepalive.js", html)

    def test_base_page_loads_dialog_css_and_script_only_for_signed_in_users(self):
        html = self._client(self.teacher).get(reverse("accounts:profile")).content.decode()
        self.assertIn("css/session_keepalive.css", html)
        self.assertIn("data-ems-session", html)
        anonymous = Client().get(reverse("home")).content.decode()
        self.assertNotIn("data-ems-session", anonymous)
        self.assertNotIn("css/session_keepalive.css", anonymous)

    def test_journal_idle_partial_follows_setting(self):
        html = self._render("registrar/partials/_jd_idle_close.html", self.teacher)
        self.assertIn('data-minutes="30"', html)
        self.assertIn("30 dəqiqə heç bir əməliyyat edilmədiyi üçün jurnal", html)
        with override_settings(JOURNAL_IDLE_CLOSE_MINUTES=0):
            self.assertNotIn("data-jd-idle", self._render("registrar/partials/_jd_idle_close.html", self.teacher))
