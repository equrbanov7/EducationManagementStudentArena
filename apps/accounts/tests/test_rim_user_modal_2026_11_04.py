"""RİM istifadəçi kartı (sahib 2026-11-04): fakültə/kafedra yerləşdirilməsi, vəzifə, «Məzun et», əməkdaş arxivi.

Fokus: icazə qapıları, əhatə (scope), audit izi, arxiv ↔ bərpa dövrü (tarixçə itmir), iyerarxiyanın arxivdə də
qorunması və müəllimin kafedraya bağlanandan sonra dərs yükü siyahısına düşməsi.
"""

from __future__ import annotations

import datetime

from django.urls import reverse

from apps.accounts.models import UserProfile
from apps.accounts.services.rim import staff_archive
from apps.accounts.services.rim.policy import SUPERADMIN_LEVEL, RimActor
from apps.audit.models import AuditLog
from apps.organizations.models import Membership, OrgUnit
from apps.registrar.models import Curriculum, Program, StudentAcademicRecord, StudentMovement
from core.constants import OrgUnitType, RoleScopeType

from .test_rim_center import RimCenterTestBase, add_member, make_role, make_user

PLACEMENT_PERMS = ["role.assign", "user.import_staff"]
GRADUATION_PERMS = ["student.movement", "people.manage_academic", "student.registry_view", "people.view_students"]


class RimModalBase(RimCenterTestBase):
    def setUp(self):
        super().setUp()
        self.faculty = OrgUnit.objects.create(
            organization=self.org, name="İnformasiya texnologiyaları", slug="it-fac", unit_type=OrgUnitType.FACULTY
        )
        self.chair = OrgUnit.objects.create(
            organization=self.org,
            name="Proqram mühəndisliyi",
            slug="se-chair",
            unit_type=OrgUnitType.CHAIR,
            parent=self.faculty,
        )
        self.other_chair = OrgUnit.objects.create(
            organization=self.org,
            name="Riyaziyyat",
            slug="math-chair",
            unit_type=OrgUnitType.CHAIR,
            parent=self.faculty,
        )

    def grant(self, *permissions):
        self.rim_role.permissions = sorted({*self.rim_role.permissions, *permissions})
        self.rim_role.save(update_fields=["permissions"])

    def revoke(self, *permissions):
        self.rim_role.permissions = [perm for perm in self.rim_role.permissions if perm not in permissions]
        self.rim_role.save(update_fields=["permissions"])

    def detail(self, user):
        return self.client.get(reverse("accounts:rim_user_detail", args=[user.pk]))

    def teacher_membership(self, user=None):
        return Membership.objects.get(user=user or self.teacher, role=self.teacher_role)


