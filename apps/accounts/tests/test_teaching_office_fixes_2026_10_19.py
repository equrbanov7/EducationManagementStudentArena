"""Tədris şöbəsi səthlərinin inventarında tapılan 7 xətanın düzəlişi (2026-10-19).

1. Plan sətri dialoqu SEÇMƏ bayrağını/blokunu itirmir (qismən yeniləmə təhlükəsiz).
2. «Semestr açılışı» dövr yazısı ``full_clean()``-dən keçir (üst-üstə düşmə qaydası).
3. Dövr dialoqunda imtahan sessiyası + seçim (qeydiyyat) pəncərəsi.
4. Köhnə plan versiyası YENİ versiya TƏSDİQLƏNƏNDƏ söndürülür (qaralamada yox).
5. Qrup formu ``settings.curriculum_id``-ni sıfırlamır.
6. İxtisas yazısının auditi davamiyyət həddi / ECTS / kafedra sahələrini daşıyır.
7. Ağacdan rəhbər təyini reyestrlə EYNİ servisdən keçir (dean/chair_head üzvlüyü).
"""

from datetime import date

from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.accounts.tests.test_teaching_office_stage2 import Stage2BaseTest
from apps.audit.models import AuditLog
from apps.organizations.models import AcademicPeriod, Membership, OrgUnit
from apps.organizations.public import get_permission_scope
from apps.registrar.curriculum_registry import programs_without_approved_plan
from apps.registrar.models import Curriculum, CurriculumSubject
from apps.registrar.models.curriculum_meta import PlanStatus
from apps.registrar.semester_open import approved_plan_for
from apps.registrar.semester_period_windows import WindowError, read_windows, validate_windows

User = get_user_model()


def _row_post(plan, row, subject, **extra):
    """Dialoqun göndərdiyi sətir payload-u (saat sahələri balanslı)."""
    payload = {
        "action": "save_row",
        "plan": str(plan.id),
        "id": str(row.id) if row else "",
        "subject": str(subject.id),
        "semester_number": "1",
        "credits": "5",
        "lecture_hours": "30",
        "seminar_hours": "15",
        "lab_hours": "15",
        "assessment_form": "exam",
    }
    payload.update(extra)
    return payload


# --------------------------------------------------------------------------- #
# 1 — seçmə sətir
# --------------------------------------------------------------------------- #


