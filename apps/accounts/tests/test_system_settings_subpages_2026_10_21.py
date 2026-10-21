"""«Sistem tənzimləmələri» alt səhifələri (sahib 2026-10-21).

Sahib: «hər şey eyni səhifədədir — onun alt səhifələrini yarat; sidebarda onun ayrı başlığı olsun və alt
hissələri, bir şeyi axtararkən rahatlıqla tapmaq üçün».

Kilidlənən qaydalar:

* sidebar-da ayrıca «Sistem tənzimləmələri» qrupu — «Ümumi baxış» + GROUPS sırası ilə hər qrupa bir bənd; yalnız
  bölməni görən (RİM rəhbəri / superadmin) üçün; «İdarəetmə» qrupunda köhnə tək bənd yoxdur;
* ``?ss_group=<qrup>`` yalnız o qrupun açarlarını render edir; qrupsuz / yanlış qrup → ümumi baxış (kartlar);
* deep link (``ss_key``) həm tam GET, həm AJAX fraqmentində işləyir, sətir vurğulanır;
* alt səhifədən saxlama yalnız göndərilən açarı dəyişir (başqa qrupun override-ı qalır);
* axtarış bütün qruplar üzrə, az/ing hərf qatlaması ilə və söz sırasından asılı olmadan;
* qlobal kabinet axtarışı (⌘K) açarı tapır və qrupun alt səhifəsinə aparır — yalnız RİM rəhbərinə.
"""

from __future__ import annotations

import re
from collections import Counter

from django.contrib.auth import get_user_model
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import RuntimeSetting
from apps.accounts.services import system_settings_pages as pages
from apps.organizations.models import Membership, Organization, Role
from core import runtime_settings as rs
from core.constants import OrganizationType, RoleScopeType

User = get_user_model()

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "sset-subpages"}}
SPRITE_IDS_RE = re.compile(r'<symbol id="([a-z0-9-]+)"')


def _visible_keys(group):
    return [spec.key for spec in rs.SPECS.values() if spec.group == group and not spec.hidden]


def _aside(html):
    start = html.index('<aside class="profile-sidebar"')
    return html[start : html.index("</aside>", start)]


def _settings_group_html(aside):
    start = aside.index('data-sidebar-group="system-settings"')
    return aside[start : aside.index("</details>", start)]


class SystemSettingsPagesPureTest(SimpleTestCase):
    """Naviqasiya / axtarış indeksi saf hesablamadır — GROUPS/SPECS-dən, DB-siz."""

    def test_nav_follows_groups_order_and_skips_empty_groups(self):
        counts = Counter(spec.group for spec in rs.SPECS.values() if not spec.hidden)
        expected = [key for key, _label in rs.GROUPS if counts.get(key)]
        nav = pages.nav_groups()
        self.assertEqual([item["key"] for item in nav], expected)
        self.assertGreaterEqual(len(nav), 14)
        for item in nav:
            self.assertEqual(item["count"], counts[item["key"]])
            self.assertIn(f"ss_group={item['key']}", item["url"])

    def test_every_group_icon_is_in_the_sprite(self):
        from django.conf import settings

        sprite = (settings.BASE_DIR / "static/vendor/lucide/ems-nav.svg").read_text(encoding="utf-8")
        ids = set(SPRITE_IDS_RE.findall(sprite))
        used = set(pages.GROUP_ICONS.values()) | {pages.DEFAULT_ICON, pages.OVERVIEW_ICON}
        self.assertEqual(sorted(used - ids), [])
        self.assertTrue(all(item["icon"] in ids for item in pages.nav_groups()))

    def test_resolve_group_rejects_unknown_codes(self):
        codes = [item["key"] for item in pages.nav_groups()]
        self.assertEqual(pages.resolve_group("login", codes), "login")
        self.assertEqual(pages.resolve_group("nope", codes), "")
        self.assertEqual(pages.resolve_group("", codes), "")
        self.assertEqual(pages.resolve_group(None, codes), "")

    def test_search_is_diacritic_insensitive_and_token_based_across_groups(self):
        keys = [hit["key"] for hit in pages.search("parol sehv cehdi")]
        self.assertIn("login.device_rate", keys)
        self.assertIn("login.account_rate", keys)
        self.assertNotIn("otp.max_attempts", keys)  # «parol» yoxdur — tokenlər VƏ ilə
        # Söz sırası fərq etmir.
        self.assertEqual(keys, [hit["key"] for hit in pages.search("cehdi parol sehv")])
        # Bir neçə qrupdan nəticə: «cəhd» həm giriş, həm OTP, həm imtahan qrupunda var.
        groups = {hit["group"] for hit in pages.search("CEHD")}
        self.assertTrue({"login", "otp", "exam"} <= groups, groups)
        # İ/I, ü/u, ö/o: «Bir İP ünvanından giriş cəhdi».
        self.assertIn("login.ip_rate", [hit["key"] for hit in pages.search("ip unvanindan giris")])
        # Açar adı da axtarılır.
        self.assertEqual([hit["key"] for hit in pages.search("otp.max_attempts")], ["otp.max_attempts"])
        hit = pages.search("otp.max_attempts")[0]
        self.assertIn("ss_group=otp", hit["url"])
        self.assertIn("ss_key=otp.max_attempts", hit["url"])
        self.assertEqual(pages.search("   "), [])
        self.assertEqual(len(pages.search("e", limit=3)), 3)


