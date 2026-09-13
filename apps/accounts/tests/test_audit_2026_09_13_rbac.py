"""Audit `access` (2026-09-13) — RBAC / tenant tapıntılarının reqressiya testləri.

Auditorun zondları (`scratchpad/audit/access/probes/test_member_removal_probes.py`,
`test_rbac_tenant_probes.py` M01–M05, T60, F43) ilə eyni sintetik mühit: iki
təşkilat (A, B), default universitet rolları, iki fakültə.

* F-03 — imtahan mərkəzi rəhbəri (85, `member.remove` YOX) üzv uzaqlaşdıra bilməz;
* F-04 — dekan yalnız öz fakültəsinin alt-ağacında (unit scope, fail-closed);
* F-06 — `member.remove` real qapıdır; «ölü» reyestr açarları pinlənir;
* F-07 — yad tenantın slug-lu struktur səhifəsi 200 boş qabıq yox, select-ə 302;
* F-12 — `assignment.edit` kataloqda + müəllim şablonunda; adi müəllim öz
  tapşırığından tələbə çıxara bilir;
* F-13 — `workload:rows?chair=<yad>` qardaşları kimi 403 `chair_not_found`.
"""

from __future__ import annotations

import os
import re

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.courses.models import Course, CourseMembership
from apps.organizations.models import Membership, Organization, OrgUnit
from core.constants import OrganizationType, OrgUnitType
from core.rls import bypass_rls

User = get_user_model()
PW = "AuditPass123!"


def _build_org(tag):
    owner = User.objects.create_user(f"rbac_owner_{tag}", f"rbac_owner_{tag}@audit.az", PW)
    org = Organization.objects.create(
        name=f"RBAC Univ {tag}",
        slug=f"rbac-{tag}",
        org_type=OrganizationType.UNIVERSITY,
        owner=owner,
        status="active",
        is_active=True,
    )
    fac = OrgUnit.objects.create(organization=org, name=f"Fak {tag}", slug=f"fak-{tag}", unit_type=OrgUnitType.FACULTY)
    chair = OrgUnit.objects.create(
        organization=org, name=f"Kaf {tag}", slug=f"kaf-{tag}", unit_type=OrgUnitType.CHAIR, parent=fac
    )
    group = OrgUnit.objects.create(
        organization=org, name=f"Qrup {tag}", slug=f"grp-{tag}", unit_type=OrgUnitType.GROUP, parent=chair
    )
    fac2 = OrgUnit.objects.create(
        organization=org, name=f"Fak2 {tag}", slug=f"fak2-{tag}", unit_type=OrgUnitType.FACULTY
    )
    chair2 = OrgUnit.objects.create(
        organization=org, name=f"Kaf2 {tag}", slug=f"kaf2-{tag}", unit_type=OrgUnitType.CHAIR, parent=fac2
    )
    group2 = OrgUnit.objects.create(
        organization=org, name=f"Qrup2 {tag}", slug=f"grp2-{tag}", unit_type=OrgUnitType.GROUP, parent=chair2
    )
    users = {}
    for key, role_name, unit in (
        ("rector", "rector", None),
        ("dean", "dean", fac),
        ("teacher", "teacher", None),
        ("teacher2", "teacher", None),
        ("hr", "hr", None),
        ("exam_center_head", "exam_center_head", None),
        ("student", "student", group),
        ("student2", "student", group2),
        ("member", "member", None),
    ):
        user = User.objects.create_user(f"rbac_{key}_{tag}", f"rbac_{key}_{tag}@audit.az", PW)
        Membership.objects.create(
            user=user,
            organization=org,
            role=org.roles.get(name=role_name),
            scope_unit=unit,
            is_primary=True,
            is_active=True,
        )
        users[key] = user
    return {
        "org": org,
        "owner": owner,
        "fac": fac,
        "chair": chair,
        "group": group,
        "fac2": fac2,
        "group2": group2,
        "users": users,
    }


class _Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            cls.A = _build_org("a")
            cls.B = _build_org("b")

    def client_for(self, user, org):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = org.slug
        session.save()
        return client

    def ua(self, key):
        return self.A["users"][key]

    def ub(self, key):
        return self.B["users"][key]

    def is_active_member(self, user, org):
        with bypass_rls():
            return Membership.objects.filter(user=user, organization=org, is_active=True).exists()