class PlanRowElectiveTest(Stage2BaseTest):
    def _post(self, payload):
        return self._client("teaching_office_head").post(reverse("registrar:curriculum_action"), payload)

    def _row(self, plan, subject=None, **fields):
        return CurriculumSubject.objects.create(
            organization=self.org,
            curriculum=plan,
            subject=subject or self.subject,
            semester_number=1,
            credits=5,
            total_hours=150,
            lecture_hours=30,
            seminar_hours=15,
            lab_hours=15,
            selfwork_hours=90,
            **fields,
        )

    def test_dialog_edit_keeps_the_elective_flag_and_block(self):
        plan = self._plan()
        row = self._row(plan, is_elective=True, elective_group="SB1", required_choices=1)
        response = self._post(
            _row_post(plan, row, self.subject, is_elective="1", elective_group="SB1", required_choices="2")
        )
        self.assertEqual(response.status_code, 200, response.content)
        row.refresh_from_db()
        self.assertTrue(row.is_elective)
        self.assertEqual(row.elective_group, "SB1")
        self.assertEqual(row.required_choices, 2)

    def test_post_without_elective_fields_keeps_existing_values(self):
        """Köhnə klient / qismən yeniləmə: sahə YOXDURSA bayraq silinmir (əvvəlki xəta)."""
        plan = self._plan()
        row = self._row(plan, is_elective=True, elective_group="SB1", required_choices=2)
        response = self._post(_row_post(plan, row, self.subject, credits="6"))
        self.assertEqual(response.status_code, 200, response.content)
        row.refresh_from_db()
        self.assertTrue(row.is_elective)
        self.assertEqual(row.elective_group, "SB1")
        self.assertEqual(row.required_choices, 2)
        self.assertEqual(row.credits, 6)

    def test_editing_a_mandatory_row_keeps_it_mandatory(self):
        plan = self._plan()
        row = self._row(plan)
        self.assertEqual(self._post(_row_post(plan, row, self.subject)).status_code, 200)
        row.refresh_from_db()
        self.assertFalse(row.is_elective)
        # Dialoq bayrağı söndürülmüş göndərir — blok/say mənasızdır, nəzərə alınmır.
        response = self._post(
            _row_post(plan, row, self.subject, is_elective="", elective_group="SB9", required_choices="0")
        )
        self.assertEqual(response.status_code, 200, response.content)
        row.refresh_from_db()
        self.assertFalse(row.is_elective)
        self.assertEqual(row.elective_group, "")
        self.assertEqual(row.required_choices, 1)

    def test_unchecking_the_flag_turns_an_elective_row_mandatory(self):
        plan = self._plan()
        row = self._row(plan, is_elective=True, elective_group="SB1")
        response = self._post(_row_post(plan, row, self.subject, is_elective="", elective_group="SB1"))
        self.assertEqual(response.status_code, 200, response.content)
        row.refresh_from_db()
        self.assertFalse(row.is_elective)
        self.assertEqual(row.elective_group, "")

    def test_required_choices_is_validated_only_for_elective_rows(self):
        plan = self._plan()
        for raw in ("0", "-1", "21", "abc"):
            with self.subTest(raw=raw):
                response = self._post(
                    _row_post(plan, None, self.subject, is_elective="1", elective_group="SB1", required_choices=raw)
                )
                self.assertEqual(response.status_code, 400, response.content)
                self.assertEqual(response.json()["error"], "bad_required_choices")
                self.assertEqual(response.json()["field"], "required_choices")
        self.assertFalse(CurriculumSubject.objects.filter(curriculum=plan).exists())

    def test_elective_row_needs_a_block(self):
        plan = self._plan()
        response = self._post(_row_post(plan, None, self.subject, is_elective="1", elective_group=" "))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "elective_group_required")

    def test_required_choices_is_synced_across_the_block(self):
        plan = self._plan()
        row_a = self._row(plan, is_elective=True, elective_group="SB1", required_choices=1)
        row_b = self._row(plan, self.subject_b, is_elective=True, elective_group="SB1", required_choices=1)
        response = self._post(
            _row_post(plan, row_a, self.subject, is_elective="1", elective_group="SB1", required_choices="2")
        )
        self.assertEqual(response.status_code, 200, response.content)
        row_b.refresh_from_db()
        self.assertEqual(row_b.required_choices, 2)
        audit = AuditLog.objects.filter(organization=self.org, reason__icontains="plan row saved").latest("created_at")
        self.assertEqual(audit.new_values["required_choices"], 2)
        self.assertEqual(audit.new_values["block_rows_synced"], 1)
        self.assertEqual(audit.old_values["is_elective"], True)

    def test_dialog_renders_the_elective_fields_and_row_prefill(self):
        plan = self._plan()
        self._row(plan, is_elective=True, elective_group="SB1", required_choices=2)
        response = self._fragment("teaching_office_head", "curriculum-editor", cu_plan=str(plan.id))
        self.assertEqual(response.status_code, 200)
        html = response.json()["html"]
        for name in ("is_elective", "elective_group", "required_choices"):
            self.assertIn(f'name="{name}"', html)
        self.assertIn('"is_elective": "1", "elective_group": "SB1", "required_choices": "2"', html)


# --------------------------------------------------------------------------- #
# 2 + 3 — dövr yazısı: model doğrulaması və təqvim pəncərələri
# --------------------------------------------------------------------------- #


