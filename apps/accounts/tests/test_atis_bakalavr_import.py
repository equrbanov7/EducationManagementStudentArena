"""ATİS «Bakalavr» ixracı (sahibin qərarı 2026-09-19): başlıqlar, dəyər tərcüməsi,
şifr ikimənalılığı, qəbul ilinə görə qrup təklifi, yeni sahələrin yazılması,
reyestr filtrləri və `import_students_atis` komandası."""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from openpyxl import Workbook

from apps.accounts.services import intake
from apps.accounts.services.intake.admission import disambiguate_program, parse_admission_status, parse_datetime
from apps.accounts.services.people import registry as registry_service
from apps.accounts.services.student_groups import group_admission_year, group_options
from apps.organizations.models import Membership, Organization, OrgUnit
from apps.registrar.models import Program, StudentAcademicRecord
from core.constants import OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()

HEADERS = [
    "MÜRACİƏT İD", "FİN", "SOYAD", "AD", "ATA ADI", "DOĞUM TARİXİ", "SERİYA", "NÖMRƏ", "ƏLAQƏ NÖMRƏSİ",
    "ELEKTRON POÇT", "QEYDİYYAT ÜNVANI", "CİNSİ", "TƏDRİS DİLİ", "QƏBUL İLİ", "VƏTƏNDAŞLIQ", "İŞ NÖMRƏSİ",
    "MÜRACİƏT TARİXİ", "BAL", "İXTİSAS KODU", "TƏHSİL HAQQI", "ÖDƏNİŞ FORMASI", "TƏHSİLALMA FORMASI", "İXTİSAS",
    "İXTİSAS ŞİFRƏSİ", "İXTİSASLAŞMA", "STATUS", "MÜƏSSİSƏ", "İXTİSAS ATİS İD", "MÜƏSSİSƏ ATİS İD",
    "TƏHSİL SƏVİYYƏSİ", "TƏHSİL PİLLƏSİ", "QƏBUL EDİLDİ", "MÖHLƏTLƏ QƏBUL EDİLDİ", "GÜZƏŞTLİ QƏBUL EDİLDİ",
    "SOSİAL TTK İLƏ QƏBUL EDİLDİ", "STANDART TTK İLƏ QƏBUL EDİLDİ", "VƏTƏNDAŞ İMTİNA ETDİ", "QƏBUL EDİLMƏDİ",
    "QƏBUL XƏTTİ", "VƏTƏNDAŞLIQ (ÖLKƏ)", "TUR", "TƏHSİL BAZASI", "GLOBAL ID", "QEYD", "IELTS",
    "Xarici dil (imtahan)", "Təhsil növü", "Əlavə təhsil növü", "Hazırlıq", "Semestr",
]  # fmt: skip


def _row(**over):
    base = {
        "MÜRACİƏT İD": "612702", "FİN": "6LC868A", "SOYAD": "ƏMİRALIYEV", "AD": "FƏRİD", "ATA ADI": "MƏCNUN OĞLU",
        "DOĞUM TARİXİ": "2003-06-22 00:00:00", "SERİYA": "AA", "NÖMRƏ": "869814", "ƏLAQƏ NÖMRƏSİ": "+994107293595",
        "ELEKTRON POÇT": "farid.amiraliyev1@icloud.com", "QEYDİYYAT ÜNVANI": "BAKI ŞƏHƏRİ, XƏTAİ RAYONU",
        "CİNSİ": "Kişi", "TƏDRİS DİLİ": "İngilis dili", "QƏBUL İLİ": "2026", "VƏTƏNDAŞLIQ": "Azərbaycan",
        "İŞ NÖMRƏSİ": "284991", "MÜRACİƏT TARİXİ": "2026-09-08 17:11:20", "BAL": "71.375", "İXTİSAS KODU": "157415",
        "TƏHSİL HAQQI": "3900", "ÖDƏNİŞ FORMASI": "Ödənişli: Öz vəsaiti hesabına", "TƏHSİLALMA FORMASI": "Əyani (FULLTIME)",
        "İXTİSAS": "Tarix", "İXTİSAS ŞİFRƏSİ": "6002016", "İXTİSASLAŞMA": "Tarix (tədris ingilis dilində)",
        "STATUS": "Möhlətlə qəbul edildi", "MÜƏSSİSƏ": "Qərbi Kaspi Universiteti ", "İXTİSAS ATİS İD": "IX50303",
        "MÜƏSSİSƏ ATİS İD": "AT0066", "TƏHSİL SƏVİYYƏSİ": "Bakalavriat", "TƏHSİL PİLLƏSİ": "Ali təhsil pilləsi",
        "MÖHLƏTLƏ QƏBUL EDİLDİ": "2026-09-08 17:21:45.352000", "QƏBUL XƏTTİ": "İmtahanda iştirak etmədən qəbul",
        "VƏTƏNDAŞLIQ (ÖLKƏ)": "Azərbaycan", "TUR": "FirstTour", "GLOBAL ID": "ROS-80096", "Təhsil növü": "Əsas təhsil",
    }  # fmt: skip
    base.update(over)
    return [base.get(h) for h in HEADERS]


class AtisBakalavrImportTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("atis_owner", "o@x.test", "pw")
        with bypass_rls():
            self.org = Organization.objects.create(
                name="ATIS U", slug="atis-u", org_type=OrganizationType.UNIVERSITY, owner=self.owner,
                status="active", is_active=True,
            )  # fmt: skip
            faculty = OrgUnit.objects.create(organization=self.org, name="Humanitar", unit_type=OrgUnitType.FACULTY)
            self.spec_az = OrgUnit.objects.create(
                organization=self.org, parent=faculty, name="Tarix", slug="tarix", unit_type=OrgUnitType.SPECIALTY
            )
            self.spec_en = OrgUnit.objects.create(
                organization=self.org, parent=faculty, name="Tarix (Tədris Ingilis Dilində)", slug="tarix-en",
                unit_type=OrgUnitType.SPECIALTY,
            )  # fmt: skip
            # 2025 qrupu boşdur, amma 2026 qəbulu ora DÜŞMƏMƏLİDİR; 2026 qrupu ad şablonundan tanınır.
            OrgUnit.objects.create(
                organization=self.org, parent=self.spec_en, name="435 T ing", unit_type=OrgUnitType.GROUP
            )
            self.group_2026 = OrgUnit.objects.create(
                organization=self.org, parent=self.spec_en, name="436 T ing", unit_type=OrgUnitType.GROUP,
                settings={"language_sector": "en"},
            )  # fmt: skip
            self.prog_az = Program.objects.create(
                organization=self.org, specialty_unit=self.spec_az, code="T", name="Tarix", official_code="6002016"
            )
            self.prog_en = Program.objects.create(
                organization=self.org, specialty_unit=self.spec_en, code="T-EN",
                name="Tarix (Tədris Ingilis Dilində)", official_code="6002016",
            )  # fmt: skip
            self.admin = User.objects.create_superuser("superadmin", "sa@x.test", "pw")
            Membership.objects.create(
                user=self.admin, organization=self.org, role=self.org.roles.get(name="rector"), is_active=True
            )
        self.tmp = TemporaryDirectory()
        self.path = Path(self.tmp.name) / "Bakalavr.xlsx"
        wb = Workbook()
        ws = wb.active
        ws.title = "MÜRACİƏTLƏR"
        ws.append(HEADERS)
        ws.append(_row())
        ws.append(_row(**{"MÜRACİƏT İD": "612660", "FİN": "6C7EL83", "SOYAD": "BABAYEVA", "AD": "MƏTANƏT", "CİNSİ": "Qadın",
                          "TƏDRİS DİLİ": "Azərbaycan dili", "ELEKTRON POÇT": "m@x.test", "ÖDƏNİŞ FORMASI": "Dövlət sifarişi",
                          "TƏHSİL HAQQI": None, "STATUS": "Qəbul edildi", "QƏBUL EDİLDİ": "2026-09-08 16:28:42.663000",
                          "MÖHLƏTLƏ QƏBUL EDİLDİ": None, "QƏBUL XƏTTİ": "DİM vasitəsilə", "İXTİSASLAŞMA": "Tarix"}))  # fmt: skip
        wb.save(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_helpers(self):
        self.assertEqual(parse_admission_status("Sosial TTK ilə qəbul edildi"), "social_ttk")
        self.assertEqual(parse_datetime("2026-09-08 16:28:42.663000").year, 2026)
        with bypass_rls():
            self.assertEqual(group_admission_year(self.group_2026), 2026)
            self.assertEqual(
                [row["name"] for row in group_options(self.org, self.spec_en, sector="en", admission_year="2026")],
                ["436 T ing"],
            )
            self.assertEqual(
                disambiguate_program(self.org, "6002016", name="Tarix", sector="İngilis dili"), self.prog_en
            )
            self.assertEqual(
                disambiguate_program(self.org, "6002016", name="Tarix", sector="Azərbaycan dili"), self.prog_az
            )

    def test_plans_from_atis_layout(self):
        with bypass_rls():
            rows = intake.read_rows(_UploadLike(self.path))
            plans = intake.build_plans(self.org, rows)
        self.assertEqual([p.status for p in plans], ["create", "create"])
        first = plans[0]
        self.assertEqual(first.targets["program"], self.prog_en)
        self.assertEqual(first.group_name, "436 T ing")
        self.assertEqual(first.values["funding_type"], "paid")
        self.assertEqual(first.values["education_form"], "full_time")
        self.assertEqual(first.values["admission_status"], "deferred")
        self.assertEqual(first.values["admission_channel"], "exam_free")
        self.assertEqual(first.values["admission_tour"], "first")
        self.assertEqual(first.values["instruction_language"], "en")
        self.assertEqual(str(first.values["tuition_fee"]), "3900")
        self.assertEqual(first.values["admitted_at"].minute, 21)
        self.assertEqual(first.values["atis_id"], "612702")
        self.assertEqual(first.values["id_series"], "AA")
        self.assertEqual(first.values["admission_extra"]["global_id"], "ROS-80096")
        second = plans[1]
        self.assertEqual(second.targets["program"], self.prog_az)
        self.assertEqual(second.values["funding_type"], "state")
        self.assertIsNone(second.targets["group"])  # az sektorunda 2026 qrupu yoxdur → təklif yoxdur

    def test_command_apply_and_registry(self):
        out = StringIO()
        creds = Path(self.tmp.name) / "creds.csv"
        with self.settings(MANAGEMENT_COMMAND_ENVIRONMENT="test"):
            call_command(
                "import_students_atis", "--file", str(self.path), "--org", "atis-u", "--actor", "superadmin",
                "--apply", "--credentials", str(creds), "--report", str(Path(self.tmp.name) / "r.csv"), stdout=out,
            )  # fmt: skip
        self.assertIn("yaradıldı=1", out.getvalue())
        with bypass_rls():
            record = StudentAcademicRecord.objects.get(organization=self.org, group=self.group_2026)
            self.assertEqual(record.admission_status, "deferred")
            self.assertEqual(record.admission_channel, "exam_free")
            self.assertEqual(record.instruction_language, "en")
            self.assertEqual(str(record.tuition_fee), "3900.00")
            self.assertEqual(record.admission_extra["work_number"], "284991")
            profile = record.student.profile
            self.assertEqual(
                (profile.citizenship, profile.id_document_series, profile.id_document_number),
                ("Azərbaycan", "AA", "869814"),
            )
            self.assertEqual(profile.student_specialization, "Tarix (tədris ingilis dilində)")
            self.assertTrue(profile.password_change_required)
        self.assertIn("ilkin_parol", creds.read_text(encoding="utf-8"))
        # Reyestr filtrləri yeni sahələrə işləyir.
        values = dict(registry_service.FILTER_DEFAULTS, admission_status="deferred", channel="exam_free", language="en")
        with bypass_rls():
            qs = registry_service._apply_filters(
                StudentAcademicRecord.objects.filter(organization=self.org), values, organization=self.org
            )
            self.assertEqual(qs.count(), 1)
            values["admission_status"] = "admitted"
            self.assertEqual(
                registry_service._apply_filters(
                    StudentAcademicRecord.objects.filter(organization=self.org), values, organization=self.org
                ).count(),
                0,
            )


class _UploadLike:
    def __init__(self, path: Path):
        self.name = path.name
        self.size = path.stat().st_size
        self._path = path

    def read(self):
        return self._path.read_bytes()
