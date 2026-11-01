"""Lock three original journals and both groups, preserving every existing row."""

import copy

from django.db.models import Q

from apps.registrar.public import credit_source, schedule_lock

from . import reviewed_aida_catalog_spec as spec
from . import reviewed_two_catalog_schema as schema
from . import reviewed_two_catalog_state as common
from .reviewed_leyla_catalog_graph import bounded, digest, graph, model, normal, require


def snapshot(org):
    pin = spec.CASE
    require(schema.fingerprints() == spec.SCHEMA, "aida_unreviewed_relation_schema")
    schedule_lock.lock_schedule(org.pk, spec.PERIOD)
    periods = bounded(model("organizations.AcademicPeriod").objects.filter(pk=spec.PERIOD, organization=org), cap=1)
    require(
        len(periods) == 1
        and periods[0]["academic_year"] == spec.YEAR
        and periods[0]["is_active"]
        and periods[0]["locked_at"] is None,
        "aida_period_locked_or_changed",
    )
    rows = bounded(model("workload.TeachingTaskRow").objects.filter(pk=spec.ROW, organization=org), cap=1)
    kings = bounded(model("registrar.CourseOffering")._base_manager.filter(pk=spec.KING, organization=org), cap=1)
    require(len(rows) == len(kings) == 1, "aida_original_row_or_king_course_missing")
    row, king = rows[0], kings[0]
    require(
        row["subject_id"] == king["subject_id"] in (pin["before_subject"], pin["after_subject"]),
        "aida_partial_alias_state",
    )
    corrected = row["subject_id"] == pin["after_subject"]
    require(all(row[k] == v for k, v in spec.PINS["row_fields"].items()), "aida_official_row_budget_or_credit_changed")
    effective = copy.deepcopy(pin)
    effective["offerings"][spec.KING]["subject_id"] = king["subject_id"]
    objects = common._identity(org, effective, spec)
    # The second source flow is a separate course/group, not an enrollment merge.
    king_pin = {
        **effective,
        "offerings": {spec.KING: effective["offerings"][spec.KING]},
        "group": spec.PINS["groups"][king["group_id"]],
    }
    common._identity(org, king_pin, spec)
    require(
        not model("registrar.CourseOffering")
        ._base_manager.filter(
            organization=org, group_id=king["group_id"], period_id=spec.PERIOD, subject_id=pin["after_subject"]
        )
        .exclude(pk=spec.KING)
        .exists(),
        "aida_existing_canonical_king_course_requires_review",
    )
    task = bounded(model("workload.TeachingTask").objects.filter(pk=spec.PINS["task"]["id"], organization=org), cap=1)
    require(
        len(task) == 1
        and all(task[0][k] == v for k, v in spec.PINS["task"].items())
        and task[0]["status"] in ("approved", "distributed", "amended"),
        "aida_released_official_task_changed",
    )
    gids = set(map(str, model("workload.TeachingTaskRow").objects.get(pk=spec.ROW).groups.values_list("pk", flat=True)))
    require(gids == set(spec.PINS["groups"]), "aida_shared_official_group_scope_changed")
    rivals = list(
        model("workload.TeachingTaskRow")
        .objects.filter(organization=org, period_id=spec.PERIOD, subject_id__in=pin["subjects"], groups__id__in=gids)
        .values_list("pk", flat=True)[:11]
    )
    require(len(rivals) <= 10 and set(map(str, rivals)) == {spec.ROW}, "aida_unreviewed_duplicate_workload_row")
    assignments = bounded(model("workload.TeacherAssignment").objects.filter(row_id=spec.ROW, organization=org), cap=2)
    fields = tuple(spec.PINS["assignments"][0])
    require(
        [{k: a[k] for k in fields} for a in assignments] == spec.PINS["assignments"],
        "aida_exact_official_allocations_changed",
    )
    enrollments = bounded(
        model("registrar.Enrollment")._base_manager.filter(organization=org, offering_id__in=pin["offerings"]), cap=150
    )
    rosters = {}
    for oid, expected in spec.PINS["rosters"].items():
        active = [r for r in enrollments if r["offering_id"] == oid and r["status"] == "enrolled"]
        users = sorted(r["student_id"] for r in active)
        require(
            len(users) == len(set(users)) == expected["count"]
            and digest(users) == expected["sha256"]
            and all(r["superseded_by_id"] is None for r in active),
            "aida_exact_source_roster_changed",
        )
        rosters[oid] = set(users)
    require(
        rosters[pin["empty"]] < rosters[pin["filled"]]
        and rosters[pin["filled"]] - rosters[pin["empty"]] == set(map(int, spec.PINS["extra_students"])),
        "aida_three_retained_source_students_changed",
    )
    extra_bridge = []
    for uid, expected in spec.PINS["extra_students"].items():
        actual = [r for r in enrollments if r["student_id"] == int(uid) and r["offering_id"] == pin["filled"]]
        require(
            len(actual) == 1 and actual[0]["source_group_id"] == expected["source_group_id"],
            "aida_extra_student_provenance_changed",
        )
        mapped = bounded(
            model("legacy_import.LegacyEntityMap").objects.filter(
                organization=org,
                source_system="myedu_mariadb",
                entity_type="student",
                legacy_pk=str(expected["legacy_id"]),
            ),
            cap=1,
        )
        require(
            len(mapped) == 1 and mapped[0]["target_pk"] == uid and mapped[0]["state"] == "migrated",
            "aida_extra_student_identity_changed",
        )
        extra_bridge.extend(mapped)
    effective_credits = {
        str(key): value
        for key, value in credit_source.credits_for_enrollments(
            model("registrar.Enrollment")._base_manager.filter(organization=org, pk__in=[e["id"] for e in enrollments]),
            organization=org,
        ).items()
    }
    common._donor(org, objects, pin)
    donor = model("syllabus.SyllabusVersion")._base_manager.get(
        pk=pin["donor"]["approved_version_id"], organization=org
    )
    topic = common.content_fingerprints({section.section_id: section.data for section in donor.sections.all()})[
        "topic_summary"
    ]
    require(
        spec.PINS["source"]["existing_own_approved_share_authorized"] is True
        and topic["nonempty_topic_count"] == 15
        and topic["hours_by_kind"] == {"lecture": 30, "seminar": 13, "practical": 0, "lab": 0},
        "aida_exact_known_43_of_45_source_required",
    )
    shares = bounded(
        model("syllabus.SyllabusShare")._base_manager.filter(organization=org, offering_id=spec.KING), cap=1
    )
    require(
        len(shares) == int(corrected)
        and all(row["syllabus_id"] == pin["donor"]["id"] and row["source"] == "legacy" for row in shares),
        "aida_existing_own_source_share_changed",
    )
    if corrected:
        common._donor(org, objects, {**pin, "filled": spec.KING})
    for target in (pin["filled"], spec.KING):
        common._schedule(org, objects, {**pin, "filled": target}, spec)
    scope = (
        Q(offering_id__in=pin["offerings"])
        | Q(author_id=pin["teacher"], subject_id__in=pin["subjects"], period_id__in=[spec.PERIOD])
        | Q(author_id=pin["teacher"], subject_id__in=pin["subjects"], period_id__isnull=True)
    )
    syllabi = bounded(model("syllabus.Syllabus")._base_manager.filter(scope, organization=org), cap=40)
    require(not any(s["offering_id"] == spec.KING for s in syllabi), "aida_new_king_syllabus_requires_explicit_review")
    # Include authored subject exams even when they have no offering M2M, and retain outcomes/QB links.
    exams = bounded(
        model("exams.Exam")._base_manager.filter(
            organization=org, author_id=pin["teacher"], subject_id__in=pin["subjects"]
        ),
        cap=100,
    )
    academic = graph(
        spec.ORG,
        {
            "registrar.CourseOffering": set(pin["offerings"]),
            "workload.TeachingTaskRow": {spec.ROW},
            "syllabus.Syllabus": {s["id"] for s in syllabi},
            "exams.Exam": {str(e["id"]) for e in exams},
        },
    )
    require({r["id"] for r in academic["workload.TeachingTaskRow"]} == {spec.ROW}, "aida_unreviewed_row_reference")
    require(
        not any(r["offering_id"] == pin["empty"] for r in academic.get("registrar.Lesson", [])),
        "aida_named_journal_new_real_activity",
    )
    counts = normal(common.snapshots.offering_counts([o.pk for o in objects]))
    require({r["offering_id"]: r for r in counts} == pin["counts"], "aida_all_three_academic_fingerprints_changed")
    return {
        "corrected": corrected,
        "row": row,
        "king": king,
        "assignments": assignments,
        "task": task,
        "periods": periods,
        "academic": academic,
        "authority": common._authority(org, pin),
        "bridge": common._bridge(org, pin),
        "extra_bridge": extra_bridge,
        "effective_credits": effective_credits,
        "shares": shares,
        "source": digest(spec.PINS["source"]),
        "schema": digest(spec.SCHEMA),
    }


def protected(value):
    result = {k: v for k, v in value.items() if k not in ("corrected", "row", "king", "academic", "shares")}
    academic = {}
    for label, values in value["academic"].items():
        if label == "workload.TeachingTaskRow":
            values = [{k: v for k, v in r.items() if k != "subject_id"} for r in values]
        elif label == "registrar.CourseOffering":
            values = [{k: v for k, v in r.items() if k != "subject_id" or r["id"] != spec.KING} for r in values]
        elif label == "syllabus.SyllabusShare":
            values = [r for r in values if r["offering_id"] != spec.KING]
        academic[label] = {"count": len(values), "sha256": digest(values)}
    academic.setdefault("syllabus.SyllabusShare", {"count": 0, "sha256": digest([])})
    result["academic"] = academic
    return result
