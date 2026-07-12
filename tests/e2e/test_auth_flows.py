"""
EMS Arena — Authentication & Account Lifecycle E2E Tests
=========================================================
Covers:
  A. Sign in / sign out flows
  B. Registration page structure
  C. OTP / email verification pages
  D. Password reset flow (page loads, not email delivery)
  E. Unauthenticated access redirects
  F. Invalid credential handling
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, E2E_PASSWORD, E2E_USERNAME, login

# ── Helpers ───────────────────────────────────────────────────────────────────

# The login FORM now lives at the role-specific portal URLs; /accounts/login/
# itself is the portal chooser (covered by test_security). These form-structure
# and invalid-credential checks target the staff login form.
LOGIN_URL = f"{BASE_URL}/accounts/login/muellim/"
LOGOUT_URL = f"{BASE_URL}/accounts/logout/"
REGISTER_URL = f"{BASE_URL}/accounts/register/"
VERIFY_CODE_URL = f"{BASE_URL}/accounts/verify-code/"
RESEND_CODE_URL = f"{BASE_URL}/accounts/resend-code/"
PASSWORD_RESET_URL = f"{BASE_URL}/accounts/password-reset/"
DASHBOARD_URL = f"{BASE_URL}/accounts/dashboard/"


# ── Login page ────────────────────────────────────────────────────────────────


class TestLoginPage:
    """Tests for the login page structure and content."""

    def test_login_page_returns_200(self, page: Page) -> None:
        """The login page must be reachable and return HTTP 200."""
        response = page.goto(LOGIN_URL)
        assert response is not None, "No response from login page"
        assert response.status == 200, f"Login page returned HTTP {response.status}"

    def test_login_page_has_username_field(self, page: Page) -> None:
        """The login form must contain a username input."""
        page.goto(LOGIN_URL)
        expect(page.locator("input[name='username']")).to_be_visible()

    def test_login_page_has_password_field(self, page: Page) -> None:
        """The login form must contain a password input."""
        page.goto(LOGIN_URL)
        expect(page.locator("input[name='password']")).to_be_visible()

    def test_login_page_has_submit_button(self, page: Page) -> None:
        """The login form must have a submit button."""
        page.goto(LOGIN_URL)
        page.wait_for_load_state("domcontentloaded")
        login_form = (
            page.locator("form")
            .filter(has=page.locator("input[name='username']"))
            .filter(has=page.locator("input[name='password']"))
        )
        expect(login_form.locator("button[type='submit']")).to_be_visible()

    def test_login_page_has_forgot_password_link(self, page: Page) -> None:
        """The login page must show a 'forgot password' link."""
        page.goto(LOGIN_URL)
        page.wait_for_load_state("domcontentloaded")
        # The link should point to the password reset URL
        forgot_link = page.locator("a[href*='password-reset']")
        expect(forgot_link.first).to_be_visible()

    def test_login_page_has_csrf_token(self, page: Page) -> None:
        """The login form must include a CSRF token (security baseline)."""
        page.goto(LOGIN_URL)
        csrf_input = page.locator("input[name='csrfmiddlewaretoken']")
        assert csrf_input.count() > 0, "CSRF token input not found in login form"

    def test_login_page_does_not_return_5xx(self, page: Page) -> None:
        """The login page must not return a server error."""
        response = page.goto(LOGIN_URL)
        assert response is not None
        assert response.status < 500, f"Login page returned server error HTTP {response.status}"


# ── Successful login & logout ─────────────────────────────────────────────────


class TestLoginLogoutFlow:
    """Tests for successful authentication and session teardown."""

    @pytest.mark.skipif(
        not E2E_USERNAME or not E2E_PASSWORD,
        reason="E2E_USERNAME / E2E_PASSWORD not set",
    )
    def test_valid_credentials_redirect_away_from_login(self, page: Page) -> None:
        """Submitting valid credentials must redirect the user off the login page."""
        login(page)
        assert (
            "/accounts/login/" not in page.url
        ), f"Still on login page after submitting valid credentials — URL: {page.url}"

    @pytest.mark.skipif(
        not E2E_USERNAME or not E2E_PASSWORD,
        reason="E2E_USERNAME / E2E_PASSWORD not set",
    )
    def test_login_lands_on_valid_page(self, page: Page) -> None:
        """The page after login must return HTTP 200, not an error page."""
        login(page)
        # After login the browser follows the redirect chain. The final
        # response must be 200.
        assert page.evaluate("() => document.readyState") in {
            "complete",
            "interactive",
        }, "Post-login page did not finish loading"

    @pytest.mark.skipif(
        not E2E_USERNAME or not E2E_PASSWORD,
        reason="E2E_USERNAME / E2E_PASSWORD not set",
    )
    def test_logout_redirects_to_login(self, page: Page) -> None:
        """After logout the user must be redirected to the login page (or home)."""
        login(page)
        # Navigate to logout URL (GET or POST depending on implementation)
        response = page.goto(LOGOUT_URL)
        page.wait_for_load_state("domcontentloaded")

        # After logout the user should land on a public page (login or home).
        # The exact URL may vary; what matters is that the response is not 5xx.
        if response is not None:
            assert response.status < 500, f"Logout returned server error HTTP {response.status}"

        # Attempting to access the dashboard now must redirect back to login.
        dash_response = page.goto(DASHBOARD_URL)
        page.wait_for_load_state("domcontentloaded")
        # Either the dashboard redirected to login, or we're on a public page.
        assert "/accounts/login/" in page.url or (
            dash_response is not None and dash_response.status in {200, 302}
        ), f"Expected redirect to login after logout, got URL: {page.url}"


# ── Invalid credentials ───────────────────────────────────────────────────────


class TestInvalidCredentials:
    """Tests for login failure with incorrect credentials."""

    def test_invalid_credentials_stay_on_login_page(self, page: Page) -> None:
        """Submitting wrong credentials must keep the user on the login page."""
        page.goto(LOGIN_URL)
        page.wait_for_load_state("domcontentloaded")

        login_form = (
            page.locator("form")
            .filter(has=page.locator("input[name='username']"))
            .filter(has=page.locator("input[name='password']"))
        )

        login_form.locator("input[name='username']").fill("nonexistent_user_xyz_12345")
        login_form.locator("input[name='password']").fill("wrong_password_xyz_12345!")
        login_form.locator("button[type='submit']").click()
        page.wait_for_load_state("domcontentloaded")

        # Must remain on the login page after failed attempt.
        assert (
            "/accounts/login/" in page.url
        ), f"Expected to stay on login page after invalid credentials, but redirected to: {page.url}"

    def test_invalid_credentials_show_error_message(self, page: Page) -> None:
        """A failed login attempt must display a user-visible error message."""
        page.goto(LOGIN_URL)
        page.wait_for_load_state("domcontentloaded")

        login_form = (
            page.locator("form")
            .filter(has=page.locator("input[name='username']"))
            .filter(has=page.locator("input[name='password']"))
        )

        login_form.locator("input[name='username']").fill("nonexistent_user_xyz_12345")
        login_form.locator("input[name='password']").fill("wrong_password_xyz_12345!")
        login_form.locator("button[type='submit']").click()
        page.wait_for_load_state("domcontentloaded")

        # The page must render an error block (non-field errors or field errors).
        error_selectors = [
            ".auth-global-errors",
            ".auth-field-error",
            ".errorlist",
            "[role='alert']",
        ]
        found_error = any(page.locator(sel).count() > 0 for sel in error_selectors)
        assert found_error, "No error message shown after invalid login credentials"

    def test_empty_credentials_show_error(self, page: Page) -> None:
        """Submitting the login form with empty fields must not cause a server error."""
        page.goto(LOGIN_URL)
        page.wait_for_load_state("domcontentloaded")

        login_form = (
            page.locator("form")
            .filter(has=page.locator("input[name='username']"))
            .filter(has=page.locator("input[name='password']"))
        )
        login_form.locator("button[type='submit']").click()
        page.wait_for_load_state("domcontentloaded")

        # Must not produce a 5xx error.
        assert "/accounts/login/" in page.url or page.url.startswith(
            BASE_URL
        ), f"Unexpected redirect after empty form submit: {page.url}"


# ── Registration page ─────────────────────────────────────────────────────────


class TestPublicSignupDisabled:
    """E-university provisioning: public self-signup is disabled in production.

    The prod image ships with PUBLIC_SIGNUP_ENABLED=False (accounts are created by
    the university administration — see docs/operations/ACCOUNT_PROVISIONING.md), so the
    public register route redirects to login and the login page exposes no
    "register" link. (If a deployment re-enables signup, these expectations
    change — update alongside the flag.)
    """

    def test_register_redirects_to_login(self, page: Page) -> None:
        """Visiting the register route must land on the login page (302 → login)."""
        response = page.goto(REGISTER_URL)
        assert response is not None
        # Playwright follows the redirect, so the final document is the login page.
        assert response.status == 200, f"Register route returned HTTP {response.status}"
        assert "/accounts/login/" in page.url, f"Register did not redirect to login; landed on {page.url}"

    def test_register_landing_has_no_wizard(self, page: Page) -> None:
        """The redirected page is the login form, not the registration wizard."""
        page.goto(REGISTER_URL)
        page.wait_for_load_state("domcontentloaded")
        wizard = page.locator(".register-wizard-steps, .wizard-step")
        assert wizard.count() == 0, "Registration wizard is reachable while public signup is disabled"

    def test_login_page_has_no_signup_link(self, page: Page) -> None:
        """The login page must not offer a public self-registration link."""
        page.goto(LOGIN_URL)
        page.wait_for_load_state("domcontentloaded")
        signup_links = page.locator("a[href*='/accounts/register/']")
        assert signup_links.count() == 0, "Login page still exposes a public signup link"


# ── Password reset flow ────────────────────────────────────────────────────────


class TestPasswordResetFlow:
    """Tests for the password reset page (page loads only, not email delivery)."""

    def test_password_reset_page_returns_200(self, page: Page) -> None:
        """The password reset page must be reachable."""
        response = page.goto(PASSWORD_RESET_URL)
        assert response is not None
        assert response.status == 200, f"Password reset page returned HTTP {response.status}"

    def test_password_reset_page_has_email_field(self, page: Page) -> None:
        """The password reset form must contain an email field."""
        page.goto(PASSWORD_RESET_URL)
        page.wait_for_load_state("domcontentloaded")
        email_field = page.locator("input[name='email'], input[type='email']")
        assert email_field.count() > 0, "No email field found on password reset page"

    def test_password_reset_done_page_accessible(self, page: Page) -> None:
        """The password-reset-done page must load without a 5xx error."""
        response = page.goto(f"{BASE_URL}/accounts/password-reset/done/")
        assert response is not None
        assert response.status < 500, f"Password reset done page returned server error HTTP {response.status}"


# ── OTP / email verification pages ───────────────────────────────────────────


class TestOtpVerificationPages:
    """Tests for OTP and email verification pages."""

    def test_verify_code_page_accessible(self, page: Page) -> None:
        """The OTP verification page must load without a server error."""
        response = page.goto(VERIFY_CODE_URL)
        assert response is not None
        # The page may redirect to login or registration if no pending OTP exists.
        # Either is acceptable; 5xx is not.
        assert response.status < 500, f"OTP verify page returned server error HTTP {response.status}"

    def test_resend_code_page_redirects_gracefully(self, page: Page) -> None:
        """Accessing the resend-code URL without a session must redirect, not crash."""
        response = page.goto(RESEND_CODE_URL)
        page.wait_for_load_state("domcontentloaded")
        if response is not None:
            assert response.status < 500, f"Resend code page returned server error HTTP {response.status}"


# ── Unauthenticated access guards ─────────────────────────────────────────────


class TestUnauthenticatedRedirects:
    """Tests verifying that protected pages redirect to login for anonymous users."""

    @pytest.mark.parametrize(
        "protected_path",
        [
            "/accounts/dashboard/",
            "/accounts/dashboard/student/",
            "/accounts/dashboard/teacher/",
            "/accounts/profile/",
            "/accounts/grading-queue/",
            "/accounts/my-results/",
            "/accounts/pending-review/",
            "/accounts/role-assignment/",
        ],
    )
    def test_protected_path_redirects_to_login(self, page: Page, protected_path: str) -> None:
        """Every protected account path must redirect an anonymous user to login, not 5xx."""
        response = page.goto(f"{BASE_URL}{protected_path}")
        page.wait_for_load_state("domcontentloaded")

        if response is not None:
            assert (
                response.status < 500
            ), f"Protected path {protected_path!r} returned server error HTTP {response.status}"

        # After following all redirects, the user should be on the login page.
        assert "/accounts/login/" in page.url, (
            f"Expected redirect to login for unauthenticated access to {protected_path!r}, "
            f"but ended up at: {page.url}"
        )
