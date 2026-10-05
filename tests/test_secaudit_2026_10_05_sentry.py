"""Təhlükəsizlik auditi 2026-10-05 — Sentry sorğu gövdəsini (sorğu cavabları, imtahan
cavabları, parollar) HEÇ VAXT göndərməməlidir.

``sentry_sdk``-nin defoltu ``max_request_body_size="medium"``-dir: xəta zamanı POST
gövdəsi (≤ 10 KB) hadisəyə əlavə olunur — anonim sorğu cavabları da daxil olmaqla.
"""

from __future__ import annotations

import sys
import types
from unittest import mock

from django.test import TestCase

from tests import test_security_configuration as _security_configuration


def _fake_sentry_modules():
    sdk = types.ModuleType("sentry_sdk")
    sdk.init = mock.MagicMock(name="sentry_sdk.init")
    integrations = types.ModuleType("sentry_sdk.integrations")
    modules = {"sentry_sdk": sdk, "sentry_sdk.integrations": integrations}
    for name, cls in (("celery", "CeleryIntegration"), ("django", "DjangoIntegration"), ("redis", "RedisIntegration")):
        module = types.ModuleType(f"sentry_sdk.integrations.{name}")
        setattr(module, cls, mock.MagicMock(name=cls))
        modules[module.__name__] = module
    return sdk, modules


class SentryRequestBodyTest(TestCase):
    def test_sentry_never_sends_request_bodies_or_pii(self):
        sdk, modules = _fake_sentry_modules()
        with mock.patch.dict(sys.modules, modules):
            _security_configuration.ProductionAdminAllowlistSettingsTest._load_production_settings(
                ADMIN_ALLOWED_IPS="", SENTRY_DSN="https://key@sentry.example.com/1"
            )
        sdk.init.assert_called_once()
        kwargs = sdk.init.call_args.kwargs
        self.assertEqual(kwargs["max_request_body_size"], "never")
        self.assertIs(kwargs["send_default_pii"], False)
