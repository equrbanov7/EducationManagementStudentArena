"""Üç iş günü, cavab yarışı, RBAC və həll edilməmiş müraciətin dürüst bağlanması."""

import ast
from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client
from django.urls import reverse
from django.utils import timezone

import pytest

from apps.applications.constants import ApplicationStatus, EventKind
from apps.applications.models import Application
from apps.applications.payloads import detail_payload
from apps.applications.services import queries, submit, workflow
from apps.applications.services.waiting_info import close_stale_waiting_info, close_waiting, waiting_deadline
from apps.applications.state_machine import TransitionDenied
from apps.applications.tests.factories import MANAGE, add_member, kind_of, make_world
from apps.organizations.models import AcademicHoliday, HolidayKind

pytestmark = pytest.mark.django_db


def stamp(day, hour=10, minute=0):
    return timezone.make_aware(datetime.combine(day, datetime.min.time()).replace(hour=hour, minute=minute))


@pytest.fixture()
def world():
    return make_world("waiting-expiry")


def new_application(world):
    return submit.submit_application(
        organization=world["organization"],
        user=world["student"],
        kind=kind_of(world, "diger"),
        subject=f"Əlavə məlumat gözləyən sorğu {Application.objects.filter(organization=world['organization']).count() + 1}",
        body="Əlavə məlumat gözləmə müddətini və cavabın qorunmasını yoxlayan müraciət.",
    )


@pytest.fixture()
def application(world):
    app = new_application(world)
    with patch("django.utils.timezone.now", return_value=stamp(date(2026, 11, 13))):
        workflow.request_info(application=app, user=world["coordinator"], text="Zəhmət olmasa qrupunuzu da yazın.")
    return app


def test_exact_three_business_days_skip_weekend_preserve_time_and_repeat_is_idempotent(world, application):
    org = world["organization"]
    assert close_stale_waiting_info(organization=org, now=stamp(date(2026, 11, 17), 23)) == 0
    assert close_stale_waiting_info(organization=org, now=stamp(date(2026, 11, 18), 9, 59)) == 0
    with patch("django.utils.timezone.now", return_value=stamp(date(2026, 11, 18))):
        assert close_stale_waiting_info(organization=org) == 1
        assert close_stale_waiting_info(organization=org) == 0
    application.refresh_from_db()
    assert application.status == ApplicationStatus.CLOSED
    assert application.closed_at is not None
    assert application.resolved_at is None
    assert "3 iş günü" in application.events.get(kind=EventKind.CLOSED).text
    assert queries.sender_counts(organization=org, user=world["student"])["resolved"] == 0


def test_organization_holiday_and_transferred_workday_are_used(world, application):
    event = application.events.get(kind=EventKind.INFO_REQUESTED)
    type(event).objects.filter(pk=event.pk).update(created_at=stamp(date(2026, 11, 6)))
    AcademicHoliday.objects.create(organization=world["organization"], date=date(2026, 11, 9), name="Bayraq günü")
    assert waiting_deadline(application)[1] == stamp(date(2026, 11, 12))
    AcademicHoliday.objects.create(
        organization=world["organization"], date=date(2026, 11, 7), name="İş günü", kind=HolidayKind.WORKDAY
    )
    assert waiting_deadline(application)[1] == stamp(date(2026, 11, 11))


@pytest.mark.parametrize("comment", [False, True])
def test_sender_reply_resumes_review_and_fresh_handler_sla(world, application, comment):
    with patch("django.utils.timezone.now", return_value=stamp(date(2026, 11, 17))):
        operation = workflow.add_comment if comment else workflow.provide_info
        operation(application=application, user=world["student"], text="Qrupum haqqında əlavə məlumatı göndərirəm.")
    application.refresh_from_db()
    assert application.status == ApplicationStatus.IN_REVIEW
    assert application.sla_due_on > date(2026, 11, 17)
    assert close_stale_waiting_info(organization=world["organization"], now=stamp(date(2026, 11, 30))) == 0


def test_latest_info_request_restarts_wait_but_staff_note_does_not(world, application):
    with patch("django.utils.timezone.now", return_value=stamp(date(2026, 11, 17))):
        workflow.add_comment(
            application=application, user=world["coordinator"], text="Daxili izləmə qeydi", is_internal=True
        )
    assert close_stale_waiting_info(organization=world["organization"], now=stamp(date(2026, 11, 18))) == 1
    other = new_application(world)
    with patch("django.utils.timezone.now", return_value=stamp(date(2026, 11, 13))):
        workflow.request_info(application=other, user=world["coordinator"], text="İlk məlumat sorğusu burada yazılır.")
    with patch("django.utils.timezone.now", return_value=stamp(date(2026, 11, 17))):
        workflow.request_info(application=other, user=world["coordinator"], text="Yeni məlumat sorğusu burada yazılır.")
    assert close_stale_waiting_info(organization=world["organization"], now=stamp(date(2026, 11, 18))) == 0
    assert waiting_deadline(other)[1] == stamp(date(2026, 11, 20))


