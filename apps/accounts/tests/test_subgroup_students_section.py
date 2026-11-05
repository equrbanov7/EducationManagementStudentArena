"""«Alt qrup tələbələri» kabinet bölməsi — reyestr, statistika, ixrac, əlavə modalı (sahib 2026-11-05).

Qurğu (``SubgroupFixture``): G1 hədəf, G2 tələbənin öz qrupu, GX kənar fakültə. Üç «alt qrupdan əlavə» sətri:

* ``e_file``   — GX tələbəsi → G1 Fizika: yüklənmiş sənəd + yerləşdirmə hadisəsi (kredit 6), aktiv;
* ``e_waived`` — G2 tələbəsi → G1 Tarix: sənədsiz RİM rəhbəri düzəlişi (``SA-…`` sərəncamı + qeyd), aktiv;
* ``e_none``   — G2 tələbəsi → G1 Riyaziyyat: sənədsiz, hadisəsiz, jurnaldan çıxarılıb.
"""

from __future__ import annotations

import datetime

from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.registrar import subgroup_students_read as read
from apps.registrar import subgroup_students_stats as stats
from apps.registrar.models import Enrollment, SubgroupPlacementEvent, SubgroupPlacementKind
from apps.registrar.tests.subgroup_base import SubgroupFixture
from apps.registrar.tests.subgroup_evidence_fixture import attach_guest_document
from core.rls import bypass_rls
from core.superadmin_waiver import RIM_NOTE_PREFIX

SECTION = "subgroup-students"


def _event(enrollment, *, reason, actor, order_number="", order_date=None, credits=0, document=None):
    return SubgroupPlacementEvent.objects.create(
        organization=enrollment.organization,
        kind=SubgroupPlacementKind.PLACE,
        enrollment=enrollment,
        student=enrollment.student,
        offering=enrollment.offering,
        source_group=enrollment.source_group,
        target_group=enrollment.offering.group,
        document=document,
        order_number=order_number,
        order_date=order_date,
        reason=reason,
        details={"credits": credits},
        actor=actor,
    )


@override_settings(UNIVERSITY_MODE=True)
class _SectionBase(SubgroupFixture, TestCase):
    PREFIX = "sst"

    @classmethod
    def setUpTestData(cls):
        cls.build_world()
        with bypass_rls():
            cls.rim = cls._member("sst_rim", cls.org.roles.get(name="ikt_rehber"))
            cls.math_g1 = cls.host.enrollments.get(offering__subject=cls.math).offering
            cls.e_file = cls._guest(cls.far_student, cls.physics_g1, cls.far_group)
            document = attach_guest_document(cls.e_file, cls.dean)
            _event(cls.e_file, reason="Dekanlığın təqdimatı №12", actor=cls.dean, credits=6, document=document)
            cls.e_waived = cls._guest(cls.student, cls.history_g1, cls.group2)
            _event(
                cls.e_waived,
                reason=f"Borc · {RIM_NOTE_PREFIX} (Rim, 05.11.2026 10:00)",
                actor=cls.rim,
                order_number="SA-20261105-1000",
                order_date=datetime.date(2026, 11, 5),
                credits=5,
            )
            cls.e_none = cls._guest(cls.student, cls.math_g1, cls.group2, status=Enrollment.Status.DROPPED)

    @classmethod
    def _guest(cls, student, offering, source_group, status=Enrollment.Status.ENROLLED):
        return Enrollment.objects.create(
            organization=cls.org,
            student=student,
            offering=offering,
            status=status,
            source_group=source_group,
            added_by=cls.dean,
            added_at=datetime.datetime(2026, 11, 4, 9, 0, tzinfo=datetime.timezone.utc),
        )

    def _page(self, scope=None, **params):
        with bypass_rls():
            return read.page(self.org, read.parse_filters(params), scope)

    def _ids(self, **params):
        return {row["id"] for row in self._page(**params)["rows"]}


