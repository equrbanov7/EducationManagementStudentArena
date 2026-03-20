"""
Model tests for live_exam app.
"""

import secrets

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.exams.models import Exam
from apps.live_exam.models import PIN_LENGTH, LiveSession, generate_pin

User = get_user_model()


class GeneratePinTest(TestCase):
    """Tests for the PIN generation function."""

    def test_pin_uses_correct_length(self):
        """generate_pin() must produce exactly PIN_LENGTH digits."""
        pin = generate_pin()
        self.assertEqual(len(pin), PIN_LENGTH)

    def test_pin_is_eight_digits(self):
        """PIN_LENGTH is now 10 (increased for security); generated PINs must be 10 characters long."""
        self.assertEqual(PIN_LENGTH, 10)
        pin = generate_pin()
        self.assertEqual(len(pin), 10)

    def test_pin_contains_only_digits(self):
        """Generated PINs must consist of uppercase alphanumeric characters (digits + A-Z)."""
        import string
        allowed = set(string.digits + string.ascii_uppercase)
        for _ in range(50):
            pin = generate_pin()
            invalid = set(pin) - allowed
            self.assertFalse(invalid, f"Unexpected characters in PIN: {invalid!r} (PIN={pin!r})")

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


class LiveSessionPinFieldTest(TestCase):
    """
    Regression tests for the LiveSession.pin field length.

    The original database schema created pin as character varying(6).
    PIN_LENGTH was later changed to 8 and migration 0006 widens the column.
    These tests ensure the model field definition and the constant stay in sync,
    so that a future PIN_LENGTH change without a matching migration is caught
    immediately in CI.
    """

    def test_pin_field_max_length_matches_constant(self):
        """LiveSession.pin max_length must equal PIN_LENGTH."""
        field = LiveSession._meta.get_field("pin")
        self.assertEqual(
            field.max_length,
            PIN_LENGTH,
            f"LiveSession.pin max_length ({field.max_length}) does not match "
            f"PIN_LENGTH ({PIN_LENGTH}). Create a migration to widen the column.",
        )

    def test_pin_field_max_length_is_eight(self):
        """Guard: PIN_LENGTH is now 10 (increased for security) and pin field reflects that."""
        self.assertEqual(PIN_LENGTH, 10)
        field = LiveSession._meta.get_field("pin")
        self.assertEqual(field.max_length, 10)

    def test_create_live_session_with_eight_char_pin(self):
        """
        Creating a LiveSession must succeed when the pin is exactly PIN_LENGTH
        characters long (regression for DataError: value too long for
        character varying(6)).
        """
        from apps.accounts.models import ProfileRole
        from apps.organizations.models import Organization
        from core.constants import OrganizationType

        teacher = User.objects.create_user(
            username="pin_test_teacher",
            email="pin_test@example.com",
            password="StrongPass123!",
        )
        teacher.profile.role = ProfileRole.TEACHER
        teacher.profile.save(update_fields=["role", "updated_at"])

        org = Organization.objects.create(
            name="Pin Test Org",
            org_type=OrganizationType.SCHOOL,
            owner=teacher,
            status="active",
            is_active=True,
        )
        teacher.profile.organization = org
        teacher.profile.organization_type = org.org_type
        teacher.profile.save(update_fields=["organization", "organization_type", "updated_at"])

        exam = Exam.objects.create(
            title="Pin Length Regression Exam",
            slug="pin-length-regression-exam",
            author=teacher,
            is_active=True,
        )
        session = LiveSession.objects.create(exam=exam, host_user=teacher)
        self.assertEqual(len(session.pin), PIN_LENGTH)
        # PIN is now alphanumeric (digits + A-Z), not purely numeric.
        import string
        allowed = set(string.digits + string.ascii_uppercase)
        self.assertTrue(set(session.pin).issubset(allowed))
        # Verify the saved row is retrievable (no silent DB truncation).
        reloaded = LiveSession.objects.get(pk=session.pk)
        self.assertEqual(reloaded.pin, session.pin)
