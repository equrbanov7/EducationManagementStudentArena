"""Independent connection leases and atomic updates from parallel ASGI clients."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.core.cache import cache
from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from apps.exams.services.final_center import presence

# Keep the configured integration cache when present, and enable presence in the dummy-cache unit suite.
PRESENCE_TEST_CACHES = settings.CACHES
if PRESENCE_TEST_CACHES["default"]["BACKEND"] == "django.core.cache.backends.dummy.DummyCache":
    PRESENCE_TEST_CACHES = {
        "default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "waiting-presence"}
    }


@override_settings(CACHES=PRESENCE_TEST_CACHES)
class WaitingPresenceTests(SimpleTestCase):
    def setUp(self):
        self.session, self.ticket = 91, 92
        presence.drop_presence(self.session, self.ticket)
        self.addCleanup(presence.drop_presence, self.session, self.ticket)

    def test_expired_tab_has_no_effect_on_renewed_tab(self):
        start = timezone.now()
        with patch.object(presence.timezone, "now", return_value=start):
            presence.touch_presence(self.session, self.ticket, connection_id="early")
        with patch.object(presence.timezone, "now", return_value=start + timedelta(seconds=60)):
            presence.touch_presence(self.session, self.ticket, status="ready", connection_id="late")
        with patch.object(presence.timezone, "now", return_value=start + timedelta(seconds=95)):
            self.assertFalse(presence.drop_presence(self.session, self.ticket, connection_id="early"))
            self.assertEqual(presence.presence_map(self.session, [self.ticket])[self.ticket]["st"], "ready")
            self.assertTrue(presence.drop_presence(self.session, self.ticket, connection_id="late"))
            self.assertFalse(presence.drop_presence(self.session, self.ticket, connection_id="late"))

    def test_existing_heartbeat_and_administrative_ticket_removal(self):
        old = {"ts": timezone.now().isoformat(), "st": "waiting"}
        cache.set(presence._key(self.session, self.ticket), old, presence.PRESENCE_TTL_SECONDS)
        self.assertEqual(presence.presence_map(self.session, [self.ticket]), {self.ticket: old})
        presence.touch_presence(self.session, self.ticket, connection_id="current")
        self.assertTrue(presence.drop_presence(self.session, self.ticket))
        self.assertFalse(presence.drop_presence(self.session, self.ticket, connection_id="current"))
        self.assertEqual(presence.presence_map(self.session, []), {})

    def test_concurrent_tab_open_and_close_emits_only_one_final_removal(self):
        def touch(name):
            return presence.touch_presence(self.session, self.ticket, connection_id=name)

        def drop(name):
            return presence.drop_presence(self.session, self.ticket, connection_id=name)

        names = [f"tab-{i}" for i in range(10)]
        with ThreadPoolExecutor(max_workers=5) as workers:
            list(workers.map(touch, names))
            self.assertEqual(presence.connected_count(self.session, [self.ticket]), 1)
            results = list(workers.map(drop, names))
        self.assertEqual(sum(results), 1)
        self.assertEqual(presence.connected_count(self.session, [self.ticket]), 0)
