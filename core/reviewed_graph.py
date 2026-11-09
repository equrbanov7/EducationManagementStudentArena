"""Bounded native full-column reverse graph; no app imports, no data mutation."""

import hashlib
import json

from django.apps import apps
from django.db import connection


def require(condition, code):
    if not condition:
        raise ValueError(code)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def rows(query, *, limit=20000):
    require(connection.vendor == "postgresql", "reviewed_graph_postgresql_required")
    ids = list(query.select_for_update().order_by("pk").values_list("pk", flat=True)[: limit + 1])
    require(len(ids) <= limit, "reviewed_graph_budget")
    if not ids:
        return []
    table = connection.ops.quote_name(query.model._meta.db_table)
    pk = connection.ops.quote_name(query.model._meta.pk.column)
    with connection.cursor() as cursor:
        # Keep the ORM's typed IDs so PostgreSQL can use the primary-key index.
        # Casting the column to text scans large related tables during dry-runs.
        cursor.execute(f"SELECT to_jsonb(t) FROM {table} t WHERE t.{pk}=ANY(%s) ORDER BY t.{pk}", [ids])
        return [json.loads(row[0]) if isinstance(row[0], str) else row[0] for row in cursor.fetchall()]


def graph(roots, *, organization_id, limit=20000):
    pending = {label: set(map(str, ids)) for label, ids in roots.items()}
    seen, result = {}, {}
    while pending:
        label, ids = pending.popitem()
        ids -= seen.get(label, set())
        if not ids:
            continue
        model = apps.get_model(label)
        found = rows(model._base_manager.filter(pk__in=ids), limit=limit)
        require(
            all(str(row.get("organization_id", organization_id)) == str(organization_id) for row in found),
            "reviewed_graph_tenant_changed",
        )
        seen.setdefault(label, set()).update(ids)
        result.setdefault(label, []).extend(found)
        require(sum(map(len, result.values())) <= limit, "reviewed_graph_budget")
        for relation in model._meta.get_fields(include_hidden=True):
            child = relation.related_model
            if not relation.auto_created or relation.concrete or child is None:
                continue
            lookup = relation.field.name if relation.many_to_many else relation.field.attname
            child_ids = list(
                child._base_manager.filter(**{lookup + "__in": ids}).values_list("pk", flat=True)[: limit + 1]
            )
            require(len(child_ids) <= limit, "reviewed_graph_budget")
            pending.setdefault(child._meta.label, set()).update(map(str, child_ids))
    return {
        label: sorted(values, key=lambda row: str(row[apps.get_model(label)._meta.pk.column]))
        for label, values in sorted(result.items())
    }
