"""Profil səhifəsi: dil × rol matrisi (Faza 8).

Nəyi qoruyur
------------
Auditdə tapılan iki sinif problem məhz burada görünürdü:

* **Xam açar sızması** — `pgettext("...", "visible_test_cases")` kimi çağırışlar
  tərcümə olunmayanda istifadəçi interfeysdə açarın özünü (`visible_test_cases`,
  `ip_address`) görürdü.
* **Mənbə dilinin sızması** — EN/RU/TR interfeysdə azərbaycanca mətn qalırdı
  (djangojs kataloqu 3 dildə tamamilə tərcüməsiz idi).

`scripts/check_i18n_catalogs.py` kataloqu statik yoxlayır; bu testlər isə
RENDER OLUNMUŞ səhifəyə baxır — yəni şablonun həqiqətən düzgün kontekst/dil ilə
çağırdığını da yoxlayır.
"""

import re

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.organizations.models import Membership, Organization, Role
from core.constants import OrganizationType, RoleScopeType

User = get_user_model()

PASSWORD = "StrongPass123!"

LANGUAGES = ("az", "en", "ru", "tr")

ROLE_LEVELS = {
    "org_admin": 80,
    "teacher": 60,
    "student": 10,
    "hr": 65,
    "exam_center_head": 85,
    "dean": 80,
}

#: Sidebar/menyu mətnində görünməməli xam açar forması: `snake_case_word`.
#: Ən azı bir alt xətt tələb olunur ki, «kredit», «saat» kimi qanuni sözlər
#: yalançı siqnal verməsin.
RAW_KEY_RE = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")

#: Şablonda qanuni olaraq görünə bilən texniki dəyərlər (açar sızması deyil).
RAW_KEY_ALLOWLIST = frozenset(
    {
        "csrfmiddlewaretoken",
        "profile_base_url",
        "data_section",
        "utf_8",
        "x_requested_with",
    }
)

#: Azərbaycan dilinə xas hərflər — digər dillərdə mətn sızmasını göstərir.
AZ_ONLY_CHARS = re.compile(r"[əƏ]")


def _visible_text(html: str) -> str:
    """Skript/stil/atributları çıxarıb yalnız görünən mətni qaytarır."""
    html = re.sub(r"<script\b.*?</script>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<style\b.*?</style>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    html = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", html)


class ProfileI18nRoleMatrixTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("i18n_owner", "i18n_owner@qku.edu.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="I18n Univ",
            slug="i18n-univ",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        cls.users = {}
        for name, level in ROLE_LEVELS.items():
            role, _ = Role.objects.update_or_create(
                organization=cls.org,
                name=name,
                defaults={
                    "display_name": name.replace("_", " ").title(),
                    "level": level,
                    "scope_type": RoleScopeType.ORGANIZATION,
                    "permissions": [],
                    "is_system": False,
                    "is_active": True,
                },
            )
            user = User.objects.create_user(f"i18n_{name}", f"i18n_{name}@qku.edu.az", PASSWORD)
            Membership.objects.create(user=user, organization=cls.org, role=role, is_primary=True, is_active=True)
            cls.users[name] = user

    def _strip_data_noise(self, text):
        """Data mənşəli adları çıxarır — onlar tərcümə olunmur, sızma deyil."""
        for noise in [self.org.name, self.org.slug, self.owner.username] + [
            user.username for user in self.users.values()
        ]:
            text = text.replace(noise, " ")
        return text

    def _render(self, role_name, language):
        client = Client()
        client.force_login(self.users[role_name])
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        client.cookies[settings.LANGUAGE_COOKIE_NAME] = language
        response = client.get(reverse("accounts:profile"), HTTP_ACCEPT_LANGUAGE=language)
        self.assertEqual(response.status_code, 200, f"{role_name}/{language}")
        return response.content.decode()

    def test_every_role_and_language_renders(self):
        for role in ROLE_LEVELS:
            for language in LANGUAGES:
                with self.subTest(role=role, language=language):
                    self.assertIn("profile-sidebar", self._render(role, language))

    def test_no_raw_translation_keys_are_visible(self):
        for role in ROLE_LEVELS:
            for language in LANGUAGES:
                with self.subTest(role=role, language=language):
                    text = self._strip_data_noise(_visible_text(self._render(role, language)))
                    leaks = {token for token in RAW_KEY_RE.findall(text) if token not in RAW_KEY_ALLOWLIST}
                    self.assertEqual(leaks, set(), f"{role}/{language} xam açar göstərir: {sorted(leaks)[:5]}")

    def test_azerbaijani_text_does_not_leak_into_other_languages(self):
        """«ə» hərfi yalnız azərbaycanca mətndə olur — digər dillərdə sızmadır.

        İstifadəçi adları/təşkilat adı istisna edilir: onlar data-dır, tərcümə
        olunmur.
        """
        for role in ROLE_LEVELS:
            for language in ("en", "ru", "tr"):
                with self.subTest(role=role, language=language):
                    text = self._strip_data_noise(_visible_text(self._render(role, language)))
                    words = {word for word in text.split() if AZ_ONLY_CHARS.search(word)}
                    self.assertEqual(words, set(), f"{role}/{language} azərbaycanca mətn göstərir: {sorted(words)[:5]}")
