"""Read/lock the complete connected graph; only the older provenance FK is mutable."""

from django.db.models import Q

from apps.syllabus.public import content_fingerprints, lock_source_lineage

from . import reviewed_aydin_lineage_spec as spec
from .reviewed_ilahe_subject_state import actor_scope as validated_actor_scope
from .reviewed_leyla_catalog_graph import RepairError, bounded, digest, graph, model, require


def actor_scope(org, actor):
    try:
        lock_source_lineage(org.pk)
        validated_actor_scope(org, actor)
    except Exception:
        raise RepairError("aydin_actor_scope_refused") from None


def _audit_anchors(org):
    query = model("audit.AuditLog")._base_manager.filter(organization=org)
    anchors = {}
    for version, audit_id in spec.CREATE_AUDITS.items():
        row = query.select_for_update().filter(pk=audit_id).first()
        require(
            row is not None
            and row.resource_type == "syllabus.version"
            and row.resource_id == version
            and row.user_id == spec.AUTHOR
            and row.created_at.isoformat() == spec.AUDIT_CREATED[audit_id]
            and row.old_values is None
            and row.action == "create"
            and row.new_values == {"status": "draft", "version": "v1.0"}
            and not row.changes,
            "aydin_creation_anchor_changed",
        )
        anchors[version] = str(row.pk)
    row = query.select_for_update().filter(pk=spec.COPY_AUDIT).first()
    require(
        row is not None
        and row.resource_type == "syllabus.version"
        and row.resource_id == spec.NEWER
        and row.user_id == spec.AUTHOR
        and row.created_at.isoformat() == spec.AUDIT_CREATED[spec.COPY_AUDIT]
        and row.old_values is None
        and row.action == "update"
        and row.new_values == {"kind": "copied", "status": "draft", "version": "v1.0"}
        and row.changes
        == {
            "reuse": "copy",
            "week_adjusted": True,
            "source_version": "v1.0",
            "source_syllabus": spec.OWNERS[spec.OLDER],
        },
        "aydin_copy_anchor_changed",
    )
    # Include every current resource audit, including a later in-place copy, as hashes.
    # Neither its text nor its provenance is deleted; unexpected concurrent changes stop apply.
    history = bounded(query.filter(Q(resource_id__in=spec.OWNERS) | Q(resource_id__in=spec.OWNERS.values())), cap=200)
    return {"anchors": anchors, "copy_anchor": str(row.pk), "count": len(history), "sha256": digest(history)}


def snapshot(org):
    versions = list(
        model("syllabus.SyllabusVersion")._base_manager.select_for_update().filter(organization=org, pk__in=spec.OWNERS)
    )
    require({str(v.pk) for v in versions} == set(spec.OWNERS), "aydin_fixed_versions_changed")
    by_id = {str(v.pk): v for v in versions}
    older, newer = by_id[spec.OLDER], by_id[spec.NEWER]
    require(
        str(newer.source_version_id) == spec.OLDER
        and (older.source_version_id is None or str(older.source_version_id) == spec.NEWER),
        "aydin_fixed_versions_changed",
    )
    for version in versions:
        key = str(version.pk)
        require(
            str(version.syllabus_id) == spec.OWNERS[key]
            and version.status == "draft"
            and version.change_kind == "copied"
            and version.created_by_id == spec.AUTHOR
            and (version.major, version.minor) == (1, 0)
            and str(version.applies_to_period_id) == spec.PERIOD
            and version.created_at.isoformat() == spec.CREATED[key],
            "aydin_fixed_versions_changed",
        )
        owner = (
            model("syllabus.Syllabus")._base_manager.select_for_update().get(pk=version.syllabus_id, organization=org)
        )
        require(
            owner.author_id == spec.AUTHOR
            and str(owner.subject_id) == spec.SUBJECT
            and str(owner.period_id) == spec.PERIOD
            and str(owner.offering_id) == spec.OFFERINGS[key]
            and str(owner.current_version_id) == key
            and owner.approved_version_id is None
            and owner.reused_from_id is None
            and owner.is_active,
            "aydin_fixed_owners_changed",
        )
        sections = bounded(model("syllabus.SyllabusSection")._base_manager.filter(version=version), cap=20)
        body = content_fingerprints({r["section_id"]: r["data"] for r in sections})
        require(len(sections) == 10 and body["canonical_body_sha256"] == spec.BODY[key], "aydin_body_changed")
    records = graph(
        str(org.pk),
        {
            "syllabus.SyllabusVersion": set(spec.OWNERS),
            "syllabus.Syllabus": set(spec.OWNERS.values()),
            "registrar.CourseOffering": set(spec.OFFERINGS.values()),
        },
    )
    enrs = [row["id"] for row in records.get("registrar.Enrollment", [])]
    lessons = [row["id"] for row in records.get("registrar.Lesson", [])]
    soft_roots = {}
    for label, predicate in (
        ("registrar.JournalCorrection", Q(enrollment_ref__in=enrs) | Q(lesson_ref__in=lessons)),
        ("registrar.LessonCorrection", Q(lesson_id__in=lessons) | Q(lesson_id__isnull=True)),
    ):
        rows = bounded(model(label)._base_manager.filter(organization=org).filter(predicate), cap=500)
        soft_roots[label] = {row["id"] for row in rows}
    if any(soft_roots.values()):
        soft_graph = graph(str(org.pk), soft_roots)
        for label, rows in soft_graph.items():
            existing = {row["id"]: row for row in records.get(label, [])}
            existing.update({row["id"]: row for row in rows})
            records[label] = sorted(existing.values(), key=lambda row: str(row["id"]))
    protected = {}
    for label, rows in records.items():
        values = [dict(row) for row in rows]
        if label == "syllabus.SyllabusVersion":
            for row in values:
                if row["id"] == spec.OLDER:
                    row.pop("source_version_id")
        protected[label] = {"count": len(values), "sha256": digest(values)}
    accounts = {}
    for label, kwargs in (
        ("auth.User", {"pk": spec.AUTHOR}),
        ("accounts.UserProfile", {"user_id": spec.AUTHOR}),
        ("organizations.Membership", {"user_id": spec.AUTHOR}),
    ):
        rows = bounded(model(label)._base_manager.filter(**kwargs), cap=100)
        accounts[label] = {"count": len(rows), "sha256": digest(rows)}
    return {
        "corrected": older.source_version_id is None,
        "historical_evidence_sha256": spec.HISTORICAL_EVIDENCE_SHA,
        "graph": protected,
        "accounts": accounts,
        "history": _audit_anchors(org),
    }
