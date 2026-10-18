"""Publik ``/yoxla/`` səhifəsi: etibarlı / ləğv / tapılmadı, maskalı ad, PII sızmır, limit, faylı müqayisə."""

from __future__ import annotations

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.verification.services import revoke_seal
from core.rate_limit import _rate_limit_cache
from core.rls import bypass_rls

from .world import build_world, download_transcript, latest_seal

UNKNOWN = "QKUPB-ZZZZ-ZZZZ-ZZZZ-ZZZZ"


class PublicVerifyTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.w = build_world("qkupb")

    def setUp(self):
        cache.clear()
        _rate_limit_cache().clear()
        self.pdf = download_transcript(self.w).content
        self.seal = latest_seal(subject_user=self.w["student"])
        self.client = Client(enforce_csrf_checks=False)

    def _get(self, code, **extra):
        return self.client.get(reverse("verification:detail", args=[code]), REMOTE_ADDR="85.132.1.1", **extra)

    def test_form_page_is_public_and_noindex(self):
        response = self.client.get(reverse("verification:home"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("noindex", response["X-Robots-Tag"])
        self.assertIn("no-store", response["Cache-Control"])
        # `same-origin` (no-referrer DEYİL): öz formamızın POST-u real Origin daşısın, CSRF HTTPS-də keçsin.
        self.assertEqual(response["Referrer-Policy"], "same-origin")
        self.assertContains(response, 'name="robots" content="noindex, nofollow"')

    def test_query_code_redirects_to_canonical_url(self):
        raw = self.seal.code.lower().replace("-", " ")
        response = self.client.get(reverse("verification:home"), {"kod": raw})
        self.assertRedirects(
            response, reverse("verification:detail", args=[self.seal.code]), fetch_redirect_response=False
        )
        lower = self._get(self.seal.code.lower())
        self.assertRedirects(
            lower, reverse("verification:detail", args=[self.seal.code]), fetch_redirect_response=False
        )

    def test_valid_seal_shows_status_and_minimal_facts(self):
        response = self._get(self.seal.code)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn("Sənəd etibarlıdır", body)
        self.assertIn("Elvin Q.", body)
        self.assertIn("Kompüter elmləri", body)
        self.assertIn(self.w["org"].name, body)
        self.assertIn(self.seal.code, body)

    def test_page_leaks_no_personal_data_or_grades(self):
        body = self._get(self.seal.code).content.decode()
        student = self.w["student"]
        for leak in ("Qurbanov", student.username, student.email, "CS101", "Proqramlaşdırmanın", "KE-101"):
            self.assertNotIn(leak, body, leak)
        self.assertNotIn(self.w["owner"].username, body)  # verən əməkdaş da görünmür

    def test_revoked_seal_shows_date_but_not_reason(self):
        with bypass_rls():
            revoke_seal(seal=self.seal, actor=self.w["office"], reason="Səhv məlumatla verilib, yenisi verildi.")
        response = self._get(self.seal.code)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Sənəd ləğv edilib")
        # Səbəb yalnız əməkdaşlara görünür (məxfilik) — publik səhifədə yalnız ləğv tarixi.
        self.assertNotContains(response, "Səhv məlumatla verilib, yenisi verildi.")
        self.assertNotContains(response, "Sənəd etibarlıdır")

    def test_unknown_and_malformed_codes_get_the_same_404(self):
        unknown = self._get(UNKNOWN)
        malformed = self._get("not-a-code")
        self.assertEqual(unknown.status_code, 404)
        self.assertEqual(malformed.status_code, 404)
        self.assertContains(unknown, "Sənəd tapılmadı", status_code=404)
        self.assertIn("noindex", unknown["X-Robots-Tag"])
        strip = lambda r: r.content.decode().replace(UNKNOWN, "")  # noqa: E731
        self.assertEqual(strip(unknown).count("dv-alert--danger"), strip(malformed).count("dv-alert--danger"))

    def test_lookup_is_audited_with_ip_hash_not_ip(self):
        from apps.audit.models import AuditLog

        self._get(self.seal.code)
        with bypass_rls():
            row = AuditLog.objects.filter(resource_type="verification.lookup", resource_id=self.seal.code).first()
        self.assertIsNotNone(row)
        self.assertEqual(row.organization_id, self.w["org"].pk)
        self.assertEqual(row.new_values["result"], "valid")
        self.assertEqual(len(row.new_values["ip_hash"]), 16)
        self.assertIsNone(row.ip_address)
        self.assertNotIn("85.132.1.1", str(row.new_values))

    @override_settings(DOCUMENT_VERIFY_MISS_RATE_LIMIT="3/10m", DOCUMENT_VERIFY_RATE_LIMIT="100/10m")
    def test_misses_are_rate_limited_and_then_even_valid_codes_are_not_resolved(self):
        for _ in range(3):
            self.assertEqual(self._get(UNKNOWN).status_code, 404)
        limited = self._get(self.seal.code)
        self.assertEqual(limited.status_code, 429)
        self.assertIn("Retry-After", limited)
        self.assertNotContains(limited, "Elvin Q.", status_code=429)
        other_ip = self.client.get(reverse("verification:detail", args=[self.seal.code]), REMOTE_ADDR="85.132.1.2")
        self.assertEqual(other_ip.status_code, 200)

    @override_settings(DOCUMENT_VERIFY_RATE_LIMIT="2/10m")
    def test_total_lookups_are_rate_limited(self):
        self.assertEqual(self._get(self.seal.code).status_code, 200)
        self.assertEqual(self._get(self.seal.code).status_code, 200)
        self.assertEqual(self._get(self.seal.code).status_code, 429)

    # ── faylı müqayisə ────────────────────────────────────────────────────
    def _upload(self, content, name="transkript.pdf", client=None):
        client = client or self.client
        return client.post(
            reverse("verification:detail", args=[self.seal.code]),
            {"sened": SimpleUploadedFile(name, content, content_type="application/pdf")},
            REMOTE_ADDR="85.132.1.1",
        )

    def test_identical_pdf_matches(self):
        response = self._upload(self.pdf)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "tam eynidir")
        self.assertEqual(response.context["compare_result"], "match")

    def test_tampered_pdf_does_not_match(self):
        tampered = self.pdf[:-10] + b"0000000000"
        response = self._upload(tampered)
        self.assertEqual(response.context["compare_result"], "mismatch")
        self.assertContains(response, "eyni DEYİL")

    def test_non_pdf_is_rejected_by_magic_bytes(self):
        response = self._upload(b"GIF89a fake", name="x.pdf")
        self.assertEqual(response.context["compare_result"], "not_pdf")

    @override_settings(DOCUMENT_VERIFY_UPLOAD_MAX_MB=1)
    def test_oversized_upload_is_rejected_and_not_stored(self):
        response = self._upload(b"%PDF-" + b"0" * (1024 * 1024 + 10))
        self.assertEqual(response.context["compare_result"], "too_large")

    def test_upload_is_kept_in_memory_only(self):
        from apps.verification import upload

        response = self._upload(self.pdf)
        handlers = response.wsgi_request.upload_handlers
        self.assertEqual([type(h) for h in handlers], [upload._CappedMemoryUploadHandler])

    def test_upload_requires_csrf_token(self):
        strict = Client(enforce_csrf_checks=True)
        response = self._upload(self.pdf, client=strict)
        self.assertEqual(response.status_code, 403)

    def test_upload_passes_csrf_over_https_with_same_origin(self):
        """Real brauzer: HTTPS, CSRF yoxlanılır, `Origin` öz domenimizdir (Referrer-Policy: same-origin)."""
        strict = Client(enforce_csrf_checks=True)
        url = reverse("verification:detail", args=[self.seal.code])
        page = strict.get(url, secure=True, REMOTE_ADDR="85.132.1.1")
        self.assertEqual(page.status_code, 200)
        token = page.cookies["csrftoken"].value if "csrftoken" in page.cookies else strict.cookies["csrftoken"].value
        response = strict.post(
            url,
            {
                "sened": SimpleUploadedFile("t.pdf", self.pdf, content_type="application/pdf"),
                "csrfmiddlewaretoken": token,
            },
            secure=True,
            HTTP_ORIGIN="https://testserver",
            REMOTE_ADDR="85.132.1.1",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["compare_result"], "match")

    def test_revoke_reason_is_not_read_by_public_lookup(self):
        from apps.verification import lookup

        self.assertNotIn("revoke_reason", lookup._PUBLIC_COLUMNS)

    @override_settings(DOCUMENT_VERIFY_UPLOAD_RATE_LIMIT="1/10m")
    def test_upload_is_rate_limited(self):
        self.assertEqual(self._upload(self.pdf).status_code, 200)
        self.assertEqual(self._upload(self.pdf).status_code, 429)

    def test_upload_to_unknown_code_is_404(self):
        response = self.client.post(
            reverse("verification:detail", args=[UNKNOWN]),
            {"sened": SimpleUploadedFile("t.pdf", self.pdf, content_type="application/pdf")},
        )
        self.assertEqual(response.status_code, 404)