class RimPlacementTests(RimModalBase):
    def setUp(self):
        super().setUp()
        self.grant(*PLACEMENT_PERMS)
        self.login_operator()

    def place(self, unit, membership=None, expected="", **extra):
        membership = membership or self.teacher_membership()
        return self.act(
            "place_unit",
            self.teacher,
            membership_id=str(membership.pk),
            unit_id=str(unit.pk) if unit is not None else "",
            expected_unit_id=expected,
            **extra,
        )

    def test_unplaced_teacher_lands_in_chair_and_workload_pool(self):
        from apps.workload.services.people import chair_teacher_memberships

        self.assertFalse(chair_teacher_memberships(self.org, self.chair, include_unscoped=False).exists())
        response = self.place(self.chair)
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertTrue(body["placement_result"]["changed"])
        membership = self.teacher_membership()
        self.assertEqual(membership.scope_unit_id, self.chair.pk)
        pool = chair_teacher_memberships(self.org, self.chair, include_unscoped=False)
        self.assertEqual(list(pool.values_list("user_id", flat=True)), [self.teacher.pk])
        self.teacher.profile.refresh_from_db()
        self.assertEqual(self.teacher.profile.department, "Proqram mühəndisliyi")
        log = AuditLog.objects.filter(changes__action="rim.membership_unit_placed").get()
        self.assertEqual(log.changes["kind"], "teacher")
        row = body["user"]["placement"]["memberships"][0]
        self.assertEqual(
            (row["unit_name"], row["faculty_name"]), ("Proqram mühəndisliyi", "İnformasiya texnologiyaları")
        )

    def test_detail_card_lists_role_faculty_and_in_scope_units(self):
        card = self.detail(self.teacher).json()["user"]["placement"]
        self.assertEqual(len(card["memberships"]), 1)
        row = card["memberships"][0]
        self.assertTrue(row["editable"], row)
        self.assertEqual(row["kind"], "teacher")
        self.assertEqual(row["unit_id"], "")
        names = {unit["name"]: unit for unit in card["units"]}
        teacher_units = {name for name, unit in names.items() if "teacher" in unit["kinds"].split()}
        self.assertEqual(teacher_units, {"Proqram mühəndisliyi", "Riyaziyyat"})
        # Fakültənin özü yalnız əməkdaş (dekanlıq) vəzifəsi üçün hədəfdir — müəllimə kafedra seçilir.
        self.assertEqual(names["İnformasiya texnologiyaları"]["kinds"], "staff")
        self.assertEqual(names["Riyaziyyat"]["faculty"], "İnformasiya texnologiyaları")
        self.assertEqual(card["faculties"], [{"id": str(self.faculty.pk), "name": "İnformasiya texnologiyaları"}])

    def test_move_between_chairs_needs_matching_expected_unit(self):
        self.assertEqual(self.place(self.chair).status_code, 200)
        stale = self.place(self.other_chair, expected="")
        self.assertEqual(stale.status_code, 409, stale.content)
        self.assertEqual(self.teacher_membership().scope_unit_id, self.chair.pk)
        moved = self.place(self.other_chair, expected=str(self.chair.pk))
        self.assertEqual(moved.status_code, 200, moved.content)
        self.assertEqual(self.teacher_membership().scope_unit_id, self.other_chair.pk)

    def test_same_unit_is_idempotent(self):
        self.place(self.chair)
        again = self.place(self.chair, expected=str(self.chair.pk))
        self.assertEqual(again.status_code, 200)
        self.assertFalse(again.json()["placement_result"]["changed"])
        self.assertEqual(AuditLog.objects.filter(changes__action="rim.membership_unit_placed").count(), 1)

    def test_teacher_imported_onto_faculty_can_be_moved_to_a_chair(self):
        Membership.objects.filter(pk=self.teacher_membership().pk).update(scope_unit=self.faculty)
        row = self.detail(self.teacher).json()["user"]["placement"]["memberships"][0]
        self.assertTrue(row["editable"], row)
        response = self.place(self.chair, expected=str(self.faculty.pk))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.teacher_membership().scope_unit_id, self.chair.pk)

    def test_role_assignment_authority_is_required(self):
        self.revoke("role.assign")
        response = self.place(self.chair)
        self.assertEqual(response.status_code, 403, response.content)
        self.assertIsNone(self.teacher_membership().scope_unit_id)
        row = self.detail(self.teacher).json()["user"]["placement"]["memberships"][0]
        self.assertFalse(row["editable"])
        self.assertIn("role.assign", row["locked_reason"])

    def test_unit_scoped_actor_cannot_place_outside_or_pull_from_other_chair(self):
        self.rim_role.scope_type = RoleScopeType.UNIT
        self.rim_role.save(update_fields=["scope_type"])
        Membership.objects.filter(user=self.operator, role=self.rim_role).update(scope_unit=self.chair)
        self.assertEqual(self.place(self.other_chair).status_code, 404)
        # Başqa kafedraya bağlı müəllimi öz kafedrasına «çəkə» bilməz.
        Membership.objects.filter(pk=self.teacher_membership().pk).update(scope_unit=self.other_chair)
        response = self.place(self.chair, expected=str(self.other_chair.pk))
        self.assertEqual(response.status_code, 404, response.content)
        self.assertEqual(self.teacher_membership().scope_unit_id, self.other_chair.pk)

    def test_foreign_unit_and_foreign_membership_are_rejected(self):
        from apps.organizations.models import Organization

        foreign = Organization.objects.create(name="Other", slug="rim-modal-other", owner=self.owner)
        unit = OrgUnit.objects.create(organization=foreign, name="Kənar", slug="kenar", unit_type=OrgUnitType.CHAIR)
        self.assertEqual(self.place(unit).status_code, 404)
        operator_membership = Membership.objects.get(user=self.operator)
        self.assertEqual(self.place(self.chair, membership=operator_membership).status_code, 404)

    def test_authority_role_is_read_only_here(self):
        head = make_user("chair.head.1", first="Kamran", last="Rzayev", organization=self.org)
        membership = add_member(head, self.org, self.staff_role)  # department_head, təşkilat əhatəli
        response = self.act(
            "place_unit", head, membership_id=str(membership.pk), unit_id=str(self.chair.pk), expected_unit_id=""
        )
        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.json()["error"], "placement_role_locked")
        row = self.detail(head).json()["user"]["placement"]["memberships"][0]
        self.assertFalse(row["editable"])

    def test_missing_unit_is_a_validation_error(self):
        response = self.place(None)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "unit_required")


