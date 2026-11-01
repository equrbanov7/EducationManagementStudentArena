"""Fresh fixed official45 scope and full academic/body/Exam closure, including undo drift."""

from types import SimpleNamespace

from django.db.models import Q
from django.utils import timezone

from apps.registrar.public import schedule_lock
from apps.syllabus.public import approved_version_for, content_fingerprints, section_data_map, syllabus_for_offering
from apps.workload.public import reviewed_catalog_graph as e
from apps.workload.public import reviewed_catalog_schema

from . import exact_syllabus_recovery as core
from . import reviewed_pervin_syllabus_spec as spec
from .blank_draft_syllabus_state import actor_scope


def require(condition, code):
    if not condition:
        raise core.RestoreError(code)


def _pins(rows, expected, key="id"):
    actual = {str(r[key]): r for r in rows}
    require(
        actual.keys() == expected.keys()
        and all(all(actual[pk].get(k) == v for k, v in p.items()) for pk, p in expected.items()),
        "pervin_fixed_identity_or_allocation_changed",
    )


def _scope(org, actor):
    actor_scope(org, actor)
    require(reviewed_catalog_schema.fingerprints() == spec.PINS["schema"], "pervin_unreviewed_relation_schema")
    schedule_lock.lock_schedule(org.pk, spec.PERIOD)
    objects = []
    for oid, pin in spec.PINS["offerings"].items():
        case = SimpleNamespace(
            organization=spec.ORG,
            period=spec.PERIOD,
            offering=oid,
            author=spec.PINS["teacher"],
            allowed_owners=(spec.PINS["teacher"],),
            subject_code="QKU-219",
            subject_id=spec.PINS["subject"],
            group_id=pin["group_id"],
            require_current_period=True,
        )
        obj = core.scope(org, actor, case)
        require(
            not obj.is_intensive
            and obj.lesson_hours == 45
            and obj.period.locked_at is None
            and obj.period.academic_year == "2026/2027"
            and obj.period.name == "Payız"
            and obj.period.start_date <= timezone.localdate() <= obj.period.end_date,
            "pervin_official45_current_period_required",
        )
        require(
            e.model("registrar.CourseOffering")
            .objects.filter(organization=org, subject_id=obj.subject_id, period_id=obj.period_id, group_id=obj.group_id)
            .count()
            == 1,
            "pervin_ambiguous_current_course",
        )
        objects.append(obj)
    row = e.bounded(e.model("workload.TeachingTaskRow").objects.filter(organization=org, pk=spec.PINS["row_id"]), cap=1)
    _pins(row, {spec.PINS["row_id"]: spec.PINS["row_fields"]})
    task = (
        e.model("workload.TeachingTask").objects.select_for_update().get(pk=spec.PINS["task"]["id"], organization=org)
    )
    require(
        all(e.normal(getattr(task, k)) == v for k, v in spec.PINS["task"].items()),
        "pervin_released_official_task_changed",
    )
    groups = sorted(
        str(pk)
        for pk in e.model("workload.TeachingTaskRow")
        .objects.get(pk=spec.PINS["row_id"])
        .groups.values_list("pk", flat=True)
    )
    require(
        groups == sorted(p["group_id"] for p in spec.PINS["offerings"].values()), "pervin_exact_two_groups_required"
    )
    assignments = e.bounded(
        e.model("workload.TeacherAssignment").objects.filter(organization=org, row_id=spec.PINS["row_id"]), cap=2
    )
    _pins(assignments, spec.PINS["assignments"])
    query = Q(pk__in=[])
    for p in spec.PINS["bridges"]:
        query |= Q(entity_type=p["entity_type"], legacy_pk=p["legacy_pk"])
    bridges = e.bounded(
        e.model("legacy_import.LegacyEntityMap").objects.filter(query, organization=org, source_system="myedu_mariadb"),
        cap=5,
    )
    expected = {(p["entity_type"], p["legacy_pk"]): p for p in spec.PINS["bridges"]}
    require(
        len(bridges) == len(expected)
        and all(
            (r["entity_type"], r["legacy_pk"]) in expected
            and all(r[k] == v for k, v in expected[(r["entity_type"], r["legacy_pk"])].items())
            for r in bridges
        ),
        "pervin_typed_source_identity_changed",
    )
    for obj in objects:
        active = e.bounded(
            e.model("registrar.Enrollment")._base_manager.filter(organization=org, offering=obj, status="enrolled"),
            cap=100,
        )
        require(
            sorted(r["student_id"] for r in active) == spec.PINS["rosters"][str(obj.pk)]
            and all(r["superseded_by_id"] is None for r in active),
            "pervin_exact_source_roster_changed",
        )
    return objects, bridges


def projected(raw, created):
    result = {}
    for label, rows in raw.items():
        pk = e.model(label)._meta.pk.attname
        rows = [r for r in rows if str(r[pk]) not in created.get(label, [])]
        if rows:
            result[label] = {"count": len(rows), "sha256": e.digest(rows)}
    return result


