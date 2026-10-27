"""Qrup imtahanın fənnini keçmir — xəbərdarlıq endpoint-i + məcburi əlavə + audit (sahib 2026-10-27).

Prod halı: «236 QM» qrupu «Azərbaycan tarixi» midterminə səhvən əlavə olunmuşdu (qrup bu fənni keçmir).
Bax ``apps/exams/services/exam_unit_coverage.py``.
"""

from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.audit.models import AuditLog
from apps.exams.models import Exam
from apps.exams.services import exam_unit_coverage
from apps.exams.tests.test_exam_journal_link_2026_10_24 import _LinkSetup, _login
from apps.organizations.models import Membership, Organization, OrgUnit
from apps.registrar import exam_journal_link as registrar_link
from apps.registrar.models import CourseOffering, Enrollment, StudentAcademicRecord, Subject
from core.constants import OrganizationType, OrgUnitType
from core.rls import bypass_rls

_REASON = "Tələbələr bu fəndən akademik borcu verir"


class _CoverageSetup(_LinkSetup):
    """Bridge quraşdırması + qrupun KEÇMƏDİYİ fənn («Azərbaycan tarixi») + ikinci tələbə."""

    def setUp(self):
        super().setUp()
        User = get_user_model()
        with bypass_rls():
            User.objects.filter(pk=self.student.pk).update(first_name="Aysel", last_name="Məmmədova")
            self.student.refresh_from_db()
            profile = self.student.profile
            profile.patronymic = "Elçin"
            profile.save(update_fields=["patronymic"])
            self.history = Subject.objects.create(organization=self.org, code="AZT101", name="Azərbaycan tarixi")

    def _record(self, student, group):
        with bypass_rls():
            return StudentAcademicRecord.objects.create(
                organization=self.org,
                student=student,
                program=self.program,
                curriculum=self.curriculum,
                group=group,
                admission_year=2024,
            )

    def _new_student(self, username, group):
        student = get_user_model().objects.create_user(username, f"{username}@qku.edu.az", "pw")
        with bypass_rls():
            Membership.objects.create(
                user=student, organization=self.org, role=self.org.roles.get(name="student"), is_active=True
            )
        self._record(student, group)
        return student

    def _forced(self, unit, reason=_REASON):
        return json.dumps({str(unit.pk): reason})