class RimPositionAndProfileTests(RimModalBase):
    def setUp(self):
        super().setUp()
        self.login_operator()

    def test_detail_offers_standard_positions_and_edit_saves_them(self):
        user = self.detail(self.teacher).json()["user"]
        values = [option["value"] for option in user["position_options"]]
        self.assertIn("Baş müəllim", values)
        self.assertIn("Dosent", values)
        self.assertTrue(user["can_edit_position"])
        response = self.act("edit", self.teacher, staff_position="Baş müəllim")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["staff_position"], "Baş müəllim")
        custom = self.act("edit", self.teacher, staff_position="Elmi katib")
        self.assertEqual(custom.json()["user"]["staff_position"], "Elmi katib")
        self.assertTrue(AuditLog.objects.filter(changes__operation="edit_profile", changes__fields=["staff_position"]))

    def test_fin_is_uppercased_and_duplicate_fin_is_a_clean_conflict(self):
        response = self.act("edit", self.namesake, fin="9zz88yy")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(UserProfile.objects.get(user=self.namesake).fin, "9ZZ88YY")
        clash = self.act("edit", self.namesake, fin="7ab12cd")  # müəllimin FİN-i
        self.assertEqual(clash.status_code, 409, clash.content)
        self.assertEqual(clash.json()["error"], "fin_taken")
        self.assertEqual(UserProfile.objects.get(user=self.namesake).fin, "9ZZ88YY")


