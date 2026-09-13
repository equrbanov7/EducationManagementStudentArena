"""Kabinet: EN/RU/TR interfeysdə azərbaycanca fallback QALMIR (Codex audit P2-06, 2026-09-13).

Nəyi qoruyur
------------
Audit tapıntısı: kataloq qapısı (``scripts/check_i18n_catalogs.py``) yaşıl olsa da
EN/RU/TR ekranlarda yeni AZ mətnlər fallback kimi görünürdü — msgid dörd
kataloqun heç birində yox idi, yaxud msgstr msgid-in özü idi. Bu test statik
kataloqa yox, RENDER OLUNMUŞ səhifəyə baxır: 6 nümayəndə bölmə × 4 rol × 3 dil
üçün ~30 açar etiketin (sidebar qrup başlıqları, `labels.py` bölmə başlıqları,
əsas düymələr/altbaşlıqlar) AZ kataloq dəyəri görünən mətndə OLMAMALIDIR.

Determinizm / sürət
-------------------
* Etalon AZ mətn kataloqdan (`translation.override("az")`) oxunur — testdə
  hərfi AZ sətir yoxdur, kataloq dəyişəndə test özü uyğunlaşır.
* Siyahıya YALNIZ üç dildə də AZ-dan fərqli olmalı etiketlər salınıb («Status»,
  «PIN» kimi qanuni eyniliklər yoxdur) — ona görə «eynidirsə keç» qaydası yoxdur:
  belə qayda tərcüməsiz kataloqu (pgettext → msgid) gizlədərdi.
* Bölmələr kanonik `?section=` səhifəsi ilə render olunur (qabıq + aktiv panel).
  Heç bir akademik data yaradılmır — boş vəziyyətlər də tərcüməli olmalıdır.
* Rol bölməni görmürsə (panel render olunmur) cüt ötürülür; amma hər bölmənin
  ən azı bir rolda render olunduğu ayrıca təsdiqlənir ki, test «boş keçməsin».
"""

import re

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import translation
from django.utils.translation import pgettext

from apps.accounts.models import ProfileRole
from apps.organizations.models import Membership, Organization
from core.constants import OrganizationType
from core.rls import bypass_rls

User = get_user_model()

TARGET_LANGUAGES = ("en", "ru", "tr")
#: test rolu → universitet sistem rolu (`default_roles`). `org_admin` sistem rolu
#: deyil — təşkilat SAHİBİ + profil rolu `ORG_ADMIN` (bax `rbac.is_org_admin`).
ROLES = {
    "student": "student",
    "teacher": "teacher",
    "org_admin": "rector",
    "exam_center_head": "exam_center_head",
}
SECTIONS = ("profile-info", "my-subjects", "my-journal", "statistics", "exam-score-entry", "applications")

#: Hər bölmənin ən azı bu rolda render olunması gözlənilir (əhatə təminatı).
EXPECTED_COVERAGE = {
    "profile-info": "student",
    "my-subjects": "student",
    "my-journal": "teacher",
    "statistics": "student",
    "exam-score-entry": "exam_center_head",
    "applications": "student",
}

