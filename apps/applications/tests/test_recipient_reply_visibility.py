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


def test_other_manager_cannot_read_named_request_or_its_internal_attachments(world):
    from django.core.files.uploadedfile import SimpleUploadedFile

    application = create(world, recipient_id=world["vice_a"].pk)
    assert not access.can_view(world["vice_b"], application)
    assert not access.can_see_internal(world["vice_b"], application)
    assert (
        not queries.list_applications(organization=world["organization"], user=world["vice_b"], tab="all", stat="all")
        .filter(pk=application.pk)
        .exists()
    )
    event = workflow.add_comment(
        application=application,
        user=world["vice_a"],
        text="Private internal reply",
        is_internal=True,
        files=[SimpleUploadedFile("private.pdf", b"%PDF-1.4\n%%EOF", content_type="application/pdf")],
    )
    assert not access.can_view_attachment(world["vice_b"], event.attachments.select_related("event").get())
    assert access.can_view(world["rim"], application)
    assert access.can_see_internal(world["organization"].owner, application)


def test_named_watch_stays_personal_after_forward_and_notifies_only_its_recipient(world):
    from apps.applications.services.notify import watcher_recipients

    application = create(world, recipient_id=world["vice_a"].pk)
    workflow.forward(
        application=application,
        user=world["vice_a"],
        target_unit=world["units"]["rim"],
        note="This department should complete the investigation.",
        keep_watching=True,
    )
    application.refresh_from_db()
    assert application.recipient_restricted
    assert application.watches.get().recipient_ids == [world["vice_a"].pk]
    assert access.can_view(world["vice_a"], application)
    assert access.can_see_internal(world["vice_a"], application)
    assert not access.can_act(world["vice_a"], application)
    assert not access.can_view(world["vice_b"], application)
    assert not access.can_see_internal(world["vice_b"], application)
    assert (
        not queries.list_applications(
            organization=world["organization"], user=world["vice_b"], tab="watching", stat="all"
        )
        .filter(pk=application.pk)
        .exists()
    )
    assert [user.pk for user in watcher_recipients(application)] == [world["vice_a"].pk]


def test_forward_without_watch_does_not_reopen_named_history_to_generic_managers(world):
    application = create(world, recipient_id=world["vice_a"].pk)
    workflow.forward(
        application=application,
        user=world["vice_a"],
        target_unit=world["units"]["rim"],
        note="Investigate this request without keeping a watch.",
        keep_watching=False,
    )
    assert not application.watches.exists()
    assert not access.can_view(world["vice_b"], application)
    assert not access.can_view(world["vice_a"], application)
    assert access.can_view(world["teacher"], application)
    assert access.can_act(world["rim"], application)


def test_named_watch_can_keep_multiple_actual_recipients_without_broadcast(world):
    from apps.applications.services.notify import watcher_recipients

    application = create(world, recipient_id=world["vice_a"].pk)
    for recipient in ("vice_a", "vice_b"):
        if recipient == "vice_b":
            workflow.forward(
                application=application,
                user=world["rim"],
                target_unit=world["units"]["tedris"],
                note="This named person should investigate the next stage.",
                recipient_id=world[recipient].pk,
                keep_watching=False,
            )
        workflow.forward(
            application=application,
            user=world[recipient],
            target_unit=world["units"]["rim"],
            note="The request returns to this department for follow-up.",
            keep_watching=True,
        )
    watch = application.watches.get()
    assert set(watch.recipient_ids) == {world["vice_a"].pk, world["vice_b"].pk}
    assert {user.pk for user in watcher_recipients(application)} == set(watch.recipient_ids)


def test_migration_restricts_existing_named_history_without_guessing_watch_audience(world):
    from importlib import import_module

    from django.apps import apps

    from apps.applications.models import Application, ApplicationWatch

    application = create(world, recipient_id=world["vice_a"].pk)
    Application.objects.filter(pk=application.pk).update(recipient_restricted=False)
    ApplicationWatch.objects.create(
        application=application, organization=world["organization"], unit=world["units"]["tedris"]
    )
    migration = import_module("apps.applications.migrations.0009_named_recipient_audience")
    migration.restrict_existing(apps, None)
    migration.restrict_existing(apps, None)
    application.refresh_from_db()
    assert application.recipient_restricted
    watch = application.watches.get()
    assert watch.recipient_ids == []
    assert not access.watch_is_visible(world["vice_a"], application, watch)
    assert not access.watch_is_visible(world["vice_b"], application, watch)


@pytest.mark.parametrize("extra_org_role", [False, True])
def test_scoped_watch_list_and_counts_match_detail_visibility_after_named_forward(world, extra_org_role):
    # Eyni koordinator rolunun başqa ixtisasdakı daşıyıcısı ümumi manage açarı
    # ilə də şəxsi müraciətin watch sətirindən özünə görünüş uydura bilməz.
    add_member(
        world["organization"],
        world["other_coordinator"],
        "program_coordinator",
        scope_unit=world["other_tree"]["specialty"],
        permissions=MANAGE,
    )
    if extra_org_role:
        add_member(world["organization"], world["other_coordinator"], "observer", permissions=MANAGE)
    application = submit.submit_application(
        organization=world["organization"],
        user=world["student"],
        kind=world["kinds"]["diger"],
        subject="Şəxsi əhatəli müraciət",
        body="Bu müraciət yalnız aidiyyəti ixtisasdan izlənilməlidir.",
    )
    workflow.forward(
        application=application,
        user=world["coordinator"],
        target_unit=world["units"]["tedris"],
        recipient_id=world["vice_a"].pk,
        note="Şəxsən araşdırmaq üçün prorektora yönləndirilir.",
        keep_watching=True,
    )
    application.refresh_from_db()
    assert application.recipient_restricted
    for viewer_key, expected in (("coordinator", True), ("other_coordinator", False)):
        viewer = world[viewer_key]
        assert access.can_view(viewer, application) is expected
        assert (
            queries.list_applications(organization=world["organization"], user=viewer, tab="watching", stat="all")
            .filter(pk=application.pk)
            .exists()
            is expected
        )
        assert queries.tab_counts(organization=world["organization"], user=viewer)["watching"] == int(expected)
        assert queries.handler_kpis(organization=world["organization"], user=viewer)["watching"] == int(expected)
    assert (
        not queries.list_applications(
            organization=world["organization"], user=world["other_coordinator"], tab="all", stat="all"
        )
        .filter(pk=application.pk)
        .exists()
    )

    # Sonra müraciət scoped şöbəyə qayıdır: əlaqəsiz org-wide rol
    # yanlış koordinatora inbox/all görünüşünü də genişləndirməməlidir.
    workflow.forward(
        application=application,
        user=world["vice_a"],
        target_unit=world["units"]["koordinator"],
        note="Aidiyyəti ixtisas üzrə araşdırmanı davam etdirin.",
        keep_watching=False,
    )
    application.refresh_from_db()
    for viewer_key, expected in (("coordinator", True), ("other_coordinator", False)):
        viewer = world[viewer_key]
        assert access.can_view(viewer, application) is expected
        assert (
            queries.list_applications(organization=world["organization"], user=viewer, tab="inbox", stat="all")
            .filter(pk=application.pk)
            .exists()
            is expected
        )
        assert queries.handler_inbox_counts(organization=world["organization"], user=viewer)["inbox_open"] == int(
            expected
        )
    assert (
        not queries.list_applications(
            organization=world["organization"], user=world["other_coordinator"], tab="all", stat="all"
        )
        .filter(pk=application.pk)
        .exists()
    )
