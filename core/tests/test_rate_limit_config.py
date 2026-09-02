"""P2-5 reqressiya: yararsız rate-limit dəyəri SÜKUTLA limiti söndürməməlidir.

2026-09-02 auditi: `*_RATE_LIMIT` env dəyərində bir hərflik səhv (`5/10min`
əvəzinə `5/10m`) həmin limiteri — LOGIN və OTP daxil — heç bir xəbərdarlıq
olmadan sıradan çıxara bilirdi.

İki qat qapadılır:
1. **Başlanğıc** — `config/settings/components/admin_ratelimit.py` bütün
   `*_RATE_LIMIT` dəyərlərini yükləmə anında parse edir və yararsız dəyərdə
   `ImproperlyConfigured` atır (səhv konfiqurasiya deploy-a keçmir).
2. **İcra** — `core.rate_limit` parse xətasında LOG yazır və FAIL-CLOSED olur
   (limitsiz keçid yox).
"""

from __future__ import annotations

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings

from core.rate_limit import (
    is_rate_limited,
    parse_rate,
    record_rate_limit_hit,
    validate_rate_limit_settings,
)


class RateLimitParsingTests(SimpleTestCase):
    def test_valid_specs_parse(self):
        self.assertEqual(parse_rate("5/10m").limit, 5)
        self.assertEqual(parse_rate("5/10m").window_seconds, 600)
        self.assertEqual(parse_rate("3/10s").window_seconds, 10)
        self.assertEqual(parse_rate("100/1h").window_seconds, 3600)

    def test_typo_raises(self):
        with self.assertRaises(ValueError):
            parse_rate("5/10min")

    @override_settings(RATELIMIT_ENABLE=True)
    def test_runtime_fails_closed_on_unparseable_spec(self):
        limited, retry_after = is_rate_limited("probe.scope", "5/10min", "actor")
        self.assertTrue(limited)
        self.assertIsNotNone(retry_after)

        limited, _retry = record_rate_limit_hit("probe.scope", "5/10min", "actor")
        self.assertTrue(limited)

    @override_settings(RATELIMIT_ENABLE=True)
    def test_failure_log_does_not_echo_the_spec_value(self):
        """CodeQL `py/clear-text-logging-sensitive-data` reqressiyası.

        Spesifikasiya `RIM_PASSWORD_RESET_RATE_LIMIT` kimi həssas adlı
        konfiqlərdən gəlir — log-a yalnız SCOPE adı düşməlidir.
        """
        with self.assertLogs("core.rate_limit", level="ERROR") as captured:
            is_rate_limited("probe.scope", "5/10min", "actor")
        joined = "\n".join(captured.output)
        self.assertIn("probe.scope", joined)
        self.assertNotIn("5/10min", joined)

    @override_settings(RATELIMIT_ENABLE=True)
    def test_empty_spec_stays_an_explicit_disable(self):
        # Boş dəyər QƏSDƏN söndürmədir — səhv yazı deyil, ona görə buraxılır.
        self.assertEqual(is_rate_limited("probe.scope", "", "actor"), (False, None))


class RateLimitSettingsValidationTests(SimpleTestCase):
    """Ayarlar modulunun validatoru yararsız dəyərdə start-up-da çökür."""

    def _validator(self):
        return validate_rate_limit_settings

    def test_clean_namespace_passes(self):
        self._validator()({"LOGIN_RATE_LIMIT": "5/10m", "OTP_VERIFY_RATE_LIMIT": "5/10m"})

    def test_typo_in_any_setting_raises_improperly_configured(self):
        with self.assertRaises(ImproperlyConfigured) as ctx:
            self._validator()({"LOGIN_RATE_LIMIT": "5/10min", "OTP_VERIFY_RATE_LIMIT": "5/10m"})
        self.assertIn("LOGIN_RATE_LIMIT", str(ctx.exception))

    def test_non_rate_settings_are_ignored(self):
        self._validator()({"SOME_OTHER_SETTING": "not-a-rate", "DEBUG": "True"})
