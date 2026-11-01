"""Journal readers publish approved content while the profile keeps teacher drafts."""

import copy

from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.organizations.models import AcademicPeriod, Membership, Organization, Role
from apps.syllabus import public as syllabus

from .. import syllabus_notice
from ..models import CourseOffering, Subject
from . import test_journal_syllabus_bridge as fixtures


@override_settings(ACADEMIC_SELFWORK_ENABLED=True)
class PublishedJournalSyllabusTests(TestCase):
    setUp = fixtures.JournalSyllabusBridgeTest.setUp
    _member = fixtures.JournalSyllabusBridgeTest._member
    _client = fixtures.JournalSyllabusBridgeTest._client
    _actor = fixtures.JournalSyllabusBridgeTest._actor
    _draft = fixtures.JournalSyllabusBridgeTest._draft
    _json_url = fixtures.JournalSyllabusBridgeTest._json_url
    _pdf_url = fixtures.JournalSyllabusBridgeTest._pdf_url

    def _published_with_edit(self):
        document, published = syllabus.import_migrated_version(
            organization=self.org,
            subject=self.subject,
            period=self.period,
            offering=self.offering,
            chair_unit=self.chair_unit,
            author=self.teacher,
            approved_at=timezone.now(),
            plan_hours={"lecture": 15, "seminar": 15, "lab": 0},
            section_data={
                "info": {"language": "az"},
                "week": {"rows": [{"topic": "Published topic", "lecture": 15, "seminar": 15}]},
                "assess": {"note": "Published assessment"},
            },
        )
        # Imported partial approval and a later human draft are valid stored states.
        type(published).objects.filter(pk=published.pk).update(completion_percent=14)
        published.refresh_from_db()
        draft = type(published).objects.create(
            organization=self.org,
            syllabus=document,
            major=1,
            minor=1,
            status="draft",
            change_kind="minor",
            applies_to_period=self.period,
            source_version=published,
            plan_hours=published.plan_hours,
            created_by=self.teacher,
            completion_percent=43,
        )
        for section in published.sections.all():
            data = copy.deepcopy(section.data)
            if section.section_id == "assess":
                data["note"] = "Teacher's unfinished assessment"
            type(section).objects.create(
                organization=self.org,
                version=draft,
                section_id=section.section_id,
                data=data,
                is_complete=section.is_complete,
                updated_by=self.teacher,
            )
        type(document).objects.filter(pk=document.pk).update(current_version=draft)
        document.refresh_from_db()
        draft.refresh_from_db()
        return document, published, draft

    def _notice(self):
        offering = CourseOffering.objects.select_related("organization", "subject", "period").get(pk=self.offering.pk)
        return syllabus_notice.journal_syllabus_notice(offering, has_lessons=False)

    def test_notice_uses_approved_status_and_label_without_draft_action(self):
        document, published, draft = self._published_with_edit()
        notice = self._notice()
        self.assertEqual(notice["state"], "approved")
        self.assertEqual(notice["version_label"], published.label)
        self.assertFalse(notice["show_banner"])
        self.assertIsNone(notice["action_label"])
        self.assertEqual(notice["reason"], "")
        self.assertTrue(notice["can_open"])
        self.assertTrue(notice["has_approved"])
        self.assertEqual(syllabus.offering_syllabus_state(document)["version"].pk, draft.pk)

    def test_teacher_panel_reads_published_body_without_changing_editor_or_records(self):
        document, published, draft = self._published_with_edit()
        before_versions = list(document.versions.order_by("pk").values())
        before_sections = list(draft.sections.order_by("pk").values())
        response = self._client(self.teacher).get(self._json_url())
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "approved")
        self.assertEqual(payload["version"], published.label)
        self.assertIn("Published assessment", response.content.decode())
        self.assertNotIn("Teacher's unfinished assessment", response.content.decode())
        document.refresh_from_db()
        self.assertEqual(document.current_version_id, draft.pk)
        self.assertEqual(document.approved_version_id, published.pk)
        self.assertEqual(list(document.versions.order_by("pk").values()), before_versions)
        self.assertEqual(list(draft.sections.order_by("pk").values()), before_sections)
        state = syllabus.offering_syllabus_state(document)
        self.assertEqual(state["state"], "draft")
        self.assertEqual(state["version"].pk, draft.pk)
        self.assertEqual((published.completion_percent, draft.completion_percent), (14, 43))

    def test_draft_without_published_version_still_warns_and_staff_can_read_it(self):
        self._draft()
        notice = self._notice()
        self.assertEqual(notice["state"], "draft")
        self.assertTrue(notice["show_banner"])
        self.assertFalse(notice["has_approved"])
        response = self._client(self.teacher).get(self._json_url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "draft")
        self.assertEqual(self._client(self.student).get(self._json_url()).status_code, 404)

    def test_missing_remains_truthful(self):
        notice = self._notice()
        self.assertEqual(notice["state"], "missing")
        self.assertTrue(notice["show_banner"])
        self.assertFalse(notice["can_open"])
        self.assertFalse(notice["has_approved"])

    def test_students_keep_published_access_and_unenrolled_users_remain_denied(self):
        _document, published, _draft = self._published_with_edit()
        response = self._client(self.student).get(self._json_url())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["version"], published.label)
        self.assertEqual(self._client(self.stranger).get(self._json_url()).status_code, 404)
        self.assertEqual(self._client(self.stranger).get(self._pdf_url()).status_code, 404)

    def test_foreign_tenant_published_document_is_not_exposed(self):
        foreign = Organization.objects.create(
            name="Foreign published university",
            slug="foreign-published",
            org_type="university",
            owner=self.teacher,
            status="active",
            is_active=True,
        )
        period = AcademicPeriod.objects.create(
            organization=foreign,
            name="Fall",
            academic_year="2026/2027",
            period_type="semester",
            start_date="2026-09-01",
            end_date="2027-01-31",
        )
        role = Role.objects.create(
            organization=foreign,
            name="Foreign teacher",
            display_name="Foreign teacher",
            permissions=fixtures.TEACHER_PERMS,
            scope_type="organization",
            level=50,
        )
        Membership.objects.create(organization=foreign, user=self.teacher, role=role, is_active=True)
        subject = Subject.objects.create(organization=foreign, code="FP", name="Foreign topic")
        offering = CourseOffering.objects.create(
            organization=foreign,
            subject=subject,
            period=period,
            instructor=self.teacher,
        )
        syllabus.import_migrated_version(
            organization=foreign,
            subject=subject,
            period=period,
            offering=offering,
            author=self.teacher,
            approved_at=timezone.now(),
            section_data={"week": {"rows": [{"topic": "Foreign published topic", "lecture": 1}]}},
        )
        client = self._client(self.teacher)
        for name in ("offering_syllabus_json", "offering_syllabus_pdf"):
            response = client.get(reverse(f"registrar:{name}", args=[offering.pk]))
            self.assertEqual(response.status_code, 404)
            self.assertNotIn("Foreign published topic", response.content.decode())

    def test_published_notice_adds_no_queries_to_canonical_state_lookup(self):
        self._published_with_edit()

        def offering():
            return CourseOffering.objects.select_related("organization", "subject", "period").get(pk=self.offering.pk)

        obj = offering()
        with CaptureQueriesContext(connection) as baseline:
            document = syllabus.syllabus_for_offering_obj(obj)
            syllabus.offering_syllabus_state(document)
        obj = offering()
        with CaptureQueriesContext(connection) as actual:
            syllabus_notice.journal_syllabus_notice(obj, has_lessons=False)
        self.assertEqual(len(actual), len(baseline))
