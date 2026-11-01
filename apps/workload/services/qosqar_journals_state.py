"""Exactly two reviewed Qoşqar pairs and their complete immutable academic graph."""

from . import qosqar_duplicate_state as duplicate
from . import qosqar_modelling_repair as modelling

model, digest, records = duplicate.model, duplicate.digest, duplicate.records
Error = duplicate.DuplicateError
RESOURCE = "workload.qosqar_two_journals"


def pairs():
    return {duplicate.EMPTY: duplicate.FILLED, modelling.EMPTY: modelling.OFFERING}


def graph():
    # Same complete reverse traversal as the reviewed Math invariant; own fixed
    # root set here, never a mutable generic caller-supplied collection.
    from django.apps import apps

    pending = {"registrar.CourseOffering": set(pairs()) | set(pairs().values())}
    seen, result = {}, {}
    while pending:
        label, ids = pending.popitem()
        ids = set(map(str, ids)) - seen.get(label, set())
        if not ids:
            continue
        cls = apps.get_model(label)
        rows = records(cls._base_manager.select_for_update().filter(pk__in=ids))
        if any(str(r.get("organization_id", duplicate.ORG)) != duplicate.ORG for r in rows):
            raise Error("reverse_graph_tenant_changed")
        seen.setdefault(label, set()).update(ids)
        result.setdefault(label, []).extend(rows)
        if sum(map(len, result.values())) > 20000:
            raise Error("fixed_reverse_graph_budget")
        for rel in cls._meta.get_fields(include_hidden=True):
            if not rel.auto_created or rel.concrete or not rel.related_model:
                continue
            lookup = rel.field.name if rel.many_to_many else rel.field.attname
            children = rel.related_model._base_manager.filter(**{lookup + "__in": ids}).values_list("pk", flat=True)
            pending.setdefault(rel.related_model._meta.label, set()).update(map(str, children))
    return {k: sorted(v, key=lambda r: str(r[model(k)._meta.pk.attname])) for k, v in sorted(result.items()) if v}


def workload_history(rows):
    """Keep review/objection/assignment descendants intact; capture amendment drift too."""
    excluded = {
        "workload.TeachingTaskRow",
        "workload.TeacherAssignment",
        model("workload.TeachingTaskRow").groups.through._meta.label,
    }
    pending = {"workload.TeachingTaskRow": set(map(str, rows.values_list("pk", flat=True)))}
    seen, result = {}, {}
    while pending:
        label, ids = pending.popitem()
        ids = set(map(str, ids)) - seen.get(label, set())
        if not ids:
            continue
        seen.setdefault(label, set()).update(ids)
        cls = model(label)
        values = records(cls._base_manager.select_for_update().filter(pk__in=ids))
        if any(str(r.get("organization_id", duplicate.ORG)) != duplicate.ORG for r in values):
            raise Error("workload_history_tenant_changed")
        if label not in excluded:
            result.setdefault(label, []).extend(values)
        if sum(map(len, result.values())) > 20000:
            raise Error("workload_history_scope_budget")
        for rel in cls._meta.get_fields(include_hidden=True):
            if not rel.auto_created or rel.concrete or not rel.related_model:
                continue
            lookup = rel.field.name if rel.many_to_many else rel.field.attname
            children = rel.related_model._base_manager.filter(**{lookup + "__in": ids}).values_list("pk", flat=True)
            pending.setdefault(rel.related_model._meta.label, set()).update(map(str, children))
    return {k: sorted(v, key=lambda r: str(r[model(k)._meta.pk.attname])) for k, v in sorted(result.items()) if v}


def capture():
    rows = model("workload.TeachingTaskRow").objects.filter(task_id=duplicate.TASK, organization_id=duplicate.ORG)
    return {
        "academic": graph(),
        "workload_history": workload_history(rows),
        "amendments": records(
            model("workload.WorkloadAmendment").objects.filter(task_id=duplicate.TASK, organization_id=duplicate.ORG)
        ),
        "rows": records(rows),
        "groups": sorted((str(r.pk), str(g)) for r in rows for g in r.groups.values_list("pk", flat=True)),
        "group_links": records(
            model("workload.TeachingTaskRow").groups.through.objects.filter(teachingtaskrow__in=rows)
        ),
        "assignments": records(model("workload.TeacherAssignment").objects.filter(row__in=rows)),
        "task": records(
            model("workload.TeachingTask").objects.filter(pk=duplicate.TASK, organization_id=duplicate.ORG)
        ),
        "subjects": records(
            model("registrar.Subject").objects.filter(
                pk__in=(duplicate.SUBJECT, duplicate.DUPLICATE_SUBJECT, modelling.OLD), organization_id=duplicate.ORG
            )
        ),
    }


