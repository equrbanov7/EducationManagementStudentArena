"""1-ci kurs datasının FILL-ONLY tamamlanması (sahib 2026-10-27): ``assign_first_year_student_codes`` və
``fill_first_year_atis_data``. Bütün adlar / FİN-lər / nömrələr SİNTETİKDİR."""

from __future__ import annotations

import datetime
import gzip
import json
import re
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from openpyxl import Workbook

from apps.accounts.models import UserProfile
from apps.accounts.services.first_year_data.codes import group_number
from apps.accounts.services.intake import create_account, student_role
from apps.accounts.tests.test_atis_bakalavr_import import HEADERS
from apps.audit.models import AuditLog
from apps.organizations.models import Organization, OrgUnit
from apps.registrar.models import Program, StudentAcademicRecord
from core.constants import OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()

CODES_RE = re.compile(r"^student_codes: [a-z_]+=[0-9a-z_,-]+( [a-z_]+=[0-9a-z_,-]+)*$")
FILL_RE = re.compile(r"^atis_fill: [a-z0-9_]+=[0-9a-z_-]+( [a-z0-9_]+=[0-9a-z_-]+)*$")
PLACEHOLDER = "legacy.{}@placeholder.invalid"


def _parse(output: str, pattern) -> dict:
    counts = {}
    for line in output.splitlines():
        assert pattern.match(line), line  # stdout-a YALNIZ saylar / kodlar
        for pair in line.split(" ")[1:]:
            key, value = pair.split("=")
            counts[key] = value
    return counts


class _FirstYearBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        owner = User.objects.create_user("fy_owner", "fy_owner@x.test", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="FY U", slug="fy-u", org_type=OrganizationType.UNIVERSITY, owner=owner, status="active",
                is_active=True,
            )  # fmt: skip
            faculty = OrgUnit.objects.create(organization=cls.org, name="Fak", unit_type=OrgUnitType.FACULTY)
            cls.spec = OrgUnit.objects.create(
                organization=cls.org, parent=faculty, name="Ixtisas", slug="fy-ix", unit_type=OrgUnitType.SPECIALTY
            )
            cls.other_spec = OrgUnit.objects.create(
                organization=cls.org, parent=faculty, name="Diger", slug="fy-dg", unit_type=OrgUnitType.SPECIALTY
            )
            cls.g_a = OrgUnit.objects.create(organization=cls.org, parent=cls.spec, name="236 AA", unit_type="group")
            cls.g_b = OrgUnit.objects.create(organization=cls.org, parent=cls.spec, name="236 BB", unit_type="group")
            cls.g_c = OrgUnit.objects.create(organization=cls.org, parent=cls.spec, name="036 CC", unit_type="group")
            cls.program = Program.objects.create(
                organization=cls.org, specialty_unit=cls.spec, code="FY-1", name="Ixtisas", official_code="6000001"
            )
            cls.other_program = Program.objects.create(
                organization=cls.org, specialty_unit=cls.other_spec, code="FY-2", name="Diger", official_code="6000002"
            )
            cls.admin = User.objects.create_superuser("fy_admin", "fy_admin@x.test", "pw")
        cls.seq = 0

    @classmethod
    def student(cls, *, fin=None, code="", group=None, last="Testov", first="Bir", patronymic="Ata", **extra):
        cls.seq += 1
        username = f"fy.st{cls.seq}"
        values = {
            "username": username, "email": PLACEHOLDER.format(cls.seq), "first_name": first, "last_name": last,
            "fin": fin, "patronymic": patronymic, "gender": "unspecified", "birth_date": None, "phone": "",
            "student_code": code, **extra,
        }  # fmt: skip
        with bypass_rls():
            user, _password = create_account(
                organization=cls.org, kind="student", values=values, role=student_role(cls.org), actor=cls.admin,
                student_targets={"group": group or cls.g_a, "program": cls.program, "admission_year": 2026},
                group_name=(group or cls.g_a).name,
            )  # fmt: skip
        return user

    def code_of(self, user):
        with bypass_rls():
            return UserProfile.objects.get(user=user).institutional_identifier


