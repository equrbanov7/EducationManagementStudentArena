"""Sahib 2026-10-01 — kənardan /jurnal/ açılanda xam «403 Forbidden · nginx» əvəzinə izah səhifəsi.

nginx kənar sorğunu (jurnal Django-ya çatmadan) ``/accounts/sebeke/<area>/``-ə yönləndirir; səhifə
403 qaytarır, sadə dildə səbəbi və «Nə etməli?» addımlarını göstərir, heç bir jurnal məlumatı yoxdur.
"""

from django.test import TestCase
from django.urls import reverse


class NetworkZonePageTest(TestCase):
    def test_journal_page_explains_in_plain_language(self):
        response = self.client.get(reverse("accounts:network_zone_denied", args=["jurnal"]))

        self.assertEqual(response.status_code, 403)
        self.assertContains(response, "Elektron jurnal yalnız universitet şəbəkəsində açılır", status_code=403)
        self.assertContains(response, "mobil interneti söndürün", status_code=403)
        self.assertContains(response, 'class="error-zone-steps"', status_code=403)
        self.assertIn("no-store", response["Cache-Control"])

    def test_admin_area_has_its_own_title(self):
        response = self.client.get(reverse("accounts:network_zone_denied", args=["idareetme"]))

        self.assertContains(response, "İdarəetmə paneli yalnız universitet şəbəkəsində açılır", status_code=403)

    def test_unknown_area_falls_back_to_journal_text(self):
        response = self.client.get(reverse("accounts:network_zone_denied", args=["xyz"]))

        self.assertContains(response, "Elektron jurnal yalnız universitet şəbəkəsində açılır", status_code=403)

    def test_nginx_rewrites_external_journal_to_this_page(self):
        with open("docker/nginx/nginx.conf", encoding="utf-8") as handle:
            conf = handle.read()
        self.assertIn("rewrite ^ /accounts/sebeke/jurnal/? last;", conf)
        self.assertIn("rewrite ^ /accounts/sebeke/idareetme/? last;", conf)
        self.assertNotIn('"^external:/(jurnal|manage)/") { return 403; }', conf)
