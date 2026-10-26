"""RİM hər müraciəti cavablandırır (sahib 2026-10-26).

Əvvəl: RİM əməkdaşı (`rim_staff`) «Bütün müraciətlər»i YALNIZ OXUYURDU və RİM şöbəsinin özünün
emalçısı da deyildi (yalnız `ikt_rehber`) — «Texniki problem» müraciətinə belə cavab verə bilmirdi;
RİM rəhbəri isə başqa şöbənin müraciətini görürdü, amma cavab verə bilmirdi.

İndi: RİM şöbəsinin emalçı rolları (kataloqdan — `ikt_rehber` + `rim_staff`) HƏR AÇIQ müraciətə
cavab yazır, həll edir, yönləndirir; sahibə bildiriş, müraciəti saxlayan şöbəyə «RİM cavab verdi»
bildirişi və audit sətri gedir. Açmaq «Yeni → Baxılır» etmir; ilk qərar «Baxılır»ı özü yazır.
"""

from __future__ import annotations

import importlib
import json

from django.apps import apps as django_apps
from django.test import Client
from django.urls import reverse

import pytest

from apps.applications.constants import RESPONDER_UNIT_CODE, ApplicationStatus, EventKind
from apps.applications.models import ApplicationEvent, ApplicationUnit
from apps.applications.services import access, submit, workflow
from apps.applications.state_machine import TransitionDenied
from apps.applications.tests.factories import MANAGE, add_member, kind_of, make_user, make_world, unit_of
from apps.audit.models import AuditLog
from apps.notifications.models import InAppNotification, NotificationType
from apps.organizations.models import Role

pytestmark = pytest.mark.django_db

VIEW_ALL = ["application.create", "application.view_all"]


def client_for(user, organization):
    client = Client()
    client.force_login(user)
    session = client.session
    session["active_organization"] = organization.slug
    session.save()
    return client


def body(response):
    return json.loads(response.content.decode())


@pytest.fixture()
def world():
    world = make_world("rimans")
    organization = world["organization"]
    rim_staff = make_user("rimans-rim-staff")
    add_member(organization, rim_staff, "rim_staff", permissions=VIEW_ALL + ["application.handle"], level=60)
    trustee = make_user("rimans-trustee")
    add_member(organization, trustee, "trustee", permissions=VIEW_ALL, level=78)
    vice_rector = make_user("rimans-vice-rector")
    add_member(organization, vice_rector, "vice_rector", permissions=MANAGE, level=90)
    world.update({"rim_staff": rim_staff, "trustee": trustee, "vice_rector": vice_rector})
    return world


@pytest.fixture()
def dean_application(world):
    """Tələbə → dekanlıq (fakültə a): RİM-in şöbəsi DEYİL."""
    return submit.submit_application(
        organization=world["organization"],
        user=world["student"],
        kind=kind_of(world, "sikayet"),
        subject="Dərs prosesi ilə bağlı şikayət",
        body="Dərs prosesi ilə bağlı şikayət — RİM cavabı testi üçün kifayət qədər uzun mətn.",
    )


def _notifications(user):
    return list(
        InAppNotification.objects.filter(recipient=user, notification_type=NotificationType.APPLICATION).values_list(
            "title", flat=True
        )
    )


# ── İcazə ──────────────────────────────────────────────────────────────────
def test_seeded_rim_unit_lists_both_rim_roles(world):
    assert set(unit_of(world, RESPONDER_UNIT_CODE).role_names) == {"ikt_rehber", "rim_staff"}


@pytest.mark.parametrize("actor", ["rim_staff", "rim"])
def test_rim_can_act_on_another_departments_application(world, dean_application, actor):
    user = world[actor]
    assert access.is_universal_responder(user, world["organization"])
    assert access.can_view(user, dean_application)
    assert access.can_act(user, dean_application)
    assert access.can_see_internal(user, dean_application)
    assert not access.is_current_handler(user, dean_application)


@pytest.mark.parametrize("actor", ["trustee", "vice_rector", "coordinator", "teacher", "outsider"])
def test_non_rim_roles_do_not_get_the_answer_right(world, dean_application, actor):
    user = world[actor]
    assert not access.is_universal_responder(user, world["organization"])
    assert not access.can_act(user, dean_application)
    with pytest.raises(TransitionDenied):
        workflow.resolve(application=dean_application, user=user, text="Səlahiyyətsiz cavab cəhdi, yoxlama.")


