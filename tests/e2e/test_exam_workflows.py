"""
EMS Arena — Exam Workflows E2E Tests
=====================================
Covers:
  G. Exam system (teacher and student perspectives)
  K. Live exam / real-time features (page accessibility)
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, E2E_PASSWORD, E2E_USERNAME

# ── URLs ─────────────────────────────────────────────────────────────────────

TEACHER_EXAM_LIST_URL = f"{BASE_URL}/exams/"
STUDENT_EXAM_LIST_URL = f"{BASE_URL}/exams/available/"
ASSIGNED_EXAM_LIST_URL = f"{BASE_URL}/exams/assigned/"
EXAM_HISTORY_URL = f"{BASE_URL}/exams/my-history/"
CREATE_EXAM_URL = f"{BASE_URL}/exams/create/"
PENDING_WORK_URL = f"{BASE_URL}/exams/pending-work/"
LIVE_PIN_ENTRY_URL = f"{BASE_URL}/live/"

# Paths that must redirect an anonymous user to login.
EXAM_PROTECTED_PATHS = [
    "/exams/",
    "/exams/available/",
    "/exams/assigned/",
    "/exams/my-history/",
    "/exams/create/",
    "/exams/pending-work/",
]


# ── Unauthenticated access guards ─────────────────────────────────────────────


class TestExamUnauthenticatedAccess:
    """All exam management pages must redirect anonymous users to login."""

    @pytest.mark.parametrize("exam_path", EXAM_PROTECTED_PATHS)
    def test_exam_path_blocks_anonymous_user(self, page: Page, exam_path: str) -> None:
        """Anonymous access to an exam path must redirect to login and not return 5xx."""
        response = page.goto(f"{BASE_URL}{exam_path}")
        page.wait_for_load_state("domcontentloaded")

        if response is not None:
            assert response.status < 500, f"Exam path {exam_path!r} returned server error HTTP {response.status}"
        assert (
            "/accounts/login/" in page.url
        ), f"Exam path {exam_path!r} did not redirect anonymous user to login — URL: {page.url}"


# ── Teacher exam management ───────────────────────────────────────────────────


class TestTeacherExamPages:
    """Tests for exam management pages accessible to a teacher/rector."""

    @pytest.mark.skipif(
        not E2E_USERNAME or not E2E_PASSWORD,
        reason="E2E_USERNAME / E2E_PASSWORD not set",
    )
    def test_teacher_exam_list_loads(self, authenticated_page: Page) -> None:
        """Teacher exam list must load without a server error."""
        response = authenticated_page.goto(TEACHER_EXAM_LIST_URL)
        assert response is not None
        assert response.status < 500, f"Teacher exam list returned HTTP {response.status}"
        authenticated_page.wait_for_load_state("domcontentloaded")
        expect(authenticated_page.locator("body")).to_be_visible()

    @pytest.mark.skipif(
        not E2E_USERNAME or not E2E_PASSWORD,
        reason="E2E_USERNAME / E2E_PASSWORD not set",
    )
    def test_create_exam_page_loads(self, authenticated_page: Page) -> None:
        """Exam creation page must load without a server error."""
        response = authenticated_page.goto(CREATE_EXAM_URL)
        assert response is not None
        assert response.status < 500, f"Create exam page returned HTTP {response.status}"
        authenticated_page.wait_for_load_state("domcontentloaded")
        expect(authenticated_page.locator("body")).to_be_visible()

    @pytest.mark.skipif(
        not E2E_USERNAME or not E2E_PASSWORD,
        reason="E2E_USERNAME / E2E_PASSWORD not set",
    )
    def test_create_exam_page_has_form(self, authenticated_page: Page) -> None:
        """Create exam page must render a form when the user is authorized."""
        response = authenticated_page.goto(CREATE_EXAM_URL)
        assert response is not None
        if response.status == 200:
            authenticated_page.wait_for_load_state("domcontentloaded")
            form = authenticated_page.locator("form")
            assert form.count() > 0, "No form found on the create exam page"

    @pytest.mark.skipif(
        not E2E_USERNAME or not E2E_PASSWORD,
        reason="E2E_USERNAME / E2E_PASSWORD not set",
    )
    def test_pending_work_page_loads(self, authenticated_page: Page) -> None:
        """Pending work (attempts awaiting grading) page must load for a teacher."""
        response = authenticated_page.goto(PENDING_WORK_URL)
        assert response is not None
        assert response.status < 500, f"Pending work page returned HTTP {response.status}"


# ── Student exam pages ────────────────────────────────────────────────────────


class TestStudentExamPages:
    """Tests for exam pages accessible to students."""

    @pytest.mark.skipif(
        not E2E_USERNAME or not E2E_PASSWORD,
        reason="E2E_USERNAME / E2E_PASSWORD not set",
    )
    def test_available_exams_page_loads(self, authenticated_page: Page) -> None:
        """Available exams page must load without a server error for a student."""
        response = authenticated_page.goto(STUDENT_EXAM_LIST_URL)
        assert response is not None
        assert response.status < 500, f"Available exams page returned HTTP {response.status}"
        authenticated_page.wait_for_load_state("domcontentloaded")
        expect(authenticated_page.locator("body")).to_be_visible()

    @pytest.mark.skipif(
        not E2E_USERNAME or not E2E_PASSWORD,
        reason="E2E_USERNAME / E2E_PASSWORD not set",
    )
    def test_assigned_exams_page_loads(self, authenticated_page: Page) -> None:
        """Assigned exams page must load without a server error."""
        response = authenticated_page.goto(ASSIGNED_EXAM_LIST_URL)
        assert response is not None
        assert response.status < 500, f"Assigned exams page returned HTTP {response.status}"

    @pytest.mark.skipif(
        not E2E_USERNAME or not E2E_PASSWORD,
        reason="E2E_USERNAME / E2E_PASSWORD not set",
    )
    def test_exam_history_page_loads(self, authenticated_page: Page) -> None:
        """Student exam history page must load without a server error."""
        response = authenticated_page.goto(EXAM_HISTORY_URL)
        assert response is not None
        assert response.status < 500, f"Exam history page returned HTTP {response.status}"

    @pytest.mark.skipif(
        not E2E_USERNAME or not E2E_PASSWORD,
        reason="E2E_USERNAME / E2E_PASSWORD not set",
    )
    def test_assigned_exams_via_accounts(self, authenticated_page: Page) -> None:
        """Assigned exams page under accounts namespace must load for a student."""
        response = authenticated_page.goto(f"{BASE_URL}/accounts/assigned-exams/")
        assert response is not None
        assert response.status < 500, f"Accounts assigned exams page returned HTTP {response.status}"


# ── Live exam / pin entry ─────────────────────────────────────────────────────


class TestLiveExamPages:
    """Tests for the live/real-time exam lobby pages."""

    def test_live_pin_entry_page_loads(self, page: Page) -> None:
        """The live exam PIN entry page must be publicly accessible (players join anonymously)."""
        response = page.goto(LIVE_PIN_ENTRY_URL)
        assert response is not None
        # The PIN entry page is public (no login required for players).
        assert response.status < 500, f"Live PIN entry page returned server error HTTP {response.status}"

    def test_live_pin_entry_page_renders_form_or_input(self, page: Page) -> None:
        """The PIN entry page must display a form or input field for the exam PIN."""
        page.goto(LIVE_PIN_ENTRY_URL)
        page.wait_for_load_state("domcontentloaded")

        pin_input = page.locator("input[name='pin'], input[type='text'], input[type='number']")
        form = page.locator("form")
        assert pin_input.count() > 0 or form.count() > 0, "No PIN input or form found on the live exam entry page"
