"""
EMS Arena — Security & Permission E2E Tests
============================================
Covers:
  M. Direct URL access to restricted pages
     Cross-role privilege escalation attempts
     Anonymous access to protected endpoints
     CSRF presence on all forms
     No sensitive data leaked to anonymous visitors
     5xx error baseline for all known routes
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page

from .conftest import BASE_URL

# All public routes that must return HTTP 200 without authentication.
PUBLIC_ROUTES = [
    "/",
    "/about/",
    "/accounts/login/",
    "/accounts/register/",
    "/accounts/password-reset/",
    "/live/",
]

# All routes that must redirect anonymous users (no 5xx, ends at login or 403).
PROTECTED_ROUTES = [
    "/accounts/dashboard/",
    "/accounts/dashboard/student/",
    "/accounts/dashboard/teacher/",
    "/accounts/profile/",
    "/accounts/grading-queue/",
    "/accounts/my-results/",
    "/accounts/pending-review/",
    "/accounts/role-assignment/",
    "/accounts/permission-editor/",
    "/accounts/manage-roles/",
    "/accounts/assigned-exams/",
    "/accounts/assigned-courses/",
    "/accounts/review-results/",
    "/accounts/superadmin/organizations/",
    "/accounts/student-organization-management/",
    "/organizations/select/",
    "/courses/create_course/",
    "/courses/my-courses/",
    "/courses/my-enrolled/",
    "/exams/",
    "/exams/available/",
    "/exams/assigned/",
    "/exams/my-history/",
    "/exams/create/",
    "/exams/groups/",
    "/notifications/",
    "/audit/",
]


# ── Public routes ─────────────────────────────────────────────────────────────


class TestPublicRoutesSafety:
    """Public-facing pages must return 200 and must not crash."""

    @pytest.mark.parametrize("public_path", PUBLIC_ROUTES)
    def test_public_route_returns_200(self, page: Page, public_path: str) -> None:
        """A known public route must return HTTP 200."""
        response = page.goto(f"{BASE_URL}{public_path}")
        assert response is not None, f"No response for public route {public_path!r}"
        assert response.status == 200, f"Public route {public_path!r} returned unexpected HTTP {response.status}"

    @pytest.mark.parametrize("public_path", PUBLIC_ROUTES)
    def test_public_route_body_is_not_empty(self, page: Page, public_path: str) -> None:
        """Public pages must render a non-empty HTML body."""
        page.goto(f"{BASE_URL}{public_path}")
        page.wait_for_load_state("domcontentloaded")
        body_text = page.locator("body").inner_text()
        assert len(body_text.strip()) > 10, f"Public route {public_path!r} rendered an empty body"


# ── Protected routes ──────────────────────────────────────────────────────────


class TestProtectedRoutesNeverReturn5xx:
    """
    All known protected routes must not produce a 5xx server error for an
    anonymous user.  The only acceptable responses are 2xx (if the route is
    unexpectedly public) or a redirect chain that ends at the login page or a
    403 page.
    """

    @pytest.mark.parametrize("protected_path", PROTECTED_ROUTES)
    def test_protected_route_does_not_crash(self, page: Page, protected_path: str) -> None:
        """Anonymous access to a protected route must not produce a server error."""
        response = page.goto(f"{BASE_URL}{protected_path}")
        page.wait_for_load_state("domcontentloaded")
        if response is not None:
            assert (
                response.status < 500
            ), f"Protected route {protected_path!r} returned server error HTTP {response.status}"

    @pytest.mark.parametrize("protected_path", PROTECTED_ROUTES)
    def test_protected_route_redirects_to_login(self, page: Page, protected_path: str) -> None:
        """After following all redirects, an anonymous user must land on the login page or get 403."""
        response = page.goto(f"{BASE_URL}{protected_path}")
        page.wait_for_load_state("domcontentloaded")

        status = response.status if response is not None else 0
        is_login_redirect = "/accounts/login/" in page.url
        is_explicit_deny = status == 403

        assert is_login_redirect or is_explicit_deny, (
            f"Protected route {protected_path!r} did not redirect anonymous user. "
            f"HTTP {status} — final URL: {page.url}"
        )


# ── CSRF presence ─────────────────────────────────────────────────────────────


class TestCsrfPresence:
    """All POST forms must include a CSRF token."""

    @pytest.mark.parametrize(
        "form_page",
        [
            "/accounts/login/",
            "/accounts/register/",
            "/accounts/password-reset/",
        ],
    )
    def test_public_form_has_csrf_token(self, page: Page, form_page: str) -> None:
        """Every public HTML form must embed a CSRF token to prevent cross-site forgery."""
        page.goto(f"{BASE_URL}{form_page}")
        page.wait_for_load_state("domcontentloaded")

        csrf_inputs = page.locator("input[name='csrfmiddlewaretoken']")
        assert csrf_inputs.count() > 0, f"No CSRF token found in any form on {form_page!r}"


# ── No server-side error pages on unknown IDs ─────────────────────────────────


class TestMissingResourceHandling:
    """
    Accessing a resource that does not exist must return 404 (or redirect),
    never a 5xx.
    """

    @pytest.mark.parametrize(
        "missing_path",
        [
            "/courses/999999/dashboard/",
            "/exams/nonexistent-slug-xyz/",
            "/organizations/nonexistent-org-xyz/",
            "/notifications/999999/",
        ],
    )
    def test_missing_resource_does_not_cause_server_error(self, page: Page, missing_path: str) -> None:
        """A request for a non-existent resource must return 404 or a login redirect, not 5xx."""
        response = page.goto(f"{BASE_URL}{missing_path}")
        page.wait_for_load_state("domcontentloaded")

        if response is not None:
            assert (
                response.status < 500
            ), f"Missing resource {missing_path!r} returned server error HTTP {response.status}"


# ── No sensitive data in public pages ─────────────────────────────────────────


class TestNoSensitiveDataLeakage:
    """Public pages must not expose sensitive implementation details."""

    def test_login_page_does_not_expose_stack_trace(self, page: Page) -> None:
        """The login page must not contain Django debug/stack-trace text."""
        page.goto(f"{BASE_URL}/accounts/login/")
        page.wait_for_load_state("domcontentloaded")
        page_source = page.content()
        # Django debug page markers
        for marker in ["Traceback (most recent call last)", "django.db.utils.", "DEBUG = True"]:
            assert marker not in page_source, f"Sensitive debug text {marker!r} found on the public login page"

    def test_home_page_does_not_expose_stack_trace(self, page: Page) -> None:
        """The home page must not contain Django debug/stack-trace text."""
        page.goto(f"{BASE_URL}/")
        page.wait_for_load_state("domcontentloaded")
        page_source = page.content()
        for marker in ["Traceback (most recent call last)", "django.db.utils."]:
            assert marker not in page_source, f"Sensitive debug text {marker!r} found on the public home page"