def test_right_follows_the_catalog_not_the_role_name(world, dean_application):
    """Tenant `rim_staff`-ı RİM şöbəsindən çıxarsa, cavab hüququ da gedir."""
    unit = unit_of(world, RESPONDER_UNIT_CODE)
    ApplicationUnit.objects.filter(pk=unit.pk).update(handler_role_names=["ikt_rehber"])
    staff = make_user("rimans-rim-staff-2")
    add_member(world["organization"], staff, "rim_staff", permissions=VIEW_ALL, level=60)
    world["organization"].refresh_from_db()  # şöbə keşi təşkilat obyektindədir
    application = type(dean_application).objects.select_related("organization").get(pk=dean_application.pk)
    assert not access.can_act(staff, application)


def test_closed_application_cannot_be_answered(world, dean_application):
    workflow.resolve(application=dean_application, user=world["rim_staff"], text="Problem aradan qaldırıldı.")
    dean_application.refresh_from_db()
    workflow.close(application=dean_application, user=world["student"])
    dean_application.refresh_from_db()
    assert not access.can_act(world["rim_staff"], dean_application)


# ── Detal: açmaq «Yeni»ni dəyişmir, amma cavab düymələri var ───────────────
def test_opening_does_not_mark_seen_but_offers_reply_actions(world, dean_application):
    client = client_for(world["rim_staff"], world["organization"])
    response = client.get(reverse("applications:detail", kwargs={"application_id": dean_application.pk}))
    assert response.status_code == 200
    detail = body(response)["application"]
    assert {"resolve", "add_comment", "forward", "request_info", "reject"} <= set(detail["allowed_actions"])
    assert detail["viewer"]["is_handler"] is True
    dean_application.refresh_from_db()
    assert dean_application.status == ApplicationStatus.SUBMITTED.value


def test_trustee_still_reads_only(world, dean_application):
    client = client_for(world["trustee"], world["organization"])
    detail = body(client.get(reverse("applications:detail", kwargs={"application_id": dean_application.pk})))
    assert detail["application"]["allowed_actions"] == []


# ── Cavab: sahibə + şöbəyə bildiriş, audit ─────────────────────────────────
def test_rim_resolves_a_new_application_with_notifications_and_audit(
    world, dean_application, django_capture_on_commit_callbacks
):
    InAppNotification.objects.all().delete()
    client = client_for(world["rim_staff"], world["organization"])
    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            reverse("applications:action", kwargs={"application_id": dean_application.pk}),
            {"action": "resolve", "text": "Problem yoxlanıldı və düzəldildi, yenidən baxa bilərsiniz."},
        )
    assert response.status_code == 200, response.content
    dean_application.refresh_from_db()
    assert dean_application.status == ApplicationStatus.RESOLVED.value
    kinds = list(
        ApplicationEvent.objects.filter(application=dean_application)
        .order_by("created_at")
        .values_list("kind", flat=True)
    )
    assert kinds == [EventKind.SUBMITTED, EventKind.SEEN, EventKind.RESOLVED]

    assert any("həll olundu" in title for title in _notifications(world["student"]))
    assert any("RİM" in title for title in _notifications(world["dean"]))
    assert not _notifications(world["rim_staff"])  # aktor özünə bildiriş almır

    audit_rows = AuditLog.objects.filter(resource_type="application", resource_id=str(dean_application.pk))
    assert any((row.changes or {}).get("responder_unit") == RESPONDER_UNIT_CODE for row in audit_rows)


def test_rim_public_reply_notifies_sender_and_department(world, dean_application, django_capture_on_commit_callbacks):
    InAppNotification.objects.all().delete()
    with django_capture_on_commit_callbacks(execute=True):
        workflow.add_comment(application=dean_application, user=world["rim"], text="Hesabınız bərpa olundu.")
    assert _notifications(world["student"])
    assert any("RİM" in title for title in _notifications(world["dean"]))
    dean_application.refresh_from_db()
    assert dean_application.status == ApplicationStatus.SUBMITTED.value  # qeyd statusu dəyişmir


