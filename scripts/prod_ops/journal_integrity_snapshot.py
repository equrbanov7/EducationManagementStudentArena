"""Fixed WCU journal/syllabus/QB audit: repeatable-read, read-only, encrypted output.

Run through the dedicated one-off workflow. No grades, counters or links are changed.
Only named academic fields are exported; credentials and contact details are excluded.
"""

import base64
import gzip
import hashlib
import json
import os
from pathlib import Path

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection, transaction
from django.db.models import Count, Q
from django.utils import timezone

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from apps.syllabus.public import approved_version_for, student_syllabus_map, syllabus_for_offering
from core.rls import bypass_rls

ORG = "526cfa63-4f80-4bba-a7a7-61c8fbb3d918"
YEAR = "2026/2027"
DATA = {}
SCHEMA_GAPS = {}


def model(label):
    return apps.get_model(label)


def read(label, fields, *, key=None, limit=300000, tenant_field="organization_id", **filters):
    cls = model(label)
    with connection.cursor() as cursor:
        columns = {item.name for item in connection.introspection.get_table_description(cursor, cls._meta.db_table)}
    available = {field.attname for field in cls._meta.concrete_fields if field.column in columns}
    wanted = fields.split()
    missing = sorted(set(wanted) - available)
    if missing:
        SCHEMA_GAPS[label] = missing
    names = [name for name in wanted if name in available]
    tenant_fields = (tenant_field,) if isinstance(tenant_field, str) else tenant_field
    scope = Q(pk__in=())
    for field in tenant_fields:
        scope |= Q(**{field: ORG})
    query = cls._base_manager.filter(scope, **filters).order_by("pk")
    rows = list(query.values(*names)[: limit + 1])
    if len(rows) > limit:
        raise ValueError("audit_row_budget_exceeded:" + label)
    DATA[key or label] = rows
    return rows


def ids(rows):
    return [row["id"] for row in rows]


def collect():
    org = model("organizations.Organization").objects.get(pk=ORG, slug="qku", is_active=True)
    read(
        "organizations.AcademicPeriod",
        "id name academic_year period_type start_date end_date is_current is_active opening_status",
    )
    offerings = model("registrar.CourseOffering")._base_manager.filter(organization_id=ORG)
    DATA["offering_universe"] = list(
        offerings.values("period_id", "is_active", "assessment_scheme__is_published").annotate(count=Count("id"))
    )
    selected = offerings.filter(
        Q(period__academic_year=YEAR) | Q(is_active=True, assessment_scheme__is_published=False)
    )
    offering_ids = list(selected.values_list("pk", flat=True))
    read(
        "legacy_import.LegacyEntityMap",
        "id entity_type target_model_label target_pk legacy_pk state",
        entity_type="course_offering",
        target_pk__in=[str(pk) for pk in offering_ids],
    )
    offered = read(
        "registrar.CourseOffering",
        "id organization_id subject_id period_id group_id instructor_id lesson_hours is_active course_format starts_on ends_on created_at updated_at",
        id__in=offering_ids,
    )
    read("registrar.AssessmentScheme", "id offering_id is_published approval_status", offering_id__in=offering_ids)
    enrollments = read(
        "registrar.Enrollment",
        "id student_id offering_id status kind superseded_by_id absence_hours legacy_qb_fail source_group_id created_at updated_at added_at",
        offering_id__in=offering_ids,
    )
    enrollment_ids = ids(enrollments)
    students = {row["student_id"] for row in enrollments}
    read(
        "registrar.Lesson",
        "id offering_id date kind topic syllabus_week hours start_time end_time instructor_id created_by_id is_legacy_synthesised off_schedule_reason created_at updated_at",
        offering_id__in=offering_ids,
    )
    read(
        "registrar.LessonMark",
        "id lesson_id enrollment_id status score entered_by_id created_at updated_at",
        enrollment_id__in=enrollment_ids,
        limit=2000000,
    )
    read(
        "registrar.AbsenceCredit",
        "id enrollment_id hours reverses_id old_absence_hours new_absence_hours created_at",
        enrollment_id__in=enrollment_ids,
    )
    read("registrar.FinalGrade", "id enrollment_id exam_score is_published", enrollment_id__in=enrollment_ids)
    read("registrar.ResitRecord", "id enrollment_id reason status resit_score", enrollment_id__in=enrollment_ids)
    read(
        "registrar.StudentAcademicRecord",
        "id student_id program_id curriculum_id group_id status is_active national_athlete_exemption",
        student_id__in=students,
    )
    read("registrar.Program", "id name code absence_limit_percent is_active")
    read(
        "registrar.LegacyExcuseDocument",
        "id student_id starts_on ends_on mapping_status source_pk",
        student_id__in=students,
    )
    tasks = read("workload.TeachingTask", "id chair_id academic_year status updated_at", academic_year=YEAR)
    rows = read(
        "workload.TeachingTaskRow",
        "id task_id period_id subject_id subject_text season row_kind groups_text specialty_id faculty_id education_form degree_level lecture_plan lecture_total seminar_plan seminar_total lab_plan lab_total total_hours union_count subgroup_count student_count intensive_offering_id review_status updated_at",
        task_id__in=ids(tasks),
    )
    assignments = read(
        "workload.TeacherAssignment",
        "id row_id teacher_id activity hours groups_note updated_at",
        row_id__in=ids(rows),
    )
    DATA["workload_groups"] = list(
        model("workload.TeachingTaskRow")
        .objects.filter(organization_id=ORG, id__in=ids(rows))
        .order_by("id", "groups__id")
        .values("id", "groups__id")
    )
    read("organizations.OrgUnit", "id name code parent_id unit_type is_active settings")
    read("registrar.Subject", "id code name chair_unit_id is_active")
    read(
        "registrar.ScheduleSlot",
        "id offering_id weekday start_time end_time kind instructor_id week_type is_deleted is_parked",
        offering_id__in=offering_ids,
    )
    shares = read(
        "registrar.JournalShare", "id offering_id teacher_id kinds is_active source", offering_id__in=offering_ids
    )
    syl_shares = read("syllabus.SyllabusShare", "id offering_id syllabus_id source", offering_id__in=offering_ids)
    periods = {row["period_id"] for row in offered}
    subject_ids = {row["subject_id"] for row in offered} | {row["subject_id"] for row in rows if row["subject_id"]}
    syllabi_ids = list(
        model("syllabus.Syllabus")
        .objects.filter(organization_id=ORG)
        .filter(
            Q(offering_id__in=offering_ids)
            | Q(pk__in=[r["syllabus_id"] for r in syl_shares])
            | Q(subject_id__in=subject_ids, period_id__in=periods)
            | Q(subject_id__in=subject_ids, period__isnull=True)
        )
        .values_list("pk", flat=True)
    )
    syllabi = read(
        "syllabus.Syllabus",
        "id subject_id period_id offering_id author_id chair_unit_id current_version_id approved_version_id reused_from_id plan_hours_override is_active updated_at",
        id__in=syllabi_ids,
    )
    versions = read(
        "syllabus.SyllabusVersion",
        "id syllabus_id major minor status change_kind applies_to_period_id source_version_id plan_hours completion_percent approval_source updated_at",
        syllabus_id__in=syllabi_ids,
    )
    selected_versions = {r[f] for r in syllabi for f in ("current_version_id", "approved_version_id") if r[f]}
    selected_versions |= {r["id"] for r in versions if r["status"] == "approved"}
    read(
        "syllabus.SyllabusSection",
        "id version_id section_id data is_complete updated_at",
        version_id__in=selected_versions,
    )
    people = students | {r["instructor_id"] for r in offered} | {r["teacher_id"] for r in assignments + shares}
    people |= {r["author_id"] for r in syllabi}
    DATA["people"] = list(
        get_user_model()
        .objects.filter(pk__in=people)
        .order_by("pk")
        .values("id", "first_name", "last_name", "is_active")
    )
    active = list(selected.filter(is_active=True).select_related("organization"))
    student_map = student_syllabus_map(org, active)
    resolved = []
    for offering in active:
        syllabus = syllabus_for_offering(
            organization=org,
            offering_id=offering.pk,
            subject_id=offering.subject_id,
            period_id=offering.period_id,
            instructor_id=offering.instructor_id,
            _metadata_only=True,
        )
        approved = approved_version_for(syllabus, metadata_only=True)
        resolved.append(
            {
                "offering_id": offering.pk,
                "teacher_syllabus_id": syllabus.pk if syllabus else None,
                "teacher_approved_version_id": approved.pk if approved else None,
                "student_syllabus_id": student_map.get(offering.pk),
            }
        )
    DATA["resolved_syllabi"] = resolved
    from scripts.prod_ops.journal_audit_scores import collect_scores

    collect_scores(read=read, model=model, data=DATA, organization_id=ORG, current_offering_ids=offering_ids)


