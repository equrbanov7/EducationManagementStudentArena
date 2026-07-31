"""Sənədli düzəlişdə «düzəldən» adı — impersonasiya altında atribusiya.

Düzəliş modulunun zəmanəti belədir: «Düzəldənin adı avtomatik profildən
götürülür və dəyişdirilə bilməz». View-as (impersonation) altında bu zəmanət
ƏKSİNƏ işləyir: ``ViewAsMiddleware`` ``request.user``-i hədəflə əvəz edir, view
isə ``by_user=request.user`` ötürür — nəticədə rəsmi, PDF sənədli düzəliş
təqlid edilən şəxsin adına düşür (2026-07-31 auditi).

``correction_author_name`` view-as aktiv olanda əsl aktoru da yazır. Model
sahəsi dəyişmir (miqrasiya yoxdur) — jurnal UI-da sarı xananın «kim» sahəsi
həqiqəti göstərir.
"""

from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.registrar.corrections import correction_author_name

User = get_user_model()


class CorrectionAuthorNameTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.target = User.objects.create_user(
            "ca_dean", "ca_dean@qku.edu.az", "pw", first_name="Dekan", last_name="Məmmədov"
        )
        cls.actor = User.objects.create_user(
            "ca_admin", "ca_admin@qku.edu.az", "pw", first_name="Admin", last_name="Əliyev"
        )

    def test_normal_request_records_only_the_author(self):
        request = SimpleNamespace(is_view_as=False, real_user=self.target)

        self.assertEqual(correction_author_name(self.target, request), "Dekan Məmmədov")

    def test_no_request_falls_back_to_the_author(self):
        self.assertEqual(correction_author_name(self.target, None), "Dekan Məmmədov")

    def test_view_as_records_the_real_actor_too(self):
        request = SimpleNamespace(is_view_as=True, real_user=self.actor)

        name = correction_author_name(self.target, request)

        self.assertIn("Dekan Məmmədov", name)
        self.assertIn("Admin Əliyev", name, "əsl aktor qeyd olunmayıb — atribusiya saxtakarlığı")

    def test_self_view_as_is_not_duplicated(self):
        """Aktor və hədəf eynidirsə ad təkrarlanmır."""
        request = SimpleNamespace(is_view_as=True, real_user=self.target)

        self.assertEqual(correction_author_name(self.target, request), "Dekan Məmmədov")

    def test_username_is_used_when_full_name_is_missing(self):
        nameless = User.objects.create_user("ca_nameless", "ca_nameless@qku.edu.az", "pw")

        self.assertEqual(correction_author_name(nameless, None), "ca_nameless")

    def test_result_fits_the_model_field(self):
        """`corrected_by_name` 200 simvolla məhduddur."""
        request = SimpleNamespace(is_view_as=True, real_user=self.actor)

        self.assertLessEqual(len(correction_author_name(self.target, request)), 200)
