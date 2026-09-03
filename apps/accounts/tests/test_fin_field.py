"""``UserProfile.fin`` sahəsi və ``core.validators`` FİN funksiyaları üçün testlər.

FAZA 3 — SLICE 1 §3.1-§3.4: normalize/validate matrisi, nullable-unique
semantikası (iki NULL yanaşı yaşayır, dublikat non-null rədd olunur) və
Django admin changelist-in ``fin`` sütununu göstərməsi.
"""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.accounts.models import UserProfile
from core.validators import FIN_LENGTH, FIN_PATTERN, normalize_fin, validate_fin

User = get_user_model()


class NormalizeFinTest(SimpleTestCase):
    """``normalize_fin`` matrisinin determinist davranışı."""

    def test_empty_inputs_return_empty_string(self):
        for value in (None, "", "   ", "\t\r\n", 0):
            with self.subTest(value=value):
                self.assertEqual(normalize_fin(value), "")

    def test_strip_inner_whitespace_and_uppercase(self):
        self.assertEqual(normalize_fin(" 5jfc0re "), "5JFC0RE")
        self.assertEqual(normalize_fin("5jf c0re"), "5JFC0RE")
        self.assertEqual(normalize_fin("5JF\tC0RE\r\n"), "5JFC0RE")

    def test_nbsp_is_removed(self):
        self.assertEqual(normalize_fin("\u00a05JFC0RE\u00a0"), "5JFC0RE")

    def test_nfkc_folds_fullwidth_characters(self):
        self.assertEqual(normalize_fin("５ＪＦＣ０ＲＥ"), "5JFC0RE")

    def test_non_string_input_is_coerced(self):
        self.assertEqual(normalize_fin(1234567), "1234567")

    def test_idempotent_on_normalized_value(self):
        self.assertEqual(normalize_fin("5JFC0RE"), "5JFC0RE")


class ValidateFinTest(SimpleTestCase):
    """``validate_fin`` matrisinin qəbul/rədd davranışı."""

    def test_constants_shape(self):
        self.assertEqual(FIN_LENGTH, 7)
        self.assertIsNotNone(FIN_PATTERN.fullmatch("A1B2C3D"))

    def test_empty_values_pass(self):
        for value in (None, ""):
            with self.subTest(value=value):
                validate_fin(value)  # heç bir istisna atmamalıdır

    def test_valid_values_pass(self):
        for value in ("5JFC0RE", "1234567", "ABCDEFG"):
            with self.subTest(value=value):
                validate_fin(value)

    def test_invalid_values_raise(self):
        invalid = (
            "5jfc0re",  # kiçik hərf — normalize edilməyib
            "5JFC0R",  # 6 simvol
            "5JFC0RE1",  # 8 simvol
            "5JFC0R!",  # icazəsiz simvol
            "5JFC0RE\n",  # sondakı newline ($ tələsinə qarşı \Z)
            " 5JFC0R",  # boşluq
            1234567,  # tip sərt yoxlanır — yalnız str
        )
        for value in invalid:
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    validate_fin(value)


class UserProfileFinFieldTest(TestCase):
    """``UserProfile.fin`` — nullable-unique DB semantikası + model validatoru."""

    @staticmethod
    def _profile(username):
        user = User.objects.create_user(username, f"{username}@example.com", "StrongPass123!")
        return user.profile

    def test_default_is_null(self):
        profile = self._profile("finuser0")
        profile.refresh_from_db()
        self.assertIsNone(profile.fin)

    def test_two_null_fins_coexist(self):
        # Unikal indeks NULL-ları fərqləndirir (PostgreSQL də, SQLite də);
        # iki NULL-lu profil yanaşı yaşamalıdır.
        first = self._profile("finuser1")
        second = self._profile("finuser2")
        first.fin = None
        first.save(update_fields=["fin"])
        second.fin = None
        second.save(update_fields=["fin"])
        self.assertEqual(
            UserProfile.objects.filter(pk__in=[first.pk, second.pk], fin__isnull=True).count(),
            2,
        )

    def test_duplicate_non_null_fin_rejected(self):
        first = self._profile("finuser3")
        second = self._profile("finuser4")
        first.fin = "5JFC0RE"
        first.save(update_fields=["fin"])
        second.fin = "5JFC0RE"
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                second.save(update_fields=["fin"])

    def test_distinct_non_null_fins_allowed(self):
        first = self._profile("finuser5")
        second = self._profile("finuser6")
        first.fin = "5JFC0RE"
        first.save(update_fields=["fin"])
        second.fin = "7ABC123"
        second.save(update_fields=["fin"])
        self.assertEqual(UserProfile.objects.filter(fin__isnull=False).count(), 2)

    def test_model_validator_wired_into_full_clean(self):
        profile = self._profile("finuser7")
        profile.fin = "bad!"
        with self.assertRaises(ValidationError) as ctx:
            profile.full_clean()
        self.assertIn("fin", ctx.exception.error_dict)

    def test_full_clean_accepts_valid_and_null(self):
        profile = self._profile("finuser8")
        for value in (None, "5JFC0RE"):
            with self.subTest(value=value):
                profile.fin = value
                profile.full_clean()


class UserProfileAdminFinTest(TestCase):
    """Admin changelist ``fin`` sütununu göstərir və onunla axtarır."""

    def setUp(self):
        self.superuser = User.objects.create_superuser("finadmin", "finadmin@example.com", "StrongPass123!")
        self.client.force_login(self.superuser)

    def test_changelist_renders_fin_column(self):
        profile = self.superuser.profile
        profile.fin = "5JFC0RE"
        profile.save(update_fields=["fin"])
        response = self.client.get(reverse("admin:accounts_userprofile_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "column-fin")
        self.assertContains(response, "5JFC0RE")

    def test_changelist_search_by_fin(self):
        profile = self.superuser.profile
        profile.fin = "7ABC123"
        profile.save(update_fields=["fin"])
        other = User.objects.create_user("finother", "finother@example.com", "StrongPass123!")
        response = self.client.get(reverse("admin:accounts_userprofile_changelist"), {"q": "7ABC123"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "7ABC123")
        self.assertNotContains(response, other.username)