#: (msgctxt, msgid) — sidebar qrup başlıqları, bölmə başlıqları, əsas düymə və
#: altbaşlıqlar. Bölmə üzrə qruplaşdırılıb; `None` = sidebar/tam səhifə.
KEY_LABELS = {
    None: (
        ("profile.sidebar", "group_general"),
        ("profile.sidebar", "group_my_studies"),
        ("profile.sidebar", "group_account"),
        ("profile.sidebar", "group_management"),
        ("profile.sidebar", "group_university_management"),
        ("profile.sidebar", "group_exam_center"),
        ("profile.sidebar", "group_blog"),
        ("profile.sidebar", "Ana səhifə"),
        ("profile.section", "edit_profile"),
        ("profile.section", "change_password"),
    ),
    "profile-info": (
        ("profile.section", "profile_info"),
        ("profile.info", "personal_info"),
        ("profile.info", "first_name"),
        ("profile.info", "organization"),
    ),
    "my-subjects": (
        ("profile.section", "my_subjects"),
        ("profile.subjects", "Akademik kontekst"),
        ("profile.subjects", "Akademik qeydiniz hələ yaradılmayıb"),
        ("profile.subjects", "Qiymətləndirmə komponentləri"),
        ("profile.subjects", "Status nişanları"),
    ),
    "my-journal": (
        ("profile.sidebar", "Elektron jurnal"),
        ("registrar.journal", "Elektron jurnal"),
        ("registrar.journal", "Jurnalı aç"),
    ),
    "statistics": (
        ("profile.section", "statistics"),
        ("profile.statistics", "Xülasə yarat"),
        ("profile.statistics", "AI xülasəsi"),
        ("profile.statistics", "Göndərişlər (CSV)"),
        ("profile.statistics", "Bu rol üçün statistika əhatəsi təyin edilməyib."),
    ),
    "exam-score-entry": (
        ("profile.section", "İmtahan balının daxil edilməsi"),
        ("registrar.exam_score_entry", "Köçürmə addımları"),
        ("registrar.exam_score_entry", "Bal daxiletmə üsulu"),
        ("registrar.exam_score_entry", "Balları sistemə yaz"),
        ("registrar.exam_score_entry", "Balları fayldan yüklə"),
        ("registrar.exam_score_entry", "Yoxla (quru icra)"),
    ),
    "applications": (
        ("profile.sidebar", "Müraciətlərim"),
        ("applications", "Yeni müraciət"),
        ("applications", "Müraciət axtar"),
        ("applications", "Mənə gələnlər"),
    ),
}


def _visible_text(html: str) -> str:
    """Skript/stil/şərh və teqləri çıxarıb yalnız görünən mətni qaytarır."""
    html = re.sub(r"<script\b.*?</script>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<style\b.*?</style>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<!--.*?-->", " ", html, flags=re.S)
    html = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", html)


