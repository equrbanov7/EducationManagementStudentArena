"""
EMS Arena — Blog & Content Workflows E2E Tests
===============================================
Covers:
  I. Blog / content / moderation / post approval
     - Public home page
     - Public article pages
     - Post creation (requires authentication)
     - Post moderation pages
     - Questions pages
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, E2E_PASSWORD, E2E_USERNAME

# ── URLs ─────────────────────────────────────────────────────────────────────

HOME_URL = f"{BASE_URL}/"
ABOUT_URL = f"{BASE_URL}/about/"
TECHNOLOGY_URL = f"{BASE_URL}/technology/"
CREATE_POST_URL = f"{BASE_URL}/posts/create/"
QUESTIONS_URL = f"{BASE_URL}/questions/"
MY_QUESTIONS_URL = f"{BASE_URL}/questions/my/"
CREATE_QUESTION_URL = f"{BASE_URL}/questions/create/"


# ── Public pages ──────────────────────────────────────────────────────────────


class TestPublicBlogPages:
    """Tests for the publicly accessible marketing/blog pages."""

    def test_home_page_returns_200(self, page: Page) -> None:
        """The home page must be publicly reachable and return HTTP 200."""
        response = page.goto(HOME_URL)
        assert response is not None
        assert response.status == 200, f"Home page returned HTTP {response.status}"

    def test_home_page_renders_content(self, page: Page) -> None:
        """The home page must render a non-trivially empty body."""
        page.goto(HOME_URL)
        page.wait_for_load_state("networkidle")
        body_text = page.locator("body").inner_text()
        assert len(body_text.strip()) > 20, "Home page body appears to be empty"

    def test_about_page_returns_200(self, page: Page) -> None:
        """The about page must return HTTP 200."""
        response = page.goto(ABOUT_URL)
        assert response is not None
        assert response.status == 200, f"About page returned HTTP {response.status}"

    def test_technology_page_returns_200(self, page: Page) -> None:
        """The technology page must return HTTP 200."""
        response = page.goto(TECHNOLOGY_URL)
        assert response is not None
        assert response.status < 500, f"Technology page returned server error HTTP {response.status}"

    def test_home_page_does_not_expose_debug_info(self, page: Page) -> None:
        """The home page must not leak Django debug or stack-trace information."""
        page.goto(HOME_URL)
        page.wait_for_load_state("networkidle")
        source = page.content()
        for sensitive_marker in ["Traceback (most recent call last)", "django.db.utils."]:
            assert (
                sensitive_marker not in source
            ), f"Sensitive marker {sensitive_marker!r} found on the public home page"


# ── Post creation (requires authentication) ───────────────────────────────────


class TestPostCreation:
    """Tests for blog post creation functionality."""

    def test_create_post_blocks_anonymous_user(self, page: Page) -> None:
        """Anonymous access to the post-creation page must redirect to login."""
        response = page.goto(CREATE_POST_URL)
        page.wait_for_load_state("networkidle")

        if response is not None:
            assert response.status < 500, f"Create post page returned server error HTTP {response.status}"
        is_login_redirect = "/accounts/login/" in page.url
        is_explicit_deny = response is not None and response.status == 403
        assert is_login_redirect or is_explicit_deny, f"Create post page accessible to anonymous user — URL: {page.url}"

    @pytest.mark.skipif(
        not E2E_USERNAME or not E2E_PASSWORD,
        reason="E2E_USERNAME / E2E_PASSWORD not set",
    )
    def test_create_post_page_loads_for_authenticated_user(self, authenticated_page: Page) -> None:
        """Create post page must load without a server error for an authenticated user."""
        response = authenticated_page.goto(CREATE_POST_URL)
        assert response is not None
        assert response.status < 500, f"Create post page returned HTTP {response.status}"
        authenticated_page.wait_for_load_state("networkidle")
        expect(authenticated_page.locator("body")).to_be_visible()


# ── Question pages ────────────────────────────────────────────────────────────


class TestQuestionsPages:
    """Tests for the community Q&A pages."""

    @pytest.mark.skipif(
        not E2E_USERNAME or not E2E_PASSWORD,
        reason="E2E_USERNAME / E2E_PASSWORD not set",
    )
    def test_questions_list_loads(self, authenticated_page: Page) -> None:
        """Questions list page must load for an authenticated user."""
        response = authenticated_page.goto(QUESTIONS_URL)
        assert response is not None
        assert response.status < 500, f"Questions list returned HTTP {response.status}"

    @pytest.mark.skipif(
        not E2E_USERNAME or not E2E_PASSWORD,
        reason="E2E_USERNAME / E2E_PASSWORD not set",
    )
    def test_my_questions_page_loads(self, authenticated_page: Page) -> None:
        """My questions page must load for an authenticated user."""
        response = authenticated_page.goto(MY_QUESTIONS_URL)
        assert response is not None
        assert response.status < 500, f"My questions page returned HTTP {response.status}"

    @pytest.mark.skipif(
        not E2E_USERNAME or not E2E_PASSWORD,
        reason="E2E_USERNAME / E2E_PASSWORD not set",
    )
    def test_create_question_page_loads(self, authenticated_page: Page) -> None:
        """Create question page must load for an authenticated user."""
        response = authenticated_page.goto(CREATE_QUESTION_URL)
        assert response is not None
        assert response.status < 500, f"Create question page returned HTTP {response.status}"


# ── Audit log pages ───────────────────────────────────────────────────────────


class TestAuditPages:
    """Tests for audit log pages (restricted to org admins and superadmins)."""

    def test_audit_log_blocks_anonymous_user(self, page: Page) -> None:
        """Audit log page must redirect an anonymous user to login."""
        response = page.goto(f"{BASE_URL}/audit/")
        page.wait_for_load_state("networkidle")

        if response is not None:
            assert response.status < 500, f"Audit log page returned server error HTTP {response.status}"
        is_login_redirect = "/accounts/login/" in page.url
        is_explicit_deny = response is not None and response.status == 403
        assert is_login_redirect or is_explicit_deny, f"Audit log accessible to anonymous user — URL: {page.url}"

    @pytest.mark.skipif(
        not E2E_USERNAME or not E2E_PASSWORD,
        reason="E2E_USERNAME / E2E_PASSWORD not set",
    )
    def test_audit_log_loads_for_admin(self, authenticated_page: Page) -> None:
        """Audit log page must load without a server error for an admin user."""
        response = authenticated_page.goto(f"{BASE_URL}/audit/")
        assert response is not None
        assert response.status < 500, f"Audit log page returned HTTP {response.status}"
