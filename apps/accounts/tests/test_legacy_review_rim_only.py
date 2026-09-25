"""«Köçürülmüş nəticələr» — YALNIZ RİM rəhbəri və superadmin (sahibin qərarı, 2026-09-26).

Yoxlanan: menyu bəndi və bölmə paneli yalnız ``ikt_rehber`` üzvlüyü / superadmin
üçün görünür; İmtahan Mərkəzi və ``*`` daşıyan rektor üçün yazma endpoint-i 403,
oxu endpoint-ləri boş (``has_access: false``) cavab qaytarır.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.tests import test_exam_score_entry_section as fixtures
from apps.organizations.models import Membership
from core.rls import bypass_rls

User = get_user_model()

SECTION = "legacy-grade-review"


@override_settings(UNIVERSITY_MODE=True, MEDIA_ROOT=fixtures._MEDIA)
class LegacyReviewRimOnlyTest(TestCase):
    _client = fixtures.ExamScoreEntrySectionTest._client

    @classmethod
    def setUpTestData(cls):
        fixtures.ExamScoreEntrySectionTest.setUpTestData.__func__(cls)
        with bypass_rls():
            cls.rim = cls._member("lrr_rim_head", "ikt_rehber")
            cls.rector = cls._member("lrr_rector", "rector")
            cls.staff = cls._member("lrr_center_staff", "exam_center_staff")

    @classmethod
    def _member(cls, username, role):
        user = User.objects.create_user(username, f"{username}@qku.edu.az", "pw")
        Membership.objects.create(
            user=user, organization=cls.org, role=cls.org.roles.get(name=role), is_primary=True, is_active=True
        )
        return user

    def _page(self, user):
        return self._client(user).get(reverse("accounts:profile"), {"section": SECTION})

    def _action(self, user):
        return self._client(user).post(reverse("accounts:legacy_review_action"), {"action": "verify", "fact_id": "1"})

    def test_denied_for_exam_center_and_rector(self):
        for user in (self.center, self.staff, self.rector):
            with self.subTest(user=user.username):
                page = self._page(user)
                self.assertEqual(page.status_code, 200)
                self.assertNotContains(page, f'data-profile-section-panel="{SECTION}"')
                self.assertNotContains(page, f'data-section="{SECTION}"')  # menyu bəndi yoxdur
                self.assertEqual(self._action(user).status_code, 403)
                queue = self._client(user).get(reverse("accounts:legacy_review_queue"))
                self.assertFalse(queue.json()["has_access"])

    def test_allowed_for_rim_head(self):
        page = self._page(self.rim)
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, f'data-profile-section-panel="{SECTION}"')
        self.assertContains(page, f'data-section="{SECTION}"')
        queue = self._client(self.rim).get(reverse("accounts:legacy_review_queue"))
        self.assertEqual(queue.status_code, 200)
        self.assertTrue(queue.json()["has_access"])
        # İcazə qapısından keçir — naməlum fakt 403 DEYİL, domen xətasıdır.
        self.assertNotEqual(self._action(self.rim).status_code, 403)

    def test_allowed_for_superadmin(self):
        with bypass_rls():
            superadmin = User.objects.create_superuser("lrr_su", "lrr_su@qku.edu.az", "pw")
        queue = self._client(superadmin).get(reverse("accounts:legacy_review_queue"))
        self.assertTrue(queue.json()["has_access"])
