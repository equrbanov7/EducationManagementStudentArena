"""Mərhələ 2 bölmələri (ekran 05/06/07) — icazə, state maşını, saat balansı,
açılış idempotentliyi və audit.

Nəyi qoruyur
------------
1. **Rol qapısı.** `teaching_office_head` üç bölməni GÖRÜR; müəllim və tələbə
   fraqment API-sindən **403** alır (`plan.*` / `unit.view` / `semester.*`
   açarları onlarda QƏSDƏN yoxdur).
2. **Səlahiyyət ayrılığı.** Zəncirin hər halqası AYRI açardır: kafedra müdiri
   şuranın mərhələsini təsdiqləyə BİLMİR (403), dekan kafedra mərhələsini keçə
   bilmir. Qeyri-qanuni keçid **409**.
3. **Təsdiqlənmiş plan IMMUTABLE-dır** (handoff §8/1): sətir yazısı da, status
   keçidi də **409 plan_immutable**; dəyişiklik yalnız yeni versiya.
4. **Saat balansı** təsdiqə göndərməni BLOKLAYIR (§8/11) — düzəldiləndən sonra
   göndəriş keçir.
5. **Açılış törətməsi İDEMPOTENTDİR** və heç nə silmir; «Plan yoxdur» ixtisas
   bloklayıcıdır (§6.1).
6. **Kilid** şərtsiz keçmir, kilidin AÇILMASI ayrıca açar + ≥20 simvol səbəb
   tələb edir; «cari dövr» açarı audit-ə yazılır.
7. **İcazə kataloqu** — yeni açarlar kataloqda və etiket cədvəlindədir.
"""

from datetime import date

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.organizations.models import AcademicPeriod, Membership, Organization, OrgUnit, Role
from apps.registrar.models import CourseOffering, Curriculum, CurriculumSubject, Program, Subject
from apps.registrar.models.curriculum_meta import PlanStatus, row_hour_errors
from core.constants import OrganizationType, OrgUnitType, RoleScopeType

User = get_user_model()

PASSWORD = "StrongPass123!"

STAGE2_SECTIONS = ("curriculum-editor", "groups-registry", "semester-opening")

#: Rol → (səviyyə, icazələr) — `default_roles_stage2.STAGE2_ROLE_GRANTS` ilə eyni.
ROLE_SPECS = {
    "teaching_office_head": (
        85,
        [
            "org.view",
            "unit.view",
            "unit.tree_manage",
            "unit.group_manage",
            "catalog.view",
            "catalog.manage",
            "plan.view",
            "plan.edit",
            "plan.submit",
            "plan.approve_office",
            "semester.view",
            "semester.open",
            "semester.lock",
            "semester.unlock",
        ],
    ),
    "chair_head": (70, ["unit.view", "catalog.view", "plan.view", "plan.edit", "plan.submit", "plan.approve_chair"]),
    "dean": (75, ["unit.view", "catalog.view", "plan.view", "plan.approve_council", "semester.view"]),
    # ⚠️ `grade.input` MƏCBURİDİR: `registrar_courseoffering.instructor_id`
    # üzərindəki PG triggeri (`registrar_guard_active_member`) müəllim
    # təyinatını məhz bu açara görə yoxlayır — açar olmasa INSERT/UPDATE çökür.
    "teacher": (50, ["course.view", "syllabus.edit", "grade.input"]),
    "student": (10, ["course.view"]),
}


