"""İcazə sərhədləri — kim OXUYUR, kim QƏRAR VERİR.

Bu modul qəsdən mənfi assert-lərlə doludur: müraciət sistemi tələbənin şəxsi
şikayətini daşıyır, ona görə «görməməli olan görmür» yoxlaması «görməli olan
görür»dən vacibdir.
"""

from __future__ import annotations

import pytest

from apps.applications.services import access, submit, workflow
from apps.applications.state_machine import TransitionDenied
from apps.applications.tests.factories import kind_of, make_world, unit_of

pytestmark = pytest.mark.django_db


@pytest.fixture()
def world():
    return make_world("bounds")


@pytest.fixture()
def application(world):
    return submit.submit_application(
        organization=world["organization"],
        user=world["student"],
        kind=kind_of(world, "diger"),
        subject="Fərdi tədris planı sualı",
        body="İxtisas üzrə seçmə fənn blokunu dəyişmək istəyirəm, izah lazımdır.",
    )


def test_sender_reads_but_cannot_decide(world, application):
    assert access.can_view(world["student"], application)
    assert not access.can_act(world["student"], application)
    with pytest.raises(TransitionDenied) as excinfo:
        workflow.resolve(application=application, user=world["student"], text="Özüm həll etdim, bağlayıram.")
    assert excinfo.value.code == "permission.not_handler"


def test_the_coordinator_of_the_students_specialty_can_act(world, application):
    assert application.current_unit.code == "koordinator"
    assert access.can_view(world["coordinator"], application)
    assert access.can_act(world["coordinator"], application)


def test_a_coordinator_of_another_specialty_sees_nothing(world, application):
    assert not access.can_view(world["other_coordinator"], application)
    assert not access.can_act(world["other_coordinator"], application)


def test_a_handler_of_another_unit_cannot_act(world, application):
    """Dekan müraciəti görmür və qərar verə bilmir — o, koordinatorun işidir."""
    assert not access.can_act(world["dean"], application)
    with pytest.raises(TransitionDenied):
        workflow.reject(application=application, user=world["dean"], reason="Bizim səlahiyyətimizdə deyil.")


def test_a_user_without_any_role_sees_nothing(world, application):
    assert not access.can_view(world["outsider"], application)


def test_rim_manage_reads_every_application(world, application):
    """RİM `application.manage` ilə bütün təşkilatı oxuyur — amma bu ƏMƏL deyil."""
    assert access.can_view(world["rim"], application)
    assert not access.can_act(world["rim"], application)


def test_a_watcher_reads_but_never_acts(world, application):
    workflow.mark_seen(application=application, user=world["coordinator"])
    workflow.forward(
        application=application,
        user=world["coordinator"],
        target_unit=unit_of(world, "rim"),
        note="Sistem tərəfli nasazlıq görünür, RİM baxsın.",
        keep_watching=True,
    )
    application.refresh_from_db()

    assert access.can_view(world["coordinator"], application)
    assert not access.can_act(world["coordinator"], application)
    with pytest.raises(TransitionDenied) as excinfo:
        workflow.resolve(application=application, user=world["coordinator"], text="İzləyən kimi bağlayıram.")
    assert excinfo.value.code == "permission.not_handler"

    assert access.can_act(world["rim"], application)


def test_a_user_without_membership_cannot_create(world):
    from apps.applications.tests.factories import make_user

    stranger = make_user("bounds-stranger")
    with pytest.raises(TransitionDenied) as excinfo:
        submit.submit_application(
            organization=world["organization"],
            user=stranger,
            kind=kind_of(world, "diger"),
            subject="Mövzu sətri",
            body="Kifayət qədər uzun müraciət mətni burada yazılıb.",
        )
    assert excinfo.value.code == "permission.denied"


def test_a_kind_closed_to_the_family_is_refused(world):
    with pytest.raises(TransitionDenied) as excinfo:
        submit.submit_application(
            organization=world["organization"],
            user=world["student"],
            kind=kind_of(world, "teqdimat"),
            subject="Kafedraya təqdimat",
            body="Tələbə müəllim növündən istifadə etməyə çalışır — bu bağlı olmalıdır.",
        )
    assert excinfo.value.code == "kind.not_allowed"


def test_short_subject_and_body_are_rejected_server_side(world):
    from django.core.exceptions import ValidationError

    with pytest.raises(ValidationError) as excinfo:
        submit.submit_application(
            organization=world["organization"],
            user=world["student"],
            kind=kind_of(world, "diger"),
            subject="qsa",
            body="qısa",
        )
    assert set(excinfo.value.message_dict) == {"subject", "body"}
