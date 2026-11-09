"""One tenant and entire active period, captured without writes or with deterministic locks."""

from django.apps import apps
from django.db.models import Q

from . import class_history
from .manifest import MAX_ROWS, digest, normalize, require


def model(name):
    return apps.get_model("registrar", name)


def read(query, lock):
    if lock:
        query = query.select_for_update(of=("self",))
    result = list(query.order_by("pk").values()[: MAX_ROWS + 1])
    require(len(result) <= MAX_ROWS, "live_scope_budget")
    return normalize(result)


def capture_class_history(result, *, organization, plan, lock):
    sources = plan["sources"]
    requested = [row for row in sources if row.get("class_authority_sha256") and row.get("slot")]
    keys = ("corrections", "reversals", "audits")
    for key in keys:
        result["class_history_" + key] = []
    if not requested:
        return
    dates = {row["slot"]["date"] for row in requested}
    corrections = read(
        model("LessonCorrection")
        .objects.filter(organization=organization, created_at__gte=class_history.CORRECTION_FROM)
        .filter(Q(old_date__in=dates) | Q(new_date__in=dates)),
        lock,
    )
    reversals = read(
        model("CorrectionReversal").objects.filter(
            organization=organization,
            created_at__gte=class_history.CORRECTION_FROM,
            lesson_correction_id__in=[row["id"] for row in corrections],
        ),
        lock,
    )
    audit_types = Q()
    for prefix in class_history.AUDIT_PREFIXES:
        audit_types |= Q(resource_type__startswith=prefix)
    audits = read(
        apps.get_model("audit", "AuditLog").objects.filter(
            audit_types, organization=organization, created_at__gte=class_history.AUDIT_FROM
        ),
        lock,
    )
    history = {"corrections": corrections, "reversals": reversals, "audits": audits, "lessons": result["lessons"]}
    courses = {row["id"]: row for row in result["offerings"]}
    retained = {key: {} for key in keys}
    routes = {row["key"]: row["offering_id"] for row in plan["routes"]}
    seen = set()
    for source in requested:
        # A route key is proven separately by Planner; retain every possible
        # current target's closure, so ambiguous routing cannot hide history.
        candidates = set(source.get("candidate_offering_ids", []))
        candidates.update(routes[key] for key in source.get("route_keys", []) if key in routes)
        for oid in sorted(candidates):
            identity = (oid, str(source["slot"]["date"]))
            if identity in seen:
                continue
            seen.add(identity)
            course = courses.get(oid)
            if course is None:
                continue
            scope = class_history.relevant(history, course=course, slot=source["slot"])
            for key in keys:
                retained[key].update({row["id"]: row for row in scope[key]})
    for key in keys:
        result["class_history_" + key] = sorted(retained[key].values(), key=lambda row: row["id"])