def protected(value):
    academic = {
        k: v for k, v in value["academic"].items() if k not in ("registrar.ScheduleSlot", "syllabus.SyllabusShare")
    }
    academic["registrar.CourseOffering"] = [
        {
            k: v
            for k, v in row.items()
            if not (str(row["id"]) in pairs() and k == "is_active")
            and not (str(row["id"]) == modelling.OFFERING and k == "subject_id")
        }
        for row in academic["registrar.CourseOffering"]
    ]
    # Only the new exact modelling share may be added/removed; pre-existing
    # shares elsewhere (including any student-limited shares) stay protected.
    shares = [
        r for r in value["academic"].get("syllabus.SyllabusShare", []) if str(r["offering_id"]) != modelling.OFFERING
    ]
    if shares:
        academic["syllabus.SyllabusShare"] = shares
    rows = [
        {
            k: v
            for k, v in r.items()
            if not (str(r["id"]) == modelling.ROW and k in ("subject_id", "subject_text", "updated_at"))
        }
        for r in value["rows"]
        if str(r["id"]) != duplicate.REMOVE_ROW
    ]
    return {
        "academic": academic,
        "workload_history": value["workload_history"],
        "subjects": value["subjects"],
        "rows": rows,
        "groups": [r for r in value["groups"] if r[0] != duplicate.REMOVE_ROW],
        "group_links": [r for r in value["group_links"] if str(r["teachingtaskrow_id"]) != duplicate.REMOVE_ROW],
        "assignments": [r for r in value["assignments"] if str(r["row_id"]) != duplicate.REMOVE_ROW],
        "task": [{k: v for k, v in r.items() if k not in ("status", "updated_at")} for r in value["task"]],
    }


def schedule_rows(value):
    return value["academic"].get("registrar.ScheduleSlot", [])


def validate(*, sections, corrected):
    if (duplicate.ORG, duplicate.TASK, duplicate.PERIOD, duplicate.TEACHER, duplicate.FILLED, duplicate.SUBJECT) != (
        modelling.ORG,
        modelling.TASK,
        modelling.PERIOD,
        modelling.TEACHER,
        modelling.ANCHOR,
        modelling.NEW,
    ):
        raise Error("fixed_combined_scope_mismatch")
    if len(pairs()) != 2 or len(set(pairs().values())) != 2:
        raise Error("fixed_two_distinct_pairs_required")
    offerings = {
        str(o.pk): o
        for o in model("registrar.CourseOffering")
        .objects.select_for_update()
        .filter(pk__in=set(pairs()) | set(pairs().values()), organization_id=duplicate.ORG)
    }
    duplicate.validate({k: offerings[k] for k in (duplicate.EMPTY, duplicate.FILLED)}, retired=corrected)
    row = (
        model("workload.TeachingTaskRow")
        .objects.select_for_update()
        .get(pk=modelling.ROW, organization_id=duplicate.ORG)
    )
    syllabus = modelling.validate(
        {k: offerings[k] for k in (modelling.EMPTY, modelling.OFFERING, modelling.ANCHOR)},
        row,
        corrected=corrected,
        sections=sections,
    )
    reviewed_rows = model("workload.TeachingTaskRow").objects.filter(
        pk__in=(duplicate.KEEP_ROW, duplicate.REMOVE_ROW, modelling.ROW), organization_id=duplicate.ORG
    )
    for reviewed in reviewed_rows:
        if (
            str(reviewed.credits),
            reviewed.union_count,
            reviewed.subgroup_count,
            reviewed.season,
            reviewed.degree_level,
            reviewed.education_form,
        ) != ("7", 1, 1, "fall", "bachelor", "eyani") or any(
            getattr(reviewed, name)
            for name in (
                "consult_hours",
                "exam_hours",
                "postgrad_hours",
                "practice_production_hours",
                "practice_research_hours",
                "thesis_hours",
            )
        ):
            raise Error("reviewed_workload_credit_multiplier_or_other_hours_changed")
        if reviewed.assignments.filter(is_hourly_paid=True).exists():
            raise Error("reviewed_assignment_pay_basis_changed")
    return offerings, row, syllabus
