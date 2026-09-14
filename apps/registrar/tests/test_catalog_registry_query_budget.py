"""Kataloq reyestrlərinin sorğu büdcəsi (audit 2026-09-10 P1-8).

* «İxtisaslar» (ekran 03): əvvəl səhifədəki HƏR ixtisas üçün ayrıca
  ``COUNT`` (qrup sayı) atılırdı — 25 sətirlik səhifə = 25 əlavə sorğu. İndi
  səhifənin bütün qrup sayları TƏK aqreqat sorğusu ilə gəlir; dərin
  yuvalanmış qrup (ixtisas → ara vahid → qrup) hələ də sayılır, passiv qrup
  sayılmır.
* «Fənn kataloqu» (ekran 04): dublikat adlar sorğu başına BİR dəfə hesablanır
  (DB ``GROUP BY name`` + Python normallaşdırması) və ``sb_dup=1`` süzgəci eyni
  nəticəni təkrar istifadə edir — ikinci tam skan yoxdur.
"""

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext

from apps.organizations.models import Organization, OrgUnit
from apps.registrar.catalog_registry import build_programs_registry, build_subject_catalog, duplicate_subject_names
from apps.registrar.models import Program, Subject
from core.constants import OrganizationType, OrgUnitType

User = get_user_model()


class _CatalogQueryBudgetBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("catqb_owner", "catqb_owner@x.test", "pw")
        cls.org = Organization.objects.create(
            name="CATQB",
            slug="catqb",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        cls.faculty = OrgUnit.objects.create(
            organization=cls.org, name="CATQB fakültə", slug="catqb-fac", unit_type=OrgUnitType.FACULTY
        )
        cls.chair = OrgUnit.objects.create(
            organization=cls.org,
            name="CATQB kafedra",
            slug="catqb-chair",
            unit_type=OrgUnitType.CHAIR,
            parent=cls.faculty,
        )

    def _request(self, **params):
        request = RequestFactory().get("/", params)
        request.user = self.owner
        request.org_permissions = ["catalog.view"]
        return request


class ProgramsRegistryGroupCountTest(_CatalogQueryBudgetBase):
    def _add_specialty(self, number: int):
        """İxtisas + birbaşa qrup + dərin qrup (ara vahid altında) + passiv qrup + proqram."""
        specialty = OrgUnit.objects.create(
            organization=self.org,
            name=f"İxtisas {number}",
            slug=f"catqb-sp-{number}",
            unit_type=OrgUnitType.SPECIALTY,
            parent=self.chair,
        )
        OrgUnit.objects.create(
            organization=self.org,
            name=f"G{number}-a",
            slug=f"catqb-g{number}-a",
            unit_type=OrgUnitType.GROUP,
            parent=specialty,
        )
        section = OrgUnit.objects.create(
            organization=self.org,
            name=f"Bölmə {number}",
            slug=f"catqb-sec-{number}",
            unit_type=OrgUnitType.SECTION,
            parent=specialty,
        )
        OrgUnit.objects.create(
            organization=self.org,
            name=f"G{number}-b",
            slug=f"catqb-g{number}-b",
            unit_type=OrgUnitType.GROUP,
            parent=section,
        )
        OrgUnit.objects.create(
            organization=self.org,
            name=f"G{number}-c",
            slug=f"catqb-g{number}-c",
            unit_type=OrgUnitType.GROUP,
            parent=specialty,
            is_active=False,
        )
        return Program.objects.create(
            organization=self.org, code=f"PRG{number}", name=f"Proqram {number}", specialty_unit=specialty
        )

    def test_group_counts_query_count_is_independent_of_page_rows(self):
        self._add_specialty(1)
        build_programs_registry(self._request(), self.org)  # isti-tut
        with CaptureQueriesContext(connection) as one:
            payload_one = build_programs_registry(self._request(), self.org)
        for number in range(2, 6):
            self._add_specialty(number)
        # İxtisassız proqram — qrup sayı 0, sorğu sayına təsir etmir.
        Program.objects.create(organization=self.org, code="PRG-NONE", name="Proqram ixtisassız")
        with CaptureQueriesContext(connection) as five:
            payload_five = build_programs_registry(self._request(), self.org)

        self.assertEqual([row["group_count"] for row in payload_one["rows"]], [2])
        counts = {row["name"]: row["group_count"] for row in payload_five["rows"]}
        self.assertEqual(
            counts,
            {
                "Proqram 1": 2,
                "Proqram 2": 2,
                "Proqram 3": 2,
                "Proqram 4": 2,
                "Proqram 5": 2,
                "Proqram ixtisassız": 0,
            },
        )
        self.assertEqual(payload_five["filtered_count"], 6)
        self.assertEqual(
            len(one.captured_queries),
            len(five.captured_queries),
            f"1 ixtisas: {len(one.captured_queries)} sorğu, 5 ixtisas: {len(five.captured_queries)} sorğu",
        )


class SubjectCatalogDuplicateTest(_CatalogQueryBudgetBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        for code, name, archived in (
            ("M1", "Riyaziyyat", False),
            ("M2", "riyaziyyat", False),  # reqistr fərqi → dublikat
            ("M3", "Fizika  1", False),  # ikiqat boşluq → dublikat
            ("M4", "Fizika 1", False),
            ("M5", "Kimya", False),
            ("M6", "Kimya", True),  # arxiv — dublikat sayılmır
        ):
            Subject.objects.create(organization=cls.org, code=code, name=name, is_archived=archived)

    def test_duplicate_filter_reuses_single_pass(self):
        build_subject_catalog(self._request(), self.org)  # isti-tut
        with CaptureQueriesContext(connection) as plain:
            payload = build_subject_catalog(self._request(), self.org)
        with CaptureQueriesContext(connection) as dup:
            payload_dup = build_subject_catalog(self._request(sb_dup="1"), self.org)

        self.assertEqual(duplicate_subject_names(self.org), {"riyaziyyat": 2, "fizika 1": 2})
        self.assertEqual(payload["duplicate_name_total"], 2)
        self.assertEqual(payload["duplicate_total"], 4)
        self.assertEqual(
            {row["code"]: row["is_duplicate"] for row in payload["rows"]},
            {"M1": True, "M2": True, "M3": True, "M4": True, "M5": False},
        )
        self.assertEqual(sorted(row["code"] for row in payload_dup["rows"]), ["M1", "M2", "M3", "M4"])
        self.assertEqual(payload_dup["filtered_count"], 4)
        self.assertEqual(payload_dup["filters"]["only_duplicates"], True)
        # `sb_dup=1` ikinci tam skan atmır — sorğu sayı adi görünüşlə eynidir.
        self.assertEqual(
            len(dup.captured_queries),
            len(plain.captured_queries),
            f"adi: {len(plain.captured_queries)} sorğu, sb_dup=1: {len(dup.captured_queries)} sorğu",
        )
