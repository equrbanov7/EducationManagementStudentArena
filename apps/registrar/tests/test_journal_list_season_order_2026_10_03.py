"""Jurnal siyahısı: «YARIM İL» dropdown-u tədris ilinin axını ilə — Payız → Yaz → Yay (2026-10-03).

Sıralama açarları («Payız») `schedule.season_label`-ın tam etiketləri («Payız semestri») ilə üst-üstə
düşmürdü — hamısı eyni çəkiyə düşür, sıra set-in təsadüfi qaydası ilə çıxırdı (klonda «Yay, Payız, Yaz»).
"""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.organizations.models import AcademicPeriod, Organization, OrgUnit
from apps.registrar import services
from apps.registrar.models import Subject
from core.constants import AcademicPeriodType, OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()

# Yaradılma sırası qəsdən «səhvdir» (Yay, Payız, Yaz) — nəticə buna görə dəyişməməlidir.
PERIODS = (
    ("Yay", "2025-07-01", "2025-08-31"),
    ("Payız", "2025-09-15", "2026-01-31"),
    ("Yaz", "2026-02-01", "2026-06-30"),
)


class JournalListSeasonOrderTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("jso_owner", "jso_owner@qku.edu.az", "pw")
        cls.admin = User.objects.create_user("jso_admin", "jso_admin@qku.edu.az", "pw", is_superuser=True)
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="JSO Univ",
                slug="jso-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            group = OrgUnit.objects.create(
                organization=cls.org, name="JSO-A", slug="jso-a", unit_type=OrgUnitType.GROUP
            )
            for index, (name, start, end) in enumerate(PERIODS):
                period = AcademicPeriod.objects.create(
                    organization=cls.org,
                    name=name,
                    period_type=AcademicPeriodType.SEMESTER,
                    academic_year="2025/2026",
                    start_date=start,
                    end_date=end,
                )
                subject = Subject.objects.create(organization=cls.org, code=f"JSO{index}", name=f"JSO fənni {index}")
                services.get_or_create_offering(organization=cls.org, subject=subject, period=period, group=group)

    def test_season_dropdown_follows_academic_year_flow(self):
        client = Client()
        client.force_login(self.admin)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()

        response = client.get(reverse("registrar:journal_list"), {"year": "2025/2026"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["journal_seasons"], ["Payız semestri", "Yaz semestri", "Yay semestri"])
