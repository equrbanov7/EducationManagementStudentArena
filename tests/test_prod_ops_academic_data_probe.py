"""`scripts/prod_ops/academic_data_probe.py` — yalnız-oxu prod yoxlaması işləyir və üst-üstə düşən dövrləri tapır."""

from __future__ import annotations

import contextlib
import io
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.organizations.models import AcademicPeriod, Organization, OrgUnit
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "prod_ops" / "academic_data_probe.py"


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
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            exec(compile(SCRIPT.read_text(encoding="utf-8"), str(SCRIPT), "exec"), {"__name__": "__probe__"})
        text = out.getvalue()
        self.assertIn("period_overlaps: 1", text)
        self.assertIn("groups_without_course_year: 1", text)
        self.assertIn("holidays_total: 0", text)
