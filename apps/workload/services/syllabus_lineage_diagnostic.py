"""Fixed 027 encrypted pointer forensics in a fresh tenant RR READ ONLY transaction.

No body/section queries, pointer mutation, cycle repair or usable content export.
The ordinary content collector's strict cycle rejection is intentionally untouched.
"""

import json

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

from apps.syllabus.public import approved_version_for, syllabus_for_offering
from core.rls import apply_rls_request_context

from . import syllabus_lineage_spec as spec
from .scoped_snapshot import SnapshotError
from .syllabus_content_export.collect import exact_get
from .syllabus_content_export.limits import bounded, query_budget
from .syllabus_content_export.projection import OFFERING_FIELDS, VERSION_ENUMS, digest, fields, raw_record


def _model(label):
    return apps.get_model(label)


def _closure(syllabi, versions):
    sy, ve = {str(s.pk): s for s in syllabi}, {str(v.pk): v for v in versions}
    for _ in range(spec.MAX_DEPTH):
        wanted_s = {str(v.syllabus_id) for v in ve.values()}
        wanted_s |= {str(s.reused_from_id) for s in sy.values() if s.reused_from_id}
        added_s = exact_get("syllabus.Syllabus", wanted_s - sy.keys(), spec.MAX_SYLLABI)
        sy.update((str(s.pk), s) for s in added_s)
        wanted_v = {str(v.source_version_id) for v in ve.values() if v.source_version_id}
        for s in sy.values():
            wanted_v.update(str(pk) for pk in (s.current_version_id, s.approved_version_id) if pk)
        approved = bounded(
            _model("syllabus.SyllabusVersion").objects.filter(
                organization_id=spec.ORG, syllabus_id__in=sy, status="approved"
            ),
            spec.MAX_VERSIONS,
        )
        wanted_v.update(str(v.pk) for v in approved)
        added_v = exact_get("syllabus.SyllabusVersion", wanted_v - ve.keys(), spec.MAX_VERSIONS)
        ve.update((str(v.pk), v) for v in added_v)
        if len(sy) > spec.MAX_SYLLABI or len(ve) > spec.MAX_VERSIONS:
            raise SnapshotError("syllabus_lineage_budget_exceeded")
        if not added_s and not added_v:
            return sy, ve
    raise SnapshotError("syllabus_lineage_depth_exceeded")


def collect(selection):
    ids = {row["id"] for row in selection["offerings"]}
    if not 1 <= len(ids) <= spec.MAX_COURSES or len(ids) != len(selection["offerings"]):
        raise SnapshotError("syllabus_root_scope_invalid")
    roots = exact_get("registrar.CourseOffering", ids, spec.MAX_COURSES)
    if (
        any(str(o.period_id) != spec.PERIOD for o in roots)
        or not _model("organizations.AcademicPeriod")
        .objects.filter(pk=spec.PERIOD, organization_id=spec.ORG, academic_year=spec.YEAR)
        .exists()
    ):
        raise SnapshotError("syllabus_root_period_mismatch")
    owned = bounded(
        _model("syllabus.Syllabus").objects.filter(organization_id=spec.ORG, offering_id__in=ids), spec.MAX_SYLLABI
    )
    chosen, effective, root_rows = [], [], []
    for offering in roots:
        doc = syllabus_for_offering(
            organization=spec.ORG,
            offering_id=offering.pk,
            subject_id=offering.subject_id,
            period_id=offering.period_id,
            instructor_id=offering.instructor_id,
            _metadata_only=True,
        )
        if doc is not None and str(doc.organization_id) != spec.ORG:
            raise SnapshotError("syllabus_closure_tenant_mismatch")
        version = approved_version_for(doc, metadata_only=True)
        if version is not None and str(version.organization_id) != spec.ORG:
            raise SnapshotError("syllabus_closure_tenant_mismatch")
        if doc:
            chosen.append(doc)
        if version:
            effective.append(version)
        root_rows.append(
            dict(
                offering_id=offering.pk,
                selected_syllabus_id=doc.pk if doc else None,
                effective_approved_version_id=version.pk if version else None,
            )
        )
    sy, ve = _closure([*owned, *chosen], effective)
    if any(str(o.organization_id) != spec.ORG for o in [*sy.values(), *ve.values()]):
        raise SnapshotError("syllabus_closure_tenant_mismatch")
    if any(
        getattr(version, key) not in VERSION_ENUMS[key]
        for version in ve.values()
        for key in ("status", "approval_source")
    ):
        raise SnapshotError("syllabus_version_enum_unknown")
    contexts = exact_get(
        "registrar.CourseOffering", ids | {str(s.offering_id) for s in sy.values() if s.offering_id}, spec.MAX_COURSES
    )
    data = {
        "roots": root_rows,
        "offerings": [fields(o, OFFERING_FIELDS) for o in contexts],
        "syllabi": [
            {**fields(o, spec.SYLLABUS_FIELDS), "record_sha256": digest(raw_record(o))} for _, o in sorted(sy.items())
        ],
        "versions": [
            {**fields(o, spec.VERSION_FIELDS), "record_sha256": digest(raw_record(o))} for _, o in sorted(ve.items())
        ],
    }
    data["edges"], data["cycles"], data["owner_mismatches"] = spec.graph(data["syllabi"], data["versions"])
    return data


def capture(username):
    selection = spec.selection()
    if connection.vendor != "postgresql" or connection.in_atomic_block:
        raise SnapshotError("fresh_postgresql_transaction_required")
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            cursor.execute("SET LOCAL statement_timeout = '120s'")
        with query_budget():
            apply_rls_request_context(user_id=None, org_id=spec.ORG, bypass=False, local=True)
            if (
                not _model("organizations.Organization")
                .objects.filter(pk=spec.ORG, is_active=True, status="active")
                .exists()
            ):
                raise SnapshotError("active_fixed_tenant_required")
            actor = (
                get_user_model()
                .objects.filter(
                    Q(profile__organization_id=spec.ORG)
                    | Q(memberships__organization_id=spec.ORG, memberships__is_active=True)
                    | Q(owned_organizations__pk=spec.ORG),
                    username=username,
                    is_active=True,
                    is_superuser=True,
                )
                .values_list("pk", flat=True)
                .first()
            )
            if actor is None:
                raise SnapshotError("active_fixed_tenant_superuser_required")
            apply_rls_request_context(user_id=actor, org_id=spec.ORG, bypass=False, local=True)
            data = collect(selection)
            with connection.cursor() as cursor:
                cursor.execute("SHOW transaction_read_only")
                if cursor.fetchone()[0] != "on":
                    raise SnapshotError("readonly_transaction_required")
            result = dict(
                format=spec.FORMAT,
                organization_id=spec.ORG,
                period_id=spec.PERIOD,
                academic_year=spec.YEAR,
                batch=spec.BATCH,
                registry_sha256=spec.REGISTRY_SHA,
                captured_at=timezone.now().isoformat(),
                actor_id=actor,
                read_only=True,
                eligible_for_apply=False,
                selection=selection,
                coverage=dict(
                    closure_complete=True,
                    truncated=False,
                    bodies_included=False,
                    absence_claim=False,
                    normal_content_export_usable=False,
                ),
                data=data,
                counts={key: len(rows) for key, rows in data.items()},
            )
            if len(json.dumps(result, cls=DjangoJSONEncoder).encode()) > spec.MAX_BYTES:
                raise SnapshotError("syllabus_output_byte_budget_exceeded")
            return result
