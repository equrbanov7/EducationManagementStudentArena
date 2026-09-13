"""Codex audit §11 (2026-09-13) — Microsoft Clarity yalnız anonim səhifələrdə.

Tapıntı: «Autentifikasiyalı kabinetdə Clarity aktiv görünür; şəxsi məlumat
maskalanması və saxlanma siyasəti ayrıca yoxlanmalıdır.» Session-replay teqi
`templates/partials/_microsoft_clarity.html`-dən HƏR səhifəyə (kabinet daxil)
düşürdü. İndi teq `microsoft_clarity_enabled` bayrağı ilə qapılanır:

  * anonim səhifə + layihə id-si → teq VAR;
  * autentifikasiyalı kabinet → teq YOXDUR (susma);
  * `MICROSOFT_CLARITY_AUTHENTICATED=True` → kabinetdə də VAR (deployment qərarı);
  * CSP mənbələri (`script-src` / `connect-src` / `img-src`) DƏYİŞMİR;
  * şəxsi məlumat daşıyan açıq formalar `data-clarity-mask="True"` daşıyır,
    `data-clarity-unmask` heç yerdə yoxdur.
"""

from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from core.context_processors import feature_flags

CLARITY_MARKER = "https://www.clarity.ms/tag/"
PROJECT_ID = "codextestclarity"

REPO_ROOT = Path(__file__).resolve().parents[2]
PII_FORM_TEMPLATES = (
    "apps/accounts/templates/accounts/login.html",
    "apps/accounts/templates/accounts/register.html",
    "apps/accounts/templates/accounts/verify_code.html",
    "apps/accounts/templates/accounts/password_reset.html",
    "apps/accounts/templates/accounts/password_reset_confirm.html",
    "apps/accounts/templates/accounts/first_login_set_password.html",
    "apps/contact/templates/contact/contact.html",
)


@override_settings(MICROSOFT_CLARITY_PROJECT_ID=PROJECT_ID, MICROSOFT_CLARITY_AUTHENTICATED=False)
class ClarityGatingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username="clarity_gate_user", email="clarity_gate@example.com", password="StrongPass123!"
        )

    def test_anonymous_page_carries_the_tag(self):
        response = self.client.get(reverse("accounts:student_login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, CLARITY_MARKER, html=False)
        self.assertContains(response, PROJECT_ID, html=False)

    def test_authenticated_cabinet_does_not_carry_the_tag(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, CLARITY_MARKER, html=False)
        self.assertNotContains(response, "clarity.ms", html=False)

    @override_settings(MICROSOFT_CLARITY_AUTHENTICATED=True)
    def test_flag_opts_the_cabinet_back_in(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, CLARITY_MARKER, html=False)

    @override_settings(MICROSOFT_CLARITY_PROJECT_ID="")
    def test_no_project_id_means_no_tag_anywhere(self):
        response = self.client.get(reverse("accounts:student_login"))
        self.assertNotContains(response, CLARITY_MARKER, html=False)

    def test_context_flag_is_computed_from_user_and_setting(self):
        request = RequestFactory().get("/")
        request.user = self.user
        self.assertFalse(feature_flags(request)["microsoft_clarity_enabled"])
        with override_settings(MICROSOFT_CLARITY_AUTHENTICATED=True):
            self.assertTrue(feature_flags(request)["microsoft_clarity_enabled"])
        # `request.user` olmayan render (məs. e-poçt şablonu) — anonim sayılır, xəta yox.
        bare = RequestFactory().get("/")
        self.assertTrue(feature_flags(bare)["microsoft_clarity_enabled"])

    def test_csp_sources_are_unchanged(self):
        directives = settings.CONTENT_SECURITY_POLICY["DIRECTIVES"]
        self.assertIn("https://www.clarity.ms", directives["script-src"])
        self.assertIn("https://*.clarity.ms", directives["script-src"])
        self.assertIn("https://c.bing.com", directives["connect-src"])
        self.assertIn("https://*.clarity.ms", directives["img-src"])
        self.assertNotIn("'unsafe-inline'", directives["script-src"])

    def test_public_pii_forms_are_masked_and_nothing_is_unmasked(self):
        for relative in PII_FORM_TEMPLATES:
            with self.subTest(template=relative):
                source = (REPO_ROOT / relative).read_text(encoding="utf-8")
                self.assertIn('data-clarity-mask="True"', source)
        for path in list(REPO_ROOT.glob("templates/**/*.html")) + list(REPO_ROOT.glob("apps/*/templates/**/*.html")):
            self.assertNotIn("data-clarity-unmask", path.read_text(encoding="utf-8"), msg=str(path))
