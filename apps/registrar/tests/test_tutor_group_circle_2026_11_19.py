"""Tyutorun «qrup dövrəsi» (sahib 2026-11-19): tələbə / qrup işlərinin hamısı tyutorun özündə, YALNIZ öz fakültəsində.

Sahib: «tyutora özəllik olaraq rol ver ki qrupa tələbə əlavə etmək, qruplardan tələbə köçürmək, qrup yaratmaq …
tələbə datasını görməkdən, müəllim qrup-qrup köçürməsi, xarici dildə xarici dil qrupu açmaq, əlavə tələbə əlavə
etmək, lab qrupları yaratmaq, alt qrupları etmək». Açar xəritəsi: ``apps/organizations/permissions_tutor_circle.py``.

Qurğu (``SubgroupFixture``): ``Fakültə → Kafedra → {G1, G2}`` (tyutorun fakültəsi) + ``Uzaq fakültə → GX`` və orada
DİL kafedrası (real universitetdə bütün dil kafedraları bir məktəbin altındadır). Tyutor — REAL ``tutor`` rol
şablonu, ``scope_unit`` = fakültə. Hər əməl üçün: öz fakültəsində işləyir, kənar fakültədə 403/404 və heç nə yazılmır.
"""

from __future__ import annotations

import importlib
import json

from django.core.exceptions import PermissionDenied
from django.test import TestCase
from django.urls import reverse

from apps.organizations.default_roles_university import UNIVERSITY_ROLES
from apps.organizations.models import OrgUnit, Role
from apps.organizations.permissions import get_all_permissions
from apps.organizations.permissions_tutor_circle import TUTOR_CIRCLE_GRANTS
from apps.registrar import guest_roster, handover, handover_actions, lab_groups_manage, lab_groups_section
from apps.registrar import language_cohort_placement as placement
from apps.registrar import language_cohorts
from apps.registrar.models import (
    CourseOffering,
    Enrollment,
    LabGroup,
    LanguageLevelCohort,
    StudentAcademicRecord,
    Subject,
)
from apps.registrar.tests.subgroup_base import SubgroupFixture
from core.constants import OrgUnitType
from core.rls import bypass_rls

MIGRATION = importlib.import_module("apps.organizations.migrations.0086_tutor_group_circle")
NEW_KEYS = ("journal.lab_groups", "journal.level_cohorts")


class TutorCircleBase(SubgroupFixture, TestCase):
    PREFIX = "tgc"

    @classmethod
    def setUpTestData(cls):
        cls.build_world()
        with bypass_rls():
            tutor_role = cls.org.roles.get(name="tutor")
            cls.tutor = cls._member("tgc_tutor", tutor_role, cls.faculty)
            cls.far_tutor = cls._member("tgc_far_tutor", tutor_role, cls.far_faculty)
            cls.rim = cls._member("tgc_rim", cls.org.roles.get(name="ikt_rehber"))
            cls.new_teacher = cls._member("tgc_new_teacher", cls.org.roles.get(name="teacher"))
            cls.lang_chair = OrgUnit.objects.create(
                organization=cls.org,
                name="Xarici dillər kafedrası",
                slug="tgc-lang",
                unit_type=OrgUnitType.CHAIR,
                parent=cls.far_faculty,
            )
            # Dil kafedrası səviyyə fənnini RƏSMİ aparır (fənnin kafedrası) və cari semestrdə adi səviyyə jurnalı var.
            cls.level_subject = Subject.objects.create(
                organization=cls.org, code="TGCLVL", name="Xarici dil-1 (Intermediate)", chair_unit=cls.lang_chair
            )
            CourseOffering.objects.create(
                organization=cls.org, subject=cls.level_subject, period=cls.period, group=cls.far_group
            )
            # Kənar fakültənin ADİ kafedrası — orada kohort açılsa da tyutora dil kafedrası kimi təklif olunmur.
            cls.far_chair = OrgUnit.objects.create(
                organization=cls.org,
                name="Uzaq kafedra",
                slug="tgc-far-ch",
                unit_type=OrgUnitType.CHAIR,
                parent=cls.far_faculty,
            )
            for user in (cls.tutor, cls.far_tutor, cls.rim, cls.teacher, cls.new_teacher, cls.host, cls.student):
                user.profile.organization = cls.org
                user.profile.save(update_fields=["organization"])
            cls.far_student.profile.organization = cls.org
            cls.far_student.profile.save(update_fields=["organization"])
            cls.far_history = cls.far_student.enrollments.get(offering__subject=cls.history).offering

    def record_of(self, student):
        with bypass_rls():
            return StudentAcademicRecord.objects.get(organization=self.org, student=student)

    def group_action(self, user, **data):
        with bypass_rls():
            return self.client_for(user).post(
                reverse("organizations:group_action", kwargs={"slug": self.org.slug}), data
            )


