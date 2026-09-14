#!/usr/bin/env python3
"""`bypass_rls()` çağırış inventarı — `docs/audits/RLS_BYPASS_AUDIT.md` cədvəlinin mənbəyi.

Audit `access` F-13 (2026-09-13): sənəddəki sayım (2026-05, «~85 çağırış») əllə
aparılmışdı və köhnəlmişdi (auditor 164 çağırış / 64 fayl saydı). Bu skript
sayımı DETERMİNİSTİK edir: sənəd yenilənəndə `--markdown` çıxışı olduğu kimi
yapışdırılır, əllə say yoxdur.

Qayda:
* `apps/`, `core/`, `config/` altındakı `.py` fayllar; `tests/`, `migrations/`,
  `test_*.py` xaric;
* sayılan: `bypass_rls()` və `set_rls_bypass(` çağırışları (alias-lı
  `_bypass_rls()` / `_bypass_rls_ts()` daxil); `def`/`import` sətirləri və şərh
  sətirləri sayılmır (auditorun xam grep-i şərhləri də sayırdı — 164);
* kateqoriya (A/B/C/D — sənəddəki təsnifat) fayl yoluna görə `CATEGORY_RULES`
  ilə verilir; uyğun gəlməyən yol `?` alır — sənədə əlavə ediləndə təsnif olunmalıdır.

İstifadə:
    venv/bin/python scripts/rls_bypass_inventory.py            # xülasə
    venv/bin/python scripts/rls_bypass_inventory.py --markdown # sənəd cədvəli
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CALL_RE = re.compile(r"\w*bypass_rls\w*\(\)|\bset_rls_bypass\(")
SKIP_PARTS = {"tests", "migrations", "__pycache__"}

# (prefix, kateqoriya, izah) — ilk uyğun gələn qalib gəlir.
CATEGORY_RULES = (
    ("core/rls.py", "D", "RLS infrastrukturunun özü (kontekst menecerləri)"),
    ("core/tenancy.py", "D", "tenant kontekst qurma"),
    ("apps/organizations/middleware.py", "D", "tenant kontekst qurma"),
    ("apps/accounts/middleware.py", "D", "ilk-giriş / sessiya qapısı"),
    ("apps/notifications/", "A", "recipient-scoped bildiriş"),
    ("apps/blog/", "A", "qlobal blog (tenant-suz)"),
    ("apps/live_exam/", "B", "public PIN/token girişi"),
    ("apps/exams/services/final_center/", "B", "final mərkəzi PIN axını"),
    ("apps/exams/views/student/final_center.py", "B", "final mərkəzi PIN axını"),
    ("apps/exams/services/exam_center_gate.py", "B", "imtahan mərkəzi qapısı"),
    ("apps/exams/tasks.py", "D", "Celery (sorğu konteksti yoxdur; job sətri org FK-lıdır)"),
    ("apps/exams/", "C", "imtahan mərkəzi / müəllim cross-org əməli"),
    ("apps/accounts/services/view_as.py", "C", "view-as (hədəf yoxlaması ilə)"),
    ("apps/accounts/services/organization_requests.py", "C", "üzvlük sorğusu axını"),
    ("apps/accounts/services/registration.py", "C", "qeydiyyat (org seçimi öncəsi)"),
    ("apps/accounts/management/", "C", "idarə əmrləri (prod kill-switch-li)"),
    ("apps/registrar/management/", "C", "idarə əmrləri"),
    ("apps/registrar/page_contexts.py", "D", "tenant konteksti itmiş səhifə fallback-i (şərhli)"),
    ("apps/syllabus/management/", "C", "idarə əmrləri"),
    ("apps/accounts/", "C", "superadmin / admin cross-org əməliyyatı"),
    ("apps/audit/", "C", "superadmin audit görünüşü"),
    ("apps/monitoring/", "C", "superadmin monitorinq"),
    ("apps/superadmin/", "C", "superadmin paneli"),
    ("apps/organizations/", "C", "təşkilat idarəetməsi"),
    ("core/", "D", "infrastruktur"),
)


def _category(rel: str) -> tuple[str, str]:
    for prefix, category, note in CATEGORY_RULES:
        if rel.startswith(prefix):
            return category, note
    return "?", "TƏSNİF EDİLMƏYİB — sənədə əlavə edin"


def _count_file(path: Path) -> int:
    count = 0
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = line.strip()
        if stripped.startswith(("#", "def ", "from ", "import ", '"""', "'''", "*", "-")):
            continue
        code = stripped.split("#", 1)[0]
        count += len(CALL_RE.findall(code))
    return count


def inventory(root: Path = ROOT) -> Counter:
    counts: Counter = Counter()
    for base in ("apps", "core", "config"):
        for path in (root / base).rglob("*.py"):
            rel = path.relative_to(root)
            if SKIP_PARTS.intersection(rel.parts) or path.name.startswith("test"):
                continue
            n = _count_file(path)
            if n:
                counts[rel.as_posix()] = n
    return counts


def render_markdown(counts: Counter) -> str:
    lines = ["| Fayl | Çağırış | Kateqoriya |", "|---|---:|---|"]
    for rel, n in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        category, note = _category(rel)
        lines.append(f"| `{rel}` | {n} | {category} — {note} |")
    by_category: Counter = Counter()
    for rel, n in counts.items():
        by_category[_category(rel)[0]] += n
    total = sum(counts.values())
    summary = ", ".join(f"{k}: {v}" for k, v in sorted(by_category.items()))
    lines.append("")
    lines.append(f"**Cəmi:** {total} çağırış / {len(counts)} fayl · kateqoriya üzrə — {summary}.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--markdown", action="store_true", help="sənəd üçün Markdown cədvəl çap et")
    args = parser.parse_args(argv)
    counts = inventory()
    if args.markdown:
        print(render_markdown(counts))
    else:
        total = sum(counts.values())
        print(f"{total} çağırış / {len(counts)} fayl")
        for rel, n in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:15]:
            print(f"{n:4d}  {rel}")
    unclassified = [rel for rel in counts if _category(rel)[0] == "?"]
    if unclassified:
        print("\nTƏSNİF EDİLMƏYİB:", ", ".join(sorted(unclassified)), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
