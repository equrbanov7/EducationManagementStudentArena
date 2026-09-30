"""Ad moderasiyası — ``screen_names``: audit izi, IP, maska, rate-limit (sahib 2026-09-30, WP MOD).

* rədd olunan cəhd MÖVCUD audit jurnalına düşür (``action=deny``,
  ``resource_type=moderation.profanity_blocked``): istifadəçi / anonim, etibarlı
  IP (``TRUSTED_PROXY_HOPS``), user-agent, yol, sahə, təşkilat; dəyərin ÖZÜ yox —
  yalnız maska + HMAC izi;
* aktor başına 5 cəhddən sonra NALAYİQ ad 429 (təmiz ad 2026-09-30-dan keçir; IP ilə kilid yoxdur); başqa
  aktor (eyni NAT IP-də olsa belə) təsirlənmir;
* IP tavanı yalnız audit yazısını kəsir, rədd davam edir;
* audit yazısı sınsa belə rədd verilir və transaksiya zədələnmir;
* audit jurnalının «Nalayiq ad cəhdləri» süzgəci (superadmin / RİM rəhbəri — yalnız oxu).
"""

from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.audit.views_filters import FLAG_PROFANITY, apply_filters, parse_filters, scoped_queryset
from core import rate_limit as rate_limit_module
from core.constants import AuditAction
from core.moderation.enforcement import (
    PROFANITY_RESOURCE_TYPE,
    rate_limited_message,
    rejection_message,
    screen_name,
    screen_names,
    value_digest,
)

User = get_user_model()
UA = "Mozilla/5.0 (MOD test)"


def _request(user=None, *, ip="203.0.113.7", forwarded=None, path="/accounts/profile/"):
    extra = {"REMOTE_ADDR": ip, "HTTP_USER_AGENT": UA}
    if forwarded:
        extra["HTTP_X_FORWARDED_FOR"] = forwarded
    request = RequestFactory().post(path, **extra)
    request.user = user or AnonymousUser()
    return request


def _rows():
    return AuditLog.objects.filter(resource_type=PROFANITY_RESOURCE_TYPE).order_by("created_at")


class ScreenNamesAuditTest(TestCase):
    def setUp(self):
        rate_limit_module._RATE_LIMIT_FALLBACK_CACHE.clear()
        self.user = User.objects.create_user("mod_user", "mod_user@example.com", "StrongPass123!")

    def test_clean_names_pass_without_audit(self):
        self.assertIsNone(screen_names(_request(self.user), {"f.first_name": "Səmədov", "f.last_name": "Pənahov"}))
        self.assertIsNone(screen_names(_request(self.user), {"f.first_name": "", "f.last_name": None}))
        self.assertFalse(_rows().exists())

    def test_blocked_attempt_is_logged_with_who_where_when(self):
        rejection = screen_names(
            _request(self.user, forwarded="198.51.100.4"),
            {"accounts.profile.first_name": "Kamran", "accounts.profile.last_name": "Siktirov"},
            target=self.user,
        )
        self.assertIsNotNone(rejection)
        self.assertEqual(rejection.status, 400)
        self.assertEqual(rejection.field, "accounts.profile.last_name")
        self.assertEqual(rejection.field_name, "last_name")
        self.assertEqual(rejection.message, rejection_message())
        self.assertNotIn("iktir", rejection.message.lower())

        row = _rows().get()
        self.assertEqual(row.action, AuditAction.DENY)
        self.assertEqual(row.user_id, self.user.pk)
        # Etibarlı proxy semantikası (TRUSTED_PROXY_HOPS=1): X-Forwarded-For-un SAĞ üzvü.
        self.assertEqual(row.ip_address, "198.51.100.4")
        self.assertEqual(row.user_agent, UA)
        self.assertIsNotNone(row.created_at)
        self.assertEqual(row.resource_repr, "accounts.profile.last_name")
        self.assertEqual(row.resource_id, str(self.user.pk))
        values = row.new_values
        self.assertEqual(values["field"], "accounts.profile.last_name")
        self.assertEqual(values["value_masked"], "S*******")
        self.assertEqual(values["value_hmac"], value_digest("Siktirov"))
        self.assertEqual(values["language"], "az")
        self.assertEqual(values["path"], "/accounts/profile/")
        self.assertFalse(values["anonymous"])
        self.assertNotIn("iktir", str(values).lower())
        self.assertNotIn("iktir", row.reason.lower())

    def test_anonymous_attempt_logs_the_live_client_id(self):
        rejection = screen_name(_request(), "live_exam.join.nickname", "blyat", client_id="cid-123", context={"x": 1})
        self.assertEqual(rejection.status, 400)
        row = _rows().get()
        self.assertIsNone(row.user_id)
        self.assertEqual(row.ip_address, "203.0.113.7")
        self.assertEqual(row.new_values["live_client_id"], "cid-123")
        self.assertTrue(row.new_values["anonymous"])
        self.assertEqual(row.new_values["x"], 1)

    def test_same_value_gets_the_same_fingerprint_regardless_of_case(self):
        self.assertEqual(value_digest("Siktir"), value_digest("  SİKTİR "))
        self.assertNotEqual(value_digest("Siktir"), value_digest("Sikdir"))

    def test_service_call_without_request_still_blocks_and_logs(self):
        rejection = screen_name(None, "accounts.rim.edit.first_name", "fuck")
        self.assertEqual(rejection.status, 400)
        row = _rows().get()
        self.assertIsNone(row.ip_address)

    def test_audit_failure_does_not_disable_moderation(self):
        with mock.patch("core.moderation.enforcement.log_action", side_effect=RuntimeError("db down")):
            rejection = screen_name(_request(self.user), "f", "siktir")
        self.assertEqual(rejection.status, 400)
        # Transaksiya zədələnməyib — sonrakı sorğu işləyir.
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())
        self.assertFalse(_rows().exists())


