"""Fixed two-row state; retain every journal, outcome, source and shared task."""

from django.db.models import Q

from apps.registrar.public import schedule_lock

from . import reviewed_gunel_duplicate_spec as spec
from . import reviewed_two_catalog_schema as schema
from . import reviewed_two_catalog_state as common
from .reviewed_leyla_catalog_graph import bounded, digest, graph, model, normal, require


def snapshot(org):
    pin = spec.CASE
    require(schema.fingerprints() == spec.SCHEMA, "gunel_unreviewed_relation_schema")
    schedule_lock.lock_schedule(org.pk, spec.PERIOD)
    periods = bounded(model("organizations.AcademicPeriod").objects.filter(pk=spec.PERIOD, organization=org), cap=1)
    require(
        len(periods) == 1
        and periods[0]["academic_year"] == spec.YEAR
        and periods[0]["is_active"]
        and periods[0]["locked_at"] is None,
        "gunel_period_locked_or_changed",
    )
    objects = common._identity(org, pin, spec)
    common._rosters(org, objects, pin)
    common._donor(org, objects, pin)
    common._schedule(org, objects, pin, spec)
    rows = bounded(
        model("workload.TeachingTaskRow").objects.filter(pk__in=[spec.KEEPER, spec.DUPLICATE], organization=org), cap=2
    )
    require({r["id"] for r in rows} == {spec.KEEPER, spec.DUPLICATE}, "gunel_exact_rows_required")
    for row in rows:
        require(
            all(row[k] == v for k, v in spec.PINS["row_invariants"][row["id"]].items()),
            "gunel_source_row_invariants_changed",
        )
        ids = list(
            map(
                str,
                model("workload.TeachingTaskRow")
                .objects.get(pk=row["id"])
                .groups.order_by("pk")
                .values_list("pk", flat=True),
            )
        )
        require(ids == spec.PINS["groups"][row["id"]], "gunel_row_groups_changed")
    states = []
    for values in (spec.PINS["row_before"], spec.PINS["row_after"]):
        states.append(all(all(row[k] == v for k, v in values[row["id"]].items()) for row in rows))
    require(sum(states) == 1, "gunel_partial_or_unreviewed_row_state")
    corrected = states[1]
    tasks = bounded(model("workload.TeachingTask").objects.filter(pk__in=spec.PINS["tasks"], organization=org), cap=2)
    require(len(tasks) == len(spec.PINS["tasks"]), "gunel_fixed_shared_tasks_missing")
    for task in tasks:
        require(
            all(task[k] == v for k, v in spec.PINS["tasks"][task["id"]].items())
            and task["status"] in ("approved", "amended"),
            "gunel_released_shared_task_changed",
        )
    rivals = bounded(
        model("workload.TeachingTaskRow").objects.filter(
            organization=org,
            subject_id__in=pin["subjects"],
            period_id=spec.PERIOD,
            groups__id=pin["group"]["id"],
        ),
        cap=3,
    )
    require({r["id"] for r in rivals} == {spec.KEEPER, spec.DUPLICATE}, "gunel_unreviewed_rival_row")
    assignments = bounded(
        model("workload.TeacherAssignment").objects.filter(row_id__in=[spec.KEEPER, spec.DUPLICATE], organization=org),
        cap=4,
    )
    expected = [a for a in spec.PINS["assignments"] if not corrected or a["row_id"] != spec.DUPLICATE]
    fields = tuple(spec.PINS["assignments"][0])
    require(
        [{k: a[k] for k in fields} for a in assignments] == expected,
        "gunel_exact_assignments_changed",
    )
    scope = (
        Q(offering_id__in=pin["offerings"])
        | Q(author_id=pin["teacher"], subject_id__in=pin["subjects"], period_id__in=[spec.PERIOD])
        | Q(author_id=pin["teacher"], subject_id__in=pin["subjects"], period_id__isnull=True)
    )
    syllabi = bounded(model("syllabus.Syllabus")._base_manager.filter(scope, organization=org), cap=40)
    academic = graph(
        spec.ORG,
        {
            "registrar.CourseOffering": set(pin["offerings"]),
            "workload.TeachingTaskRow": {spec.KEEPER, spec.DUPLICATE},
            "syllabus.Syllabus": {s["id"] for s in syllabi},
        },
    )
    require(
        {r["id"] for r in academic["workload.TeachingTaskRow"]} == {spec.KEEPER, spec.DUPLICATE},
        "gunel_unreviewed_row_reference",
    )
    require(
        not any(r["offering_id"] == pin["empty"] for r in academic.get("registrar.Lesson", [])),
        "gunel_redundant_named_journal_has_activity",
    )
    counts = normal(common.snapshots.offering_counts([o.pk for o in objects]))
    require({r["offering_id"]: r for r in counts} == pin["counts"], "gunel_academic_fingerprint_changed")
    return {
        "corrected": corrected,
        "rows": rows,
        "tasks": tasks,
        "assignments": assignments,
        "periods": periods,
        "academic": academic,
        "authority": common._authority(org, pin),
        "bridge": common._bridge(org, pin),
        "source": digest(spec.PINS["source"]),
        "schema": digest(spec.SCHEMA),
    }


def protected(value):
    """Whitelist exact scalar deltas and exact removed assignments; nothing else."""
    result = {k: v for k, v in value.items() if k not in ("corrected", "rows", "assignments", "academic")}
    academic = {}
    for label, rows in value["academic"].items():
        if label == "workload.TeachingTaskRow":
            rows = [{k: v for k, v in r.items() if k not in spec.PINS["row_after"][r["id"]]} for r in rows]
        elif label == "workload.TeacherAssignment":
            rows = [r for r in rows if r["row_id"] != spec.DUPLICATE]
        academic[label] = {"count": len(rows), "sha256": digest(rows)}
    result["academic"] = academic
    return result
