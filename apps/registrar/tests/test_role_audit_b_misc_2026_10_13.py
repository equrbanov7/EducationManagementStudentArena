"""Rol auditi 2026-10-13 B17 — semestr YAZI əməlləri təşkilat səviyyəli əhatə tələb edir.

Əvvəl `semester_actions.py` yalnız açara baxırdı (`semester.open` / `.lock` / `.unlock`): rol
redaktorunda açar kafedra/fakültə (UNIT) roluna verilsə, həmin rol BÜTÜN universitetin semestrini
kilidləyə, açılışını ləğv edə bilərdi. İndi açar ORGANIZATION rolunda olmalıdır; UNIT rolu → 403.
Oxu (`semester.view`) dəyişmir.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

import pytest

from apps.registrar.models import CourseOffering
from apps.syllabus.tests.factories import activate_member, make_academic_stack, make_org
from core.constants import RoleScopeType

User = get_user_model()

pytestmark = pytest.mark.django_db

SEMESTER_KEYS = ["semester.view", "semester.open", "semester.lock", "semester.unlock"]


def _client(user, org):
    client = Client()
    client.force_login(user)
    session = client.session
    session["active_organization"] = org.slug
    session.save()
    return client


@pytest.fixture()
def world():
    org = make_org("rab17")
    stack = make_academic_stack(org, code="RAB17")
    office = User.objects.create_user("rab17_office", "rab17_office@x.test", "pw")
    unit_holder = User.objects.create_user("rab17_unit", "rab17_unit@x.test", "pw")
    activate_member(org, office, "teaching_office_head", permissions=SEMESTER_KEYS, level=80)
    # Redaktorda kafedra roluna BÜTÜN semestr açarları verilib (ssenari — default şablonda yoxdur).
    activate_member(
        org,
        unit_holder,
        "chair_head",
        permissions=SEMESTER_KEYS,
        scope_unit=stack["chair"],
        scope_type=RoleScopeType.UNIT,
        level=70,
    )
    return {"org": org, "stack": stack, "office": office, "unit_holder": unit_holder}


@pytest.mark.parametrize(
    "payload",
    [
        {"action": "send_to_chairs"},
        {"action": "lock"},
        {"action": "unlock", "reason": "Kilid səhvən qoyulub, yenidən açılır."},
        {"action": "generate", "semester_number": "1"},
        {"action": "remind_readiness"},
        {"action": "set_current"},
    ],
)
def test_unit_scoped_key_holder_gets_403(world, payload):
    data = {"period": str(world["stack"]["period"].pk), **payload}
    response = _client(world["unit_holder"], world["org"]).post(reverse("registrar:semester_action"), data)
    assert response.status_code == 403, response.content
    assert response.json()["error"] == "forbidden"


def test_unit_scoped_holder_cannot_cancel_offering(world):
    stack = world["stack"]
    offering = CourseOffering.objects.create(
        organization=world["org"], subject=stack["subject"], period=stack["period"], group=stack["group"]
    )
    response = _client(world["unit_holder"], world["org"]).post(
        reverse("registrar:semester_action"),
        {"action": "cancel_offering", "id": str(offering.pk), "reason": "Ləğv səbəbi kifayət qədər uzundur."},
    )
    assert response.status_code == 403
    offering.refresh_from_db()
    assert offering.is_active is True


def test_org_wide_holder_still_acts(world):
    response = _client(world["office"], world["org"]).post(
        reverse("registrar:semester_action"),
        {"action": "send_to_chairs", "period": str(world["stack"]["period"].pk)},
    )
    assert response.status_code == 200, response.content
    assert response.json()["opening_status"] == "sent"