class CoverageEndpointTests(_CoverageSetup):
    url = reverse("exams:unit_journal_coverage")

    def _get(self, user=None, **params):
        params.setdefault("units", str(self.group.pk))
        params.setdefault("category", "midterm")
        client = _login(user or self.center, self.org)
        return client.get(self.url, params, HTTP_X_REQUESTED_WITH="XMLHttpRequest")

    def _json(self, **params):
        response = self._get(**params)
        self.assertEqual(response.status_code, 200, response.content[:300])
        return response.json()

    def test_group_enrolled_in_subject_journal_is_covered(self):
        data = self._json(subject=str(self.subject.pk))
        self.assertTrue(data["applies"])
        row = data["groups"][0]
        self.assertEqual(
            (row["id"], row["total"], row["uncovered"], row["has_journal"]), (str(self.group.pk), 1, 0, True)
        )
        self.assertEqual(row["names"], [])

    def test_group_without_the_subject_is_uncovered_with_patronymic_names(self):
        data = self._json(subject=str(self.history.pk))
        row = data["groups"][0]
        self.assertEqual((row["total"], row["uncovered"], row["has_journal"], row["more"]), (1, 1, False, 0))
        self.assertEqual(row["names"], ["Aysel Məmmədova Elçin"])
        self.assertIn("Azərbaycan tarixi", data["subject"])

    def test_partial_coverage_counts_only_students_missing_from_the_journal(self):
        second = self._new_student("cov_second", self.group)
        with bypass_rls():
            offering = CourseOffering.objects.create(
                organization=self.org, subject=self.history, period=self.period, group=self.group
            )
            Enrollment.objects.create(organization=self.org, student=second, offering=offering)
        row = self._json(subject=str(self.history.pk))["groups"][0]
        self.assertEqual((row["total"], row["uncovered"], row["has_journal"]), (2, 1, True))

    def test_subgroup_students_count_for_the_parent_group(self):
        with bypass_rls():
            faculty = OrgUnit.objects.create(organization=self.org, name="Fak", slug="cov-fak", unit_type="faculty")
            OrgUnit.objects.filter(pk=self.group.pk).update(parent=faculty, name="234 K az")
            sub = OrgUnit.objects.create(
                organization=self.org, name="234 K-1", slug="cov-sub", unit_type=OrgUnitType.GROUP, parent=faculty
            )
        self._new_student("cov_sub_student", sub)
        row = self._json(subject=str(self.subject.pk))["groups"][0]
        # Ana qrupun tələbəsi jurnaldadır, alt qrupunkü yox → qrup əhatəsizdir.
        self.assertEqual((row["total"], row["uncovered"]), (2, 1))
        sub_row = self._json(subject=str(self.subject.pk), units=str(sub.pk))["groups"][0]
        self.assertEqual((sub_row["total"], sub_row["uncovered"], sub_row["has_journal"]), (1, 1, True))

    def test_no_subject_or_non_journal_category_does_not_apply(self):
        self.assertEqual(self._json(subject="")["applies"], False)
        self.assertEqual(self._json(subject=str(self.history.pk), category="quiz"), {"applies": False, "groups": []})

    def test_other_tenant_units_and_subjects_are_ignored(self):
        with bypass_rls():
            other_org = Organization.objects.create(
                name="Other U",
                slug="cov-other",
                org_type=OrganizationType.UNIVERSITY,
                owner=self.owner,
                status="active",
                is_active=True,
            )
            foreign_group = OrgUnit.objects.create(
                organization=other_org, name="X1", slug="cov-x1", unit_type=OrgUnitType.GROUP
            )
            foreign_subject = Subject.objects.create(organization=other_org, code="X101", name="Xarici")
        data = self._json(subject=str(self.history.pk), units=f"{foreign_group.pk},{self.group.pk}")
        self.assertEqual([row["id"] for row in data["groups"]], [str(self.group.pk)])
        self.assertFalse(self._json(subject=str(foreign_subject.pk))["applies"])

    def test_student_is_denied(self):
        self.assertEqual(self._get(user=self.student, subject=str(self.history.pk)).status_code, 403)

    def test_registrar_coverage_query_budget_does_not_grow_with_groups(self):
        groups = [self.group, self.other_group]
        for index in range(3):
            with bypass_rls():
                unit = OrgUnit.objects.create(
                    organization=self.org, name=f"CB{index}", slug=f"cov-cb{index}", unit_type=OrgUnitType.GROUP
                )
            self._new_student(f"cov_cb{index}", unit)
            groups.append(unit)
        with bypass_rls():
            with CaptureQueriesContext(connection) as one:
                registrar_link.group_subject_coverage(self.org, self.history.pk, [self.group.pk], period=self.period)
            with CaptureQueriesContext(connection) as many:
                result = registrar_link.group_subject_coverage(
                    self.org, self.history.pk, [unit.pk for unit in groups], period=self.period
                )
        self.assertEqual(len(one), len(many))
        self.assertLessEqual(len(many), 6)
        self.assertEqual(len(result[self.other_group.pk]["students"]), 0)


