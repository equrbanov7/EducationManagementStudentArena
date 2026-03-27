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
from dataclasses import dataclass
from typing import Iterator
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Browser, Page

# ── Configuration ─────────────────────────────────────────────────────────────
BASE_URL: str = os.environ.get("BASE_URL", "http://localhost").rstrip("/")
E2E_USERNAME: str = os.environ.get("E2E_USERNAME", "")
E2E_PASSWORD: str = os.environ.get("E2E_PASSWORD", "")
E2E_ROLE_PASSWORD: str = os.environ.get("E2E_ROLE_PASSWORD", "")

E2E_ORG_SLUG: str = os.environ.get("E2E_ORG_SLUG", "ci-role-matrix-university").strip()
E2E_ISOLATED_ORG_SLUG: str = os.environ.get("E2E_ISOLATED_ORG_SLUG", "ci-isolated-university").strip()
E2E_PENDING_ORG_SLUG: str = os.environ.get("E2E_PENDING_ORG_SLUG", "ci-pending-university").strip()

E2E_SCENARIO_COURSE_TITLE: str = os.environ.get("E2E_SCENARIO_COURSE_TITLE", "CI Role Matrix Course").strip()
E2E_SCENARIO_ASSIGNMENT_TITLE: str = os.environ.get(
    "E2E_SCENARIO_ASSIGNMENT_TITLE",
    "CI Assignment",
).strip()
E2E_SCENARIO_EXAM_TITLE: str = os.environ.get("E2E_SCENARIO_EXAM_TITLE", "CI Exam").strip()
E2E_SCENARIO_EXAM_SLUG: str = os.environ.get("E2E_SCENARIO_EXAM_SLUG", "ci-role-matrix-exam").strip()
E2E_RESUME_EXAM_SLUG: str = os.environ.get("E2E_RESUME_EXAM_SLUG", "ci-resume-exam").strip()
E2E_ISOLATED_EXAM_SLUG: str = os.environ.get("E2E_ISOLATED_EXAM_SLUG", "ci-isolated-exam").strip()

ROLE_ENV_PREFIXES = {
    "owner": "E2E_OWNER",
    "org_admin": "E2E_ORG_ADMIN",
    "teacher": "E2E_TEACHER",
    "staff": "E2E_STAFF",
    "student": "E2E_STUDENT",
    "late_student": "E2E_LATE_STUDENT",
    "resume_student": "E2E_RESUME_STUDENT",
    "pending_owner": "E2E_PENDING_OWNER",
}

ROLE_DEFAULT_USERNAMES = {
    "owner": "ci_owner_e2e",
    "org_admin": "ci_admin_e2e",
    "teacher": "ci_teacher_e2e",
    "staff": "ci_staff_e2e",
    "student": "ci_student_e2e",
    "late_student": "ci_late_student_e2e",
    "resume_student": "ci_resume_student_e2e",
    "pending_owner": "ci_pending_owner_e2e",
}

ROLE_DEFAULT_ORGANIZATIONS = {
    "owner": E2E_ORG_SLUG,
    "org_admin": E2E_ORG_SLUG,
    "teacher": E2E_ORG_SLUG,
    "staff": E2E_ORG_SLUG,
    "student": E2E_ORG_SLUG,
    "late_student": E2E_ORG_SLUG,
    "resume_student": E2E_ORG_SLUG,
    "pending_owner": "",
}


@dataclass(frozen=True)
class E2EAccount:
    role: str
    username: str
    password: str
    organization_slug: str = ""


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


def build_url(path: str) -> str:
    """Build an absolute application URL from a relative path."""
    if path.startswith(("http://", "https://")):
        return path
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{BASE_URL}{path}"


def _role_account(role: str) -> E2EAccount:
    """Resolve role credentials from environment with stable CI defaults."""
    prefix = ROLE_ENV_PREFIXES[role]
    username = os.environ.get(f"{prefix}_USERNAME", ROLE_DEFAULT_USERNAMES[role]).strip()
    password = (os.environ.get(f"{prefix}_PASSWORD", "") or E2E_ROLE_PASSWORD).strip()
    organization_slug = os.environ.get(f"{prefix}_ORG_SLUG", ROLE_DEFAULT_ORGANIZATIONS[role]).strip()
    return E2EAccount(role=role, username=username, password=password, organization_slug=organization_slug)


def require_role_account(role: str) -> E2EAccount:
    """Return role credentials or skip when they are not configured."""
    account = _role_account(role)
    if not account.username or not account.password:
        pytest.skip(
            f"{ROLE_ENV_PREFIXES[role]}_USERNAME / _PASSWORD (or E2E_ROLE_PASSWORD) not set "
            f"— skipping {role} role test"
        )
    return account


