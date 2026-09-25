"""``subject_folder:action`` — müəllim, baxış və tələbə əməlləri (JSON), icazə sərhədləri."""

from __future__ import annotations

from datetime import timedelta

from django.test import Client
from django.urls import reverse
from django.utils import timezone

import pytest

from apps.subject_folder import public
from apps.subject_folder.constants import SubmissionStatus
from apps.subject_folder.models import FolderAssignment, FolderMaterial, SubjectFolder, TaskDeadline

from . import factories as f
from .conftest import upload

pytestmark = pytest.mark.django_db

URL = "subject_folder:action"


def _client(user, org):
    client = Client()
    client.force_login(user)
    session = client.session
    session["active_organization"] = org.slug
    session.save()
    return client


def _post(user, org, **data):
    response = _client(user, org).post(reverse(URL), data)
    return response, response.json()


def test_anonymous_is_redirected_and_get_is_rejected(world):
    assert Client().post(reverse(URL), {"action": "folder_create"}).status_code == 302
    assert _client(world.teacher, world.org).get(reverse(URL)).status_code == 405


def test_unknown_action_and_missing_object(world):
    response, payload = _post(world.teacher, world.org, action="nope")
    assert response.status_code == 400 and payload["error"] == "unknown_action"
    response, payload = _post(world.teacher, world.org, action="folder_update", folder="not-a-uuid", title="X")
    assert response.status_code == 404 and payload["error"] == "not_found"


def test_teacher_creates_folder_from_teachable_subject(world):
    response, payload = _post(
        world.teacher, world.org, action="folder_create", subject_period=f"{world.subject.pk}|{world.period.pk}"
    )
    assert response.status_code == 200 and payload["ok"] and payload["created"]
    folder = SubjectFolder.objects.get(pk=payload["folder"])
    assert folder.owner == world.teacher and folder.topics.exists()
    assert "sf_folder=" in payload["url"]
    # İkinci dəfə — mövcud qovluq qaytarılır.
    _response, again = _post(
        world.teacher, world.org, action="folder_create", subject_period=f"{world.subject.pk}|{world.period.pk}"
    )
    assert again["created"] is False and again["folder"] == payload["folder"]


def test_student_cannot_create_folder_or_manage_content(world, folder):
    student = world.students[0]
    response, payload = _post(
        student, world.org, action="folder_create", subject_period=f"{world.subject.pk}|{world.period.pk}"
    )
    assert response.status_code in (400, 403) and not payload["ok"]
    response, payload = _post(student, world.org, action="folder_update", folder=folder.pk, title="Oğurluq")
    assert response.status_code == 403 and payload["error"].startswith("permission.")
    folder.refresh_from_db()
    assert folder.title != "Oğurluq"


def test_material_topic_homework_and_publish_flow(world, folder):
    client_user = world.teacher
    response, payload = _post(
        client_user, world.org, action="topic_save", folder=folder.pk, title="Əlavə mövzu", week_no="16"
    )
    assert payload["ok"], payload
    topic = folder.topics.get(title="Əlavə mövzu")
    client = _client(client_user, world.org)
    response = client.post(
        reverse(URL),
        {
            "action": "material_save",
            "folder": folder.pk,
            "kind": "file",
            "title": "Slayd",
            "topic": topic.pk,
            "file": upload("slayd.txt", b"slayd"),
        },
    )
    assert response.json()["ok"], response.json()
    material = FolderMaterial.objects.get(folder=folder, title="Slayd")
    assert material.topic == topic and not material.is_published
    _response, payload = _post(client_user, world.org, action="material_publish", material=material.pk, published="1")
    material.refresh_from_db()
    assert payload["ok"] and material.is_published
    _response, payload = _post(
        client_user,
        world.org,
        action="homework_create",
        folder=folder.pk,
        title="Ev işi",
        allow_text_answer="1",
        allow_files="1",
        allowed_extensions="pdf, .py",
        max_files="3",
    )
    assert payload["ok"], payload
    homework = folder.tasks.get(title="Ev işi")
    assert homework.allowed_extensions == [".pdf", ".py"] and homework.max_files == 3
    _response, payload = _post(
        client_user,
        world.org,
        action="task_update",
        task=homework.pk,
        title="Ev işi (yenilənib)",
        allow_text_answer__present="1",
        allow_files__present="1",
        allow_files="1",
    )
    homework.refresh_from_db()
    assert payload["ok"] and homework.title == "Ev işi (yenilənib)" and homework.allow_text_answer is False
    _response, payload = _post(client_user, world.org, action="material_archive", material=material.pk)
    material.refresh_from_db()
    assert payload["ok"] and material.is_archived


