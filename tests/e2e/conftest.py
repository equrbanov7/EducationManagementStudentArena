"""
EMS Arena — Shared E2E Fixtures & Helpers
==========================================
This conftest.py is shared across all E2E test modules in this directory.

Environment variables used:
  BASE_URL        – Root URL of the running EMS Arena instance (default: http://localhost)
  E2E_USERNAME    – Username for authenticated test flows
  E2E_PASSWORD    – Password for authenticated test flows

``require_reachable_base_url`` is an autouse fixture that skips every test in
this directory when BASE_URL is not reachable, so the E2E suite degrades
gracefully on developer machines that have not started the app.
"""

from __future__ import annotations

import os
import socket
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Page

# ── Configuration ─────────────────────────────────────────────────────────────
BASE_URL: str = os.environ.get("BASE_URL", "http://localhost").rstrip("/")
E2E_USERNAME: str = os.environ.get("E2E_USERNAME", "")
E2E_PASSWORD: str = os.environ.get("E2E_PASSWORD", "")


# ── Internal helpers ──────────────────────────────────────────────────────────


def _base_url_is_reachable() -> bool:
    """Return True if BASE_URL's host:port accepts a TCP connection."""
    parsed = urlsplit(BASE_URL)
    host = parsed.hostname or "localhost"
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def login(page: Page) -> None:
    """
    Navigate to the login page and submit the credentials from the environment.

    If ``E2E_USERNAME`` or ``E2E_PASSWORD`` are not set the function returns
    without filling the form, leaving the page at the login URL.
    """
    page.goto(f"{BASE_URL}/accounts/login/")
    page.wait_for_load_state("networkidle")

    if not E2E_USERNAME or not E2E_PASSWORD:
        return

    # Scope all actions to the real login form; the page also contains hidden
    # language-switcher submit buttons.
    login_form = (
        page.locator("form")
        .filter(has=page.locator("input[name='username']"))
        .filter(has=page.locator("input[name='password']"))
    )

    login_form.locator("input[name='username']").fill(E2E_USERNAME)
    login_form.locator("input[name='password']").fill(E2E_PASSWORD)
    login_form.locator("button[type='submit']").click()
    page.wait_for_load_state("networkidle")


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def require_reachable_base_url() -> None:  # type: ignore[return]
    """
    Skip every test in the E2E suite when BASE_URL is not reachable.

    This prevents meaningless failures on CI runners that did not start the
    application stack, and on developer machines that have not booted the app.
    """
    if not _base_url_is_reachable():
        pytest.skip(f"BASE_URL is not reachable — skipping E2E tests: {BASE_URL}")


@pytest.fixture
def authenticated_page(page: Page) -> Page:
    """
    Return a Playwright Page that is already logged in as ``E2E_USERNAME``.

    Tests that depend on this fixture are automatically skipped when credentials
    are not configured.
    """
    if not E2E_USERNAME or not E2E_PASSWORD:
        pytest.skip("E2E_USERNAME / E2E_PASSWORD not set — skipping authenticated test")

    login(page)

    # Verify that the login actually succeeded before handing the page to the test.
    if "/accounts/login/" in page.url:
        pytest.fail(
            f"Login failed for user '{E2E_USERNAME}': still on login page after submit. "
            "Check that the credentials are correct and the user is active."
        )

    return page
