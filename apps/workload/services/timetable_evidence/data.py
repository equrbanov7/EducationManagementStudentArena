"""Current schedule/lesson metadata, scoped to fixed roots; no grades or student rows."""

from django.apps import apps
from django.db.models import Q
from django.db.models.expressions import RawSQL

from .spec import FIELDS, LIMITS, ORG, PERIOD

MODELS = {
    "offerings": "registrar.CourseOffering",
    "slots": "registrar.ScheduleSlot",
    "lessons": "registrar.Lesson",
    "lesson_corrections": "registrar.LessonCorrection",
    "rows": "workload.TeachingTaskRow",
    "assignments": "workload.TeacherAssignment",
    "groups": "organizations.OrgUnit",
    "periods": "organizations.AcademicPeriod",
    "rooms": "exams.ExamRoom",
}


def bounded(query, limit):
    rows = list(query[: limit + 1])
    if len(rows) > limit:
        raise ValueError("timetable_evidence_row_budget")
    return rows


def fingerprint(query):
    table = query.model._meta.db_table
    return query.annotate(
        _raw_sha=RawSQL(f"encode(sha256(convert_to(row_to_json(\"{table}\")::text,'UTF8')),'hex')", [])
    )


def private_annotations(query, fields):
    table = query.model._meta.db_table
    annotations = {}
    for field in fields:
        column = query.model._meta.get_field(field).column
        ref = f'"{table}"."{column}"'
        text = f"COALESCE(to_jsonb({ref})::text,'null')"
        annotations[field + "_sha256"] = RawSQL(f"encode(sha256(convert_to({text},'UTF8')),'hex')", [])
        if field not in {"topic", "settings", "name"}:
            annotations[field + "_present"] = RawSQL(f"COALESCE({ref}::text,'') <> ''", [])
    return query.annotate(**annotations), tuple(annotations)


def projected(query, table, extras=()):
    query, private = private_annotations(query, extras)
    result = bounded(fingerprint(query.order_by("pk")).values(*FIELDS[table], *private, "_raw_sha"), LIMITS[table])
    for row in result:
        row["raw_record_sha256"] = row.pop("_raw_sha")
    return result


def collect(selected):
    ids = {r["id"] for r in selected}
    managers = {k: apps.get_model(v).objects for k, v in MODELS.items()}
    managers["slots"] = apps.get_model(MODELS["slots"]).all_objects
    base = {k: m.filter(organization_id=ORG) for k, m in managers.items()}
    courses = base["offerings"].filter(pk__in=ids, period_id=PERIOD)
    data = {"offerings": projected(courses, "offerings")}
    if {str(r["id"]) for r in data["offerings"]} != ids:
        raise ValueError("fixed_current_timetable_roots_missing")
    group_ids = {r["group_id"] for r in data["offerings"]}
    subjects = {r["subject_id"] for r in data["offerings"]}
    data["slots"] = projected(base["slots"].filter(offering_id__in=ids), "slots", ("park_reason",))
    data["lessons"] = projected(
        base["lessons"].filter(offering_id__in=ids), "lessons", ("off_schedule_reason", "topic")
    )
    rows = base["rows"].filter(period_id=PERIOD, subject_id__in=subjects, groups__id__in=group_ids).distinct()
    data["rows"] = projected(rows, "rows", ("note", "groups_text"))
    rows_by_id = {str(r["id"]): r for r in data["rows"]}
    for row in data["rows"]:
        row["group_ids"] = []
    for rid, gid in base["rows"].filter(pk__in=rows_by_id).order_by("pk", "groups__id").values_list("id", "groups__id"):
        rows_by_id[str(rid)]["group_ids"].append(str(gid))
    data["assignments"] = projected(
        base["assignments"].filter(row_id__in=rows_by_id), "assignments", ("note", "groups_note")
    )
    data["groups"] = projected(base["groups"].filter(pk__in=group_ids), "groups", ("settings", "name"))
    data["periods"] = projected(base["periods"].filter(pk=PERIOD), "periods", ("name",))
    rooms = {r["room_id"] for r in data["lessons"] if r["room_id"] is not None}
    data["rooms"] = projected(base["rooms"].filter(pk__in=rooms), "rooms", ("name",))
    slot_ids = {str(r["id"]) for r in data["slots"]}
    lesson_ids = {str(r["id"]) for r in data["lessons"]}
    data["lesson_corrections"] = projected(
        base["lesson_corrections"].filter(lesson_id__in=lesson_ids),
        "lesson_corrections",
        ("note", "reason", "document"),
    )
    data["audits"] = scheduling_audits(ids, slot_ids, lesson_ids)
    data["slot_ledger"] = slot_ledger(slot_ids)
    return data


