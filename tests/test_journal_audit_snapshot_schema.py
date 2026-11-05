"""The production snapshot must run against the migrated schema without writes."""

from django.db import connection, transaction

import pytest

from apps.registrar.models import Enrollment, FinalGrade, ResitRecord, Subject
from apps.syllabus.tests.factories import activate_member, make_academic_stack, make_offering, make_org
from core.rls import bypass_rls
from scripts.prod_ops import journal_integrity_snapshot as snapshot


@pytest.mark.django_db(transaction=True)
def test_snapshot_uses_actual_schema_and_excludes_other_tenants(monkeypatch):
    org = make_org("qku")
    stack = make_academic_stack(org, code="AUDIT-SCOPE")
    type(stack["period"]).objects.filter(pk=stack["period"].pk).update(academic_year="2026/2027")
    offering = make_offering(org, stack, None)
    historical = make_offering(org, make_academic_stack(org, code="HISTORICAL-RESIT"), None)
    type(historical).objects.filter(pk=historical.pk).update(is_active=False)
    activate_member(org, org.owner, "student")
    enrollment = Enrollment.objects.create(organization=org, offering=historical, student=org.owner)
    ResitRecord.objects.create(
        organization=org, enrollment=enrollment, reason="exam", status="completed", resit_score=35
    )
    assert not FinalGrade.objects.filter(enrollment=enrollment).exists()
    other = make_org("other-audit-org")
    foreign = Subject.objects.create(organization=other, code="FOREIGN", name="Must stay private")
    monkeypatch.setattr(snapshot, "ORG", str(org.pk))
    monkeypatch.setattr(snapshot, "DATA", {})
    monkeypatch.setattr(snapshot, "SCHEMA_GAPS", {})
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        with bypass_rls():
            snapshot.collect()
    assert not snapshot.SCHEMA_GAPS
    assert offering.pk in {row["id"] for row in snapshot.DATA["registrar.CourseOffering"]}
    assert historical.pk not in {row["id"] for row in snapshot.DATA["registrar.CourseOffering"]}
    assert historical.pk in {row["id"] for row in snapshot.DATA["final_offerings"]}
    assert enrollment.pk in {row["id"] for row in snapshot.DATA["final_enrollments"]}
    assert foreign.pk not in {row["id"] for row in snapshot.DATA["registrar.Subject"]}
    assert "registrar.ExamScoreEntry" in snapshot.DATA
    assert "appeals.ScoreAdjustment" in snapshot.DATA