class Stage2BaseTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user("ds2_owner", "ds2_owner@qku.edu.az", PASSWORD)
        cls.org = Organization.objects.create(
            name="Mərhələ2 Univ",
            slug="ds2-univ",
            org_type=OrganizationType.UNIVERSITY,
            owner=cls.owner,
            status="active",
            is_active=True,
        )
        cls.faculty = OrgUnit.objects.create(
            organization=cls.org, unit_type=OrgUnitType.FACULTY, name="Mühəndislik", slug="ds2-fak"
        )
        cls.chair = OrgUnit.objects.create(
            organization=cls.org,
            parent=cls.faculty,
            unit_type=OrgUnitType.CHAIR,
            name="İnformatika kafedrası",
            slug="ds2-kaf",
        )
        cls.specialty = OrgUnit.objects.create(
            organization=cls.org,
            parent=cls.chair,
            unit_type=OrgUnitType.SPECIALTY,
            name="Kompüter elmləri",
            slug="ds2-ixt",
        )
        cls.group = OrgUnit.objects.create(
            organization=cls.org,
            parent=cls.specialty,
            unit_type=OrgUnitType.GROUP,
            name="QA-DS2 KE-24A",
            slug="ds2-qrup",
            code="KE-24A",
            settings={"language_sector": "AZ", "course_year": 1, "admission_year": 2024},
        )

        cls.users, cls.roles = {}, {}
        for name, (level, permissions) in ROLE_SPECS.items():
            scope_type = RoleScopeType.UNIT if name in ("chair_head", "dean") else RoleScopeType.ORGANIZATION
            role, _ = Role.objects.update_or_create(
                organization=cls.org,
                name=name,
                defaults={
                    "display_name": name.replace("_", " ").title(),
                    "level": level,
                    "scope_type": scope_type,
                    "permissions": permissions,
                    "is_system": True,
                    "is_active": True,
                },
            )
            cls.roles[name] = role
            user = User.objects.create_user(f"ds2_{name}", f"ds2_{name}@qku.edu.az", PASSWORD)
            scope_unit = None
            if name == "chair_head":
                scope_unit = cls.chair
            elif name == "dean":
                scope_unit = cls.faculty
            Membership.objects.create(
                user=user,
                organization=cls.org,
                role=role,
                scope_unit=scope_unit,
                is_primary=True,
                is_active=True,
            )
            cls.users[name] = user

        cls.program = Program.objects.create(
            organization=cls.org,
            code="QA-DS2-PRG",
            official_code="6050100",
            name="QA-DS2 Kompüter elmləri",
            specialty_unit=cls.specialty,
        )
        cls.orphan_program = Program.objects.create(
            organization=cls.org,
            code="QA-DS2-PRG2",
            official_code="6050200",
            name="QA-DS2 Plansız ixtisas",
            specialty_unit=None,
        )
        cls.subject = Subject.objects.create(
            organization=cls.org, code="QA-DS2-SBJ", name="QA-DS2 Alqoritmlər", ects=5, chair_unit=cls.chair
        )
        cls.subject_b = Subject.objects.create(
            organization=cls.org, code="QA-DS2-SBJ2", name="QA-DS2 Diskret riyaziyyat", ects=5, chair_unit=cls.chair
        )
        cls.period = AcademicPeriod.objects.create(
            organization=cls.org,
            name="Payız semestri",
            period_type="semester",
            academic_year="2026/2027",
            start_date=date(2026, 9, 15),
            end_date=date(2027, 1, 25),
        )

    # ── köməkçilər ──────────────────────────────────────────────────────────

    def _client(self, role_name):
        client = Client()
        client.force_login(self.users[role_name])
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _sections(self, role_name):
        response = self._client(role_name).get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200, role_name)
        return set(response.context["allowed_sections"])

    def _fragment(self, role_name, section, **params):
        url = reverse("accounts:profile_section_fragment", kwargs={"section": section})
        return self._client(role_name).get(url, params)

    def _plan(self, *, status=PlanStatus.DRAFT, year=2026, version=1):
        return Curriculum.objects.create(
            organization=self.org,
            program=self.program,
            admission_year=year,
            name="QA-DS2 plan",
            status=status,
            version=version,
        )

    def _balanced_row(self, plan, subject=None, *, semester=1, credits=30):
        """Balansı POZULMAYAN sətir: kredit × 30 = ümumi; bölgü cəmi = ümumi."""
        total = credits * 30
        return CurriculumSubject.objects.create(
            organization=self.org,
            curriculum=plan,
            subject=subject or self.subject,
            semester_number=semester,
            credits=credits,
            total_hours=total,
            lecture_hours=30,
            seminar_hours=15,
            lab_hours=15,
            selfwork_hours=total - 60,
        )


class Stage2AccessTest(Stage2BaseTest):
    """1 — bölmə görünürlüyü və fraqment qapısı."""

    def test_teaching_office_head_sees_all_three_sections(self):
        sections = self._sections("teaching_office_head")
        for key in STAGE2_SECTIONS:
            self.assertIn(key, sections, key)

    def test_fragment_returns_200_for_teaching_office_head(self):
        for section in STAGE2_SECTIONS:
            with self.subTest(section=section):
                self.assertEqual(self._fragment("teaching_office_head", section).status_code, 200)

    def test_fragment_returns_403_for_teacher_and_student(self):
        for role in ("teacher", "student"):
            for section in STAGE2_SECTIONS:
                with self.subTest(role=role, section=section):
                    self.assertEqual(self._fragment(role, section).status_code, 403)

    def test_teacher_and_student_do_not_see_sections_in_menu(self):
        for role in ("teacher", "student"):
            leaked = self._sections(role) & set(STAGE2_SECTIONS)
            self.assertEqual(leaked, set(), f"{role}: {sorted(leaked)}")

    def test_chair_head_sees_plan_editor_but_not_semester_opening(self):
        """Kafedra müdirində `plan.view` var, `semester.view` YOXDUR."""
        sections = self._sections("chair_head")
        self.assertIn("curriculum-editor", sections)
        self.assertNotIn("semester-opening", sections)

    def test_chair_head_sees_only_own_subtree_groups(self):
        other_faculty = OrgUnit.objects.create(
            organization=self.org, unit_type=OrgUnitType.FACULTY, name="Başqa fakültə", slug="ds2-fak2"
        )
        other_specialty = OrgUnit.objects.create(
            organization=self.org, parent=other_faculty, unit_type=OrgUnitType.SPECIALTY, name="Digər", slug="ds2-ixt2"
        )
        OrgUnit.objects.create(
            organization=self.org,
            parent=other_specialty,
            unit_type=OrgUnitType.GROUP,
            name="QA-DS2 XX-24A",
            slug="ds2-qrup2",
        )
        response = self._fragment("chair_head", "groups-registry")
        self.assertEqual(response.status_code, 200)
        names = {row["name"] for row in response.context["groups_registry_section"]["rows"]}
        self.assertEqual(names, {self.group.name})


