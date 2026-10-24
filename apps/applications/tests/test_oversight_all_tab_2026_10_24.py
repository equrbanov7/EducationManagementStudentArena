"""«Bütün müraciətlər» tabı — RİM təşkilatın HƏR müraciətini görür (sahib 2026-10-24).

Qapı: ``access.can_oversee`` = ``application.view_all`` (RİM əməkdaşı) və ya ``application.manage``
(RİM rəhbəri / rektorat), superuser, təşkilat sahibi. Bu YALNIZ OXUDUR — əməl, daxili qeyd və
«Yeni → Baxılır» yan-təsiri yoxdur. Digərləri tabı görmür, URL-i əl ilə yazsa 403 alır.
"""

from __future__ import annotations

import importlib
import json

from django.apps import apps as django_apps
from django.db import connection
from django.test import Client, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

import pytest

from apps.applications.constants import ApplicationStatus
from apps.applications.models import ApplicationEvent
from apps.applications.services import access, oversight, queries, submit, workflow
from apps.applications.tests.factories import add_member, kind_of, make_org, make_tree, make_user, make_world
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


def _submit(world, user, code, subject):
    return submit.submit_application(
        organization=world["organization"],
        user=user,
        kind=kind_of(world, code),
        subject=subject,
        body=f"{subject} — nəzarət tabının testi üçün kifayət qədər uzun mətn.",
    )


@pytest.fixture()
def world():
    world = make_world("ovs")
    organization = world["organization"]
    rim_staff = make_user("ovs-rim-staff")
    add_member(organization, rim_staff, "rim_staff", permissions=VIEW_ALL, level=60)
    student_b = make_user("ovs-student-b")
    add_member(
        organization,
        student_b,
        "student",
        scope_unit=world["other_tree"]["group"],
        permissions=["application.create"],
        level=10,
    )
    world.update({"rim_staff": rim_staff, "student_b": student_b})
    world["apps"] = {
        # tələbə (a ağacı) → koordinator (ixtisas a)
        "koordinator": _submit(world, world["student"], "diger", "Seçmə fənn bloku"),
        # tələbə (a ağacı) → Tələbə Xidmətləri Mərkəzi (mərkəzi şöbə)
        "telebe": _submit(world, world["student"], "transkript", "Transkript lazımdır"),
        # müəllim (kafedra a) → kafedra müdirliyi
        "kafedra": _submit(world, world["teacher"], "teqdimat", "Kafedraya təqdimat"),
        # tələbə (b ağacı) → dekanlıq (fakültə b)
        "dekan": _submit(world, student_b, "sikayet", "Dərs prosesi ilə bağlı şikayət"),
    }
    return world


def _ids(payload):
    return {row["id"] for row in payload["results"]}


def _list(world, actor, **params):
    client = client_for(world[actor], world["organization"])
    return client.get(reverse("applications:list"), {"tab": "all", "stat": "all", **params})


# ── Görünüş: RİM hər şöbənin müraciətini görür ─────────────────────────────
@pytest.mark.parametrize("actor", ["rim_staff", "rim"])
def test_overseer_sees_every_application_across_departments(world, actor):
    response = _list(world, actor)
    assert response.status_code == 200
    payload = body(response)
    expected = {str(application.pk) for application in world["apps"].values()}
    assert _ids(payload) == expected
    assert {row["current_unit"]["code"] for row in payload["results"]} == set(world["apps"])
    assert payload["counts"]["all"] == len(expected)


def test_superuser_and_owner_are_overseers(world):
    organization = world["organization"]
    superuser = make_user("ovs-root")
    superuser.is_superuser = True
    superuser.save(update_fields=["is_superuser"])
    assert access.can_oversee(superuser, organization)
    assert access.can_oversee(organization.owner, organization)


def test_department_filter_narrows_to_the_routed_unit(world):
    payload = body(_list(world, "rim_staff", unit="dekan"))
    assert _ids(payload) == {str(world["apps"]["dekan"].pk)}
    assert body(_list(world, "rim_staff", unit="yoxdur"))["results"] == []


