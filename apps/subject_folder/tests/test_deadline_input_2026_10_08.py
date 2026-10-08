"""Fənn qovluğu son tarixi — «gg.aa.iiii ss:dd» (24 saat), ISO da qəbul (sahib qərarı 2026-10-08)."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from django.template.loader import render_to_string

import pytest

from apps.subject_folder.models import FolderAssignment, TaskDeadline

from .test_cabinet_actions import _post

pytestmark = pytest.mark.django_db
BAKU = ZoneInfo("Asia/Baku")


def _assignment_and_task(world, folder):
    _response, payload = _post(world.teacher, world.org, action="assign", folder=folder.pk, offering=world.offering.pk)
    assert payload["ok"], payload
    return (
        FolderAssignment.objects.get(folder=folder, offering=world.offering),
        folder.tasks.filter(kind="selfwork").first(),
    )


def test_day_first_deadline_is_saved_in_baku_time(world, folder):
    assignment, task = _assignment_and_task(world, folder)
    _response, payload = _post(
        world.teacher,
        world.org,
        action="deadline_set",
        task=task.pk,
        assignment=assignment.pk,
        opens_at="01.11.2030 08:00",
        due_at="15/11/2030 23:59",
    )
    assert payload["ok"], payload
    deadline = TaskDeadline.objects.get(assignment=assignment, task=task)
    assert deadline.opens_at.astimezone(BAKU).replace(tzinfo=None) == datetime(2030, 11, 1, 8, 0)
    assert deadline.due_at.astimezone(BAKU).replace(tzinfo=None) == datetime(2030, 11, 15, 23, 59)


def test_unreadable_deadline_keeps_code_and_explains(world, folder):
    assignment, task = _assignment_and_task(world, folder)
    response, payload = _post(
        world.teacher, world.org, action="deadline_set", task=task.pk, assignment=assignment.pk, due_at="15.11.2030"
    )
    assert response.status_code == 400
    assert payload["error"] == "invalid_datetime"
    assert "ss:dd" in payload["message"]


def test_deadline_dialog_renders_locale_free_inputs():
    html = render_to_string("subject_folder/cabinet/teacher/dlg/_deadline.html", {"sp": {}})
    assert "datetime-local" not in html
    assert html.count("data-ems-dt-input") == 2
    assert 'id="sfDeadlineDue"' in html and "ems-input" in html