class PlanStateMachineTest(Stage2BaseTest):
    """2/3/4 — zəncir, immutability və saat balansı."""

    def _post(self, role, payload):
        return self._client(role).post(reverse("registrar:curriculum_action"), payload)

    def test_full_chain_draft_to_approved(self):
        plan = self._plan()
        self._balanced_row(plan)

        submitted = self._post("chair_head", {"action": "submit", "plan": str(plan.id)})
        self.assertEqual(submitted.status_code, 200, submitted.content)
        plan.refresh_from_db()
        self.assertEqual(plan.status, PlanStatus.CHAIR_REVIEW)
        self.assertIsNotNone(plan.submitted_at)

        self.assertEqual(self._post("chair_head", {"action": "approve_chair", "plan": str(plan.id)}).status_code, 200)
        plan.refresh_from_db()
        self.assertEqual(plan.status, PlanStatus.FACULTY_COUNCIL)

        self.assertEqual(self._post("dean", {"action": "approve_council", "plan": str(plan.id)}).status_code, 200)
        plan.refresh_from_db()
        self.assertEqual(plan.status, PlanStatus.TEACHING_OFFICE)

        final = self._post(
            "teaching_office_head",
            {"action": "approve_office", "plan": str(plan.id), "protocol_number": "№ 04 — 12.05.2026"},
        )
        self.assertEqual(final.status_code, 200)
        plan.refresh_from_db()
        self.assertEqual(plan.status, PlanStatus.APPROVED)
        self.assertEqual(plan.protocol_number, "№ 04 — 12.05.2026")
        self.assertIsNotNone(plan.approved_at)

    def test_chair_head_cannot_approve_faculty_council_stage(self):
        plan = self._plan(status=PlanStatus.FACULTY_COUNCIL)
        self._balanced_row(plan)
        response = self._post("chair_head", {"action": "approve_council", "plan": str(plan.id)})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["error"], "forbidden")

    def test_illegal_transition_returns_409(self):
        plan = self._plan()
        self._balanced_row(plan)
        response = self._post("teaching_office_head", {"action": "approve_office", "plan": str(plan.id)})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "illegal_transition")

    def test_return_requires_reason_and_writes_audit(self):
        plan = self._plan(status=PlanStatus.CHAIR_REVIEW)
        self._balanced_row(plan)
        short = self._post("chair_head", {"action": "return", "plan": str(plan.id), "reason": "qısa"})
        self.assertEqual(short.status_code, 400)
        self.assertEqual(short.json()["error"], "reason_too_short")

        reason = "Semestr kredit balansı 30-a uyğun deyil, sətirlər yenidən nəzərdən keçirilməlidir."
        ok = self._post("chair_head", {"action": "return", "plan": str(plan.id), "reason": reason})
        self.assertEqual(ok.status_code, 200)
        plan.refresh_from_db()
        self.assertEqual(plan.status, PlanStatus.RETURNED)
        self.assertEqual(plan.last_reason, reason)
        self.assertTrue(AuditLog.objects.filter(organization=self.org, reason__icontains="curriculum: return").exists())

    def test_approved_plan_is_immutable_for_rows_and_transitions(self):
        plan = self._plan(status=PlanStatus.APPROVED)
        row = self._balanced_row(plan)

        write = self._post(
            "teaching_office_head",
            {
                "action": "save_row",
                "plan": str(plan.id),
                "id": str(row.id),
                "subject": str(self.subject.id),
                "semester_number": "1",
                "credits": "6",
            },
        )
        self.assertEqual(write.status_code, 409)
        self.assertEqual(write.json()["error"], "plan_immutable")

        delete = self._post("teaching_office_head", {"action": "delete_row", "plan": str(plan.id), "id": str(row.id)})
        self.assertEqual(delete.status_code, 409)

        transition = self._post("chair_head", {"action": "submit", "plan": str(plan.id)})
        self.assertEqual(transition.status_code, 409)
        self.assertEqual(transition.json()["error"], "plan_immutable")

    def test_new_version_clones_rows_and_keeps_the_old_plan(self):
        plan = self._plan(status=PlanStatus.APPROVED)
        self._balanced_row(plan)
        response = self._post("teaching_office_head", {"action": "new_version", "plan": str(plan.id)})
        self.assertEqual(response.status_code, 200, response.content)

        clone = Curriculum.objects.get(pk=response.json()["id"])
        self.assertEqual(clone.version, 2)
        self.assertEqual(clone.status, PlanStatus.DRAFT)
        self.assertEqual(clone.previous_version_id, plan.id)
        self.assertEqual(clone.rows.count(), plan.rows.count())
        # Köhnə plan SİLİNMİR və statusu dəyişmir.
        plan.refresh_from_db()
        self.assertEqual(plan.status, PlanStatus.APPROVED)

    def test_forward_button_is_disabled_for_the_wrong_approver(self):
        """Düymə GİZLƏNMİR, `disabled` olur (handoff §4) — server yenə 403 verir."""
        plan = self._plan(status=PlanStatus.CHAIR_REVIEW)
        self._balanced_row(plan)
        office = self._fragment("teaching_office_head", "curriculum-editor", cu_plan=str(plan.id))
        payload = office.context["curriculum_editor_section"]["plan"]
        self.assertEqual(payload["next_action"], "approve_chair")
        self.assertFalse(payload["can_advance"])
        self.assertFalse(payload["can_return"])

        chair = self._fragment("chair_head", "curriculum-editor", cu_plan=str(plan.id))
        chair_payload = chair.context["curriculum_editor_section"]["plan"]
        self.assertTrue(chair_payload["can_advance"])
        self.assertTrue(chair_payload["can_return"])

    def test_approved_plan_hides_row_actions(self):
        plan = self._plan(status=PlanStatus.APPROVED)
        self._balanced_row(plan)
        response = self._fragment("teaching_office_head", "curriculum-editor", cu_plan=str(plan.id))
        section = response.context["curriculum_editor_section"]
        self.assertFalse(section["can_edit_rows"])
        self.assertNotContains(response, 'data-tof-open="tofPlanRowDialog"')

    def test_hour_mismatch_blocks_submit(self):
        plan = self._plan()
        # Kredit 30 → ümumi 900 olmalıdır; 100 verilir (POZULMUŞ).
        CurriculumSubject.objects.create(
            organization=self.org,
            curriculum=plan,
            subject=self.subject,
            semester_number=1,
            credits=30,
            total_hours=100,
            lecture_hours=10,
            seminar_hours=10,
            lab_hours=10,
            selfwork_hours=10,
        )
        blocked = self._post("chair_head", {"action": "submit", "plan": str(plan.id)})
        self.assertEqual(blocked.status_code, 400)
        self.assertEqual(blocked.json()["error"], "blocking_warnings")

    def test_semester_credit_target_is_a_blocking_warning(self):
        plan = self._plan()
        self._balanced_row(plan, credits=20)  # 20 ≠ 30 → semestr xəbərdarlığı
        blocked = self._post("chair_head", {"action": "submit", "plan": str(plan.id)})
        self.assertEqual(blocked.status_code, 400)
        self.assertEqual(blocked.json()["error"], "blocking_warnings")

    def test_row_hour_errors_pure_function(self):
        self.assertEqual(row_hour_errors(credits=0, total_hours=0, **_ZERO_SPLIT), ["credits_required"])
        # Ümumi saat kredit × 30 ilə uyğun gəlmir VƏ bölgü cəmi ümumiyə çatmır —
        # iki AYRI xəbərdarlıq, ikisi də təsdiqə göndərməni bloklayır.
        self.assertEqual(
            row_hour_errors(credits=5, total_hours=100, **_ZERO_SPLIT),
            ["total_mismatch", "split_mismatch"],
        )
        self.assertEqual(
            row_hour_errors(
                credits=5, total_hours=150, lecture_hours=30, seminar_hours=15, lab_hours=15, selfwork_hours=90
            ),
            [],
        )

    def test_row_save_fills_total_hours_from_credits(self):
        plan = self._plan()
        response = self._post(
            "teaching_office_head",
            {
                "action": "save_row",
                "plan": str(plan.id),
                "subject": str(self.subject.id),
                "semester_number": "1",
                "credits": "5",
                "lecture_hours": "30",
                "seminar_hours": "15",
                "lab_hours": "15",
            },
        )
        self.assertEqual(response.status_code, 200, response.content)
        row = CurriculumSubject.objects.get(curriculum=plan)
        self.assertEqual(row.total_hours, 150)  # kredit × 30
        self.assertEqual(row.selfwork_hours, 90)  # ümumi − auditoriya
        self.assertEqual(response.json()["row_errors"], [])


