"""Kabinet bölmələri — qeydiyyat, görünürlük, render (CSP: inline kod yoxdur) və kontekst vəziyyətləri."""

from __future__ import annotations

import re

from django.test import Client
from django.urls import reverse

import pytest

from apps.accounts.views.profile.sections_api import AJAX_SAFE_SECTIONS, SECTION_PARTIALS
from apps.subject_folder import public

from .conftest import upload

pytestmark = pytest.mark.django_db

SECTIONS = ("subject-folders", "subject-folder-review", "my-subject-folders")
INLINE_SCRIPT = re.compile(r"<script(?![^>]*\bsrc=)(?![^>]*application/json)[^>]*>", re.I)


@pytest.fixture(autouse=True)
def _university_mode(settings):
    """Bölmələr universitet kabinetinindir; ``config/settings/test.py`` rejimi söndürür."""
    settings.UNIVERSITY_MODE = True


def _client(user, org):
    client = Client()
    client.force_login(user)
    session = client.session
    session["active_organization"] = org.slug
    session.save()
    return client


def _panel(html, section):
    """Bölmə panelinin HTML-i — iç-içə ``<section>`` kartlarını nəzərə alır."""
    start = html.index(f'data-profile-section-panel="{section}"')
    depth = 1
    for tag in re.finditer(r"<(/?)section\b", html[start:]):
        depth += -1 if tag.group(1) else 1
        if depth == 0:
            return html[start : start + tag.start()]
    raise AssertionError(f"{section}: bağlanmamış <section>")


def _get(user, org, section, **params):
    query = "&".join(f"sf_{key}={value}" for key, value in params.items())
    url = f"{reverse('accounts:profile')}?section={section}" + (f"&{query}" if query else "")
    response = _client(user, org).get(url)
    assert response.status_code == 200
    html = response.content.decode()
    return response, _panel(html, section)


def _assert_csp_clean(panel):
    assert not INLINE_SCRIPT.search(panel), "inline <script> panelin içində"
    assert 'style="' not in panel, "inline style= atributu"


def test_sections_are_registered_and_ajax_safe():
    for section in SECTIONS:
        assert section in SECTION_PARTIALS
        assert section in AJAX_SAFE_SECTIONS
    assert public.SECTION_TEACHER == "subject-folders"
    assert public.SECTION_REVIEW == "subject-folder-review"
    assert public.SECTION_STUDENT == "my-subject-folders"


def test_menu_visibility_follows_role(world):
    teacher_response = _client(world.teacher, world.org).get(reverse("accounts:profile"))
    student_response = _client(world.students[0], world.org).get(reverse("accounts:profile"))
    teacher_sections = set(teacher_response.context["allowed_sections"])
    student_sections = set(student_response.context["allowed_sections"])
    assert {"subject-folders", "subject-folder-review"} <= teacher_sections
    assert "my-subject-folders" not in teacher_sections
    assert "my-subject-folders" in student_sections
    assert not {"subject-folders", "subject-folder-review"} & student_sections


def test_sections_hidden_outside_university_mode(world, settings):
    settings.UNIVERSITY_MODE = False
    for user in (world.teacher, world.students[0]):
        response = _client(user, world.org).get(reverse("accounts:profile"))
        assert not set(SECTIONS) & set(response.context["allowed_sections"])


def test_teacher_list_offers_creation_and_lists_folders(world, folder):
    _response, panel = _get(world.teacher, world.org, "subject-folders")
    _assert_csp_clean(panel)
    assert folder.title in panel
    assert "sfFolderCreate" in panel
    assert f"{world.subject.pk}|{world.period.pk}" in panel  # «Yeni qovluq» seçimi


def test_teacher_folder_content_and_groups_tabs_render(ready):
    public.create_material(
        ready.folder, by_user=ready.teacher, kind="link", title="Mühazirə videosu", url="https://example.com/v"
    )
    _response, panel = _get(ready.teacher, ready.org, "subject-folders", folder=ready.folder.pk)
    _assert_csp_clean(panel)
    assert "Mühazirə videosu" in panel
    assert ready.slot1.title in panel
    assert 'data-sf-open="sfMaterial"' in panel
    _response, panel = _get(ready.teacher, ready.org, "subject-folders", folder=ready.folder.pk, tab="groups")
    _assert_csp_clean(panel)
    assert 'data-sf-open="sfDeadline"' in panel
    assert str(ready.assignment.pk) in panel


def test_foreign_teacher_cannot_open_folder(ready):
    from . import factories as f

    other = f.make_teacher(ready.org, prefix="other")
    _response, panel = _get(other, ready.org, "subject-folders", folder=ready.folder.pk)
    assert ready.folder.title not in panel
    assert "fa-folder-minus" in panel  # «Qovluq tapılmadı» vəziyyəti


def test_student_list_folder_and_task_views(ready):
    student = ready.students[0]
    _response, panel = _get(student, ready.org, "my-subject-folders")
    _assert_csp_clean(panel)
    assert ready.folder.title in panel
    _response, panel = _get(student, ready.org, "my-subject-folders", folder=ready.folder.pk)
    assert ready.homework.title in panel
    _response, panel = _get(student, ready.org, "my-subject-folders", folder=ready.folder.pk, task=ready.homework.pk)
    _assert_csp_clean(panel)
    assert "data-sf-answer" in panel
    assert str(ready.assignment.pk) in panel


def test_unenrolled_student_sees_nothing(ready):
    from . import factories as f

    outsider = f.make_student(ready.org, prefix="outsider")
    _response, panel = _get(outsider, ready.org, "my-subject-folders", folder=ready.folder.pk)
    assert ready.folder.title not in panel


def test_review_panel_lists_submitted_work_and_detail_renders(ready, django_capture_on_commit_callbacks):
    student = ready.students[0]
    with django_capture_on_commit_callbacks(execute=True):
        submission = public.submit(
            task=ready.slot1, assignment=ready.assignment, student=student, text="Sərbəst işin cavabı", files=()
        )
    _response, panel = _get(ready.teacher, ready.org, "subject-folder-review")
    _assert_csp_clean(panel)
    assert f'data-sf-review="{submission.pk}"' in panel
    response = _client(ready.teacher, ready.org).get(reverse("subject_folder:review_detail", args=[submission.pk]))
    payload = response.json()
    assert response.status_code == 200 and payload["ok"]
    assert "review_accept" in payload["html"]
    assert "Sərbəst işin cavabı" in payload["html"]
    assert not INLINE_SCRIPT.search(payload["html"])
    preview = _client(ready.teacher, ready.org).get(
        reverse("subject_folder:review_preview", args=[submission.pk]) + "?points=4"
    )
    assert preview.json()["ok"] and not preview.json()["error"]


def test_review_detail_is_hidden_from_students(ready, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        submission = public.submit(
            task=ready.homework,
            assignment=ready.assignment,
            student=ready.students[0],
            text="",
            files=[upload()],
        )
    other_student = ready.students[1]
    response = _client(other_student, ready.org).get(reverse("subject_folder:review_detail", args=[submission.pk]))
    assert response.status_code == 404
    preview = _client(other_student, ready.org).get(reverse("subject_folder:review_preview", args=[submission.pk]))
    assert preview.status_code == 404


def test_superadmin_without_org_gets_empty_state():
    from django.contrib.auth import get_user_model

    admin = get_user_model().objects.create_superuser("sf_root", "sf_root@example.com", "x-Pass-12345")
    client = Client()
    client.force_login(admin)
    for section in SECTIONS:
        response = client.get(f"{reverse('accounts:profile')}?section={section}")
        assert response.status_code == 200