def login(page: Page, username: str | None = None, password: str | None = None) -> None:
    """
    Navigate to the login page and submit the credentials from the environment.

    If ``E2E_USERNAME`` or ``E2E_PASSWORD`` are not set the function returns
    without filling the form, leaving the page at the login URL.
    """
    username = username or E2E_USERNAME
    password = password or E2E_PASSWORD

    page.goto(build_url("/accounts/login/"))
    page.wait_for_load_state("networkidle")

    if not username or not password:
        return

    # Scope all actions to the real login form; the page also contains hidden
    # language-switcher submit buttons.
    login_form = (
        page.locator("form")
        .filter(has=page.locator("input[name='username']"))
        .filter(has=page.locator("input[name='password']"))
    )

    login_form.locator("input[name='username']").fill(username)
    login_form.locator("input[name='password']").fill(password)
    login_form.locator("button[type='submit']").click()
    page.wait_for_load_state("networkidle")


def logout(page: Page) -> None:
    """Log out the current browser page session."""
    page.goto(build_url("/accounts/logout/"))
    page.wait_for_load_state("networkidle")


def select_organization(page: Page, organization_slug: str = E2E_ORG_SLUG) -> None:
    """Switch the active tenant context to the requested organization."""
    if not organization_slug:
        return

    response = page.goto(build_url(f"/organizations/switch/{organization_slug}/"))
    page.wait_for_load_state("networkidle")

    if response is not None and response.status >= 500:
        pytest.fail(f"Organization switch for '{organization_slug}' returned HTTP {response.status}")

    if "/accounts/login/" in page.url:
        pytest.fail(
            f"Organization switch for '{organization_slug}' redirected back to login. "
            "Check that the role user exists and belongs to the organization."
        )


def login_as_role(page: Page, role: str) -> E2EAccount:
    """Authenticate the page as a configured role user and switch organization when needed."""
    account = require_role_account(role)
    login(page, account.username, account.password)

    if "/accounts/login/" in page.url:
        pytest.fail(
            f"Login failed for role '{role}' with user '{account.username}': "
            "still on login page after submit. Check that the scenario seed command has run."
        )

    if account.organization_slug:
        select_organization(page, account.organization_slug)

    return account


def _role_page(browser: Browser, role: str) -> Iterator[Page]:
    account = require_role_account(role)
    page = browser.new_page()
    try:
        login(page, account.username, account.password)

        if "/accounts/login/" in page.url:
            pytest.fail(
                f"Login failed for role '{role}' with user '{account.username}': "
                "still on login page after submit. Check that the scenario seed command has run."
            )

        if account.organization_slug:
            select_organization(page, account.organization_slug)

        yield page
    finally:
        page.close()


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


@pytest.fixture(scope="session")
def base_url() -> str:
    """Expose the configured base URL as a fixture for new tests."""
    return BASE_URL


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


@pytest.fixture
def owner_page(browser: Browser) -> Iterator[Page]:
    """Return a page authenticated as the seeded organization owner."""
    yield from _role_page(browser, "owner")


@pytest.fixture
def org_admin_page(browser: Browser) -> Iterator[Page]:
    """Return a page authenticated as the seeded organization admin."""
    yield from _role_page(browser, "org_admin")


@pytest.fixture
def teacher_page(browser: Browser) -> Iterator[Page]:
    """Return a page authenticated as the seeded teacher."""
    yield from _role_page(browser, "teacher")


@pytest.fixture
def staff_page(browser: Browser) -> Iterator[Page]:
    """Return a page authenticated as the seeded staff user."""
    yield from _role_page(browser, "staff")


@pytest.fixture
def student_page(browser: Browser) -> Iterator[Page]:
    """Return a page authenticated as the seeded primary student."""
    yield from _role_page(browser, "student")


@pytest.fixture
def late_student_page(browser: Browser) -> Iterator[Page]:
    """Return a page authenticated as the seeded late-joiner student."""
    yield from _role_page(browser, "late_student")


@pytest.fixture
def resume_student_page(browser: Browser) -> Iterator[Page]:
    """Return a page authenticated as the seeded resume-attempt student."""
    yield from _role_page(browser, "resume_student")


@pytest.fixture
def pending_owner_page(browser: Browser) -> Iterator[Page]:
    """Return a page authenticated as the seeded pending-organization owner."""
    yield from _role_page(browser, "pending_owner")
