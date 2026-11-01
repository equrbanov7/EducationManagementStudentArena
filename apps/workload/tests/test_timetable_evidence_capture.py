"""Fresh read-only PostgreSQL capture, including live slots and private metadata hashes."""

import datetime as dt
import json

from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext

import pytest

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar.models import CourseOffering, Lesson, ScheduleSlot, Subject
from apps.workload.models import TeacherAssignment, TeachingTask, TeachingTaskRow
from apps.workload.services.timetable_evidence.capture import capture
from apps.workload.services.timetable_evidence.contract import validate
from apps.workload.services.timetable_evidence.spec import ORG, PERIOD, selection
from core.rls import bypass_rls


@pytest.mark.django_db(transaction=True)
def test_fresh_capture_exports_full_kind_geometry_without_notes_grades_or_writes(monkeypatch):
    actor = get_user_model().objects.create_superuser("timetable.capture", password="test-only")
    with bypass_rls():
        org = Organization.objects.create(
            id=ORG,
            name="Timetable Evidence",
            slug="timetable-evidence",
            owner=actor,
            org_type="university",
            status="active",
            is_active=True,
        )
        Membership.objects.create(user=actor, organization=org, role=org.roles.get(name="teacher"), is_active=True)
        period = AcademicPeriod.objects.create(
            id=PERIOD,
            organization=org,
            name="Payız",
            academic_year="2026/2027",
            start_date=dt.date(2026, 9, 15),
            end_date=dt.date(2027, 2, 1),
        )
        selected = selection("timetable-review-008")
        subjects, groups, courses = {}, {}, []
        for i, root in enumerate(selected):
            if root["subject_id"] not in subjects:
                subjects[root["subject_id"]] = Subject.objects.create(
                    id=root["subject_id"], organization=org, code=f"TT{i}", name="Private subject"
                )
            if root["group_id"] not in groups:
                groups[root["group_id"]] = OrgUnit.objects.create(
                    id=root["group_id"], organization=org, name="Private group", slug=f"tt-{i}", unit_type="group"
                )
            courses.append(
                CourseOffering.objects.create(
                    id=root["id"],
                    organization=org,
                    period=period,
                    subject=subjects[root["subject_id"]],
                    group=groups[root["group_id"]],
                    instructor=actor,
                )
            )
        first = courses[0]
        slot = ScheduleSlot.all_objects.create(
            organization=org,
            offering=first,
            weekday=1,
            start_time=dt.time(8, 30),
            end_time=dt.time(10),
            kind="lecture",
            is_parked=True,
            park_reason="PRIVATE PARK REASON",
        )
        Lesson.objects.create(
            organization=org,
            offering=first,
            date=dt.date(2026, 10, 26),
            start_time=dt.time(8, 30),
            end_time=dt.time(10),
            kind="lecture",
            instructor=actor,
            topic="PRIVATE TOPIC",
            off_schedule_reason="PRIVATE OFF REASON",
        )
        chair = OrgUnit.objects.create(organization=org, name="Private chair", slug="tt-chair", unit_type="chair")
        extra = OrgUnit.objects.create(organization=org, name="Another group", slug="tt-extra", unit_type="group")
        task = TeachingTask.objects.create(organization=org, chair=chair, academic_year="2026/2027")
        row = TeachingTaskRow.objects.create(
            organization=org,
            task=task,
            subject=first.subject,
            period=period,
            lecture_plan=30,
            lecture_total=30,
            note="PRIVATE ROW",
            groups_text="PRIVATE TEXT",
        )
        row.groups.add(first.group, extra)
        TeacherAssignment.objects.create(
            organization=org,
            row=row,
            teacher=actor,
            activity="lecture",
            hours=30,
            note="PRIVATE ASSIGNMENT",
            groups_note="PRIVATE GROUPS NOTE",
        )
        from django.apps import apps

        apps.get_model("audit.AuditLog").objects.create(
            organization=org,
            user=actor,
            action="create",
            resource_type="registrar.ScheduleSlot",
            resource_id="PRIVATE FILE.docx",
            changes={"source": "import_timetable_docx", "created_ids": [str(slot.pk)]},
            reason="PRIVATE AUDIT REASON",
        )
    with CaptureQueriesContext(connection) as queries:
        payload = capture(actor.username, "timetable-review-008")
    validate(payload)
    text = json.dumps(payload)
    assert "PRIVATE" not in text
    assert all(r["organization_id"] == ORG for values in payload["data"].values() for r in values)
    assert payload["data"]["slots"][0]["is_parked"] is True
    assert payload["data"]["lessons"][0]["off_schedule_reason_present"] is True
    assert payload["data"]["rows"][0]["group_ids"] == sorted([str(first.group_id), str(extra.pk)])
    assert payload["data"]["assignments"][0]["groups_note_present"] is True
    assert payload["data"]["audits"][0]["source_kind"] == "document"
    assert all(not q["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "ALTER")) for q in queries)
    with transaction.atomic(), pytest.raises(ValueError, match="fresh_postgresql_transaction_required"):
        capture(actor.username, "timetable-review-008")

    # READ ONLY is enforced by PostgreSQL, not just a promise by the collector.
    import importlib

    from django.db import DatabaseError

    module = importlib.import_module("apps.workload.services.timetable_evidence.capture")

    def forbidden_write(_selected):
        with connection.cursor() as cursor:
            cursor.execute("UPDATE organizations_organization SET name='forbidden' WHERE id=%s", [ORG])

    monkeypatch.setattr(module, "collect", forbidden_write)
    with pytest.raises(DatabaseError, match="read-only"):
        capture(actor.username, "timetable-review-008")
    with bypass_rls():
        org.refresh_from_db()
        assert org.name == "Timetable Evidence"