_ZERO_SPLIT = {"lecture_hours": 0, "seminar_hours": 0, "lab_hours": 0, "selfwork_hours": 0}


class GroupsRegistryTest(Stage2BaseTest):
    """6 — qrup reyestri: yaratma, arxiv (səbəb), toplu kursa keçirmə."""

    def _post(self, role, payload):
        url = reverse("organizations:group_action", kwargs={"slug": self.org.slug})
        return self._client(role).post(url, payload)

    def test_create_and_edit_group(self):
        created = self._post(
            "teaching_office_head",
            {
                "action": "save_group",
                "name": "QA-DS2 KE-25A",
                "code": "KE-25A",
                "specialty": str(self.specialty.id),
                "course_year": "1",
                "language_sector": "EN",
                "admission_year": "2025",
            },
        )
        self.assertEqual(created.status_code, 200, created.content)
        unit = OrgUnit.objects.get(organization=self.org, name="QA-DS2 KE-25A")
        self.assertEqual(unit.unit_type, OrgUnitType.GROUP)
        self.assertEqual(unit.settings["language_sector"], "EN")
        self.assertEqual(unit.parent_id, self.specialty.id)

    def test_archive_requires_reason_and_keeps_the_row(self):
        short = self._post("teaching_office_head", {"action": "archive", "id": str(self.group.id), "reason": "qısa"})
        self.assertEqual(short.status_code, 400)
        self.assertEqual(short.json()["error"], "reason_too_short")

        reason = "Qrup 2026/2027 tədris ilində formalaşmadı, tələbələri başqa qrupa köçürüldü."
        ok = self._post("teaching_office_head", {"action": "archive", "id": str(self.group.id), "reason": reason})
        self.assertEqual(ok.status_code, 200)
        self.group.refresh_from_db()
        self.assertTrue(OrgUnit.objects.filter(pk=self.group.pk).exists())  # SİLMƏ YOXDUR
        self.assertFalse(self.group.is_active)
        self.assertTrue(AuditLog.objects.filter(organization=self.org, reason__icontains="groups: archived").exists())

    def test_promote_bumps_course_year_and_audits_each_group(self):
        reason = "2026/2027 tədris ilinin başlanğıcında bütün qruplar növbəti kursa keçirilir."
        response = self._post(
            "teaching_office_head", {"action": "promote", "ids": [str(self.group.id)], "reason": reason}
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["promoted"], 1)
        self.group.refresh_from_db()
        self.assertEqual(self.group.settings["course_year"], 2)
        self.assertTrue(AuditLog.objects.filter(organization=self.org, reason__icontains="groups: promoted").exists())

    def test_promote_requires_reason(self):
        response = self._post("teaching_office_head", {"action": "promote", "ids": [str(self.group.id)]})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "reason_too_short")

    def test_group_status_follows_the_approved_plan_not_the_metadata(self):
        """«Plan yoxdur» qrupun metadatasından DEYİL, ixtisasın planından gəlir."""
        without = self._fragment("teaching_office_head", "groups-registry")
        row = next(r for r in without.context["groups_registry_section"]["rows"] if r["name"] == self.group.name)
        self.assertEqual(row["status_key"], "no_plan")

        plan = self._plan(status=PlanStatus.APPROVED)
        self._balanced_row(plan)
        with_plan = self._fragment("teaching_office_head", "groups-registry")
        row = next(r for r in with_plan.context["groups_registry_section"]["rows"] if r["name"] == self.group.name)
        self.assertEqual(row["status_key"], "active")

    def test_group_action_is_forbidden_for_teacher(self):
        response = self._post("teacher", {"action": "save_group", "name": "X", "specialty": str(self.specialty.id)})
        self.assertEqual(response.status_code, 403)

    def test_filters_and_pagination_are_server_side(self):
        for index in range(30):
            OrgUnit.objects.create(
                organization=self.org,
                parent=self.specialty,
                unit_type=OrgUnitType.GROUP,
                name=f"QA-DS2 F-{index:02d}",
                slug=f"ds2-bulk-{index}",
                settings={"language_sector": "RU", "course_year": 2},
            )
        first = self._fragment("teaching_office_head", "groups-registry")
        second = self._fragment("teaching_office_head", "groups-registry", gr_page="2")
        self.assertEqual(first.context["groups_registry_section"]["page_obj"].number, 1)
        self.assertEqual(second.context["groups_registry_section"]["page_obj"].number, 2)

        filtered = self._fragment("teaching_office_head", "groups-registry", gr_lang="AZ")
        names = {row["name"] for row in filtered.context["groups_registry_section"]["rows"]}
        self.assertEqual(names, {self.group.name})


