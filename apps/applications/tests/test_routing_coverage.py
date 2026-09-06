"""Marşrut əhatəsi — QA 2026-09-05 APPLICATIONS-01 reqressiya qapısı.

Aidiyyət bölməsini (ixtisas/fakültə) ÖRTƏN emalçı yoxdursa müraciət heç kimin
inbox-una düşmür və bildiriş getmirdi («qara dəlik»). İndi əhatə açılır: şöbənin
rolunu daşıyan hər kəs görür, audit izində ``coverage=fallback_unscoped`` qeyd olunur.
"""

from __future__ import annotations

import pytest

from apps.applications.services import notify
from apps.applications.services.submit import submit_application
from apps.applications.tests.factories import CREATE, add_member, kind_of, make_tree, make_user, make_world

pytestmark = pytest.mark.django_db


@pytest.fixture()
def world():
    return make_world("app-cov")


def test_covered_specialty_keeps_its_scope(world):
    org = world["organization"]
    application = submit_application(
        organization=org,
        user=world["student"],
        kind=kind_of(world, "diger"),
        subject="QA- örtülən ixtisas",
        body="Koordinatoru olan ixtisasdan göndərilən müraciət mətni.",
    )
    assert application.current_scope_unit_id == world["tree"]["specialty"].pk
    assert notify.handler_recipients(application), "koordinator inbox-u boş olmamalıdır"


def test_uncovered_specialty_falls_back_to_unscoped_route(world):
    org = world["organization"]
    orphan_tree = make_tree(org, tag="c")  # koordinatoru OLMAYAN ixtisas
    student = make_user("app-cov-orphan")
    add_member(org, student, "student", scope_unit=orphan_tree["group"], permissions=CREATE, level=10)

    application = submit_application(
        organization=org,
        user=student,
        kind=kind_of(world, "diger"),
        subject="QA- örtülməyən ixtisas",
        body="Koordinatoru olmayan ixtisasdan göndərilən müraciət mətni.",
    )

    assert application.current_scope_unit_id is None
    recipients = notify.handler_recipients(application)
    assert recipients, "əhatə açılandan sonra şöbənin rol daşıyıcıları görməlidir"
