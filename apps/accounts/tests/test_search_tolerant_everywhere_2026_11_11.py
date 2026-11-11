"""Registr + az/ing əlifbasına dözümlü axtarış — əsas axtarış nöqtələri üzrə cədvəl testi (sahib 2026-11-11).

Sahib: «Search yerini elə düzəlt ki, böyük-kiçik hərfə görə problem olmasın, az/eng əlifbasına
görə də». Səbəb: bərpa olunmuş tələbə «aqsin quliyev» (kiçik, ASCII, «ş»-siz) saxlanıb, əməkdaş
«Aqşin Quliyev» yazanda tapmayıb; əksi də (saxlanan «Aqşin», yazılan «aqsin»/«AQSIN»/«Aqshin»)
işləməlidir. Hər nöqtə eyni cədvəldən keçir (REAL endpoint/servis, PostgreSQL ``~*``):

* tələbə reyestri (``student-registry`` fraqmenti, ``sr_q``) və hədəf qrup seçicisi;
* ⌘K qlobal axtarış (tələbələr);
* view-as axtarışı və RİM mərkəzi istifadəçi axtarışı (``search_users``);
* müəllimin kursa qrup əlavə etmə axtarışı (``course_groups.search_group_rows``);
* sənəd yoxlama reyestri (``verification.views_staff._search``).
"""

from __future__ import annotations

import json

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.services.rim import search_users
from apps.accounts.services.rim.policy import RimActor
from apps.organizations.models import Membership, Organization, OrgUnit
from apps.registrar.course_groups import search_group_rows
from apps.registrar.models import AcademicStatus, Curriculum, Program, StudentAcademicRecord
from apps.verification.models import DocumentSeal
from apps.verification.views_staff import _search as verification_search
from core.constants import OrganizationType, OrgUnitType
from core.rls import bypass_rls

from .test_student_services_sections import PASSWORD, StudentServicesBase
from .test_view_as import ViewAsTestBase, _add_member

User = get_user_model()

GROUP_NAME = "534 T az"

#: (açar, ad, soyad) — «ascii» sahibin halıdır (kiçik, ASCII), «az» düzgün az yazılışı,
#: «ism» «İ»/«ı» registr tələsi, «other» yalan-müsbət nəzarəti.
PEOPLE = (
    ("ascii", "aqsin", "quliyev"),
    ("az", "Aqşin", "Quliyev"),
    ("ism", "Elvin", "İsmayılov"),
    ("other", "Rauf", "Məmmədov"),
)

#: (sorğu, gözlənilən açarlar)
NAME_CASES = (
    # Saxlanan «aqsin quliyev» — az hərfi / böyük hərf / söz sırası ilə yazılır.
    ("Aqşin", {"ascii", "az"}),
    ("AQŞİN QULİYEV", {"ascii", "az"}),
    ("quliyev aqsin", {"ascii", "az"}),
    ("Aqşin Quliyev", {"ascii", "az"}),
    # Saxlanan «Aqşin Quliyev» — ASCII / ingilis «sh» / böyük hərf.
    ("aqsin", {"ascii", "az"}),
    ("AQSIN", {"ascii", "az"}),
    ("Aqshin", {"az"}),
    # «İ»/«ı»: PostgreSQL ``'İ' ~* 'i'`` false-dur — siniflər açıq olmalıdır.
    ("ismayilov", {"ism"}),
    ("ISMAYILOV", {"ism"}),
    ("İSMAYILOV elvin", {"ism"}),
    # Yalan-müsbət yoxdur.
    ("Məmmədov Aqşin", set()),
    ("Quliyeva", set()),
)

GROUP_CASES = ("534t", "534 t az", "534 T az", "534-T", "534taz")


def _keys(names_by_key, found_names):
    return {key for key, name in names_by_key.items() if name in set(found_names)}