@override_settings(UNIVERSITY_MODE=True)
class CabinetNoAzerbaijaniFallbackSmokeTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("nofb_owner", "nofb_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="NoFallback Univ",
                slug="nofb-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.users = {}
            for role_name, system_role in ROLES.items():
                if role_name == "org_admin":
                    user = cls.owner
                else:
                    user = User.objects.create_user(f"nofb_{role_name}", f"nofb_{role_name}@qku.edu.az", "pw")
                Membership.objects.create(
                    user=user,
                    organization=cls.org,
                    role=cls.org.roles.get(name=system_role),
                    is_primary=True,
                    is_active=True,
                )
                cls.users[role_name] = user
            owner_profile = cls.owner.profile
            owner_profile.organization = cls.org
            owner_profile.organization_type = cls.org.org_type
            owner_profile.role = ProfileRole.ORG_ADMIN
            owner_profile.save()

    # ── köməkçilər ──────────────────────────────────────────────────────
    def _client(self, role_name, language):
        client = Client()
        client.force_login(self.users[role_name])
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        client.cookies[settings.LANGUAGE_COOKIE_NAME] = language
        return client

    def _section(self, role_name, section, language):
        """Kanonik `?section=` səhifəsi; rol bölməni görmürsə (panel yoxdur) None.

        `profile_section_fragment` yalnız AJAX-safe bölmələri verir —
        `exam-score-entry` forma bölməsidir və oradan 403 qaytarır; ona görə
        hamısı üçün eyni yol — tam səhifə — işlədilir (qabıq da hər dəfə yoxlanır).
        """
        client = self._client(role_name, language)
        response = client.get(reverse("accounts:profile"), {"section": section}, HTTP_ACCEPT_LANGUAGE=language)
        self.assertEqual(response.status_code, 200, f"{role_name}/{section}/{language}")
        html = response.content.decode()
        if f'data-profile-section-panel="{section}"' not in html:
            return None
        return _visible_text(html)

    def _full_page(self, role_name, language):
        client = self._client(role_name, language)
        response = client.get(reverse("accounts:profile"), HTTP_ACCEPT_LANGUAGE=language)
        self.assertEqual(response.status_code, 200, f"{role_name}/{language}")
        return _visible_text(response.content.decode())

    @staticmethod
    def _catalog_value(language, ctx, msgid):
        with translation.override(language):
            return pgettext(ctx, msgid)

    def _assert_no_az_labels(self, text, labels, language, where):
        """Görünən mətndə açar etiketlərin AZ dəyəri OLMAMALIDIR.

        DİQQƏT: «hədəf tərcümə AZ ilə eynidirsə keç» qaydası QƏSDƏN yoxdur —
        tərcüməsiz kataloqda `pgettext` msgid-i (AZ mətni) qaytarır və belə
        qayda məhz axtarılan səhvi gizlədərdi (köhnə .mo ilə test yaşıl qalırdı).
        Siyahı elə seçilib ki, hər etiket üç dildə də AZ-dan fərqli olmalıdır.
        """
        leaks = []
        for ctx, msgid in labels:
            az_text = self._catalog_value("az", ctx, msgid)
            target = self._catalog_value(language, ctx, msgid)
            if target == az_text or target == msgid:
                leaks.append(f"{ctx}|{msgid}: kataloqda tərcümə yoxdur (msgstr == «{target}»)")
                continue
            # Söz sərhədi: «Profil» ⊂ «Profile» yalançı siqnal verməsin.
            if re.search(r"(?<!\w)" + re.escape(az_text) + r"(?!\w)", text):
                leaks.append(f"{ctx}|{msgid} → «{az_text}» ekranda görünür")
        self.assertEqual(leaks, [], f"{where}/{language} azərbaycanca göstərir: {leaks}")

    # ── testlər ─────────────────────────────────────────────────────────
    def test_catalog_has_target_translations_for_key_labels(self):
        """Etalonun özü: hər açar etiket AZ-da tərcümə olunub, EN/RU/TR-də isə AZ-dan fərqlidir."""
        untranslated = []
        for labels in KEY_LABELS.values():
            for ctx, msgid in labels:
                az_text = self._catalog_value("az", ctx, msgid)
                if az_text == msgid and "_" in msgid:
                    untranslated.append(f"az:{ctx}|{msgid}")
                for language in TARGET_LANGUAGES:
                    target = self._catalog_value(language, ctx, msgid)
                    if target == msgid or target == az_text:
                        untranslated.append(f"{language}:{ctx}|{msgid}")
        self.assertEqual(untranslated, [], f"tərcüməsiz açar etiket: {untranslated}")

    def test_sidebar_and_shell_have_no_azerbaijani_in_other_languages(self):
        for role_name in ROLES:
            for language in TARGET_LANGUAGES:
                with self.subTest(role=role_name, language=language):
                    text = self._full_page(role_name, language)
                    self._assert_no_az_labels(text, KEY_LABELS[None], language, f"{role_name}/shell")

    def test_sections_have_no_azerbaijani_in_other_languages(self):
        rendered = {section: set() for section in SECTIONS}
        for role_name in ROLES:
            for section in SECTIONS:
                for language in TARGET_LANGUAGES:
                    with self.subTest(role=role_name, section=section, language=language):
                        text = self._section(role_name, section, language)
                        if text is None:
                            continue
                        rendered[section].add(role_name)
                        self._assert_no_az_labels(text, KEY_LABELS[section], language, f"{role_name}/{section}")
        for section, role_name in EXPECTED_COVERAGE.items():
            self.assertIn(role_name, rendered[section], f"{section} bölməsi {role_name} üçün render olunmadı")
