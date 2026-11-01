"""Bounded canonical resolver + complete selected/current/approved/lineage closure."""

import json

from django.apps import apps
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import F, Func, IntegerField, Q, Sum, TextField
from django.db.models.functions import Cast

from apps.syllabus.public import approved_version_for, syllabus_for_offering

from ..scoped_snapshot import SnapshotError
from . import projection as project
from . import spec
from .limits import bounded


def model(label):
    return apps.get_model(label)


def ensure_tenant(objects):
    if any(str(obj.organization_id) != spec.ORG for obj in objects):
        raise SnapshotError("syllabus_closure_tenant_mismatch")


def exact_get(label, ids, limit):
    if not ids:
        return []
    objects = bounded(model(label).objects.filter(pk__in=ids), limit)
    if {str(o.pk) for o in objects} != set(map(str, ids)):
        raise SnapshotError("syllabus_lineage_reference_missing")
    ensure_tenant(objects)
    return objects


def closure(syllabi, versions):
    """Only referenced current/approved/source ancestry; visited IDs terminate legitimate forks."""
    sy, ve = {str(s.pk): s for s in syllabi}, {str(v.pk): v for v in versions}
    for _ in range(spec.MAX_CLOSURE_DEPTH):
        need_s = {str(v.syllabus_id) for v in ve.values()}
        need_s |= {str(s.reused_from_id) for s in sy.values() if s.reused_from_id}
        added_s = exact_get("syllabus.Syllabus", need_s - sy.keys(), spec.MAX_SYLLABI)
        sy.update((str(s.pk), s) for s in added_s)
        need_v = {str(v.source_version_id) for v in ve.values() if v.source_version_id}
        for s in sy.values():
            need_v.update(str(v) for v in (s.current_version_id, s.approved_version_id) if v)
        # Include the real approved fallback when a stored pointer is absent/stale.
        approved = bounded(
            model("syllabus.SyllabusVersion").objects.filter(syllabus_id__in=sy, status="approved"), spec.MAX_VERSIONS
        )
        ensure_tenant(approved)
        need_v.update(str(v.pk) for v in approved)
        added_v = exact_get("syllabus.SyllabusVersion", need_v - ve.keys(), spec.MAX_VERSIONS)
        ve.update((str(v.pk), v) for v in added_v)
        if len(sy) > spec.MAX_BODY_SYLLABI or len(ve) > spec.MAX_VERSIONS:
            raise SnapshotError("syllabus_lineage_budget_exceeded")
        if not added_s and not added_v:
            for syllabus in sy.values():
                for pointer in (syllabus.current_version_id, syllabus.approved_version_id):
                    if pointer and ve[str(pointer)].syllabus_id != syllabus.pk:
                        raise SnapshotError("syllabus_version_owner_mismatch")
            # Explicitly reject cycles, rather than silently call them complete.
            for objects, attr in ((sy, "reused_from_id"), (ve, "source_version_id")):
                for start in objects:
                    seen, current = set(), start
                    while current in objects:
                        if current in seen:
                            raise SnapshotError("syllabus_lineage_cycle")
                        seen.add(current)
                        target = getattr(objects[current], attr)
                        current = str(target) if target else None
            return sy, ve
    raise SnapshotError("syllabus_lineage_depth_exceeded")


