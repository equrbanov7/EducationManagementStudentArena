"""Actual PostgreSQL parity and planner regression for full-column graph reads."""

import json
from uuid import UUID

from django.db import connection, models
from django.test.utils import isolate_apps

import pytest

from core.reviewed_graph import rows

pytestmark = [pytest.mark.django_db, pytest.mark.postgres]


@pytest.fixture(params=["integer", "bigint", "uuid", "varchar(40)"])
def graph_model(request):
    kind = request.param
    field = {
        "integer": models.AutoField,
        "bigint": models.BigAutoField,
        "uuid": models.UUIDField,
        "varchar(40)": lambda **kw: models.CharField(max_length=40, **kw),
    }[kind]
    with isolate_apps():

        class SyntheticGraphRow(models.Model):
            id = field(primary_key=True)

            class Meta:
                app_label = "synthetic_graph"
                managed = False
                db_table = "test_reviewed_graph_typed_pk"

        expr = {
            "integer": "n",
            "bigint": "n::bigint",
            "uuid": "lpad(to_hex(n),32,'0')::uuid",
            "varchar(40)": "lpad(n::text,8,'0')",
        }[kind]
        with connection.cursor() as cursor:
            cursor.execute(
                f"CREATE TEMP TABLE test_reviewed_graph_typed_pk (id {kind} PRIMARY KEY, "
                "extra_database_column jsonb, amount numeric(12,4), observed_at timestamptz) ON COMMIT DROP"
            )
            cursor.execute(
                "INSERT INTO test_reviewed_graph_typed_pk "
                f"SELECT {expr}, jsonb_build_object('zero', 0, 'text', 'ə'), "
                "0.0000, '2026-10-21 10:10:10.123456+00' FROM generate_series(1,10000) n"
            )
            cursor.execute("ANALYZE test_reviewed_graph_typed_pk")
        convert = {
            "integer": int,
            "bigint": int,
            "uuid": lambda n: UUID(int=n),
            "varchar(40)": lambda n: str(n).zfill(8),
        }[kind]
        yield SyntheticGraphRow, [convert(n) for n in (2, 5000, 9999)]


def test_full_database_columns_and_order_match_previous_query(graph_model):
    model, ids = graph_model
    actual = rows(model.objects.filter(pk__in=ids))
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT to_jsonb(t) FROM test_reviewed_graph_typed_pk t " "WHERE t.id::text=ANY(%s) ORDER BY t.id",
            [list(map(str, ids))],
        )
        expected = [json.loads(r[0]) if isinstance(r[0], str) else r[0] for r in cursor.fetchall()]
    assert actual == expected
    assert len(actual) == 3
    assert all(r["extra_database_column"] == {"zero": 0, "text": "ə"} for r in actual)
    assert all(r["amount"] == 0 and ".123456" in r["observed_at"] for r in actual)


def test_real_planner_uses_primary_key_index_without_forced_settings(graph_model):
    model, ids = graph_model
    captured = []

    def collect(execute, sql, params, many, context):
        captured.append((sql, params))
        return execute(sql, params, many, context)

    with connection.execute_wrapper(collect):
        rows(model.objects.filter(pk__in=ids))
    assert len(captured) == 2
    assert "FOR UPDATE" in captured[0][0]
    sql, params = captured[1]
    with connection.cursor() as cursor:
        cursor.execute("EXPLAIN (FORMAT JSON, COSTS OFF) " + sql, params)
        plan = cursor.fetchone()[0][0]["Plan"]

    def nodes(node):
        yield node
        for child in node.get("Plans", []):
            yield from nodes(child)

    assert any(n.get("Index Name") == "test_reviewed_graph_typed_pk_pkey" for n in nodes(plan))
    assert not any(n["Node Type"] == "Seq Scan" for n in nodes(plan))


def test_budget_still_refuses_before_full_row_read(graph_model):
    model, ids = graph_model
    with pytest.raises(ValueError, match="^reviewed_graph_budget$"):
        rows(model.objects.filter(pk__in=ids), limit=2)
    assert rows(model.objects.filter(pk__in=[])) == []