def test_rim_internal_note_stays_internal(world, dean_application, django_capture_on_commit_callbacks):
    InAppNotification.objects.all().delete()
    with django_capture_on_commit_callbacks(execute=True):
        workflow.add_comment(
            application=dean_application, user=world["rim_staff"], text="Daxili: log-a baxıldı.", is_internal=True
        )
    assert not _notifications(world["student"])
    assert ApplicationEvent.objects.filter(application=dean_application, is_internal=True).exists()


def test_department_handler_reply_does_not_ping_itself(world, dean_application, django_capture_on_commit_callbacks):
    workflow.mark_seen(application=dean_application, user=world["dean"])
    InAppNotification.objects.all().delete()
    with django_capture_on_commit_callbacks(execute=True):
        workflow.resolve(application=dean_application, user=world["dean"], text="Dekanlıq məsələni həll etdi.")
    assert not any("RİM" in title for title in _notifications(world["dean"]))


def test_rim_forward_notifies_the_previous_department(world, dean_application, django_capture_on_commit_callbacks):
    InAppNotification.objects.all().delete()
    with django_capture_on_commit_callbacks(execute=True):
        workflow.forward(
            application=dean_application,
            user=world["rim_staff"],
            target_unit=unit_of(world, "telebe"),
            note="Bu məsələ Tələbə Xidmətləri Mərkəzinə aiddir.",
        )
    dean_application.refresh_from_db()
    assert dean_application.current_unit.code == "telebe"
    assert any("RİM" in title for title in _notifications(world["dean"]))


def test_too_short_reply_rolls_back_the_implicit_review(world, dean_application):
    with pytest.raises(TransitionDenied):
        workflow.resolve(application=dean_application, user=world["rim_staff"], text="qısa")
    dean_application.refresh_from_db()
    assert dean_application.status == ApplicationStatus.SUBMITTED.value
    assert not ApplicationEvent.objects.filter(application=dean_application, kind=EventKind.SEEN).exists()


# ── RİM-in öz növbəsi: əməkdaş da «Mənə gələnlər»dədir ─────────────────────
def test_rim_staff_receives_technical_applications_in_inbox(world):
    application = submit.submit_application(
        organization=world["organization"],
        user=world["teacher"],
        kind=kind_of(world, "texniki"),
        subject="Jurnala giriş yoxdur",
        body="Jurnala daxil ola bilmirəm, səhifə xəta verir — texniki problem.",
    )
    client = client_for(world["rim_staff"], world["organization"])
    payload = body(client.get(reverse("applications:list"), {"tab": "inbox", "stat": "all"}))
    assert str(application.pk) in {row["id"] for row in payload["results"]}
    assert access.is_current_handler(world["rim_staff"], application)


# ── Mövcud tenantlar: miqrasiya ────────────────────────────────────────────
def test_migration_adds_rim_staff_to_unit_and_handle_key(world):
    migration = importlib.import_module("apps.applications.migrations.0007_rim_staff_answers_every_application")
    organization = world["organization"]
    unit = unit_of(world, RESPONDER_UNIT_CODE)
    ApplicationUnit.objects.filter(pk=unit.pk).update(handler_role_names=["ikt_rehber"])
    role = Role.objects.get(organization=organization, name="rim_staff")
    Role.objects.filter(pk=role.pk).update(permissions=["application.view_all"])
    dean = unit_of(world, "dekan")
    dean_roles_before = list(dean.role_names)

    migration.forward(django_apps, None)
    migration.forward(django_apps, None)  # idempotent
    unit.refresh_from_db()
    role.refresh_from_db()
    assert unit.handler_role_names == ["ikt_rehber", "rim_staff"]
    assert role.permissions == ["application.view_all", "application.handle"]
    dean.refresh_from_db()
    assert dean.role_names == dean_roles_before  # başqa şöbəyə toxunulmur

    migration.backward(django_apps, None)
    unit.refresh_from_db()
    role.refresh_from_db()
    assert unit.handler_role_names == ["ikt_rehber"]
    assert role.permissions == ["application.view_all"]