def ledger(offering_ids, subject_ids, author_ids, syllabus_ids, version_ids, section_ids, group_ids):
    targets = {
        "registrar.courseoffering": offering_ids,
        "registrar.subject": subject_ids,
        "auth.user": author_ids,
        "syllabus.syllabus": syllabus_ids,
        "syllabus.syllabusversion": version_ids,
        "syllabus.syllabussection": section_ids,
        "organizations.orgunit": group_ids,
    }
    query = Q(pk__in=[])
    for label, ids in targets.items():
        query |= Q(target_model_label=label, target_pk__in=list(map(str, ids)))
    values = bounded(
        model("legacy_import.LegacyEntityMap").objects.filter(organization_id=spec.ORG).filter(query), spec.MAX_LEDGER
    )
    entity_codes = {
        "worker",
        "subject",
        "group_unit",
        "syllabus",
        "syllabus_version",
        "syllabus_section",
        "journal",
        "course_offering",
    }
    return [
        {
            "id": v.pk,
            "organization_id": v.organization_id,
            "source_system": "myedu_mariadb" if v.source_system == "myedu_mariadb" else None,
            "source_system_sha256": project.digest(v.source_system),
            "entity_type": v.entity_type if v.entity_type in entity_codes else None,
            "entity_type_sha256": project.digest(v.entity_type),
            "legacy_numeric_id": (
                int(v.legacy_pk) if v.legacy_pk.isascii() and v.legacy_pk.isdigit() and len(v.legacy_pk) <= 10 else None
            ),
            "legacy_pk_sha256": project.digest(v.legacy_pk),
            "target_model_label": v.target_model_label,
            "target_pk": v.target_pk,
            "state": v.state,
            "source_row_hash": v.source_row_hash,
            "record_sha256": project.digest(project.raw_record(v)),
        }
        for v in values
    ]


