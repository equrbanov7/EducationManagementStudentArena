"""Təhlükəsizlik başlıqlarının snapshot testləri (Faza 7, audit 2026-07-02).

Auditin "tests/security boşdur" tapıntısını bağlayır: middleware/settings
zəncirinin verdiyi qoruyucu başlıqlar burada MÜQAVİLƏ kimi sabitlənir —
təsadüfi silinmə/zəifləmə CI-də dərhal görünür.
"""

from django.test import TestCase


class SecurityHeadersSnapshotTests(TestCase):
    """Anonim login səhifəsi üzərində başlıq dəsti."""

    def _get_login(self):
        response = self.client.get("/accounts/login/")
        self.assertEqual(response.status_code, 200)
        return response

    def test_clickjacking_and_sniffing_headers(self):
        response = self._get_login()
        self.assertEqual(response.headers.get("X-Frame-Options"), "DENY")
        self.assertEqual(response.headers.get("X-Content-Type-Options"), "nosniff")

    def test_hardening_headers_from_security_middleware(self):
        response = self._get_login()
        self.assertEqual(response.headers.get("Referrer-Policy"), "strict-origin-when-cross-origin")
        self.assertIn("camera=()", response.headers.get("Permissions-Policy", ""))
        self.assertEqual(response.headers.get("Cross-Origin-Opener-Policy"), "same-origin")
        self.assertEqual(response.headers.get("Cross-Origin-Resource-Policy"), "same-origin")

    def test_csp_present_with_nonce_and_no_unsafe_inline_scripts(self):
        response = self._get_login()
        csp = response.headers.get("Content-Security-Policy", "")
        self.assertIn("script-src", csp)
        self.assertIn("'nonce-", csp)
        # script-src daxilində 'unsafe-inline' QADAĞANDIR (yalnız style-src-attr
        # keçid dövrü üçün açıqdır) — reqressiyaya qarşı qoruyucu.
        script_src = [d for d in csp.split(";") if d.strip().startswith("script-src")]
        self.assertTrue(script_src)
        self.assertNotIn("'unsafe-inline'", script_src[0])

    def test_csp_nonce_is_actually_used_in_markup(self):
        response = self._get_login()
        csp = response.headers.get("Content-Security-Policy", "")
        nonce = None
        for part in csp.replace(";", " ").split():
            if part.startswith("'nonce-"):
                nonce = part[len("'nonce-") :].rstrip("'")
                break
        self.assertTrue(nonce, "CSP başlığında nonce tapılmadı")
        self.assertIn(f'nonce="{nonce}"', response.content.decode("utf-8"))

    def test_request_id_echoed_for_tracing(self):
        response = self._get_login()
        self.assertTrue(response.headers.get("X-Request-ID"))
