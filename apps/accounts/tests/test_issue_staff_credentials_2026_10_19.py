"""``issue_staff_credentials`` — siyahıda olmayan, aktivləşməmiş fakültə heyətinə ilkin parol (sahib 2026-10-19)."""

from __future__ import annotations

import csv
import io
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.organizations.models import Membership, Organization, OrgUnit
from core.constants import OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()


class IssueStaffCredentialsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        owner = User.objects.create_user("isc_owner", "isc@isc.test", "pw")
        with bypass_rls():
            cls.org = Organization.objects.create(
                name="ISC", slug="isc-org", org_type=OrganizationType.UNIVERSITY, owner=owner, status="active"
            )
            unit = OrgUnit.objects.create
            cls.fac = unit(
                organization=cls.org, name="Yüksək texnologiyalar", slug="isc-f", unit_type=OrgUnitType.FACULTY
            )
            cls.chair = unit(
                organization=cls.org, name="Təbiət elmləri", slug="isc-c", unit_type=OrgUnitType.CHAIR, parent=cls.fac
            )
            other = unit(organization=cls.org, name="Dizayn", slug="isc-o", unit_type=OrgUnitType.FACULTY)
            teacher_role = cls.org.roles.get(name="teacher")
            student_role = cls.org.roles.get(name="student")
            vice_dean = cls.org.roles.get(name="vice_dean")

            def member(username, role, scope, *, activated=False, first="Ad", last="Soyad"):
                user = User.objects.create_user(
                    username, f"{username}@isc.test", "old-pass", first_name=first, last_name=last
                )
                Membership.objects.create(user=user, organization=cls.org, role=role, scope_unit=scope, is_active=True)
                profile = user.profile
                profile.email_verified = activated
                profile.password_change_required = not activated
                profile.save(update_fields=["email_verified", "password_change_required", "updated_at"])
                return user

            cls.known = member("isc.known", teacher_role, cls.chair)
            cls.new = member("isc.new", teacher_role, cls.chair)
            cls.active = member("isc.active", teacher_role, cls.chair, activated=True)
            cls.vice = member("isc.vice", vice_dean, cls.fac, first="Aynurə", last="Qocuyeva")
            cls.student = member("isc.student", student_role, cls.chair)
            cls.outside = member("isc.outside", teacher_role, other)

    def _run(self, **kwargs):
        tmp = Path(tempfile.mkdtemp())
        known = tmp / "known.txt"
        known.write_text("isc.known\n", encoding="utf-8")
        report, creds = tmp / "report.csv", tmp / "creds.csv"
        out = io.StringIO()
        call_command(
            "issue_staff_credentials",
            "--org",
            "isc-org",
            "--known-usernames",
            str(known),
            "--report-out",
            str(report),
            stdout=out,
            **kwargs,
        )
        rows = list(csv.DictReader(report.open(encoding="utf-8")))
        cred_rows = list(csv.DictReader(creds.open(encoding="utf-8"))) if creds.exists() else []
        return out.getvalue(), rows, cred_rows, creds

    def test_dry_run_lists_faculty_staff_without_writing(self):
        out, rows, _creds, _ = self._run(faculty="yuksek texno")
        usernames = {r["username"]: r for r in rows}
        self.assertEqual(set(usernames), {"isc.known", "isc.new", "isc.active", "isc.vice"})  # tələbə/kənar yox
        self.assertEqual(usernames["isc.new"]["emel"], "yeni ilkin parol veriləcək")
        self.assertEqual(usernames["isc.known"]["emel"], "siyahıdakı ilkin parol")
        self.assertIn("parol verilmir", usernames["isc.active"]["emel"])
        self.assertIn("mode=DRY-RUN", out)
        self.assertIn("new_targets=2", out)  # isc.new + isc.vice
        self.assertNotIn("isc.new", out)  # stdout-a yalnız saylar
        self.new.refresh_from_db()
        self.assertTrue(self.new.check_password("old-pass"))

    def test_apply_issues_only_missing_inactive_accounts(self):
        tmp = Path(tempfile.mkdtemp()) / "creds.csv"
        out, rows, _c, _ = self._run(
            faculty="Yüksək",
            apply=True,
            credentials_out=str(tmp),
            reason="Fakültə üzrə ilkin parol siyahısının tamamlanması",
            i_know_this_is_production=True,
        )
        creds = list(csv.DictReader(tmp.open(encoding="utf-8")))
        self.assertEqual({r["username"] for r in creds}, {"isc.new", "isc.vice"})
        password = next(r["ilkin_parol"] for r in creds if r["username"] == "isc.new")
        self.new.refresh_from_db()
        self.assertTrue(self.new.check_password(password))
        self.assertTrue(self.new.profile.password_change_required)
        for untouched in (self.known, self.active, self.student, self.outside):
            untouched.refresh_from_db()
            self.assertTrue(untouched.check_password("old-pass"), untouched.username)
        self.assertIn("issued=2", out)

    def test_find_name_reports_role_and_faculty(self):
        _out, rows, _c, _ = self._run(find_name="aynure qocuyeva")
        found = [r for r in rows if r["nov"] == "find"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["fakulte"], "Yüksək texnologiyalar")

    def test_apply_requires_reason_and_credentials_file(self):
        with self.assertRaises(CommandError):
            self._run(faculty="Yüksək", apply=True, reason="qısa", i_know_this_is_production=True)
        with self.assertRaises(CommandError):
            self._run(faculty="Yüksək", apply=True, reason="x" * 25, i_know_this_is_production=True)

    def test_center_unit_is_accepted(self):
        with bypass_rls():
            center = OrgUnit.objects.create(
                organization=self.org, name="İngilis dili mərkəzi", slug="isc-ce", unit_type=OrgUnitType.CENTER
            )
            user = User.objects.create_user("isc.center", "isc.center@isc.test", "old-pass")
            Membership.objects.create(
                user=user,
                organization=self.org,
                role=self.org.roles.get(name="teacher"),
                scope_unit=center,
                is_active=True,
            )
        _out, rows, _c, _ = self._run(faculty="İngilis dili mərkəzi")
        self.assertEqual([r["username"] for r in rows], ["isc.center"])

    def test_ambiguous_faculty_is_refused(self):
        with self.assertRaises(CommandError):
            self._run(faculty="a")