class TutorRoleKeysTest(TutorCircleBase):
    """Rol şablonu + miqrasiya: açarlar verilib, qərar açarları (xaric, yük bölgüsü) VERİLMƏYİB."""

    def test_template_and_live_role_carry_the_circle_keys(self):
        templates = {role["name"]: role for role in UNIVERSITY_ROLES}
        catalog = set(get_all_permissions())
        for name in ("tutor", "program_coordinator"):
            permissions = set(templates[name]["permissions"])
            for key in TUTOR_CIRCLE_GRANTS[name]:
                self.assertIn(key, permissions, (name, key))
                self.assertIn(key, catalog, key)
            self.assertNotIn("student.movement", permissions)
            self.assertNotIn("workload.distribute", permissions)
        self.assertEqual(set(templates["tutor"]["permissions"]), set(templates["program_coordinator"]["permissions"]))
        with bypass_rls():
            live = set(self.org.roles.get(name="tutor").permissions)
        self.assertTrue(set(TUTOR_CIRCLE_GRANTS["tutor"]) <= live)

    def test_migration_is_idempotent_and_reverses_only_new_keys(self):
        from django.apps import apps as django_apps

        with bypass_rls():
            role = Role.objects.get(organization=self.org, name="tutor")
            role.permissions = [key for key in role.permissions if key not in TUTOR_CIRCLE_GRANTS["tutor"]]
            role.save(update_fields=["permissions"])
            MIGRATION.forward(django_apps, None)
            MIGRATION.forward(django_apps, None)
            role.refresh_from_db()
            for key in TUTOR_CIRCLE_GRANTS["tutor"]:
                self.assertEqual(role.permissions.count(key), 1, key)
            MIGRATION.backward(django_apps, None)
            role.refresh_from_db()
            for key in NEW_KEYS:
                self.assertNotIn(key, role.permissions)
            self.assertIn("journal.reassign", role.permissions)


class StudentDataTest(TutorCircleBase):
    """1. Tələbə datası — reyestr kartı öz fakültəsində açılır, kənar fakültədə 404."""

    def test_registry_card_own_faculty_only(self):
        client = self.client_for(self.tutor)
        with bypass_rls():
            own = client.get(reverse("accounts:student_registry_card", args=[self.record_of(self.student).pk]))
            far = client.get(reverse("accounts:student_registry_card", args=[self.record_of(self.far_student).pk]))
        self.assertEqual(own.status_code, 200)
        self.assertTrue(own.json()["ok"])
        self.assertEqual(far.status_code, 404)

    def test_contacts_and_records_scope_is_the_faculty(self):
        from apps.organizations.public import get_permission_scope

        with bypass_rls():
            for key in ("student.records_view", "people.view_contacts", "people.view_demographics"):
                scope = get_permission_scope(self.tutor, self.org, key)
                self.assertTrue(scope.has_structure_access, key)
                self.assertFalse(scope.is_org_wide, key)
                self.assertTrue(OrgUnit.objects.filter(pk=self.group2.pk).filter(scope.unit_subtree_q()).exists())
                self.assertFalse(OrgUnit.objects.filter(pk=self.far_group.pk).filter(scope.unit_subtree_q()).exists())


