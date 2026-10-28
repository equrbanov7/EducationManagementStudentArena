import pytest

from apps.applications.constants import EventKind
from apps.applications.models import ApplicationEvent
from apps.applications.payloads import detail_payload
from apps.applications.services import access, queries, submit, workflow
from apps.applications.services.notify import handler_recipients
from apps.applications.services.reply_visibility import set_reply_visibility
from apps.applications.state_machine import TransitionDenied

from .factories import MANAGE, add_member, make_user, make_world

pytestmark = pytest.mark.django_db


@pytest.fixture
def world():
    world = make_world("recipient-reply")
    for key in ("vice_a", "vice_b"):
        world[key] = make_user(key)
        add_member(world["organization"], world[key], "vice_rector", permissions=MANAGE)
    return world


def create(world, user="teacher", **kwargs):
    return submit.submit_application(
        organization=world["organization"],
        user=world[user],
        kind=world["kinds"]["prorektor"],
        subject="Plan üzrə müraciət",
        body="Plan üzrə bu problemi araşdırmağınızı xahiş edirəm.",
        **kwargs,
    )


def test_student_cannot_forge_prorector_submission(world):
    with pytest.raises(TransitionDenied):
        create(world, "student", recipient_id=world["vice_a"].pk)
    with pytest.raises(TransitionDenied):
        submit.submit_application(
            organization=world["organization"],
            user=world["student"],
            kind=world["kinds"]["transkript"],
            subject="Saxta şöbə seçimi",
            body="Bu sorğu başqa şöbəyə yönləndirilməməlidir.",
            unit_override=world["units"]["tedris"],
            recipient_id=world["vice_a"].pk,
        )


def test_only_selected_recipient_gets_inbox_badge_notification_and_action(world):
    application = create(world, recipient_id=world["vice_a"].pk)
    assert access.is_current_handler(world["vice_a"], application)
    assert not access.is_current_handler(world["vice_b"], application)
    assert not access.can_act(world["vice_b"], application)
    assert queries.handler_inbox_counts(organization=world["organization"], user=world["vice_a"])["inbox_open"] == 1
    assert queries.handler_inbox_counts(organization=world["organization"], user=world["vice_b"])["inbox_open"] == 0
    assert [user.pk for user in handler_recipients(application)] == [world["vice_a"].pk]


def test_named_destination_rejects_missing_wrong_role_and_cross_tenant_recipient(world):
    other = make_world("recipient-other")
    for recipient in (None, "garbage", world["student"].pk, other["rim"].pk):
        with pytest.raises(TransitionDenied):
            create(world, recipient_id=recipient)


def test_reply_hide_restore_keeps_original_and_denies_other_handler(world):
    application = create(world, recipient_id=world["vice_a"].pk)
    event = workflow.add_comment(application=application, user=world["vice_a"], text="Bu cavabın mətni saxlanılacaq.")
    with pytest.raises(TransitionDenied):
        set_reply_visibility(application=application, user=world["vice_b"], event_id=event.pk, hidden=True)
    set_reply_visibility(application=application, user=world["vice_a"], event_id=event.pk, hidden=True)
    event.refresh_from_db()
    assert event.text == "Bu cavabın mətni saxlanılacaq."
    assert event.hidden_at is not None
    payload = detail_payload(application, user=world["teacher"])
    assert next(row for row in payload["events"] if row["id"] == str(event.pk))["text"] == "Cavab silinib."
    set_reply_visibility(application=application, user=world["vice_a"], event_id=event.pk, hidden=False)
    event.refresh_from_db()
    assert event.hidden_at is None
    opening = ApplicationEvent.objects.get(application=application, kind=EventKind.SUBMITTED)
    with pytest.raises(TransitionDenied):
        set_reply_visibility(application=application, user=world["teacher"], event_id=opening.pk, hidden=True)


def test_migration_seed_is_idempotent_and_reversible(world):
    from importlib import import_module

    from django.apps import apps

    migration = import_module("apps.applications.migrations.0008_recipient_and_reply_visibility")
    migration.seed(apps, None)
    migration.seed(apps, None)
    unit = world["units"]["tedris"]
    unit.refresh_from_db()
    assert unit.requires_recipient and not unit.accepts_students
    assert unit.kinds.filter(code="prorektor").count() == 1
    migration.unseed(apps, None)
    unit.refresh_from_db()
    assert not unit.requires_recipient and unit.accepts_students


def test_hidden_reply_attachment_is_not_downloadable(world):
    from django.core.files.uploadedfile import SimpleUploadedFile

    application = create(world, recipient_id=world["vice_a"].pk)
    event = workflow.add_comment(
        application=application,
        user=world["vice_a"],
        text="Sənəd əlavə olunan cavabdır.",
        files=[SimpleUploadedFile("proof.pdf", b"%PDF-1.4\n%%EOF", content_type="application/pdf")],
    )
    attachment = event.attachments.get()
    assert access.can_view_attachment(world["teacher"], attachment)
    set_reply_visibility(application=application, user=world["vice_a"], event_id=event.pk, hidden=True)
    attachment = event.attachments.select_related("event").get()
    assert not access.can_view_attachment(world["teacher"], attachment)
    assert not detail_payload(application, user=world["teacher"])["attachments"]
