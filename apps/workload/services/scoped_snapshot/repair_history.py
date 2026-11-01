"""Fixed Math wrong-row history, typed metadata only; never apply authority."""

import hashlib
import json
import re
import uuid

from django.apps import apps
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
TASK = "743c143e-254a-4ef1-bf73-c368a477cc2f"
ROW = "eb41b840-05b1-4637-8c2c-03fb8b36c0c3"
ASSIGNMENTS = ("45e4d53b-e6b0-4891-afc4-d387ee6307ec", "4db00940-f2a3-4d54-97ff-6f7730bd0af1")
MAX_ROWS = 2500
NUMBER_FIELDS = {
    "hours",
    "total_hours",
    "lecture_total",
    "seminar_total",
    "lab_total",
    "lecture_plan",
    "seminar_plan",
    "lab_plan",
    "union_count",
    "subgroup_count",
    "student_count",
    "teacher",
    "teacher_id",
    "assigned_by_id",
    "consult_hours",
    "exam_hours",
    "thesis_hours",
    "postgrad_hours",
    "practice_production_hours",
    "practice_research_hours",
}
UUID_FIELDS = {
    "subject_id",
    "period_id",
    "specialty_id",
    "row_id",
    "task_id",
    "group_id",
    "assignment_id",
    "assignment",
}
CODES = {
    "activity": {
        "lecture",
        "seminar",
        "lab",
        "consult",
        "exam",
        "thesis",
        "postgrad",
        "practice_production",
        "practice_research",
    },
    "season": {"fall", "spring", "annual"},
    "row_kind": {"teaching", "other"},
    "action": {
        "row_added",
        "row_edited",
        "row_deleted",
        "assignment_added",
        "assignment_edited",
        "assignment_deleted",
        "assignment_saved",
        "assignment_removed",
        "assigned",
        "unassigned",
    },
}
CHOICE_FIELDS = set(CODES) | {
    "target_kind",
    "reason",
    "reason_key",
    "status",
    "review_status",
    "degree_level",
    "education_form",
}


def sha(value):
    return hashlib.sha256(json.dumps(value, cls=DjangoJSONEncoder, sort_keys=True).encode()).hexdigest()


def material(value):
    """No arbitrary strings/nesting: unknown JSON remains hash-only evidence."""
    if not isinstance(value, dict):
        return {}
    result = {}
    for key, item in value.items():
        if key in NUMBER_FIELDS and type(item) is int:
            result[key] = item
        elif key in NUMBER_FIELDS and isinstance(item, str) and re.fullmatch(r"[0-9]{1,10}", item):
            result[key] = int(item)
        elif key in UUID_FIELDS:
            try:
                result[key] = str(uuid.UUID(str(item))) if item is not None else None
            except (ValueError, TypeError, AttributeError):
                pass
        elif key == "is_hourly_paid" and type(item) is bool:
            result[key] = item
        elif (
            key == "credits" and isinstance(item, (str, int)) and re.fullmatch(r"[0-9]{1,3}(\.[0-9]{1,2})?", str(item))
        ):
            result[key] = str(item)
        elif key in CODES and isinstance(item, str) and item in CODES[key]:
            result[key] = item
        elif key == "fields" and isinstance(item, list):
            result[key] = sorted(
                {
                    v
                    for v in item
                    if isinstance(v, str)
                    and v in NUMBER_FIELDS | UUID_FIELDS | {"is_hourly_paid", "credits"} | set(CODES)
                }
            )
    return result


