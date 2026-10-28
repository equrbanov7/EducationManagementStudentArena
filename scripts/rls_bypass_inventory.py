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
    # 2026-10-18: publik sənəd yoxlaması — dəqiq 80 bitlik kod üzrə TƏK sətir, yalnız publik sütunlar, yazısız.
    ("apps/verification/lookup.py", "B", "public sənəd yoxlaması (kod üzrə tək sətir)"),
    ("apps/exams/services/final_center/", "B", "final mərkəzi PIN axını"),
    ("apps/exams/views/student/final_center.py", "B", "final mərkəzi PIN axını"),
    ("apps/exams/services/exam_center_gate.py", "B", "imtahan mərkəzi qapısı"),
    ("apps/exams/tasks.py", "D", "Celery (sorğu konteksti yoxdur; job sətri org FK-lıdır)"),
    # 2026-10-21: sınaq imtahanının silinməsi — --org + DƏQİQ --slug + --expect-title, defolt dry-run, prod kill-switch.
    (
        "apps/exams/management/commands/purge_trial_exam.py",
        "C",
        "idarə əmri (--org + dəqiq --slug + --expect-title; dry-run defolt, prod kill-switch-li)",
    ),
    # 2026-10-25: tələbənin səhv cəhdinin silinməsi — --org + dəqiq --username + cəhd + --expect-exam-slug, dry-run defolt.
    (
        "apps/exams/management/commands/purge_exam_attempt.py",
        "C",
        "idarə əmri (--org + dəqiq --username + cəhd + --expect-exam-slug; dry-run defolt, prod kill-switch-li)",
    ),
    # 2026-10-27: imtahan qrupunun jurnal boşluğu — --org + superadmin --actor, YALNIZ əlavə (qrupa sonra gəlmiş tələbə
    # jurnala), dry-run defolt, idempotent; çıxış yalnız id / kod / say.
    (
        "apps/exams/management/commands/fix_exam_journal_gaps.py",
        "C",
        "idarə əmri (--org + superadmin --actor; yalnız əlavə, dry-run defolt, idempotent)",
    ),
    ("apps/exams/", "C", "imtahan mərkəzi / müəllim cross-org əməli"),
    # 2026-10-23: aktivləşdirmə bildirişi — alıcılar sabit RİM rolları + aktivləşdirənin ÖZ təşkilatı, sətir qayıtmır.
    ("apps/accounts/services/rim/activation.py", "A", "recipient-scoped bildiriş (RİM rolları, öz təşkilat)"),
    ("apps/accounts/services/view_as.py", "C", "view-as (hədəf yoxlaması ilə)"),
    ("apps/accounts/services/organization_requests.py", "C", "üzvlük sorğusu axını"),
    ("apps/accounts/services/registration.py", "C", "qeydiyyat (org seçimi öncəsi)"),
    ("apps/accounts/management/", "C", "idarə əmrləri (prod kill-switch-li)"),
    ("apps/registrar/management/", "C", "idarə əmrləri"),
    ("apps/registrar/page_contexts.py", "D", "tenant konteksti itmiş səhifə fallback-i (şərhli)"),
    ("apps/syllabus/management/", "C", "idarə əmrləri"),
    # 2026-10-07 təsnifatı (audit 2026-09-28 T-04 + 2026-10-07 təkrar yoxlama): hamısı
    # request-siz fon işi / idarə əmri; servis sorğuları açıq `organization` süzgəci daşıyır.
    ("apps/ai_assistant/retention.py", "D", "dövri log saxlama süpürgəsi (yalnız müddət üzrə DELETE)"),
    ("apps/subject_folder/tasks.py", "D", "Celery (rls_worker_atomic; sətrin öz təşkilatı)"),
    ("apps/subject_folder/services/plagiarism/dispatch.py", "D", "Celery/sinxron oxşarlıq (engine org süzgəcli)"),
    ("apps/subject_folder/management/", "C", "idarə əmrləri"),
    ("apps/surveys/tasks.py", "D", "Celery (rls_worker_atomic; sorğunun öz təşkilatı)"),
    ("apps/surveys/services/pending.py", "D", "anonim cavab buferi köçürməsi (artıq icazəli kampaniya id-si)"),
    ("apps/surveys/services/survey_buffer.py", "D", "anonim cavab buferi köçürməsi (artıq icazəli sorğu id-si)"),
    ("apps/surveys/management/", "C", "idarə əmrləri"),
    ("apps/timetable/tasks.py", "D", "Celery (cədvəl generatoru, run sətrinin təşkilatı)"),
    # 2026-10-19: əmək müqaviləsi xatırlatmaları — bütün təşkilatlar bir keçiddə, hər sətir öz org-u ilə yazılır.
    ("apps/hr_contracts/tasks.py", "D", "Celery (rls_worker_atomic; müqavilənin öz təşkilatı)"),
    ("apps/hr_contracts/management/", "C", "idarə əmrləri (--org / --dry-run)"),
    # Rəy A5/A6 (2026-10-19): alıcı üzvlükləri açıq org süzgəcli (transaction-scoped RLS-dən asılı olmasın) və
    # əvəz olunmuş faylın «hələ istinad olunurmu» yoxlaması (commit-dən sonra, yalnız `file` yolu üzrə).
    ("apps/hr_contracts/services/notify.py", "D", "bildiriş alıcıları (açıq təşkilat süzgəcli üzvlük oxusu)"),
    ("apps/hr_contracts/services/files.py", "D", "commit-dən sonra yetim fayl təmizliyi (yol üzrə EXISTS)"),
    ("apps/workload/management/", "C", "idarə əmrləri (--org ilə)"),
    # 2026-10-25: köhnə jurnal müəllim sübutu — yalnız oxu (lokal prod kopyası), çıxış şifrəli sübut faylıdır.
    (
        "apps/legacy_import/management/commands/legacy_journal_teachers_extract.py",
        "C",
        "idarə əmri (yalnız oxu; sübut faylı)",
    ),
    # 2026-10-27: RİM əkiz jurnal planları — yalnız oxu (lokal prod surəti), plan faylında yalnız id-lər.
    (
        "apps/legacy_import/management/commands/build_twin_repair_plans.py",
        "C",
        "idarə əmri (yalnız oxu; id-li plan faylı)",
    ),
    # 2026-10-28: «Praktiki məşğələ» bayrağının planı — yalnız oxu (lokal prod surəti), plan faylında yalnız id-lər.
    (
        "apps/legacy_import/management/commands/build_practical_flag_plan.py",
        "C",
        "idarə əmri (yalnız oxu; id-li plan faylı)",
    ),
    # 2026-10-27: səhv arxivlənmiş konkret tələbənin girişi — auditli restore_archived_account, dry-run defolt.
    (
        "apps/legacy_import/management/commands/restore_archived_students.py",
        "C",
        "idarə əmri (adla verilən hesablar; auditli bərpa, dry-run defolt)",
    ),
    # 2026-10-27: səviyyə jurnalı payları/birləşmə planı + kafedra jurnal sağlamlığı — yalnız oxu, yalnız id-lər.
    (
        "apps/legacy_import/management/commands/build_journal_share_plans.py",
        "C",
        "idarə əmri (yalnız oxu; id-li plan faylı)",
    ),
    (
        "apps/legacy_import/management/commands/chair_journal_health.py",
        "C",
        "idarə əmri (yalnız oxu; müəllim id-ləri)",
    ),
    # 2026-10-08: WS qapısı — tenant GUC-suz ASGI scope; yalnız qoşulan istifadəçinin öz
    # profil/üzvlük oxusu (pk süzgəcli) + rədd audit sətri.
    ("apps/accounts/ws_gate.py", "D", "WebSocket giriş qapısı (istifadəçinin öz sətirləri + audit)"),
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
