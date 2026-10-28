"""Həssas mətn tarixçəsi, dəyişməz qərar, bərpa və ünvan/tenant qapıları."""

import json
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

import pytest

from apps.applications.constants import ApplicationStatus
from apps.applications.models import ApplicationContentRevision
from apps.applications.payloads import detail_payload
from apps.applications.services import access, maintenance, queries, workflow
from apps.applications.services.content import edit_application, edit_reply, set_application_deleted
from apps.applications.services.reply_visibility import set_reply_visibility
from apps.applications.state_machine import TransitionDenied
from apps.audit.models import AuditLog

from .test_endpoints import client_for
from .test_recipient_reply_visibility import create
from .test_recipient_reply_visibility import world as _world_fixture

world = _world_fixture
pytestmark = pytest.mark.django_db


def test_reply_edit_keeps_original_and_private_history_out_of_general_audit(world):
    application = create(world, recipient_id=world["vice_a"].pk)
    event = workflow.add_comment(application=application, user=world["vice_a"], text="PRIVATE-ORIGINAL-REPLY")
    edit_reply(
        application=application,
        user=world["vice_a"],
        event_id=event.pk,
        text="PRIVATE-CORRECTED-REPLY",
        expected_revision="",
    )
    revision = ApplicationContentRevision.objects.get(event=event)
    assert revision.old_text == "PRIVATE-ORIGINAL-REPLY"
    event.refresh_from_db()
    assert event.text == "PRIVATE-ORIGINAL-REPLY"
    payload = detail_payload(application, user=world["teacher"])
    reply = next(row for row in payload["events"] if row["id"] == str(event.pk))
    assert reply["text"] == "PRIVATE-CORRECTED-REPLY" and reply["revision"] == str(revision.pk)
    assert "PRIVATE-ORIGINAL-REPLY" not in json.dumps(payload)
    audits = list(
        AuditLog.objects.filter(changes__operation="reply_edit").values("changes", "reason", "old_values", "new_values")
    )
    assert audits and "PRIVATE-" not in json.dumps(audits)
    set_reply_visibility(application=application, user=world["vice_a"], event_id=event.pk, hidden=True)
    set_reply_visibility(application=application, user=world["vice_a"], event_id=event.pk, hidden=False)
    assert (
        next(row for row in detail_payload(application, user=world["teacher"])["events"] if row["id"] == str(event.pk))[
            "text"
        ]
        == "PRIVATE-CORRECTED-REPLY"
    )
    with pytest.raises(ValidationError):
        revision.save()
    with pytest.raises(ValidationError):
        revision.delete()


def test_other_prorector_and_stale_reply_edit_are_denied(world):
    application = create(world, recipient_id=world["vice_a"].pk)
    event = workflow.add_comment(application=application, user=world["vice_a"], text="Əvvəlki cavabın mətni")
    with pytest.raises(TransitionDenied):
        edit_reply(
            application=application,
            user=world["vice_b"],
            event_id=event.pk,
            text="İcazəsiz dəyişiklik",
            expected_revision="",
        )
    client = client_for(world["vice_a"], world["organization"])
    url = reverse("applications:action", args=[application.pk])
    assert (
        client.post(
            url, {"action": "edit_reply", "event": str(event.pk), "text": "Düzəldilmiş cavab", "revision": ""}
        ).status_code
        == 200
    )
    assert (
        client.post(
            url, {"action": "edit_reply", "event": str(event.pk), "text": "Köhnə formadan cavab", "revision": ""}
        ).status_code
        == 409
    )
    assert ApplicationContentRevision.objects.filter(event=event).count() == 1


def test_application_edit_preserves_routing_decision_and_full_private_previous_body(world):
    application = create(world, recipient_id=world["vice_a"].pk)
    workflow.resolve(application=application, user=world["vice_a"], text="Bu məsələ həll edildi.")
    before = (
        application.status,
        application.current_unit_id,
        application.assigned_to_id,
        application.recipient_restricted,
        application.sla_due_on,
        application.resolved_at,
    )
    old_body = application.body
    edit_application(
        application=application,
        user=world["teacher"],
        subject="Düzəldilmiş mövzu",
        body="Müraciətin düzəldilmiş tam məzmunu burada saxlanır.",
        expected_updated_at=application.updated_at.isoformat(),
    )
    assert (
        application.status,
        application.current_unit_id,
        application.assigned_to_id,
        application.recipient_restricted,
        application.sla_due_on,
        application.resolved_at,
    ) == before
    revision = ApplicationContentRevision.objects.get(application=application, event=None)
    assert revision.old_text == old_body
    assert application.body == revision.new_text
    with pytest.raises(TransitionDenied):
        edit_application(
            application=application,
            user=world["vice_b"],
            subject="İcazəsiz mətn",
            body="Başqasının göndərişinə dəyişiklik edilməməlidir.",
            expected_updated_at=application.updated_at.isoformat(),
        )