def test_internal_note_of_sender_who_is_also_staff_does_not_count_as_public_reply(world, application):
    add_member(world["organization"], world["student"], "ikt_rehber", permissions=MANAGE, level=88)
    with patch("django.utils.timezone.now", return_value=stamp(date(2026, 11, 17))):
        workflow.add_comment(
            application=application, user=world["student"], text="Yalnız əməkdaşlar üçün qeyddir.", is_internal=True
        )
    application.refresh_from_db()
    assert application.status == ApplicationStatus.WAITING_INFO
    assert close_stale_waiting_info(organization=world["organization"], now=stamp(date(2026, 11, 18))) == 1


def test_handler_can_close_waiting_without_reply_but_not_unanswered_normal_case(world, application):
    payload = detail_payload(application, user=world["coordinator"])
    assert "close_waiting" in payload["allowed_actions"]
    closed = workflow.ACTION_DISPATCH["close_waiting"](application=application, user=world["coordinator"])
    assert closed.status == ApplicationStatus.CLOSED and closed.resolved_at is None
    assert closed.events.get(kind=EventKind.CLOSED).actor_id == world["coordinator"].pk
    other = new_application(world)
    with pytest.raises(TransitionDenied):
        close_waiting(application=other, user=world["coordinator"])
    other.refresh_from_db()
    assert other.status == ApplicationStatus.SUBMITTED


def test_waiting_handler_http_action_accepts_no_text(world, application):
    client = Client()
    client.force_login(world["coordinator"])
    session = client.session
    session["active_organization"] = world["organization"].slug
    session.save()
    response = client.post(
        reverse("applications:action", kwargs={"application_id": application.pk}), {"action": "close_waiting"}
    )
    assert response.status_code == 200
    assert response.json()["application"]["status"]["key"] == ApplicationStatus.CLOSED
    application.refresh_from_db()
    assert application.resolved_at is None


def test_sender_outsider_and_other_tenant_handler_cannot_close(world, application):
    other = make_world("other-waiting")
    for user in (world["student"], world["outsider"], other["coordinator"], other["rim"]):
        with pytest.raises(TransitionDenied):
            close_waiting(application=application, user=user)
        application.refresh_from_db()
        assert application.status == ApplicationStatus.WAITING_INFO


def test_waiting_is_not_overdue_in_model_list_kpi_or_banner(world, application):
    Application.objects.filter(pk=application.pk).update(sla_due_on=date(2026, 10, 1))
    application.refresh_from_db()
    assert application.is_open and not application.is_overdue
    assert queries.handler_inbox_counts(organization=world["organization"], user=world["coordinator"])["overdue"] == 0
    assert not queries.list_applications(
        organization=world["organization"], user=world["coordinator"], tab="inbox", stat="overdue"
    ).exists()
    payload = detail_payload(application, user=world["coordinator"])
    assert payload["sla"]["tone"] == "waiting"
    assert payload["sla"]["sla_days"] == 3


def test_sweep_org_scope_deleted_rows_and_legacy_sender_reply_are_protected(world, application):
    other = make_world("other-waiting")
    other_app = new_application(other)
    with patch("django.utils.timezone.now", return_value=stamp(date(2026, 11, 13))):
        workflow.request_info(
            application=other_app, user=other["coordinator"], text="Başqa təşkilatın məlumat sorğusu."
        )
    Application.objects.filter(pk=application.pk).update(deleted_at=timezone.now())
    assert close_stale_waiting_info(organization=world["organization"], now=stamp(date(2026, 11, 20))) == 0
    other_app.refresh_from_db()
    assert other_app.status == ApplicationStatus.WAITING_INFO
    # Köhnə versiyanın saxladığı waiting_info + artıq gəlmiş cavab heç vaxt avtomatik bağlanmır.
    event = other_app.events.create(
        organization=other["organization"], actor=other["student"], kind=EventKind.COMMENT, text="Cavab gəlib."
    )
    type(event).objects.filter(pk=event.pk).update(created_at=stamp(date(2026, 11, 17)))
    assert close_stale_waiting_info(organization=other["organization"], now=stamp(date(2026, 11, 30))) == 0


def test_job_is_scheduled_and_unknown_org_command_does_not_close_all(world, application):
    # Test settings intentionally omit Celery; inspect the production schedule's literal entry.
    path = Path(__file__).resolve().parents[3] / "config/settings/components/celery_cache.py"
    assignment = next(
        node
        for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "CELERY_BEAT_SCHEDULE" for t in node.targets)
    )
    entry = next(
        value
        for key, value in zip(assignment.value.keys, assignment.value.values)
        if isinstance(key, ast.Constant) and key.value == "applications-close-stale-waiting-info"
    )
    assert ast.literal_eval(entry) == {
        "task": "applications.close_stale_waiting_info",
        "schedule": 3600.0,
    }
    with pytest.raises(CommandError, match="Təşkilat tapılmadı"):
        call_command("close_stale_waiting_info", org="missing-org")
    application.refresh_from_db()
    assert application.status == ApplicationStatus.WAITING_INFO
