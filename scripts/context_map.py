#!/usr/bin/env python3
"""Məhdud kontekst xəritəsi + «jurnal modellərinə birbaşa import» ratchet-i.

Sahib 2026-09-21: «sonradan mikroservisə (məs. e-jurnal) çıxmaq lazım gəlsə
rahat alınsın». Bunun texniki şərti: başqa app-lar jurnal kontekstinin
MODELLƏRİNƏ birbaşa toxunmasın, yalnız `apps/registrar/public.py`
müqaviləsindən keçsin. Bu skript:

* ``(arqumentsiz)`` — kontekst xəritəsini çap edir: hər kontekstin modulları,
  daxil olan (inbound) və çıxan (outbound) import sayı, birbaşa model
  importlarının siyahısı;
* ``--check`` — CI qapısı: ``apps.registrar.models`` (jurnal/akademik
  reyestr) YENİ birbaşa importu (registrar-dan kənar, test olmayan modul)
  baseline-dən artıq ola bilməz (ratchet: azaltmaq olar, artırmaq olmaz);
* ``--update`` — baseline-i cari vəziyyətə yazır (yalnız şüurlu halda).

Baseline: ``scripts/context_map_baseline.json`` — {fayl: [import-sətri sayı]}.
Bax: docs/architecture/MICROSERVICE_READINESS.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASELINE = ROOT / "scripts" / "context_map_baseline.json"

#: Məhdud kontekstlər → app-lar (registrar üç kontekstə bölünür; bölgü modul
#: prefiksinə görədir, bax `REGISTRAR_CONTEXTS`).
CONTEXTS = {
    "identity_tenant": ("accounts", "organizations"),
    "academic_registry": ("registrar",),  # catalog/curriculum/offerings/enrollment/movements
    "e_journal": ("registrar",),  # lessons/marks/assessment/finals/corrections/close
    "schedule": ("registrar",),  # schedule_*
    "syllabus": ("syllabus",),
    "workload": ("workload",),
    "exams": ("exams", "live_exam", "appeals", "trial_exams"),
    "learning_tasks": ("courses", "assignments", "labs", "projects", "task_submission_core"),
    "platform": ("notifications", "audit", "monitoring", "ai_assistant", "blog", "contact", "applications"),
    "legacy_import": ("legacy_import",),
}

#: registrar modul prefiksi → kontekst (ilk uyğun gələn qalib gəlir).
REGISTRAR_CONTEXTS = (
    ("schedule", "schedule"),
    ("ical", "schedule"),
    ("lesson_rooms", "schedule"),
    ("calendar_context", "schedule"),
    ("catalog", "academic_registry"),
    ("curriculum", "academic_registry"),
    ("plan_", "academic_registry"),
    ("program_detail", "academic_registry"),
    ("movements", "academic_registry"),
    ("transfer", "academic_registry"),
    ("guest_", "academic_registry"),
    ("reference_identity", "academic_registry"),
    ("individual_plan", "academic_registry"),
    ("semester_", "academic_registry"),
    ("transcript", "academic_registry"),
    ("status", "academic_registry"),
    ("campus", "academic_registry"),
    ("subgroup_rollup", "academic_registry"),
)

#: Jurnal kontekstinin modelləri — mikroservisə çıxarılacaq DB sərhədi.
JOURNAL_MODELS = {
    "Lesson",
    "LessonMark",
    "LessonKind",
    "AssessmentScheme",
    "AssessmentComponent",
    "ComponentScore",
    "CriterionScore",
    "Rubric",
    "RubricCriterion",
    "SelfWorkTopic",
    "SelfWorkMark",
    "CourseWork",
    "FinalGrade",
    "ResitRecord",
    "ExamScoreSheet",
    "ExamScoreSheetSource",
    "ExamScoreSheetKind",
    "ExamScoreEntryKind",
    "KollokviumWindow",
    "KollokviumExtraGrant",
    "KOLLOKVIUM_WINDOW_COUNT",
    "JournalCloseNotice",
    "JournalCloseScope",
    "JournalCorrection",
    "CorrectionReason",
    "ImmutableCorrectionEvidence",
    "LegacyExcuseDocument",
}

IMPORT_RE = re.compile(r"^\s*from apps\.registrar\.models(?:\.[\w.]+)? import (.+)$")
NAMES_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _py_files():
    for base in ("apps", "core", "config"):
        for path in (ROOT / base).rglob("*.py"):
            rel = path.relative_to(ROOT).as_posix()
            if "/tests/" in rel or "/migrations/" in rel or rel.startswith("apps/registrar/"):
                continue
            yield rel, path


def direct_model_imports() -> dict:
    """{fayl: [(sətir, adlar)]} — registrar-dan kənar birbaşa `registrar.models` importları."""
    found: dict = defaultdict(list)
    for rel, path in _py_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        lines = text.splitlines()
        for index, line in enumerate(lines, start=1):
            match = IMPORT_RE.match(line)
            if not match:
                continue
            names_text = match.group(1)
            # Çoxsətirli `import (` — bağlanan mötərizəyə qədər oxu.
            if names_text.strip().startswith("(") and ")" not in names_text:
                j = index
                while j < len(lines) and ")" not in lines[j]:
                    names_text += " " + lines[j]
                    j += 1
            names = [n for n in NAMES_RE.findall(names_text.replace("import", "")) if n != "as"]
            found[rel].append((index, names))
    return dict(found)


def registrar_context(module: str) -> str:
    for prefix, context in REGISTRAR_CONTEXTS:
        if module.startswith(prefix):
            return context
    return "e_journal"


def report(imports: dict) -> None:
    print("Məhdud kontekstlər (app-lar):")
    for context, apps in CONTEXTS.items():
        print(f"  {context:<18} → {', '.join(apps)}")
    registrar_dir = ROOT / "apps" / "registrar"
    buckets: dict = defaultdict(list)
    for path in sorted(registrar_dir.glob("*.py")):
        if path.name in ("__init__.py", "apps.py", "admin.py", "urls.py", "signals.py", "forms.py"):
            continue
        buckets[registrar_context(path.stem)].append(path.stem)
    print("\nregistrar modulları kontekst üzrə:")
    for context in ("academic_registry", "e_journal", "schedule"):
        mods = buckets.get(context, [])
        print(f"  {context:<18} {len(mods):>3} modul: {', '.join(mods[:12])}{' …' if len(mods) > 12 else ''}")
    total = sum(len(v) for v in imports.values())
    journal = {
        f: [(ln, [n for n in names if n in JOURNAL_MODELS]) for ln, names in rows] for f, rows in imports.items()
    }
    journal = {f: [(ln, ns) for ln, ns in rows if ns] for f, rows in journal.items()}
    journal = {f: rows for f, rows in journal.items() if rows}
    print(
        f"\nBirbaşa `apps.registrar.models` importu (registrar-dan kənar, test olmayan): {len(imports)} fayl / {total} sətir"
    )
    print(f"  bunlardan JURNAL modellərinə: {len(journal)} fayl")
    for f, rows in sorted(journal.items()):
        for ln, ns in rows:
            print(f"    {f}:{ln}  {', '.join(ns)}")
    print(
        "\nQayda: yeni kodda `apps.registrar.public` (və `public_services`) müqaviləsindən keçin; bax docs/architecture/MICROSERVICE_READINESS.md"
    )


def counts(imports: dict) -> dict:
    return {f: len(rows) for f, rows in sorted(imports.items())}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--update", action="store_true")
    args = parser.parse_args()
    imports = direct_model_imports()
    current = counts(imports)
    if args.update:
        BASELINE.write_text(json.dumps(current, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"✅ Kontekst baseline-i yazıldı: {len(current)} fayl, {sum(current.values())} import sətri")
        return 0
    if args.check:
        baseline = json.loads(BASELINE.read_text(encoding="utf-8")) if BASELINE.exists() else {}
        new = {f: n for f, n in current.items() if n > baseline.get(f, 0)}
        if new:
            print("❌ Kontekst qapısı: `apps.registrar.models`-ə YENİ birbaşa import (registrar-dan kənar):")
            for f, n in new.items():
                print(f"     {f}: {n} (baseline {baseline.get(f, 0)})")
            print(
                "   → apps/registrar/public.py müqaviləsindən keçin (bax docs/architecture/MICROSERVICE_READINESS.md)"
            )
            return 1
        shrunk = sum(1 for f, n in baseline.items() if current.get(f, 0) < n)
        print(
            f"✅ Kontekst qapısı: yeni birbaşa jurnal/reyestr model importu yoxdur "
            f"({len(current)} fayl; {shrunk} fayl kiçilib — `--update` ilə sıxın)"
        )
        return 0
    report(imports)
    return 0


if __name__ == "__main__":
    sys.exit(main())