class MemberRemovalGateTest(_Base):
    """F-03 / F-04 — `student_organization_management` remove_* əməlləri."""

    URL_NAME = "accounts:student_organization_management"

    def _remove(self, actor, target, *, action="remove_org_member"):
        client = self.client_for(actor, self.A["org"])
        return client.post(
            reverse(self.URL_NAME),
            {"action": action, "user_id": str(target.pk), "remove_reason": "audit"},
        )

    def test_f03_exam_center_head_cannot_remove_teacher(self):
        response = self._remove(self.ua("exam_center_head"), self.ua("teacher"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.is_active_member(self.ua("teacher"), self.A["org"]))

    def test_f03_exam_center_head_cannot_remove_hr(self):
        response = self._remove(self.ua("exam_center_head"), self.ua("hr"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.is_active_member(self.ua("hr"), self.A["org"]))

    def test_f03_hr_with_member_remove_still_removes_teacher(self):
        """Nəzarət: açarı daşıyan ORGANIZATION rolu (HR) əvvəlki kimi işləyir."""
        response = self._remove(self.ua("hr"), self.ua("teacher"))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(self.is_active_member(self.ua("teacher"), self.A["org"]))

    def test_f03_owner_and_rector_wildcard_still_remove(self):
        response = self._remove(self.A["owner"], self.ua("teacher2"))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(self.is_active_member(self.ua("teacher2"), self.A["org"]))
        response = self._remove(self.ua("rector"), self.ua("member"))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(self.is_active_member(self.ua("member"), self.A["org"]))

    def test_f04_dean_without_member_remove_cannot_remove_other_faculty_student(self):
        """Zond M03: dekan(fak1) → student2(fak2). Default dekan şablonunda
        `member.remove` YOXDUR → açar qapısı rədd edir."""
        response = self._remove(self.ua("dean"), self.ua("student2"), action="remove_student")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.is_active_member(self.ua("student2"), self.A["org"]))

    def test_f04_dean_granted_member_remove_is_limited_to_own_subtree(self):
        """`member.remove` verilən UNIT-scope dekan: öz fakültəsi ✅, başqa fakültə ❌."""
        with bypass_rls():
            dean_role = self.A["org"].roles.get(name="dean")
            dean_role.permissions = list(dean_role.permissions) + ["member.remove"]
            dean_role.save(update_fields=["permissions"])
        try:
            denied = self._remove(self.ua("dean"), self.ua("student2"), action="remove_student")
            self.assertEqual(denied.status_code, 302)
            self.assertTrue(self.is_active_member(self.ua("student2"), self.A["org"]))

            allowed = self._remove(self.ua("dean"), self.ua("student"), action="remove_student")
            self.assertEqual(allowed.status_code, 302)
            self.assertFalse(self.is_active_member(self.ua("student"), self.A["org"]))
        finally:
            with bypass_rls():
                dean_role.permissions = [p for p in dean_role.permissions if p != "member.remove"]
                dean_role.save(update_fields=["permissions"])

    def test_student_manage_delegation_covers_students_only(self):
        """`member.student_manage` (müəllimə delegasiya) tələbəni çıxarır, `member` rolunu YOX."""
        with bypass_rls():
            teacher_role = self.A["org"].roles.get(name="teacher")
            teacher_role.permissions = list(teacher_role.permissions) + ["member.student_manage"]
            teacher_role.save(update_fields=["permissions"])
        try:
            denied = self._remove(self.ua("teacher"), self.ua("member"))
            self.assertEqual(denied.status_code, 302)
            self.assertTrue(self.is_active_member(self.ua("member"), self.A["org"]))

            allowed = self._remove(self.ua("teacher"), self.ua("student2"), action="remove_student")
            self.assertEqual(allowed.status_code, 302)
            self.assertFalse(self.is_active_member(self.ua("student2"), self.A["org"]))
        finally:
            with bypass_rls():
                teacher_role.permissions = [p for p in teacher_role.permissions if p != "member.student_manage"]
                teacher_role.save(update_fields=["permissions"])

    def test_cross_tenant_removal_still_blocked(self):
        """Zond M05 — B rektoru A müəllimini çıxara bilmir (dəyişməməlidir)."""
        client = self.client_for(self.ub("rector"), self.B["org"])
        response = client.post(
            reverse(self.URL_NAME),
            {"action": "remove_org_member", "user_id": str(self.ua("teacher").pk), "remove_reason": "audit"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(self.is_active_member(self.ua("teacher"), self.A["org"]))


_KEY_PATTERN = re.compile(r"""["']([a-z_]+\.[a-z_]+(?:\.[a-z_]+)?)["']""")
_SKIP_DIRS = {"tests", "migrations", "__pycache__", "node_modules", "static", "venv", ".venv", "locale", "docs"}

# F-06 — reyestrdə olub kodda HEÇ YERDƏ istinad olunmayan açarlar (2026-09-13
# vəziyyəti). İcazə redaktoru bu açarları göstərir, amma verib/almaq heç nəyi
# dəyişmir. Siyahı RATCHET-dir: yeni «ölü» açar → test qırılır (ya qapıya bağla,
# ya bura səbəblə əlavə et); açar qapıya bağlananda buradan SİLİNMƏLİDİR.
KNOWN_UNREFERENCED_PERMISSION_KEYS = frozenset(
    {
        "analytics.view_own",
        "audit.export",
        "grade.override",
        "journal.view",
        "org.delete",
        "org.edit",
        "org.settings",
        "qa.flag",
        "qa.review",
        "qa.view",
        "role.create",
        "role.delete",
        "role.edit",
    }
)


def _referenced_permission_keys(root, catalog):
    found = set()
    for base in ("apps", "core", "config", "templates"):
        for dirpath, dirnames, filenames in os.walk(os.path.join(root, base)):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
            for filename in filenames:
                if not filename.endswith((".py", ".html")) or filename.startswith("test"):
                    continue
                path = os.path.join(dirpath, filename)
                rel = os.path.relpath(path, root)
                if rel.startswith(("apps/organizations/permissions", "apps/organizations/default_roles")):
                    continue
                with open(path, encoding="utf-8", errors="ignore") as handle:
                    for match in _KEY_PATTERN.finditer(handle.read()):
                        if match.group(1) in catalog:
                            found.add(match.group(1))
    return found


class PermissionCatalogDriftTest(TestCase):
    """F-06 — reyestr ↔ kod drift-i CI-də görünsün (auditorun setB skriptinin CI versiyası)."""

    def test_unreferenced_registry_keys_are_pinned(self):
        from django.conf import settings

        from apps.organizations.permissions import get_all_permissions

        catalog = set(get_all_permissions())
        referenced = _referenced_permission_keys(str(settings.BASE_DIR), catalog)
        dead = catalog - referenced
        newly_dead = sorted(dead - KNOWN_UNREFERENCED_PERMISSION_KEYS)
        self.assertEqual(newly_dead, [], f"Kodda yoxlanmayan YENİ reyestr açarları: {newly_dead}")
        revived = sorted(KNOWN_UNREFERENCED_PERMISSION_KEYS - dead)
        self.assertEqual(revived, [], f"Artıq qapıya bağlanıb — pin siyahısından silin: {revived}")

    def test_member_remove_and_assignment_edit_are_wired(self):
        from django.conf import settings

        from apps.organizations.permissions import get_all_permissions

        catalog = set(get_all_permissions())
        referenced = _referenced_permission_keys(str(settings.BASE_DIR), catalog)
        self.assertIn("member.remove", referenced)
        self.assertIn("assignment.edit", catalog)
        self.assertIn("assignment.edit", referenced)


class ForeignOrgStructurePageTest(_Base):
    """F-07 — slug-lu struktur səhifəsi yad tenant üçün select-ə yönləndirir."""

    def test_foreign_rector_is_redirected_to_select(self):
        client = self.client_for(self.ub("rector"), self.B["org"])
        for name in ("organizations:structure_faculties", "organizations:structure_kafedras"):
            response = client.get(reverse(name, kwargs={"slug": self.A["org"].slug}))
            self.assertEqual(response.status_code, 302, name)
            self.assertEqual(response.url, reverse("organizations:select"), name)

    def test_own_rector_and_scoped_dean_still_see_page(self):
        client = self.client_for(self.ua("rector"), self.A["org"])
        response = client.get(reverse("organizations:structure_faculties", kwargs={"slug": self.A["org"].slug}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.A["fac"].name)

        dean_client = self.client_for(self.ua("dean"), self.A["org"])
        response = dean_client.get(reverse("organizations:structure_faculties", kwargs={"slug": self.A["org"].slug}))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.A["fac"].name)
        self.assertNotContains(response, self.A["fac2"].name)


class AssignmentEditKeyTest(_Base):
    """F-12 — `assignment.edit` kataloqda, müəllim şablonunda və endpoint müəllimə açıqdır."""

    def test_key_in_catalog_and_teacher_templates(self):
        from apps.organizations.default_roles import DEFAULT_ROLES
        from apps.organizations.permissions import PERMISSION_CATEGORIES, PERMISSION_LABELS, get_all_permissions

        self.assertIn("assignment.edit", PERMISSION_CATEGORIES["courses"])
        self.assertIn("assignment.edit", get_all_permissions())
        self.assertTrue(str(PERMISSION_LABELS["assignment.edit"]).strip())
        university_teacher = next(r for r in DEFAULT_ROLES[OrganizationType.UNIVERSITY] if r["name"] == "teacher")
        self.assertIn("assignment.edit", university_teacher["permissions"])

    def test_default_teacher_can_remove_student_from_own_assignment(self):
        from apps.assignments.models import Assignment

        teacher = self.ua("teacher")
        student = self.ua("student")
        with bypass_rls():
            course = Course.objects.create(
                owner=teacher, title="F-12 Course", status="published", organization=self.A["org"]
            )
            CourseMembership.objects.create(course=course, user=student, role="student")
            assignment = Assignment.objects.create(course=course, title="F-12 Assignment", start_date=timezone.now())
            assignment.assigned_students.add(student)

        client = self.client_for(teacher, self.A["org"])
        response = client.post(
            reverse("assignments:remove_student_from_assignment", kwargs={"pk": assignment.pk}),
            data={"student_id": str(student.pk)},
        )
        self.assertEqual(response.status_code, 200, response.content[:200])
        self.assertTrue(response.json().get("success"))
        with bypass_rls():
            self.assertFalse(assignment.assigned_students.filter(pk=student.pk).exists())

    def test_teacher2_is_not_course_owner(self):
        from apps.assignments.models import Assignment

        teacher = self.ua("teacher")
        with bypass_rls():
            course = Course.objects.create(
                owner=teacher, title="F-12 Course 2", status="published", organization=self.A["org"]
            )
            assignment = Assignment.objects.create(course=course, title="F-12 Assignment 2", start_date=timezone.now())
        client = self.client_for(self.ua("teacher2"), self.A["org"])
        response = client.post(
            reverse("assignments:remove_student_from_assignment", kwargs={"pk": assignment.pk}),
            data={"student_id": str(self.ua("student").pk)},
        )
        self.assertEqual(response.status_code, 403)


class WorkloadRowsForeignChairTest(_Base):
    """F-13 — `workload:rows?chair=<yad>` → 403 `workload.chair_not_found` (qardaşları kimi)."""

    def test_foreign_chair_returns_403_like_siblings(self):
        client = self.client_for(self.ub("rector"), self.B["org"])
        for name in ("workload:teachers", "workload:options", "workload:rows"):
            response = client.get(reverse(name), {"chair": str(self.A["chair"].pk), "year": "2024/2025"})
            self.assertEqual(response.status_code, 403, name)
            self.assertEqual(response.json().get("error"), "workload.chair_not_found", name)

    def test_own_chair_without_task_still_returns_empty_shell(self):
        client = self.client_for(self.ua("rector"), self.A["org"])
        response = client.get(reverse("workload:rows"), {"chair": str(self.A["chair"].pk), "year": "2024/2025"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertIsNone(payload["task"])
        self.assertEqual(payload["rows"], [])


class GuestRosterDocumentRlsMigrationTest(TestCase):
    """F-05 — miqrasiya faylı mövcuddur və hədəf cədvəli göstərir (DB səviyyəli
    yoxlama `core/tests/test_audit_2026_09_13_rls_coverage.py`-dədir)."""

    def test_migration_targets_guest_roster_document(self):
        from importlib import import_module

        module = import_module("apps.registrar.migrations.0074_rls_guest_roster_document")
        self.assertEqual(module._TABLES, ["registrar_guestrosterdocument"])
        self.assertIn(("registrar", "0073_exam_score_sheet_integrity"), module.Migration.dependencies)