@override_settings(RUNTIME_SETTINGS_ENABLED=True, CACHES=LOCMEM, UNIVERSITY_MODE=True)
class SystemSettingsSubpagesTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("ssp_owner", "ssp_owner@qku.edu.az", "pw")
        cls.org = Organization.objects.create(
            name="SSP Univ", slug="ssp-univ", org_type=OrganizationType.UNIVERSITY, owner=cls.owner, status="active"
        )

        def member(username, role_name, level):
            role, _ = Role.objects.update_or_create(
                organization=cls.org,
                name=role_name,
                defaults={
                    "display_name": role_name,
                    "level": level,
                    "scope_type": RoleScopeType.ORGANIZATION,
                    "permissions": ["semester.view"],
                    "is_active": True,
                },
            )
            user = User.objects.create_user(username, f"{username}@qku.edu.az", "pw")
            Membership.objects.create(user=user, organization=cls.org, role=role, is_primary=True, is_active=True)
            return user

        cls.rim = member("ssp_rim", "ikt_rehber", 95)
        cls.dean = member("ssp_dean", "dean", 80)

    def setUp(self):
        RuntimeSetting.objects.all().delete()
        rs.invalidate()

    def tearDown(self):
        rs.invalidate()

    def _client(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _page(self, user, **params):
        response = self._client(user).get(reverse("accounts:profile"), params)
        self.assertEqual(response.status_code, 200)
        return response

    def _fragment(self, user, **params):
        response = self._client(user).get(
            reverse("accounts:profile_section_fragment", kwargs={"section": "system-settings"}), params
        )
        self.assertEqual(response.status_code, 200, response.content[:300])
        return response

    # ── sidebar ─────────────────────────────────────────────────────────────
    def test_sidebar_has_own_heading_with_one_child_per_group_for_rim_head(self):
        aside = _aside(self._page(self.rim).content.decode())
        group = _settings_group_html(aside)
        self.assertIn("Sistem tənzimləmələri", group)
        subs = re.findall(r'data-section="system-settings"\s+data-section-sub="([a-z0-9_-]+)"', group)
        self.assertEqual(subs, ["overview"] + [item["key"] for item in pages.nav_groups()])
        for item in pages.nav_groups():
            with self.subTest(group=item["key"]):
                self.assertIn(item["label"], group)
                self.assertIn(f"ss_group={item['key']}", group)
        # Köhnə tək bənd «İdarəetmə» qrupunda qalmayıb — bölmə linkləri yalnız yeni qrupdadır.
        self.assertEqual(aside.count('data-section="system-settings"'), len(subs))
        self.assertIn('data-sidebar-group="management"', aside)
        management = aside[aside.index('data-sidebar-group="management"') :]
        management = management[: management.index("</details>")]
        self.assertNotIn('data-section="system-settings"', management)
        self.assertIn('data-section="journal-hygiene"', management)

    def test_sidebar_heading_is_hidden_from_others(self):
        aside = _aside(self._page(self.dean).content.decode())
        self.assertNotIn('data-sidebar-group="system-settings"', aside)
        self.assertNotIn('data-section="system-settings"', aside)
        self.assertNotIn("ss_group=", aside)

    def test_sidebar_marks_the_active_sub_page(self):
        aside = _aside(self._page(self.rim, section="system-settings", ss_group="login").content.decode())
        group = _settings_group_html(aside)
        active = re.findall(r'data-section-sub="([a-z0-9_-]+)"[^>]*class="[^"]*\bactive\b', group, re.S)
        self.assertEqual(active, ["login"])
        overview = _settings_group_html(_aside(self._page(self.rim, section="system-settings").content.decode()))
        self.assertEqual(
            re.findall(r'data-section-sub="([a-z0-9_-]+)"[^>]*class="[^"]*\bactive\b', overview, re.S), ["overview"]
        )

    # ── alt səhifələr ───────────────────────────────────────────────────────
    def test_each_group_sub_page_renders_only_its_keys(self):
        all_keys = {spec.key for spec in rs.SPECS.values() if not spec.hidden}
        for item in pages.nav_groups():
            code = item["key"]
            with self.subTest(group=code):
                response = self._fragment(self.rim, ss_group=code)
                html = response.json()["html"]
                own = set(_visible_keys(code))
                rendered = set(re.findall(r'data-ss-field="([^"]+)"', html))
                self.assertEqual(rendered, own)
                for key in all_keys - own:
                    self.assertNotIn(f'id="ss-{key}"', html)
                self.assertIn(f'data-profile-section-sub="{code}"', html)
                self.assertIn(f'data-ss-group="{code}"', html)
                self.assertIn('id="ssConfirmDialog"', html)
                section = response.context["system_settings_section"]
                self.assertEqual((section["view"], section["active_key"]), ("group", code))
                # Panel saxlamadan sonra EYNİ alt səhifəni yeniləyir.
                self.assertIn(f"ss_group={code}", section["source_url"])
                # Axtarış indeksi BÜTÜN qrupları daşıyır (redaktə sahəsi kimi yox — keçid kimi).
                self.assertEqual(set(re.findall(r'data-ss-hit-key="([^"]+)"', html)), all_keys)

    def test_overview_shows_cards_with_changed_counts_and_no_form(self):
        RuntimeSetting.objects.create(key="otp.max_attempts", value=8)
        RuntimeSetting.objects.create(key="otp.expiry_minutes", value=12)
        rs.invalidate()
        response = self._fragment(self.rim)
        html = response.json()["html"]
        section = response.context["system_settings_section"]
        self.assertEqual(section["view"], "overview")
        self.assertNotIn("data-ss-form", html)
        self.assertNotIn('data-ss-field="', html)
        self.assertIn('data-profile-section-sub="overview"', html)
        cards = {card["key"]: card for card in section["cards"]}
        self.assertEqual(list(cards), [item["key"] for item in pages.nav_groups()])
        self.assertEqual(cards["otp"]["changed"], 2)
        self.assertEqual(cards["otp"]["count"], len(_visible_keys("otp")))
        self.assertEqual(cards["login"]["changed"], 0)
        for code in cards:
            self.assertIn(f'data-ss-card="{code}"', html)
        # Konteks müqaviləsi saxlanılıb: `groups` bütün qruplardır.
        self.assertEqual([group["key"] for group in section["groups"]], list(cards))

    def test_unknown_group_falls_back_to_overview(self):
        section = self._fragment(self.rim, ss_group="does-not-exist").context["system_settings_section"]
        self.assertEqual((section["view"], section["active_key"]), ("overview", ""))

    def test_deep_link_works_for_full_get_and_ajax(self):
        key = "journal.lesson_edit_minutes"
        page = self._page(self.rim, section="system-settings", ss_group="journal", ss_key=key)
        html = page.content.decode()
        self.assertEqual(page.context["active_section"], "system-settings")
        self.assertIn(f'data-ss-focus-key="{key}"', html)
        self.assertIn(f'data-ss-field="{key}" id="ss-row-{key}"', html)
        self.assertRegex(html, r'class="sysset__row[^"]*is-target[^"]*" data-ss-field="journal\.lesson_edit_minutes"')
        self.assertNotIn('id="ss-otp.max_attempts"', html)

        fragment = self._fragment(self.rim, ss_group="journal", ss_key=key).json()["html"]
        self.assertIn(f'data-ss-focus-key="{key}"', fragment)
        self.assertRegex(fragment, r'is-target[^"]*" data-ss-field="journal\.lesson_edit_minutes"')
        # Başqa qrupun açarı vurğulanmır.
        other = self._fragment(self.rim, ss_group="journal", ss_key="otp.max_attempts")
        self.assertEqual(other.context["system_settings_section"]["focus_key"], "")

    def test_save_on_a_sub_page_changes_only_that_key(self):
        RuntimeSetting.objects.create(key="otp.max_attempts", value=8)  # başqa qrupun override-ı
        rs.invalidate()
        html = self._fragment(self.rim, ss_group="journal").json()["html"]
        # Brauzerin göndərdiyi kimi: formadakı BÜTÜN sahələr (cari dəyərlərlə), biri dəyişdirilib.
        data = {}
        for tag in re.findall(r"<(?:input|select)\b[^>]*\bname=\"[^\"]+\"[^>]*>", html):
            name = re.search(r'name="([^"]+)"', tag).group(1)
            if name == "csrfmiddlewaretoken":
                continue
            if 'type="checkbox"' in tag:
                data[name] = "1" if " checked" in tag else "0"
            else:
                value = re.search(r'value="([^"]*)"', tag)
                data[name] = value.group(1) if value else ""
        self.assertTrue(set(data) <= set(_visible_keys("journal")), data)
        data["journal.lesson_edit_minutes"] = "300"
        response = self._client(self.rim).post(
            reverse("accounts:system_settings_save"), data=data, content_type="application/json"
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual([item["key"] for item in response.json()["changed"]], ["journal.lesson_edit_minutes"])
        self.assertEqual(
            dict(RuntimeSetting.objects.values_list("key", "value")),
            {"otp.max_attempts": 8, "journal.lesson_edit_minutes": 300},
        )

    def test_dean_gets_no_sub_pages(self):
        response = self._client(self.dean).get(
            reverse("accounts:profile_section_fragment", kwargs={"section": "system-settings"}), {"ss_group": "login"}
        )
        self.assertEqual(response.status_code, 403)

    # ── qlobal axtarış ─────────────────────────────────────────────────────
    def test_global_cabinet_search_finds_a_settings_key(self):
        payload = self._client(self.rim).get(reverse("accounts:global_search"), {"q": "sessiya cixis"}).json()
        groups = {group["key"]: group for group in payload["groups"]}
        self.assertIn("settings", groups)
        item = groups["settings"]["items"][0]
        self.assertIn("ss_group=session", item["url"])
        self.assertIn("ss_key=session.idle_hours", item["url"])
        self.assertIn("session.idle_hours", item["subtitle"])

        dean = self._client(self.dean).get(reverse("accounts:global_search"), {"q": "sessiya cixis"}).json()
        self.assertNotIn("settings", {group["key"] for group in dean["groups"]})
