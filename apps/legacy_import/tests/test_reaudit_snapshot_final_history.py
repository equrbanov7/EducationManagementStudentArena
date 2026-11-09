"""Synthetic historical paper/final evidence; tenant isolation and cell bounds."""

import datetime as dt
import hashlib
import zlib
from collections import defaultdict

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import connection, transaction

import pytest

from apps.legacy_import.services.reaudit_snapshot.queries import ORG, PERIOD, SCHEMAS, scoped_query
from core.rls import apply_rls_request_context, bypass_rls, journal_unlock

HISTORICAL = (
    "organizations.AcademicPeriod",
    "registrar.CourseOffering",
    "registrar.Enrollment",
    "registrar.FinalGrade",
    "registrar.ResitRecord",
    "registrar.ExamScoreEntry",
    "registrar.ExamScoreSheet",
    "registrar.LegacyGradeFact",
    "registrar.LegacyGradeReview",
    "registrar.LegacyGradeArtifact",
)


def create(label, **fields):
    return apps.get_model(label).objects.create(**fields)


def fact(org, enrollment, source_pk):
    return create(
        "registrar.LegacyGradeFact",
        organization=org,
        enrollment=enrollment,
        source_system="synthetic",
        source_table="journals_dates_points",
        source_pk=source_pk,
        source_snapshot_sha256="1" * 64,
        source_row_hash="2" * 64,
        materialization_digest="3" * 64,
        transform_version="test-v1",
        evidence_kind="exam",
        score_code="im",
        mapping_status="linked" if enrollment else "unresolved",
        mapping_issue_code="" if enrollment else "legacy_grade_fact_unresolved",
        source_enrollment_ref=f"synthetic-journal:{source_pk}" if enrollment else "",
        source_student_ref=str(source_pk),
        source_journal_ref="synthetic-journal",
        exam_score=21,
    )


@pytest.fixture
def world():
    kept, excluded = defaultdict(set), defaultdict(set)
    current_cells = defaultdict(set)
    with bypass_rls(), journal_unlock():
        actor = get_user_model().objects.create_superuser("synthetic-history-operator", password="synthetic")
        for tenant in ("kept", "foreign"):
            org = create(
                "organizations.Organization",
                **({"id": ORG} if tenant == "kept" else {}),
                name=tenant,
                slug="synthetic-history-" + tenant,
                owner=actor,
                status="active",
                is_active=True,
            )
            expected = kept if tenant == "kept" else excluded
            teacher = get_user_model().objects.create_user("synthetic-teacher-" + tenant)
            student = get_user_model().objects.create_user("synthetic-student-" + tenant)
            for user, role_name, permissions in (
                (teacher, "teacher", ["grade.input"]),
                (student, "student", []),
                (actor, "org_admin", ["final_score.entry"]),
            ):
                role, _ = apps.get_model("organizations.Role").objects.get_or_create(
                    organization=org,
                    name=role_name,
                    defaults={"display_name": role_name, "permissions": permissions},
                )
                create("organizations.Membership", organization=org, user=user, role=role, is_active=True)
            group = create(
                "organizations.OrgUnit", organization=org, name="Synthetic", slug="synthetic", unit_type="group"
            )
            subject = create("registrar.Subject", organization=org, code="SYN", name="Synthetic")
            for index, historical in enumerate((False, True), 1):
                period = create(
                    "organizations.AcademicPeriod",
                    **({"id": PERIOD} if tenant == "kept" and not historical else {}),
                    organization=org,
                    name="Historical" if historical else "Current",
                    academic_year="2025/2026" if historical else "2026/2027",
                    period_type="semester",
                    start_date=dt.date(2025 if historical else 2026, 9, 15),
                    end_date=dt.date(2026 if historical else 2027, 1, 15),
                    is_current=not historical,
                )
                offering = create(
                    "registrar.CourseOffering",
                    organization=org,
                    subject=subject,
                    period=period,
                    group=group,
                    instructor=teacher,
                )
                enrollment = create("registrar.Enrollment", organization=org, offering=offering, student=student)
                grade = create("registrar.FinalGrade", organization=org, enrollment=enrollment, exam_score=21)
                resit = create(
                    "registrar.ResitRecord",
                    organization=org,
                    enrollment=enrollment,
                    reason="total",
                    status="completed",
                    resit_score=25,
                )
                sheet = create("registrar.ExamScoreSheet", organization=org, offering=offering, created_by=actor)
                entry = create(
                    "registrar.ExamScoreEntry",
                    organization=org,
                    enrollment=enrollment,
                    sheet=sheet,
                    entered_by=actor,
                    kind="appeal",
                    assessment="final",
                    old_score=20,
                    new_score=21,
                    note="Synthetic documented change",
                )
                source = fact(org, enrollment, index)
                review = create(
                    "registrar.LegacyGradeReview",
                    organization=org,
                    fact=source,
                    decision="verified",
                    reason_code="exam_center_corrected",
                    evidence_digest="4" * 64,
                    reviewed_by=actor,
                )
                payload = b"synthetic-private-binary"
                artifact = create(
                    "registrar.LegacyGradeArtifact",
                    organization=org,
                    source_system="myedu_mariadb",
                    source_table="balvereqi_logs",
                    source_pk=index,
                    source_snapshot_sha256="1" * 64,
                    source_row_hash="2" * 64,
                    materialization_digest="3" * 64,
                    transform_version="test-v1",
                    artifact_kind="score_sheet_export",
                    source_owner_ref=str(actor.pk),
                    source_journal_ref="synthetic-journal",
                    source_exported_at_text="2026-01-01 00:00:00",
                    payload_sha256=hashlib.sha256(payload).hexdigest(),
                    payload_size_bytes=len(payload),
                    payload_zlib=zlib.compress(payload),
                )
                for obj in (period, offering, enrollment, grade, resit, sheet, entry, source, review, artifact):
                    expected[obj._meta.label].add(str(obj.pk))
                lesson = create(
                    "registrar.Lesson",
                    organization=org,
                    offering=offering,
                    date=period.start_date,
                    kind="seminar",
                    hours=2,
                )
                mark = create(
                    "registrar.LessonMark",
                    organization=org,
                    lesson=lesson,
                    enrollment=enrollment,
                    status="present",
                )
                if tenant == "kept" and not historical:
                    current_cells[lesson._meta.label].add(str(lesson.pk))
                    current_cells[mark._meta.label].add(str(mark.pk))
            source = fact(org, None, 3)
            expected[source._meta.label].add(str(source.pk))
    return actor, kept, excluded, current_cells