class AccessTest(_SectionBase):
    def test_rim_head_sees_section_with_rows(self):
        client = self.client_for(self.rim)
        page = client.get(reverse("accounts:profile"), {"section": SECTION})
        self.assertContains(page, f'data-profile-section-panel="{SECTION}"')
        self.assertContains(page, f'data-section="{SECTION}"')
        fragment = client.get(reverse("accounts:profile_section_fragment", args=[SECTION]))
        self.assertEqual(fragment.status_code, 200)
        html = fragment.json()["html"]
        self.assertIn("data-sst-root", html)
        self.assertIn("Dekanlığın təqdimatı №12", html)
        self.assertIn(reverse("accounts:subgroup_students_export"), html)
        self.assertIn("data-sst-add-form", html)  # RİM rəhbəri jurnal siyahısını idarə edə bilir

    def test_teacher_is_denied_everywhere(self):
        client = self.client_for(self.teacher)
        page = client.get(reverse("accounts:profile"), {"section": SECTION})
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, f'data-profile-section-panel="{SECTION}"')
        self.assertNotContains(page, f'data-section="{SECTION}"')
        self.assertNotContains(page, "data-sst-add-form")
        self.assertEqual(client.get(reverse("accounts:subgroup_students_export")).status_code, 403)
        self.assertEqual(client.get(reverse("accounts:subgroup_students_journals")).status_code, 403)

    def test_menu_gate_follows_placement_key(self):
        from apps.accounts.views._helpers.rbac_sections import apply_permission_section_gates

        for user, expected in ((self.dean, True), (self.rim, True), (self.plain, False), (self.teacher, False)):
            sections: set = set()
            apply_permission_section_gates(user, self.org, sections, is_superadmin=False, is_owner=False)
            self.assertEqual(SECTION in sections, expected, user.username)

    def test_unit_scope_limits_rows(self):
        far = self.client_for(self.far_dean).get(reverse("accounts:profile_section_fragment", args=[SECTION]))
        html = far.json()["html"]
        self.assertIn("Dekanlığın təqdimatı №12", html)  # öz qrupu GX — əhatədə
        self.assertNotIn("sst_stud", html)  # G1 / G2 əhatədən kənardır
        self.assertNotIn("data-sst-add-form", html)  # `journal.roster` yoxdur → əlavə düyməsi yox
        dean = self.client_for(self.dean).get(reverse("accounts:profile_section_fragment", args=[SECTION]))
        self.assertIn("sst_stud", dean.json()["html"])


class RegistryTest(_SectionBase):
    def test_document_column_states(self):
        rows = {row["id"]: row for row in self._page()["rows"]}
        file_doc = rows[str(self.e_file.pk)]["document"]
        self.assertEqual(file_doc["state"], "file")
        self.assertIn("guest_roster_documents/", file_doc["url"])
        self.assertEqual(rows[str(self.e_waived.pk)]["document"]["state"], "waived")
        self.assertEqual(rows[str(self.e_none.pk)]["document"]["state"], "none")

    def test_row_fields(self):
        row = next(row for row in self._page()["rows"] if row["id"] == str(self.e_file.pk))
        self.assertEqual((row["home_group"], row["target_group"]), ("GX", "G1"))
        self.assertEqual((row["subject_code"], row["credits"], row["status"]), ("SSTFIZ", 6, "active"))
        self.assertEqual(row["reason"], "Dekanlığın təqdimatı №12")
        self.assertTrue(row["actor"])
        removed = next(row for row in self._page()["rows"] if row["id"] == str(self.e_none.pk))
        self.assertEqual((removed["status"], removed["credits"]), ("removed", 5))  # hadisə yoxdur → Subject.ects

    def test_filters(self):
        self.assertEqual(self._page()["total"], 3)
        self.assertEqual(self._ids(ss_doc="present"), {str(self.e_file.pk)})
        self.assertEqual(self._ids(ss_doc="waived"), {str(self.e_waived.pk)})
        self.assertEqual(self._ids(ss_doc="absent"), {str(self.e_none.pk)})
        self.assertEqual(self._ids(ss_status="removed"), {str(self.e_none.pk)})
        self.assertEqual(self._page(ss_status="active")["total"], 2)
        self.assertEqual(self._ids(ss_q="sst_farst"), {str(self.e_file.pk)})
        self.assertEqual(self._page(ss_home=str(self.group2.pk))["total"], 2)
        self.assertEqual(self._page(ss_target=str(self.group1.pk))["total"], 3)
        self.assertEqual(self._ids(ss_subject=str(self.physics.pk)), {str(self.e_file.pk)})
        self.assertEqual(self._ids(ss_faculty=str(self.far_faculty.pk)), {str(self.e_file.pk)})
        self.assertEqual(self._page(ss_faculty=str(self.faculty.pk))["total"], 2)
        self.assertEqual(self._page(ss_teacher="sst_teacher")["total"], 1)  # yalnız Fizika jurnalının müəllimi var
        self.assertEqual(self._page(ss_period=str(self.period.pk))["total"], 3)
        self.assertEqual(self._page(ss_kind="intensive")["total"], 0)
        self.assertEqual(self._page(ss_from="2026-11-05")["total"], 0)
        self.assertEqual(self._page(ss_from="2026-11-04", ss_to="2026-11-04")["total"], 3)
        self.assertEqual(self._page(ss_doc="bogus")["total"], 3)  # naməlum dəyər — süzgəcsiz

    def test_sort(self):
        by_credits = [row["credits"] for row in self._page(ss_sort="-credits")["rows"]]
        self.assertEqual(by_credits, sorted(by_credits, reverse=True))
        by_subject = [row["subject_name"] for row in self._page(ss_sort="subject")["rows"]]
        self.assertEqual(by_subject, sorted(by_subject))
        self.assertEqual(read.parse_filters({"ss_sort": "drop table"}).sort, read.DEFAULT_SORT)

    def test_stats(self):
        with bypass_rls():
            data = stats.build(self.org, read.parse_filters({}))
        totals = data["totals"]
        self.assertEqual(
            (totals["total"], totals["students"], totals["active"]),
            (3, 2, 2),
        )
        self.assertEqual(
            (totals["with_document"], totals["waived"], totals["without_document"], totals["credits"]),
            (1, 1, 1, 16),
        )
        self.assertEqual({item["label"]: item["count"] for item in data["home_groups"]}, {"G2": 2, "GX": 1})
        self.assertEqual(data["target_groups"][0], {"label": "G1", "count": 3, "pct": 100.0})
        self.assertEqual(len(data["subjects"]), 3)
        self.assertEqual(
            {item["label"]: item["count"] for item in data["faculties"]}, {"Fakültə": 2, "Uzaq fakültə": 1}
        )
        self.assertEqual(len(data["weeks"]), stats.TREND_WEEKS)

    def test_query_budget_does_not_grow_with_rows(self):
        def run():
            with bypass_rls(), CaptureQueriesContext(connection) as ctx:
                read.page(self.org, read.parse_filters({}))
                stats.build(self.org, read.parse_filters({}))
            return len(ctx.captured_queries)

        before = run()
        with bypass_rls():
            for student in (self.host,):
                extra = self._guest(student, self.own_history, self.group1)
                attach_guest_document(extra, self.dean)
                _event(extra, reason="Əlavə sətir", actor=self.dean, credits=5)
        self.assertEqual(run(), before)
        self.assertLessEqual(before, 20)


