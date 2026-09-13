"""Dalğa 2 (2026-09-14) — audit 2026-09-13 backend F-07: `journal_detail`
`save_finals` budağı (sətir-sətir `finals.set_exam_score` / `set_final_extras`)
BİR ``transaction.atomic`` içindədir — ikinci tələbədə yazı sınanda birinci də
geri alınır (yarımçıq toplu bal yazısı olmur)."""

from __future__ import annotations

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar import finals, services
from apps.registrar.models import Enrollment, FinalGrade, Subject
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class SaveFinalsAtomicTest(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("w2sf_owner", "w2sf_owner@qku.edu.az", "pw")
        with bypass_rls():
            self.org = Organization.objects.create(
                name="W2 Finals Univ",
                slug="w2-finals-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=self.owner,
                status="active",
                is_active=True,
            )
            group = OrgUnit.objects.create(
                organization=self.org, name="G1", slug="w2sf-g1", unit_type=OrgUnitType.GROUP
            )
            period = AcademicPeriod.objects.create(
                organization=self.org,
                name="2024/2025 Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2024/2025",
                start_date="2024-09-01",
                end_date="2025-01-31",
                is_current=True,
            )
            subject = Subject.objects.create(organization=self.org, code="W2SF", name="Dalğa 2")
            self.teacher = User.objects.create_user("w2sf_teacher", "w2sf_teacher@qku.edu.az", "pw")
            # Müəllim ORGANIZATION-əhatəli imtahan mərkəzi rəhbəridir (`final_score.entry` +
            # `grade.view`/`exam.*`) və əlavə `grade.input` alır — birbaşa redaktor + bal
            # yazma hüququ eyni şəxsdə (view-un `save_finals` budağı; müəllim rolu COURSE
            # əhatəlidir, ona görə `final_score.entry` orada boş əhatə verərdi).
            role = self.org.roles.get(name="exam_center_head")
            role.permissions = sorted(set(role.permissions) | {"grade.input"})
            role.save(update_fields=["permissions"])
            Membership.objects.create(user=self.teacher, organization=self.org, role=role, is_primary=True)
            self.offering = services.get_or_create_offering(
                organization=self.org, subject=subject, period=period, group=group
            )
            self.offering.instructor = self.teacher
            self.offering.save(update_fields=["instructor"])
            self.enrollments = []
            for index in range(2):
                student = User.objects.create_user(f"w2sf_s{index}", f"w2sf_s{index}@qku.edu.az", "pw")
                Membership.objects.create(
                    user=student, organization=self.org, role=self.org.roles.get(name="student"), is_primary=True
                )
                self.enrollments.append(
                    Enrollment.objects.create(organization=self.org, student=student, offering=self.offering)
                )
        self.client = Client()
        self.client.force_login(self.teacher)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()
        self.url = reverse("registrar:journal_detail", args=[self.offering.id])

    def _post(self):
        data = {"action": "save_finals"}
        for index, enrollment in enumerate(self.enrollments):
            data[f"exam__{enrollment.id}"] = str(40 + index)
        return self.client.post(self.url, data)

    def test_second_row_failure_rolls_back_the_first(self):
        original = finals.set_exam_score
        calls = {"n": 0}

        def _flaky(**kwargs):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("second row boom")
            return original(**kwargs)

        with mock.patch("apps.registrar.views.finals.set_exam_score", side_effect=_flaky):
            with self.assertRaises(RuntimeError):
                self._post()
        with bypass_rls():
            self.assertFalse(FinalGrade.objects.filter(enrollment__in=self.enrollments).exists())

    def test_happy_path_writes_every_row(self):
        self.assertEqual(self._post().status_code, 302)
        with bypass_rls():
            scores = {
                fg.enrollment_id: fg.exam_score for fg in FinalGrade.objects.filter(enrollment__in=self.enrollments)
            }
        self.assertEqual(len(scores), 2)