def project(cls, row):
    fields, links, link_models = {}, {}, {}
    note_present = False
    for field in cls._meta.concrete_fields:
        value = row[field.attname]
        if field.is_relation:
            links[field.attname] = value
            link_models[field.attname] = field.related_model._meta.label
        elif field.name in {"note", "text", "comment", "resolution_note", "groups_note"}:
            note_present |= bool(value)
        elif field.name in NUMBER_FIELDS | {"revision", "credits", "is_hourly_paid", "is_active"} and isinstance(
            field, (models.BooleanField, models.IntegerField, models.DecimalField)
        ):
            fields[field.name] = str(value) if isinstance(field, models.DecimalField) and value is not None else value
        elif field.name in CHOICE_FIELDS and field.choices and value in {choice[0] for choice in field.flatchoices}:
            fields[field.name] = value
    return {
        "model_label": cls._meta.label,
        "id": row[cls._meta.pk.attname],
        "organization_id": ORG,
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
        "foreign_keys": links,
        "foreign_key_models": link_models,
        "material": fields,
        "target_id": row.get("target_id"),
        "old_material": material(row.get("old_values")),
        "new_material": material(row.get("new_values")),
        "old_values_sha256": sha(row["old_values"]) if "old_values" in row else None,
        "new_values_sha256": sha(row["new_values"]) if "new_values" in row else None,
        "raw_record_sha256": sha(row),
        "note_present": note_present,
        "document_present": bool(row.get("document")),
    }


def collect_math_history():
    def bounded_ids(query):
        values = list(query[: MAX_ROWS + 1])
        if len(values) > MAX_ROWS:
            raise ValueError("math_history_scope_budget_exceeded")
        return set(map(str, values))

    Row = apps.get_model("workload.TeachingTaskRow")
    roots = Row.objects.filter(organization_id=ORG, task__organization_id=ORG, task_id=TASK, pk=ROW)
    root_ids = set(map(str, roots.values_list("pk", flat=True)))
    Assignment = apps.get_model("workload.TeacherAssignment")
    assigned = sorted(
        bounded_ids(
            Assignment.objects.filter(organization_id=ORG, row_id__in=root_ids)
            .order_by("pk")
            .values_list("pk", flat=True)
        )
    )
    pending = {"workload.TeachingTaskRow": root_ids}
    seen, output = {}, []
    # Generic amendment target IDs are deliberately not real FK relations.
    if root_ids:
        amendments = apps.get_model("workload.WorkloadAmendment").objects.filter(
            organization_id=ORG, task_id=TASK, target_id__in=[ROW, *ASSIGNMENTS, *assigned]
        )
        pending["workload.WorkloadAmendment"] = bounded_ids(amendments.values_list("pk", flat=True))
        # Include assignment-pointing objections even if row_id was corrupted.
        objections = apps.get_model("workload.LoadObjection").objects.filter(
            organization_id=ORG, assignment_id__in=assigned
        )
        pending["workload.LoadObjection"] = bounded_ids(objections.values_list("pk", flat=True))
    while pending:
        label, keys = pending.popitem()
        keys = set(map(str, keys)) - seen.get(label, set())
        if not keys:
            continue
        cls = apps.get_model(label)
        query = cls._base_manager.filter(pk__in=keys)
        if any(field.name == "organization" for field in cls._meta.concrete_fields):
            if query.exclude(organization_id=ORG).exists():
                raise ValueError("math_history_cross_tenant_relation")
            query = query.filter(organization_id=ORG)
        values = list(query.order_by("pk").values()[: MAX_ROWS - len(output) + 1])
        seen.setdefault(label, set()).update(keys)
        output.extend(project(cls, row) for row in values)
        if len(output) > MAX_ROWS:
            raise ValueError("math_history_scope_budget_exceeded")
        for rel in cls._meta.get_fields(include_hidden=True):
            if not rel.auto_created or rel.concrete or not rel.related_model:
                continue
            lookup = rel.field.name if rel.many_to_many else rel.field.attname
            children = rel.related_model._base_manager.filter(**{lookup + "__in": keys}).values_list("pk", flat=True)
            pending.setdefault(rel.related_model._meta.label, set()).update(bounded_ids(children))
    return {
        "repair_math_history": sorted(output, key=lambda item: (item["model_label"], str(item["id"]))),
        "repair_math_history_scope": [
            {
                "organization_id": ORG,
                "task_id": TASK,
                "row_id": ROW,
                "expected_assignment_ids": sorted(ASSIGNMENTS),
                "actual_assignment_ids": list(map(str, assigned)),
                "root_present": bool(root_ids),
                "closure_rows": len(output),
                "typed_metadata_only": True,
                "automatic_apply_authority": False,
            }
        ],
    }