def test_assign_and_deadline(world, folder):
    _response, payload = _post(world.teacher, world.org, action="assign", folder=folder.pk, offering=world.offering.pk)
    assert payload["ok"], payload
    assignment = FolderAssignment.objects.get(folder=folder, offering=world.offering)
    assert assignment.is_active
    folder.refresh_from_db()
    assert folder.status == public.FolderStatus.ACTIVE
    task = folder.tasks.filter(kind="selfwork").first()
    due = (timezone.localtime() + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M")
    _response, payload = _post(
        world.teacher,
        world.org,
        action="deadline_set",
        task=task.pk,
        assignment=assignment.pk,
        due_at=due,
        late_policy="allow",
    )
    assert payload["ok"], payload
    deadline = TaskDeadline.objects.get(assignment=assignment, task=task)
    assert deadline.late_policy == "allow" and deadline.due_at is not None
    _response, payload = _post(world.teacher, world.org, action="deadline_set", task=task.pk, assignment=assignment.pk)
    assert payload["ok"] and not TaskDeadline.objects.filter(assignment=assignment, task=task).exists()
    response, payload = _post(
        world.teacher, world.org, action="deadline_set", task=task.pk, due_at="sabah axşam", assignment=assignment.pk
    )
    assert response.status_code == 400 and payload["error"] == "invalid_datetime"


def test_teacher_cannot_assign_offering_they_do_not_teach(world, folder):
    other_teacher = f.make_teacher(world.org, prefix="t2")
    other = f.make_offering(world.org, subject=world.subject, period=world.period, instructor=other_teacher)
    response, payload = _post(world.teacher, world.org, action="assign", folder=folder.pk, offering=other.pk)
    assert response.status_code == 403 and not payload["ok"]
    assert not FolderAssignment.objects.filter(offering=other).exists()


def test_student_submits_and_teacher_reviews(ready, django_capture_on_commit_callbacks):
    student = ready.students[0]
    client = _client(student, ready.org)
    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            reverse(URL),
            {"action": "draft_save", "task": ready.slot1.pk, "assignment": ready.assignment.pk, "text": "Qaralama"},
        )
    assert response.json()["ok"], response.json()
    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            reverse(URL),
            {
                "action": "submit",
                "task": ready.slot1.pk,
                "assignment": ready.assignment.pk,
                "text": "Yekun cavab",
                "files": upload(),
            },
        )
    assert response.json()["ok"], response.json()
    submission = ready.slot1.submissions.get(student=student, is_current=True)
    assert submission.status == SubmissionStatus.SUBMITTED and submission.text_answer == "Yekun cavab"
    # Başqa tələbə bu göndərişi qəbul edə bilməz.
    response, payload = _post(
        ready.students[1], ready.org, action="review_accept", submission=submission.pk, points="4"
    )
    assert response.status_code == 403
    # Müəllim limitdən artıq bal verə bilməz.
    response, payload = _post(ready.teacher, ready.org, action="review_accept", submission=submission.pk, points="9")
    assert response.status_code == 400 and payload["error"] == "review.points_invalid"
    with django_capture_on_commit_callbacks(execute=True):
        response, payload = _post(
            ready.teacher, ready.org, action="review_accept", submission=submission.pk, points="4.5"
        )
    assert payload["ok"], payload
    submission.refresh_from_db()
    assert submission.status == SubmissionStatus.ACCEPTED and str(submission.points) == "4.5"
    assert payload["level"] == "warning"  # hook bu testdə yoxdur → bal növbədədir


def test_return_requires_feedback_and_bulk_check(ready, django_capture_on_commit_callbacks):
    student = ready.students[0]
    with django_capture_on_commit_callbacks(execute=True):
        homework_row = public.submit(
            task=ready.homework, assignment=ready.assignment, student=student, text="Ev işi", files=()
        )
        other_row = public.submit(
            task=ready.homework, assignment=ready.assignment, student=ready.students[1], text="Ev işi 2", files=()
        )
    response, payload = _post(
        ready.teacher, ready.org, action="review_return", submission=homework_row.pk, feedback="x"
    )
    assert response.status_code == 400 and payload["error"] == "review.feedback_required"
    client = _client(ready.teacher, ready.org)
    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            reverse(URL),
            {"action": "review_bulk", "bulk_action": "check", "submission": [homework_row.pk, other_row.pk]},
        )
    payload = response.json()
    assert payload["ok"] and payload["level"] == "success", payload
    homework_row.refresh_from_db()
    other_row.refresh_from_db()
    assert homework_row.status == other_row.status == SubmissionStatus.CHECKED
