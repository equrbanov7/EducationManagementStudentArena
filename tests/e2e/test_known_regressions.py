"""
Former regressions captured during the QA audit.

These assertions now enforce the fixes for the highest-risk authorization and
exam-resume bugs that were discovered during the audit.
"""

from __future__ import annotations

from playwright.sync_api import Page

from .conftest import E2E_ORG_SLUG, E2E_PENDING_ORG_SLUG, E2E_RESUME_EXAM_SLUG, build_url


def test_pending_owner_cannot_access_pending_org_dashboard(pending_owner_page: Page) -> None:
    pending_owner_page.goto(build_url(f"/organizations/{E2E_PENDING_ORG_SLUG}/"))
    pending_owner_page.wait_for_load_state("domcontentloaded")

    assert pending_owner_page.url.endswith(
        "/organizations/select/"
    ), "Pending owners should be blocked from their organization dashboard until approval."


def test_student_cannot_open_org_members_page(student_page: Page) -> None:
    student_page.goto(build_url(f"/organizations/{E2E_ORG_SLUG}/members/"))
    student_page.wait_for_load_state("domcontentloaded")

    assert student_page.url.endswith(
        "/organizations/select/"
    ), "Students should be redirected away from the organization member directory."


def test_student_cannot_open_org_roles_page(student_page: Page) -> None:
    student_page.goto(build_url(f"/organizations/{E2E_ORG_SLUG}/roles/"))
    student_page.wait_for_load_state("domcontentloaded")

    assert student_page.url.endswith(
        "/organizations/select/"
    ), "Students should be redirected away from the organization role matrix."


def test_in_progress_exam_can_resume_via_start_url(resume_student_page: Page) -> None:
    resume_student_page.goto(build_url(f"/exams/{E2E_RESUME_EXAM_SLUG}/start/"))
    resume_student_page.wait_for_load_state("domcontentloaded")

    assert (
        "/attempt/" in resume_student_page.url
    ), "Students with an active attempt should be routed back into the in-progress attempt."
