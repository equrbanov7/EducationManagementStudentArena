"""2026-09-14 wave 2 (audit F-07, §27 «6 ixracda formula neytrallaşdırma») — repo-boyu ixrac qoruyucusu.

Qayda: istifadəçiyə endirilən CSV/XLSX-lər YALNIZ ``core.export_safety``
(``safe_csv_writer`` / ``sheet_append`` / ``sheet_cell`` / ``neutralise_cell``) ilə
yazılır. Bu test ``apps/ core/ config/`` altında (testlər/migrasiyalar xaric)
«çılpaq» yazıcı çağırışlarını sayır və icazəli dəsti PİNLƏYİR:

* ``csv.writer(``            — birbaşa CSV yazıcısı;
* ``<ws|sheet…>.append(``    — openpyxl vərəq sətri;
* ``.cell(… value=…)``       — openpyxl xana yazısı (``value=neutralise_cell(`` sayılmır).

İcazəli dəst: operator-only idarəetmə əmrləri, idxal şablonları (başlıq/ipucu
sabitləri, dəyərlər ``export_text`` ilə keçir) və yalnız i18n sabiti yazan
xanalar. Yeni ixrac əlavə edən şəxs helper-i işlətməli, ya da bu siyahını
ŞÜURLU şəkildə (kod rəyi ilə) genişləndirməlidir.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.test import SimpleTestCase

REPO_ROOT = Path(__file__).resolve().parents[2]
SCAN_DIRS = ("apps", "core", "config")
HELPER_MODULE = "core/export_safety.py"

PATTERNS = {
    "csv_writer": re.compile(r"\bcsv\.writer\("),
    "sheet_append": re.compile(r"\b(?:ws|ws_\w+|\w+_ws|sheet|worksheet|\w+_sheet)\.append\("),
    "cell_value": re.compile(r"\.cell\([^)]*\bvalue=(?!neutralise_cell\()"),
}

#: Pinlənmiş icazəli dəst: fayl → {pattern: maksimum say}. Say AZALARSA pin-i azaldın.
ALLOWED: dict[str, dict[str, int]] = {
    # İdarəetmə əmrləri — yalnız operator işlədir, çıxış diskə/konsola gedir.
    "apps/accounts/management/commands/import_users_from_excel.py": {"csv_writer": 1},
    "apps/accounts/management/commands/make_user_import_template.py": {"cell_value": 8},
    "apps/accounts/management/commands/seed_staff_roster.py": {"csv_writer": 1},
    # İdxal şablonları — başlıq/ipucu sabitləri (istifadəçi mətni yoxdur).
    "apps/accounts/services/intake/spec.py": {"csv_writer": 1, "sheet_append": 2},
    "apps/accounts/services/intake/teachers.py": {"csv_writer": 1, "sheet_append": 2},
    # İmtahan balı idxal şablonu — sətirlər əvvəlcədən `export_text` ilə neytrallaşdırılır.
    "apps/registrar/exam_score_import.py": {"csv_writer": 1, "sheet_append": 2},
    # Jurnal ixracı — boş sətir (`ws.append([])`) və i18n əfsanə mətni; data `neutralise_cell` ilə.
    "apps/registrar/journal_export.py": {"sheet_append": 2, "cell_value": 2},
    # Final mərkəzi hesabatı — yalnız başlıq/etiket sabitləri; data `neutralise_cell` ilə.
    "apps/exams/services/final_center/xlsx_build.py": {"cell_value": 4},
}

#: F-07 üzrə düzəldilən 6 ixrac — helper importu MƏCBURİDİR (reqressiya qoruyucusu).
MUST_USE_HELPER = (
    "apps/accounts/views/student_registry.py",
    "apps/accounts/views/profile/statistics_export.py",
    "apps/accounts/views/profile/statistics_export_metrics.py",
    "apps/exams/views/teacher/results/_export_builder.py",
    "apps/exams/views/teacher/question_bank/_reports.py",
    "apps/exams/views/exam_center/statistics.py",
    "apps/workload/views/teacher_api.py",
)


def _scan() -> dict[str, dict[str, int]]:
    found: dict[str, dict[str, int]] = {}
    for base in SCAN_DIRS:
        for path in sorted((REPO_ROOT / base).rglob("*.py")):
            rel = path.relative_to(REPO_ROOT).as_posix()
            if "/tests/" in rel or "/migrations/" in rel or rel == HELPER_MODULE:
                continue
            text = path.read_text(encoding="utf-8")
            counts = {name: len(pattern.findall(text)) for name, pattern in PATTERNS.items()}
            counts = {name: count for name, count in counts.items() if count}
            if counts:
                found[rel] = counts
    return found


class ExportWriterGuardTest(SimpleTestCase):
    def test_no_bare_export_writers_outside_allowed_set(self):
        found = _scan()
        violations = []
        for rel, counts in found.items():
            allowed = ALLOWED.get(rel, {})
            for name, count in counts.items():
                if count > allowed.get(name, 0):
                    violations.append(f"{rel}: {name}={count} (icazəli: {allowed.get(name, 0)})")
        self.assertEqual(
            violations,
            [],
            "Çılpaq ixrac yazıcısı tapıldı — `core.export_safety` helper-ini işlədin:\n" + "\n".join(violations),
        )

    def test_allowed_pins_are_not_stale(self):
        found = _scan()
        stale = [rel for rel in ALLOWED if rel not in found]
        self.assertEqual(stale, [], f"ALLOWED-də artıq mövcud olmayan giriş(lər): {stale}")

    def test_fixed_exports_import_helper(self):
        missing = []
        for rel in MUST_USE_HELPER:
            text = (REPO_ROOT / rel).read_text(encoding="utf-8")
            if "from core.export_safety import" not in text:
                missing.append(rel)
        self.assertEqual(missing, [], f"F-07 ixracları helper-siz qalıb: {missing}")
