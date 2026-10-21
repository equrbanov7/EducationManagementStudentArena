"""`scripts/prod_ops/academic_data_probe.py` — yalnız-oxu prod yoxlaması işləyir və üst-üstə düşən dövrləri tapır;
R01 (2026-10-21): plan ↔ kataloq kredit fərqinin saylarını (sətir, yazılış, tələbə, möhürlü transkript) çap edir."""

from __future__ import annotations

import contextlib
import io
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit
from apps.registrar.models import (
    CourseOffering,
    Curriculum,
    CurriculumSubject,
    Enrollment,
    Program,
    StudentAcademicRecord,
    Subject,
)
from apps.verification.models import DocumentSeal
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "prod_ops" / "academic_data_probe.py"


def _run_probe() -> str:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        exec(compile(SCRIPT.read_text(encoding="utf-8"), str(SCRIPT), "exec"), {"__name__": "__probe__"})
    return out.getvalue()


class AcademicDataProbeTest(TestCase):
    def test_reports_overlaps_and_groups_without_course(self):
        owner = get_user_model().objects.create_user("adp_owner", "adp@adp.test", "pw")
        with bypass_rls():
            org = Organization.objects.create(
                name="ADP", slug="adp-org", org_type=OrganizationType.UNIVERSITY, owner=owner, status="active"
            )
            for name, start, end in (("Payız", "2026-09-15", "2027-01-31"), ("Yaz", "2027-01-20", "2027-06-30")):
                AcademicPeriod.objects.bulk_create(
                    [
                        AcademicPeriod(
                            organization=org,
                            name=name,
                            period_type=AcademicPeriodType.SEMESTER,
                            academic_year="2026/2027",
                            start_date=start,
                            end_date=end,
                        )
                    ]
                )
            OrgUnit.objects.create(organization=org, name="236 K", slug="adp-g", unit_type=OrgUnitType.GROUP)
        text = _run_probe()
        self.assertIn("period_overlaps: 1", text)
        self.assertIn("groups_without_course_year: 1", text)
        self.assertIn("holidays_total: 0", text)

    def test_reports_credit_source_mismatch_counts(self):
        user_model = get_user_model()
        owner = user_model.objects.create_user("adp_owner2", "adp2@adp.test", "pw")
        student = user_model.objects.create_user("adp_student", "adp_s@adp.test", "pw")
        other = user_model.objects.create_user("adp_other", "adp_o@adp.test", "pw")
        with bypass_rls():
            org = Organization.objects.create(
                name="ADP2", slug="adp-org2", org_type=OrganizationType.UNIVERSITY, owner=owner, status="active"
            )
            past = AcademicPeriod.objects.create(
                organization=org,
                name="Payız",
                period_type=AcademicPeriodType.SEMESTER,
                academic_year="2024/2025",
                start_date="2024-09-15",
                end_date="2025-01-31",
            )
            program = Program.objects.create(organization=org, code="ADPP", name="Proqram")
            plan = Curriculum.objects.create(
                organization=org, program=program, admission_year=2024, status="approved", is_active=True
            )
            draft = Curriculum.objects.create(
                organization=org, program=program, admission_year=2024, version=2, status="draft"
            )
            math = Subject.objects.create(organization=org, code="ADPM", name="Riyaziyyat", ects=5)
            same = Subject.objects.create(organization=org, code="ADPS", name="Tarix", ects=5)
            for curriculum, subject, credits in ((plan, math, 8), (plan, same, 5), (draft, same, 9)):
                CurriculumSubject.objects.create(
                    organization=org, curriculum=curriculum, subject=subject, semester_number=1, credits=credits
                )
            for user in (student, other):
                Membership.objects.create(
                    user=user, organization=org, role=org.roles.get(name="student"), is_primary=True, is_active=True
                )
                StudentAcademicRecord.objects.create(
                    organization=org, student=user, program=program, curriculum=plan, admission_year=2024
                )
            for subject in (math, same):
                offering = CourseOffering.objects.create(organization=org, subject=subject, period=past)
                Enrollment.objects.create(organization=org, student=student, offering=offering)
                if subject is same:
                    Enrollment.objects.create(organization=org, student=other, offering=offering)
            DocumentSeal.objects.create(
                organization=org,
                code="ADPSEAL1",
                doc_type="transcript",
                subject_user=student,
                title="Transkript",
                issued_at=timezone.now(),
                payload_sha256="0" * 64,
            )
        text = _run_probe()
        self.assertIn("credit_plan_rows_mismatch: 1", text)  # qaralama planın sətri sayılmır
        self.assertIn("credit_mismatch_enrollments: 1 (bitmiş dövr: 1, davam edən: 0)", text)
        self.assertIn("credit_mismatch_students: 1", text)
        self.assertIn("credit_mismatch_sealed_transcripts: 1 (ləğv edilməmiş: 1, tələbə: 1)", text)
        self.assertNotIn("adp_student", text)  # yalnız saylar