class RegistryAndPickerOwnerCasesTest(StudentServicesBase):
    """Tələbə reyestri (ad + qrup) və hədəf qrup seçicisi."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.group_534 = OrgUnit.objects.create(
            organization=cls.org,
            parent=cls.specialty,
            unit_type=OrgUnitType.GROUP,
            name=GROUP_NAME,
            slug="tol-534-t-az",
        )
        cls.names = {}
        for key, first, last in PEOPLE:
            group = cls.group_534 if key == "ascii" else cls.group_a
            cls._student(f"tol_{key}", first, last, group)
            cls.names[key] = f"{first} {last}"

    @classmethod
    def _student(cls, username, first, last, group):
        user = User.objects.create_user(username, f"{username}@qku.edu.az", PASSWORD, first_name=first, last_name=last)
        Membership.objects.create(
            user=user, organization=cls.org, role=cls.student_role, is_primary=True, is_active=True
        )
        StudentAcademicRecord.objects.create(
            organization=cls.org,
            student=user,
            program=cls.program,
            curriculum=cls.curriculum,
            group=group,
            admission_year=2025,
            status=AcademicStatus.ENROLLED,
        )
        return user

    def _found(self, query):
        response = self._fragment("student_services", "student-registry", sr_q=query)
        self.assertEqual(response.status_code, 200)
        return _keys(self.names, [row["name"] for row in response.context["student_registry_section"]["rows"]])

    def test_registry_names(self):
        for query, expected in NAME_CASES:
            with self.subTest(query=query):
                self.assertEqual(self._found(query), expected)

    def test_registry_group_name(self):
        for query in GROUP_CASES:
            with self.subTest(query=query):
                self.assertEqual(self._found(query), {"ascii"})

    def test_target_group_picker(self):
        client = self._client("student_services")
        for query in GROUP_CASES:
            with self.subTest(query=query):
                response = client.get(reverse("accounts:people_academic_groups"), {"q": query})
                self.assertEqual(response.status_code, 200)
                self.assertEqual([row["text"] for row in response.json()["results"]], [GROUP_NAME])


@override_settings(UNIVERSITY_MODE=True)
class GlobalSearchCourseGroupsAndVerificationOwnerCasesTest(TestCase):
    """⌘K tələbə axtarışı, kursa qrup əlavə etmə axtarışı, sənəd yoxlama reyestri."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("tolgs_owner", "tolgs_owner@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="Tol GS Univ",
                slug="tol-gs-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            cls.faculty = OrgUnit.objects.create(
                organization=cls.org, name="Tol Fakültə", slug="tolgs-f1", unit_type=OrgUnitType.FACULTY
            )
            cls.group = OrgUnit.objects.create(
                organization=cls.org, name=GROUP_NAME, slug="tolgs-g1", unit_type=OrgUnitType.GROUP, parent=cls.faculty
            )
            cls.other_group = OrgUnit.objects.create(
                organization=cls.org, name="KE-101", slug="tolgs-g2", unit_type=OrgUnitType.GROUP, parent=cls.faculty
            )
            program = Program.objects.create(organization=cls.org, code="TOLCS", name="Kompüter elmləri")
            curriculum = Curriculum.objects.create(organization=cls.org, program=program, admission_year=2026)
            cls.dean = User.objects.create_user("tolgs_dean", "tolgs_dean@qku.edu.az", "pw")
            Membership.objects.create(
                user=cls.dean,
                organization=cls.org,
                role=cls.org.roles.get(name="dean"),
                scope_unit=cls.faculty,
                is_primary=True,
                is_active=True,
            )
            cls.names = {}
            cls.users = {}
            for key, first, last in PEOPLE:
                user = User.objects.create_user(
                    f"tolgs_{key}", f"tolgs_{key}@qku.edu.az", "pw", first_name=first, last_name=last
                )
                Membership.objects.create(
                    user=user, organization=cls.org, role=cls.org.roles.get(name="student"), is_active=True
                )
                StudentAcademicRecord.objects.create(
                    organization=cls.org,
                    student=user,
                    program=program,
                    curriculum=curriculum,
                    group=cls.group if key == "ascii" else cls.other_group,
                    admission_year=2026,
                )
                cls.names[key] = f"{first} {last}"
                cls.users[key] = user
                DocumentSeal.objects.create(
                    organization=cls.org,
                    code=f"TOL{key.upper()}0001",
                    doc_type="transcript",
                    subject_user=user,
                    title="Arayış",
                    issued_at=timezone.now(),
                    payload_sha256="0" * 64,
                )

    def _global_students(self, query):
        client = Client()
        client.force_login(self.dean)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        response = client.get(reverse("accounts:global_search"), {"q": query})
        self.assertEqual(response.status_code, 200)
        groups = {group["key"]: group for group in json.loads(response.content)["groups"]}
        return _keys(self.names, [item["title"] for item in groups.get("students", {"items": []})["items"]])

    def test_global_search_students(self):
        for query, expected in NAME_CASES:
            with self.subTest(query=query):
                self.assertEqual(self._global_students(query), expected)
        for query in GROUP_CASES:
            with self.subTest(query=query):
                self.assertEqual(self._global_students(query), {"ascii"})

    def test_course_group_search(self):
        for query in GROUP_CASES:
            with self.subTest(query=query):
                rows = search_group_rows(organization=self.org, query=query)
                self.assertEqual([row["name"] for row in rows], [GROUP_NAME])
        self.assertEqual(search_group_rows(organization=self.org, query="535t"), [])

    def test_verification_registry_search(self):
        by_pk = {user.pk: key for key, user in self.users.items()}
        base = DocumentSeal.objects.filter(organization=self.org)
        for query, expected in NAME_CASES:
            with self.subTest(query=query):
                found = {by_pk[pk] for pk in verification_search(base, query).values_list("subject_user_id", flat=True)}
                self.assertEqual(found, expected)


class ViewAsAndRimOwnerCasesTest(ViewAsTestBase):
    """view-as siyahısı + RİM mərkəzi istifadəçi axtarışı."""

    def setUp(self):
        super().setUp()
        self.people = {}
        for key, first, last in PEOPLE:
            user = User.objects.create_user(
                f"tolva_{key}", f"tolva_{key}@example.com", PASSWORD, first_name=first, last_name=last
            )
            _add_member(user, self.org, self.student_role)
            self.people[key] = user
        self.by_pk = {user.pk: key for key, user in self.people.items()}

    def test_view_as_search(self):
        self._login(self.admin)
        by_username = {user.username: key for key, user in self.people.items()}
        for query, expected in NAME_CASES:
            with self.subTest(query=query):
                response = self.client.get(reverse("accounts:view_as_search"), {"q": query})
                self.assertEqual(response.status_code, 200)
                found = {
                    by_username[row["username"]] for row in response.json()["results"] if row["username"] in by_username
                }
                self.assertEqual(found, expected)

    def test_rim_user_search(self):
        actor = RimActor(user=self.superadmin, organization=self.org, level=999, is_superadmin=True)
        for query, expected in NAME_CASES:
            with self.subTest(query=query):
                found = search_users(actor, query=query)
                self.assertEqual({self.by_pk[u.pk] for u in found["results"] if u.pk in self.by_pk}, expected)
