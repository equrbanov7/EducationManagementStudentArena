"""Six fixed contact journals' existing rights/provenance; diagnostic evidence only."""

import hashlib
import json
import re

from django.apps import apps
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Q

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
SOURCES = {
    "0ad85d3e-a9a3-480e-926a-68a384cb2435": {
        "case_code": "az_onomastics",
        "official_source_sha256": "765ff7cfa1a8999e98c7b2ea169df4cd204a0d36dd66a9982041982f5764aeff",
        "teacher_ids": [7824, 9526],
    },
    "4fee5132-a7ff-4f9f-b4d9-93c22f54bdfc": {
        "case_code": "az_morphology",
        "official_source_sha256": "765ff7cfa1a8999e98c7b2ea169df4cd204a0d36dd66a9982041982f5764aeff",
        "teacher_ids": [7824, 7958],
    },
    "7effa191-f9c6-420c-9a6d-bd2b75f872a7": {
        "case_code": "tarix_europe",
        "official_source_sha256": "57f0fdb5babaa7ab693c5623426982ac268a84691702fac6b68610f567bd3f9d",
        "teacher_ids": [7885],
    },
    "86236c69-0011-46e3-88a4-0e5124290d0f": {
        "case_code": "tarix_region",
        "official_source_sha256": "57f0fdb5babaa7ab693c5623426982ac268a84691702fac6b68610f567bd3f9d",
        "teacher_ids": [7885, 9524],
    },
    "dfb06cc3-4b48-47ea-a90d-d15ef5e840ca": {
        "case_code": "az_morphology",
        "official_source_sha256": "765ff7cfa1a8999e98c7b2ea169df4cd204a0d36dd66a9982041982f5764aeff",
        "teacher_ids": [7824, 7958],
    },
    "e3071d54-4e9a-48fb-8243-5fcd293f590e": {
        "case_code": "az_onomastics",
        "official_source_sha256": "765ff7cfa1a8999e98c7b2ea169df4cd204a0d36dd66a9982041982f5764aeff",
        "teacher_ids": [7824, 9526],
    },
}
MAX_ROWS = 2500
BATCH = re.compile(r"(?:shares-[0-9]{8}-[0-9]{6}-[a-f0-9]{4}|kindshare-[a-f0-9]{12})")
KINDS = {"lecture", "seminar", "lab", "practical", "consultation", "exam"}


def sha(value):
    return hashlib.sha256(json.dumps(value, cls=DjangoJSONEncoder, sort_keys=True).encode()).hexdigest()


def rows(query, fields=None):
    values = list(query.order_by("pk").values(*(fields or ()))[: MAX_ROWS + 1])
    if len(values) > MAX_ROWS:
        raise ValueError("contact_rights_scope_budget_exceeded")
    return values


