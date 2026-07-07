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
    # Deprecated no-op — Django auth groups artıq istifadə olunmur; command
    # yalnız self.stdout.write çağırır.
    "apps/accounts/management/commands/create_roles.py",
    # ExamSupervisionConsumer yalnız channel-layer group send/discard edir;
    # `scope["user"]` və feature-flag settings oxuyur; DB sorğusu yoxdur.
    "apps/exams/consumers.py",
    # make_user_import_template yalnız openpyxl ilə .xlsx şablonu yazır —
    # heç bir DB sorğusu yoxdur (sabit nümunə sətirlər).
    "apps/accounts/management/commands/make_user_import_template.py",
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
