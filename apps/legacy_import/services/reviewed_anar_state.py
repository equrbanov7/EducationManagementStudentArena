"""Closed graph for 28 reviewed own source lessons; no inferred future workload."""

import hashlib
import json
from pathlib import Path

from django.apps import apps
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection
from django.db.models import Q

from apps.registrar.public import schedule_lock

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
PERIOD = "a4f88744-8d49-4772-84ef-c28a96c3b372"
SUBJECT = "64c97c9c-ec80-409e-80bc-bdf4731683e2"
TEACHER = 9490
OFFERINGS = {
    "3a56acc0-cb00-43ba-976a-6eae2afbe666": "3ee0cd72-1aef-41f6-a000-2565a9f16d04",
    "8cc86c4b-eee6-43a8-ba18-5a69ab94e99b": "e2c74423-580a-4201-b35a-1babdf8ad3ad",
}
PINS = json.loads(Path(__file__).with_name("reviewed_anar_pins.json").read_text())
LIMIT = 20000


class RepairError(ValueError):
    pass


def require(condition, code):
    if not condition:
        raise RepairError("anar_" + code)


def model(label):
    return apps.get_model(label)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def rows(query):
    ids = list(query.select_for_update().order_by("pk").values_list("pk", flat=True)[: LIMIT + 1])
    require(len(ids) <= LIMIT, "row_budget")
    if not ids:
        return []
    cls = query.model
    table = connection.ops.quote_name(cls._meta.db_table)
    pk = connection.ops.quote_name(cls._meta.pk.column)
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT to_jsonb(t) FROM {table} t WHERE t.{pk}::text=ANY(%s) ORDER BY t.{pk}",
            [list(map(str, ids))],
        )
        return [json.loads(r[0]) if isinstance(r[0], str) else r[0] for r in cursor.fetchall()]


def raw_projection(query, fields):
    """Exactly the authenticated RAW codec; never used for native full-row preservation.

    DjangoJSONEncoder floors datetimes to milliseconds and encodes Decimal as a
    string. Full SQL graph/baseline retains all microseconds and database columns.
    """
    values = list(query.order_by("pk").values(*fields)[: LIMIT + 1])
    require(len(values) <= LIMIT, "row_budget")
    return json.loads(json.dumps(values, cls=DjangoJSONEncoder))


def graph(roots):
    pending = {k: set(map(str, v)) for k, v in roots.items()}
    seen, result = {}, {}
    while pending:
        label, ids = pending.popitem()
        ids -= seen.get(label, set())
        if not ids:
            continue
        cls = model(label)
        found = rows(cls._base_manager.filter(pk__in=ids))
        require(all(str(r.get("organization_id", ORG)) == ORG for r in found), "graph_tenant_changed")
        seen.setdefault(label, set()).update(ids)
        result.setdefault(label, []).extend(found)
        require(sum(map(len, result.values())) <= LIMIT, "graph_budget")
        for relation in cls._meta.get_fields(include_hidden=True):
            child = relation.related_model
            if not relation.auto_created or relation.concrete or child is None:
                continue
            lookup = relation.field.name if relation.many_to_many else relation.field.attname
            child_ids = list(
                child._base_manager.filter(**{lookup + "__in": ids}).values_list("pk", flat=True)[: LIMIT + 1]
            )
            require(len(child_ids) <= LIMIT, "graph_budget")
            pending.setdefault(child._meta.label, set()).update(map(str, child_ids))
    return {
        label: sorted(values, key=lambda r: str(r[model(label)._meta.pk.column]))
        for label, values in sorted(result.items())
    }


def actor_scope(organization, actor):
    require(connection.vendor == "postgresql", "postgresql_required")
    require(str(organization.pk) == ORG and actor.is_active and actor.is_superuser, "actor_scope_required")
    require(
        model("organizations.Organization")
        .objects.select_for_update()
        .filter(pk=ORG, is_active=True, status="active")
        .exists(),
        "active_tenant_required",
    )
    require(
        model("auth.User")
        .objects.select_for_update(of=("self",))
        .filter(pk=actor.pk, is_active=True, is_superuser=True)
        .filter(
            Q(profile__organization_id=ORG)
            | Q(memberships__organization_id=ORG, memberships__is_active=True)
            | Q(owned_organizations__pk=ORG)
        )
        .values("id")
        .first()
        is not None,
        "actor_tenant_required",
    )
    require(
        not model("accounts.UserProfile")
        .objects.filter(user_id=actor.pk)
        .exclude(is_deleted=False, deleted_at__isnull=True, blocked_at__isnull=True, access_state="active")
        .exists(),
        "actor_inactive",
    )
    schedule_lock.lock_schedule(ORG, PERIOD)


