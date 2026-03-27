"""
EMS Arena — Role-based E2E journeys backed by the deterministic CI scenario.

These tests reuse the existing pytest + Playwright direction but exercise
deeper, role-specific workflows than the original smoke-level page-load checks.
"""

from __future__ import annotations

import re

from playwright.sync_api import Page, expect

from .conftest import (
    E2E_ISOLATED_EXAM_SLUG,
    E2E_ISOLATED_ORG_SLUG,
    E2E_ORG_SLUG,
    E2E_SCENARIO_ASSIGNMENT_TITLE,
    E2E_SCENARIO_COURSE_TITLE,
    E2E_SCENARIO_EXAM_TITLE,
    build_url,
)


def _open_seeded_course_dashboard(page: Page, listing_path: str) -> None:
    """Navigate from a course listing page into the seeded scenario course dashboard."""
    page.goto(build_url(listing_path))
    page.wait_for_load_state("networkidle")
    expect(page.get_by_text(E2E_SCENARIO_COURSE_TITLE)).to_be_visible()

    dashboard_url = page.evaluate(
        """
        (courseTitle) => {
            const cards = Array.from(document.querySelectorAll('.course-card'));
            const matchingCard = cards.find((card) => (card.textContent || '').includes(courseTitle));
            if (!matchingCard) {
                return null;
            }

            const match = matchingCard.querySelector('a[href*="/courses/"][href*="/dashboard/"]');
            return match ? match.href : null;
        }
        """,
        E2E_SCENARIO_COURSE_TITLE,
    )

    assert dashboard_url, "Could not find any course dashboard link on the enrolled-course page."
    page.goto(dashboard_url)
    page.wait_for_load_state("networkidle")


def _open_seeded_assignment_detail(page: Page) -> None:
    """Navigate from the course dashboard to the seeded assignment detail page."""
    assignment_url = page.evaluate(
        """
        (assignmentTitle) => {
            const items = Array.from(document.querySelectorAll('.list-group-item'));
            const matchingItem = items.find((item) => (item.textContent || '').includes(assignmentTitle));
            if (!matchingItem) {
                return null;
            }

            const match = matchingItem.querySelector('a[href*="/assignments/"][href*="/detail/"]');
            return match ? match.href : null;
        }
        """,
        E2E_SCENARIO_ASSIGNMENT_TITLE,
    )

    assert assignment_url, "Could not find the seeded assignment detail link on the course dashboard."
    page.goto(assignment_url)
    page.wait_for_load_state("networkidle")


class TestRoleJourneys:
    """Stable role journeys that should pass once the deterministic scenario is seeded."""

    def test_org_owner_can_open_org_settings(self, owner_page: Page) -> None:
        owner_page.goto(build_url(f"/organizations/{E2E_ORG_SLUG}/settings/"))
        owner_page.wait_for_load_state("networkidle")

        assert owner_page.url.endswith(f"/organizations/{E2E_ORG_SLUG}/settings/")
        expect(owner_page.locator("form")).to_be_visible()
        expect(owner_page.locator("input[name='email']")).to_be_visible()

    def test_org_admin_can_open_org_settings(self, org_admin_page: Page) -> None:
        org_admin_page.goto(build_url(f"/organizations/{E2E_ORG_SLUG}/settings/"))
        org_admin_page.wait_for_load_state("networkidle")

        assert org_admin_page.url.endswith(f"/organizations/{E2E_ORG_SLUG}/settings/")
        expect(org_admin_page.locator("form")).to_be_visible()
        expect(org_admin_page.locator("input[name='email']")).to_be_visible()

    def test_teacher_sees_seeded_course_and_exam(self, teacher_page: Page) -> None:
        teacher_page.goto(build_url("/courses/my-courses/"))
        teacher_page.wait_for_load_state("networkidle")
        expect(teacher_page.get_by_text(E2E_SCENARIO_COURSE_TITLE)).to_be_visible()

        teacher_page.goto(build_url("/exams/"))
        teacher_page.wait_for_load_state("networkidle")
        expect(teacher_page.get_by_text(E2E_SCENARIO_EXAM_TITLE)).to_be_visible()

    def test_student_sees_seeded_course_assignment_and_exam(self, student_page: Page) -> None:
        _open_seeded_course_dashboard(student_page, "/courses/my-enrolled/")

        _open_seeded_assignment_detail(student_page)
        expect(
            student_page.get_by_role("heading", name=re.compile(E2E_SCENARIO_ASSIGNMENT_TITLE, re.I))
        ).to_be_visible()

        student_page.goto(build_url("/exams/assigned/"))
        student_page.wait_for_load_state("networkidle")
        expect(student_page.get_by_text(E2E_SCENARIO_EXAM_TITLE)).to_be_visible()

    def test_late_student_inherits_group_based_access(self, late_student_page: Page) -> None:
        _open_seeded_course_dashboard(late_student_page, "/courses/my-enrolled/")

        _open_seeded_assignment_detail(late_student_page)
        expect(
            late_student_page.get_by_role("heading", name=re.compile(E2E_SCENARIO_ASSIGNMENT_TITLE, re.I))
        ).to_be_visible()

        late_student_page.goto(build_url("/exams/assigned/"))
        late_student_page.wait_for_load_state("networkidle")
        expect(late_student_page.get_by_text(E2E_SCENARIO_EXAM_TITLE)).to_be_visible()

    def test_cross_tenant_org_and_exam_are_blocked_for_student(self, student_page: Page) -> None:
        response = student_page.goto(build_url(f"/organizations/{E2E_ISOLATED_ORG_SLUG}/"))
        student_page.wait_for_load_state("networkidle")

        assert response is not None
        assert response.status < 500
        assert student_page.url.endswith(
            "/organizations/select/"
        ), "Student from the seeded org should not land inside the isolated org dashboard."

        exam_response = student_page.goto(build_url(f"/exams/{E2E_ISOLATED_EXAM_SLUG}/start/"))
        student_page.wait_for_load_state("networkidle")

        assert exam_response is not None
        assert exam_response.status == 404, "Cross-tenant exam start should be hidden behind a 404."