class SemesterOpeningTest(Stage2BaseTest):
    """5/6 — açılış törətməsi, bloklayıcılar, kilid və «cari dövr»."""

    def _post(self, role, payload):
        return self._client(role).post(reverse("registrar:semester_action"), payload)

    def _approved_plan(self):
        plan = self._plan(status=PlanStatus.APPROVED)
        self._balanced_row(plan, self.subject, semester=1, credits=15)
        self._balanced_row(plan, self.subject_b, semester=1, credits=15)
        return plan

    def test_generate_creates_offerings_and_is_idempotent(self):
        self._approved_plan()
        payload = {
            "action": "generate",
            "period": str(self.period.id),
            "semester_number": "1",
            "programs": [str(self.program.id)],
        }
        first = self._post("teaching_office_head", payload)
        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(first.json()["created"], 2)
        self.assertEqual(CourseOffering.objects.filter(organization=self.org, period=self.period).count(), 2)

        second = self._post("teaching_office_head", payload)
        self.assertEqual(second.json()["created"], 0)
        self.assertEqual(second.json()["existing"], 2)
        self.assertEqual(CourseOffering.objects.filter(organization=self.org, period=self.period).count(), 2)

    def test_generate_never_clears_an_existing_instructor(self):
        self._approved_plan()
        payload = {
            "action": "generate",
            "period": str(self.period.id),
            "semester_number": "1",
            "programs": [str(self.program.id)],
        }
        self._post("teaching_office_head", payload)
        offering = CourseOffering.objects.filter(organization=self.org, period=self.period).first()
        offering.instructor = self.users["teacher"]
        offering.save(update_fields=["instructor"])

        self._post("teaching_office_head", payload)
        offering.refresh_from_db()
        self.assertEqual(offering.instructor_id, self.users["teacher"].id)

    def test_programme_without_approved_plan_is_a_blocker(self):
        response = self._post(
            "teaching_office_head",
            {
                "action": "generate",
                "period": str(self.period.id),
                "semester_number": "1",
                "programs": [str(self.orphan_program.id)],
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["created"], 0)
        self.assertEqual(response.json()["skipped_no_plan"], 1)
        blocked = {item["label"] for item in response.json()["blocked_programs"]}
        self.assertIn(self.orphan_program.display_label, blocked)

    def test_draft_plan_is_not_a_source_for_offerings(self):
        plan = self._plan(status=PlanStatus.DRAFT)
        self._balanced_row(plan)
        response = self._post(
            "teaching_office_head",
            {
                "action": "generate",
                "period": str(self.period.id),
                "semester_number": "1",
                "programs": [str(self.program.id)],
            },
        )
        self.assertEqual(response.json()["created"], 0)
        self.assertEqual(response.json()["skipped_no_plan"], 1)

    def test_lock_is_blocked_while_instructors_are_missing(self):
        self._approved_plan()
        self._post(
            "teaching_office_head",
            {
                "action": "generate",
                "period": str(self.period.id),
                "semester_number": "1",
                "programs": [str(self.program.id)],
            },
        )
        response = self._post("teaching_office_head", {"action": "lock", "period": str(self.period.id)})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "missing_instructors")

    def test_lock_then_unlock_requires_reason_and_audits(self):
        self._approved_plan()
        self._post(
            "teaching_office_head",
            {
                "action": "generate",
                "period": str(self.period.id),
                "semester_number": "1",
                "programs": [str(self.program.id)],
            },
        )
        CourseOffering.objects.filter(organization=self.org, period=self.period).update(
            instructor=self.users["teacher"]
        )

        locked = self._post("teaching_office_head", {"action": "lock", "period": str(self.period.id)})
        self.assertEqual(locked.status_code, 200, locked.content)
        self.period.refresh_from_db()
        self.assertIsNotNone(self.period.locked_at)
        self.assertEqual(self.period.opening_status, "locked")

        short = self._post(
            "teaching_office_head", {"action": "unlock", "period": str(self.period.id), "reason": "qısa"}
        )
        self.assertEqual(short.status_code, 400)

        reason = "Kafedra müəllim təyinatında səhv aşkarladı; düzəliş üçün semestr müvəqqəti açılır."
        opened = self._post(
            "teaching_office_head", {"action": "unlock", "period": str(self.period.id), "reason": reason}
        )
        self.assertEqual(opened.status_code, 200)
        self.period.refresh_from_db()
        self.assertIsNone(self.period.locked_at)
        self.assertTrue(AuditLog.objects.filter(organization=self.org, reason__icontains="semester: unlocked").exists())

    def test_generation_is_rejected_on_a_locked_semester(self):
        self._approved_plan()
        self.period.locked_at = timezone.now()
        self.period.save(update_fields=["locked_at"])
        response = self._post(
            "teaching_office_head",
            {
                "action": "generate",
                "period": str(self.period.id),
                "semester_number": "1",
                "programs": [str(self.program.id)],
            },
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "locked")

    def test_set_current_period_is_audited(self):
        other = AcademicPeriod.objects.create(
            organization=self.org,
            name="Yaz semestri",
            period_type="semester",
            academic_year="2026/2027",
            start_date=date(2027, 2, 1),
            end_date=date(2027, 6, 20),
            is_current=True,
        )
        response = self._post("teaching_office_head", {"action": "set_current", "id": str(self.period.id)})
        self.assertEqual(response.status_code, 200, response.content)
        self.period.refresh_from_db()
        other.refresh_from_db()
        self.assertTrue(self.period.is_current)
        self.assertFalse(other.is_current)
        self.assertTrue(
            AuditLog.objects.filter(organization=self.org, reason__icontains="current period switched").exists()
        )

    def test_offering_cancel_is_soft_and_needs_a_reason(self):
        self._approved_plan()
        self._post(
            "teaching_office_head",
            {
                "action": "generate",
                "period": str(self.period.id),
                "semester_number": "1",
                "programs": [str(self.program.id)],
            },
        )
        offering = CourseOffering.objects.filter(organization=self.org, period=self.period).first()
        reason = "Qrupda minimum tələbə həddi toplanmadı, açılış bu semestr üçün ləğv olunur."
        response = self._post(
            "teaching_office_head", {"action": "cancel_offering", "id": str(offering.id), "reason": reason}
        )
        self.assertEqual(response.status_code, 200)
        offering.refresh_from_db()
        self.assertTrue(CourseOffering.objects.filter(pk=offering.pk).exists())  # SİLMƏ YOXDUR
        self.assertFalse(offering.is_active)

    def test_semester_action_is_forbidden_for_dean_without_open_permission(self):
        """Dekanda `semester.view` var, `semester.open` YOXDUR."""
        response = self._post("dean", {"action": "generate", "period": str(self.period.id), "semester_number": "1"})
        self.assertEqual(response.status_code, 403)


