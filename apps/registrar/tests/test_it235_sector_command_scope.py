"""SET LOCAL must cover tenant lookups even when transaction pooling is off."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.db import connection
from django.test import override_settings

import pytest

from apps.registrar.management.commands import repair_it235_sector as command


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("pooled", [False, True])
def test_command_holds_local_scope_through_service_and_restores_it(pooled):
    actor = SimpleNamespace(pk=8444, is_active=True, is_superuser=True)
    organization = SimpleNamespace(pk="526cfa63-4f80-4bba-a7a7-61c8fbb3d918")
    auth = SimpleNamespace(objects=Mock())
    auth.objects.get.return_value = actor
    org_model = SimpleNamespace(objects=Mock())

    def tenant_setting():
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_setting('app.current_org_id', true)")
            return cursor.fetchone()[0] or ""

    before = tenant_setting()

    def assert_lookup(**kwargs):
        assert connection.in_atomic_block
        assert tenant_setting() == organization.pk
        return organization

    def assert_service(**kwargs):
        assert connection.in_atomic_block
        assert tenant_setting() == organization.pk
        assert kwargs["organization"] is organization
        return {"pending": 2, "baseline": "a" * 64}

    org_model.objects.get.side_effect = assert_lookup
    with (
        override_settings(RLS_TRANSACTION_SCOPED=pooled),
        patch.object(command, "get_user_model", return_value=auth),
        patch("django.apps.apps.get_model", return_value=org_model),
        patch.object(command, "run", side_effect=assert_service),
    ):
        command.Command().handle(actor="reviewed-actor", apply=False, expected_baseline="")
    assert not connection.in_atomic_block
    assert tenant_setting() == before
