"""Closed, bounded reverse graph for a metadata-only workload relink.

All base managers and hidden through relations are included. No grade, syllabus,
exam or enrollment values are written; receipts contain counts and hashes only.
"""

import hashlib
import json

from django.apps import apps

LIMIT = 20000


class RepairError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise RepairError(code)


def normal(value):
    # str(datetime) retains microseconds; DjangoJSONEncoder truncates to milliseconds.
    return json.loads(json.dumps(value, default=str))


def digest(value):
    return hashlib.sha256(json.dumps(normal(value), ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def model(label):
    return apps.get_model(label)


def bounded(query, *, cap=LIMIT, lock=True):
    if lock:
        query = query.select_for_update()
    rows = normal(list(query.order_by("pk").values()[: cap + 1]))
    require(len(rows) <= cap, "leyla_row_budget")
    return rows


def graph(organization_id, roots, *, lock=True):
    pending = {label: set(map(str, ids)) for label, ids in roots.items()}
    seen, result = {}, {}
    while pending:
        label, ids = pending.popitem()
        ids -= seen.get(label, set())
        if not ids:
            continue
        cls = model(label)
        rows = bounded(cls._base_manager.filter(pk__in=ids), lock=lock)
        require(
            all(str(r.get("organization_id", organization_id)) == organization_id for r in rows),
            "leyla_reverse_graph_tenant_changed",
        )
        seen.setdefault(label, set()).update(ids)
        result.setdefault(label, []).extend(rows)
        require(sum(map(len, result.values())) <= LIMIT, "leyla_graph_budget")
        for rel in cls._meta.get_fields(include_hidden=True):
            child = rel.related_model
            if not rel.auto_created or rel.concrete or child is None:
                continue
            lookup = rel.field.name if rel.many_to_many else rel.field.attname
            require(bool(lookup), "leyla_reverse_relation_not_supported")
            child_ids = list(
                child._base_manager.filter(**{lookup + "__in": ids})
                .order_by("pk")
                .values_list("pk", flat=True)[: LIMIT + 1]
            )
            require(len(child_ids) <= LIMIT, "leyla_reverse_relation_budget")
            pending.setdefault(child._meta.label, set()).update(map(str, child_ids))
    return {
        label: sorted(rows, key=lambda r: str(r[model(label)._meta.pk.attname]))
        for label, rows in sorted(result.items())
    }


def protected(rows):
    result = {}
    for label, values in rows.items():
        if label == "workload.TeachingTaskRow":
            values = [{k: v for k, v in row.items() if k != "subject_id"} for row in values]
        result[label] = {"count": len(values), "sha256": digest(values)}
    return result
