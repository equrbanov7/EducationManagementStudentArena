"""PIN yoxlama memo-su: təkrar uğurlu yoxlama hash-siz, səhv PIN həmişə tam hash (tutum testi 2026-10-05)."""

from unittest import mock

from django.contrib.auth.hashers import make_password
from django.test import SimpleTestCase

from apps.exams.services.final_center import pins


class PinVerifyMemoTests(SimpleTestCase):
    def setUp(self):
        pins._verified_pins.clear()
        self.encoded = make_password("12345678")

    def test_repeat_success_skips_hashing(self):
        with mock.patch.object(pins, "check_password", wraps=pins.check_password) as spy:
            self.assertTrue(pins.check_pin_hash("12345678", self.encoded))
            self.assertTrue(pins.check_pin_hash("12345678", self.encoded))
        self.assertEqual(spy.call_count, 1)

    def test_wrong_pin_always_hashes_and_never_cached(self):
        with mock.patch.object(pins, "check_password", wraps=pins.check_password) as spy:
            self.assertFalse(pins.check_pin_hash("00000000", self.encoded))
            self.assertFalse(pins.check_pin_hash("00000000", self.encoded))
        self.assertEqual(spy.call_count, 2)

    def test_reissued_hash_is_not_served_from_memo(self):
        self.assertTrue(pins.check_pin_hash("12345678", self.encoded))
        reissued = make_password("87654321")
        self.assertFalse(pins.check_pin_hash("12345678", reissued))

    def test_expired_entry_rehashes(self):
        self.assertTrue(pins.check_pin_hash("12345678", self.encoded))
        with mock.patch.object(pins.time, "monotonic", return_value=pins.time.monotonic() + 120):
            with mock.patch.object(pins, "check_password", wraps=pins.check_password) as spy:
                self.assertTrue(pins.check_pin_hash("12345678", self.encoded))
        self.assertEqual(spy.call_count, 1)