def main():
    public = serialization.load_pem_public_key(base64.b64decode(os.environ["AUDIT_PUBLIC_KEY_B64"]))
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            cursor.execute("SET LOCAL statement_timeout = '60s'")
            cursor.execute(
                "SELECT current_timestamp, current_setting('transaction_read_only'), txid_current_snapshot()"
            )
            started, readonly, snapshot_id = cursor.fetchone()
        if readonly != "on":
            raise ValueError("readonly_required")
        with bypass_rls():
            collect()
        DATA["metadata"] = {
            "organization_id": ORG,
            "academic_year": YEAR,
            "captured_at": started,
            "finished_at": timezone.now(),
            "read_only": True,
            "snapshot_id": snapshot_id,
            "scope": "All 2026/2027 offerings plus active unpublished journals in other periods; "
            "all tenant final/resit/score-entry/legacy-grade evidence and online attempt/appeal history",
            "schema_gaps": SCHEMA_GAPS,
        }
    raw = json.dumps(DATA, cls=DjangoJSONEncoder, ensure_ascii=False, separators=(",", ":")).encode()
    key, nonce = os.urandom(32), os.urandom(12)
    aad = b"wcu-journal-integrity-audit/20261104"
    cipher = AESGCM(key).encrypt(nonce, gzip.compress(raw), aad)
    wrapped = public.encrypt(
        key, padding.OAEP(mgf=padding.MGF1(hashes.SHA256()), algorithm=hashes.SHA256(), label=None)
    )
    envelope = {
        "format": aad.decode(),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "nonce": base64.b64encode(nonce).decode(),
        "wrapped_key": base64.b64encode(wrapped).decode(),
        "ciphertext": base64.b64encode(cipher).decode(),
    }
    output = Path(os.environ["AUDIT_OUTPUT"])
    with output.open("x", encoding="utf-8") as stream:
        json.dump(envelope, stream)
    output.chmod(0o600)
    print(json.dumps({"read_only": True, "counts": {k: len(v) for k, v in DATA.items() if isinstance(v, list)}}))


if __name__ == "__main__":
    main()