def scheduling_audits(offering_ids, slot_ids, lesson_ids):
    # Private audit JSON/reasons never leave PostgreSQL; only refs, flags and hashes.
    model = apps.get_model("audit.AuditLog")
    q = Q(resource_id__in=offering_ids | slot_ids | lesson_ids)
    for sid in sorted(slot_ids):
        q |= Q(changes__icontains=sid) | Q(old_values__icontains=sid) | Q(new_values__icontains=sid)
    query = model.objects.filter(
        organization_id=ORG, resource_type__in=("registrar.ScheduleSlot", "registrar.Lesson", "registrar.lesson")
    ).filter(q)
    table = model._meta.db_table
    pre = query.annotate(_bytes=RawSQL(f'octet_length(row_to_json("{table}")::text)', []))
    sizes = bounded(pre.order_by("pk").values_list("_bytes", flat=True), LIMITS["audits"])
    if sum(sizes) > 4 * 1024 * 1024 or any(n > 1024 * 1024 for n in sizes):
        raise ValueError("timetable_audit_material_budget")
    query, private = private_annotations(query, ("changes", "old_values", "new_values", "reason", "resource_id"))
    # Presence is useful only for reason, never a substitute for source authority.
    unwanted = {k for k in private if k.endswith("_present") and k != "reason_present"}
    private = tuple(k for k in private if k not in unwanted)
    source = "COALESCE(new_values->>'source',changes->>'source',old_values->>'source')"
    source_kind = f"CASE {source} WHEN 'infer_timetable_from_lessons' THEN 'inferred' WHEN 'import_timetable_docx' THEN 'document' ELSE 'other_or_manual' END"
    annotations = {
        "source_kind": RawSQL(source_kind, []),
        "source_sha256": RawSQL(
            f"encode(sha256(convert_to(COALESCE(to_jsonb({source})::text,'null'),'UTF8')),'hex')", []
        ),
    }
    material = "COALESCE(changes::text,'')||COALESCE(old_values::text,'')||COALESCE(new_values::text,'')"
    for key, ids in (
        ("matched_slot_ids", slot_ids),
        ("matched_offering_ids", offering_ids),
        ("matched_lesson_ids", lesson_ids),
    ):
        annotations[key] = RawSQL(
            f"ARRAY(SELECT ref FROM unnest(%s::text[]) ref WHERE ref=resource_id OR strpos({material},ref)>0 ORDER BY ref)",
            [sorted(ids)],
        )
    fields = ("id", "organization_id", "created_at", "user_id", "action", "resource_type")
    query = fingerprint(query.annotate(**annotations).order_by("pk"))
    result = bounded(query.values(*fields, *private, *annotations, "_raw_sha"), LIMITS["audits"])
    for row in result:
        row["raw_record_sha256"] = row.pop("_raw_sha")
    return result


def slot_ledger(slot_ids):
    model = apps.get_model("legacy_import.LegacyEntityMap")
    qs = model.objects.filter(
        organization_id=ORG, target_model_label__iexact="registrar.scheduleslot", target_pk__in=slot_ids
    )
    fields = ("id", "organization_id", "target_model_label", "target_pk", "state", "source_row_hash")
    qs, private = private_annotations(qs, ("entity_type", "legacy_pk", "transform_version"))
    private = tuple(k for k in private if not k.endswith("_present"))
    result = bounded(fingerprint(qs.order_by("pk")).values(*fields, *private, "_raw_sha"), LIMITS["slot_ledger"])
    for r in result:
        r["raw_record_sha256"] = r.pop("_raw_sha")
        r["target_model_label"] = r["target_model_label"].lower()
    return result