class AssignStudentCodesTest(_FirstYearBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.with_legacy = cls.student(fin="TSTA001")
        cls.two_legacy = cls.student(fin="TSTA002", group=cls.g_b)
        cls.taken_legacy = cls.student(fin="TSTA003")
        cls.coded = cls.student(fin="TSTA004", code="777")
        cls.owner_of_9003 = cls.student(fin="TSTA005", code="9003", group=cls.g_c)
        cls.g_a_first = cls.student(last="Aaa", first="Bir")
        cls.g_a_second = cls.student(last="Bbb", first="Bir")
        cls.g_c_first = cls.student(group=cls.g_c, last="Ccc")
        with bypass_rls():
            # Qrup nömrəsi kodunun ilk namizədi artıq başqa hesabdadır → növbəti nömrə götürülməlidir.
            cls.collider = cls.student(group=cls.other_spec_group(), code="2360101")

    @classmethod
    def other_spec_group(cls):
        return OrgUnit.objects.create(organization=cls.org, parent=cls.other_spec, name="912 ZZ", unit_type="group")

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        bundle = {
            "format": "ems-legacy-delta/1",
            "students": [
                {"id": 9001, "fincode": "TSTA001", "group_id": 1, "azadedildi": 0},
                {"id": 9010, "fincode": "TSTA002", "group_id": 1, "azadedildi": 0},
                {"id": 9011, "fincode": "TSTA002", "group_id": 2, "azadedildi": 0},
                {"id": 9003, "fincode": "TSTA003", "group_id": 1, "azadedildi": 0},
            ],
            "expelled_students": [],
            "groups": [{"id": 1, "name": "236 AA"}, {"id": 2, "name": "236 bb"}],
        }
        self.bundle = Path(self.tmp.name) / "delta.json.gz"
        self.bundle.write_bytes(gzip.compress(json.dumps(bundle).encode()))

    def _run(self, *args):
        out = StringIO()
        call_command(
            "assign_first_year_student_codes", "--org", self.org.slug, "--actor", self.admin.username,
            "--legacy-bundle", str(self.bundle), *args, stdout=out,
        )  # fmt: skip
        return _parse(out.getvalue(), CODES_RE)

    def test_group_number(self):
        self.assertEqual(group_number("236 İT"), "236")
        self.assertEqual(group_number("3/336F1"), "336")
        self.assertEqual(group_number("036 ing"), "36")
        self.assertEqual(group_number("Dizayn"), "")

    def test_dry_run_writes_nothing(self):
        counts = self._run()
        self.assertEqual(counts["mode"], "dry_run")
        self.assertEqual((counts["targets"], counts["legacy_assigned"], counts["group_assigned"]), ("6", "2", "3"))
        self.assertEqual(counts["skip_legacy_id_taken"], "1")
        self.assertEqual(counts["examples"], "2360102,2360103,360101")
        self.assertIsNone(self.code_of(self.with_legacy))
        self.assertIsNone(self.code_of(self.g_a_first))
        with bypass_rls():
            self.assertFalse(AuditLog.objects.filter(resource_type="accounts.first_year_codes_batch").exists())

    def test_apply_fill_only_unique_idempotent(self):
        counts = self._run("--apply")
        self.assertEqual(counts["written"], "5")
        self.assertEqual(self.code_of(self.with_legacy), "9001")
        self.assertEqual(self.code_of(self.two_legacy), "9011")  # eyni FİN-in iki sətri → cari qrupla eyni adlı
        self.assertEqual(counts["legacy_multi_by_group"], "1")
        self.assertIsNone(self.code_of(self.taken_legacy))  # legacy id başqa hesabın kodudur → ötürülür
        self.assertEqual(self.code_of(self.coded), "777")  # dolu kod toxunulmur
        self.assertEqual(self.code_of(self.g_a_first), "2360102")  # 2360101 başqa hesabdadır → ondan sonra
        self.assertEqual(self.code_of(self.g_a_second), "2360103")
        self.assertEqual(self.code_of(self.g_c_first), "360101")  # «036» → 36
        with bypass_rls():
            codes = [
                value.lower()
                for value in UserProfile.objects.filter(organization=self.org)
                .exclude(institutional_identifier=None)
                .values_list("institutional_identifier", flat=True)
            ]
            self.assertEqual(len(codes), len(set(codes)))
            audit = AuditLog.objects.get(resource_type="accounts.first_year_codes_batch")
            self.assertEqual(len(audit.new_values["assigned"]), 5)
            self.assertEqual(StudentAcademicRecord.objects.get(student=self.g_a_first).group_id, self.g_a.pk)
        again = self._run("--apply")
        self.assertEqual((again["targets"], again["written"]), ("1", "0"))  # yalnız ötürülən qalır

    def test_bad_bundle_fails_closed(self):
        self.bundle.write_text('{"format": "other"}')
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            self._run()


ATIS_COLUMNS = {
    "MÜRACİƏT İD": "atis", "FİN": "fin", "SOYAD": "last", "AD": "first", "ATA ADI": "patronymic",
    "DOĞUM TARİXİ": "birth", "SERİYA": "series", "NÖMRƏ": "number", "ƏLAQƏ NÖMRƏSİ": "phone",
    "ELEKTRON POÇT": "email", "CİNSİ": "gender", "TƏDRİS DİLİ": "language", "QƏBUL İLİ": "year", "BAL": "score",
    "İXTİSAS": "speciality", "İXTİSAS ŞİFRƏSİ": "code", "TƏHSİLALMA FORMASI": "form", "VƏTƏNDAŞLIQ": "citizenship",
}  # fmt: skip


def _atis_row(**values):
    base = {
        "atis": "100", "fin": "", "last": "Testov", "first": "Bir", "patronymic": "Ata oğlu", "birth": "2008-01-02",
        "series": "AA", "number": "1000001", "phone": "+994500000099", "email": "", "gender": "Kişi",
        "language": "Azərbaycan dili", "year": "2026", "score": "500", "speciality": "Ixtisas", "code": "6000001",
        "form": "Əyani (FULLTIME)", "citizenship": "Azərbaycan",
    }  # fmt: skip
    base.update(values)
    by_header = {header: base.get(key) for header, key in ATIS_COLUMNS.items()}
    return [by_header.get(header) for header in HEADERS]


class FillAtisDataTest(_FirstYearBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # FİN-li delta hesabı: telefonu DOLUDUR (toxunulmamalı), e-poçtu placeholder-dir.
        cls.by_fin = cls.student(fin="TSTB001", last="Fin", phone="+994500000001")
        # FİN-siz delta hesabı — ad + ata adı ilə tapılır.
        cls.by_name = cls.student(last="Adli", first="Iki", patronymic="Veli")
        # FİN-siz, ATİS-də eyni açarlı İKİ sətir → qeyri-müəyyən.
        cls.ambiguous = cls.student(last="Eyni", first="Uc", patronymic="Ali")
        # FİN-siz, ATİS sətri başqa ixtisasdadır → ziddiyyət.
        cls.mismatch = cls.student(last="Basqa", first="Dord", patronymic="Huseyn")
        # Artıq ATİS datası var (atis_id dolu) → hədəf deyil.
        cls.complete = cls.student(fin="TSTB009", last="Tam", atis_id="555")

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "atis.xlsx"
        wb = Workbook()
        ws = wb.active
        ws.append(HEADERS)
        ws.append(
            _atis_row(atis="101", fin="TSTB001", last="Fin", email="fin.real@example.test", phone="+994500000077")
        )
        ws.append(
            _atis_row(atis="102", fin="TSTB002", last="ADLİ", first="İki", patronymic="Vəli qızı", gender="Qadın")
        )
        ws.append(_atis_row(atis="103", fin="TSTB003", last="Eyni", first="Uc", patronymic="Ali"))
        ws.append(_atis_row(atis="104", fin="TSTB004", last="Eyni", first="Uc", patronymic="Ali oğlu"))
        ws.append(_atis_row(atis="105", fin="TSTB005", last="Basqa", first="Dord", patronymic="Huseyn", code="6000002"))
        ws.append(_atis_row(atis="106", fin="TSTB006", last="Hesabsiz", first="Bes", form="Qiyabi (PARTTIME)"))
        ws.append(_atis_row(atis="109", fin="TSTB009", last="Tam"))
        wb.save(self.path)

    def _run(self, *args):
        out = StringIO()
        call_command(
            "fill_first_year_atis_data", "--org", self.org.slug, "--actor", self.admin.username,
            "--file", str(self.path), *args, stdout=out,
        )  # fmt: skip
        return _parse(out.getvalue(), FILL_RE)

    def _state(self, user):
        with bypass_rls():
            profile = UserProfile.objects.select_related("user").get(user=user)
            record = StudentAcademicRecord.objects.get(student=user)
        return profile, record

    def test_dry_run_writes_nothing(self):
        counts = self._run()
        self.assertEqual(counts["mode"], "dry_run")
        self.assertEqual((counts["targets"], counts["matched_fin"], counts["matched_name"]), ("4", "1", "1"))
        self.assertEqual((counts["skip_ambiguous_name"], counts["skip_program_mismatch"]), ("1", "1"))
        self.assertEqual((counts["atis_rows_without_account"], counts["atis_rows_ambiguous"]), ("2", "2"))
        self.assertEqual(counts["missing_form_part_time"], "1")
        profile, record = self._state(self.by_name)
        self.assertIsNone(profile.fin)
        self.assertEqual(record.atis_id, "")
        with bypass_rls():
            self.assertFalse(AuditLog.objects.filter(resource_type="accounts.first_year_atis_fill_batch").exists())

    def test_apply_fills_only_empty_and_is_idempotent(self):
        counts = self._run("--apply")
        self.assertEqual(counts["students_filled"], "2")
        profile, record = self._state(self.by_fin)
        self.assertEqual(profile.phone, "+994500000001")  # dolu telefon toxunulmur
        self.assertEqual(profile.user.email, "fin.real@example.test")  # placeholder → real e-poçt
        self.assertEqual(profile.birth_date, datetime.date(2008, 1, 2))
        self.assertEqual((profile.id_document_series, profile.citizenship), ("AA", "Azərbaycan"))
        self.assertEqual(
            (record.atis_id, record.instruction_language, str(record.admission_score)), ("101", "az", "500.00")
        )
        self.assertEqual(record.group_id, self.g_a.pk)  # qrup dəyişmir
        named, named_record = self._state(self.by_name)
        self.assertEqual((named.fin, named.gender, named.patronymic), ("TSTB002", "female", "Veli"))
        self.assertEqual(named_record.atis_id, "102")
        self.assertTrue(named.user.email.endswith("@placeholder.invalid"))  # ATİS-də e-poçt yoxdur
        for user in (self.ambiguous, self.mismatch):
            other, other_record = self._state(user)
            self.assertIsNone(other.fin)
            self.assertEqual(other_record.atis_id, "")
        complete, complete_record = self._state(self.complete)
        self.assertEqual(complete_record.atis_id, "555")
        self.assertIsNone(complete.birth_date)
        with bypass_rls():
            audit = AuditLog.objects.get(resource_type="accounts.first_year_atis_fill_batch")
            self.assertEqual(len(audit.new_values["filled"]), 2)
            self.assertNotIn("TSTB", json.dumps(audit.new_values))  # audit-də yalnız sahə adları
        again = self._run("--apply")
        self.assertEqual((again["students_filled"], again["matched_fin"], again["matched_name"]), ("0", "0", "0"))


class FirstYearWorkflowTest(SimpleTestCase):
    """``prod-data-ops.yml``: ağ siyahı, şifrəli giriş və loq süzgəci əmrlərin çıxışı ilə uyğundur."""

    def test_workflow_whitelists_commands_and_filters_output(self):
        text = (Path(__file__).resolve().parents[3] / ".github/workflows/prod-data-ops.yml").read_text(encoding="utf-8")
        for command in ("assign_first_year_student_codes", "fill_first_year_atis_data"):
            self.assertIn(f"          - {command}\n", text)
        self.assertIn("^(student-codes|legacy-delta)-[0-9a-z-]+$", text)
        self.assertIn("^atis-fill-[0-9a-z-]+$", text)
        pattern = "^(student_codes|atis_fill): [a-z0-9_]+=[0-9a-z_,-]+( [a-z0-9_]+=[0-9a-z_,-]+)*$"
        self.assertIn(pattern, text)
        workflow_re = re.compile(pattern)
        for line in (
            "student_codes: mode=dry_run targets=996 legacy_assigned=702 group_assigned=294 written=996",
            "student_codes: examples=1360601,1360602,1360603",
            "atis_fill: missing_form_part_time=9 missing_program_6008008=10",
            "atis_fill: batch=atisfill-20261027-120000-ab12",
        ):
            self.assertRegex(line, workflow_re)