class Stage2PermissionCatalogTest(TestCase):
    """7 — icazə kataloqunun bütövlüyü (açar ↔ etiket ↔ rol xəritəsi)."""

    def test_new_keys_are_in_the_catalog_and_labelled(self):
        from apps.organizations.permissions import (
            PERMISSION_CATEGORIES,
            PERMISSION_CATEGORY_LABELS,
            PERMISSION_LABELS,
        )

        keys = {key for bucket in PERMISSION_CATEGORIES.values() for key in bucket}
        expected = {
            "unit.group_manage",
            "plan.view",
            "plan.edit",
            "plan.submit",
            "plan.approve_chair",
            "plan.approve_council",
            "plan.approve_office",
            "semester.view",
            "semester.open",
            "semester.lock",
            "semester.unlock",
        }
        self.assertTrue(expected <= keys, sorted(expected - keys))
        self.assertTrue(expected <= set(PERMISSION_LABELS), sorted(expected - set(PERMISSION_LABELS)))
        self.assertIn("plan", PERMISSION_CATEGORY_LABELS)
        self.assertIn("semester", PERMISSION_CATEGORY_LABELS)

    def test_no_legacy_prefix_is_introduced(self):
        """`structure.*` LEGACY-dir; Mərhələ 2 açarları ona toxunmur."""
        from apps.organizations.default_roles_stage2 import STAGE2_ROLE_GRANTS

        offenders = [
            key
            for keys in STAGE2_ROLE_GRANTS.values()
            for key in keys
            if key.startswith(("grading.", "courses.", "exams.", "members.", "structure."))
        ]
        self.assertEqual(offenders, [])

    def test_separation_of_duties_in_the_default_grants(self):
        """Heç bir akademik rol zənciri təkbaşına başdan-sona keçə bilmir."""
        from apps.organizations.default_roles_stage2 import STAGE2_ROLE_GRANTS

        chain = {"plan.approve_chair", "plan.approve_council", "plan.approve_office"}
        for role in ("chair_head", "dean", "teaching_office_head", "teaching_office_staff"):
            granted = set(STAGE2_ROLE_GRANTS.get(role, ())) & chain
            self.assertLess(len(granted), len(chain), f"{role} zəncirin hamısını daşıyır: {sorted(granted)}")

    def test_university_role_seed_carries_the_new_keys(self):
        from apps.organizations.default_roles_university import UNIVERSITY_ROLES

        by_name = {role["name"]: set(role.get("permissions", [])) for role in UNIVERSITY_ROLES}
        self.assertIn("plan.approve_office", by_name.get("teaching_office_head", set()))
        self.assertIn("plan.approve_chair", by_name.get("chair_head", set()))
        self.assertIn("plan.approve_council", by_name.get("dean", set()))
        self.assertNotIn("plan.approve_office", by_name.get("teaching_office_staff", set()))


