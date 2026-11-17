"""organizations/0083: laborant «Kafedra müdirliyi» şöbəsinin emalçısıdır (sahib 2026-11-17)."""

import importlib

from django.apps import apps as django_apps

import pytest

from apps.applications.constants import DEFAULT_UNIT_SEED

migration = importlib.import_module("apps.organizations.migrations.0083_lab_assistant_chair_applications")


def test_seed_lists_lab_assistant_as_chair_handler():
    unit = next(row for row in DEFAULT_UNIT_SEED if row["code"] == "kafedra")
    assert unit["handler_role_names"] == ["chair_head", "lab_assistant"]


@pytest.mark.django_db
def test_migration_adds_role_and_permission_idempotently():
    Organization = django_apps.get_model("organizations", "Organization")
    Role = django_apps.get_model("organizations", "Role")
    ApplicationUnit = django_apps.get_model("applications", "ApplicationUnit")
    owner = django_apps.get_model("auth", "User").objects.create(username="owner0083")
    org = Organization.objects.create(name="Lab Org", slug="lab-org-0083", owner=owner)
    role, _ = Role.objects.get_or_create(
        organization=org, name="lab_assistant", defaults={"permissions": ["journal.view"]}
    )
    role.permissions = ["journal.view"]
    role.save()
    unit = ApplicationUnit.objects.create(
        organization=org,
        code="kafedra",
        name="Kafedra müdirliyi",
        handler_role_names=["chair_head"],
        resolve_by="chair",
    )
    for _ in range(2):
        migration.forward(django_apps, None)
    role.refresh_from_db()
    unit.refresh_from_db()
    assert role.permissions.count("application.handle") == 1
    assert unit.handler_role_names == ["chair_head", "lab_assistant"]
    migration.backward(django_apps, None)
    role.refresh_from_db()
    unit.refresh_from_db()
    assert "application.handle" not in role.permissions
    assert unit.handler_role_names == ["chair_head"]