class RimStaffArchiveTests(RimModalBase):
    def setUp(self):
        super().setUp()
        Membership.objects.filter(pk=self.teacher_membership().pk).update(scope_unit=self.chair)
        self.lab_role = make_role(self.org, "lab_assistant", 40)
        self.old_lab = Membership.objects.create(
            organization=self.org, user=self.teacher, role=self.lab_role, scope_unit=self.other_chair, is_active=False
        )
        self.login_operator()

    def refresh(self):
        from django.contrib.auth import get_user_model

        return get_user_model().objects.select_related("profile").get(pk=self.teacher.pk)

    def test_archive_and_unarchive_round_trip_keeps_history(self):
        response = self.act("archive_staff", self.teacher, reason="Müqavilə bitib")
        self.assertEqual(response.status_code, 200, response.content)
        user = self.refresh()
        self.assertFalse(user.is_active)
        self.assertEqual(user.profile.block_reason_code, "employment_ended")
        self.assertFalse(self.teacher_membership().is_active)
        body = response.json()["user"]
        self.assertEqual((body["status"], body["archive_kind"]), ("archived", "staff"))
        self.assertTrue(body["actions"]["unarchive_staff"])
        self.assertFalse(body["actions"]["unblock"])
        log = AuditLog.objects.get(changes__action="rim.staff_archived")
        self.assertEqual(log.changes["membership_ids"], [str(self.teacher_membership().pk)])

        # Arxiv RİM-də itmir: «Arxiv» tabında görünür, «Bloklanmış»da yox.
        archived = self.search("Əliyev Elvin Səməd", status="archived").json()
        self.assertEqual([row["username"] for row in archived["results"]], ["myedu.worker.772"])
        self.assertEqual(self.search("Əliyev Elvin Səməd", status="blocked").json()["total"], 0)
        self.assertEqual(self.detail(self.teacher).status_code, 200)

        restored = self.act("unarchive_staff", self.teacher)
        self.assertEqual(restored.status_code, 200, restored.content)
        user = self.refresh()
        self.assertTrue(user.is_active)
        self.assertEqual(user.profile.block_reason_code, "")
        membership = self.teacher_membership()
        self.assertTrue(membership.is_active)
        self.assertEqual(membership.scope_unit_id, self.chair.pk)
        self.old_lab.refresh_from_db()
        self.assertFalse(self.old_lab.is_active)  # arxivdən ƏVVƏL deaktiv olan rol toxunulmur
        self.assertTrue(AuditLog.objects.filter(changes__action="rim.staff_unarchived").exists())
        self.assertEqual(restored.json()["user"]["status"], "active")

    def test_archived_teacher_leaves_workload_pool(self):
        from apps.workload.services.people import chair_teacher_memberships

        self.assertTrue(chair_teacher_memberships(self.org, self.chair, include_unscoped=False).exists())
        self.act("archive_staff", self.teacher)
        self.assertFalse(chair_teacher_memberships(self.org, self.chair, include_unscoped=False).exists())

    def test_plain_unblock_cannot_bypass_role_restore(self):
        self.act("archive_staff", self.teacher)
        self.grant("user.block")
        response = self.act("unblock", self.teacher)
        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.json()["error"], "use_unarchive")
        self.assertFalse(self.refresh().is_active)

    def test_block_permission_is_required(self):
        self.revoke("user.block")
        self.assertEqual(self.act("archive_staff", self.teacher).status_code, 403)
        self.assertTrue(self.refresh().is_active)
        card = self.detail(self.teacher).json()["user"]["staff_archive"]
        self.assertFalse(card["can_archive"])
        self.assertTrue(card["disabled_reason"])

    def test_student_cannot_be_staff_archived(self):
        student = make_user("std.one", first="Aysel", last="Quliyeva", organization=self.org)
        add_member(student, self.org, self.student_role)
        self.grant("people.view_students")
        response = self.act("archive_staff", student)
        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.json()["error"], "target_is_student")
        self.assertIsNone(self.detail(student).json()["user"]["staff_archive"])

    def test_archived_higher_rank_stays_out_of_reach(self):
        root = RimActor(user=self.superuser, organization=self.org, level=SUPERADMIN_LEVEL, is_superadmin=True)
        staff_archive.archive(root, self.higher, reason="Ayrılıb")
        self.assertFalse(Membership.objects.filter(user=self.higher, is_active=True).exists())
        # Arxivdə də rütbə BÜTÜN üzvlüklərlə sayılır: 88-lik operator 90-lıq prorektoru nə görür, nə açır.
        self.assertEqual(self.search("Həsənov", status="archived").json()["total"], 0)
        self.assertEqual(self.detail(self.higher).status_code, 404)
        self.assertEqual(self.act("unarchive_staff", self.higher).status_code, 403)
        self.assertFalse(Membership.objects.filter(user=self.higher, is_active=True).exists())

    def test_catalog_style_employment_block_is_archive_and_unblocks(self):
        """Kataloqdan «İşdən ayrılıb» bloku (rollar aktiv qalıb) — arxiv sayılır, sadə bərpa da işləyir."""
        from apps.accounts.services.account_deletion import block_account

        block_account(self.teacher, actor=self.operator, reason="x", reason_code="employment_ended", contact_code="hr")
        self.assertEqual(self.detail(self.teacher).json()["user"]["status"], "archived")
        response = self.act("unarchive_staff", self.teacher)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(self.refresh().is_active)
        self.assertTrue(self.teacher_membership().is_active)


