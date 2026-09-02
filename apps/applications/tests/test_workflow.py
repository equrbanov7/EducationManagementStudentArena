"""Axın — yönləndirmə izləməni saxlayır, tarixçə append-only qalır,
bildiriş və audit sətirləri yazılır."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.utils import timezone

import pytest

from apps.applications.constants import ApplicationStatus, EventKind
from apps.applications.models import ApplicationEvent, ApplicationWatch
from apps.applications.services import maintenance, submit, workflow
from apps.applications.tests.factories import kind_of, make_world, unit_of
from apps.audit.models import AuditLog
from apps.notifications.models import InAppNotification, NotificationType

pytestmark = pytest.mark.django_db


@pytest.fixture()
def world():
    return make_world("flow")


@pytest.fixture()
def application(world):
    return submit.submit_application(
        organization=world["organization"],
        user=world["student"],
        kind=kind_of(world, "diger"),
        subject="Seçmə fənn bloku",
        body="İxtisas üzrə seçmə fənn blokunu dəyişmək istəyirəm, izah lazımdır.",
    )


def test_submission_numbers_sequentially_per_organization(world, application):
    assert application.number == "MR-000001"
    second = submit.submit_application(
        organization=world["organization"],
        user=world["student"],
        kind=kind_of(world, "diger"),
        subject="İkinci müraciət",
        body="İkinci müraciətin kifayət qədər uzun mətni burada yazılıb.",
    )
    assert second.number == "MR-000002"


def test_submission_computes_the_sla_in_working_days(world, application):
    from apps.applications.sla import add_working_days

    assert application.sla_due_on == add_working_days(timezone.localdate(), kind_of(world, "diger").sla_days)


def test_submission_writes_the_first_timeline_row(world, application):
    events = list(application.events.all())
    assert [event.kind for event in events] == [EventKind.SUBMITTED]
    assert events[0].new_status == ApplicationStatus.SUBMITTED


def test_mark_seen_is_idempotent(world, application):
    assert workflow.mark_seen(application=application, user=world["coordinator"]) is True
    application.refresh_from_db()
    assert application.status == ApplicationStatus.IN_REVIEW
    assert workflow.mark_seen(application=application, user=world["coordinator"]) is False
    assert application.events.filter(kind=EventKind.SEEN).count() == 1


def test_forwarding_moves_the_unit_and_keeps_the_watch(world, application):
    workflow.mark_seen(application=application, user=world["coordinator"])
    source = application.current_unit
    workflow.forward(
        application=application,
        user=world["coordinator"],
        target_unit=unit_of(world, "rim"),
        note="Sistem tərəfli nasazlıq görünür, RİM baxsın.",
        keep_watching=True,
    )
    application.refresh_from_db()

    assert application.status == ApplicationStatus.FORWARDED
    assert application.current_unit.code == "rim"
    assert application.current_scope_unit is None
    watch = ApplicationWatch.objects.get(application=application)
    assert watch.unit_id == source.pk
    assert watch.scope_unit == world["tree"]["specialty"]


def test_forwarding_without_keep_watching_creates_no_watch(world, application):
    workflow.mark_seen(application=application, user=world["coordinator"])
    workflow.forward(
        application=application,
        user=world["coordinator"],
        target_unit=unit_of(world, "rim"),
        note="Bizim səlahiyyətimizdə deyil, ötürürəm.",
        keep_watching=False,
    )
    assert not ApplicationWatch.objects.filter(application=application).exists()


def test_forwarding_to_the_same_unit_is_refused(world, application):
    from apps.applications.state_machine import TransitionDenied

    workflow.mark_seen(application=application, user=world["coordinator"])
    with pytest.raises(TransitionDenied) as excinfo:
        workflow.forward(
            application=application,
            user=world["coordinator"],
            target_unit=application.current_unit,
            note="Özümə göndərməyə çalışıram — bu qadağandır.",
        )
    assert excinfo.value.code == "unit.same"


def test_history_survives_forwarding(world, application):
    workflow.mark_seen(application=application, user=world["coordinator"])
    workflow.forward(
        application=application,
        user=world["coordinator"],
        target_unit=unit_of(world, "rim"),
        note="Sistem tərəfli nasazlıq görünür, RİM baxsın.",
    )
    kinds = list(application.events.values_list("kind", flat=True))
    assert kinds == [EventKind.SUBMITTED, EventKind.SEEN, EventKind.FORWARDED]


def test_events_are_append_only(world, application):
    event = application.events.first()
    event.text = "dəyişdirildi"
    with pytest.raises(ValidationError):
        event.save()
    with pytest.raises(ValidationError):
        event.delete()


def test_info_request_round_trip(world, application):
    workflow.mark_seen(application=application, user=world["coordinator"])
    workflow.request_info(application=application, user=world["coordinator"], text="Hansı fənni nəzərdə tutursunuz?")
    application.refresh_from_db()
    assert application.status == ApplicationStatus.WAITING_INFO

    workflow.provide_info(application=application, user=world["student"], text="Riyaziyyat-2 fənnini nəzərdə tuturam.")
    application.refresh_from_db()
    assert application.status == ApplicationStatus.IN_REVIEW


def test_return_and_resubmit_round_trip(world, application):
    workflow.mark_seen(application=application, user=world["coordinator"])
    workflow.return_for_correction(
        application=application, user=world["coordinator"], reason="Mətn aydın deyil, konkretləşdirin."
    )
    application.refresh_from_db()
    assert application.status == ApplicationStatus.RETURNED

    workflow.resubmit(
        application=application,
        user=world["student"],
        subject="Seçmə fənn bloku — Riyaziyyat-2",
        body="Riyaziyyat-2 fənnini seçmə blokdan çıxarmaq üçün müraciət edirəm.",
    )
    application.refresh_from_db()
    assert application.status == ApplicationStatus.SUBMITTED
    assert "Riyaziyyat-2" in application.subject


def test_resolve_then_sender_close(world, application):
    workflow.mark_seen(application=application, user=world["coordinator"])
    workflow.resolve(application=application, user=world["coordinator"], text="Blok dəyişdirildi, tamamdır.")
    application.refresh_from_db()
    assert application.status == ApplicationStatus.RESOLVED and application.resolved_at is not None

    workflow.close(application=application, user=world["student"])
    application.refresh_from_db()
    assert application.status == ApplicationStatus.CLOSED and not application.is_open


def test_sender_can_cancel_an_open_application(world, application):
    workflow.cancel(application=application, user=world["student"], reason="Özüm həll etdim.")
    application.refresh_from_db()
    assert application.status == ApplicationStatus.CANCELLED


def test_assign_requires_a_handler_of_the_current_unit(world, application):
    from apps.applications.state_machine import TransitionDenied

    workflow.mark_seen(application=application, user=world["coordinator"])
    with pytest.raises(TransitionDenied) as excinfo:
        workflow.assign(application=application, user=world["coordinator"], assignee=world["dean"])
    assert excinfo.value.code == "assignee.not_handler"

    workflow.assign(application=application, user=world["coordinator"], assignee=world["coordinator"])
    application.refresh_from_db()
    assert application.status == ApplicationStatus.ASSIGNED
    assert application.assigned_to_id == world["coordinator"].pk


def test_internal_notes_are_handler_only(world, application):
    workflow.mark_seen(application=application, user=world["coordinator"])
    workflow.add_comment(application=application, user=world["coordinator"], text="Daxili qeyd", is_internal=True)
    # Sahibin öz qeydi heç vaxt daxili ola bilməz.
    workflow.add_comment(application=application, user=world["student"], text="Cavab gözləyirəm", is_internal=True)
    flags = list(application.events.filter(kind=EventKind.COMMENT).values_list("is_internal", flat=True))
    assert flags == [True, False]


def test_notifications_are_emitted_to_the_right_people(world, django_capture_on_commit_callbacks):
    """⚠️ Bildirişlər `transaction.on_commit`-lə göndərilir — `django_db` altında
    commit BAŞ VERMİR, ona görə callback-lər açıq şəkildə icra edilməlidir."""
    InAppNotification.objects.all().delete()
    with django_capture_on_commit_callbacks(execute=True):
        application = submit.submit_application(
            organization=world["organization"],
            user=world["student"],
            kind=kind_of(world, "diger"),
            subject="Bildiriş yoxlaması",
            body="Bu müraciət bildirişlərin doğru adamlara getdiyini yoxlayır.",
        )
    rows = InAppNotification.objects.filter(notification_type=NotificationType.APPLICATION)
    recipients = set(rows.values_list("recipient_id", flat=True))
    assert world["student"].pk in recipients, "sahibə təsdiq bildirişi getməlidir"
    assert world["coordinator"].pk in recipients, "aidiyyəti koordinatora bildiriş getməlidir"
    assert world["other_coordinator"].pk not in recipients, "başqa ixtisasın koordinatoru bildiriş almamalıdır"
    assert application.number in "".join(rows.values_list("title", flat=True))


def test_watchers_are_notified_on_resolve(world, application, django_capture_on_commit_callbacks):
    workflow.mark_seen(application=application, user=world["coordinator"])
    workflow.forward(
        application=application,
        user=world["coordinator"],
        target_unit=unit_of(world, "rim"),
        note="Sistem tərəfli nasazlıq görünür, RİM baxsın.",
    )
    application.refresh_from_db()
    InAppNotification.objects.all().delete()
    with django_capture_on_commit_callbacks(execute=True):
        workflow.resolve(application=application, user=world["rim"], text="Nasazlıq aradan qaldırıldı.")
    recipients = set(InAppNotification.objects.values_list("recipient_id", flat=True))
    assert world["student"].pk in recipients
    assert world["coordinator"].pk in recipients, "izləyən şöbə cavabdan xəbər tutmalıdır"


def test_audit_rows_are_written(world, application):
    workflow.mark_seen(application=application, user=world["coordinator"])
    workflow.resolve(application=application, user=world["coordinator"], text="Blok dəyişdirildi, tamamdır.")
    rows = AuditLog.objects.filter(resource_type="application", resource_id=str(application.pk))
    assert rows.count() >= 3
    assert any("resolved" in (row.resource_repr or "") for row in rows)


def test_auto_close_after_five_working_days(world, application):
    from datetime import timedelta

    workflow.mark_seen(application=application, user=world["coordinator"])
    workflow.resolve(application=application, user=world["coordinator"], text="Blok dəyişdirildi, tamamdır.")
    application.refresh_from_db()

    assert maintenance.close_stale_resolved(organization=world["organization"]) == 0
    later = (application.resolved_at + timedelta(days=14)).date()
    assert maintenance.close_stale_resolved(organization=world["organization"], today=later) == 1
    application.refresh_from_db()
    assert application.status == ApplicationStatus.CLOSED
    assert application.events.filter(kind=EventKind.CLOSED, actor__isnull=True).exists()


def test_every_transition_writes_exactly_one_event(world, application):
    before = ApplicationEvent.objects.filter(application=application).count()
    workflow.mark_seen(application=application, user=world["coordinator"])
    workflow.request_info(application=application, user=world["coordinator"], text="Əlavə izah lazımdır.")
    workflow.provide_info(application=application, user=world["student"], text="Bu da əlavə izah.")
    after = ApplicationEvent.objects.filter(application=application).count()
    assert after - before == 3