def snapshot(org, actor, *, children=None, archived=False):
    objects, bridges = _scope(org, actor)
    children = children or []
    require(
        not children or len(children) == 2 and {c["offering"] for c in children} == set(spec.COURSES),
        "pervin_exact_created_source_set_required",
    )
    created, versions = {}, []
    for obj in objects:
        child = next((r for r in children if r["offering"] == str(obj.pk)), None)
        selected = syllabus_for_offering(
            organization=org,
            offering_id=obj.pk,
            subject_id=obj.subject_id,
            period_id=obj.period_id,
            instructor_id=spec.PINS["teacher"],
        )
        syllabi = list(e.model("syllabus.Syllabus").objects.select_for_update().filter(organization=org, offering=obj))
        if child is None:
            require(not syllabi and selected is None, "pervin_existing_syllabus_no_overwrite")
            continue
        require(
            len(syllabi) == 1 and str(syllabi[0].pk) == child["syllabus"], "pervin_created_syllabus_binding_changed"
        )
        syllabus = syllabi[0]
        rows = list(
            e.model("syllabus.SyllabusVersion").objects.select_for_update().filter(organization=org, syllabus=syllabus)
        )
        require(len(rows) == 1 and str(rows[0].pk) == child["version"], "pervin_added_version_requires_review")
        version = rows[0]
        data = section_data_map(version)
        require(
            syllabus.author_id == spec.PINS["teacher"]
            and syllabus.subject_id == obj.subject_id
            and syllabus.period_id == obj.period_id
            and syllabus.is_active is not archived
            and version.status == ("archived" if archived else "approved")
            and version.approval_source == "migration"
            and version.approved_by_id is None
            and version.plan_hours == {"lecture": 30, "seminar": 30, "practical": 0, "lab": 0}
            and version.decision_reason == spec.NOTE
            and content_fingerprints(data)["canonical_body_sha256"] == spec.BODY_SHA
            and (
                selected is None
                if archived
                else selected is not None
                and selected.pk == syllabus.pk
                and approved_version_for(selected).pk == version.pk
            ),
            "pervin_exact_original60_approved_body_changed",
        )
        sections = e.bounded(
            e.model("syllabus.SyllabusSection").objects.filter(organization=org, version=version), cap=10
        )
        require(len(sections) == 10, "pervin_exact_ten_source_sections_required")
        for label, ids in (
            ("syllabus.Syllabus", [str(syllabus.pk)]),
            ("syllabus.SyllabusVersion", [str(version.pk)]),
            ("syllabus.SyllabusSection", [str(r["id"]) for r in sections]),
        ):
            created.setdefault(label, []).extend(ids)
        versions.append(
            {
                "offering": str(obj.pk),
                "syllabus": core.metadata_digest(syllabus),
                "version": core.metadata_digest(version),
                "sections": e.digest(sections),
            }
        )
    exams = e.bounded(
        e.model("exams.Exam")
        ._base_manager.filter(organization=org)
        .filter(Q(subject_id=spec.PINS["subject"]) | Q(author_id=spec.PINS["teacher"])),
        cap=100,
    )
    roots = {
        "registrar.CourseOffering": list(spec.COURSES),
        "workload.TeachingTaskRow": [spec.PINS["row_id"]],
        "exams.Exam": [r["id"] for r in exams],
    }
    raw = e.graph(spec.ORG, roots)
    for oid, expected in spec.PINS["counts"].items():
        actual = {
            "enrollments": sum(r["offering_id"] == oid for r in raw.get("registrar.Enrollment", [])),
            "lessons": sum(r["offering_id"] == oid for r in raw.get("registrar.Lesson", [])),
        }
        lessons = {r["id"] for r in raw.get("registrar.Lesson", []) if r["offering_id"] == oid}
        actual["marks"] = sum(r["lesson_id"] in lessons for r in raw.get("registrar.LessonMark", []))
        require(all(actual[k] == expected[k] for k in actual), "pervin_reviewed_academic_counts_changed")

    memberships = e.bounded(
        e.model("organizations.Membership").objects.filter(organization=org, user_id=spec.PINS["teacher"]), cap=20
    )
    protected = projected(raw, created)
    protected["teacher_authority"] = {
        "memberships": memberships,
        "roles": e.bounded(
            e.model("organizations.Role").objects.filter(pk__in=[r["role_id"] for r in memberships]), cap=20
        ),
        "profile": e.bounded(
            e.model("accounts.UserProfile").objects.filter(organization=org, user_id=spec.PINS["teacher"]), cap=1
        ),
        "bridges": bridges,
    }
    protected["source_scope_metadata"] = {
        "groups": e.bounded(
            e.model("organizations.OrgUnit").objects.filter(organization=org, pk__in=[o.group_id for o in objects]),
            cap=2,
        ),
        "subject": e.bounded(
            e.model("registrar.Subject").objects.filter(organization=org, pk=spec.PINS["subject"]), cap=1
        ),
        "period": e.bounded(
            e.model("organizations.AcademicPeriod").objects.filter(organization=org, pk=spec.PERIOD), cap=1
        ),
        "task": core.metadata_digest(
            e.model("workload.TeachingTask").objects.get(pk=spec.PINS["task"]["id"], organization=org)
        ),
    }
    return {"protected": protected, "created": created, "versions": versions}, objects
