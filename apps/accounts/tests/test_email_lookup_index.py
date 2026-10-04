"""The full lookup index keeps canonical identity probes and collision guards indexable."""

import importlib
import json

from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection

import pytest

from apps.accounts.identity import canonical_identity_queryset

pytestmark = [pytest.mark.postgres, pytest.mark.django_db(transaction=True)]
migration = importlib.import_module("apps.accounts.migrations.0029_identity_email_lookup_index")


@pytest.fixture(autouse=True)
def require_postgres():
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL expression index")


def test_unconditional_canonical_email_probe_can_use_lookup_index():
    query = canonical_identity_queryset(get_user_model().objects.all(), "email", "missing@example.com")
    with connection.cursor() as cursor:
        cursor.execute("SET enable_seqscan = off")
    try:
        plan = query.explain(format="json")
        assert migration.INDEX in plan
        assert json.loads(plan)[0]["Plan"]["Node Type"] in {"Index Scan", "Bitmap Heap Scan"}
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET enable_seqscan")


def test_new_index_is_selected_without_planner_overrides_for_blank_email_pool():
    user = get_user_model()
    user.objects.bulk_create([user(username=f"lookup_pool_{i}", email="") for i in range(5000)])
    with connection.schema_editor(atomic=False) as editor:
        migration.remove_index(None, editor)
        migration.add_index(None, editor)
    # The production login orders and limits results. Without fresh expression
    # statistics that combination can prefer scanning the primary key.
    query = canonical_identity_queryset(user.objects.all(), "email", "absent@example.com").order_by("pk")[:2]
    assert migration.INDEX in query.explain(format="json")


def test_migration_is_repeatable_reversible_and_recovers_failed_build():
    user = get_user_model()
    user.objects.create_user("blank_email_one", email="")
    user.objects.create_user("blank_email_two", email="")
    with connection.schema_editor(atomic=False) as editor:
        migration.remove_index(None, editor)
        try:
            # Duplicate blank emails deliberately make a concurrent UNIQUE build
            # fail, leaving an invalid index just as an interrupted build would.
            with connection.cursor() as cursor:
                with pytest.raises(IntegrityError):
                    cursor.execute(f'CREATE UNIQUE INDEX CONCURRENTLY "{migration.INDEX}" ON auth_user(email)')
                cursor.execute("SELECT indisvalid FROM pg_index WHERE indexrelid=to_regclass(%s)", [migration.INDEX])
                assert cursor.fetchone() == (False,)
            migration.add_index(None, editor)
            migration.add_index(None, editor)
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT indisvalid, indisunique, indpred IS NULL FROM pg_index " "WHERE indexrelid=to_regclass(%s)",
                    [migration.INDEX],
                )
                assert cursor.fetchone() == (True, False, True)
            migration.remove_index(None, editor)
            migration.remove_index(None, editor)
        finally:
            migration.add_index(None, editor)
