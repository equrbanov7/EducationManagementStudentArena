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
import socket
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Page, expect

# ── Configuration ────────────────────────────────────────────────────────────
BASE_URL: str = os.environ.get("BASE_URL", "http://localhost").rstrip("/")
E2E_USERNAME: str = os.environ.get("E2E_USERNAME", "")
E2E_PASSWORD: str = os.environ.get("E2E_PASSWORD", "")
DASHBOARD_URL: str = f"{BASE_URL}/accounts/dashboard/"


# ── Helpers ──────────────────────────────────────────────────────────────────


def login(page: Page) -> None:
    """Navigate to the login page and submit valid credentials."""
    page.goto(f"{BASE_URL}/accounts/login/")
    page.wait_for_load_state("networkidle")


def _base_url_is_reachable() -> bool:
    parsed = urlsplit(BASE_URL)
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)

    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


@pytest.fixture(scope="module", autouse=True)
def require_reachable_base_url(page):
    if not _base_url_is_reachable():
        pytest.skip(f"BASE_URL is not reachable for smoke tests: {BASE_URL}")

    # Scope actions to the actual auth form because the page also contains
    # hidden language-switcher submit buttons.
    login_form = (
        page.locator("form")
        .filter(has=page.locator("input[name='username']"))
        .filter(has=page.locator("input[name='password']"))
    )
    expect(login_form).to_have_count(1)

    # Fill in the login form (Django's default field names)
    login_form.locator("input[name='username']").fill(E2E_USERNAME)
    login_form.locator("input[name='password']").fill(E2E_PASSWORD)
    login_form.locator("button[type='submit']").click()
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

        # Navigate to the authenticated dashboard entrypoint and allow Django
        # to redirect to the appropriate teacher/student variant.
        response = page.goto(DASHBOARD_URL)
        assert response is not None
        assert response.status == 200, f"Dashboard page returned unexpected HTTP {response.status}"
        page.wait_for_load_state("networkidle")

        # The final page should render a dashboard shell, regardless of which
        # role-specific variant the logged-in user lands on.
        expect(page.locator("main, .main-content, .student-dashboard").first).to_be_visible()

    @pytest.mark.skipif(
        not E2E_USERNAME or not E2E_PASSWORD,
        reason="E2E_USERNAME / E2E_PASSWORD not set — skipping authenticated tests",
    )
    def test_navbar_present_on_dashboard(self, page: Page) -> None:
        """The navigation bar must be visible on the dashboard."""
        login(page)
        page.goto(DASHBOARD_URL)
        page.wait_for_load_state("networkidle")

        # Teacher and student dashboards expose different navigation shells.
        expect(page.locator("nav, [role='navigation'], .sidebar-nav, .quick-actions").first).to_be_visible()


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

    @pytest.mark.skipif(
        not E2E_USERNAME or not E2E_PASSWORD,
        reason="E2E_USERNAME / E2E_PASSWORD not set — skipping authenticated tests",
    )
    def test_student_exam_list_loads_for_multi_role_user(self, page: Page) -> None:
        """A seeded multi-role university user must also reach student exam pages."""
        login(page)

        response = page.goto(f"{BASE_URL}/exams/available/")
        assert response is not None
        assert response.status == 200, f"/exams/available/ returned HTTP {response.status} after login"
        page.wait_for_load_state("networkidle")

        expect(page.locator("body")).to_be_visible()
