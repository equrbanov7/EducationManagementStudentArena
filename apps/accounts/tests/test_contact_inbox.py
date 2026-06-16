from __future__ import annotations

from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import RequestFactory

import pytest

from apps.accounts.views.profile import contact_inbox
from apps.contact.models import ContactMessage
from apps.trial_exams.models import TrialExamRequest

pytestmark = pytest.mark.django_db


_CAPABILITIES = {
    "is_superadmin": True,
    "allowed_sections": {"superadmin-contact-messages"},
}


def _pdf(name: str = "questions.pdf") -> SimpleUploadedFile:
    return SimpleUploadedFile(
        name,
        b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n",
        content_type="application/pdf",
    )


def _request(path: str, user):
    request = RequestFactory().get(path)
    request.user = user
    return request


def test_contact_inbox_context_includes_trial_requests(settings, tmp_path, django_user_model):
    settings.MEDIA_ROOT = tmp_path
    user = django_user_model.objects.create_user(
        username="contact-inbox-admin",
        email="admin@example.com",
        password="testpass123",
        is_staff=True,
        is_superuser=True,
    )
    ContactMessage.objects.create(
        name="Contact Sender",
        email="contact@example.com",
        subject="support",
        message="Need support with the platform.",
    )
    trial = TrialExamRequest.objects.create(
        user=user,
        full_name="Trial Student",
        email="trial@example.com",
        subject_name="Riyaziyyat",
        note="Please add these questions.",
        questions_file=_pdf(),
        original_filename="questions.pdf",
    )

    ctx = contact_inbox.build_contact_inbox_context(
        _request("/accounts/profile/?section=superadmin-contact-messages", user),
        capabilities=_CAPABILITIES,
        active_section="superadmin-contact-messages",
    )

    assert ctx["contact_total_count"] == 2
    assert ctx["contact_unhandled_count"] == 2
    trial_item = next(item for item in ctx["contact_messages_list"] if item["kind"] == "trial")
    assert trial_item["pk"] == trial.pk
    assert trial_item["has_attachment"] is True
    assert "Riyaziyyat" in trial_item["subject"]


def test_contact_inbox_selects_trial_request_detail(settings, tmp_path, django_user_model):
    settings.MEDIA_ROOT = tmp_path
    user = django_user_model.objects.create_user(
        username="contact-inbox-admin-2",
        email="admin2@example.com",
        password="testpass123",
        is_staff=True,
        is_superuser=True,
    )
    trial = TrialExamRequest.objects.create(
        user=user,
        full_name="Trial Student",
        email="trial@example.com",
        subject_name="Fizika",
        questions_file=_pdf("physics.pdf"),
        original_filename="physics.pdf",
    )

    ctx = contact_inbox.build_contact_inbox_context(
        _request(f"/accounts/profile/?section=superadmin-contact-messages&trial_id={trial.pk}", user),
        capabilities=_CAPABILITIES,
        active_section="superadmin-contact-messages",
    )

    assert ctx["trial_selected_request"] == trial
    assert "contact_selected_message" not in ctx


def test_contact_inbox_trial_reply_post_uses_trial_service(monkeypatch, settings, tmp_path, django_user_model):
    settings.MEDIA_ROOT = tmp_path
    user = django_user_model.objects.create_user(
        username="contact-inbox-admin-3",
        email="admin3@example.com",
        password="testpass123",
        is_staff=True,
        is_superuser=True,
    )
    trial = TrialExamRequest.objects.create(
        user=user,
        full_name="Trial Student",
        email="trial@example.com",
        subject_name="Kimya",
        questions_file=_pdf("chemistry.pdf"),
        original_filename="chemistry.pdf",
    )
    called = {}

    def fake_send_reply_to_trial_request(**kwargs):
        called.update(kwargs)
        return True

    monkeypatch.setattr(contact_inbox, "send_reply_to_trial_request", fake_send_reply_to_trial_request)

    request = RequestFactory().post(
        "/accounts/profile/?section=superadmin-contact-messages",
        {
            "action": "trial_reply",
            "trial_id": str(trial.pk),
            "reply_from": "info",
            "reply_body": "Suallar sistemə əlavə olundu.",
        },
    )
    request.user = user
    request.session = {}
    request._messages = FallbackStorage(request)

    response = contact_inbox.handle_contact_reply_post(request, capabilities=_CAPABILITIES)

    assert response.status_code == 302
    assert f"trial_id={trial.pk}" in response["Location"]
    assert called["request_obj"] == trial
    assert called["sent_by"] == user
    assert called["reply_from"] == "info"