def snapshot():
    courses = list(
        model("registrar.CourseOffering")
        .objects.select_for_update(of=("self",))
        .select_related("period", "group")
        .filter(pk__in=OFFERINGS)
    )
    require(len(courses) == 2, "fixed_offerings_required")
    for course in courses:
        require(
            str(course.organization_id) == ORG
            and course.instructor_id == TEACHER
            and str(course.group_id) == OFFERINGS[str(course.pk)]
            and str(course.subject_id) == SUBJECT
            and str(course.period_id) == PERIOD
            and course.is_active
            and not course.is_intensive
            and course.lesson_hours == 75
            and course.period.organization_id == course.organization_id
            and course.period.is_active
            and course.period.is_current
            and course.period.locked_at is None
            and course.group.organization_id == course.organization_id
            and course.group.is_active,
            "fixed_offering_changed",
        )
    teacher = model("auth.User").objects.select_for_update().filter(pk=TEACHER, is_active=True).first()
    require(teacher is not None, "teacher_inactive")
    profile = (
        model("accounts.UserProfile")
        .objects.select_for_update()
        .filter(
            user_id=TEACHER,
            organization_id=ORG,
            is_deleted=False,
            deleted_at__isnull=True,
            blocked_at__isnull=True,
            access_state="active",
        )
        .first()
    )
    require(profile is not None, "teacher_profile_inactive")
    require(
        (teacher.first_name, teacher.last_name, profile.patronymic) == ("Anar", "Vəliyev", "Cümşüd"),
        "reviewed_identity_changed",
    )
    require(
        not model("registrar.TeachingHandover").objects.filter(offering_id__in=OFFERINGS).exists(),
        "handover_requires_review",
    )
    require(
        not model("registrar.JournalShare")
        .objects.filter(offering_id__in=OFFERINGS, is_active=True)
        .exclude(teacher_id=TEACHER)
        .exists(),
        "other_teacher_share",
    )
    groups = (
        set(OFFERINGS.values())
        | {str(c.group.parent_id) for c in courses}
        | {str((c.group.settings or {}).get("parent_group")) for c in courses}
    )
    load_rows = (
        model("workload.TeachingTaskRow")
        .objects.filter(organization_id=ORG, subject_id=SUBJECT, period_id=PERIOD, groups__pk__in=groups - {"None"})
        .distinct()
    )
    assignments = (
        model("workload.TeacherAssignment").objects.filter(row__in=load_rows, hours__gt=0).exclude(teacher_id=TEACHER)
    )
    require(not assignments.exists(), "other_positive_teacher_assignment")
    roots = {
        "registrar.CourseOffering": OFFERINGS,
        "workload.TeachingTaskRow": list(load_rows.values_list("pk", flat=True)),
    }
    students = list(
        model("registrar.Enrollment").objects.filter(offering_id__in=OFFERINGS).values_list("student_id", flat=True)
    )
    roots["registrar.StudentAcademicRecord"] = list(
        model("registrar.StudentAcademicRecord")
        ._base_manager.filter(organization_id=ORG, student_id__in=students)
        .values_list("pk", flat=True)
    )
    bridge = rows(
        model("legacy_import.LegacyEntityMap")._base_manager.filter(
            organization_id=ORG, entity_type="group_unit", legacy_pk__in=["788", "816"]
        )
    )
    expected_bridge = PINS["bridge"]
    require(
        len(bridge) == len(expected_bridge)
        and all(any(all(row.get(k) == value for k, value in pin.items()) for row in bridge) for pin in expected_bridge),
        "source_group_bridge_changed",
    )
    references = {
        "groups": rows(model("organizations.OrgUnit").objects.filter(pk__in=OFFERINGS.values())),
        "subject": rows(model("registrar.Subject").objects.filter(pk=SUBJECT)),
        "period": rows(model("organizations.AcademicPeriod").objects.filter(pk=PERIOD)),
        "tasks": rows(
            model("workload.TeachingTask").objects.filter(pk__in=load_rows.values_list("task_id", flat=True))
        ),
        "bridge": bridge,
    }
    data = graph(roots)
    lessons = data.get("registrar.Lesson", [])
    require({r["id"] for r in lessons} == set(PINS["lessons"]), "reviewed_lesson_inventory_changed")
    for row in lessons:
        require(
            all(row.get(k) == v for k, v in PINS["lessons"][row["id"]]["fields"].items()),
            "reviewed_source_lesson_changed",
        )
        require(row["instructor_id"] in (None, TEACHER), "other_lesson_instructor")
    authors = {r["instructor_id"] for r in lessons}
    require(len(authors) == 1, "partial_authorship_requires_review")
    projected_lessons = raw_projection(
        model("registrar.Lesson")._base_manager.filter(pk__in=PINS["lessons"]), PINS["lesson_fields"]
    )
    for row in projected_lessons:
        row["instructor_id"] = None
    require(
        digest(projected_lessons) == PINS["lessons_sha256"],
        "reviewed_raw_lessons_changed",
    )
    marks = data.get("registrar.LessonMark", [])
    projected_marks = raw_projection(
        model("registrar.LessonMark")._base_manager.filter(lesson_id__in=PINS["lessons"]), PINS["mark_fields"]
    )
    require(
        len(marks) == PINS["marks_count"] and digest(projected_marks) == PINS["marks_sha256"], "reviewed_cells_changed"
    )
    require(all(r["entered_by_id"] in (None, TEACHER) for r in marks), "other_mark_author")
    return {
        "graph": data,
        "references": references,
        "teacher": rows(model("auth.User").objects.filter(pk=TEACHER)),
        "profile": rows(model("accounts.UserProfile").objects.filter(pk=profile.pk)),
        "corrected": authors == {TEACHER},
    }
