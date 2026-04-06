from django.test import SimpleTestCase, override_settings

from apps.accounts.models import ProfileRole
from apps.accounts.services.pending_registration import (
    clear_pending_registration,
    get_pending_registration,
    store_pending_registration,
)
from core.constants import OrganizationType


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.dummy.DummyCache",
        }
    }
)
class PendingRegistrationCacheFallbackTest(SimpleTestCase):
    def setUp(self):
        self.email = "pending@example.com"
        clear_pending_registration(self.email)

    def tearDown(self):
        clear_pending_registration(self.email)

    def test_dummy_cache_uses_process_local_fallback(self):
        store_pending_registration(
            {
                "username": "pending-user",
                "email": self.email,
                "password": "StrongPass123!",
                "first_name": "Pending",
                "last_name": "User",
                "country": "AZ",
                "organization_type": OrganizationType.INDIVIDUAL,
                "signup_mode": "individual",
                "join_organization": None,
                "institution_not_listed_name": "",
                "organization_identifier": "",
                "organization_license_identifier": "",
                "initial_role": ProfileRole.ORG_ADMIN,
                "phone": "",
                "specialization": "",
                "group_number": "",
                "department": "",
                "staff_position": "",
            }
        )

        payload = get_pending_registration(self.email)

        self.assertIsNotNone(payload)
        self.assertEqual(payload["email"], self.email)
        self.assertEqual(payload["username"], "pending-user")