class ScreenNamesRateLimitTest(TestCase):
    def setUp(self):
        rate_limit_module._RATE_LIMIT_FALLBACK_CACHE.clear()
        self.user = User.objects.create_user("mod_rl", "mod_rl@example.com", "StrongPass123!")
        self.other = User.objects.create_user("mod_rl2", "mod_rl2@example.com", "StrongPass123!")

    def test_repeated_attempts_lock_the_actor_not_the_whole_ip(self):
        for index in range(5):
            rejection = screen_name(_request(self.user), "f", f"siktir{index}")
            self.assertEqual(rejection.status, 400, index)
        self.assertTrue(_rows().last().new_values["lock_engaged"])

        locked = screen_name(_request(self.user), "f", "siktir")
        self.assertEqual(locked.status, 429)
        self.assertEqual(locked.message, rate_limited_message())
        self.assertTrue(locked.rate_limited)
        self.assertEqual(_rows().count(), 5)  # kilidli cəhdlər jurnalı doldurmur
        # 2026-09-30 (M6): təmiz ad kilid altında da keçir.
        self.assertIsNone(screen_name(_request(self.user), "f", "Səmədov"))

        # Eyni IP (sinfin NAT-ı), başqa istifadəçi — təsirlənmir.
        self.assertIsNone(screen_name(_request(self.other), "f", "Səmədov"))

    def test_anonymous_clients_behind_one_ip_are_separate(self):
        for index in range(5):
            screen_name(_request(), "live_exam.join.nickname", f"fuck{index}", client_id="cid-a")
        self.assertEqual(screen_name(_request(), "live_exam.join.nickname", "fuck9", client_id="cid-a").status, 429)
        self.assertIsNone(screen_name(_request(), "live_exam.join.nickname", "Ali", client_id="cid-a"))
        self.assertEqual(screen_name(_request(), "live_exam.join.nickname", "fuck9", client_id="cid-b").status, 400)

    def test_cookieless_attempts_are_never_locked_by_shared_ip(self):
        for index in range(7):
            rejection = screen_name(_request(), "live_exam.join.nickname", f"fuck{index}")
            self.assertEqual(rejection.status, 400, index)
        self.assertIsNone(screen_name(_request(), "live_exam.join.nickname", "Ali"))

    @override_settings(PROFANITY_IP_LOG_RATE_LIMIT="2/10m")
    def test_ip_cap_limits_audit_rows_but_keeps_rejecting(self):
        for index in range(4):
            rejection = screen_name(_request(), "live_exam.join.nickname", "blyat", client_id=f"cid-{index}")
            self.assertEqual(rejection.status, 400)
        self.assertEqual(_rows().count(), 2)

    @override_settings(RATELIMIT_ENABLE=False)
    def test_disabled_rate_limit_never_locks(self):
        for _index in range(8):
            self.assertEqual(screen_name(_request(self.user), "f", "siktir").status, 400)


class AuditProfanityFilterTest(TestCase):
    def setUp(self):
        rate_limit_module._RATE_LIMIT_FALLBACK_CACHE.clear()
        self.superuser = User.objects.create_superuser("mod_root", "mod_root@example.com", "StrongPass123!")
        screen_name(_request(), "live_exam.join.nickname", "orospu", client_id="cid-f")
        AuditLog.objects.create(action=AuditAction.DENY, resource_type="User", reason="başqa rədd")

    def test_flag_filters_only_profanity_rows(self):
        request = RequestFactory().get("/", {"al_flag": FLAG_PROFANITY, "al_range": "all"})
        filters = parse_filters(request, is_superadmin=True)
        self.assertEqual(filters["flag"], FLAG_PROFANITY)
        rows = list(apply_filters(scoped_queryset(is_superadmin=True, organization=None), filters))
        self.assertEqual([row.resource_type for row in rows], [PROFANITY_RESOURCE_TYPE])

    def test_superadmin_sees_the_filtered_list_read_only(self):
        client = Client()
        client.force_login(self.superuser)
        response = client.get(reverse("audit:list"), {"al_flag": FLAG_PROFANITY, "al_range": "all"})
        self.assertEqual(response.status_code, 200)
        section = response.context["audit_log_section"]
        self.assertEqual(section["filtered_count"], 1)
        row = section["rows"][0]
        self.assertEqual(row["resource_label"], "live_exam.join.nickname")
        self.assertEqual(row["ip"], "203.0.113.7")
        detail = client.get(reverse("audit:detail", kwargs={"pk": row["id"]})).json()["entry"]
        self.assertEqual(detail["user_agent"], UA)
        self.assertEqual(detail["raw"]["new_values"]["value_masked"], "o*****")

    def test_anonymous_cannot_read_the_list(self):
        response = Client().get(reverse("audit:list"), {"al_flag": FLAG_PROFANITY})
        self.assertEqual(response.status_code, 302)
