"""Service-layer tests: persistence, filename randomisation, reply flow."""

from __future__ import annotations

import pytest

from apps.trial_exams import services
from apps.trial_exams.forms import TrialExamRequestForm
from apps.trial_exams.models import TrialExamRequest

pytestmark = pytest.mark.django_db


class _DummyRequest:
    def __init__(self, user):
        self.user = user
        self.META = {"REMOTE_ADDR": "203.0.113.7", "HTTP_USER_AGENT": "pytest-UA"}


def _bound_form(valid_post_data, pdf):
    form = TrialExamRequestForm(valid_post_data, {"questions_file": pdf})
    assert form.is_valid(), form.errors
    return form


def test_create_persists_and_randomises_filename(monkeypatch, create_user, valid_post_data, pdf_upload):
    # Avoid background email/notification I/O during the test.
    monkeypatch.setattr(services, "dispatch_trial_notifications", lambda obj: None)

    user = create_user()
    form = _bound_form(valid_post_data, pdf_upload(name="my-questions.pdf"))
    obj = services.create_trial_exam_request(form=form, request=_DummyRequest(user))

    assert TrialExamRequest.objects.count() == 1
    assert obj.user_id == user.id
    assert obj.ip_address == "203.0.113.7"
    assert obj.user_agent == "pytest-UA"
    assert obj.status == TrialExamRequest.STATUS_PENDING
    # Original name preserved, stored name randomised (no original name on disk).
    assert obj.original_filename == "my-questions.pdf"
    assert "my-questions" not in obj.questions_file.name
    assert obj.questions_file.name.endswith(".pdf")


def test_send_reply_marks_added(monkeypatch, create_user, valid_post_data, pdf_upload):
    monkeypatch.setattr(services, "dispatch_trial_notifications", lambda obj: None)
    # Keep the reply email out of the test; the status change is synchronous.
    monkeypatch.setattr(services, "send_email_with_fallback", lambda **kw: (True, ""))

    admin = create_user(username="admin", email="admin@example.com", is_superuser=True, is_staff=True)
    student = create_user()
    form = _bound_form(valid_post_data, pdf_upload())
    obj = services.create_trial_exam_request(form=form, request=_DummyRequest(student))

    ok = services.send_reply_to_trial_request(
        request_obj=obj,
        reply_body="Suallar əlavə olundu.",
        reply_from="info",
        sent_by=admin,
    )
    assert ok is True

    obj.refresh_from_db()
    assert obj.status == TrialExamRequest.STATUS_ADDED
    assert obj.reply_body == "Suallar əlavə olundu."
    assert obj.reply_from == "info"
    assert obj.reply_sent_by_id == admin.id


def test_send_reply_rejects_unknown_inbox(monkeypatch, create_user, valid_post_data, pdf_upload):
    monkeypatch.setattr(services, "dispatch_trial_notifications", lambda obj: None)
    student = create_user()
    form = _bound_form(valid_post_data, pdf_upload())
    obj = services.create_trial_exam_request(form=form, request=_DummyRequest(student))

    with pytest.raises(ValueError):
        services.send_reply_to_trial_request(request_obj=obj, reply_body="x" * 20, reply_from="nope", sent_by=student)