def test_sender_unit_filter_covers_the_whole_subtree(world):
    faculty_a = world["tree"]["faculty"]
    payload = body(_list(world, "rim_staff", sender_unit=str(faculty_a.pk)))
    # Fakültə a: tələbənin qrupu və müəllimin kafedrası onun alt-ağacındadır; b ağacı düşmür.
    assert _ids(payload) == {str(world["apps"][code].pk) for code in ("koordinator", "telebe", "kafedra")}

    chair_b = world["other_tree"]["chair"]
    assert _ids(body(_list(world, "rim_staff", sender_unit=str(chair_b.pk)))) == {str(world["apps"]["dekan"].pk)}


def test_sender_unit_filter_combines_with_department_and_status(world):
    faculty_a = world["tree"]["faculty"]
    payload = body(_list(world, "rim_staff", sender_unit=str(faculty_a.pk), unit="kafedra"))
    assert _ids(payload) == {str(world["apps"]["kafedra"].pk)}
    assert body(_list(world, "rim_staff", stat="closed"))["results"] == []


def test_foreign_or_malformed_sender_unit_yields_nothing(world):
    foreign = make_tree(make_org("ovs-foreign"), "x")["faculty"]
    assert body(_list(world, "rim_staff", sender_unit=str(foreign.pk)))["results"] == []
    response = _list(world, "rim_staff", sender_unit="not-a-uuid")
    assert response.status_code == 200
    assert body(response)["results"] == []


def test_all_tab_query_count_does_not_grow_with_rows(world):
    client = client_for(world["rim_staff"], world["organization"])
    url = reverse("applications:list")
    params = {"tab": "all", "stat": "all", "sender_unit": str(world["tree"]["faculty"].pk)}

    def measure():
        client.get(url, params)  # isinmə (sessiya, proses keşləri)
        with CaptureQueriesContext(connection) as ctx:
            response = client.get(url, params)
        return len(body(response)["results"]), len(ctx.captured_queries)

    rows_before, queries_before = measure()
    for index in range(6):
        _submit(world, world["teacher"], "teqdimat", f"Əlavə təqdimat {index}")
    rows_after, queries_after = measure()
    assert (rows_before, rows_after) == (3, 9)
    assert queries_before == queries_after


# ── Qapı: adi istifadəçi tabı görmür, URL-də 403 alır ──────────────────────
@pytest.mark.parametrize("actor", ["student", "teacher", "dean", "coordinator", "staff", "outsider"])
def test_non_overseers_are_denied_the_all_tab(world, actor):
    assert not access.can_oversee(world[actor], world["organization"])
    response = _list(world, actor)
    assert response.status_code == 403
    assert body(response)["ok"] is False
    # Servis qatı da fail-closed: tab sorğusu birbaşa çağırılsa da boşdur.
    queryset = queries.list_applications(organization=world["organization"], user=world[actor], tab="all", stat="all")
    assert not queryset.exists()
    assert "all" not in queries.tab_counts(organization=world["organization"], user=world[actor])


def test_filters_never_widen_an_ordinary_tab(world):
    """Şöbə süzgəci başqa tabda görünən dəsti yalnız DARALDIR."""
    client = client_for(world["dean"], world["organization"])
    payload = body(client.get(reverse("applications:list"), {"tab": "inbox", "stat": "all", "unit": "rim"}))
    assert payload["results"] == []


# ── Detal: yalnız oxu ──────────────────────────────────────────────────────
def test_overseer_opens_any_application_read_only(world):
    application = world["apps"]["dekan"]
    client = client_for(world["rim_staff"], world["organization"])
    response = client.get(reverse("applications:detail", kwargs={"application_id": application.pk}))
    assert response.status_code == 200
    detail = body(response)["application"]
    assert detail["allowed_actions"] == []
    assert detail["viewer"]["is_handler"] is False
    # Oxumaq «Yeni → Baxılır» keçidini TƏTİKLƏMİR (o, yalnız qərar verən emalçınındır).
    application.refresh_from_db()
    assert application.status == ApplicationStatus.SUBMITTED.value

    denied = client.post(
        reverse("applications:action", kwargs={"application_id": application.pk}),
        {"action": "resolve", "text": "Nəzarətçi bu müraciəti həll edə bilməz, yoxlama."},
    )
    assert denied.status_code == 403
    application.refresh_from_db()
    assert application.status == ApplicationStatus.SUBMITTED.value