class PeriodSaveTest(Stage2BaseTest):
    def _post(self, **fields):
        payload = {"action": "save_period", "name": "Yaz semestri", "academic_year": "2026/2027"}
        payload.update(fields)
        return self._client("teaching_office_head").post(reverse("registrar:semester_action"), payload)

    def test_overlapping_period_of_the_same_type_is_rejected(self):
        response = self._post(start_date="2027-01-10", end_date="2027-06-01")
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["error"], "overlap")
        self.assertEqual(response.json()["field"], "start_date")
        self.assertFalse(AcademicPeriod.objects.filter(organization=self.org, name="Yaz semestri").exists())

    def test_non_overlapping_period_is_accepted(self):
        response = self._post(start_date="2027-02-10", end_date="2027-06-10")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(AcademicPeriod.objects.filter(organization=self.org, name="Yaz semestri").exists())

    def test_editing_a_period_does_not_overlap_with_itself(self):
        response = self._post(
            id=str(self.period.id),
            name=self.period.name,
            start_date="2026-09-16",
            end_date="2027-01-30",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.period.refresh_from_db()
        self.assertEqual(self.period.end_date, date(2027, 1, 30))

    def test_editing_into_another_period_is_rejected(self):
        spring = AcademicPeriod.objects.create(
            organization=self.org,
            name="Yaz semestri",
            period_type="semester",
            academic_year="2026/2027",
            start_date=date(2027, 2, 10),
            end_date=date(2027, 6, 10),
        )
        response = self._post(id=str(spring.id), start_date="2027-01-20", end_date="2027-06-10")
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["error"], "overlap")
        spring.refresh_from_db()
        self.assertEqual(spring.start_date, date(2027, 2, 10))

    def test_duplicate_name_and_year_is_a_field_error(self):
        response = self._post(name=self.period.name, start_date="2028-02-10", end_date="2028-06-10")
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["error"], "duplicate")
        self.assertEqual(response.json()["field"], "name")

    def test_windows_are_saved_and_audited(self):
        response = self._post(
            id=str(self.period.id),
            name=self.period.name,
            start_date="2026-09-15",
            end_date="2027-01-25",
            # Sessiyanın sonu semestrdən SONRAYA uzanır — xəbərdarlıq yoxdur.
            exam_session_start="2027-01-10",
            exam_session_end="2027-02-05",
            registration_start="2026-08-25",
            registration_end="2026-09-10",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["warnings"], [])
        self.period.refresh_from_db()
        self.assertEqual(self.period.exam_session_start, date(2027, 1, 10))
        self.assertEqual(self.period.exam_session_end, date(2027, 2, 5))
        self.assertEqual(self.period.registration_start, date(2026, 8, 25))
        self.assertEqual(self.period.registration_end, date(2026, 9, 10))
        audit = AuditLog.objects.filter(organization=self.org, reason="semester: period saved").latest("created_at")
        self.assertEqual(audit.old_values["exam_session_end"], "")
        self.assertEqual(audit.new_values["exam_session_end"], "2027-02-05")
        self.assertEqual(audit.new_values["registration_start"], "2026-08-25")

    def test_absent_window_fields_keep_values_and_empty_ones_clear_them(self):
        AcademicPeriod.objects.filter(pk=self.period.pk).update(
            exam_session_start=date(2027, 1, 10), exam_session_end=date(2027, 1, 31)
        )
        base = {"id": str(self.period.id), "name": self.period.name, "start_date": "2026-09-15"}
        self.assertEqual(self._post(end_date="2027-01-26", **base).status_code, 200)
        self.period.refresh_from_db()
        self.assertEqual(self.period.exam_session_end, date(2027, 1, 31))
        cleared = self._post(end_date="2027-01-26", exam_session_start="", exam_session_end="", **base)
        self.assertEqual(cleared.status_code, 200, cleared.content)
        self.period.refresh_from_db()
        self.assertIsNone(self.period.exam_session_start)
        self.assertIsNone(self.period.exam_session_end)

    def test_window_end_before_start_is_rejected(self):
        response = self._post(
            start_date="2027-02-10",
            end_date="2027-06-10",
            exam_session_start="2027-06-01",
            exam_session_end="2027-05-20",
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["error"], "window_order")
        self.assertEqual(response.json()["field"], "exam_session_end")

    def test_half_window_is_rejected(self):
        response = self._post(start_date="2027-02-10", end_date="2027-06-10", registration_start="2027-02-01")
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["error"], "window_incomplete")
        self.assertEqual(response.json()["field"], "registration_end")

    def test_window_far_outside_the_period_saves_with_a_warning(self):
        response = self._post(
            start_date="2027-02-10",
            end_date="2027-06-10",
            exam_session_start="2027-09-01",
            exam_session_end="2027-09-20",
            registration_start="2026-01-01",
            registration_end="2026-01-10",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(len(response.json()["warnings"]), 2)
        self.assertTrue(response.json()["message"])

    def test_dialog_renders_the_window_fields_and_edit_prefill(self):
        response = self._fragment("teaching_office_head", "semester-opening", sm_period=str(self.period.id))
        self.assertEqual(response.status_code, 200)
        html = response.json()["html"]
        for name in ("exam_session_start", "exam_session_end", "registration_start", "registration_end"):
            self.assertIn(f'name="{name}"', html)
        self.assertIn("&quot;exam_session_start&quot;: &quot;&quot;", html)
        self.assertIn(f"&quot;id&quot;: &quot;{self.period.id}&quot;", html)


class PeriodWindowRulesTest(Stage2BaseTest):
    """Saf qaydalar — HTTP-siz."""

    START, END = date(2026, 9, 15), date(2027, 1, 25)

    def _validate(self, **values):
        full = {name: None for name in ("exam_session_start", "exam_session_end")}
        full.update({name: None for name in ("registration_start", "registration_end")})
        full.update(values)
        return validate_windows(full, period_start=self.START, period_end=self.END)

    def test_exam_session_may_extend_after_the_period(self):
        self.assertEqual(self._validate(exam_session_start=date(2027, 1, 12), exam_session_end=date(2027, 2, 20)), [])

    def test_exam_session_starting_before_the_period_warns(self):
        self.assertEqual(
            len(self._validate(exam_session_start=date(2026, 9, 1), exam_session_end=date(2026, 9, 20))), 1
        )

    def test_registration_adjacent_to_the_start_is_fine(self):
        self.assertEqual(self._validate(registration_start=date(2026, 8, 20), registration_end=date(2026, 9, 10)), [])

    def test_same_day_window_is_allowed(self):
        self.assertEqual(self._validate(registration_start=date(2026, 9, 1), registration_end=date(2026, 9, 1)), [])

    def test_bad_date_names_the_field(self):
        with self.assertRaises(WindowError) as ctx:
            read_windows({"exam_session_start": "31.01.2027"}, None)
        self.assertEqual(ctx.exception.field, "exam_session_start")


# --------------------------------------------------------------------------- #
# 4 — versiya keçidi
# --------------------------------------------------------------------------- #


class PlanVersionSupersedeTest(Stage2BaseTest):
    def _post(self, role, payload):
        return self._client(role).post(reverse("registrar:curriculum_action"), payload)

    def _new_version(self, plan):
        response = self._post("teaching_office_head", {"action": "new_version", "plan": str(plan.id)})
        self.assertEqual(response.status_code, 200, response.content)
        return Curriculum.objects.get(pk=response.json()["id"])

    def test_draft_version_does_not_deactivate_the_approved_one(self):
        old = self._plan(status=PlanStatus.APPROVED)
        self._balanced_row(old)
        clone = self._new_version(old)
        old.refresh_from_db()
        self.assertTrue(old.is_active)
        self.assertTrue(clone.is_active)
        # Arada plansız boşluq yoxdur: açılış hələ köhnə versiyanı görür.
        self.assertEqual(approved_plan_for(self.org, self.program), old)
        self.assertNotIn(str(self.program.id), {item["id"] for item in programs_without_approved_plan(self.org)})

    def test_approving_the_new_version_deactivates_the_old_one(self):
        old = self._plan(status=PlanStatus.APPROVED)
        self._balanced_row(old)
        clone = self._new_version(old)
        parallel = self._new_version(old)  # paralel qaralama — toxunulmamalıdır
        other_year = self._plan(status=PlanStatus.APPROVED, year=2025)
        Curriculum.objects.filter(pk=clone.pk).update(status=PlanStatus.TEACHING_OFFICE)

        response = self._post("teaching_office_head", {"action": "approve_office", "plan": str(clone.id)})
        self.assertEqual(response.status_code, 200, response.content)

        old.refresh_from_db()
        clone.refresh_from_db()
        parallel.refresh_from_db()
        other_year.refresh_from_db()
        self.assertEqual(clone.status, PlanStatus.APPROVED)
        self.assertTrue(clone.is_active)
        self.assertFalse(old.is_active)  # SİLİNMİR, söndürülür
        self.assertEqual(old.status, PlanStatus.APPROVED)
        self.assertTrue(parallel.is_active)
        self.assertTrue(other_year.is_active)
        self.assertEqual(approved_plan_for(self.org, self.program), clone)
        audit = AuditLog.objects.filter(organization=self.org, reason__icontains="approve_office").latest("created_at")
        self.assertEqual(audit.new_values["superseded_versions"], [old.version])


# --------------------------------------------------------------------------- #
# 5 — qrup formu planı sıfırlamır
# --------------------------------------------------------------------------- #


class GroupCurriculumLinkTest(Stage2BaseTest):
    def _post(self, payload):
        url = reverse("organizations:group_action", kwargs={"slug": self.org.slug})
        return self._client("teaching_office_head").post(url, payload)

    def _form(self, **extra):
        payload = {
            "action": "save_group",
            "id": str(self.group.id),
            "name": self.group.name,
            "code": self.group.code,
            "course_year": "2",
            "language_sector": "AZ",
            "admission_year": "2024",
        }
        payload.update(extra)
        return payload

    def test_saving_a_group_keeps_the_curriculum_link(self):
        plan = self._plan(status=PlanStatus.APPROVED)
        OrgUnit.objects.filter(pk=self.group.pk).update(settings={**self.group.settings, "curriculum_id": str(plan.id)})
        response = self._post(self._form())
        self.assertEqual(response.status_code, 200, response.content)
        self.group.refresh_from_db()
        self.assertEqual(self.group.settings["curriculum_id"], str(plan.id))
        self.assertEqual(self.group.settings["course_year"], 2)

    def test_explicit_curriculum_field_still_sets_or_clears_it(self):
        plan = self._plan(status=PlanStatus.APPROVED)
        self.assertEqual(self._post(self._form(curriculum_id=str(plan.id))).status_code, 200)
        self.group.refresh_from_db()
        self.assertEqual(self.group.settings["curriculum_id"], str(plan.id))
        self.assertEqual(self._post(self._form(curriculum_id="not-a-uuid")).status_code, 200)
        self.group.refresh_from_db()
        self.assertEqual(self.group.settings["curriculum_id"], "")


# --------------------------------------------------------------------------- #
# 6 — ixtisas auditi
# --------------------------------------------------------------------------- #


class ProgramAuditTest(Stage2BaseTest):
    def test_absence_limit_and_ects_changes_are_audited(self):
        self.program.absence_limit_percent = 25
        self.program.ects_total = 240
        self.program.save()
        response = self._client("teaching_office_head").post(
            reverse("registrar:catalog_action"),
            {
                "action": "save_program",
                "id": str(self.program.id),
                "name": self.program.name,
                "degree_level": self.program.degree_level,
                "education_form": self.program.education_form,
                "official_code": self.program.official_code,
                "specialty_unit": str(self.specialty.id),
                "ects_total": "300",
                "absence_limit_percent": "30",
            },
        )
        self.assertEqual(response.status_code, 200, response.content)
        audit = AuditLog.objects.filter(organization=self.org, reason="catalog: program updated").latest("created_at")
        self.assertEqual(audit.old_values["absence_limit_percent"], 25)
        self.assertEqual(audit.new_values["absence_limit_percent"], 30)
        self.assertEqual(audit.old_values["ects_total"], 240)
        self.assertEqual(audit.new_values["ects_total"], 300)
        self.assertEqual(audit.new_values["specialty_unit"], str(self.specialty.id))
        self.assertEqual(audit.new_values["official_code"], self.program.official_code)


# --------------------------------------------------------------------------- #
# 7 — rəhbər təyini: ağac və reyestr eyni servis
# --------------------------------------------------------------------------- #


class UnitHeadAssignmentTest(Stage2BaseTest):
    REASON = "Kafedra müdiri vəzifəsinə rektorun əmri əsasında təyinat."

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        role = cls.roles["teaching_office_head"]
        role.permissions = [*role.permissions, "unit.assign_head"]
        role.save(update_fields=["permissions"])
        # Hədəf şəxslər: təşkilat üzvü olan müəllim və ikinci müəllim.
        cls.target = cls.users["teacher"]
        cls.second = User.objects.create_user("ds2_teacher2", "ds2_teacher2@qku.edu.az", "StrongPass123!")
        Membership.objects.create(
            user=cls.second, organization=cls.org, role=cls.roles["teacher"], is_primary=True, is_active=True
        )

    def _tree(self, unit, head):
        url = reverse("organizations:structure_tree_action", kwargs={"slug": self.org.slug})
        payload = {"action": "assign_head", "unit": str(unit.id), "head": str(head.id) if head else ""}
        payload["reason"] = self.REASON
        return self._client("teaching_office_head").post(url, payload)

    def _registry(self, unit, head):
        url = reverse("organizations:structure_unit_action", kwargs={"slug": self.org.slug})
        payload = {"action": "assign_head", "id": str(unit.id), "head": str(head.id) if head else ""}
        payload["reason"] = self.REASON
        return self._client("teaching_office_head").post(url, payload)

    def _active(self, user, role_name, unit):
        return Membership.objects.filter(
            organization=self.org, user=user, role=self.roles[role_name], scope_unit=unit, is_active=True
        ).exists()

    def test_tree_assigns_chair_head_membership_and_approval_scope(self):
        response = self._tree(self.chair, self.target)
        self.assertEqual(response.status_code, 200, response.content)
        self.chair.refresh_from_db()
        self.assertEqual(self.chair.head_id, self.target.id)
        self.assertTrue(self._active(self.target, "chair_head", self.chair))
        # Plan zənciri (və sillabus təsdiqi) əhatəni ÜZVLÜKDƏN alır.
        scope = get_permission_scope(User.objects.get(pk=self.target.pk), self.org, "plan.approve_chair")
        self.assertIn(self.chair.id, scope.unit_ids)
        audit = AuditLog.objects.filter(organization=self.org, reason__icontains="structure tree: head assigned")
        self.assertEqual(audit.latest("created_at").new_values["role"], "chair_head")

    def test_tree_reassignment_deactivates_the_previous_head_membership(self):
        self.assertEqual(self._tree(self.chair, self.target).status_code, 200)
        self.assertEqual(self._tree(self.chair, self.second).status_code, 200)
        self.assertFalse(self._active(self.target, "chair_head", self.chair))
        self.assertTrue(self._active(self.second, "chair_head", self.chair))
        # Silmə yoxdur — köhnə üzvlük qalır, sadəcə passivdir.
        self.assertTrue(
            Membership.objects.filter(
                organization=self.org, user=self.target, role=self.roles["chair_head"], scope_unit=self.chair
            ).exists()
        )
        self.assertEqual(self._tree(self.chair, None).status_code, 200)
        self.assertFalse(self._active(self.second, "chair_head", self.chair))
        self.chair.refresh_from_db()
        self.assertIsNone(self.chair.head_id)

    def test_tree_assigns_dean_membership_for_a_faculty(self):
        self.assertEqual(self._tree(self.faculty, self.target).status_code, 200)
        self.assertTrue(self._active(self.target, "dean", self.faculty))

    def test_tree_keeps_head_only_for_other_unit_types(self):
        before = Membership.objects.filter(organization=self.org, user=self.target).count()
        self.assertEqual(self._tree(self.specialty, self.target).status_code, 200)
        self.specialty.refresh_from_db()
        self.assertEqual(self.specialty.head_id, self.target.id)
        self.assertEqual(Membership.objects.filter(organization=self.org, user=self.target).count(), before)

    def test_tree_still_requires_a_reason(self):
        url = reverse("organizations:structure_tree_action", kwargs={"slug": self.org.slug})
        response = self._client("teaching_office_head").post(
            url, {"action": "assign_head", "unit": str(self.chair.id), "head": str(self.target.id), "reason": "qısa"}
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(self._active(self.target, "chair_head", self.chair))

    def test_tree_refuses_a_student_for_a_chair(self):
        response = self._tree(self.chair, self.users["student"])
        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.json()["error"], "target_is_student")
        self.chair.refresh_from_db()
        self.assertIsNone(self.chair.head_id)

    def test_registry_path_uses_the_same_service(self):
        response = self._registry(self.chair, self.target)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(self._active(self.target, "chair_head", self.chair))
        # Ağac → reyestr qarışıq ardıcıllıq da tutarlıdır.
        self.assertEqual(self._tree(self.chair, self.second).status_code, 200)
        self.assertFalse(self._active(self.target, "chair_head", self.chair))
        self.assertTrue(self._active(self.second, "chair_head", self.chair))
        self.assertEqual(self._registry(self.faculty, self.second).status_code, 200)
        self.assertTrue(self._active(self.second, "dean", self.faculty))
