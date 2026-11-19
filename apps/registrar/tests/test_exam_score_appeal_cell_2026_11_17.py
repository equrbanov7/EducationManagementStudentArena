"""Sahibin 2026-11-17 tələbləri — imtahan balının daxil edilməsi və apellyasiya səthləri.

1. «İmtahan tarixi», «Nəzarətçi» (və təsdiqdəki yoxlanma tarixi) istəyə bağlıdır.
2. Balı redaktə etmə müddəti 1 saat (``exam.score_edit_minutes`` = 60; saxlanmış sətir də 60).
3. Midterm TƏK sütun, maksimum 30.
4. «Apellyasiyalar» siyahısı qərardan sonra eyni səhifədə qalır (``data-manage-page``).
6. İmtahan balı + «Apellyasiya balı» xanası — apellyasiya balı əsas götürülür (yekun bal, jurnal, transkript eyni).
"""

from __future__ import annotations

import importlib
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from unittest import mock

from django.apps import apps as django_apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.template.loader import get_template
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.registrar import exam_score_appeal as appeal_rules
from apps.registrar import exam_score_assessment as rules
from apps.registrar import exam_score_entry as service
from apps.registrar import exam_score_sheets as sheets
from apps.registrar import finals, gradebook, interim_components
from apps.registrar.models import ComponentScore, ExamAssessment, ExamScoreEntry, ExamScoreEntryKind, FinalGrade
from apps.registrar.tests.test_exam_score_assessment_2026_10_25 import _MEDIA, MidtermPeriodFixture, _pdf
from core.rls import bypass_rls

INT = "10.0.2.50"