class SaveValidationTests(_CoverageSetup):
    def _create(self, **extra):
        client = _login(self.center, self.org)
        with self.captureOnCommitCallbacks(execute=True):
            return client.post(
                reverse("exams:create_exam") + "?modal=1",
                self._payload(**extra),
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )

    def _edit(self, exam, **extra):
        client = _login(self.center, self.org)
        with self.captureOnCommitCallbacks(execute=True):
            return client.post(
                reverse("exams:edit_exam", kwargs={"slug": exam.slug}) + "?modal=1",
                self._payload(**extra),
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )

    def _forced_logs(self, exam=None):
        with bypass_rls():
            rows = AuditLog.objects.filter(resource_type=exam_unit_coverage.AUDIT_RESOURCE)
            if exam is not None:
                rows = rows.filter(resource_id=str(exam.pk))
            return list(rows)

    def _exam_count(self):
        with bypass_rls():
            return Exam.objects.filter(title="JS Loop").count()

    def test_new_uncovered_group_without_reason_is_rejected_on_access_step(self):
        response = self._create(subject=str(self.history.pk))
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["success"])
        self.assertEqual((payload["step"], payload["field"]), (2, "allowed_units"))
        self.assertEqual(payload["unit_coverage_required"][0]["id"], str(self.group.pk))
        self.assertIn("data-ew-unit-coverage", payload["html"])
        self.assertIn("Aysel Məmmədova Elçin", payload["html"])  # data-blocked modalı yenidən açır
        self.assertEqual(self._exam_count(), 0)
        self.assertEqual(self._forced_logs(), [])

    def test_short_reason_is_rejected(self):
        response = self._create(subject=str(self.history.pk), forced_units=self._forced(self.group, "səhv"))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self._exam_count(), 0)

    def test_forced_group_with_reason_is_saved_and_audited(self):
        response = self._create(subject=str(self.history.pk), forced_units=self._forced(self.group))
        self.assertEqual(response.status_code, 200, response.content[:400])
        with bypass_rls():
            exam = Exam.objects.get(title="JS Loop")
            self.assertEqual(list(exam.allowed_units.values_list("pk", flat=True)), [self.group.pk])
        logs = self._forced_logs(exam)
        self.assertEqual(len(logs), 1)
        log = logs[0]
        self.assertEqual(log.user, self.center)
        self.assertEqual(log.reason, _REASON)
        self.assertEqual(log.changes["unit_id"], str(self.group.pk))
        self.assertEqual((log.changes["uncovered"], log.changes["students"]), (1, 1))
        self.assertIn("Azərbaycan tarixi", log.changes["subject"])

        history = exam_unit_coverage.history(exam)
        self.assertEqual([row["reason"] for row in history], [_REASON])
        page = _login(self.center, self.org).get(reverse("exams:teacher_exam_detail", kwargs={"slug": exam.slug}))
        self.assertContains(page, "ted-unit-forced-history")
        self.assertContains(page, _REASON)

    def test_per_unit_reason_field_and_id_list_are_accepted(self):
        response = self._create(
            subject=str(self.history.pk),
            forced_units=str(self.group.pk),
            **{f"forced_unit_reason_{self.group.pk}": _REASON},
        )
        self.assertEqual(response.status_code, 200, response.content[:400])

    def test_covered_group_needs_no_reason(self):
        response = self._create()
        self.assertEqual(response.status_code, 200, response.content[:400])
        self.assertEqual(self._forced_logs(), [])

    def test_non_journal_category_is_not_checked(self):
        response = self._create(subject=str(self.history.pk), exam_type_extended="quiz")
        self.assertEqual(response.status_code, 200, response.content[:400])

    def test_existing_group_on_edit_is_not_rechecked(self):
        exam, _options = self._exam(title="JS Loop")
        with bypass_rls():
            Exam.objects.filter(pk=exam.pk).update(subject=self.history, author=self.center)
            exam.refresh_from_db()
            exam.allowed_units.add(self.group)
        response = self._edit(exam, subject=str(self.history.pk))
        self.assertEqual(response.status_code, 200, response.content[:400])
        self.assertEqual(self._forced_logs(), [])

    def test_newly_added_uncovered_group_on_edit_is_rejected(self):
        exam, _options = self._exam(title="JS Loop")
        with bypass_rls():
            uncovered = OrgUnit.objects.create(
                organization=self.org, name="236 QM", slug="cov-236", unit_type=OrgUnitType.GROUP
            )
        self._new_student("cov_236", uncovered)
        with bypass_rls():
            Exam.objects.filter(pk=exam.pk).update(author=self.center)
            exam.refresh_from_db()
            exam.allowed_units.add(self.group)
        units = [str(self.group.pk), str(uncovered.pk)]
        response = self._edit(exam, allowed_units=units)
        self.assertEqual(response.status_code, 400)
        self.assertEqual([row["id"] for row in response.json()["unit_coverage_required"]], [str(uncovered.pk)])
        with bypass_rls():
            self.assertEqual(list(exam.allowed_units.values_list("pk", flat=True)), [self.group.pk])
        response = self._edit(exam, allowed_units=units, forced_units=self._forced(uncovered))
        self.assertEqual(response.status_code, 200, response.content[:400])
        self.assertEqual([log.changes["unit"] for log in self._forced_logs(exam)], ["236 QM"])

    def test_edit_form_lists_existing_units_for_the_client(self):
        exam, _options = self._exam(title="JS Loop")
        with bypass_rls():
            Exam.objects.filter(pk=exam.pk).update(author=self.center)
            exam.allowed_units.add(self.group)
        html = (
            _login(self.center, self.org)
            .get(reverse("exams:edit_exam", kwargs={"slug": exam.slug}) + "?modal=1")
            .content.decode()
        )
        self.assertIn("data-ew-unit-coverage", html)
        self.assertIn(str(self.group.pk), html.split("data-existing=")[1].split(">")[0])


class ParseForcedTests(_CoverageSetup):
    def test_parse_forced_variants(self):
        from django.http import QueryDict

        data = QueryDict(mutable=True)
        data["forced_units"] = '{"a": "  bir   iki  "}'
        self.assertEqual(exam_unit_coverage.parse_forced(data), {"a": "bir iki"})
        data = QueryDict(mutable=True)
        data["forced_units"] = "a,b"
        data["forced_units_reason"] = "ümumi səbəb"
        data["forced_unit_reason_b"] = "xüsusi səbəb"
        self.assertEqual(exam_unit_coverage.parse_forced(data), {"a": "ümumi səbəb", "b": "xüsusi səbəb"})
        self.assertEqual(exam_unit_coverage.parse_forced(QueryDict()), {})
