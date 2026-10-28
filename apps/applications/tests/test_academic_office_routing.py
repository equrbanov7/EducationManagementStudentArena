"""Eyni proqramın məktəb rəhbəri və koordinatoru; kafedra seçimi və məxfilik."""

import pytest

from apps.applications.services import access, notify, queries, submit, workflow
from apps.applications.state_machine import TransitionDenied
from apps.applications.tests.factories import HANDLE, MANAGE, add_member, make_unit, make_user, make_world
from core.constants import OrgUnitType

pytestmark = pytest.mark.django_db


@pytest.fixture
def world():
    world = make_world("academic-office")
    for key, tree in [("deputy", "tree"), ("other_deputy", "other_tree")]:
        user = make_user(key)
        add_member(world["organization"], user, "vice_dean", scope_unit=world[tree]["faculty"], permissions=HANDLE)
        world[key] = user
    return world


def create(world, code):
    return submit.submit_application(
        organization=world["organization"],
        user=world["student"],
        kind=world["kinds"][code],
        subject="Akademik sorğu",
        body="Bu müraciətin düzgün bölmədə araşdırılmasını xahiş edirəm.",
    )


@pytest.mark.parametrize("kind", ["sikayet", "diger"])
def test_office_queue_inbox_counts_and_notifications_have_same_school_program_scope(world, kind):
    app = create(world, kind)
    expected = {world[key].pk for key in ["deputy", "dean", "coordinator"]}
    assert {user.pk for user in notify.handler_recipients(app)} == expected
    for key in ["deputy", "dean", "coordinator", "other_deputy", "other_coordinator"]:
        visible = key in {"deputy", "dean", "coordinator"}
        user = world[key]
        assert access.can_view(user, app) is visible
        assert access.can_act(user, app) is visible
        assert (
            queries.list_applications(organization=app.organization, user=user, tab="inbox").filter(pk=app.pk).exists()
            is visible
        )
        assert queries.handler_inbox_counts(organization=app.organization, user=user)["inbox_open"] == int(visible)


def test_forward_to_real_ancestor_chair_is_scoped_and_notifies_only_matching_head(world):
    app = create(world, "sikayet")
    other_head = make_user("other-chair-head")
    add_member(app.organization, other_head, "chair_head", scope_unit=world["other_tree"]["chair"], permissions=HANDLE)
    workflow.forward(
        application=app,
        user=world["deputy"],
        target_unit=world["units"]["kafedra"],
        note="Kafedranın araşdırması üçün göndərilir.",
    )
    assert app.current_scope_unit_id == world["tree"]["chair"].pk
    assert access.can_act(world["chair_head"], app)
    assert not access.can_view(other_head, app)
    assert {user.pk for user in notify.handler_recipients(app)} == {world["chair_head"].pk}


def test_flat_specialty_requires_explicit_same_school_chair_and_rejects_other_school(world):
    specialty = world["tree"]["specialty"]
    specialty.parent = world["tree"]["faculty"]
    specialty.save()
    world["tree"]["group"].refresh_from_db()
    # Membership fixture caches its group instance before the reparent.
    world["student"].__dict__.pop("_applications_memberships", None)
    app = create(world, "sikayet")
    args = dict(
        application=app,
        user=world["deputy"],
        target_unit=world["units"]["kafedra"],
        note="Kafedra üzrə araşdırılmasını xahiş edirəm.",
    )
    for scope_id in [None, world["other_tree"]["chair"].pk]:
        with pytest.raises(TransitionDenied):
            workflow.forward(**args, scope_id=scope_id)
    workflow.forward(**args, scope_id=world["tree"]["chair"].pk)
    assert app.current_scope_unit_id == world["tree"]["chair"].pk


def test_same_school_other_program_coordinator_is_not_in_the_queue(world):
    unit = make_unit(world["organization"], "Other program", OrgUnitType.SPECIALTY, parent=world["tree"]["faculty"])
    user = make_user("same-school-other-program")
    add_member(world["organization"], user, "program_coordinator", scope_unit=unit, permissions=HANDLE)
    app = create(world, "sikayet")
    assert not access.can_view(user, app)
    assert not queries.list_applications(organization=app.organization, user=user, tab="inbox").exists()
    assert user.pk not in {u.pk for u in notify.handler_recipients(app)}


def test_named_prorector_is_not_opened_to_academic_office(world):
    add_member(world["organization"], world["deputy"], "office-audit", permissions=MANAGE)
    vp = make_user("named-vice")
    add_member(world["organization"], vp, "vice_rector", permissions=HANDLE)
    app = submit.submit_application(
        organization=world["organization"],
        user=world["teacher"],
        kind=world["kinds"]["prorektor"],
        recipient_id=vp.pk,
        subject="Plan sorğusu",
        body="Bu sorğu yalnız konkret prorektora ünvanlanır.",
    )
    for key in ["deputy", "dean", "coordinator"]:
        assert not access.can_view(world[key], app)
        assert (
            not queries.list_applications(organization=app.organization, user=world[key], tab="inbox")
            .filter(pk=app.pk)
            .exists()
        )


def test_academic_program_is_authoritative_when_group_tree_is_inconsistent(world):
    from apps.registrar.models import Curriculum, Program, StudentAcademicRecord

    org = world["organization"]
    program = Program.objects.create(
        organization=org, code="AUTHORITATIVE", name="Program", specialty_unit=world["other_tree"]["specialty"]
    )
    curriculum = Curriculum.objects.create(organization=org, program=program, admission_year=2025)
    StudentAcademicRecord.objects.create(
        organization=org,
        student=world["student"],
        program=program,
        curriculum=curriculum,
        group=world["tree"]["group"],
        admission_year=2025,
    )
    app = create(world, "sikayet")
    assert app.current_scope_unit_id == world["other_tree"]["specialty"].pk
    assert not access.can_view(world["deputy"], app)
    assert access.can_view(world["other_deputy"], app)
    assert access.can_view(world["other_coordinator"], app)


