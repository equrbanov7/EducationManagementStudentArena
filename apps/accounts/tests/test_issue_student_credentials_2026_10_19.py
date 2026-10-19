"""``issue_staff_credentials --audience students`` — oxuyan tələbələrin ilkin parol siyahısı (sahib 2026-10-19)."""

from __future__ import annotations

import csv
import io
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from apps.organizations.models import Membership, Organization, OrgUnit
from apps.registrar.models import Curriculum, Program, StudentAcademicRecord
from core.constants import OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class IssueStudentCredentialsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        owner = User.objects.create_user("isc2_owner", "isc2@isc2.test", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="ISC2", slug="isc2-org", org_type=OrganizationType.UNIVERSITY, owner=owner, status="active"
            )
            unit = OrgUnit.objects.create
            fac = unit(organization=cls.org, name="Dizayn məktəbi", slug="isc2-f", unit_type=OrgUnitType.FACULTY)
            chair = unit(organization=cls.org, name="Dizayn", slug="isc2-c", unit_type=OrgUnitType.CHAIR, parent=fac)
            cls.group = unit(organization=cls.org, name="321", slug="isc2-g", unit_type=OrgUnitType.GROUP, parent=chair)
            cls.subgroup = unit(
                organization=cls.org, name="321/A", slug="isc2-sg", unit_type=OrgUnitType.GROUP, parent=cls.group
            )
            other_fac = unit(organization=cls.org, name="Psixologiya", slug="isc2-o", unit_type=OrgUnitType.FACULTY)
            cls.other_group = unit(
                organization=cls.org, name="028", slug="isc2-og", unit_type=OrgUnitType.GROUP, parent=other_fac
            )
            program = Program.objects.create(organization=cls.org, code="DZ", name="Dizayn")
            curriculum = Curriculum.objects.create(organization=cls.org, program=program, admission_year=2025)
            student_role = cls.org.roles.get(name="student")

            def student(username, group, *, activated=False, status="enrolled", password="list-pass"):
                user = User.objects.create_user(username, f"{username}@isc2.test", password, last_name=username)
                Membership.objects.create(user=user, organization=cls.org, role=student_role, is_active=True)
                StudentAcademicRecord.objects.create(
                    organization=cls.org,
                    student=user,
                    program=program,
                    curriculum=curriculum,
                    group=group,
                    admission_year=2025,
                    status=status,
                )
                profile = user.profile
                profile.email_verified = activated
                profile.password_change_required = not activated
                profile.save(update_fields=["email_verified", "password_change_required", "updated_at"])
                return user

            cls.valid = student("isc2.valid", cls.group)
            cls.stale = student("isc2.stale", cls.subgroup, password="reset-later")
            cls.missing = student("isc2.missing", cls.group)
            cls.active = student("isc2.active", cls.group, activated=True)
            cls.leave = student("isc2.leave", cls.group, status="academic_leave")
            cls.other = student("isc2.other", cls.other_group)

    def _run(self, **kwargs):
        tmp = Path(tempfile.mkdtemp())
        known = tmp / "known.txt"
        known.write_text(
            "isc2.valid\tlist-pass\nisc2.stale\tlist-pass\nisc2.active\tlist-pass\nisc2.other\tlist-pass\n",
            encoding="utf-8",
        )
        report = tmp / "report.csv"
        out = io.StringIO()
        call_command(
            "issue_staff_credentials",
            "--org",
            "isc2-org",
            "--audience",
            "students",
            "--known-usernames",
            str(known),
            "--report-out",
            str(report),
            stdout=out,
            **kwargs,
        )
        return out.getvalue(), {r["username"]: r for r in csv.DictReader(report.open(encoding="utf-8"))}

    def test_dry_run_checks_list_passwords_and_skips_non_enrolled(self):
        out, rows = self._run(faculty="Dizayn məktəbi")
        self.assertEqual(set(rows), {"isc2.valid", "isc2.stale", "isc2.missing", "isc2.active"})
        self.assertEqual(rows["isc2.valid"]["emel"], "siyahıdakı ilkin parol (yoxlanıldı)")
        self.assertEqual(rows["isc2.stale"]["emel"], "yeni ilkin parol veriləcək")
        self.assertEqual(rows["isc2.missing"]["emel"], "yeni ilkin parol veriləcək")
        self.assertIn("parol verilmir", rows["isc2.active"]["emel"])
        self.assertEqual(rows["isc2.stale"]["qrup"], "321")
        self.assertEqual(rows["isc2.stale"]["alt_qrup"], "321/A")
        self.assertEqual(rows["isc2.valid"]["fakulte"], "Dizayn məktəbi")
        self.assertIn("list_password_valid=1", out)
        self.assertIn("list_password_stale=1", out)
        self.assertIn("new_targets=2", out)
        self.assertNotIn("isc2.", out)

    def test_apply_without_faculty_covers_all_and_writes_new_passwords(self):
        creds_path = Path(tempfile.mkdtemp()) / "creds.csv"
        out, rows = self._run(
            apply=True,
            credentials_out=str(creds_path),
            reason="Tələbələrin ilkin parol siyahısının tamamlanması",
            i_know_this_is_production=True,
        )
        self.assertIn("isc2.other", rows)
        creds = {r["username"]: r for r in csv.DictReader(creds_path.open(encoding="utf-8"))}
        self.assertEqual(set(creds), {"isc2.stale", "isc2.missing"})
        self.assertEqual(creds["isc2.stale"]["sebeb"], "siyahıdakı parol uyğun deyil")
        self.stale.refresh_from_db()
        self.assertTrue(self.stale.check_password(creds["isc2.stale"]["ilkin_parol"]))
        self.assertTrue(self.stale.profile.password_change_required)
        for untouched in (self.valid, self.other, self.active):
            untouched.refresh_from_db()
            self.assertTrue(untouched.check_password("list-pass"), untouched.username)
        self.assertIn("issued=2", out)