class GroupRegistryTest(TutorCircleBase):
    """2–3, 7. Qrup yaratmaq, qruplar arası köçürmə (rəsmi xidmət), ana qrupu alt qruplara bölmək."""

    def test_create_group_in_own_faculty_only(self):
        ok = self.group_action(self.tutor, action="save_group", name="TGC-NEW", specialty=str(self.chair.pk))
        self.assertEqual(ok.status_code, 200, ok.content)
        far = self.group_action(self.tutor, action="save_group", name="TGC-FAR", specialty=str(self.far_faculty.pk))
        self.assertEqual(far.status_code, 404)
        with bypass_rls():
            self.assertEqual(OrgUnit.objects.get(organization=self.org, name="TGC-NEW").parent_id, self.chair.pk)
            self.assertFalse(OrgUnit.objects.filter(organization=self.org, name="TGC-FAR").exists())

    def test_move_student_between_own_groups_via_official_transfer(self):
        response = self.group_action(
            self.tutor,
            action="move_student",
            id=str(self.group1.pk),
            record_id=str(self.record_of(self.student).pk),
            reason="Tyutor qərarı",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.record_of(self.student).group_id, self.group1.pk)

    def test_move_to_or_from_other_faculty_is_refused(self):
        into_far = self.group_action(
            self.tutor,
            action="move_student",
            id=str(self.far_group.pk),
            record_id=str(self.record_of(self.student).pk),
            reason="Tyutor qərarı",
        )
        from_far = self.group_action(
            self.tutor,
            action="move_student",
            id=str(self.group1.pk),
            record_id=str(self.record_of(self.far_student).pk),
            reason="Tyutor qərarı",
        )
        self.assertEqual(into_far.status_code, 404)
        self.assertEqual(from_far.status_code, 404)
        self.assertEqual(self.record_of(self.student).group_id, self.group2.pk)
        self.assertEqual(self.record_of(self.far_student).group_id, self.far_group.pk)

    def test_split_own_group_into_subgroups(self):
        with bypass_rls():
            extra = self._student("tgc_extra", self.group1)
        subgroups = [
            {"name": "G1-1", "record_ids": [str(self.record_of(self.host).pk)]},
            {"name": "G1-2", "record_ids": [str(self.record_of(extra).pk)]},
        ]
        response = self.group_action(
            self.tutor,
            action="split_group",
            id=str(self.group1.pk),
            reason="Lab bölgüsü",
            subgroups=json.dumps(subgroups),
        )
        self.assertEqual(response.status_code, 200, response.content)
        with bypass_rls():
            self.assertEqual(
                OrgUnit.objects.filter(organization=self.org, settings__parent_group=str(self.group1.pk)).count(), 2
            )
        far = self.group_action(
            self.far_tutor, action="split_group", id=str(self.group1.pk), reason="Lab bölgüsü", subgroups="[]"
        )
        self.assertEqual(far.status_code, 404)


class TeacherHandoverTest(TutorCircleBase):
    """4. Müəllimin qrupdan-qrupa təhvili (``journal.reassign``) — açılışın qrupu öz fakültəsindədirsə."""

    def test_reassign_own_faculty_journal(self):
        with bypass_rls():
            self.assertTrue(handover.can_reassign(self.tutor, self.org))
            offering = self.history_g1
            self.assertNotIn("outside_scope", handover.blockers(offering, actor=self.tutor, organization=self.org))
            handover_actions.reassign(
                actor=self.tutor,
                organization=self.org,
                offering_id=offering.pk,
                new_instructor_id=self.new_teacher.pk,
                reason="Müəllim başqa qrupa keçdi",
            )
            offering.refresh_from_db()
        self.assertEqual(offering.instructor_id, self.new_teacher.pk)

    def test_other_faculty_journal_is_refused(self):
        with bypass_rls():
            self.assertIn("outside_scope", handover.blockers(self.far_history, actor=self.tutor, organization=self.org))
            with self.assertRaises(handover_actions.HandoverError):
                handover_actions.reassign(
                    actor=self.tutor,
                    organization=self.org,
                    offering_id=self.far_history.pk,
                    new_instructor_id=self.new_teacher.pk,
                    reason="Müəllim başqa qrupa keçdi",
                )
            self.far_history.refresh_from_db()
        self.assertNotEqual(self.far_history.instructor_id, self.new_teacher.pk)


