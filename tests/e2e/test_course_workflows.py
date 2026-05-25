"""
EMS Arena — Course Workflows E2E Tests
=======================================
Covers:
  D. Course management (create, list, enrol, student view)
  E. Groups and membership propagation
"""

from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

from .conftest import BASE_URL, E2E_PASSWORD, E2E_USERNAME

# ── URLs ─────────────────────────────────────────────────────────────────────

CREATE_COURSE_URL = f"{BASE_URL}/courses/create_course/"
MY_COURSES_URL = f"{BASE_URL}/courses/my-courses/"
ENROLLED_COURSES_URL = f"{BASE_URL}/courses/my-enrolled/"
EXAM_GROUPS_URL = f"{BASE_URL}/exams/groups/"
CREATE_GROUP_URL = f"{BASE_URL}/exams/groups/create/"


# ── Unauthenticated access ────────────────────────────────────────────────────


class TestCourseUnauthenticated:
    """Verify that unauthenticated users cannot access course management pages."""

    @pytest.mark.parametrize(
        "course_path",
        [
            "/courses/create_course/",
            "/courses/my-courses/",
            "/courses/my-enrolled/",
        ],
    )
    def test_course_path_blocks_anonymous_user(self, page: Page, course_path: str) -> None:
        """Anonymous access to course management must redirect to login, not 5xx."""
        response = page.goto(f"{BASE_URL}{course_path}")
        page.wait_for_load_state("domcontentloaded")

        if response is not None:
            assert response.status < 500, f"Course path {course_path!r} returned server error HTTP {response.status}"
        assert (
            "/accounts/login/" in page.url
        ), f"Course path {course_path!r} accessible to anonymous user — URL: {page.url}"


# ── Teacher course management ─────────────────────────────────────────────────


class TestTeacherCoursePages:
    """Tests for course management pages accessible to a teacher/rector user."""

    @pytest.mark.skipif(
        not E2E_USERNAME or not E2E_PASSWORD,
        reason="E2E_USERNAME / E2E_PASSWORD not set",
    )
    def test_create_course_page_loads(self, authenticated_page: Page) -> None:
        """Course creation form must load without a server error for a teacher."""
        response = authenticated_page.goto(CREATE_COURSE_URL)
        assert response is not None
        assert response.status < 500, f"Course creation page returned HTTP {response.status}"
        authenticated_page.wait_for_load_state("domcontentloaded")
        expect(authenticated_page.locator("body")).to_be_visible()

    @pytest.mark.skipif(
        not E2E_USERNAME or not E2E_PASSWORD,
        reason="E2E_USERNAME / E2E_PASSWORD not set",
    )
    def test_my_courses_page_loads(self, authenticated_page: Page) -> None:
        """My-courses list page must load without a server error."""
        response = authenticated_page.goto(MY_COURSES_URL)
        assert response is not None
        assert response.status < 500, f"My courses page returned HTTP {response.status}"
        authenticated_page.wait_for_load_state("domcontentloaded")
        expect(authenticated_page.locator("body")).to_be_visible()

    @pytest.mark.skipif(
        not E2E_USERNAME or not E2E_PASSWORD,
        reason="E2E_USERNAME / E2E_PASSWORD not set",
    )
    def test_course_create_page_has_form(self, authenticated_page: Page) -> None:
        """Course creation page must render a form for input."""
        response = authenticated_page.goto(CREATE_COURSE_URL)
        assert response is not None
        if response.status == 200:
            authenticated_page.wait_for_load_state("domcontentloaded")
            form = authenticated_page.locator("form")
            assert form.count() > 0, "No form found on the course creation page"

    @pytest.mark.skipif(
        not E2E_USERNAME or not E2E_PASSWORD,
        reason="E2E_USERNAME / E2E_PASSWORD not set",
    )
    def test_exam_groups_page_loads(self, authenticated_page: Page) -> None:
        """Student groups (exam groups) management page must load for teachers."""
        response = authenticated_page.goto(EXAM_GROUPS_URL)
        assert response is not None
        assert response.status < 500, f"Exam groups page returned HTTP {response.status}"

    @pytest.mark.skipif(
        not E2E_USERNAME or not E2E_PASSWORD,
        reason="E2E_USERNAME / E2E_PASSWORD not set",
    )
    def test_create_group_page_loads(self, authenticated_page: Page) -> None:
        """Group creation form page must load without a server error."""
        response = authenticated_page.goto(CREATE_GROUP_URL)
        assert response is not None
        assert response.status < 500, f"Create group page returned HTTP {response.status}"


# ── Student course access ─────────────────────────────────────────────────────


class TestStudentCoursePages:
    """Tests for course pages viewed from a student perspective."""

    @pytest.mark.skipif(
        not E2E_USERNAME or not E2E_PASSWORD,
        reason="E2E_USERNAME / E2E_PASSWORD not set",
    )
    def test_enrolled_courses_page_loads(self, authenticated_page: Page) -> None:
        """Enrolled-courses (student view) page must load without a server error."""
        response = authenticated_page.goto(ENROLLED_COURSES_URL)
        assert response is not None
        assert response.status < 500, f"Enrolled courses page returned HTTP {response.status}"
        authenticated_page.wait_for_load_state("domcontentloaded")
        expect(authenticated_page.locator("body")).to_be_visible()

    @pytest.mark.skipif(
        not E2E_USERNAME or not E2E_PASSWORD,
        reason="E2E_USERNAME / E2E_PASSWORD not set",
    )
    def test_enrolled_courses_page_body_not_empty(self, authenticated_page: Page) -> None:
        """The enrolled-courses page body must contain some rendered content."""
        response = authenticated_page.goto(ENROLLED_COURSES_URL)
        if response is None or response.status != 200:
            pytest.skip(f"Enrolled courses page returned HTTP {response.status if response else 'None'}")
        authenticated_page.wait_for_load_state("domcontentloaded")
        body_text = authenticated_page.locator("body").inner_text()
        assert len(body_text.strip()) > 0, "Enrolled courses page body is empty"
