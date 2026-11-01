"""Actual PG transaction/GUC and tenant queries in both worker-pooling modes."""

import io
from unittest.mock import patch

from django.db import connection
from django.test import override_settings

import pytest

from apps.legacy_import.management.commands import repair_qosqar_journals as command
from apps.workload.tests import test_qosqar_journals_repair as fixtures


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("pooled", [False, True])
def test_actual_command_retains_set_local_scope_and_rolls_back_dry_mode(pooled):
    fixture = fixtures.QosqarJournalsTests(methodName="runTest")
    fixture.setUp()
    fixture.prepare()

    def context():
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT current_setting('app.current_org_id',true),current_setting('app.current_user_id',true),current_setting('app.bypass_rls',true)"
            )
            return tuple(value or "" for value in cursor.fetchone())

    original_scope = context()
    original_service = command.repair_qosqar_journals
    seen = []

    def checked_service(**kwargs):
        assert connection.in_atomic_block
        org, user, bypass = context()
        assert org == str(fixture.org.pk)
        assert user == str(fixture.actor.pk)
        assert bypass == "off"
        # Actual tenant ORM query, not a mocked actor/organization lookup.
        assert type(fixture.org).objects.filter(pk=fixture.org.pk, is_active=True).exists()
        result = original_service(**kwargs)
        # Deliberate reversible write proves command dry-run rollback is real.
        type(fixture.org).objects.filter(pk=fixture.org.pk).update(name="DRY_WRITE_MUST_ROLL_BACK")
        seen.append(result)
        return result

    name = fixture.org.name
    try:
        with (
            override_settings(RLS_TRANSACTION_SCOPED=pooled),
            patch.object(
                command.qosqar_modelling_evidence, "load", return_value=(fixture.sections, fixture.mod.SOURCE_SHA)
            ),
            patch.object(command, "repair_qosqar_journals", side_effect=checked_service),
        ):
            command.Command().handle(
                org=fixture.org.slug,
                actor=fixture.actor.username,
                file="source-proof",
                sha256=fixture.mod.SOURCE_SHA,
                baseline="",
                apply=False,
                undo=False,
                stdout=io.StringIO(),
            )
        assert len(seen) == 1
        assert not connection.in_atomic_block
        assert context() == original_scope
        fixture.org.refresh_from_db()
        assert fixture.org.name == name
    finally:
        fixture.doCleanups()
