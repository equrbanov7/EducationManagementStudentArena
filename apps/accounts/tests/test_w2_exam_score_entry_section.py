"""W2 `w2paper` (2026-09-14) — «İmtahan balının daxil edilməsi» bölməsi: sual balları, filtrlər, «Dəyişən nəticələr».

Sahibin tələbi: «qrupu seçib balları yazmaq; filter, search, müəllim seçmək və
s. — hər şey orada; apellyasiyadan sonra DƏYİŞƏN nəticələrin izlənməsi; max
bal 50 / sualdan 10 / yekun 100 — hamısına nəzarət.» Burada yoxlanır:

* siyahı S1..S10 sahələri ilə render olunur (sual sayı vərəq kartında);
* POST ``q__<enr>__n`` → server cəmi yazır (``score__`` nəzərə alınmır),
  pozuntu (sual > 10, cəm > 50, sayı > vərəq) sətri rədd edir;
* dialoqdan gələn ``kind=appeal`` sətrin növü olur;
* müəllim seçici / tələbə axtarışı / vəziyyət çipləri;
* ``?ese_view=changes`` cədvəli + CSV ixracı; müəllim/tələbə 403;
* sorğu büdcəsi: siyahı və «dəyişən nəticələr» sətir sayından asılı deyil
  (5 və 60 tələbə → eyni sorğu sayı).
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.accounts.tests import test_exam_score_entry_section as fixtures
from apps.organizations.models import Membership
from apps.registrar import exam_score_entry as service
from apps.registrar.models import CorrectionReason, Enrollment, ExamScoreEntry, ExamScoreEntryKind, FinalGrade
from apps.registrar.models.exam_score_entry import ExamScoreSheetKind
from core.rls import bypass_rls

User = get_user_model()

PROFILE = "accounts:profile"
SECTION = "exam-score-entry"


#: Etiket kataloqdan gəlir (fill skripti işlədilməmiş ola bilər) — literal yox.
PRACTICAL_LABEL = str(ExamScoreSheetKind.PRACTICAL.label)


def _pdf(name="teqdimat.pdf"):
    return SimpleUploadedFile(name, b"%PDF-1.4\n%%EOF\n", content_type="application/pdf")


@override_settings(UNIVERSITY_MODE=True, MEDIA_ROOT=fixtures._MEDIA)
class W2ExamScoreEntrySectionTest(fixtures.ExamScoreEntrySectionTest):
    """Mövcud fixture (bir qrup, bir tələbə, imtahan mərkəzi rəhbəri) üzərində."""

    def _get(self, client, **params):
        return client.get(reverse(PROFILE), {"section": SECTION, "ese_offering": str(self.offering.id), **params})

    def _save(self, client, questions=None, score=None, **extra):
        payload = {"action": "save_scores", "offering_id": str(self.offering.id), "question_count": "5"}
        payload[f"score__{self.enrollment.id}"] = "" if score is None else score
        for index, value in enumerate(questions or [], start=1):
            payload[f"q__{self.enrollment.id}__{index}"] = value
        payload.update(extra)
        return client.post(reverse(fixtures.SECTION_URL_NAME), payload)

    def _exam_score(self):
        with bypass_rls():
            grade = FinalGrade.objects.filter(enrollment=self.enrollment).first()
        return grade.exam_score if grade is not None else None

    # ── render ───────────────────────────────────────────────────────────────
    def test_roster_renders_question_inputs_and_grid_controls(self):
        resp = self._get(self._client(self.center))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, f'name="q__{self.enrollment.id}__1"')
        self.assertContains(resp, f'name="q__{self.enrollment.id}__10"')
        self.assertContains(resp, "data-ese-question-count")
        self.assertContains(resp, "data-ese-question-max")
        self.assertContains(resp, 'name="ese_teacher"')
        self.assertContains(resp, 'name="ese_q"')
        self.assertContains(resp, "data-ese-kind")
        self.assertContains(resp, "ese_view=changes")
        # Defolt 5 sual → 6-cı sütun gizli və söndürülüb, yekun sahəsi yalnız-oxunan.
        self.assertContains(resp, 'data-ese-qcell="6" hidden')
        self.assertContains(resp, 'data-ese-qcol="5">S5')
        self.assertContains(resp, "readonly")

    # ── yazı ─────────────────────────────────────────────────────────────────
    def test_question_scores_are_summed_by_server(self):
        client = self._client(self.center)
        resp = self._save(client, questions=["10", "8", "", "7", "5"], score="999")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self._exam_score(), Decimal(30))
        with bypass_rls():
            entry = ExamScoreEntry.objects.get(enrollment=self.enrollment)
            self.assertEqual(entry.question_scores, [10, 8, 0, 7, 5])
            self.assertEqual(entry.sheet.question_count, 5)
            self.assertEqual(entry.sheet.question_max, 10)

    def test_question_above_max_is_rejected(self):
        resp = self._save(self._client(self.center), questions=["11", "1"])
        self.assertEqual(resp.status_code, 302)
        self.assertIsNone(self._exam_score())

    def test_sum_above_cap_is_rejected_even_with_ten_questions(self):
        client = self._client(self.center)
        payload = {"question_count": "10"}
        resp = self._save(client, questions=["10"] * 6, **payload)
        self.assertEqual(resp.status_code, 302)
        self.assertIsNone(self._exam_score())

    def test_more_questions_than_sheet_count_is_rejected(self):
        resp = self._save(self._client(self.center), questions=["1", "1", "1"], question_count="2")
        self.assertEqual(resp.status_code, 302)
        self.assertIsNone(self._exam_score())

    def test_invalid_grid_is_rejected_before_sheet(self):
        resp = self._save(self._client(self.center), questions=["1"], question_count="11")
        self.assertEqual(resp.status_code, 302)
        self.assertIsNone(self._exam_score())
        with bypass_rls():
            self.assertFalse(self.offering.exam_score_sheets.exists())

    def test_zero_questions_keeps_single_total_mode(self):
        resp = self._save(self._client(self.center), score="42", question_count="0")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self._exam_score(), Decimal(42))

    def test_change_dialog_kind_appeal_is_recorded(self):
        client = self._client(self.center)
        self._save(client, questions=["10", "10"])
        resp = self._save(
            client,
            questions=["10", "10", "5"],
            kind="appeal",
            reason=CorrectionReason.APPEAL,
            note="komissiya",
            sheet_evidence=_pdf(),
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self._exam_score(), Decimal(25))
        with bypass_rls():
            latest = ExamScoreEntry.objects.filter(enrollment=self.enrollment).order_by("-created_at").first()
            self.assertEqual(latest.kind, ExamScoreEntryKind.APPEAL)

    def test_teacher_cannot_post_question_scores(self):
        resp = self._save(self._client(self.teacher), questions=["10"])
        self.assertEqual(resp.status_code, 403)
        self.assertIsNone(self._exam_score())

    # ── filtrlər ─────────────────────────────────────────────────────────────
    def test_teacher_filter_narrows_offerings(self):
        client = self._client(self.center)
        resp = self._get(client, ese_teacher=str(self.teacher.id))
        self.assertContains(resp, f"score__{self.enrollment.id}")
        with bypass_rls():
            other = User.objects.create_user("w2_other_t", "w2_other_t@qku.edu.az", "pw")
            Membership.objects.create(
                user=other,
                organization=self.org,
                role=self.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )
        resp = self._get(client, ese_teacher=str(other.id))
        # Müəllimin bu dövrdə açılışı yoxdur → seçici onu tanımır → filtr düşür (hamısı).
        self.assertContains(resp, f"score__{self.enrollment.id}")

    def test_student_search_and_status_chips(self):
        client = self._client(self.center)
        resp = self._get(client, ese_q="yoxdur-bele-telebe")
        self.assertNotContains(resp, f"score__{self.enrollment.id}")
        self.assertContains(resp, "Bu filtrə uyğun tələbə yoxdur.")
        resp = self._get(client, ese_q=self.student.username[:6])
        self.assertContains(resp, f"score__{self.enrollment.id}")
        resp = self._get(client, ese_status="recorded")
        self.assertNotContains(resp, f"score__{self.enrollment.id}")
        self._save(client, questions=["10"])
        resp = self._get(client, ese_status="recorded")
        self.assertContains(resp, f"score__{self.enrollment.id}")
        resp = self._get(client, ese_status="changed")
        self.assertNotContains(resp, f"score__{self.enrollment.id}")
        self.assertContains(resp, 'aria-pressed="true"')

    # ── «Dəyişən nəticələr» ──────────────────────────────────────────────────
    def _make_change(self, client):
        self._save(client, questions=["10", "10"])
        self._save(
            client,
            questions=["10", "5"],
            kind="appeal",
            reason=CorrectionReason.APPEAL,
            note="apellyasiya qərarı",
            sheet_evidence=_pdf(),
        )

    def test_changes_view_lists_non_initial_entries(self):
        client = self._client(self.center)
        resp = client.get(reverse(PROFILE), {"section": SECTION, "ese_view": "changes"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Bu filtrə uyğun dəyişiklik yoxdur.")
        self._make_change(client)
        resp = client.get(reverse(PROFILE), {"section": SECTION, "ese_view": "changes"})
        self.assertContains(resp, "ese-changes__row is-appeal")
        self.assertContains(resp, "20 → <b>15</b>")
        self.assertContains(resp, "apellyasiya qərarı")
        self.assertContains(resp, 'name="ese_kind"')
        self.assertContains(resp, 'name="ese_from"')
        self.assertContains(resp, reverse("accounts:exam_score_changes_export"))
        resp = client.get(reverse(PROFILE), {"section": SECTION, "ese_view": "changes", "ese_kind": "correction"})
        self.assertNotContains(resp, "ese-changes__row is-appeal")

    def test_changes_csv_export_and_permissions(self):
        client = self._client(self.center)
        self._make_change(client)
        url = reverse("accounts:exam_score_changes_export")
        resp = client.get(url, {"ese_period": str(self.period.id), "ese_year": self.period.year_display})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/csv", resp["Content-Type"])
        body = resp.content.decode("utf-8-sig")
        self.assertIn("apellyasiya qərarı", body)
        self.assertIn(",20,15,", body)
        self.assertEqual(len(body.strip().splitlines()), 2)
        resp = client.get(url, {"ese_period": str(self.period.id), "ese_kind": "correction"})
        self.assertEqual(len(resp.content.decode("utf-8-sig").strip().splitlines()), 1)
        self.assertEqual(self._client(self.teacher).get(url).status_code, 403)
        self.assertEqual(self._client(self.student).get(url).status_code, 403)

    def test_changes_view_hidden_from_teacher(self):
        resp = self._client(self.teacher).get(reverse(PROFILE), {"section": SECTION, "ese_view": "changes"})
        self.assertNotContains(resp, 'data-profile-section-panel="exam-score-entry"')

    # ── sorğu büdcəsi ────────────────────────────────────────────────────────
    def _add_students(self, count, start=0):
        with bypass_rls():
            role = self.org.roles.get(name="student")
            for index in range(start, start + count):
                user = User.objects.create_user(f"w2_bulk_{index}", f"w2_bulk_{index}@qku.edu.az", "pw")
                Membership.objects.create(user=user, organization=self.org, role=role, is_primary=True, is_active=True)
                Enrollment.objects.create(organization=self.org, student=user, offering=self.offering)

    def _count_queries(self, client, **params):
        # İlk sorğu keşləri (rol/icazə, təşkilat) isidir — ölçmə ikinci çağırışdır.
        client.get(reverse(PROFILE), {"section": SECTION, "ese_offering": str(self.offering.id), **params})
        with CaptureQueriesContext(connection) as ctx:
            resp = client.get(reverse(PROFILE), {"section": SECTION, "ese_offering": str(self.offering.id), **params})
        self.assertEqual(resp.status_code, 200)
        return len(ctx.captured_queries), resp

    def test_roster_query_budget_is_independent_of_roster_size(self):
        client = self._client(self.center)
        self._add_students(4)
        small, resp = self._count_queries(client, ese_q="w2_bulk")
        self.assertContains(resp, "w2_bulk_3")
        self._add_students(55, start=4)
        big, resp = self._count_queries(client, ese_q="w2_bulk")
        self.assertContains(resp, "w2_bulk_58")
        self.assertEqual(big, small, f"siyahı sorğu büdcəsi sətir sayından asılıdır: 5 → {small}, 60 → {big}")

    def test_changes_query_budget_is_independent_of_row_count(self):
        client = self._client(self.center)
        self._add_students(4)
        with bypass_rls():
            enrollments = list(Enrollment.objects.filter(offering=self.offering).order_by("student__username"))
            sheet = None
            for enrollment in enrollments[:2]:
                service.record_exam_score(enrollment=enrollment, score="30", by_user=self.center, sheet=sheet)
                service.record_exam_score(
                    enrollment=enrollment,
                    score="31",
                    by_user=self.center,
                    reason=CorrectionReason.TECHNICAL,
                    note="düzəliş",
                    evidence=_pdf(),
                    kind="correction",
                )
        small, _resp = self._count_queries(client, ese_view="changes")
        with bypass_rls():
            for enrollment in enrollments[2:]:
                service.record_exam_score(enrollment=enrollment, score="30", by_user=self.center)
                service.record_exam_score(
                    enrollment=enrollment,
                    score="32",
                    by_user=self.center,
                    reason=CorrectionReason.APPEAL,
                    note="apellyasiya",
                    evidence=_pdf(),
                    kind="appeal",
                )
        big, resp = self._count_queries(client, ese_view="changes")
        self.assertContains(resp, "ese-changes__row is-appeal")
        self.assertEqual(big, small, f"dəyişikliklər sorğu büdcəsi sətir sayından asılıdır: {small} → {big}")

    # ── ADDENDUM 2026-09-14: imtahan növü (yazılı / praktiki) ─────────────────
    def test_exam_kind_is_stored_and_invalid_kind_is_rejected(self):
        client = self._client(self.center)
        resp = self._save(client, questions=["10", "5"], exam_kind="practical")
        self.assertEqual(resp.status_code, 302)
        with bypass_rls():
            sheet = self.offering.exam_score_sheets.get()
            self.assertEqual(sheet.exam_kind, "practical")
        resp = self._get(client)
        self.assertContains(resp, 'name="exam_kind"')
        self.assertContains(resp, 'value="practical" selected')  # sonuncu vərəqdən defolt
        self.assertContains(resp, PRACTICAL_LABEL)
        # Yad növ → xəta, vərəq yaranmır, bal yazılmır.
        resp = self._save(client, questions=["10", "6"], exam_kind="oral")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self._exam_score(), Decimal(15))
        with bypass_rls():
            self.assertEqual(self.offering.exam_score_sheets.count(), 1)

    def test_sheet_kind_chips_filter_sheet_list(self):
        client = self._client(self.center)
        self._save(client, questions=["10"], exam_kind="written")
        self._save(
            client,
            questions=["10", "2"],
            exam_kind="practical",
            kind="correction",
            reason=CorrectionReason.TECHNICAL,
            note="praktiki vərəq",
            sheet_evidence=_pdf(),
        )
        resp = self._get(client, ese_sheet_kind="practical")
        self.assertContains(resp, "ese_sheet_kind=practical")
        self.assertContains(resp, "1 / 2")  # süzülmüş / cəmi
        resp = self._get(client, ese_sheet_kind="written")
        self.assertContains(resp, "1 / 2")
        resp = self._get(client)
        self.assertNotContains(resp, "1 / 2")

    def test_changes_exam_kind_filter_and_csv_column(self):
        client = self._client(self.center)
        self._save(client, questions=["10", "10"], exam_kind="practical")
        self._save(
            client,
            questions=["10", "5"],
            exam_kind="practical",
            kind="appeal",
            reason=CorrectionReason.APPEAL,
            note="praktiki apellyasiya",
            sheet_evidence=_pdf(),
        )
        base = {"section": SECTION, "ese_view": "changes"}
        resp = client.get(reverse(PROFILE), {**base, "ese_exam_kind": "practical"})
        self.assertContains(resp, "praktiki apellyasiya")
        self.assertContains(resp, PRACTICAL_LABEL)
        resp = client.get(reverse(PROFILE), {**base, "ese_exam_kind": "written"})
        self.assertNotContains(resp, "praktiki apellyasiya")
        url = reverse("accounts:exam_score_changes_export")
        resp = client.get(url, {"ese_period": str(self.period.id), "ese_exam_kind": "practical"})
        body = resp.content.decode("utf-8-sig")
        self.assertIn("İmtahan növü", body.splitlines()[0])
        self.assertIn(f",{PRACTICAL_LABEL},", body)
        resp = client.get(url, {"ese_period": str(self.period.id), "ese_exam_kind": "written"})
        self.assertEqual(len(resp.content.decode("utf-8-sig").strip().splitlines()), 1)

    # ── ADDENDUM: RİM rəhbəri (ikt_rehber, org-wide) bölməni görür və yazır ───
    def test_rim_head_sees_section_and_saves_scores(self):
        with bypass_rls():
            rim = User.objects.create_user("w2_rim_head", "w2_rim_head@qku.edu.az", "pw")
            role = self.org.roles.get(name="ikt_rehber")
            permissions = list(role.permissions or [])
            # 2026-09-14: RİM tam wildcard (`*`) daşıyır.
            self.assertTrue("final_score.entry" in permissions or "*" in permissions)
            Membership.objects.create(user=rim, organization=self.org, role=role, is_primary=True, is_active=True)
        client = self._client(rim)
        resp = client.get(reverse(PROFILE), {"section": SECTION})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'data-profile-section-panel="exam-score-entry"')
        self.assertContains(resp, "data-ese-root")
        resp = self._save(client, questions=["9", "8", "7"], exam_kind="written")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self._exam_score(), Decimal(24))
        resp = client.get(reverse(PROFILE), {"section": SECTION, "ese_view": "changes"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "ese-changes")

    # ── ADDENDUM: imtahan mərkəzi statistikası — kağız imtahan KPI-ları ──────
    def test_exam_center_stats_paper_kpi_by_kind(self):
        client = self._client(self.center)
        self._save(client, questions=["10", "10"], exam_kind="practical")
        self._save(
            client,
            questions=["10", "5"],
            exam_kind="practical",
            kind="appeal",
            reason=CorrectionReason.APPEAL,
            note="apellyasiya",
            sheet_evidence=_pdf(),
        )
        url = reverse("exams:exam_center_stats_data")
        resp = client.get(url, {"paper": "1"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(resp.status_code, 200)
        paper = {row["kind"]: row for row in resp.json()["paper"]}
        self.assertEqual(set(paper), {"written", "practical"})
        self.assertEqual((paper["practical"]["sheets"], paper["practical"]["entries"]), (2, 2))
        self.assertEqual(paper["practical"]["changes"], 1)
        self.assertEqual(paper["practical"]["avg"], 15.0)  # sonuncu daxiletmə (20 → 15)
        self.assertEqual((paper["written"]["sheets"], paper["written"]["entries"]), (0, 0))
        resp = client.get(url, {"paper": "1", "paper_kind": "written"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual([row["kind"] for row in resp.json()["paper"]], ["written"])
        resp = client.get(url, {"paper": "1", "year": "1999"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(sum(row["entries"] for row in resp.json()["paper"]), 0)
        # Tam cavabda da eyni blok var və büdcə sətir sayından asılı deyil.
        with CaptureQueriesContext(connection) as ctx:
            resp = client.get(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertIn("paper", resp.json()["summary"])
        budget = len(ctx.captured_queries)
        self._add_students(9)
        with bypass_rls():
            for enrollment in Enrollment.objects.filter(
                offering=self.offering, student__username__startswith="w2_bulk"
            ):
                service.record_exam_score(enrollment=enrollment, score="33", by_user=self.center)
        with CaptureQueriesContext(connection) as ctx:
            resp = client.get(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(len(ctx.captured_queries), budget)
        self.assertEqual(
            {row["kind"]: row["entries"] for row in resp.json()["summary"]["paper"]}, {"written": 9, "practical": 2}
        )

    # ── Sahibin rəyi (2026-09-14, 2-ci dövrə): seçimlər, təsdiq dialoqu, nəzarətçi FK ──
    def test_roster_uses_project_selects_and_confirm_dialog_markup(self):
        resp = self._get(self._client(self.center))
        html = resp.content.decode()
        # Yoxlayan / nəzarətçi — axtarışlı project select, defolt yoxlayan = açılışın müəllimi.
        self.assertIn('name="examiner"', html)
        self.assertIn('name="invigilator"', html)
        self.assertIn(f'<option value="{self.teacher.id}" selected>', html)
        self.assertNotIn('name="examiner_name"', html)
        self.assertIn("data-ese-examiner", html)
        self.assertIn('data-live-search="true"', html)
        # Sual balı — SEÇİM (native number input yoxdur), hazır toggle + tənbəl gücləndirmə.
        self.assertIn(f'name="q__{self.enrollment.id}__1"', html)
        self.assertIn("data-ese-qtoggle", html)
        self.assertIn("bootstrap-single-select--compact", html)
        self.assertNotIn(
            f'type="number" class="ems-input ese-score ese-qscore" name="q__{self.enrollment.id}__1"', html
        )
        # Yekun sahəsi yalnız-oxunan, hərf sütunu, təsdiq dialoqu + şkala.
        self.assertIn("readonly", html)
        self.assertIn("data-ese-letter", html)
        self.assertIn('id="ese-confirm-config"', html)
        self.assertIn("data-ese-confirm-rows", html)
        self.assertIn("data-ese-confirm-failed-count", html)
        self.assertIn("data-ese-confirm", html)
        # İmtahan növü — seçilmiş etiket server tərəfdən (JS-dən əvvəl) + `required`.
        self.assertIn("data-ese-exam-kind-chip", html)
        self.assertIn('data-ese-exam-kind-label="', html)
        self.assertIn(
            'name="exam_kind" form="ese-roster-form" class="ems-select bootstrap-single-select__native" required', html
        )

    def test_confirm_config_uses_organisation_scale(self):
        resp = self._get(self._client(self.center))
        self.assertContains(resp, '"letter_bands"')
        self.assertContains(resp, '"pass_threshold"')
        self.assertContains(resp, '"min_final_exam_score"')
        self.assertContains(resp, '[91, "A", "4.00"]')

    def test_save_stores_examiner_and_invigilator_fk_and_persists_defaults(self):
        with bypass_rls():
            other = User.objects.create_user("w2_invig", "w2_invig@qku.edu.az", "pw")
            Membership.objects.create(
                user=other,
                organization=self.org,
                role=self.org.roles.get(name="teacher"),
                is_primary=True,
                is_active=True,
            )
        client = self._client(self.center)
        resp = self._save(
            client,
            questions=["8", "7"],
            examiner=str(self.teacher.id),
            invigilator=str(other.id),
            exam_kind="practical",
        )
        self.assertEqual(resp.status_code, 302)
        with bypass_rls():
            sheet = self.offering.exam_score_sheets.get()
            self.assertEqual(sheet.examiner_id, self.teacher.id)
            self.assertEqual(sheet.invigilator_id, other.id)
            self.assertEqual(sheet.invigilator_name, other.get_full_name() or other.username)
        resp = self._get(client)
        html = resp.content.decode()
        self.assertIn(f'<option value="{other.id}" selected>', html)  # nəzarətçi yenidən seçili
        self.assertIn('value="practical" selected', html)
        self.assertIn("ems-badge--", html)
        # Yad istifadəçi → vərəq yaranmır, bal yazılmır.
        with bypass_rls():
            stranger = User.objects.create_user("w2_stranger", "w2_stranger@qku.edu.az", "pw")
        resp = self._save(client, questions=["9", "9"], invigilator=str(stranger.id))
        self.assertEqual(resp.status_code, 302)
        with bypass_rls():
            self.assertEqual(self.offering.exam_score_sheets.count(), 1)
        self.assertEqual(self._exam_score(), Decimal(15))

    def test_section_is_ajax_safe_fragment(self):
        """Filtr paneli / çiplər / görünüş açarı SPA ilə işləsin — fraqment endpoint-i 200."""
        client = self._client(self.center)
        resp = client.get(
            reverse("accounts:profile_section_fragment", kwargs={"section": SECTION}),
            {"ese_offering": str(self.offering.id), "ese_status": "empty"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertTrue(payload.get("ok"))
        self.assertIn(f"score__{self.enrollment.id}", payload["html"])

    # Mövcud fixture sinfinin testləri bu modulda təkrar işləməsin.
    for _name in list(vars(fixtures.ExamScoreEntrySectionTest)):
        if _name.startswith("test_"):
            locals()[_name] = None
    del _name