class RimGraduationTests(RimModalBase):
    def setUp(self):
        super().setUp()
        self.grant(*GRADUATION_PERMS)
        self.group = OrgUnit.objects.create(
            organization=self.org, name="231 PM", slug="g-231", unit_type=OrgUnitType.GROUP, parent=self.faculty
        )
        self.program = Program.objects.create(organization=self.org, code="PM", name="Proqram mühəndisliyi")
        self.curriculum = Curriculum.objects.create(organization=self.org, program=self.program, admission_year=2022)
        self.student = make_user("std.grad", first="Nərmin", last="Həsənli", organization=self.org)
        add_member(self.student, self.org, self.student_role)
        self.record = StudentAcademicRecord.objects.create(
            organization=self.org,
            student=self.student,
            program=self.program,
            curriculum=self.curriculum,
            group=self.group,
            admission_year=2022,
            status="enrolled",
        )
        self.login_operator()

    def graduate(self, **payload):
        payload.setdefault("order_number", "M-115")
        payload.setdefault("order_date", datetime.date.today().isoformat())
        return self.act("graduate", self.student, **payload)

    def test_graduation_moves_record_archives_account_and_writes_ledger(self):
        card = self.detail(self.student).json()["user"]["graduation"]
        self.assertTrue(card["can_graduate"], card)
        self.assertEqual(card["enrolled"][0]["group"], "231 PM")
        response = self.graduate(reason="Təhsili başa vurub")
        self.assertEqual(response.status_code, 200, response.content)
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, "graduated")
        self.assertEqual(UserProfile.objects.get(user=self.student).access_state, "archived")
        movement = StudentMovement.objects.get(record=self.record)
        self.assertEqual((movement.kind, movement.order_number), ("graduation", "M-115"))
        user = response.json()["user"]
        self.assertEqual((user["status"], user["archive_kind"]), ("archived", "student"))
        self.assertFalse(user["actions"]["graduate"])
        self.assertTrue(AuditLog.objects.filter(changes__action="people.student_movement").exists())

    def test_order_number_is_required(self):
        response = self.graduate(order_number="")
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["error"], "order_number_required")
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, "enrolled")

    def test_registry_permissions_are_required(self):
        self.revoke("student.movement")
        card = self.detail(self.student).json()["user"]["graduation"]
        self.assertFalse(card["can_graduate"])
        self.assertIn("student.movement", card["disabled_reason"])
        self.assertEqual(self.graduate().status_code, 403)
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, "enrolled")

    def test_foreign_record_id_is_rejected(self):
        other = make_user("std.other", first="Orxan", last="Səfərov", organization=self.org)
        add_member(other, self.org, self.student_role)
        other_record = StudentAcademicRecord.objects.create(
            organization=self.org,
            student=other,
            program=self.program,
            curriculum=self.curriculum,
            group=self.group,
            admission_year=2022,
            status="enrolled",
        )
        response = self.graduate(record_id=str(other_record.pk))
        self.assertEqual(response.status_code, 404, response.content)
        other_record.refresh_from_db()
        self.assertEqual(other_record.status, "enrolled")

    def test_teacher_has_no_graduation(self):
        self.assertIsNone(self.detail(self.teacher).json()["user"]["graduation"])
        response = self.act("graduate", self.teacher, order_number="M-1", order_date="2026-11-04")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "no_enrolled_record")