class PlanCrossScopeTest(Stage2BaseTest):
    """5 — ƏHATƏ (audit 2026-09-03): başqa kafedranın/fakültənin planı 404-dür.

    İcazə açarı («nə edə bilərsən») ilə struktur əhatəsi («nəyə toxuna
    bilərsən») AYRI suallardır. `plan.edit` / `plan.approve_chair` daşıyan
    kafedra müdiri YALNIZ öz alt-ağacındakı ixtisasın planına toxunmalıdır;
    əks halda bir kafedra müdiri bütün universitetin tədris planlarını
    redaktə edə və kafedra mərhələsini keçirə bilərdi.
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.faculty_b = OrgUnit.objects.create(
            organization=cls.org, unit_type=OrgUnitType.FACULTY, name="Dizayn", slug="ds2-fak-b"
        )
        cls.chair_b = OrgUnit.objects.create(
            organization=cls.org,
            parent=cls.faculty_b,
            unit_type=OrgUnitType.CHAIR,
            name="Dizayn kafedrası",
            slug="ds2-kaf-b",
        )
        cls.specialty_b = OrgUnit.objects.create(
            organization=cls.org,
            parent=cls.chair_b,
            unit_type=OrgUnitType.SPECIALTY,
            name="Qrafik dizayn",
            slug="ds2-ixt-b",
        )
        cls.program_b = Program.objects.create(
            organization=cls.org,
            code="QA-DS2-PRG-B",
            official_code="6050300",
            name="QA-DS2 Qrafik dizayn",
            specialty_unit=cls.specialty_b,
        )
        cls.chair_head_b = User.objects.create_user("ds2_chair_head_b", "ds2_chb@qku.edu.az", PASSWORD)
        Membership.objects.create(
            user=cls.chair_head_b,
            organization=cls.org,
            role=cls.roles["chair_head"],
            scope_unit=cls.chair_b,
            is_primary=True,
            is_active=True,
        )
        cls.dean_b = User.objects.create_user("ds2_dean_b", "ds2_deanb@qku.edu.az", PASSWORD)
        Membership.objects.create(
            user=cls.dean_b,
            organization=cls.org,
            role=cls.roles["dean"],
            scope_unit=cls.faculty_b,
            is_primary=True,
            is_active=True,
        )

    def _client_for(self, user):
        client = Client()
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    def _post_as(self, user, payload):
        return self._client_for(user).post(reverse("registrar:curriculum_action"), payload)

    def _post(self, role, payload):
        return self._client(role).post(reverse("registrar:curriculum_action"), payload)

    def test_foreign_chair_head_cannot_add_a_row_to_another_chairs_plan(self):
        plan = self._plan()
        response = self._post_as(
            self.chair_head_b,
            {
                "action": "save_row",
                "plan": str(plan.id),
                "subject": str(self.subject.id),
                "semester_number": "1",
                "credits": "5",
            },
        )
        self.assertIn(response.status_code, (403, 404), response.content)
        self.assertEqual(CurriculumSubject.objects.filter(curriculum=plan).count(), 0)

    def test_foreign_chair_head_cannot_approve_the_chair_stage(self):
        plan = self._plan(status=PlanStatus.CHAIR_REVIEW)
        self._balanced_row(plan)
        response = self._post_as(self.chair_head_b, {"action": "approve_chair", "plan": str(plan.id)})
        self.assertIn(response.status_code, (403, 404), response.content)
        plan.refresh_from_db()
        self.assertEqual(plan.status, PlanStatus.CHAIR_REVIEW)

    def test_foreign_dean_cannot_approve_the_faculty_council_stage(self):
        plan = self._plan(status=PlanStatus.FACULTY_COUNCIL)
        self._balanced_row(plan)
        response = self._post_as(self.dean_b, {"action": "approve_council", "plan": str(plan.id)})
        self.assertIn(response.status_code, (403, 404), response.content)
        plan.refresh_from_db()
        self.assertEqual(plan.status, PlanStatus.FACULTY_COUNCIL)

    def test_foreign_chair_head_cannot_create_a_plan_for_another_specialty(self):
        response = self._post_as(
            self.chair_head_b,
            {"action": "create_plan", "program": str(self.program.id), "admission_year": "2027"},
        )
        self.assertIn(response.status_code, (403, 404), response.content)
        self.assertFalse(Curriculum.objects.filter(program=self.program, admission_year=2027).exists())

    def test_own_chair_head_still_works(self):
        """Pozitiv nəzarət — öz kafedrasında heç nə qırılmır."""
        plan = self._plan(status=PlanStatus.CHAIR_REVIEW)
        self._balanced_row(plan)
        response = self._post("chair_head", {"action": "approve_chair", "plan": str(plan.id)})
        self.assertEqual(response.status_code, 200, response.content)
        plan.refresh_from_db()
        self.assertEqual(plan.status, PlanStatus.FACULTY_COUNCIL)

    def test_org_wide_teaching_office_is_unaffected(self):
        """Tədris şöbəsi ORGANIZATION scope-ludur — hər ixtisasa toxuna bilər."""
        plan = self._plan()
        response = self._post(
            "teaching_office_head",
            {
                "action": "save_row",
                "plan": str(plan.id),
                "subject": str(self.subject.id),
                "semester_number": "1",
                "credits": "5",
            },
        )
        self.assertEqual(response.status_code, 200, response.content)
