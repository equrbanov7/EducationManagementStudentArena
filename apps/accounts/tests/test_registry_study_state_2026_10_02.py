"""Sahib 2026-10-02: «aktiv oxuyanları və məzunları tapa bilim — hamını aktiv göstərməsin» +
«parolunu bərpa etmiş tələbələrin sayını görüm».

Köçürmədə bütün akademik qeydlər «enrolled» qaldı; reyestr indi HESABLANAN vəziyyəti göstərir
(rəsmi status dəyişmir): oxuyur / oxu müddəti bitib / arxiv (məzun və ya xaric) / qəbul ili bilinmir /
rəsmi məzun-xaric-məzuniyyət. Hesab: öz parolunu qurub (aktivləşdirib) / hələ ilkin parolda.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model

from apps.accounts.services.people.study_state import UNKNOWN_ADMISSION_YEAR, current_academic_year_start
from apps.organizations.models import Membership
from apps.registrar.models import AcademicStatus, Curriculum, StudentAcademicRecord

from .test_student_services_sections import PASSWORD, StudentServicesBase

User = get_user_model()


class RegistryStudyStateTest(StudentServicesBase):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        year_start = current_academic_year_start()
        cls.cases = {}

        def make(name, *, admission_year, status=AcademicStatus.ENROLLED, archived=False, activated=False):
            user = User.objects.create_user(f"st_{name}", f"st_{name}@qku.edu.az", PASSWORD)
            Membership.objects.create(
                user=user, organization=cls.org, role=cls.student_role, is_primary=True, is_active=True
            )
            curriculum, _ = Curriculum.objects.get_or_create(
                organization=cls.org,
                program=cls.program,
                admission_year=admission_year,
                defaults={"name": f"plan {admission_year}"},
            )
            StudentAcademicRecord.objects.create(
                organization=cls.org,
                student=user,
                program=cls.program,
                curriculum=curriculum,
                group=cls.group_b,
                admission_year=admission_year,
                status=status,
            )
            profile = user.profile
            profile.password_change_required = not activated
            profile.email_verified = activated
            if archived:
                profile.access_state = "archived"
            profile.save()
            cls.cases[name] = user

        make("current", admission_year=year_start - 1, activated=True)
        make("ended", admission_year=year_start - 4)  # 4 illik bakalavr: müddət bitib
        make("archived", admission_year=year_start - 2, archived=True)
        make("unknown", admission_year=UNKNOWN_ADMISSION_YEAR)
        make("graduated", admission_year=year_start - 5, status=AcademicStatus.GRADUATED)

    def _section(self, **params):
        response = self._fragment("student_services", "student-registry", **params)
        self.assertEqual(response.status_code, 200)
        return response.context["student_registry_section"]

    def _states(self, section):
        return {row["data"]["user_id"]: row["data"]["study_state"] for row in section["table_rows"]}

    def test_states_are_computed_and_not_everyone_is_active(self):
        section = self._section()
        states = self._states(section)
        expected = {
            self.cases["current"].pk: "studying",
            self.cases["ended"].pk: "period_ended",
            self.cases["archived"].pk: "archived",
            self.cases["unknown"].pk: "year_unknown",
            self.cases["graduated"].pk: "graduated",
        }
        for user_id, state in expected.items():
            self.assertEqual(states[user_id], state, user_id)
        badge_keys = {cell.get("badge_key") for row in section["table_rows"] for cell in row["cells"]}
        self.assertIn("period_ended", badge_keys)
        tiles = {tile["filter"]: tile["value"] for tile in section["state_tiles"]}
        self.assertGreaterEqual(tiles["studying"], 1)
        self.assertEqual(tiles["period_ended"], 1)
        self.assertEqual(tiles["archived"], 1)
        self.assertEqual(tiles["year_unknown"], 1)

    def test_state_filter_returns_only_that_state_and_tiles_still_count_all(self):
        section = self._section(sr_state="period_ended")
        self.assertEqual({row["data"]["study_state"] for row in section["table_rows"]}, {"period_ended"})
        tiles = {tile["filter"]: tile for tile in section["state_tiles"]}
        self.assertTrue(tiles["period_ended"]["pressed"])
        self.assertEqual(tiles["archived"]["value"], 1)  # plitələr vəziyyət filtrindən əvvəl sayılır

    def test_account_activation_counts_and_filter(self):
        section = self._section()
        tiles = {tile["filter"]: tile["value"] for tile in section["account_tiles"]}
        self.assertEqual(tiles["account:activated"], 1)
        self.assertGreaterEqual(tiles["account:initial"], 3)
        only_activated = self._section(sr_account="activated")
        self.assertEqual({row["data"]["user_id"] for row in only_activated["table_rows"]}, {self.cases["current"].pk})

    def test_invalid_filter_values_are_ignored(self):
        section = self._section(sr_state="drop table", sr_account="x")
        self.assertGreaterEqual(len(section["table_rows"]), 5)
