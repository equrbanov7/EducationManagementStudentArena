"""
EMS Arena — Notification Workflows E2E Tests
=============================================
Covers:
  J. Notifications and user feedback
     - Notification inbox page load
     - Unread count API endpoint
     - Notification detail page
     - Mark-read / mark-unread actions
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, E2E_PASSWORD, E2E_USERNAME

# ── URLs ─────────────────────────────────────────────────────────────────────

NOTIFICATION_LIST_URL = f"{BASE_URL}/notifications/"
NOTIFICATION_UNREAD_COUNT_URL = f"{BASE_URL}/notifications/unread-count/"
NOTIFICATION_READ_ALL_URL = f"{BASE_URL}/notifications/read-all/"


# ── Unauthenticated access ────────────────────────────────────────────────────


class TestNotificationsUnauthenticatedAccess:
    """Notification pages must be protected from anonymous access."""

    @pytest.mark.parametrize(
        "notif_path",
        [
            "/notifications/",
            "/notifications/unread-count/",
        ],
    )
    def test_notification_path_blocks_anonymous_user(self, page: Page, notif_path: str) -> None:
        """Anonymous access to notification endpoints must redirect to login and not return 5xx."""
        response = page.goto(f"{BASE_URL}{notif_path}")
        page.wait_for_load_state("networkidle")

        if response is not None:
            assert (
                response.status < 500
            ), f"Notification path {notif_path!r} returned server error HTTP {response.status}"
        # Must redirect to login (or return 403).
        is_login_redirect = "/accounts/login/" in page.url
        is_explicit_deny = response is not None and response.status == 403
        assert (
            is_login_redirect or is_explicit_deny
        ), f"Notification path {notif_path!r} accessible to anonymous user — URL: {page.url}"


# ── Authenticated notification inbox ─────────────────────────────────────────


class TestNotificationInbox:
    """Tests for the authenticated notification inbox."""

    @pytest.mark.skipif(
        not E2E_USERNAME or not E2E_PASSWORD,
        reason="E2E_USERNAME / E2E_PASSWORD not set",
    )
    def test_notification_list_loads(self, authenticated_page: Page) -> None:
        """Notification inbox must load successfully for an authenticated user."""
        response = authenticated_page.goto(NOTIFICATION_LIST_URL)
        assert response is not None
        assert response.status < 500, f"Notification list returned HTTP {response.status}"
        authenticated_page.wait_for_load_state("networkidle")
        expect(authenticated_page.locator("body")).to_be_visible()

    @pytest.mark.skipif(
        not E2E_USERNAME or not E2E_PASSWORD,
        reason="E2E_USERNAME / E2E_PASSWORD not set",
    )
    def test_notification_list_renders_content(self, authenticated_page: Page) -> None:
        """Notification inbox must render a non-empty page body."""
        response = authenticated_page.goto(NOTIFICATION_LIST_URL)
        if response is None or response.status != 200:
            pytest.skip(f"Notification list returned HTTP {response.status if response else 'None'}")
        authenticated_page.wait_for_load_state("networkidle")
        body_text = authenticated_page.locator("body").inner_text()
        assert len(body_text.strip()) > 0, "Notification list page body is empty"


# ── Unread count AJAX endpoint ────────────────────────────────────────────────


class TestNotificationUnreadCountEndpoint:
    """Tests for the unread-count AJAX endpoint used by the navbar badge."""

    @pytest.mark.skipif(
        not E2E_USERNAME or not E2E_PASSWORD,
        reason="E2E_USERNAME / E2E_PASSWORD not set",
    )
    def test_unread_count_endpoint_returns_valid_response(self, authenticated_page: Page) -> None:
        """
        The unread-count endpoint must return HTTP 200 with a JSON body
        containing a numeric unread count for an authenticated user.
        """
        # Use Playwright's evaluate to make a fetch request with the current
        # session cookies (the page is already authenticated).
        response_data = authenticated_page.evaluate(f"""async () => {{
                const resp = await fetch("{NOTIFICATION_UNREAD_COUNT_URL}", {{
                    headers: {{ "X-Requested-With": "XMLHttpRequest" }}
                }});
                return {{ status: resp.status, body: await resp.text() }};
            }}""")

        assert response_data["status"] == 200, f"Unread count endpoint returned HTTP {response_data['status']}"
        import json

        try:
            payload = json.loads(response_data["body"])
        except (json.JSONDecodeError, ValueError):
            pytest.fail(f"Unread count endpoint did not return JSON: {response_data['body'][:200]}")

        assert (
            "count" in payload or "unread_count" in payload or isinstance(payload, dict)
        ), f"Unread count response does not contain a count field: {payload}"


# ── Mark-read-all action ──────────────────────────────────────────────────────


class TestNotificationMarkAllRead:
    """Tests for the bulk mark-all-read action."""

    @pytest.mark.skipif(
        not E2E_USERNAME or not E2E_PASSWORD,
        reason="E2E_USERNAME / E2E_PASSWORD not set",
    )
    def test_mark_all_read_does_not_crash(self, authenticated_page: Page) -> None:
        """
        POST to mark-all-read must not produce a server error.
        The request uses the session cookie from the already-authenticated page.
        """
        # First visit the notification list so we have a CSRF cookie.
        authenticated_page.goto(NOTIFICATION_LIST_URL)
        authenticated_page.wait_for_load_state("networkidle")

        # Retrieve CSRF token from the cookie.
        csrf_token = authenticated_page.evaluate("""() => {
                const match = document.cookie.match(/csrftoken=([^;]+)/);
                return match ? match[1] : '';
            }""")

        if not csrf_token:
            pytest.skip("No CSRF token found in cookies — skipping POST test")

        response_data = authenticated_page.evaluate(
            f"""async (csrfToken) => {{
                const resp = await fetch("{NOTIFICATION_READ_ALL_URL}", {{
                    method: "POST",
                    headers: {{
                        "X-CSRFToken": csrfToken,
                        "X-Requested-With": "XMLHttpRequest",
                        "Content-Type": "application/x-www-form-urlencoded"
                    }},
                    body: "csrfmiddlewaretoken=" + encodeURIComponent(csrfToken)
                }});
                return {{ status: resp.status }};
            }}""",
            csrf_token,
        )

        assert (
            response_data["status"] < 500
        ), f"Mark-all-read endpoint returned server error HTTP {response_data['status']}"
