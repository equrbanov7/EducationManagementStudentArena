"""Codex audit §7 (2026-09-13) — «Göstəricilər (CSV)» rol-aware ixracı.

Tapıntı: statistika CSV-si köhnə göndəriş selector-larını ixrac edirdi; ekranda
görünən yeni rol-aware göstəricilər (`services/statistics_metrics/`) heç bir
ixraca düşmürdü. Yeni ixrac (`statistics_export_metrics.py`):

  * tələbə / müəllim / org-admin — hər rol öz profilinin sətirlərini alır;
  * əhatə dashboard ilə EYNİDİR (P1-11): unit-əhatəli dekan yalnız öz
    alt-ağacını, əhatəsiz dekan BOŞ alt-ağacı alır, `stat_organization` parametri
    superadmin olmayanda nəzərə alınmır;
  * superadmin təşkilat süzgəci ötürülür;
  * UTF-8 BOM + düstur-inyeksiyası neytrallaşdırılır;
  * bölməsi olmayan aktor → 404 (köhnə ixrac ilə eyni qapı).
"""

from unittest import mock

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.accounts.views.profile.statistics_export_metrics import UTF8_BOM, build_metrics_csv_rows
from apps.organizations.models import Membership, Organization, OrgUnit
from core.constants import OrganizationType, OrgUnitType

User = get_user_model()
PASSWORD = "StrongPass123!"
URL_NAME = "accounts:statistics_export_metrics_csv"


def _user(username):
    return User.objects.create_user(username, f"{username}@stxcsv.test", PASSWORD)


def _member(org, user, role_name, scope_unit=None, *, is_primary=True):
    return Membership.objects.create(
        user=user,
        organization=org,
        role=org.roles.get(name=role_name),
        scope_unit=scope_unit,
        is_primary=is_primary,
        is_active=True,
    )


def _client(user, org=None):
    client = Client()
    client.force_login(user)
    if org is not None:
        session = client.session
        session["active_organization"] = org.slug
        session.save()
    return client


def _passthrough_cache():
    return mock.patch("core.cache.get_or_set_cached_statistics", side_effect=lambda **kw: kw["compute"]())


