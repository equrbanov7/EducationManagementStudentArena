"""Sahib 2026-10-29: «Laborantlara bu hissəni aç, hər laborant özünə aid olan kafedranın yükləri görsün və
editləyə də bilsin».

Nəyi qoruyur (DEFOLT rol şablonu ilə — signal təşkilat yaradılanda əkir):

1. Laborant rolunda ``workload.manage`` + ``workload.distribute`` var (şablon + idempotent tətbiq).
2. «Yük bölgüsü» menyusu açılır, kafedra siyahısında YALNIZ öz kafedrası var.
3. Yazı qapısı (``scoping``) öz kafedrasını buraxır, başqa kafedranı rədd edir.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

import pytest

from apps.organizations.default_roles_university import UNIVERSITY_ROLES
from apps.organizations.models import Membership, Organization, OrgUnit
from apps.organizations.permissions_lab_workload import LAB_WORKLOAD_GRANTS, apply_lab_workload_grants
from apps.workload.services.scoping import can_distribute_chair, can_manage_chair, resolve_actor
from core.constants import OrganizationType, OrgUnitType
from core.rls import bypass_rls

pytestmark = pytest.mark.django_db

User = get_user_model()


def test_template_grants_lab_assistant_workload_keys():
    role = next(role for role in UNIVERSITY_ROLES if role["name"] == "lab_assistant")
    for key in LAB_WORKLOAD_GRANTS:
        assert key in role["permissions"]
    before = list(role["permissions"])
    apply_lab_workload_grants(UNIVERSITY_ROLES)
    assert role["permissions"] == before  # idempotent


@pytest.fixture
def world():
    owner = User.objects.create_user("lw_owner", "lw_owner@x.test", "pw")
    laborant = User.objects.create_user("lw_lab", "lw_lab@x.test", "pw")
    with bypass_rls():
        org = Organization.objects.create(
            name="LW Univ", slug="lw-univ", org_type=OrganizationType.UNIVERSITY, owner=owner, status="active"
        )
        faculty = OrgUnit.objects.create(organization=org, name="Fakültə", slug="lw-f", unit_type=OrgUnitType.FACULTY)
        chair = OrgUnit.objects.create(
            organization=org, name="Marketinq", slug="lw-c1", unit_type=OrgUnitType.CHAIR, parent=faculty
        )
        other_chair = OrgUnit.objects.create(
            organization=org, name="Riyaziyyat", slug="lw-c2", unit_type=OrgUnitType.CHAIR, parent=faculty
        )
        Membership.objects.create(
            user=laborant,
            organization=org,
            role=org.roles.get(name="lab_assistant"),
            scope_unit=chair,
            is_primary=True,
            is_active=True,
        )
    profile = laborant.profile
    profile.role = "lab_assistant"
    profile.save(update_fields=["role"])
    return {"org": org, "chair": chair, "other_chair": other_chair, "laborant": laborant}


def test_lab_assistant_manages_only_own_chair(world):
    actor = resolve_actor(world["laborant"], world["org"])
    assert can_manage_chair(actor, world["chair"].pk)
    assert can_distribute_chair(actor, world["chair"].pk)
    assert not can_manage_chair(actor, world["other_chair"].pk)
    assert not can_distribute_chair(actor, world["other_chair"].pk)


def test_lab_assistant_sees_distribution_section_with_own_chair(world):
    client = Client()
    client.force_login(world["laborant"])
    response = client.get(reverse("accounts:profile"), {"section": "workload-distribution"})
    assert response.status_code == 200
    section = response.context["workload_distribution_section"]
    assert section["has_access"] is True
    assert [str(chair["id"]) for chair in section["chairs"]] == [str(world["chair"].pk)]


def test_lab_assistant_without_chair_cannot_manage_any_chair(world):
    with bypass_rls():
        Membership.objects.filter(user=world["laborant"], organization=world["org"]).update(scope_unit=None)
    actor = resolve_actor(world["laborant"], world["org"])
    assert not can_manage_chair(actor, world["chair"].pk)
    assert not can_distribute_chair(actor, world["chair"].pk)


def test_lab_assistant_foreign_chair_write_is_denied(world):
    client = Client()
    client.force_login(world["laborant"])
    response = client.post(
        reverse("workload:action"),
        {"action": "create_task", "chair": str(world["other_chair"].pk), "academic_year": "2027/2028"},
    )
    assert response.status_code == 403


def test_full_catalogue_is_searchable_beyond_old_two_thousand_cap(world):
    from apps.registrar.models import Subject

    with bypass_rls():
        Subject.objects.bulk_create(
            [Subject(organization=world["org"], code=f"LW{i:04}", name=f"Kataloq {i:04}") for i in range(2001)]
        )
        last = Subject.objects.create(organization=world["org"], code="LW_LAST", name="Sonuncu fənn")
    client = Client()
    client.force_login(world["laborant"])
    response = client.get(reverse("workload:options"), {"chair": str(world["chair"].pk)})
    assert response.status_code == 200
    subjects = response.json()["subjects"]
    assert len(subjects) == 2002
    assert subjects[-1]["id"] == str(last.pk)


def test_migration_grants_once_preserving_other_permissions(world):
    import importlib

    from django.apps import apps

    migration = importlib.import_module("apps.organizations.migrations.0077_lab_assistant_workload_distribution")
    with bypass_rls():
        role = world["org"].roles.get(name="lab_assistant")
        role.permissions = ["workload.view", "custom.keep"]
        role.save(update_fields=["permissions"])
        migration.forward(apps, None)
        role.refresh_from_db()
        once = list(role.permissions)
        assert {"workload.manage", "workload.distribute", "custom.keep"} <= set(once)
        migration.forward(apps, None)
        role.refresh_from_db()
        assert role.permissions == once
        migration.backward(apps, None)
        role.refresh_from_db()
        assert role.permissions == ["workload.view", "custom.keep"]