def capture(*, organization, actor, plan, lock=False):
    require(str(organization.pk) == plan["organization_id"] and organization.is_active, "tenant_mismatch")
    require(actor.is_active and actor.is_superuser, "active_superadmin_required")
    require(
        len(read(actor.__class__.objects.filter(pk=actor.pk, is_active=True, is_superuser=True), lock)) == 1,
        "actor_changed",
    )
    profile = apps.get_model("accounts", "UserProfile").objects.filter(user_id=actor.pk)
    profiles = read(profile, lock)
    require(
        len(profiles) == 1
        and profiles[0]["organization_id"] == str(organization.pk)
        and profiles[0]["access_state"] == "active"
        and not profiles[0]["is_deleted"]
        and profiles[0]["blocked_at"] is None,
        "actor_tenant_mismatch",
    )
    periods = read(organization.academic_periods.filter(pk=plan["period_id"]), lock)
    require(
        len(periods) == 1 and periods[0]["is_active"] and periods[0]["is_current"] and periods[0]["locked_at"] is None,
        "period_unavailable",
    )
    courses = read(
        model("CourseOffering").objects.filter(organization=organization, period_id=plan["period_id"], is_active=True),
        lock,
    )
    ids = [row["id"] for row in courses]
    require(set(ids) == set(plan["offering_ids"]), "full_live_offering_scope_changed")
    result = {"period": periods, "offerings": courses}
    for name, key, lookup in (
        ("Enrollment", "enrollments", "offering_id__in"),
        ("Lesson", "lessons", "offering_id__in"),
        ("AssessmentScheme", "schemes", "offering_id__in"),
        ("AssessmentComponent", "components", "offering_id__in"),
        ("LabGroup", "lab_groups", "offering_id__in"),
        ("SeminarGroup", "seminar_groups", "offering_id__in"),
    ):
        result[key] = read(model(name).objects.filter(organization=organization, **{lookup: ids}), lock)
    enrollment_ids = [r["id"] for r in result["enrollments"]]
    lesson_ids = [r["id"] for r in result["lessons"]]
    component_ids = [r["id"] for r in result["components"]]
    result["history_enrollments"] = read(
        model("Enrollment").objects.filter(organization=organization, superseded_by_id__in=enrollment_ids), lock
    )
    history_ids = [row["id"] for row in result["history_enrollments"]]
    history_offerings = {row["offering_id"] for row in result["history_enrollments"]} - set(ids)
    result["history_offerings"] = read(
        model("CourseOffering").objects.filter(organization=organization, pk__in=history_offerings), lock
    )
    result["history_lessons"] = read(
        model("Lesson").objects.filter(organization=organization, offering_id__in=history_offerings), lock
    )
    result["history_marks"] = read(
        model("LessonMark").objects.filter(organization=organization, enrollment_id__in=history_ids), lock
    )
    result["absence_credits"] = read(
        model("AbsenceCredit").objects.filter(
            organization=organization, enrollment_id__in=enrollment_ids + history_ids
        ),
        lock,
    )
    for name, key, lookup, values in (
        ("LessonMark", "marks", "enrollment_id__in", enrollment_ids),
        ("ComponentScore", "component_scores", "enrollment_id__in", enrollment_ids),
        ("JournalCorrection", "journal_corrections", "enrollment_ref__in", enrollment_ids),
        ("LessonCorrection", "lesson_corrections", "lesson_id__in", lesson_ids),
        ("ComponentScoreCorrection", "component_corrections", "component_id__in", component_ids),
        ("JournalHygieneDecision", "hygiene", "enrollment_id__in", enrollment_ids),
    ):
        result[key] = read(model(name).objects.filter(organization=organization, **{lookup: values}), lock)
    ledger = apps.get_model("legacy_import", "LegacyEntityMap")
    requested = Q(entity_type="student", legacy_pk__in={str(row["legacy_student_id"]) for row in plan["sources"]})
    for entity, field in (
        ("course_offering", "legacy_offering_key"),
        ("lesson_subject", "legacy_subject_id"),
        ("group_unit", "legacy_group_id"),
        ("worker", "legacy_teacher_id"),
    ):
        requested |= Q(entity_type=entity, legacy_pk__in={str(row[field]) for row in plan["routes"] if field in row})
    requested |= Q(
        pk__in={
            row.get("import_proof", {}).get("map_id")
            for row in plan["sources"]
            if row.get("import_proof", {}).get("map_id")
        }
    )
    result["ledger"] = read(
        ledger.objects.filter(requested, organization=organization, source_system=plan["source_system"]),
        lock,
    )
    result["ledger_versions"] = read(
        apps.get_model("legacy_import", "LegacyEntityMapVersion").objects.filter(
            organization=organization, entity_map_id__in=[row["id"] for row in result["ledger"]]
        ),
        lock,
    )
    result["migration_runs"] = read(
        apps.get_model("legacy_import", "LegacyMigrationRun").objects.filter(
            organization=organization,
            pk__in={row["created_run_id"] for row in result["ledger"]}
            | {row["recorded_run_id"] for row in result["ledger_versions"]},
        ),
        lock,
    )
    audit_ids = {
        row.get("import_proof", {}).get("audit_id")
        for row in plan["sources"]
        if row.get("import_proof", {}).get("audit_id")
    }
    audit = apps.get_model("audit", "AuditLog")
    result["creation_audits"] = read(
        audit.objects.filter(organization=organization).filter(
            Q(pk__in=audit_ids) | Q(changes__undo_of__in=list(audit_ids)) | Q(new_values__undo_of__in=list(audit_ids))
        ),
        lock,
    )
    capture_class_history(result, organization=organization, plan=plan, lock=lock)
    require(
        all(row["organization_id"] == str(organization.pk) for rows in result.values() for row in rows),
        "cross_tenant_live_row",
    )
    return result


def baseline(snapshot):
    return digest(snapshot)