def test_soft_delete_hides_counts_files_and_actions_then_restores_same_status(world):
    application = create(world, recipient_id=world["vice_a"].pk)
    event = workflow.add_comment(
        application=application,
        user=world["vice_a"],
        text="Sənədli cavab mətni",
        files=[SimpleUploadedFile("proof.pdf", b"%PDF-1.4\n%%EOF", content_type="application/pdf")],
    )
    assert queries.handler_inbox_counts(organization=world["organization"], user=world["vice_a"])["inbox_open"] == 1
    before = (application.status, application.sla_due_on, application.resolved_at)
    set_application_deleted(
        application=application,
        user=world["teacher"],
        deleted=True,
        expected_updated_at=application.updated_at.isoformat(),
    )
    assert (application.status, application.sla_due_on, application.resolved_at) == before
    assert not queries.list_applications(organization=world["organization"], user=world["teacher"], tab="mine").exists()
    assert (
        queries.list_applications(organization=world["organization"], user=world["teacher"], tab="deleted")
        .filter(pk=application.pk)
        .exists()
    )
    assert not queries.list_applications(
        organization=world["organization"], user=world["vice_b"], tab="deleted"
    ).exists()
    assert queries.handler_inbox_counts(organization=world["organization"], user=world["vice_a"])["inbox_open"] == 0
    assert queries.sender_counts(organization=world["organization"], user=world["teacher"])["open"] == 0
    payload = detail_payload(application, user=world["teacher"])
    assert not payload["allowed_actions"] and not payload["attachments"] and payload["content_actions"]["can_restore"]
    assert not access.can_view_attachment(world["teacher"], event.attachments.select_related("event").get())
    with pytest.raises(TransitionDenied):
        workflow.add_comment(application=application, user=world["teacher"], text="Silinmişə yeni qeyd")
    with pytest.raises(TransitionDenied):
        set_application_deleted(
            application=application,
            user=world["vice_b"],
            deleted=False,
            expected_updated_at=application.updated_at.isoformat(),
        )
    set_application_deleted(
        application=application,
        user=world["teacher"],
        deleted=False,
        expected_updated_at=application.updated_at.isoformat(),
    )
    assert (application.status, application.sla_due_on, application.resolved_at) == before
    assert access.can_view_attachment(world["teacher"], event.attachments.select_related("event").get())
    assert queries.handler_inbox_counts(organization=world["organization"], user=world["vice_a"])["inbox_open"] == 1


def test_deleted_resolved_request_never_auto_closes(world):
    application = create(world, recipient_id=world["vice_a"].pk)
    workflow.resolve(application=application, user=world["vice_a"], text="Köhnə tarixdə həll edilmiş məsələ.")
    type(application).objects.filter(pk=application.pk).update(resolved_at=timezone.now() - timedelta(days=30))
    application.refresh_from_db()
    set_application_deleted(
        application=application,
        user=world["teacher"],
        deleted=True,
        expected_updated_at=application.updated_at.isoformat(),
    )
    assert maintenance.close_stale_resolved(organization=world["organization"]) == 0
    application.refresh_from_db()
    assert application.status == ApplicationStatus.RESOLVED


def test_deleted_named_history_is_not_opened_by_a_former_watch_manager(world):
    application = create(world, recipient_id=world["vice_a"].pk)
    workflow.forward(
        application=application,
        user=world["vice_a"],
        target_unit=world["units"]["rim"],
        note="Aidiyyəti şöbənin araşdırmasına göndərilir.",
        keep_watching=True,
    )
    assert access.can_view(world["vice_a"], application)
    set_application_deleted(
        application=application,
        user=world["teacher"],
        deleted=True,
        expected_updated_at=application.updated_at.isoformat(),
    )
    assert not access.can_view(world["vice_a"], application)
    assert not access.can_see_internal(world["vice_a"], application)
    assert not queries.list_applications(
        organization=world["organization"], user=world["vice_a"], tab="deleted"
    ).exists()
    with pytest.raises(TransitionDenied):
        set_application_deleted(
            application=application,
            user=world["vice_a"],
            deleted=False,
            expected_updated_at=application.updated_at.isoformat(),
        )
    assert access.can_view(world["rim"], application)


@pytest.mark.parametrize("operation", ["resolve", "comment", "reply_visibility"])
def test_stale_instance_cannot_write_after_delete(world, operation):
    application = create(world, recipient_id=world["vice_a"].pk)
    event = workflow.add_comment(application=application, user=world["vice_a"], text="Qorunmalı əvvəlki cavab")
    stale = type(application).objects.get(pk=application.pk)
    set_application_deleted(
        application=application,
        user=world["teacher"],
        deleted=True,
        expected_updated_at=application.updated_at.isoformat(),
    )
    with pytest.raises(TransitionDenied):
        if operation == "resolve":
            workflow.resolve(application=stale, user=world["vice_a"], text="Silinmiş müraciətə qərar verilməməlidir.")
        elif operation == "comment":
            workflow.add_comment(application=stale, user=world["vice_a"], text="Silinmişə qeyd yazılmamalıdır.")
        else:
            set_reply_visibility(application=stale, user=world["vice_a"], event_id=event.pk, hidden=True)
    application.refresh_from_db()
    assert application.status == ApplicationStatus.SUBMITTED
    event.refresh_from_db()
    assert not event.hidden_at


def test_named_handler_cannot_soft_delete_or_restore_another_persons_request(world):
    application = create(world, recipient_id=world["vice_a"].pk)
    assert access.can_act(world["vice_a"], application)
    assert not detail_payload(application, user=world["vice_a"])["content_actions"]["can_delete"]
    with pytest.raises(TransitionDenied):
        set_application_deleted(
            application=application,
            user=world["vice_a"],
            deleted=True,
            expected_updated_at=application.updated_at.isoformat(),
        )