class _World(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = _user("stxcsv_owner")
        cls.org = Organization.objects.create(
            name="STX CSV University",
            slug="stx-csv-university",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        cls.faculty_a = OrgUnit.objects.create(organization=cls.org, unit_type=OrgUnitType.FACULTY, name="Fakültə A")
        cls.chair_a1 = OrgUnit.objects.create(
            organization=cls.org, unit_type=OrgUnitType.CHAIR, name="Kafedra A1", parent=cls.faculty_a
        )
        cls.faculty_b = OrgUnit.objects.create(organization=cls.org, unit_type=OrgUnitType.FACULTY, name="Fakültə B")
        cls.chair_b1 = OrgUnit.objects.create(
            organization=cls.org, unit_type=OrgUnitType.CHAIR, name="Kafedra B1", parent=cls.faculty_b
        )
        cls.student = _user("stxcsv_student")
        _member(cls.org, cls.student, "student", cls.chair_a1)
        cls.teacher = _user("stxcsv_teacher")
        _member(cls.org, cls.teacher, "teacher", cls.chair_a1)
        cls.vice_rector = _user("stxcsv_vice_rector")
        _member(cls.org, cls.vice_rector, "vice_rector")
        # Dekan (əhatə: Fakültə A) + başqa fakültənin kafedrasına «borc» müəllim üzvlüyü.
        cls.dean_lent = _user("stxcsv_dean_lent")
        _member(cls.org, cls.dean_lent, "dean", cls.faculty_a)
        _member(cls.org, cls.dean_lent, "teacher", cls.chair_b1, is_primary=False)
        cls.dean_unscoped = _user("stxcsv_dean_unscoped")
        _member(cls.org, cls.dean_unscoped, "dean", None)
        # Rəqəm olsun deyə: müəllimin imtahanı + tələbənin bitmiş cəhdi.
        from apps.exams.models import Exam, ExamAttempt

        cls.exam = Exam.objects.create(title="STX CSV imtahanı", author=cls.teacher, organization=cls.org)
        ExamAttempt.objects.create(
            user=cls.student, exam=cls.exam, status="submitted", checked_by_teacher=True, teacher_score=80
        )

    def _csv(self, user, org=None, query=""):
        response = _client(user, org).get(reverse(URL_NAME) + query)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertIn('filename="statistics_metrics.csv"', response["Content-Disposition"])
        text = response.content.decode("utf-8")
        self.assertTrue(text.startswith(UTF8_BOM))
        return text[len(UTF8_BOM) :].splitlines()

    def _captured_scoped_ids(self, user, query=""):
        from apps.accounts.services.statistics_metrics.org import org_metrics

        calls = []

        def capture(**kwargs):
            calls.append(kwargs.get("scoped_unit_ids"))
            return org_metrics(**kwargs)

        with (
            _passthrough_cache(),
            mock.patch("apps.accounts.services.statistics_metrics.org_metrics", side_effect=capture),
        ):
            self._csv(user, self.org, query)
        self.assertEqual(len(calls), 1)
        return calls[0]


class RoleRowsTest(_World):
    def test_student_gets_personal_profile_rows(self):
        lines = self._csv(self.student, self.org)
        self.assertEqual(lines[0], "Bölmə,Sətir,Göstərici,Dəyər,Vahid,Qeyd")
        self.assertIn("Kontekst,,Profil,student,,", lines)
        self.assertTrue(any(line.startswith("Əsas göstəricilər,,İmtahan cəhdləri,1,") for line in lines), lines[:8])
        # Şəxsi mənzərədə təşkilat/kurs süzgəci və başqa rolun blokları yoxdur.
        self.assertFalse(any(line.startswith("Təşkilatlar,") for line in lines))

    def test_teacher_gets_teacher_profile_rows(self):
        lines = self._csv(self.teacher, self.org)
        self.assertIn("Kontekst,,Profil,teacher,,", lines)
        self.assertTrue(any(line.startswith("Əsas göstəricilər,,İmtahanlarım,1,") for line in lines), lines[:12])
        # Tələbənin şəxsi kartı müəllim ixracına düşmür.
        self.assertFalse(any("İmtahan cəhdləri" in line for line in lines))

    def test_org_admin_gets_org_wide_profile_rows(self):
        lines = self._csv(self.vice_rector, self.org)
        self.assertIn("Kontekst,,Profil,org_admin,,", lines)
        self.assertTrue(any(line.startswith("Əsas göstəricilər,") for line in lines))

    def test_superadmin_gets_org_comparison_and_selector_is_respected(self):
        superuser = User.objects.create_superuser("stxcsv_super", "stxcsv_super@stxcsv.test", PASSWORD)
        from apps.accounts.services.statistics_metrics.superadmin import superadmin_metrics

        seen = []

        def capture(**kwargs):
            seen.append(kwargs.get("organization_id"))
            return superadmin_metrics(**kwargs)

        with (
            _passthrough_cache(),
            mock.patch("apps.accounts.services.statistics_metrics.superadmin_metrics", side_effect=capture),
        ):
            lines = self._csv(superuser, query=f"?stat_organization={self.org.pk}")
        self.assertEqual(seen, [str(self.org.pk)])
        self.assertIn("Kontekst,,Profil,superadmin,,", lines)
        self.assertTrue(any(line.startswith(f"Təşkilatlar,{self.org.name},Üzvlər,") for line in lines), lines)


class ScopeTest(_World):
    def test_unit_scoped_dean_exports_only_own_subtree(self):
        scoped = self._captured_scoped_ids(self.dean_lent)
        self.assertEqual(set(scoped), {self.faculty_a.pk, self.chair_a1.pk})
        self.assertNotIn(self.chair_b1.pk, scoped)

    def test_unscoped_dean_is_fail_closed_not_org_wide(self):
        self.assertEqual(self._captured_scoped_ids(self.dean_unscoped), [])

    def test_stat_organization_param_is_ignored_for_non_superadmin(self):
        other = Organization.objects.create(
            name="Other Org", slug="stx-csv-other", org_type=OrganizationType.UNIVERSITY, owner=self.owner
        )
        scoped = self._captured_scoped_ids(self.dean_lent, query=f"?stat_organization={other.pk}")
        self.assertEqual(set(scoped), {self.faculty_a.pk, self.chair_a1.pk})

    def test_actor_without_statistics_section_gets_404(self):
        with mock.patch(
            "apps.accounts.views.profile.statistics_export_metrics._role_capabilities",
            return_value={"allowed_sections": set(), "is_superadmin": False},
        ):
            response = _client(self.student, self.org).get(reverse(URL_NAME))
        self.assertEqual(response.status_code, 404)

    def test_anonymous_is_redirected_to_login(self):
        response = Client().get(reverse(URL_NAME))
        self.assertEqual(response.status_code, 302)


class FormulaNeutralisationTest(TestCase):
    def test_cells_starting_with_formula_characters_are_prefixed(self):
        presented = {
            "scope_label": '=HYPERLINK("http://evil")',
            "window": {"period_name": "+cmd", "date_from": "2026-02-01", "date_to": "2026-06-30"},
            "kpis": [{"label": "-1+1", "value": "@SUM(A1)", "unit": "\tx", "note": None}],
            "blocks": [
                {"title": "Blok", "bars": [{"label": "=1", "value_label": "5", "sub": ""}]},
                {
                    "title": "Cədvəl",
                    "columns": [{"label": "Ad"}, {"label": "Sütun"}],
                    "rows": [{"row_head": "=A", "cells": [{"text": "=B"}]}],
                },
            ],
            "extra": [],
        }
        rows = build_metrics_csv_rows("teacher", presented)
        flat = [cell for row in rows for cell in row]
        for dangerous in ('=HYPERLINK("http://evil")', "+cmd", "-1+1", "@SUM(A1)", "\tx", "=1", "=A", "=B"):
            self.assertIn("'" + dangerous, flat)
            self.assertNotIn(dangerous, flat)
        self.assertEqual(rows[0], ["Bölmə", "Sətir", "Göstərici", "Dəyər", "Vahid", "Qeyd"])
        # Cədvəl xanası `columns[1:]`-ə uyğunlaşır (`columns[0]` = sətir başlığı).
        self.assertIn(["Cədvəl", "'=A", "Sütun", "'=B", "", ""], rows)
