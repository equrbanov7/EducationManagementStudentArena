"""``build_student_structure_levels`` müqaviləsi (profil məlumatı kartı).

2026-08 sahib şikayəti: tələbə profilindəki akademik struktur "Fakültə >
Kafedra > İxtisas > Qrup" tək sətirli breadcrumb kimi göstərilirdi (çirkin).
Həll: hər səviyyə AYRICA kart. Bu modul köməkçinin müqaviləsini kilidləyir:

* hər səviyyə (fakültə/kafedra/ixtisas/qrup) sıra ilə (kök→yarpaq) gəlir;
* İxtisas AYRICA ``record.program``-dan qurulur (ad + ``Program.code``) —
  ``record.group``-un əcdad zəncirindəki specialty node-a etibar edilmir,
  çünki tenant-a görə bu node YA yoxdur, YA da adı proqramla üst-üstə
  düşməyə bilər (bax [[project_group_sector_variability]]);
* mövcud olmayan səviyyə üçün kart YARADILMIR (boş "—" kart yox).
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.accounts.views.profile.context_builder._helpers import build_student_structure_levels
from apps.organizations.models import Membership, Organization, OrgUnit
from apps.registrar.models import Curriculum, Program, StudentAcademicRecord
from core.constants import OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class BuildStudentStructureLevelsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("struct_owner", "struct_owner@qku.edu.az", "pw")
        cls.student = User.objects.create_user("struct_student", "struct_student@qku.edu.az", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="Struct Univ",
                slug="struct-univ",
                org_type=OrganizationType.UNIVERSITY,
                owner=cls.owner,
                status="active",
                is_active=True,
            )
            # AKTİV membership şərtdir: PG trigger-i (registrar_guard_active_member)
            # StudentAcademicRecord.student referansı üçün əks halda insert-i rədd edir.
            Membership.objects.create(
                user=cls.student,
                organization=cls.org,
                role=cls.org.roles.get(name="student"),
                is_primary=True,
                is_active=True,
            )

    def _record(self, *, group=None, specialty_unit=None, code="COD-1"):
        program = Program.objects.create(
            organization=self.org,
            code=code,
            name="Test İxtisası",
            specialty_unit=specialty_unit,
        )
        curriculum = Curriculum.objects.create(organization=self.org, program=program, admission_year=2024)
        return StudentAcademicRecord.objects.create(
            organization=self.org,
            student=self.student,
            program=program,
            curriculum=curriculum,
            group=group,
            admission_year=2024,
        )

    def test_full_chain_replaces_specialty_node_with_program_and_code(self):
        faculty = OrgUnit.objects.create(
            organization=self.org, name="Fakültə A", slug="sl-faculty-a", unit_type=OrgUnitType.FACULTY
        )
        chair = OrgUnit.objects.create(
            organization=self.org, name="Kafedra A", slug="sl-chair-a", unit_type=OrgUnitType.CHAIR, parent=faculty
        )
        specialty = OrgUnit.objects.create(
            organization=self.org,
            name="Specialty Node Name",  # qəsdən proqram adından fərqli
            slug="sl-specialty-a",
            unit_type=OrgUnitType.SPECIALTY,
            parent=chair,
        )
        group = OrgUnit.objects.create(
            organization=self.org, name="Qrup A", slug="sl-group-a", unit_type=OrgUnitType.GROUP, parent=specialty
        )
        record = self._record(group=group, specialty_unit=specialty, code="FUL-001")

        levels = build_student_structure_levels(record)

        self.assertEqual(
            [lvl["unit_type"] for lvl in levels],
            [
                OrgUnitType.FACULTY,
                OrgUnitType.CHAIR,
                OrgUnitType.SPECIALTY,
                OrgUnitType.GROUP,
            ],
        )
        self.assertEqual(levels[0]["value"], "Fakültə A")
        self.assertEqual(levels[1]["value"], "Kafedra A")
        # Specialty node-un öz adı yox, proqramın adı + kodu göstərilir.
        self.assertEqual(levels[2]["value"], "Test İxtisası")
        self.assertEqual(levels[2]["code"], "FUL-001")
        self.assertEqual(levels[3]["value"], "Qrup A")
        self.assertEqual(levels[3]["code"], "")

    def test_chain_without_specialty_node_inserts_program_before_group(self):
        # Real tenant nümunəsi (bax test_my_results_academic.py): qrup birbaşa
        # kafedra altındadır, specialty tipli node ümumiyyətlə yoxdur.
        chair = OrgUnit.objects.create(
            organization=self.org, name="Kafedra B", slug="sl-chair-b", unit_type=OrgUnitType.CHAIR
        )
        group = OrgUnit.objects.create(
            organization=self.org, name="Qrup B", slug="sl-group-b", unit_type=OrgUnitType.GROUP, parent=chair
        )
        record = self._record(group=group, code="NOSPEC-1")

        levels = build_student_structure_levels(record)

        self.assertEqual(
            [lvl["unit_type"] for lvl in levels],
            [
                OrgUnitType.CHAIR,
                OrgUnitType.SPECIALTY,
                OrgUnitType.GROUP,
            ],
        )
        self.assertEqual(levels[1]["value"], "Test İxtisası")
        self.assertEqual(levels[1]["code"], "NOSPEC-1")

    def test_no_group_shows_only_program_card(self):
        record = self._record(group=None, code="ALONE-1")

        levels = build_student_structure_levels(record)

        self.assertEqual(len(levels), 1)
        self.assertEqual(levels[0]["unit_type"], OrgUnitType.SPECIALTY)
        self.assertEqual(levels[0]["value"], "Test İxtisası")
        self.assertEqual(levels[0]["code"], "ALONE-1")

    def test_missing_program_code_omits_code_without_blank_placeholder(self):
        group = OrgUnit.objects.create(
            organization=self.org, name="Qrup C", slug="sl-group-c", unit_type=OrgUnitType.GROUP
        )
        record = self._record(group=group, code="")

        levels = build_student_structure_levels(record)

        specialty_level = next(lvl for lvl in levels if lvl["unit_type"] == OrgUnitType.SPECIALTY)
        self.assertEqual(specialty_level["code"], "")