def collect(selection):
    selected = {row["id"] for row in selection["offerings"]}
    if not 1 <= len(selected) <= spec.MAX_COURSES or len(selected) != len(selection["offerings"]):
        raise SnapshotError("syllabus_root_scope_invalid")
    roots = exact_get("registrar.CourseOffering", selected, spec.MAX_COURSES)
    if (
        any(str(o.period_id) != spec.PERIOD for o in roots)
        or not model("organizations.AcademicPeriod")
        .objects.filter(pk=spec.PERIOD, organization_id=spec.ORG, academic_year=spec.YEAR)
        .exists()
    ):
        raise SnapshotError("syllabus_root_period_mismatch")
    subjects = {o.subject_id for o in roots}
    # Whole-tenant, all-author bases/unbound candidates, including NULL period and inactive dosyes.
    candidates = bounded(
        model("syllabus.Syllabus")
        .objects.filter(organization_id=spec.ORG, subject_id__in=subjects)
        .filter(Q(offering__isnull=True) | Q(offering_id__in=selected)),
        spec.MAX_SYLLABI,
    )
    owned = [s for s in candidates if str(s.offering_id) in selected]
    root_rows, chosen, effective = [], [], []
    for offering in roots:
        syllabus = syllabus_for_offering(
            organization=spec.ORG,
            offering_id=offering.pk,
            subject_id=offering.subject_id,
            period_id=offering.period_id,
            instructor_id=offering.instructor_id,
            _metadata_only=True,
        )
        version = approved_version_for(syllabus, metadata_only=True)
        if syllabus:
            ensure_tenant([syllabus])
            chosen.append(syllabus)
        if version:
            ensure_tenant([version])
            effective.append(version)
        root_rows.append(
            {
                "organization_id": spec.ORG,
                "offering_id": offering.pk,
                "selected_syllabus_id": syllabus.pk if syllabus else None,
                "current_version_id": syllabus.current_version_id if syllabus else None,
                "stored_approved_version_id": syllabus.approved_version_id if syllabus else None,
                "effective_approved_version_id": version.pk if version else None,
                "relation": (
                    "own"
                    if syllabus and syllabus.offering_id == offering.pk
                    else "external_or_base" if syllabus else "none"
                ),
                "lookup_complete": True,
                "base_candidates_complete": True,
                "base_candidate_count": sum(
                    s.subject_id == offering.subject_id and s.offering_id is None for s in candidates
                ),
            }
        )
    syllabi, versions = closure([*owned, *chosen], effective)
    all_syllabi = {str(s.pk): s for s in [*candidates, *syllabi.values()]}
    if len(all_syllabi) > spec.MAX_SYLLABI:
        raise SnapshotError("syllabus_candidate_budget_exceeded")
    shares = bounded(model("syllabus.SyllabusShare").objects.filter(offering_id__in=selected), spec.MAX_SYLLABI)
    cohorts = bounded(model("registrar.LanguageLevelCohort").objects.filter(offering_id__in=selected), spec.MAX_COURSES)
    ensure_tenant([*shares, *cohorts])
    share_candidates = exact_get(
        "syllabus.Syllabus", {str(s.syllabus_id) for s in shares} - all_syllabi.keys(), spec.MAX_SYLLABI
    )
    all_syllabi.update((str(s.pk), s) for s in share_candidates)
    if len(all_syllabi) > spec.MAX_SYLLABI:
        raise SnapshotError("syllabus_candidate_budget_exceeded")
    selected_map = {str(s.pk): s for s in chosen}
    for root in root_rows:
        selected_syllabus = selected_map.get(str(root["selected_syllabus_id"]))
        if selected_syllabus is None:
            root["relation"] = "none"
        elif str(selected_syllabus.offering_id) == str(root["offering_id"]):
            root["relation"] = "own"
        elif selected_syllabus.offering_id is None:
            root["relation"] = "base" if selected_syllabus.period_id is None else "subject_period"
        elif any(s.offering_id == root["offering_id"] and s.syllabus_id == selected_syllabus.pk for s in shares):
            root["relation"] = "shared"
        elif any(
            c.offering_id == root["offering_id"] and c.source_offering_id == selected_syllabus.offering_id
            for c in cohorts
        ):
            root["relation"] = "language_level_source"
        else:
            root["relation"] = "unknown"
    course_ids = (
        selected
        | {str(s.offering_id) for s in [*syllabi.values(), *share_candidates] if s.offering_id}
        | {str(c.source_offering_id) for c in cohorts if c.source_offering_id}
    )
    offerings = exact_get("registrar.CourseOffering", course_ids, spec.MAX_COURSES)
    sections_query = model("syllabus.SyllabusSection").objects.filter(version_id__in=versions)
    sizes = sections_query.annotate(
        _size=Func(Cast(F("data"), TextField()), function="octet_length", output_field=IntegerField())
    )
    if (sizes.aggregate(total=Sum("_size"))["total"] or 0) > spec.MAX_BODY_BYTES or sizes.filter(
        _size__gt=spec.MAX_SECTION_BYTES
    ).exists():
        raise SnapshotError("syllabus_source_body_byte_budget_exceeded")
    sections = bounded(sections_query, spec.MAX_SECTIONS)
    ensure_tenant(sections)
    raw_bytes = sum(len(json.dumps(s.data, cls=DjangoJSONEncoder).encode()) for s in sections)
    if raw_bytes > spec.MAX_BODY_BYTES:
        raise SnapshotError("syllabus_source_body_byte_budget_exceeded")
    data = {
        "roots": root_rows,
        "offerings": [project.fields(o, project.OFFERING_FIELDS) for o in offerings],
        "syllabi": [project.syllabus(s, str(s.pk) in syllabi) for _, s in sorted(all_syllabi.items())],
        "versions": [],
        "sections": [],
        "topics": [],
        "shares": [
            {
                **project.fields(s, project.SHARE_FIELDS),
                "effective": any(
                    r["offering_id"] == s.offering_id and r["selected_syllabus_id"] == s.syllabus_id for r in root_rows
                ),
                "record_sha256": project.digest(project.raw_record(s)),
            }
            for s in shares
        ],
        "cohorts": [
            {**project.fields(c, project.COHORT_FIELDS), "record_sha256": project.digest(project.raw_record(c))}
            for c in cohorts
        ],
    }
    for _, version in sorted(versions.items()):
        own_sections = [s for s in sections if s.version_id == version.pk]
        result, projected, topics = project.version(version, own_sections)
        data["versions"].append(result)
        data["sections"].extend(projected)
        data["topics"].extend(topics)
        if len(data["topics"]) > spec.MAX_TOPICS:
            raise SnapshotError("syllabus_topic_budget_exceeded")
    data["ledger"] = ledger(
        course_ids,
        subjects | {s.subject_id for s in syllabi.values()},
        {s.author_id for s in all_syllabi.values() if s.author_id}
        | {o.instructor_id for o in offerings if o.instructor_id},
        all_syllabi,
        versions,
        {s.pk for s in sections},
        {o.group_id for o in offerings if o.group_id},
    )
    if sum(map(len, data.values())) > spec.MAX_ROWS:
        raise SnapshotError("syllabus_total_row_budget_exceeded")
    return data