def test_view_all_does_not_reveal_internal_notes(world):
    application = world["apps"]["koordinator"]
    workflow.mark_seen(application=application, user=world["coordinator"])
    workflow.add_comment(
        application=application,
        user=world["coordinator"],
        text="Daxili qeyd: yalnız emalçılar görməlidir.",
        is_internal=True,
    )
    assert ApplicationEvent.objects.filter(application=application, is_internal=True).exists()

    def internal_events(actor):
        client = client_for(world[actor], world["organization"])
        detail = body(client.get(reverse("applications:detail", kwargs={"application_id": application.pk})))
        return [event for event in detail["application"]["events"] if event["is_internal"]]

    assert internal_events("rim_staff") == []
    assert internal_events("rim")  # `application.manage` daxili qeydləri görür (mövcud qayda)


# ── Kataloq + kabinet bölməsi ──────────────────────────────────────────────
def test_catalog_gives_overseers_every_kind_for_the_filter(world):
    payload = body(client_for(world["rim_staff"], world["organization"]).get(reverse("applications:catalog")))
    assert payload["can_oversee"] is True
    assert {kind["code"] for kind in payload["filter_kinds"]} == set(world["kinds"])

    student_payload = body(client_for(world["student"], world["organization"]).get(reverse("applications:catalog")))
    assert student_payload["can_oversee"] is False
    assert "filter_kinds" not in student_payload


def test_sender_unit_options_are_grouped_and_only_for_overseers(world):
    organization = world["organization"]
    groups = oversight.sender_unit_options(world["rim_staff"], organization)
    names = {unit["name"] for group in groups for unit in group["units"]}
    assert {"Fakültə a", "Fakültə b", "Kafedra a", "Kafedra b"} <= names
    assert "Qrup a" not in names  # qrup/ixtisas siyahını şişirtmir — alt-ağac süzgəci onları əhatə edir
    assert oversight.sender_unit_options(world["dean"], organization) == []


@override_settings(UNIVERSITY_MODE=True)
def test_cabinet_section_shows_the_tab_only_to_overseers(world):
    url = reverse("accounts:profile_section_fragment", kwargs={"section": "applications"})

    def html(actor):
        response = client_for(world[actor], world["organization"]).get(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        assert response.status_code == 200
        return response.json()["html"]

    overseer = html("rim_staff")
    assert 'data-apx-tab="all"' in overseer
    assert "data-apx-oversight-unit" in overseer
    assert "data-apx-oversight-sender" in overseer
    assert "applications_oversight.js" in overseer
    assert 'value="dekan"' in overseer

    for actor in ("student", "dean"):
        ordinary = html(actor)
        assert 'data-apx-tab="all"' not in ordinary
        assert "data-apx-oversight" not in ordinary


# ── Mövcud tenantlar: miqrasiya ────────────────────────────────────────────
def test_migration_grants_view_all_to_existing_rim_staff_and_trustee_roles(world):
    migration = importlib.import_module("apps.applications.migrations.0006_grant_view_all_to_rim_staff")
    organization = world["organization"]
    roles = {name: Role.objects.get(organization=organization, name=name) for name in ("rim_staff", "trustee")}
    Role.objects.filter(pk__in=[role.pk for role in roles.values()]).update(permissions=["exam.view"])
    dean = Role.objects.get(organization=organization, name="dean")
    dean_before = list(dean.permissions)

    migration.forward(django_apps, None)
    migration.forward(django_apps, None)  # idempotent
    for role in roles.values():
        role.refresh_from_db()
        assert role.permissions == ["exam.view", "application.view_all"], role.name
    dean.refresh_from_db()
    assert dean.permissions == dean_before  # başqa rollara toxunulmur

    migration.backward(django_apps, None)
    for role in roles.values():
        role.refresh_from_db()
        assert role.permissions == ["exam.view"], role.name
