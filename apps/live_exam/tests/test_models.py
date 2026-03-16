"""
Model tests for live_exam app.
"""

import secrets

from django.test import TestCase

from apps.live_exam.models import PIN_LENGTH, generate_pin


class GeneratePinTest(TestCase):
    """Tests for the PIN generation function."""

    def test_pin_uses_correct_length(self):
        """generate_pin() must produce exactly PIN_LENGTH digits."""
        pin = generate_pin()
        self.assertEqual(len(pin), PIN_LENGTH)

    def test_pin_is_eight_digits(self):
        """PIN_LENGTH is 8; generated PINs must be 8 characters long."""
        self.assertEqual(PIN_LENGTH, 8)
        pin = generate_pin()
        self.assertEqual(len(pin), 8)

    def test_pin_contains_only_digits(self):
        """Generated PINs must consist entirely of decimal digits."""
        for _ in range(50):
            pin = generate_pin()
            self.assertTrue(pin.isdigit(), f"Non-digit character found in PIN: {pin!r}")

    def test_pin_uses_secrets_module(self):
        """generate_pin() must not rely on the non-cryptographic random module."""
        import inspect
        import apps.live_exam.models as models_module

        source = inspect.getsource(models_module.generate_pin)
        self.assertIn("secrets", source, "generate_pin() must use the secrets module")
        self.assertNotIn("random.choices", source, "generate_pin() must not use random.choices")

    def test_pins_are_unique_across_many_calls(self):
        """Statistical uniqueness: 100 generated PINs should not all be identical."""
        pins = {generate_pin() for _ in range(100)}
        # With 10^8 possible values it is astronomically unlikely all 100 match.
        self.assertGreater(len(pins), 1)