class ExportTest(_SectionBase):
    def test_export_is_xlsx_and_audited(self):
        response = self.client_for(self.rim).get(reverse("accounts:subgroup_students_export"), {"ss_doc": "present"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("spreadsheetml", response["Content-Type"])
        self.assertTrue(response.content.startswith(b"PK"))
        with bypass_rls():
            log = AuditLog.objects.filter(resource_type="accounts.subgroup_students", user=self.rim).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.new_values["rows"], 1)

    def test_scoped_dean_export_is_scoped(self):
        response = self.client_for(self.far_dean).get(reverse("accounts:subgroup_students_export"))
        self.assertEqual(response.status_code, 200)
        with bypass_rls():
            log = AuditLog.objects.filter(resource_type="accounts.subgroup_students", user=self.far_dean).first()
        self.assertEqual(log.new_values["rows"], 1)


class AddFromSectionTest(_SectionBase):
    def test_journal_lookup_is_scoped_to_current_open_journals(self):
        data = self.client_for(self.rim).get(reverse("accounts:subgroup_students_journals"), {"q": "Fizika"}).json()
        self.assertEqual([row["id"] for row in data["results"]], [str(self.physics_g1.pk)])
        self.assertIn("G1", data["results"][0]["text"])

    def test_rim_head_adds_without_document_through_official_endpoint(self):
        client = self.client_for(self.rim)
        response = client.post(
            reverse("registrar:journal_guest_add", args=[self.physics_g1.pk]),
            {"group": str(self.group2.pk), "student": str(self.student.pk), "reason": "Akademik borc"},
        )
        self.assertEqual(response.status_code, 200, response.content)
        enrollment_id = response.json()["enrollment_id"]
        row = next(row for row in self._page()["rows"] if row["id"] == enrollment_id)
        self.assertEqual(row["document"]["state"], "waived")
        self.assertIn(RIM_NOTE_PREFIX, row["reason"])
        self.assertEqual((row["home_group"], row["target_group"], row["credits"]), ("G2", "G1", 6))
        html = client.get(reverse("accounts:profile_section_fragment", args=[SECTION])).json()["html"]
        self.assertIn("sənədsiz — superadmin/RİM rəhbəri düzəlişi", html)

    def test_teacher_cannot_add(self):
        response = self.client_for(self.teacher).post(
            reverse("registrar:journal_guest_add", args=[self.physics_g1.pk]),
            {"group": str(self.group2.pk), "student": str(self.student.pk), "reason": "Akademik borc"},
        )
        self.assertEqual(response.status_code, 404)
        with bypass_rls():
            self.assertFalse(Enrollment.objects.filter(student=self.student, offering=self.physics_g1).exists())
