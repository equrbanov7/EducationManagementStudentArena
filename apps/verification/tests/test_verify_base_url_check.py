"""Rəy 2026-10-21: QR yoxlama ünvanının kökü üçün deploy check-i (``verification.E001`` / ``W001``).

Production-da ``SITE_URL`` defoltu ``https://127.0.0.1``-dir; .env-də unudulsa çap olunan hər QR kod kənardan
açılmayan ünvana aparır. ``check --deploy`` (remote_deploy.sh preflight, CI _security.yml) bunu dayandırır.
"""

from __future__ import annotations

from pathlib import Path

from django.core import checks
from django.test import SimpleTestCase, override_settings

import yaml

from apps.verification.checks import (
    E_VERIFY_BASE_URL,
    W_VERIFY_BASE_URL,
    check_document_verify_base_url,
    verify_base_url_problem,
)

ROOT = Path(__file__).resolve().parents[3]


class VerifyBaseUrlProblemTest(SimpleTestCase):
    def test_bad_bases_are_reported(self):
        for base in (
            "",
            "   ",
            "https://127.0.0.1",
            "https://127.0.1.5:8443",
            "http://localhost:8000",
            "https://localhost",
            "https://0.0.0.0",
            "https://[::1]",
            "http://ems.wcu.edu.az",
            "ems.wcu.edu.az",
        ):
            with self.subTest(base=base):
                self.assertIsNotNone(verify_base_url_problem(base))

    def test_public_https_base_passes(self):
        for base in ("https://ems.wcu.edu.az", "https://ems.wcu.edu.az/", "https://10.0.2.42"):
            with self.subTest(base=base):
                self.assertIsNone(verify_base_url_problem(base))


class VerifyBaseUrlCheckTest(SimpleTestCase):
    def _ids(self):
        return [message.id for message in check_document_verify_base_url(None)]

    @override_settings(
        MANAGEMENT_COMMAND_ENVIRONMENT="production", DOCUMENT_VERIFY_BASE_URL="", SITE_URL="https://127.0.0.1"
    )
    def test_production_default_site_url_is_an_error(self):
        messages = check_document_verify_base_url(None)
        self.assertEqual([message.id for message in messages], [E_VERIFY_BASE_URL])
        self.assertEqual(messages[0].level, checks.ERROR)

    @override_settings(MANAGEMENT_COMMAND_ENVIRONMENT="production", DOCUMENT_VERIFY_BASE_URL="", SITE_URL="")
    def test_production_empty_base_is_an_error(self):
        self.assertEqual(self._ids(), [E_VERIFY_BASE_URL])

    @override_settings(
        MANAGEMENT_COMMAND_ENVIRONMENT="production",
        DOCUMENT_VERIFY_BASE_URL="https://ems.wcu.edu.az",
        SITE_URL="https://127.0.0.1",
    )
    def test_explicit_verify_base_wins_over_site_url(self):
        self.assertEqual(self._ids(), [])

    @override_settings(
        MANAGEMENT_COMMAND_ENVIRONMENT="production", DOCUMENT_VERIFY_BASE_URL="", SITE_URL="https://ems.wcu.edu.az"
    )
    def test_production_public_site_url_passes(self):
        self.assertEqual(self._ids(), [])

    @override_settings(
        MANAGEMENT_COMMAND_ENVIRONMENT="local", DOCUMENT_VERIFY_BASE_URL="", SITE_URL="http://172.20.10.11:8000"
    )
    def test_non_production_is_only_a_warning(self):
        messages = check_document_verify_base_url(None)
        self.assertEqual([message.id for message in messages], [W_VERIFY_BASE_URL])
        self.assertEqual(messages[0].level, checks.WARNING)

    def test_registered_as_deploy_only_check(self):
        registry = checks.registry.registry
        self.assertIn(check_document_verify_base_url, registry.get_checks(include_deployment_checks=True))
        self.assertNotIn(check_document_verify_base_url, registry.get_checks(include_deployment_checks=False))


class ComposePassThroughTest(SimpleTestCase):
    def test_compose_passes_verify_base_url_like_site_url(self):
        data = yaml.safe_load((ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8"))
        env = data["x-app-env"]
        self.assertEqual(env["SITE_URL"], "${SITE_URL}")
        self.assertEqual(env["DOCUMENT_VERIFY_BASE_URL"], "${DOCUMENT_VERIFY_BASE_URL:-}")
        for service in ("app", "celery_worker", "celery_worker_heavy", "celery_beat"):
            with self.subTest(service=service):
                service_env = data["services"][service]["environment"]
                self.assertIn("DOCUMENT_VERIFY_BASE_URL", service_env)

    def test_ci_deploy_check_sets_a_public_verify_base(self):
        workflow = (ROOT / ".github/workflows/_security.yml").read_text(encoding="utf-8")
        self.assertIn('DOCUMENT_VERIFY_BASE_URL: "https://', workflow)
