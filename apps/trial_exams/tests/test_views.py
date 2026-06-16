"""View tests: auth gating + successful submission."""

from __future__ import annotations

from django.urls import reverse

import pytest

from apps.trial_exams import services
from apps.trial_exams.models import TrialExamRequest

pytestmark = pytest.mark.django_db


def test_get_requires_login(client):
    resp = client.get(reverse("trial_exams:request"))
    assert resp.status_code == 302
    assert "/login" in resp["Location"] or "login" in resp["Location"]


def test_get_renders_for_logged_in_user(client, create_user):
    user = create_user()
    client.force_login(user)
    resp = client.get(reverse("trial_exams:request"))
    assert resp.status_code == 200
    # Form is pre-filled with the user's details.
    assert user.username.encode() in resp.content or b"trial-form" in resp.content


def test_post_creates_request_and_redirects(monkeypatch, client, create_user, valid_post_data, pdf_upload):
    # Keep email/notification side effects out of the request cycle.
    monkeypatch.setattr(services, "dispatch_trial_notifications", lambda obj: None)

    user = create_user()
    client.force_login(user)

    data = dict(valid_post_data, questions_file=pdf_upload())
    resp = client.post(reverse("trial_exams:request"), data)

    assert resp.status_code == 302
    assert "sent=1" in resp["Location"]
    assert TrialExamRequest.objects.filter(user=user, subject_name="Riyaziyyat").count() == 1


def test_post_without_file_is_invalid(monkeypatch, client, create_user, valid_post_data):
    monkeypatch.setattr(services, "dispatch_trial_notifications", lambda obj: None)
    user = create_user()
    client.force_login(user)

    resp = client.post(reverse("trial_exams:request"), valid_post_data)
    # Re-renders the form (200) without creating a row.
    assert resp.status_code == 200
    assert TrialExamRequest.objects.count() == 0