def test_unknown_school_never_opens_academic_queue_to_every_handler(world):
    from apps.applications.tests.factories import CREATE

    user = make_user("unknown-school")
    add_member(world["organization"], user, "student", permissions=CREATE)
    app = submit.submit_application(
        organization=world["organization"],
        user=user,
        kind=world["kinds"]["diger"],
        subject="Əhatəsiz sorğu",
        body="Bu sorğunun məktəb üzrə əlaqəsi hələ müəyyən deyil.",
    )
    assert app.current_scope_unit_id is None
    assert notify.handler_recipients(app) == []
    for key in ["deputy", "coordinator", "other_deputy", "other_coordinator"]:
        assert not access.can_view(world[key], app)
        assert (
            not queries.list_applications(organization=app.organization, user=world[key], tab="inbox")
            .filter(pk=app.pk)
            .exists()
        )
    assert access.can_view(world["rim"], app)


def test_forward_scope_picker_and_endpoint_restrict_choices_to_applicant_school(world):
    from django.urls import reverse

    from apps.applications.payloads import detail_payload
    from apps.applications.tests.test_endpoints import client_for

    app = create(world, "sikayet")
    payload = detail_payload(app, user=world["deputy"])
    assert payload["forward_scopes"] == [{"id": str(world["tree"]["chair"].pk), "name": world["tree"]["chair"].name}]
    client = client_for(world["deputy"], app.organization)
    url = reverse("applications:action", args=[app.pk])
    response = client.post(
        url,
        {
            "action": "forward",
            "target_unit": "kafedra",
            "scope": str(world["other_tree"]["chair"].pk),
            "text": "Başqa məktəbə yönləndirmək cəhdi.",
        },
    )
    assert response.status_code == 400
    response = client.post(
        url,
        {
            "action": "forward",
            "target_unit": "kafedra",
            "scope": str(world["tree"]["chair"].pk),
            "text": "Düzgün kafedraya araşdırılması üçün.",
        },
    )
    assert response.status_code == 200


def test_academic_scope_migration_backfills_legacy_queue_and_is_reversible(world):
    from importlib import import_module

    from django.apps import apps

    from apps.applications.models import Application, ApplicationUnit

    app = create(world, "sikayet")
    Application.objects.filter(pk=app.pk).update(current_scope_unit=world["tree"]["faculty"])
    migration = import_module("apps.applications.migrations.0011_academic_office_scope")
    migration.seed(apps, None)
    migration.seed(apps, None)
    app.refresh_from_db()
    assert app.current_scope_unit_id == world["tree"]["specialty"].pk
    unit = ApplicationUnit.objects.get(pk=app.current_unit_id)
    assert unit.requires_scope and set(unit.role_names) == {"dean", "vice_dean", "program_coordinator", "tutor"}
    migration.unseed(apps, None)
    app.refresh_from_db()
    assert app.current_scope_unit_id == world["tree"]["faculty"].pk
    unit.refresh_from_db()
    assert unit.role_names == ["dean"] and not unit.requires_scope
    migration.seed(apps, None)


def test_existing_blank_scope_is_backfilled_from_official_academic_program(world):
    from importlib import import_module

    from django.apps import apps

    from apps.applications.models import Application
    from apps.registrar.models import Curriculum, Program, StudentAcademicRecord

    app = create(world, "sikayet")
    Application.objects.filter(pk=app.pk).update(current_scope_unit=None, sender_scope_unit=None)
    program = Program.objects.create(
        organization=app.organization,
        code="BACKFILL",
        name="Official program",
        specialty_unit=world["other_tree"]["specialty"],
    )
    curriculum = Curriculum.objects.create(organization=app.organization, program=program, admission_year=2025)
    StudentAcademicRecord.objects.create(
        organization=app.organization,
        student=world["student"],
        program=program,
        curriculum=curriculum,
        group=world["other_tree"]["group"],
        admission_year=2025,
    )
    migration = import_module("apps.applications.migrations.0011_academic_office_scope")
    migration.seed(apps, None)
    app.refresh_from_db()
    assert app.current_scope_unit_id == world["other_tree"]["specialty"].pk
    assert access.can_view(world["other_deputy"], app)
    assert not access.can_view(world["deputy"], app)
    assert (
        queries.list_applications(organization=app.organization, user=world["other_deputy"], tab="inbox")
        .filter(pk=app.pk)
        .exists()
    )


def test_known_school_without_program_is_visible_only_to_that_school_office(world):
    app = submit.submit_application(
        organization=world["organization"],
        user=world["teacher"],
        kind=world["kinds"]["sikayet"],
        subject="Məktəb üzrə sorğu",
        body="Bu sorğunun məktəb rəhbərliyi tərəfindən araşdırılmasını xahiş edirəm.",
    )
    assert app.current_scope_unit_id == world["tree"]["faculty"].pk
    assert access.can_view(world["deputy"], app)
    assert not access.can_view(world["other_deputy"], app)
    assert not access.can_view(world["coordinator"], app)
    assert {user.pk for user in notify.handler_recipients(app)} == {world["dean"].pk, world["deputy"].pk}
