"""
EXAM-SEC-002 — ExamStudentPin login-yolunun per-username throttle-i.

Kritik tələb (istifadəçi qeydi): throttle YALNIZ username üzrə açar götürür,
paylaşılan IP üzrə YOX — belə ki, lokal test / NAT arxası imtahan zalında bir
tələbənin bloklanması digərlərini dondurmasın.
"""

from django.core.cache import cache
from django.test import TestCase, override_settings

from apps.exams.services.student_pins import student_pin_login_rate_limited


# DummyCache (test default) incr-i saxlamır — bu throttle Redis/LocMem tələb
# edir (entry.py rate-limiter-i ilə eyni). LocMem ilə real davranışı yoxlayırıq.
@override_settings(
    FINAL_EXAM_STUDENT_PIN_RATE_PER_MINUTE=5,
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "sp-throttle-test"}},
)
class StudentPinThrottleTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_allows_up_to_limit_then_blocks(self):
        for _ in range(5):
            self.assertFalse(student_pin_login_rate_limited("alice"))
        self.assertTrue(student_pin_login_rate_limited("alice"))

    def test_per_username_isolation_is_freeze_safe(self):
        """Bir tələbənin dolması digərini dondurmamalıdır (paylaşılan IP ssenarisi)."""
        for _ in range(20):
            student_pin_login_rate_limited("alice")
        self.assertFalse(student_pin_login_rate_limited("bob"))

    def test_case_and_whitespace_normalised(self):
        for _ in range(5):
            student_pin_login_rate_limited("  Alice ")
        self.assertTrue(student_pin_login_rate_limited("alice"))

    def test_blank_username_never_limited(self):
        for _ in range(50):
            self.assertFalse(student_pin_login_rate_limited("   "))

    def test_zero_limit_disables_throttle(self):
        with override_settings(FINAL_EXAM_STUDENT_PIN_RATE_PER_MINUTE=0):
            for _ in range(50):
                self.assertFalse(student_pin_login_rate_limited("alice"))
