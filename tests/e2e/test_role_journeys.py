"""
EMS Arena — Role-based E2E journeys backed by the deterministic CI scenario.

These tests reuse the existing pytest + Playwright direction but exercise
deeper, role-specific workflows than the original smoke-level page-load checks.
"""

from __future__ import annotations

import re
from urllib.parse import urlencode

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
    page.wait_for_load_state("domcontentloaded")
    expect(page.get_by_text(E2E_SCENARIO_COURSE_TITLE)).to_be_visible()

    dashboard_url = page.evaluate(
        """
        (courseTitle) => {
            // Kabinet «Təyin olunmuş kurslar» bölməsində kartın ÖZÜ keçiddir (`a.mc-card[data-mc-card]`);
            // köhnə siyahı səhifəsində (`.course-card`) keçid kartın içindədir (URL auditi 2026-10-10).
            const cards = Array.from(document.querySelectorAll('.course-card, [data-mc-card]'));
            const matchingCard = cards.find((card) => (card.textContent || '').includes(courseTitle));
            if (!matchingCard) {
                return null;
            }

            const selector = 'a[href*="/courses/"][href*="/dashboard/"]';
            const match = matchingCard.matches(selector) ? matchingCard : matchingCard.querySelector(selector);
            return match ? match.href : null;
        }
        """,
        E2E_SCENARIO_COURSE_TITLE,
    )

    assert dashboard_url, "Could not find any course dashboard link on the enrolled-course page."
    page.goto(dashboard_url)
    page.wait_for_load_state("domcontentloaded")


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
    page.wait_for_load_state("domcontentloaded")


def _open_seeded_assigned_exam_list(page: Page) -> None:
    """Open the assigned-exams page filtered to the deterministic seeded exam."""
    query = urlencode({"q": E2E_SCENARIO_EXAM_TITLE})
    page.goto(build_url(f"/exams/assigned/?{query}"))
    page.wait_for_load_state("domcontentloaded")


class TestRoleJourneys:
    """Stable role journeys that should pass once the deterministic scenario is seeded."""

    def test_org_owner_settings_url_lands_in_cabinet(self, owner_page: Page) -> None:
        # Sahib 2026-10-11: köhnə «Təşkilat Ayarları» səhifəsi silindi — URL kabinetə aparır.
        owner_page.goto(build_url(f"/organizations/{E2E_ORG_SLUG}/settings/"))
        owner_page.wait_for_load_state("domcontentloaded")

        assert "/accounts/profile/" in owner_page.url

    def test_org_admin_settings_url_lands_in_cabinet(self, org_admin_page: Page) -> None:
        # Sahib 2026-10-11: köhnə «Təşkilat Ayarları» səhifəsi silindi — URL kabinetə aparır.
        org_admin_page.goto(build_url(f"/organizations/{E2E_ORG_SLUG}/settings/"))
        org_admin_page.wait_for_load_state("domcontentloaded")

        assert "/accounts/profile/" in org_admin_page.url

    def test_teacher_sees_seeded_course_and_exam(self, teacher_page: Page) -> None:
        teacher_page.goto(build_url("/accounts/profile/?section=my-courses"))
        teacher_page.wait_for_load_state("domcontentloaded")
        expect(teacher_page.get_by_text(E2E_SCENARIO_COURSE_TITLE)).to_be_visible()

        teacher_page.goto(build_url("/exams/"))
        teacher_page.wait_for_load_state("domcontentloaded")
        expect(teacher_page.get_by_text(E2E_SCENARIO_EXAM_TITLE)).to_be_visible()

    def test_student_sees_seeded_course_assignment_and_exam(self, student_page: Page) -> None:
        _open_seeded_course_dashboard(student_page, "/accounts/profile/?section=assigned-courses")

        _open_seeded_assignment_detail(student_page)
        expect(
            student_page.get_by_role("heading", name=re.compile(E2E_SCENARIO_ASSIGNMENT_TITLE, re.I))
        ).to_be_visible()

        _open_seeded_assigned_exam_list(student_page)
        expect(student_page.get_by_text(E2E_SCENARIO_EXAM_TITLE)).to_be_visible()

    def test_late_student_inherits_group_based_access(self, late_student_page: Page) -> None:
        _open_seeded_course_dashboard(late_student_page, "/accounts/profile/?section=assigned-courses")

        _open_seeded_assignment_detail(late_student_page)
        expect(
            late_student_page.get_by_role("heading", name=re.compile(E2E_SCENARIO_ASSIGNMENT_TITLE, re.I))
        ).to_be_visible()

        _open_seeded_assigned_exam_list(late_student_page)
        expect(late_student_page.get_by_text(E2E_SCENARIO_EXAM_TITLE)).to_be_visible()

    def test_cross_tenant_org_and_exam_are_blocked_for_student(self, student_page: Page) -> None:
        response = student_page.goto(build_url(f"/organizations/{E2E_ISOLATED_ORG_SLUG}/"))
        student_page.wait_for_load_state("domcontentloaded")

        assert response is not None
        assert response.status < 500
        assert student_page.url.endswith(
            "/organizations/select/"
        ), "Student from the seeded org should not land inside the isolated org dashboard."

        exam_response = student_page.goto(build_url(f"/exams/{E2E_ISOLATED_EXAM_SLUG}/start/"))
        student_page.wait_for_load_state("domcontentloaded")

        assert exam_response is not None
        assert exam_response.status == 404, "Cross-tenant exam start should be hidden behind a 404."
