"""2026-10-15 — sadə parol siyasəti (``apps/accounts/password_policy.py``).

Sahib: «Parolu təyin etməni yüngülləşdir, 8 simvol olsun, amma çox da zorlamasın … müəllimlər uzun böyük
kodları yadda saxlaya bilməyəcək — sadə kod qoymağa icazə olsun.» Qayda: ən azı 8 simvol, tərkib tələbi yox,
yalnız qısa qadağa siyahısı + istifadəçi adı.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.accounts.forms import CustomPasswordChangeForm
from apps.accounts.models import RuntimeSetting
from apps.accounts.password_policy import TRIVIAL_PASSWORDS
from core import runtime_settings as rs

User = get_user_model()
LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "pw-policy"}}
SIMPLE_PASSWORDS = ("elvin123", "19850412", "salam123", "aaaaaaab", "Elvin Qurbanov")


class _Named:
    username = "elvin.qurbanov"
    first_name = "Elvin"
    last_name = "Qurbanov"
    email = "elvin.qurbanov@qku.edu.az"


def _codes(password, user=None):
    try:
        validate_password(password, user=user)
    except ValidationError as exc:
        return {error.code for error in exc.error_list}
    return set()


class SimplePasswordPolicyTest(SimpleTestCase):
    def test_only_the_simple_validators_are_configured(self):
        names = [item["NAME"] for item in settings.AUTH_PASSWORD_VALIDATORS]
        self.assertEqual(
            names,
            [
                "apps.accounts.password_policy.MinimumLengthValidator",
                "apps.accounts.password_policy.TrivialPasswordValidator",
                # SEC-1 F5 (2026-10-17): yalnız rəhbər hesablarda tam rəqəm / tarix parolu olmaz.
                "apps.accounts.password_policy.PrivilegedPasswordValidator",
            ],
        )

    def test_simple_eight_char_passwords_are_accepted(self):
        user = _Named()
        for password in SIMPLE_PASSWORDS:
            with self.subTest(password=password):
                self.assertEqual(_codes(password, user), set())

    def test_name_like_password_is_accepted(self):
        # Köhnə UserAttributeSimilarityValidator bunu rədd edirdi.
        self.assertEqual(_codes("qurbanov1", _Named()), set())

    def test_seven_chars_are_rejected(self):
        self.assertEqual(_codes("elvin12"), {"password_too_short"})
        self.assertEqual(_codes(""), {"password_too_short"})

    def test_blocklisted_passwords_are_rejected(self):
        for password in sorted(TRIVIAL_PASSWORDS) + ["PASSWORD", " Qwerty12 "]:
            with self.subTest(password=password):
                self.assertIn("password_too_common", _codes(password))

    def test_own_username_is_rejected(self):
        user = _Named()
        self.assertEqual(_codes("elvin.qurbanov", user), {"password_too_common"})
        self.assertEqual(_codes("Elvin.Qurbanov", user), {"password_too_common"})

    def test_single_repeated_character_is_rejected(self):
        # QA-1 F12: «11111111» siyahıdadır, «aaaaaaaa» isə keçirdi.
        for password in ("aaaaaaaa", "ZZZZZZZZZ", "........"):
            with self.subTest(password=password):
                self.assertEqual(_codes(password), {"password_too_common"})

    def test_messages_are_short_and_friendly(self):
        with self.assertRaises(ValidationError) as short:
            validate_password("abc")
        with self.assertRaises(ValidationError) as trivial:
            validate_password("12345678")
        self.assertIn("8", short.exception.messages[0])
        for message in short.exception.messages + trivial.exception.messages:
            self.assertLess(len(message), 80)


@override_settings(RUNTIME_SETTINGS_ENABLED=True, CACHES=LOCMEM)
class MinLengthRuntimeSettingTest(TestCase):
    def tearDown(self):
        rs.invalidate()

    def test_default_is_eight(self):
        rs.invalidate()
        self.assertEqual(rs.get_int("password.min_length"), 8)
        spec = rs.SPECS["password.min_length"]
        self.assertEqual((spec.group, spec.min, spec.max), ("login", 8, 32))  # SEC-1 F5: alt hədd 8

    def test_override_changes_the_validator(self):
        RuntimeSetting.objects.create(key="password.min_length", value=10)
        rs.invalidate()
        self.assertEqual(_codes("salam123"), {"password_too_short"})
        self.assertEqual(_codes("salam12345"), set())

    def test_out_of_range_value_falls_back_to_default(self):
        RuntimeSetting.objects.create(key="password.min_length", value=3)
        rs.invalidate()
        self.assertEqual(_codes("abcdef1"), {"password_too_short"})
        self.assertEqual(_codes("abcdefg1"), set())


class SimplePasswordFlowsTest(TestCase):
    def test_profile_change_password_accepts_all_digit_code(self):
        user = User.objects.create_user("pw.simple", "pw.simple@qku.edu.az", "OldPassword!42")
        form = CustomPasswordChangeForm(
            user, {"old_password": "OldPassword!42", "new_password1": "19850412", "new_password2": "19850412"}
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_first_login_accepts_simple_password(self):
        user = User.objects.create_user("first.simple", "first.simple@qku.edu.az", "TempReset123!Qz")
        profile = user.profile
        profile.password_change_required = True
        profile.email_verified = True
        profile.save(update_fields=["password_change_required", "email_verified", "updated_at"])
        self.client.force_login(user)
        url = reverse("accounts:set_initial_password")

        page = self.client.get(url)
        self.assertContains(page, 'minlength="8"')
        self.assertContains(page, "sadə parol da olar")

        response = self.client.post(url, {"action": "set_password", "password1": "salam123", "password2": "salam123"})

        self.assertEqual(response["Location"], reverse("accounts:profile"))
        user.refresh_from_db()
        self.assertTrue(user.check_password("salam123"))
        self.assertFalse(user.profile.password_change_required)

    def test_first_login_rejects_blocklisted_password(self):
        user = User.objects.create_user("first.trivial", "first.trivial@qku.edu.az", "TempReset123!Qz")
        profile = user.profile
        profile.password_change_required = True
        profile.email_verified = True
        profile.save(update_fields=["password_change_required", "email_verified", "updated_at"])
        self.client.force_login(user)

        self.client.post(
            reverse("accounts:set_initial_password"),
            {"action": "set_password", "password1": "12345678", "password2": "12345678"},
        )

        user.refresh_from_db()
        self.assertTrue(user.check_password("TempReset123!Qz"))
        self.assertTrue(user.profile.password_change_required)

    def test_change_password_section_shows_simple_rules(self):
        user = User.objects.create_user("pw.section", "pw.section@qku.edu.az", "OldPassword!42")
        self.client.force_login(user)

        response = self.client.get(reverse("accounts:profile") + "?section=change-password")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-pw-min="8"')
        self.assertContains(response, 'data-pw-username="pw.section"')
        self.assertContains(response, 'data-pw-rule="trivial"')
        self.assertNotContains(response, 'data-pw-rule="variety"')
        self.assertNotContains(response, 'data-pw-rule="numeric"')

    def test_profile_change_password_rejects_the_current_password(self):
        user = User.objects.create_user("pw.same", "pw.same@qku.edu.az", "OldPassword!42")
        same = CustomPasswordChangeForm(
            user,
            {"old_password": "OldPassword!42", "new_password1": "OldPassword!42", "new_password2": "OldPassword!42"},
        )
        self.assertFalse(same.is_valid())
        self.assertEqual(same.errors["new_password1"].as_data()[0].code, "password_unchanged")

    def test_current_password_hint_is_not_given_when_the_old_one_is_wrong(self):
        user = User.objects.create_user("pw.guess", "pw.guess@qku.edu.az", "OldPassword!42")
        guess = CustomPasswordChangeForm(
            user,
            {"old_password": "Wrong-guess-1", "new_password1": "OldPassword!42", "new_password2": "OldPassword!42"},
        )
        self.assertFalse(guess.is_valid())
        self.assertNotIn("new_password1", guess.errors)
