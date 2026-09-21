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

    @staticmethod
    def _inline_executable_scripts(html: str) -> list:
        """`src`-siz, JSON/LD+JSON olmayan `<script>` teqləri — CSP altında YALNIZ nonce ilə icra olunar."""
        import re

        return [
            tag
            for tag in re.findall(r"<script\b[^>]*>", html)
            if "src=" not in tag and "application/json" not in tag and "ld+json" not in tag
        ]

    def test_csp_script_src_has_no_unsafe_inline(self):
        response = self._get_login()
        csp = response.headers.get("Content-Security-Policy", "")
        self.assertIn("script-src", csp)
        # script-src daxilində 'unsafe-inline' QADAĞANDIR (yalnız style-src-attr
        # keçid dövrü üçün açıqdır) — reqressiyaya qarşı qoruyucu.
        script_src = [d for d in csp.split(";") if d.strip().startswith("script-src")]
        self.assertTrue(script_src)
        self.assertNotIn("'unsafe-inline'", script_src[0])

    def test_csp_nonce_is_used_when_present_and_inline_scripts_carry_it(self):
        """2026-09-21: bütün skriptlər xarici fayldadır (`src=`), konfiq JSON
        data-adalarındadır. django-csp nonce-u başlığa yalnız şablon
        `request.csp_nonce`-a müraciət edəndə yazır — inline skripti olmayan
        səhifədə nonce OLMAYA BİLƏR. Qayda: başlıqda nonce varsa markup-da
        işlənməlidir; markup-dakı hər icra olunan inline skript nonce daşımalıdır."""
        response = self._get_login()
        csp = response.headers.get("Content-Security-Policy", "")
        nonce = None
        for part in csp.replace(";", " ").split():
            if part.startswith("'nonce-"):
                nonce = part[len("'nonce-") :].rstrip("'")
                break
        html = response.content.decode("utf-8")
        inline = self._inline_executable_scripts(html)
        if nonce:
            self.assertIn(f'nonce="{nonce}"', html)
        else:
            self.assertEqual(inline, [], f"nonce-suz inline skript: {inline}")
        self.assertEqual([tag for tag in inline if "nonce=" not in tag], [], "nonce daşımayan inline skript var")

    def test_request_id_echoed_for_tracing(self):
        response = self._get_login()
        self.assertTrue(response.headers.get("X-Request-ID"))
