#!/usr/bin/env python3
"""FAZA 4 / Task 1 regressiya qoruyucusu.

Bütün request-external DB entry-point-ləri (Celery task-ları, signal
handler-ləri, management command-ları, WebSocket consumer-ləri) ya
`rls_worker_atomic()` istifadə etməli, ya da açıq şəkildə istisnalar
siyahısında olmalıdır (DB toxunmayan komponentlər).

CI-də (`_lint.yml`) çağırılır — yeni sarınmamış entry-point əlavə etməkdən
qoruyur.

İstifadə::

    python scripts/check_worker_atomic_coverage.py --check
    python scripts/check_worker_atomic_coverage.py --list  # bütün faylları göstər
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# request-external DB entry-point pattern-ləri
ENTRY_PATTERNS = [
    re.compile(r"database_sync_to_async"),
    re.compile(r"@shared_task"),
    re.compile(r"@app\.task"),
    re.compile(r"class\s+\w+\s*\(.*BaseCommand.*\)"),
    re.compile(r"@receiver"),
    # Channels consumer sinifləri (WebSocket entry-point).
    re.compile(
        r"class\s+\w+\s*\(.*(?:AsyncJsonWebsocketConsumer|AsyncWebsocketConsumer|JsonWebsocketConsumer|WebsocketConsumer|SyncConsumer|AsyncConsumer).*\)"
    ),
]

WRAP_PATTERN = re.compile(r"rls_worker_atomic")

# Bilərəkdən istisnalar — DB-yə toxunmayan komponentlər.
# Yeni istisna əlavə edərkən komment ilə səbəbini yaz.
INTENTIONAL_EXEMPTIONS = {
    # Fixed WCU snapshot delegates every DB read to scoped_snapshot.capture(), which
    # requires a FRESH transaction before SET TRANSACTION REPEATABLE READ READ ONLY,
    # sets fixed tenant + bypass=False locally, and cannot be wrapped outside.
    # DB-enforced write rejection and non-bypass FORCE-RLS are regression-tested in
    # apps/workload/tests/test_scoped_snapshot.py; see docs/operations/WCU_WORKLOAD_SNAPSHOT.md.
    "apps/workload/management/commands/export_wcu_workload_snapshot.py",
    # Same fresh READ ONLY transaction requirement; explicit export schema and RLS tests.
    "apps/workload/management/commands/export_wcu_journal_cells.py",
    # Reviewed fixed additive parts own a fresh repeatable-read READ ONLY transaction;
    # old collector/query budget unchanged, both RLS modes and DB write rejection tested.
    "apps/workload/management/commands/export_wcu_journal_cells_part.py",
    # Independent text-free syllabus capture also owns a fresh tenant-scoped READ ONLY
    # transaction; no outer worker wrapper is possible. Both RLS modes and DB-level
    # write rejection: apps/workload/tests/test_syllabus_content_export.py.
    "apps/workload/management/commands/export_wcu_syllabus_content.py",
    # Fixed027/029 forensic content uses the same fresh RR READ ONLY capture;
    # outer worker atomic would prevent setting its isolation/read-only boundary.
    "apps/workload/management/commands/export_wcu_syllabus_forensic.py",
    # Fixed027 pointer-only diagnostic independently owns fresh tenant RR READ ONLY;
    # actual DB write rejection, RLS modes and strict normal-cycle rejection tested.
    "apps/workload/management/commands/export_wcu_syllabus_lineage_diagnostic.py",
    # Fresh fixed Four/Source28 metadata-only RR READ ONLY transaction; PG write-rejection tests.
    "apps/workload/management/commands/export_wcu_recovery_audit_diagnostic.py",
    # Fixed-four text-free history reader owns a fresh RR READ ONLY transaction;
    # no enclosing worker transaction is possible. Actual command and both-RLS tests.
    "apps/workload/management/commands/export_wcu_four_cell_history.py",
    # Source58 full-audit chunk diagnostic owns fresh RR READ ONLY + fixed tenant,
    # bypass=False. An outer worker atomic would break its fresh-transaction guard.
    # Real PG write rejection/context/outer-atomic tests: test_source58_audit_capture.py;
    # rationale: docs/REVIEWED_SOURCE58_AUDIT_CHUNKS.md (no recovery authority).
    "apps/workload/management/commands/export_wcu_source58_audit_chunks.py",
    # Fixed <=25 timetable roots own fresh tenant-local RR READ ONLY transaction;
    # outer wrapper would invalidate SET TRANSACTION. Capture/outer-atomic regression tested.
    "apps/workload/management/commands/export_wcu_timetable_evidence.py",
    # Fixed English metadata reader requires a fresh RR READ ONLY transaction;
    # tenant/actor SET LOCAL, DB write rejection and both RLS modes are tested.
    "apps/workload/management/commands/export_wcu_english_level_evidence.py",
    # ExamSupervisionConsumer yalnız channel-layer group send/discard edir;
    # `scope["user"]` və feature-flag settings oxuyur; DB sorğusu yoxdur.
    "apps/exams/consumers.py",
    # make_user_import_template yalnız openpyxl ilə .xlsx şablonu yazır —
    # heç bir DB sorğusu yoxdur (sabit nümunə sətirlər).
    "apps/accounts/management/commands/make_user_import_template.py",
    # Legacy miqrasiya komandaları — QƏSDƏN exempt:
    # preflight yalnız fayl sistemində SHA/ölçü/cədvəl sayı oxuyur — DB yoxdur.
    "apps/legacy_import/management/commands/legacy_import_preflight.py",
    # source_attest / source_pk_inventory yalnız inject olunmuş read-only
    # MariaDB mənbəyinə qoşulur; Django DB-yə heç bir sorğu yoxdur.
    "apps/legacy_import/management/commands/legacy_import_source_attest.py",
    "apps/legacy_import/management/commands/legacy_import_source_pk_inventory.py",
    # 2026-10-27 RİM əkiz düzəlişləri: bütün DB işi `relocate_twin_enrollment.run_plan`-dadır
    # (`rls_worker_atomic()` + `bypass_rls()` + RLS konteksti); bu fayllar yalnız plan faylını oxuyub runner verir.
    "apps/registrar/management/commands/fix_legacy_lesson_kinds.py",
    "apps/registrar/management/commands/merge_twin_offerings.py",
    # 2026-10-28 «Praktiki məşğələ» bayrağı: eyni `relocate_twin_enrollment.run_plan` gövdəsi (plan faylı → runner).
    "apps/registrar/management/commands/set_practical_offerings.py",
    # 2026-11-05 Psixologiya dublikatları: DB işi `merge_duplicate_student`-dədir (call_command; rls_worker_atomic orada).
    "apps/accounts/management/commands/merge_psychology_duplicates_20261105.py",
    "apps/accounts/management/commands/merge_psychology_duplicates_20261106.py",
    # 2026-11-05 RİM müraciətləri (MR-190/161/110): sabit cütlər, eyni `relocate_twin_enrollment.run_plan` gövdəsi.
    "apps/registrar/management/commands/repair_applications_20261105.py",
    "apps/registrar/management/commands/repair_applications_20261105c.py",
    "apps/registrar/management/commands/fix_ydk236_subject_20261106.py",
    "apps/registrar/management/commands/repair_applications_20261106.py",
    "apps/registrar/management/commands/rebuild_language_cohorts_20261106.py",
    # 2026-11-06 lab qrupları (Ekologiya kafedrası): eyni `relocate_twin_enrollment.run_plan` gövdəsi.
    "apps/registrar/management/commands/apply_lab_groups_20261106.py",
    # rehearse öz RLS kontekstini (set_rls_tenant, session-scoped, bypass-sız)
    # və öz transaction sərhədlərini (ledger advisory-lock atomic-ləri, batch
    # checkpoint/resume) idarə edir — tək böyük rls_worker_atomic() sarğısı
    # resume semantikasını pozardı. Bax: apps/legacy_import/services/
    # rehearsal_orchestrator.py §11 transaction cədvəli.
    "apps/legacy_import/management/commands/legacy_import_rehearse.py",
}

SEARCH_DIRS = ["apps", "core"]


def find_entry_point_files() -> list[Path]:
    """DB-yə toxuna biləcək bütün faylları tap."""
    files: set[Path] = set()
    for base in SEARCH_DIRS:
        base_path = ROOT / base
        if not base_path.exists():
            continue
        for py_path in base_path.rglob("*.py"):
            # Tests/migrations altındakı fayllar bu auditə aid deyil
            parts = set(py_path.relative_to(ROOT).parts)
            if "tests" in parts or "migrations" in parts:
                continue
            try:
                content = py_path.read_text(encoding="utf-8")
            except Exception:
                continue
            for pattern in ENTRY_PATTERNS:
                if pattern.search(content):
                    files.add(py_path)
                    break
    return sorted(files)


def is_wrapped(path: Path) -> bool:
    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        return False
    return bool(WRAP_PATTERN.search(content))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail if any entry-point is unwrapped and not exempt")
    parser.add_argument("--list", action="store_true", help="List all entry-point files")
    args = parser.parse_args()

    entry_files = find_entry_point_files()
    unwrapped: list[Path] = []
    exempt_used: set[str] = set()

    for path in entry_files:
        rel = str(path.relative_to(ROOT))
        if is_wrapped(path):
            continue
        if rel in INTENTIONAL_EXEMPTIONS:
            exempt_used.add(rel)
            continue
        unwrapped.append(path)

    if args.list:
        print(f"Cəmi request-external entry-point: {len(entry_files)}")
        for p in entry_files:
            rel = str(p.relative_to(ROOT))
            status = "✅" if is_wrapped(p) else ("⚪ EXEMPT" if rel in INTENTIONAL_EXEMPTIONS else "❌ UNWRAPPED")
            print(f"  {status}  {rel}")
        return 0

    if unwrapped:
        print("❌ Sarınmamış request-external DB entry-point-ləri tapıldı:")
        for p in unwrapped:
            print(f"   - {p.relative_to(ROOT)}")
        print()
        print("Həll: hər DB sorğusunu `with rls_worker_atomic(): ...` blokuna sar")
        print("      (`from core.rls_pooling import rls_worker_atomic`). Əgər fayl")
        print("      DB-yə toxunmursa, `INTENTIONAL_EXEMPTIONS`-ə əlavə et və səbəbi yaz.")
        return 1

    # Yoxla — bütün istisnaların hələ də candidate siyahısında olduğuna əmin ol
    entry_rels = {str(p.relative_to(ROOT)) for p in entry_files}
    stale_exempt = INTENTIONAL_EXEMPTIONS - entry_rels
    if stale_exempt:
        print("⚠️  İstisna siyahısında (INTENTIONAL_EXEMPTIONS) köhnəlmiş girişlər var:")
        for rel in sorted(stale_exempt):
            print(f"   - {rel}  (artıq entry-point pattern-inə uyğun deyil)")
        print("     Onları scripts/check_worker_atomic_coverage.py-dən silin.")
        return 1

    print(f"✅ Bütün {len(entry_files)} request-external DB entry-point-i düzgün sarınıb")
    print(f"   (aktiv istisna: {len(exempt_used)}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