class LevelCohortTest(TutorCircleBase):
    """5. Xarici dil səviyyə qrupu — dil kafedrasında açır, yalnız öz tələbələrini yerləşdirir / çıxarır."""

    def create(self, actor, department, name):
        with bypass_rls():
            return language_cohorts.create_cohort(
                organization=self.org,
                actor=actor,
                department=department,
                period=self.period,
                subject=self.level_subject,
                instructor=self.teacher,
                name=name,
                lecture_hours=0,
                seminar_hours=30,
                lab_hours=0,
                confirm_separate=True,
            )

    def place(self, cohort, student, actor):
        with bypass_rls():
            return placement.place_student(
                cohort=cohort, record_id=self.record_of(student).pk, actor=actor, reason="Səviyyə testi nəticəsi"
            )

    def test_tutor_opens_group_at_language_chair_and_places_own_student(self):
        chair_cohort = self.create(self.rim, self.lang_chair, "Kafedranın B1 qrupu")
        with bypass_rls():
            choices = set(language_cohorts.department_choices(self.tutor, self.org).values_list("pk", flat=True))
        self.assertIn(self.lang_chair.pk, choices)
        self.assertIn(self.chair.pk, choices)
        cohort = self.create(self.tutor, self.lang_chair, "Tyutorun B1 qrupu")
        with bypass_rls():
            self.assertTrue(language_cohorts.can_manage_as_staff(self.tutor, cohort))
            # Başqasının (kafedranın) qrupu — kafedra tyutorun əhatəsində deyil.
            self.assertFalse(language_cohorts.can_manage_as_staff(self.tutor, chair_cohort))
            self.assertEqual([row.pk for row in language_cohorts.authorized_cohorts(self.tutor, self.org)], [cohort.pk])
        enrollment = self.place(cohort, self.host, self.tutor)
        self.assertEqual(enrollment.offering_id, cohort.offering_id)
        with self.assertRaises(PermissionDenied):
            self.place(cohort, self.far_student, self.tutor)

    def test_tutor_cannot_remove_another_faculty_student_from_own_cohort(self):
        self.create(self.rim, self.lang_chair, "Kafedranın B1 qrupu")
        cohort = self.create(self.tutor, self.lang_chair, "Tyutorun B1 qrupu")
        own = self.place(cohort, self.host, self.tutor)
        far = self.place(cohort, self.far_student, self.rim)
        with bypass_rls(), self.assertRaises(PermissionDenied):
            placement.remove_student(cohort=cohort, enrollment_id=far.pk, actor=self.tutor, reason="Səhv yerləşdirmə")
        with bypass_rls():
            placement.remove_student(cohort=cohort, enrollment_id=own.pk, actor=self.tutor, reason="Səhv yerləşdirmə")
            self.assertEqual(Enrollment.objects.get(pk=own.pk).status, Enrollment.Status.DROPPED)
            self.assertEqual(Enrollment.objects.get(pk=far.pk).status, Enrollment.Status.ENROLLED)

    def test_other_faculty_ordinary_chair_is_not_offered_even_with_a_cohort(self):
        self.create(self.rim, self.far_chair, "Uzaq kafedranın qrupu")
        with bypass_rls():
            choices = language_cohorts.department_choices(self.tutor, self.org)
            self.assertFalse(choices.filter(pk=self.far_chair.pk).exists())
            self.assertTrue(choices.filter(pk=self.lang_chair.pk).exists())
            with self.assertRaises(PermissionDenied):
                language_cohorts.create_cohort(
                    organization=self.org,
                    actor=self.tutor,
                    department=self.far_chair,
                    period=self.period,
                    subject=self.level_subject,
                    instructor=self.teacher,
                    name="Kənar kafedrada",
                    lecture_hours=0,
                    seminar_hours=30,
                    lab_hours=0,
                    confirm_separate=True,
                )

    def test_creator_sees_only_own_faculty_students_on_the_detail_page(self):
        cohort = self.create(self.tutor, self.lang_chair, "Tyutorun B1 qrupu")
        self.place(cohort, self.host, self.tutor)
        self.place(cohort, self.far_student, self.rim)
        with bypass_rls():
            response = self.client_for(self.tutor).get(reverse("registrar:language_cohort_detail", args=[cohort.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["enrollment"].student_id for row in response.context["rows"]], [self.host.pk])
        self.assertEqual({event.student_id for event in response.context["events"]}, {self.host.pk})
        with bypass_rls():
            full = self.client_for(self.rim).get(reverse("registrar:language_cohort_detail", args=[cohort.pk]))
        self.assertEqual(len(full.context["rows"]), 2)

    def test_other_tutor_has_no_access(self):
        cohort = self.create(self.tutor, self.chair, "Öz kafedrasında")
        with bypass_rls():
            self.assertFalse(language_cohorts.can_manage_as_staff(self.far_tutor, cohort))
        response = self.client_for(self.far_tutor).post(
            reverse("registrar:language_cohort_detail", args=[cohort.pk]),
            {"action": "place", "record": str(self.record_of(self.far_student).pk), "reason": "Səviyyə testi"},
        )
        self.assertEqual(response.status_code, 404)
        with bypass_rls():
            self.assertFalse(LanguageLevelCohort.objects.get(pk=cohort.pk).offering.enrollments.exists())


class JournalGuestTest(TutorCircleBase):
    """6. Jurnala alt qrupdan əlavə tələbə (sənəd qaydası view-da qalır) — öz fakültəsinin jurnalı."""

    def test_add_guest_to_own_faculty_journal(self):
        with bypass_rls():
            self.assertTrue(guest_roster.can_manage_offering_roster(self.tutor, self.physics_g1))
            self.assertFalse(guest_roster.can_manage_offering_roster(self.tutor, self.far_history))
            enrollment = guest_roster.add_guest_student(
                offering=self.physics_g1, student=self.student, by_user=self.tutor, reason="Alt qrupdan əlavə"
            )
        self.assertEqual(enrollment.source_group_id, self.group2.pk)

    def test_other_faculty_journal_add_is_refused_over_http(self):
        response = self.client_for(self.tutor).post(
            reverse("registrar:journal_guest_add", args=[self.far_history.pk]),
            {"student": str(self.student.pk), "reason": "Alt qrupdan əlavə"},
        )
        self.assertIn(response.status_code, (403, 404))
        with bypass_rls():
            self.assertFalse(Enrollment.objects.filter(offering=self.far_history, student=self.student).exists())


class LabGroupsTest(TutorCircleBase):
    """7. Lab qrupları — QRUPU öz fakültəsində olan jurnal; kənar fakültənin jurnalında 403."""

    def test_tutor_manages_lab_groups_of_own_group_journal(self):
        with bypass_rls():
            self.assertTrue(lab_groups_manage.can_manage(self.tutor, self.history_g1))
            self.assertFalse(lab_groups_manage.can_manage(self.tutor, self.far_history))
            scope = lab_groups_section.resolve_scope(self.tutor, self.org)
            self.assertIn(str(self.group1.pk), scope.group_units)
            self.assertNotIn(str(self.far_group.pk), scope.group_units)
        url = reverse("registrar:journal_lab_groups", args=[self.history_g1.pk])
        response = self.client_for(self.tutor).post(url, {"action": "create", "name": "Lab A"})
        self.assertLess(response.status_code, 400, response.content)
        with bypass_rls():
            self.assertTrue(LabGroup.objects.filter(offering=self.history_g1).exists())

    def test_other_faculty_journal_is_403(self):
        url = reverse("registrar:journal_lab_groups", args=[self.far_history.pk])
        response = self.client_for(self.tutor).post(url, {"action": "create", "name": "Lab X"})
        self.assertEqual(response.status_code, 403)
        with bypass_rls():
            self.assertFalse(LabGroup.objects.filter(offering=self.far_history).exists())
