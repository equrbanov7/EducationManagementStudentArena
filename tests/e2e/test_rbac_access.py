"""
EMS Arena — Role-Based Access Control E2E Tests
================================================
Covers:
  B. Organization lifecycle access
  C. User and role management pages
  M. Security — direct URL access, unauthorized page access
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, E2E_PASSWORD, E2E_USERNAME

# ── URLs ─────────────────────────────────────────────────────────────────────

ORGANIZATION_SELECT_URL = f"{BASE_URL}/organizations/select/"
SUPERADMIN_ORGS_URL = f"{BASE_URL}/accounts/superadmin/organizations/"
ROLE_ASSIGNMENT_URL = f"{BASE_URL}/accounts/role-assignment/"
PERMISSION_EDITOR_URL = f"{BASE_URL}/accounts/permission-editor/"
MANAGE_ROLES_URL = f"{BASE_URL}/accounts/manage-roles/"
STUDENT_ORG_MGMT_URL = f"{BASE_URL}/accounts/student-organization-management/"
GRADING_QUEUE_URL = f"{BASE_URL}/accounts/grading-queue/"
REVIEW_RESULTS_URL = f"{BASE_URL}/accounts/review-results/"
MY_RESULTS_URL = f"{BASE_URL}/accounts/my-results/"
PENDING_REVIEW_URL = f"{BASE_URL}/accounts/pending-review/"

# Protected paths that any anonymous user must NOT be able to access.
PROTECTED_PATHS = [
    "/organizations/select/",
    "/accounts/superadmin/organizations/",
    "/accounts/role-assignment/",
    "/accounts/permission-editor/",
    "/accounts/manage-roles/",
    "/accounts/grading-queue/",
    "/accounts/review-results/",
    "/accounts/my-results/",
    "/accounts/pending-review/",
    "/accounts/assigned-exams/",
    "/accounts/assigned-courses/",
    "/courses/create_course/",
    "/courses/my-courses/",
    "/exams/",
    "/notifications/",
]


# ── Anonymous access guards ───────────────────────────────────────────────────


class TestAnonymousAccessBlocked:
    """
    Verify that every sensitive route redirects an unauthenticated user to login
    (or returns 403) and does not return a 5xx error.
    """

    @pytest.mark.parametrize("protected_path", PROTECTED_PATHS)
    def test_anonymous_access_does_not_return_5xx(self, page: Page, protected_path: str) -> None:
        """Anonymous access to a protected path must not produce a server error."""
        response = page.goto(f"{BASE_URL}{protected_path}")
        page.wait_for_load_state("domcontentloaded")

        if response is not None:
            assert (
                response.status < 500
            ), f"Protected path {protected_path!r} returned server error HTTP {response.status}"

    @pytest.mark.parametrize("protected_path", PROTECTED_PATHS)
    def test_anonymous_access_redirects_to_login_or_returns_403(self, page: Page, protected_path: str) -> None:
        """Anonymous access must redirect to login or return 403, not expose the content."""
        response = page.goto(f"{BASE_URL}{protected_path}")
        page.wait_for_load_state("domcontentloaded")

        status = response.status if response is not None else 0
        # 403 is an acceptable explicit denial; login redirect is also correct.
        is_login_redirect = "/accounts/login/" in page.url
        is_explicit_deny = status == 403

        assert is_login_redirect or is_explicit_deny, (
            f"Anonymous user accessed {protected_path!r} without redirect to login. "
            f"HTTP {status} — final URL: {page.url}"
        )


# ── Organization selection page ───────────────────────────────────────────────


class TestOrganizationSelectionPage:
    """Tests for the organization selection/switch UI."""

    @pytest.mark.skipif(
        not E2E_USERNAME or not E2E_PASSWORD,
        reason="E2E_USERNAME / E2E_PASSWORD not set",
    )
    def test_organization_select_page_loads(self, authenticated_page: Page) -> None:
        """Authenticated user must be able to load the organization selection page."""
        response = authenticated_page.goto(ORGANIZATION_SELECT_URL)
        assert response is not None
        assert response.status < 500, f"Organization select page returned HTTP {response.status}"
        authenticated_page.wait_for_load_state("domcontentloaded")
        # The page should render a body without crashing.
        expect(authenticated_page.locator("body")).to_be_visible()

    @pytest.mark.skipif(
        not E2E_USERNAME or not E2E_PASSWORD,
        reason="E2E_USERNAME / E2E_PASSWORD not set",
    )
    def test_organization_select_has_content(self, authenticated_page: Page) -> None:
        """Organization select page must show organization cards or an empty-state message."""
        authenticated_page.goto(ORGANIZATION_SELECT_URL)
        authenticated_page.wait_for_load_state("domcontentloaded")
        # Either organization cards or a "no organizations" message.
        has_org_card = authenticated_page.locator(".org-card, .organization-card").count() > 0
        has_body_text = len(authenticated_page.locator("body").inner_text()) > 0
        assert has_org_card or has_body_text, "Organization select page appears to be blank"


# ── Authenticated role-management pages ───────────────────────────────────────


class TestRoleManagementPages:
    """Tests that role-management pages load for an authorized user."""

    @pytest.mark.skipif(
        not E2E_USERNAME or not E2E_PASSWORD,
        reason="E2E_USERNAME / E2E_PASSWORD not set",
    )
    def test_role_assignment_page_loads(self, authenticated_page: Page) -> None:
        """Role-assignment page must load without a server error."""
        response = authenticated_page.goto(ROLE_ASSIGNMENT_URL)
        assert response is not None
        assert response.status < 500, f"Role assignment page returned HTTP {response.status}"

    @pytest.mark.skipif(
        not E2E_USERNAME or not E2E_PASSWORD,
        reason="E2E_USERNAME / E2E_PASSWORD not set",
    )
    def test_manage_roles_page_loads(self, authenticated_page: Page) -> None:
        """Manage-roles page must load without a server error."""
        response = authenticated_page.goto(MANAGE_ROLES_URL)
        assert response is not None
        assert response.status < 500, f"Manage roles page returned HTTP {response.status}"

    @pytest.mark.skipif(
        not E2E_USERNAME or not E2E_PASSWORD,
        reason="E2E_USERNAME / E2E_PASSWORD not set",
    )
    def test_permission_editor_page_loads(self, authenticated_page: Page) -> None:
        """Permission editor page must load without a server error."""
        response = authenticated_page.goto(PERMISSION_EDITOR_URL)
        assert response is not None
        assert response.status < 500, f"Permission editor page returned HTTP {response.status}"


# ── Superadmin oversight ──────────────────────────────────────────────────────


class TestSuperadminOrganizationsPage:
    """Tests for the superadmin organization oversight page."""

    @pytest.mark.skipif(
        not E2E_USERNAME or not E2E_PASSWORD,
        reason="E2E_USERNAME / E2E_PASSWORD not set",
    )
    def test_superadmin_orgs_page_does_not_crash(self, authenticated_page: Page) -> None:
        """
        The superadmin organizations page must not return a 5xx error.

        Note: the CI E2E user is an org-owner, not a Django superuser; a 403
        response is therefore acceptable and expected.
        """
        response = authenticated_page.goto(SUPERADMIN_ORGS_URL)
        assert response is not None
        assert response.status < 500, f"Superadmin org oversight page returned server error HTTP {response.status}"

    def test_superadmin_orgs_page_blocks_anonymous_user(self, page: Page) -> None:
        """Unauthenticated access to the superadmin oversight page must redirect to login."""
        response = page.goto(SUPERADMIN_ORGS_URL)
        page.wait_for_load_state("domcontentloaded")
        if response is not None:
            assert response.status < 500
        # Must redirect to login (or 403) — not expose the admin data.
        is_login_redirect = "/accounts/login/" in page.url
        is_explicit_deny = response is not None and response.status == 403
        assert is_login_redirect or is_explicit_deny, f"Superadmin page accessible to anonymous user: {page.url}"


# ── Dashboard access ──────────────────────────────────────────────────────────


class TestDashboardAccess:
    """Tests that authenticated users can reach their dashboard."""

    @pytest.mark.skipif(
        not E2E_USERNAME or not E2E_PASSWORD,
        reason="E2E_USERNAME / E2E_PASSWORD not set",
    )
    def test_dashboard_loads_after_login(self, authenticated_page: Page) -> None:
        """The main dashboard must load for an authenticated user."""
        response = authenticated_page.goto(f"{BASE_URL}/accounts/dashboard/")
        assert response is not None
        assert response.status == 200, f"Dashboard returned HTTP {response.status}"
        authenticated_page.wait_for_load_state("domcontentloaded")
        expect(authenticated_page.locator("main, .main-content, .student-dashboard").first).to_be_visible()

    @pytest.mark.skipif(
        not E2E_USERNAME or not E2E_PASSWORD,
        reason="E2E_USERNAME / E2E_PASSWORD not set",
    )
    def test_grading_queue_loads(self, authenticated_page: Page) -> None:
        """The grading queue page must load for an authorized teacher/staff user."""
        response = authenticated_page.goto(GRADING_QUEUE_URL)
        assert response is not None
        assert response.status < 500, f"Grading queue page returned HTTP {response.status}"

    @pytest.mark.skipif(
        not E2E_USERNAME or not E2E_PASSWORD,
        reason="E2E_USERNAME / E2E_PASSWORD not set",
    )
    def test_my_results_page_loads(self, authenticated_page: Page) -> None:
        """The my-results page must load for an authenticated student/user."""
        response = authenticated_page.goto(MY_RESULTS_URL)
        assert response is not None
        assert response.status < 500, f"My results page returned HTTP {response.status}"

    @pytest.mark.skipif(
        not E2E_USERNAME or not E2E_PASSWORD,
        reason="E2E_USERNAME / E2E_PASSWORD not set",
    )
    def test_student_organization_management_loads(self, authenticated_page: Page) -> None:
        """Student organization management page must load without a server error."""
        response = authenticated_page.goto(STUDENT_ORG_MGMT_URL)
        assert response is not None
        assert response.status < 500, f"Student org management page returned HTTP {response.status}"

    @pytest.mark.skipif(
        not E2E_USERNAME or not E2E_PASSWORD,
        reason="E2E_USERNAME / E2E_PASSWORD not set",
    )
    def test_pending_review_page_loads(self, authenticated_page: Page) -> None:
        """Pending-review page must load without a server error."""
        response = authenticated_page.goto(PENDING_REVIEW_URL)
        assert response is not None
        assert response.status < 500, f"Pending review page returned HTTP {response.status}"

    @pytest.mark.skipif(
        not E2E_USERNAME or not E2E_PASSWORD,
        reason="E2E_USERNAME / E2E_PASSWORD not set",
    )
    def test_review_results_page_loads(self, authenticated_page: Page) -> None:
        """Review-results page must load without a server error."""
        response = authenticated_page.goto(REVIEW_RESULTS_URL)
        assert response is not None
        assert response.status < 500, f"Review results page returned HTTP {response.status}"
