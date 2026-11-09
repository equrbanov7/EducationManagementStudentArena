"""Fixed tenant: current lesson cells and all-period final/paper evidence."""

import hashlib
import json
from pathlib import Path

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db.models import CharField, Q
from django.db.models.functions import Cast

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
PERIOD = "a4f88744-8d49-4772-84ef-c28a96c3b372"
SYLLABUS_BODY_POLICY = "metadata-only-bodies-deferred-to-native-connected-batches/1"
SCHEMA_FILE = Path(__file__).with_name("schemas.json")
SCHEMAS = json.loads(SCHEMA_FILE.read_text())
# Bounded core: identity, maps, enrollment, lesson, mark, correction, load and
# syllabus headers only. Omitted tables are undeclared, never empty.
CORE_SCHEMA_FILE = Path(__file__).with_name("schemas_core.json")
CORE_SCHEMAS = json.loads(CORE_SCHEMA_FILE.read_text())
SCOPES = {"full": (SCHEMA_FILE, SCHEMAS), "core": (CORE_SCHEMA_FILE, CORE_SCHEMAS)}
CORE_MAP_ROUTE_SCOPE = "direct_and_offering_only"


def schemas_for(scope):
    if scope not in SCOPES:
        raise ValueError("fixed_capture_scope_required")
    return SCOPES[scope][1]


def schema_digest(scope="full"):
    if scope not in SCOPES:
        raise ValueError("fixed_capture_scope_required")
    return hashlib.sha256(SCOPES[scope][0].read_bytes()).hexdigest()


def current_exam_ids():
    return (
        apps.get_model("exams", "Exam")
        .objects.filter(organization_id=ORG)
        .filter(
            Q(journal_offerings__period_id=PERIOD)
            | Q(start_datetime__gte="2026-09-01T00:00:00+04:00", start_datetime__lt="2027-02-01T00:00:00+04:00")
            | Q(created_at__gte="2026-09-01T00:00:00+04:00", created_at__lt="2027-02-01T00:00:00+04:00")
        )
        .values("pk")
        .distinct()
    )


def scoped_query(label, spec, scope="full"):
    schemas = schemas_for(scope)
    if label not in schemas or schemas[label] != spec:
        raise ValueError("fixed_schema_required")
    if label == "auth.User":
        return (
            get_user_model()
            .objects.filter(Q(profile__organization_id=ORG) | Q(memberships__organization_id=ORG))
            .distinct()
        )
    model = apps.get_model(label)
    # Timetable recovery needs the retained rows of earlier soft deletions.
    # Keep the same fixed tenant/period filters; application reads stay unchanged.
    manager = model.all_objects if label == "registrar.ScheduleSlot" else model.objects
    query = manager.filter(**{spec["org_path"]: ORG})
    if spec["period_path"]:
        query = query.filter(**{spec["period_path"]: PERIOD})
    if spec["filters"]:
        query = query.filter(**spec["filters"])
    if spec.get("exam_path"):
        query = query.filter(**{spec["exam_path"] + "__in": current_exam_ids()})
    if label == "syllabus.SyllabusSection":
        if spec.get("body_policy") != SYLLABUS_BODY_POLICY:
            raise ValueError("fixed_schema_required")
    if label in {"legacy_import.LegacyEntityMap", "legacy_import.LegacyEntityMapVersion"}:
        # Historical final rows need canonical offering/enrollment map versions.
        # Lesson/mark routes stay current-period, matching the bounded cell tables.
        direct = [
            "auth.user",
            "accounts.user",
            "organizations.orgunit",
            "organizations.academicperiod",
            "registrar.subject",
            "syllabus.syllabus",
        ]
        offerings = apps.get_model("registrar", "CourseOffering").objects.filter(organization_id=ORG)
        ids = offerings.annotate(text_id=Cast("pk", CharField())).values("text_id")
        routes = Q(target_model_label__in=direct) | Q(target_model_label="registrar.courseoffering", target_pk__in=ids)
        # The bounded core keeps only identity/offering routes; per-cell map rows
        # (enrollment, lesson, mark targets) are the full capture's own scope.
        cell_targets = (
            ()
            if spec.get("route_scope") == CORE_MAP_ROUTE_SCOPE
            else (
                ("Enrollment", ""),
                ("Lesson", "offering__period_id"),
                ("LessonMark", "enrollment__offering__period_id"),
            )
        )
        for target, path in cell_targets:
            scope = {path: PERIOD} if path else {}
            target_ids = (
                apps.get_model("registrar", target)
                .objects.filter(organization_id=ORG, **scope)
                .annotate(text_id=Cast("pk", CharField()))
                .values("text_id")
            )
            routes |= Q(target_model_label="registrar." + target.lower(), target_pk__in=target_ids)
        maps = apps.get_model("legacy_import", "LegacyEntityMap")
        versions = apps.get_model("legacy_import", "LegacyEntityMapVersion")
        # Canonical remaps are immutable versions. Include both directions and
        # every version of a selected map, including a latest quarantined target.
        version_roots = versions.objects.filter(organization_id=ORG).filter(routes).values("entity_map_id")
        roots = maps.objects.filter(organization_id=ORG).filter(routes | Q(pk__in=version_roots)).values("pk")
        query = query.filter(**{"pk__in" if label.endswith("LegacyEntityMap") else "entity_map_id__in": roots})
    if label == "audit.AuditLog":
        query = query.filter(
            Q(resource_type__startswith="registrar.")
            | Q(resource_type__startswith="legacy_import.")
            | Q(resource_type__startswith="workload.")
            | Q(resource_type__startswith="syllabus.")
            # Native twin merge/restore logs identify their object via the
            # GenericForeignKey and intentionally leave resource_type blank.
            | Q(content_type__app_label__in=("registrar", "workload", "syllabus", "legacy_import"))
        )
    return query