@pytest.mark.django_db(transaction=True)
def test_all_period_final_paper_evidence_and_reference_closure(world):
    assert connection.vendor == "postgresql"
    actor, kept, excluded, _ = world
    with transaction.atomic():
        apply_rls_request_context(user_id=actor.pk, org_id=ORG, bypass=False, local=True)
        rows = {
            label: list(scoped_query(label, SCHEMAS[label]).values(*SCHEMAS[label]["fields"])) for label in HISTORICAL
        }
    ids = {label: {str(row["id"]) for row in values} for label, values in rows.items()}
    for label in HISTORICAL:
        assert ids[label] == kept[label]
        assert not ids[label] & excluded[label]
    for row in rows["registrar.CourseOffering"]:
        assert str(row["period_id"]) in ids["organizations.AcademicPeriod"]
    for row in rows["registrar.Enrollment"]:
        assert str(row["offering_id"]) in ids["registrar.CourseOffering"]
    for label in ("registrar.FinalGrade", "registrar.ResitRecord", "registrar.ExamScoreEntry"):
        assert all(str(row["enrollment_id"]) in ids["registrar.Enrollment"] for row in rows[label])
    assert all(str(row["sheet_id"]) in ids["registrar.ExamScoreSheet"] for row in rows["registrar.ExamScoreEntry"])
    assert all(str(row["fact_id"]) in ids["registrar.LegacyGradeFact"] for row in rows["registrar.LegacyGradeReview"])
    assert sum(row["enrollment_id"] is None for row in rows["registrar.LegacyGradeFact"]) == 1


@pytest.mark.django_db(transaction=True)
def test_historical_final_scope_does_not_expand_lesson_cells(world):
    actor, _, _, expected = world
    with transaction.atomic():
        apply_rls_request_context(user_id=actor.pk, org_id=ORG, bypass=False, local=True)
        for label in ("registrar.Lesson", "registrar.LessonMark"):
            rows = list(scoped_query(label, SCHEMAS[label]).values(*SCHEMAS[label]["fields"]))
            assert {str(row["id"]) for row in rows} == expected[label]


def test_artifact_and_review_export_metadata_without_payload_or_names():
    assert "payload_zlib" not in SCHEMAS["registrar.LegacyGradeArtifact"]["fields"]
    assert "payload_sha256" in SCHEMAS["registrar.LegacyGradeArtifact"]["fields"]
    assert "reviewed_by_name" not in SCHEMAS["registrar.LegacyGradeReview"]["fields"]
    assert "evidence_digest" in SCHEMAS["registrar.LegacyGradeReview"]["fields"]
    assert all(not SCHEMAS[label]["period_path"] for label in HISTORICAL)
