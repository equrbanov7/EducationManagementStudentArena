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


class AdminOtpExternalLoopTest(TestCase):
    """Sahib 2026-10-27: superadmin kənardan girəndə ``/manage/verify-otp/`` ERR_TOO_MANY_REDIRECTS verirdi.

    nginx kənar ``/manage/``-i izah səhifəsinə yönləndirirdi, OTP qapısı isə izah səhifəsini yenə verify-otp-yə
    göndərirdi. İndi OTP addımları kənardan açıqdır, izah səhifəsi də OTP-yə yönləndirmir.
    """

    def test_nginx_keeps_admin_otp_steps_open_before_manage_rewrite(self):
        for name in ("docker/nginx/nginx.conf", "docker/nginx/nginx.ci.conf"):
            with open(name, encoding="utf-8") as handle:
                conf = handle.read()
            rule = 'if ($ems_zone_path ~ "^external:/manage/(verify-otp|resend-otp|logout)/$") { set $ems_zone_path "open"; }'
            self.assertIn(rule, conf, name)
            block = conf.index("^external:/manage/") if '^external:/manage/")' in conf else conf.index("|manage|")
            self.assertLess(conf.index(rule), block, name)

    def test_zone_page_does_not_redirect_unverified_admin_to_otp(self):
        from django.contrib.auth import get_user_model
        from django.test import override_settings

        admin = get_user_model().objects.create_user(
            username="otp.loop.admin", password="x-Strong-pass-1", is_staff=True
        )
        self.client.force_login(admin)
        with override_settings(ADMIN_2FA_REQUIRED=True):
            page = self.client.get(reverse("accounts:network_zone_denied", args=["idareetme"]))
            other = self.client.get(reverse("accounts:profile"))

        self.assertEqual(page.status_code, 403)
        self.assertEqual(other.status_code, 302)
        self.assertEqual(other["Location"], reverse("admin:verify-otp"))