def collect_contact_rights():
    Offering = apps.get_model("registrar.CourseOffering")
    Share = apps.get_model("registrar.JournalShare")
    Handover = apps.get_model("registrar.TeachingHandover")
    through = Share.enrollments.through
    offerings = rows(
        Offering.objects.filter(organization_id=ORG, pk__in=SOURCES),
        (
            "id",
            "organization_id",
            "subject_id",
            "period_id",
            "group_id",
            "instructor_id",
            "lesson_hours",
            "is_active",
        ),
    )
    shares = rows(Share.objects.filter(organization_id=ORG, offering_id__in=[v["id"] for v in offerings]))
    ids = [v["id"] for v in shares]
    links = rows(through.objects.filter(journalshare_id__in=ids))
    linked = {v["enrollment_id"] for v in links}
    Enrollment = apps.get_model("registrar.Enrollment")
    enrollments = rows(
        Enrollment.objects.filter(pk__in=linked),
        (
            "id",
            "organization_id",
            "offering_id",
            "student_id",
            "status",
            "superseded_by_id",
            "source_group_id",
        ),
    )
    enrollment_map = {v["id"]: v for v in enrollments}
    share_map = {v["id"]: v for v in shares}
    if set(enrollment_map) != linked or any(
        str(enrollment_map[v["enrollment_id"]]["organization_id"]) != ORG
        or enrollment_map[v["enrollment_id"]]["offering_id"] != share_map[v["journalshare_id"]]["offering_id"]
        for v in links
    ):
        raise ValueError("contact_rights_foreign_enrollment")
    share_output = []
    for value in shares:
        raw = value["kinds"]
        valid = isinstance(raw, list) and all(isinstance(kind, str) and kind in KINDS for kind in raw)
        batch = value["batch"]
        selected = sorted(str(v["enrollment_id"]) for v in links if v["journalshare_id"] == value["id"])
        share_output.append(
            {
                **{
                    key: value[key]
                    for key in (
                        "id",
                        "organization_id",
                        "offering_id",
                        "teacher_id",
                        "source",
                        "is_active",
                        "created_by_id",
                        "created_at",
                        "updated_at",
                    )
                },
                "kinds": raw if valid else [],
                "kinds_valid": valid,
                "kinds_sha256": sha(raw),
                "batch_code": batch if BATCH.fullmatch(batch or "") else None,
                "batch_present": bool(batch),
                "batch_sha256": sha(batch),
                "enrollment_ids": selected,
                "enrollments_restricted": bool(selected),
                "raw_record_sha256": sha(value),
                "rights_sha256": sha([raw, selected, value["teacher_id"], value["is_active"]]),
            }
        )
    handovers = rows(Handover.objects.filter(organization_id=ORG, offering_id__in=[v["id"] for v in offerings]))
    handover_output = [
        {
            **{
                key: value[key]
                for key in (
                    "id",
                    "organization_id",
                    "offering_id",
                    "from_instructor_id",
                    "to_instructor_id",
                    "performed_by_id",
                    "reverted_at",
                    "reverted_by_id",
                    "created_at",
                    "updated_at",
                )
            },
            "reason_present": bool(value["reason"]),
            "revert_reason_present": bool(value["revert_reason"]),
            "raw_record_sha256": sha(value),
        }
        for value in handovers
    ]
    batches = {v["batch"] for v in shares if v["batch"]}
    object_ids = {str(v["id"]) for v in [*shares, *handovers]}
    Audit = apps.get_model("audit.AuditLog")
    audits = rows(
        Audit.objects.filter(organization_id=ORG).filter(
            Q(
                resource_type__in=(
                    "registrar.JournalShare",
                    "registrar.TeachingHandover",
                    "registrar.journalshare",
                    "registrar.teachinghandover",
                ),
                resource_id__in=object_ids,
            )
            | Q(resource_type="registrar.journal_shares_batch", resource_id__in=batches)
            | Q(
                content_type__app_label="registrar",
                content_type__model__in=("journalshare", "teachinghandover"),
                object_id__in=object_ids,
            )
        ),
        (
            "id",
            "organization_id",
            "user_id",
            "action",
            "resource_type",
            "resource_id",
            "object_id",
            "old_values",
            "new_values",
            "reason",
            "created_at",
        ),
    )
    audit_output = []
    for value in audits:
        body = value["new_values"] if isinstance(value["new_values"], dict) else {}
        hashes = sorted(
            {
                v
                for k, v in body.items()
                if k in {"sha256", "source_sha256", "source_sha"}
                and isinstance(v, str)
                and re.fullmatch(r"[a-f0-9]{64}", v)
            }
        )
        created = body.get("created")
        deactivated = body.get("deactivated")
        updated = body.get("updated")
        audit_output.append(
            {
                **{key: value[key] for key in ("id", "organization_id", "user_id", "action", "created_at")},
                "resource_kind": "batch" if value["resource_type"] == "registrar.journal_shares_batch" else "object",
                "resource_id_sha256": sha(value["resource_id"]),
                "target_object_ids": sorted({v for v in (value["resource_id"], value["object_id"]) if v in object_ids}),
                "batch_code": (
                    value["resource_id"]
                    if value["resource_type"] == "registrar.journal_shares_batch"
                    and BATCH.fullmatch(value["resource_id"] or "")
                    else None
                ),
                "source_sha256s": hashes,
                "reason_present": bool(value["reason"]),
                "created_share_ids": (
                    sorted(set(map(str, created)) & set(map(str, ids))) if isinstance(created, list) else []
                ),
                "deactivated_share_ids": (
                    sorted(set(map(str, deactivated)) & set(map(str, ids))) if isinstance(deactivated, list) else []
                ),
                "updated_share_ids": sorted(set(updated) & set(map(str, ids))) if isinstance(updated, dict) else [],
                "old_values_sha256": sha(value["old_values"]),
                "new_values_sha256": sha(value["new_values"]),
                "selected_record_sha256": sha(value),
            }
        )
    count = len(offerings) + len(shares) + len(links) + len(enrollments) + len(handovers) + len(audits)
    if count > MAX_ROWS:
        raise ValueError("contact_rights_scope_budget_exceeded")
    return {
        "repair_contact_rights_scope": [
            {
                "organization_id": ORG,
                "offering_ids": sorted(SOURCES),
                "teacher_ids": sorted({uid for v in SOURCES.values() for uid in v["teacher_ids"]}),
                "official_source_sha256s": sorted({v["official_source_sha256"] for v in SOURCES.values()}),
                "root_offering_ids": sorted(str(v["id"]) for v in offerings),
                "metadata_rows": count,
                "automatic_apply_authority": False,
            }
        ],
        "repair_contact_sources": [{"offering_id": key, **value} for key, value in sorted(SOURCES.items())],
        "repair_contact_offerings": offerings,
        "repair_contact_shares": share_output,
        "repair_contact_share_rows": links,
        "repair_contact_enrollments": enrollments,
        "repair_contact_handovers": handover_output,
        "repair_contact_share_audits": audit_output,
    }
