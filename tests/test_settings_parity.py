"""Audit 2026-09-28 AD-04: base-in hər ayarı production və local-da da olmalıdır.

`production.py` / `local.py` əvvəl `from .base import (...)` açıq siyahısı ilə
idxal edirdi; siyahıya düşməyən komponent ayarı (22 ədəd: AI_ASSISTANT_ENABLED,
AUTH_OTP_*, FINAL_EXAM_PIN_*, MONITORING_*_URL …) səssizcə yox olurdu və sahib
açarları təsirsiz qalırdı. İndi `from .base import *` + açıq override-lar; bu
test siyahı yenidən yaranarsa (və ya ad düşərsə) qırılır.
"""

from __future__ import annotations

import importlib
import os
import sys
from unittest.mock import patch

from django.test import TestCase

PRODUCTION_ENV = {
    "SECRET_KEY": "test-secret-key-for-production-imports-only",
    "DATABASE_URL": "sqlite:////tmp/emsarena-production-settings-test.sqlite3",
    "ALLOWED_HOSTS": "example.com",
    "ADMIN_URL_PREFIX": "manage/",
    "ADMIN_2FA_REQUIRED": "True",
    "SITE_URL": "https://example.com",
    "SECURE_SSL_REDIRECT": "True",
    "SESSION_COOKIE_SECURE": "True",
    "CSRF_COOKIE_SECURE": "True",
}


def _fresh_import(module_name: str, env: dict[str, str]):
    """Modulu verilmiş env ilə TƏZƏDƏN yükləyir (base daxil — env base-də oxunur)."""
    names = ("config.settings.base", module_name)
    with patch.dict(os.environ, env, clear=False):
        saved = {name: sys.modules.pop(name, None) for name in names}
        try:
            return importlib.import_module(module_name)
        finally:
            for name, module in saved.items():
                sys.modules.pop(name, None)
                if module is not None:
                    sys.modules[name] = module


def _setting_names(module) -> set[str]:
    return {name for name in dir(module) if name.isupper() and not name.startswith("_")}


class SettingsParityTest(TestCase):
    def _base_names(self, env):
        return _setting_names(_fresh_import("config.settings.base", env))

    def test_production_defines_every_base_setting(self):
        production = _fresh_import("config.settings.production", PRODUCTION_ENV)
        missing = sorted(self._base_names(PRODUCTION_ENV) - _setting_names(production))
        self.assertEqual(missing, [], f"production.py base ayarlarını itirir: {missing}")

    def test_local_defines_every_base_setting(self):
        env = {"DATABASE_URL": PRODUCTION_ENV["DATABASE_URL"]}
        local = _fresh_import("config.settings.local", env)
        missing = sorted(self._base_names(env) - _setting_names(local))
        self.assertEqual(missing, [], f"local.py base ayarlarını itirir: {missing}")

    def test_owner_switches_reach_production(self):
        """Audit-in env probu: sahib açarları production-da həqiqətən təsir edir."""
        production = _fresh_import(
            "config.settings.production",
            {
                **PRODUCTION_ENV,
                "AI_ASSISTANT_ENABLED": "false",
                "AUTH_OTP_MAX_ATTEMPTS": "2",
                "FINAL_EXAM_PIN_MAX_FAILURES": "3",
                "LOGIN_ACCOUNT_RATE_LIMIT": "7/1h",
                "LIVE_PIN_IP_RATE_LIMIT": "9/10m",
            },
        )
        self.assertFalse(production.AI_ASSISTANT_ENABLED)
        self.assertEqual(production.AUTH_OTP_MAX_ATTEMPTS, 2)
        self.assertEqual(production.FINAL_EXAM_PIN_MAX_FAILURES, 3)
        self.assertEqual(production.LOGIN_ACCOUNT_RATE_LIMIT, "7/1h")
        self.assertEqual(production.LIVE_PIN_IP_RATE_LIMIT, "9/10m")

    def test_new_rate_limit_defaults_match_code_fallbacks(self):
        from apps.accounts.views.auth.constants import (
            LOGIN_ACCOUNT_DISTINCT_IP_ALERT_DEFAULT,
            LOGIN_ACCOUNT_RATE_LIMIT_DEFAULT,
        )
        from apps.live_exam.views.player.constants import (
            LIVE_JOIN_IP_RATE_LIMIT_DEFAULT,
            LIVE_PIN_IP_RATE_LIMIT_DEFAULT,
        )

        clean = {
            name: ""
            for name in (
                "LOGIN_ACCOUNT_RATE_LIMIT",
                "LOGIN_ACCOUNT_DISTINCT_IP_ALERT",
                "LIVE_EXAM_JOIN_IP_RATE_LIMIT",
                "LIVE_PIN_IP_RATE_LIMIT",
            )
        }
        with patch.dict(os.environ, clean):
            for name in clean:
                os.environ.pop(name)
            base = _fresh_import("config.settings.base", {})
        self.assertEqual(base.LOGIN_ACCOUNT_RATE_LIMIT, LOGIN_ACCOUNT_RATE_LIMIT_DEFAULT)
        self.assertEqual(base.LOGIN_ACCOUNT_DISTINCT_IP_ALERT, LOGIN_ACCOUNT_DISTINCT_IP_ALERT_DEFAULT)
        self.assertEqual(base.LIVE_EXAM_JOIN_IP_RATE_LIMIT, LIVE_JOIN_IP_RATE_LIMIT_DEFAULT)
        self.assertEqual(base.LIVE_PIN_IP_RATE_LIMIT, LIVE_PIN_IP_RATE_LIMIT_DEFAULT)

    def test_deleted_otp_routes_are_not_in_request_queue_exclusions(self):
        base = _fresh_import("config.settings.base", {})
        for gone in ("/accounts/send-otp/", "/accounts/verify-otp/", "/accounts/resend-otp/"):
            self.assertNotIn(gone, base.REQUEST_QUEUE_EXCLUDED_PATH_PREFIXES)