@override_settings(UNIVERSITY_MODE=True, MEDIA_ROOT=_MEDIA)
class ExamAppealCellTest(MidtermPeriodFixture, TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            cls.build_fixture("eac")

    # ── köməkçilər ────────────────────────────────────────────────────────────
    def _sheet(self, user, *, assessment=ExamAssessment.FINAL, evidence=None):
        maxes = [30] if assessment == ExamAssessment.MIDTERM else [50]
        return sheets.create_sheet(
            offering=self.offering,
            by_user=user,
            assessment=assessment,
            question_maxes=maxes,
            evidence=evidence,
            checked_on=timezone.localdate(),
        )

    def _save(self, user, rows, *, assessment=ExamAssessment.FINAL, evidence=None):
        return service.save_roster_scores(
            offering=self.offering,
            rows=rows,
            by_user=user,
            sheet=self._sheet(user, assessment=assessment, evidence=evidence),
        )

    def _exam(self, score, enrollment=None):
        return {"enrollment_id": str((enrollment or self.enrollments[0]).pk), "question_scores": [score]}

    def _appeal(self, score, enrollment=None):
        return {
            "enrollment_id": str((enrollment or self.enrollments[0]).pk),
            "score": score,
            "question_scores": None,
            "kind": ExamScoreEntryKind.APPEAL,
            "appeal_cell": True,
        }

    def _final_score(self, enrollment=None):
        return FinalGrade.objects.get(enrollment=enrollment or self.enrollments[0]).exam_score

    def _client(self, user):
        client = Client(REMOTE_ADDR=INT)
        client.force_login(user)
        session = client.session
        session["active_organization"] = self.org.slug
        session.save()
        return client

    # ── 1. tarix / nəzarətçi istəyə bağlı ─────────────────────────────────────
    def test_exam_date_invigilator_and_checked_on_are_optional(self):
        with bypass_rls():
            meta = sheets.sheet_metadata_from_post(
                {"assessment": "final", "question_maxes": "50"}, {}, offering=self.offering
            )
            self.assertIsNone(meta["exam_date"])
            self.assertIsNone(meta["invigilator"])
            self.assertEqual(meta["checked_on"], timezone.localdate())  # boş → bu gün
            sheet = sheets.create_sheet(offering=self.offering, by_user=self.center, **meta)
            result = service.save_roster_scores(
                offering=self.offering, rows=[self._exam("40")], by_user=self.center, sheet=sheet
            )
        self.assertEqual(result["written"], 1, result)

    def test_meta_card_marks_date_and_invigilator_optional(self):
        meta = Path(get_template("accounts/partials/exam_score_entry/_meta.html").origin.name).read_text()
        self.assertIn("istəyə bağlı", meta)
        dialog = Path(get_template("accounts/partials/exam_score_entry/_save_dialog_body.html").origin.name).read_text()
        checked_on = dialog.split('id="ese-checked-on"')[1].split(">")[0]
        self.assertNotIn("required", checked_on)

    # ── 2. 1 saat ─────────────────────────────────────────────────────────────
    def test_edit_window_is_one_hour(self):
        self.assertEqual(rules.edit_window(), timedelta(minutes=60))
        with bypass_rls():
            self._save(self.center, [self._exam("40")])
            with mock.patch("django.utils.timezone.now", return_value=timezone.now() + timedelta(minutes=55)):
                inside = self._save(self.center, [self._exam("42")])
            with mock.patch("django.utils.timezone.now", return_value=timezone.now() + timedelta(minutes=65)):
                outside = self._save(self.center, [self._exam("44")])
            self.assertEqual(inside["written"], 1, inside)
            self.assertEqual(outside["written"], 0)
            self.assertEqual(self._final_score(), Decimal("42"))

    def test_migration_moves_saved_window_to_sixty_minutes(self):
        RuntimeSetting = django_apps.get_model("accounts", "RuntimeSetting")
        RuntimeSetting.objects.update_or_create(key="exam.score_edit_minutes", defaults={"value": 15})
        migration = importlib.import_module("apps.accounts.migrations.0037_exam_score_edit_one_hour_2026_11_17")
        migration.raise_window(django_apps, None)
        self.assertEqual(RuntimeSetting.objects.get(key="exam.score_edit_minutes").value, 60)
        migration.restore_window(django_apps, None)
        self.assertEqual(RuntimeSetting.objects.get(key="exam.score_edit_minutes").value, 15)

    # ── 3. midterm tək sütun ──────────────────────────────────────────────────
    def test_midterm_is_single_thirty_point_column(self):
        self.assertEqual(rules.default_columns(rules.MIDTERM, 30), [30])
        with bypass_rls():
            old = sheets.create_sheet(
                offering=self.offering,
                by_user=self.center,
                assessment=ExamAssessment.MIDTERM,
                question_maxes=[10, 10, 10],
                checked_on=timezone.localdate(),
            )
            defaults = sheets.latest_sheet_defaults([sheets.sheet_row(old)], assessment=ExamAssessment.MIDTERM, cap=30)
            self.assertEqual(defaults["question_maxes"], [30])  # köhnə 3 × 10 miras qalmır
            with self.assertRaisesMessage(ValidationError, "Midterm tək sütundur"):
                sheets.sheet_metadata_from_post(
                    {"assessment": "midterm", "question_maxes": "10,10,10"}, {}, offering=self.offering
                )
            meta = sheets.sheet_metadata_from_post(
                {"assessment": "midterm", "question_maxes": "30"}, {}, offering=self.offering
            )
        self.assertEqual(meta["question_maxes"], [30])

    # ── 4. apellyasiya siyahısı səhifədə qalır ────────────────────────────────
    def test_manage_appeals_reload_keeps_current_page(self):
        body = Path(get_template("appeals/partials/_manage_appeals_body.html").origin.name).read_text()
        self.assertIn('data-manage-page="{{ appeal_page_obj.number }}"', body)
        script = (Path(settings.BASE_DIR) / "apps/appeals/static/appeals/js/appeals_sections.js").read_text()
        reload_query = script.split("function listQueryFromLocation(panel)")[1].split("function reloadManageList")[0]
        self.assertIn('p.set("page", page)', reload_query)
        self.assertIn("listQueryFromLocation(panel)", script)

    # ── 6. iki xana: apellyasiya üstündür ─────────────────────────────────────
    def test_appeal_cell_becomes_final_exam_score(self):
        with bypass_rls():
            self._save(self.center, [self._exam("30")])
            result = self._save(self.center, [self._appeal("38")], evidence=_pdf())
            self.assertEqual(result["written"], 1, result)
            self.assertEqual(self._final_score(), Decimal("38"))
            entry = ExamScoreEntry.objects.get(kind=ExamScoreEntryKind.APPEAL)
            self.assertEqual((entry.old_score, entry.new_score), (Decimal("30"), Decimal("38")))
            scheme = gradebook.ensure_assessment_scheme(offering=self.offering)
            computed = finals.compute_final_result(enrollment=self.enrollments[0], scheme=scheme)
            self.assertEqual(computed["exam_score"], Decimal("38"))  # yekun / transkript eyni balı görür
            roster = service.roster_for_offering(offering=self.offering)
            row = next(r for r in roster["rows"] if r["enrollment"].pk == self.enrollments[0].pk)
            appeal_rules.attach_row(row)
            self.assertTrue(row["appeal_set"])
            self.assertEqual((row["exam_base_display"], row["appeal_display"]), ("30", "38"))

    def test_exam_cell_cannot_change_after_appeal(self):
        with bypass_rls():
            self._save(self.center, [self._exam("30")])
            self._save(self.center, [self._appeal("38")], evidence=_pdf())
            # Pəncərə (1 saat) hələ açıqdır, amma apellyasiya balı var → imtahan xanası dəyişmir.
            changed = self._save(self.center, [self._exam("33")])
            self.assertEqual(changed["written"], 0)
            self.assertIn("apellyasiya balı var", changed["errors"][0][1])
            same = self._save(self.center, [{"enrollment_id": str(self.enrollments[0].pk), "score": "38"}])
            self.assertEqual((same["written"], same["failed"]), (0, 0))  # köhnə forma/idxal: eyni bal səssiz
            self.assertEqual(self._final_score(), Decimal("38"))

    @mock.patch("apps.registrar.exam_score_assessment.appeal_document_required", new=lambda: True)
    def test_appeal_cell_needs_appeal_role_and_document(self):
        with bypass_rls():
            self._save(self.center, [self._exam("30")])
            no_doc = self._save(self.center, [self._appeal("38")])
            self.assertIn("apellyasiya sənədi", no_doc["errors"][0][1])
            teacher = self._save(self.teacher, [self._appeal("38")], evidence=_pdf())
            self.assertIn("işçisi yazır", teacher["errors"][0][1])
            self.assertEqual(self._final_score(), Decimal("30"))
            self.assertFalse(ExamScoreEntry.objects.filter(kind=ExamScoreEntryKind.APPEAL).exists())
            # Sahib 2026-11-18: İmtahan Mərkəzinin işçisi də apellyasiya balını yazır.
            staff = self._save(self.staff, [self._appeal("38")], evidence=_pdf())
            self.assertEqual(staff["written"], 1, staff)
            self.assertEqual(self._final_score(), Decimal("38"))

    def test_appeal_cell_document_is_optional_by_default(self):
        """Sahib 2026-11-19: «sənəd yükləməyə ehtiyac olmasın, indilik opsional olsun» — açar söndürülü (defolt)."""
        with bypass_rls():
            self._save(self.center, [self._exam("30")])
            result = self._save(self.staff, [self._appeal("38")])
            self.assertEqual((result["written"], result["failed"]), (1, 0), result)
            self.assertEqual(self._final_score(), Decimal("38"))
            self.assertTrue(ExamScoreEntry.objects.filter(kind=ExamScoreEntryKind.APPEAL).exists())

    @mock.patch("apps.registrar.exam_score_assessment.appeal_document_required", new=lambda: True)
    def test_appeal_cell_on_student_without_exam_score(self):
        """Sahib 2026-11-18: imtahan balı yazılmamış tələbəyə də apellyasiya balı yazılır (sənəd yenə məcburi)."""
        second = self.enrollments[1]
        with bypass_rls():
            no_doc = self._save(self.staff, [self._appeal("20", second)])
            self.assertIn("apellyasiya sənədi", no_doc["errors"][0][1])
            self.assertFalse(FinalGrade.objects.filter(enrollment=second, exam_score__isnull=False).exists())
            result = self._save(self.staff, [self._appeal("20", second)], evidence=_pdf())
            self.assertEqual(result["written"], 1, result)
            self.assertEqual(self._final_score(second), Decimal("20"))
            entry = ExamScoreEntry.objects.get(enrollment=second)
            self.assertEqual(
                (entry.kind, entry.old_score, entry.new_score), (ExamScoreEntryKind.APPEAL, None, Decimal("20"))
            )
            roster = service.roster_for_offering(offering=self.offering)
            row = next(r for r in roster["rows"] if r["enrollment"].pk == second.pk)
            appeal_rules.attach_row(row)
            self.assertTrue(row["appeal_set"])
            self.assertEqual((row["exam_base_display"], row["appeal_display"]), ("", "20"))
            # İmtahan xanası sonradan dəyişmir — yekun bal apellyasiyadır.
            changed = self._save(self.staff, [self._exam("33", second)])
            self.assertIn("apellyasiya balı var", changed["errors"][0][1])

    def test_midterm_appeal_cell_without_midterm_score(self):
        second = self.enrollments[1]
        with bypass_rls():
            result = self._save(
                self.rim, [self._appeal("24", second)], assessment=ExamAssessment.MIDTERM, evidence=_pdf()
            )
            self.assertEqual(result["written"], 1, result)
            component = interim_components.ensure_kollokviums(self.offering)[0]
            cell = ComponentScore.objects.get(component=component, enrollment=second)
            self.assertEqual(cell.score, Decimal("24"))

    def test_staff_screen_opens_appeal_cell_on_empty_rows(self):
        from apps.organizations.models import Role

        with bypass_rls():
            role = Role.objects.get(organization=self.org, name="exam_center_staff")
            if "final_score.entry" not in role.permissions:
                role.permissions = list(role.permissions) + ["final_score.entry"]
                role.save(update_fields=["permissions"])
        page = self._client(self.staff).get(
            reverse("accounts:profile"),
            {"section": "exam-score-entry", "ese_offering": str(self.offering.pk), "ese_assessment": "final"},
        )
        self.assertEqual(page.status_code, 200)
        html = page.content.decode()
        for enrollment in self.enrollments:
            cell = html.split(f'name="appeal__{enrollment.pk}"')[1].split(">")[0]
            self.assertNotIn("disabled", cell)

    def test_unchanged_appeal_value_is_not_rewritten(self):
        with bypass_rls():
            self._save(self.center, [self._exam("30")])
            self._save(self.center, [self._appeal("38")], evidence=_pdf())
            again = self._save(self.center, [self._appeal("38")], evidence=_pdf())
            self.assertEqual((again["written"], again["failed"], again["skipped"]), (0, 0, 0))
            lowered = self._save(self.center, [self._appeal("35")], evidence=_pdf())
            self.assertEqual(lowered["written"], 1, lowered)
            self.assertEqual(self._final_score(), Decimal("35"))
            self.assertEqual(ExamScoreEntry.objects.filter(kind=ExamScoreEntryKind.APPEAL).count(), 2)

    def test_midterm_appeal_cell_writes_journal_midterm(self):
        with bypass_rls():
            self._save(self.center, [self._exam("18")], assessment=ExamAssessment.MIDTERM)
            result = self._save(self.center, [self._appeal("24")], assessment=ExamAssessment.MIDTERM, evidence=_pdf())
            self.assertEqual(result["written"], 1, result)
            component = interim_components.ensure_kollokviums(self.offering)[0]
            cell = ComponentScore.objects.get(component=component, enrollment=self.enrollments[0])
            self.assertEqual(cell.score, Decimal("24"))
            entry = ExamScoreEntry.objects.get(kind=ExamScoreEntryKind.APPEAL)
            self.assertEqual(entry.assessment, ExamAssessment.MIDTERM)

    def test_split_entries_handles_digital_appeal_chain(self):
        appeal_only = [{"kind": "appeal", "old": "30", "new": "35"}]
        self.assertEqual(appeal_rules.split_entries(appeal_only), ("30", "35"))
        mixed = [
            {"kind": "appeal", "old": "36", "new": "40"},
            {"kind": "appeal", "old": "30", "new": "36"},
            {"kind": "window_edit", "old": "28", "new": "30"},
        ]
        self.assertEqual(appeal_rules.split_entries(mixed), ("30", "40"))
        self.assertEqual(appeal_rules.split_entries([{"kind": "initial", "old": "—", "new": "30"}]), (None, None))

    def test_screen_post_with_appeal_field_and_two_cells(self):
        enrollment = self.enrollments[0]
        client = self._client(self.center)
        base = {
            "action": "save_scores",
            "offering_id": str(self.offering.pk),
            "assessment": "final",
            "question_maxes": "50",
            f"score__{enrollment.pk}": "",
            f"q__{enrollment.pk}__1": "30",
        }
        self.assertEqual(client.post(reverse("accounts:exam_score_entry"), base).status_code, 302)
        response = client.post(
            reverse("accounts:exam_score_entry"),
            {**base, f"appeal__{enrollment.pk}": "41", "justification_evidence": _pdf()},
        )
        self.assertEqual(response.status_code, 302)
        with bypass_rls():
            self.assertEqual(self._final_score(), Decimal("41"))
        page = client.get(
            reverse("accounts:profile"),
            {"section": "exam-score-entry", "ese_offering": str(self.offering.pk), "ese_assessment": "final"},
        ).content.decode()
        self.assertIn("Apellyasiya balı", page)
        self.assertIn(f'name="appeal__{enrollment.pk}"', page)
        appeal_input = page.split(f'name="appeal__{enrollment.pk}"')[1].split(">")[0]
        self.assertIn('data-initial="41"', appeal_input)  # 2026-11-18: seçim (select), dəyər seçilmiş variantdadır
        self.assertNotIn("disabled", appeal_input)
        self.assertIn('<option value="41" selected>41</option>', page)
        # Sahib 2026-11-18: sütun sırası — S… | Apellyasiya balı | İmtahan balı (yekun), yekun xana apellyasiyanı göstərir.
        head = page.split('class="ems-table ems-table--zebra ese-table"')[1].split("</thead>")[0]
        self.assertLess(head.index("Apellyasiya balı"), head.index("İmtahan balı"))
        final_cell = page.split(f'name="score__{enrollment.pk}"')[1].split("</td>")[0]
        self.assertIn("data-ese-effective", final_cell)
        self.assertIn(">41</output>", final_cell)
        self.assertIn(
            "has-appeal", page.split(f'name="appeal__{enrollment.pk}"')[1].split(f'name="score__{enrollment.pk}"')[0]
        )
        score_input = page.split(f'name="score__{enrollment.pk}"')[1].split(">")[0]
        self.assertIn('value="30"', score_input)  # imtahan xanası apellyasiyadan əvvəlki bal
        self.assertIn("disabled", score_input)

    # ── 5. «Excel» şablonu həmişə .xlsx (HTML/JSON xəta faylı yox) ───────────
    def test_midterm_template_downloads_xlsx_with_single_thirty_column(self):
        client = self._client(self.center)
        response = client.get(
            reverse("accounts:exam_score_import_template"),
            {
                "offering": str(self.offering.pk),
                "assessment": "midterm",
                "question_count": "1",
                "question_max": "30",  # köhnə «≤ 10» qaydası bunu 400 ilə rədd edirdi
                "question_maxes": "30",
                "exam_kind": "written",
            },
        )
        self.assertEqual(response.status_code, 200, response.content[:300])
        self.assertEqual(response["Content-Type"], "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        self.assertRegex(response["Content-Disposition"], r'^attachment; filename="[A-Za-z0-9_-]+\.xlsx"$')
        self.assertTrue(response.content.startswith(b"PK"))  # zip (xlsx), HTML deyil

    def test_midterm_import_preview_uses_midterm_cap(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        client = self._client(self.center)
        template = client.get(
            reverse("accounts:exam_score_import_template"),
            {"offering": str(self.offering.pk), "format": "csv", "assessment": "midterm", "question_maxes": "30"},
        )
        self.assertEqual(template.status_code, 200)
        lines = template.content.decode("utf-8-sig").splitlines()
        header, first = lines[0].split(","), lines[1].split(",")
        self.assertIn("Bal (0–30)", header)
        first[header.index("Bal (0–30)")] = "27"
        csv_bytes = ("\n".join([",".join(header), ",".join(first)]) + "\n").encode("utf-8")
        response = client.post(
            reverse("accounts:exam_score_import_preview"),
            {
                "offering_id": str(self.offering.pk),
                "assessment": "midterm",
                "question_count": "1",
                "question_max": "30",
                "question_maxes": "30",
                "file": SimpleUploadedFile("m.csv", csv_bytes, content_type="text/csv"),
            },
        )
        self.assertEqual(response.status_code, 200, response.content[:400])
        self.assertTrue(response.json()["ok"])
