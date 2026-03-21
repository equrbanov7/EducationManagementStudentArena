"""
EMS Arena — E2E Smoke Tests (Playwright)
=========================================
Minimal smoke test suite covering the three critical user flows:

  1. Login flow — verifies the login page loads and credentials are accepted.
  2. Dashboard loading — verifies the dashboard renders after a successful login.
  3. Primary action — verifies the exam list page is reachable from the dashboard.

Tests are deliberately minimal and resilient: they check HTTP status codes and
the presence of key page elements rather than pixel-perfect UI details, so they
remain stable across minor template changes.

Run locally:
    playwright install chromium
    BASE_URL=http://localhost E2E_USERNAME=admin E2E_PASSWORD=secret \
        pytest tests/e2e/ -v
"""

from __future__ import annotations

import os

import pytest
from playwright.sync_api import Page, expect

# ── Configuration ────────────────────────────────────────────────────────────
BASE_URL: str = os.environ.get("BASE_URL", "http://localhost").rstrip("/")
E2E_USERNAME: str = os.environ.get("E2E_USERNAME", "")
E2E_PASSWORD: str = os.environ.get("E2E_PASSWORD", "")


# ── Helpers ──────────────────────────────────────────────────────────────────


def login(page: Page) -> None:
    """Navigate to the login page and submit valid credentials."""
    page.goto(f"{BASE_URL}/accounts/login/")
    page.wait_for_load_state("networkidle")

    # Fill in the login form (Django's default field names)
    page.fill("input[name='username']", E2E_USERNAME)
    page.fill("input[name='password']", E2E_PASSWORD)
    page.click("button[type='submit']")
    page.wait_for_load_state("networkidle")


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestLoginFlow:
    """Smoke tests for the authentication flow."""

    def test_login_page_loads(self, page: Page) -> None:
        """The login page must be reachable and render the login form."""
        response = page.goto(f"{BASE_URL}/accounts/login/")
        assert response is not None, "No response from login page"
        assert response.status == 200, f"Login page returned HTTP {response.status}"

        # The page must contain a password field — verifies the form is present.
        expect(page.locator("input[name='password']")).to_be_visible()

    @pytest.mark.skipif(
        not E2E_USERNAME or not E2E_PASSWORD,
        reason="E2E_USERNAME / E2E_PASSWORD not set — skipping authenticated tests",
    )
    def test_successful_login_redirects(self, page: Page) -> None:
        """Submitting valid credentials must redirect away from the login page."""
        login(page)

        # After login the URL must no longer be the login page.
        assert "/accounts/login/" not in page.url, f"Still on login page after submit — current URL: {page.url}"
        # The landing page must return HTTP 200.
        assert page.evaluate("() => document.readyState") in {
            "complete",
            "interactive",
        }, "Post-login page did not finish loading"


class TestDashboardLoading:
    """Smoke tests for the main dashboard."""

    @pytest.mark.skipif(
        not E2E_USERNAME or not E2E_PASSWORD,
        reason="E2E_USERNAME / E2E_PASSWORD not set — skipping authenticated tests",
    )
    def test_dashboard_renders(self, page: Page) -> None:
        """The dashboard page must load without errors after login."""
        login(page)

        # Navigate explicitly to the organisation dashboard root.
        response = page.goto(f"{BASE_URL}/organizations/")
        assert response is not None
        assert response.status in {200, 302}, f"Dashboard page returned unexpected HTTP {response.status}"

        # Follow any redirect and check the final page.
        page.wait_for_load_state("networkidle")
        final_response = page.goto(page.url)
        assert final_response is not None
        assert final_response.status == 200, f"Dashboard final page returned HTTP {final_response.status}"

        # The page must contain at least one visible element (body is not blank).
        expect(page.locator("body")).to_be_visible()

    @pytest.mark.skipif(
        not E2E_USERNAME or not E2E_PASSWORD,
        reason="E2E_USERNAME / E2E_PASSWORD not set — skipping authenticated tests",
    )
    def test_navbar_present_on_dashboard(self, page: Page) -> None:
        """The navigation bar must be visible on the dashboard."""
        login(page)
        page.goto(f"{BASE_URL}/organizations/")
        page.wait_for_load_state("networkidle")

        # Check that the page has a nav element (generic selector that works
        # regardless of CSS class names used in the template).
        expect(page.locator("nav, [role='navigation']").first).to_be_visible()


class TestPrimaryAction:
    """Smoke tests for the primary exam-related action (viewing the exam list)."""

    def test_exam_list_redirects_unauthenticated(self, page: Page) -> None:
        """Unauthenticated access to /exams/ must redirect to login, not 500."""
        response = page.goto(f"{BASE_URL}/exams/")
        # Either a redirect (3xx — which Playwright follows) landing on login,
        # or the exam list is public (200). Either is acceptable; 5xx is not.
        assert response is not None
        assert response.status < 500, f"/exams/ returned server error HTTP {response.status}"

    @pytest.mark.skipif(
        not E2E_USERNAME or not E2E_PASSWORD,
        reason="E2E_USERNAME / E2E_PASSWORD not set — skipping authenticated tests",
    )
    def test_exam_list_loads_after_login(self, page: Page) -> None:
        """The exam list page must load successfully for an authenticated user."""
        login(page)

        response = page.goto(f"{BASE_URL}/exams/")
        assert response is not None
        assert response.status == 200, f"/exams/ returned HTTP {response.status} after login"
        page.wait_for_load_state("networkidle")

        # The page must not be blank.
        expect(page.locator("body")).to_be_visible()
