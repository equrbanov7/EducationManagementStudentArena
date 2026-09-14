"""PostgreSQL trigger matrisi — ``0073_exam_score_sheet_integrity`` (Codex audit P2-09, 2026-09-13).

Model ``clean()``-dən YAN KEÇƏN yazılar (``objects.create`` — ``full_clean`` çağırmır —
və ``QuerySet.update()``) DB-də dayanmalıdır: xəta ``IntegrityError``-dur
(ERRCODE 23514), ``ValidationError`` deyil. Servis yolu (``create_sheet`` →
``record_exam_score`` → ``finalize_sheet``) isə trigger-lərdən keçməlidir.

Əlavə iki yoxlama:

* miqrasiyanın ÖN YOXLAMASI (``_PRECHECK_SQL``) mövcud pozuntuda dayanır, təmiz
  bazada keçir — ``0041`` fəlsəfəsi («heç nə yenidən yazılmır»);
* istehsal ssenarisi: test qoşulması superuser-dir (RLS-i keçir), ona görə
  ``rls_app_role`` (NOSUPERUSER + NOBYPASSRLS) sessiyasında, ``app.current_org_id``
  qoyulmuş halda və funksiyaların sahibi də həmin rol olanda (trigger daxilindəki
  SELECT-lər FORCE RLS-dən keçir) qanuni yazı KEÇİR, yad açılış/vərəq RƏDD olunur.
"""

import importlib
from decimal import Decimal

from django.db import IntegrityError, connection, transaction
from django.test import TestCase

import pytest

from apps.registrar import exam_score_entry as service
from apps.registrar import exam_score_sheets as sheets
from apps.registrar.models import ExamScoreEntry, ExamScoreSheet
from apps.registrar.tests.test_exam_score_sheet_invariants import build_tenant

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(connection.vendor != "postgresql", reason="PostgreSQL triggers are required."),
]

_MIGRATION = importlib.import_module("apps.registrar.migrations.0073_exam_score_sheet_integrity")
_SHEET_TABLE = _MIGRATION._SHEET_TABLE
_ENTRY_TABLE = _MIGRATION._ENTRY_TABLE
_SHEET_TRIGGER = _MIGRATION._SHEET_TRIGGER
_ENTRY_TRIGGER = _MIGRATION._ENTRY_TRIGGER
_SHEET_FUNCTION = _MIGRATION._SHEET_FUNCTION
_ENTRY_FUNCTION = _MIGRATION._ENTRY_FUNCTION


class ExamScoreSheetTriggerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.a = build_tenant("pgess_a")
        cls.b = build_tenant("pgess_b")

    # ── köməkçilər (modelin clean()-i çağırılmır — yalnız DB səddi) ──────
    def _raw_sheet(self, organization, offering, **extra):
        return ExamScoreSheet.objects.create(
            organization=organization, offering=offering, created_by_name="raw", **extra
        )

    def _raw_entry(self, organization, enrollment, **extra):
        return ExamScoreEntry.objects.create(
            organization=organization,
            enrollment=enrollment,
            new_score=Decimal("10"),
            entered_by_name="raw",
            **extra,
        )

    def test_triggers_are_installed(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal AND tgname IN (%s, %s)",
                [_SHEET_TRIGGER, _ENTRY_TRIGGER],
            )
            names = {row[0] for row in cursor.fetchall()}
        self.assertEqual(names, {_SHEET_TRIGGER, _ENTRY_TRIGGER})

    # ── I1: vərəq ↔ açılış ───────────────────────────────────────────────
    def test_sheet_with_offering_of_other_tenant_is_rejected(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._raw_sheet(self.b.org, self.a.offerings[0])

    def test_sheet_identity_is_immutable_after_insert(self):
        sheet = self._raw_sheet(self.a.org, self.a.offerings[0])
        with self.assertRaises(IntegrityError), transaction.atomic():
            ExamScoreSheet.objects.filter(pk=sheet.pk).update(offering=self.a.offerings[1])
        with self.assertRaises(IntegrityError), transaction.atomic():
            ExamScoreSheet.objects.filter(pk=sheet.pk).update(organization=self.b.org)
        # Sayğac yeniləməsi sərbəstdir.
        ExamScoreSheet.objects.filter(pk=sheet.pk).update(rows_total=3, rows_written=2)
        sheet.refresh_from_db()
        self.assertEqual((sheet.rows_total, sheet.rows_written), (3, 2))

    # ── I4: skanın org-prefiksi ──────────────────────────────────────────
    def test_sheet_evidence_outside_own_organization_prefix_is_rejected(self):
        sheet = self._raw_sheet(self.a.org, self.a.offerings[0])
        foreign_path = f"exam_score_sheets/{self.b.org.id}/CODEX_TEST.pdf"
        with self.assertRaises(IntegrityError), transaction.atomic():
            ExamScoreSheet.objects.filter(pk=sheet.pk).update(evidence=foreign_path)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._raw_sheet(self.a.org, self.a.offerings[0], evidence=foreign_path)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._raw_sheet(self.a.org, self.a.offerings[0], evidence="journal_corrections/CODEX_TEST.pdf")
        own_path = f"exam_score_sheets/{self.a.org.id}/CODEX_TEST.pdf"
        ExamScoreSheet.objects.filter(pk=sheet.pk).update(evidence=own_path)  # keçir
        self.assertEqual(ExamScoreSheet.objects.get(pk=sheet.pk).evidence.name, own_path)

    # ── I3: sətir ↔ qeydiyyat ↔ vərəq ────────────────────────────────────
    def test_entry_with_enrollment_of_other_tenant_is_rejected(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._raw_entry(self.b.org, self.a.enrollments[0])

    def test_entry_with_sheet_of_other_offering_is_rejected(self):
        other = self._raw_sheet(self.a.org, self.a.offerings[1])
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._raw_entry(self.a.org, self.a.enrollments[0], sheet=other)

    def test_entry_with_sheet_of_other_tenant_is_rejected(self):
        foreign = self._raw_sheet(self.b.org, self.b.offerings[0])
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._raw_entry(self.a.org, self.a.enrollments[0], sheet=foreign)

    def test_entry_cannot_be_reattached_to_foreign_sheet_by_update(self):
        own = self._raw_sheet(self.a.org, self.a.offerings[0])
        entry = self._raw_entry(self.a.org, self.a.enrollments[0], sheet=own)
        other = self._raw_sheet(self.a.org, self.a.offerings[1])
        with self.assertRaises(IntegrityError), transaction.atomic():
            ExamScoreEntry.objects.filter(pk=entry.pk).update(sheet=other)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ExamScoreEntry.objects.filter(pk=entry.pk).update(organization=self.b.org)
        self.assertEqual(ExamScoreEntry.objects.get(pk=entry.pk).sheet_id, own.pk)

    def test_entry_without_sheet_still_requires_same_tenant_enrollment(self):
        entry = self._raw_entry(self.a.org, self.a.enrollments[0])  # sheet=NULL keçir
        with self.assertRaises(IntegrityError), transaction.atomic():
            ExamScoreEntry.objects.filter(pk=entry.pk).update(enrollment=self.b.enrollments[0])

    # ── servis yolu trigger-lərdən keçir ─────────────────────────────────
    def test_service_flow_passes_the_triggers(self):
        sheet = sheets.create_sheet(offering=self.a.offerings[0], by_user=self.a.center, protocol_number="P-1")
        entry = service.record_exam_score(
            enrollment=self.a.enrollments[0], score="40", by_user=self.a.center, sheet=sheet
        )
        self.assertEqual(entry.sheet_id, sheet.pk)
        sheets.finalize_sheet(sheet, {"total": 1, "written": 1, "skipped": 0, "failed": 0}, by_user=self.a.center)
        sheet.refresh_from_db()
        self.assertEqual((sheet.rows_total, sheet.rows_written), (1, 1))

    # ── miqrasiyanın ön yoxlaması ────────────────────────────────────────
    def _with_trigger_disabled(self, table, trigger, make_row):
        """Pozucu sətri yalnız trigger söndürülmüş halda yazmaq olar (DDL tranzaksiya daxilindədir).

        Test tranzaksiyasında əvvəlki INSERT-lərin DEFERRABLE FK yoxlamaları hələ
        gözləyir; PostgreSQL «pending trigger events» olan cədvəldə `ALTER TABLE`
        icra etmir — ona görə əvvəlcə `SET CONSTRAINTS ALL IMMEDIATE` ilə boşaldılır.
        """
        with connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
            cursor.execute(f"ALTER TABLE public.{table} DISABLE TRIGGER {trigger}")
        try:
            return make_row()
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
                cursor.execute(f"ALTER TABLE public.{table} ENABLE TRIGGER {trigger}")

    def _run_precheck(self):
        with connection.cursor() as cursor:
            cursor.execute(_MIGRATION._PRECHECK_SQL)

    def test_precheck_stops_on_existing_violation_and_passes_when_clean(self):
        self._run_precheck()  # təmiz baza → keçir

        bad_sheet = self._with_trigger_disabled(
            _SHEET_TABLE, _SHEET_TRIGGER, lambda: self._raw_sheet(self.b.org, self.a.offerings[0])
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._run_precheck()  # I1 pozuntusu → dayanır
        ExamScoreSheet.objects.filter(pk=bad_sheet.pk).delete()
        self._run_precheck()

        other = self._raw_sheet(self.a.org, self.a.offerings[1])
        bad_entry = self._with_trigger_disabled(
            _ENTRY_TABLE, _ENTRY_TRIGGER, lambda: self._raw_entry(self.a.org, self.a.enrollments[0], sheet=other)
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._run_precheck()  # I3 pozuntusu → dayanır
        ExamScoreEntry.objects.filter(pk=bad_entry.pk).delete()
        self._run_precheck()

    # ── istehsal ssenarisi: qeyri-superuser sessiya + tenant konteksti ────
    def test_triggers_hold_for_restricted_role_with_tenant_context(self):
        foreign_sheet = self._raw_sheet(self.b.org, self.b.offerings[0])  # superuser kimi, əvvəlcədən
        other_offering_sheet = self._raw_sheet(self.a.org, self.a.offerings[1])
        with connection.cursor() as cursor:
            # Funksiyaların sahibi müvəqqəti `rls_app_role` olur — miqrasiyanı
            # qeyri-superuser cədvəl sahibi icra etmiş kimi: SECURITY DEFINER
            # gövdəsindəki SELECT-lər FORCE RLS-ə tabe olur. Sahib dəyişikliyi
            # sxemdə CREATE tələb edir; hamısı test tranzaksiyası ilə geri qayıdır.
            cursor.execute("GRANT CREATE ON SCHEMA public TO rls_app_role")
            cursor.execute(f"ALTER FUNCTION public.{_SHEET_FUNCTION}() OWNER TO rls_app_role")
            cursor.execute(f"ALTER FUNCTION public.{_ENTRY_FUNCTION}() OWNER TO rls_app_role")
            cursor.execute("SELECT set_config('app.bypass_rls', 'off', true)")
            cursor.execute("SELECT set_config('app.current_org_id', %s, true)", [str(self.a.org.pk)])
            cursor.execute("SET LOCAL ROLE rls_app_role")
        try:
            self.assertEqual(ExamScoreSheet.objects.count(), 1)  # RLS işləyir: yalnız A-nın vərəqi
            sheet = self._raw_sheet(self.a.org, self.a.offerings[0])  # qanuni → keçir
            entry = self._raw_entry(self.a.org, self.a.enrollments[0], sheet=sheet)  # qanuni → keçir
            self.assertEqual(entry.sheet_id, sheet.pk)
            with self.assertRaises(IntegrityError), transaction.atomic():
                self._raw_sheet(self.a.org, self.b.offerings[0])  # yad açılış RLS-də görünmür → rədd
            with self.assertRaises(IntegrityError), transaction.atomic():
                self._raw_entry(self.a.org, self.a.enrollments[0], sheet=foreign_sheet)  # yad vərəq → rədd
            with self.assertRaises(IntegrityError), transaction.atomic():
                self._raw_entry(self.a.org, self.a.enrollments[0], sheet=other_offering_sheet)  # öz tenant, yad açılış
            with self.assertRaises(IntegrityError), transaction.atomic():
                ExamScoreSheet.objects.filter(pk=sheet.pk).update(offering=self.a.offerings[1])  # kimlik dəyişmir
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")
                cursor.execute("SELECT set_config('app.bypass_rls', 'on', true)")
