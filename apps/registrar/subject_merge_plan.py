"""Fənn birləşdirməsi — PLAN rejimi: bir qaçışda çoxlu cüt (sahib 2026-11-04, ~95 dublikat kart).

Hər apply qaçışı prod-da tam ``pg_dump`` alır (~770 MB) — 95 ayrı qaçış təhlükəlidir. Plan rejimi BİR qaçışda (BİR
backup) bütün cütləri işlədir; HƏR CÜT ÖZ tranzaksiyasındadır: toqquşan cüt atlanır və hesabatda göstərilir, qalanlar
davam edir. Hər uğurlu cütün audit id-si ayrıca çap olunur (``undo_subject_merge`` bununla).

Format (sətir, workflow ``batch`` girişi)::

    QKU-934:SAYT-0004;QKU-1746:QKU-1801,QKU-1829;…

* saxlanılan (``:`` solu) YALNIZ ``QKU-N`` (sahib 2026-11-04: «SAYT … kodlar QKU olmalıdı» — SAYT kartı həmişə mənbədir);
* mənbələr ``QKU-N`` və ya ``SAYT-N``, vergüllə (cüt başına ≤ ``MAX_SOURCES``);
* hər kod planda BİR dəfə (zəncir/dövr yaranmasın — ``A←B; B←C`` rədd olunur); cüt sayı ≤ :data:`MAX_PAIRS`.
"""

from __future__ import annotations

from django.core.management.base import CommandError
from django.db import DatabaseError

from .subject_codes import KEEPER_CODE_RE, SOURCE_CODE_RE
from .subject_merge import MAX_SOURCES, MergeError, preview
from .subject_merge_apply import apply

MAX_PAIRS = 150
MAX_PLAN_LENGTH = 6000
CONFLICT_LINES = 5


def parse_plan(text: str) -> list:
    """``[(saxlanılan, [mənbələr])]`` — format pozulsa ``CommandError`` (heç nə işləmir)."""

    text = str(text or "").strip()
    if not text or len(text) > MAX_PLAN_LENGTH:
        raise CommandError("plan_invalid: boşdur və ya çox uzundur")
    pairs, seen = [], set()
    for chunk in text.split(";"):
        keeper, sep, rest = chunk.strip().partition(":")
        keeper = keeper.strip()
        sources = [part.strip() for part in rest.split(",") if part.strip()]
        if not sep or not KEEPER_CODE_RE.match(keeper):
            raise CommandError(f"plan_invalid: saxlanılan kod QKU-N olmalıdır ({keeper or '—'})")
        if not sources or len(sources) > MAX_SOURCES or not all(SOURCE_CODE_RE.match(code) for code in sources):
            raise CommandError(f"plan_invalid: {keeper} üçün mənbə kodları QKU-N / SAYT-N olmalıdır")
        for code in (keeper, *sources):
            if code in seen:
                raise CommandError(f"plan_invalid: {code} planda bir dəfədən çox")
            seen.add(code)
        pairs.append((keeper, sources))
    if len(pairs) > MAX_PAIRS:
        raise CommandError(f"plan_invalid: ən çox {MAX_PAIRS} cüt")
    return pairs


def _moved(payload) -> str:
    parts = [f"{table['key']}={table['count']}" for table in payload["tables"] if table["count"]]
    if payload["resolvable_total"]:
        parts.append(f"resolvable={payload['resolvable_total']}")
    parts.extend(f"{key}:left_past={count}" for key, count in sorted((payload.get("left_past") or {}).items()))
    return " ".join(parts) or "—"


def run_plan(
    command, organization, pairs, *, scope, do_apply, reason, drop_attendance_only, current_only=False
) -> dict:
    """Hər cüt üçün önizləmə (+ apply). Qaytarır: ``{"ok", "conflict", "error"}`` sayları.

    ``scope`` — cüt başına DB konteksti (``rls_worker_atomic`` + ``bypass_rls``): onu İDARƏ ƏMRİ verir ki, RLS
    bypass yalnız təsnif olunmuş yerdə (``apps/registrar/management/``, RLS_BYPASS_AUDIT C) qalsın.
    """

    totals = {"ok": 0, "conflict": 0, "error": 0}
    write = command.stdout.write
    for index, (keeper, sources) in enumerate(pairs, 1):
        label = f"[{index}/{len(pairs)}] {keeper} ← {','.join(sources)}"
        try:
            with scope():
                payload = preview(
                    organization,
                    keeper,
                    sources,
                    by_code=True,
                    drop_attendance_only=drop_attendance_only,
                    current_only=current_only,
                )
                if payload["blocking_total"]:
                    totals["conflict"] += 1
                    write(f"{label}: ATLANDI — {payload['blocking_total']} toqquşma")
                    for item in payload["blocking"][:CONFLICT_LINES]:
                        write(f"    TOQQUŞMA: {item['message']}")
                    continue
                if not do_apply:
                    totals["ok"] += 1
                    write(f"{label}: OK (dry-run) {_moved(payload)}")
                    continue
                result = apply(
                    organization=organization,
                    actor=None,
                    target_ref=keeper,
                    source_refs=sources,
                    reason=reason,
                    expected_digest=payload["digest"],
                    by_code=True,
                    drop_attendance_only=drop_attendance_only,
                    current_only=current_only,
                )
        except MergeError as exc:
            totals["error"] += 1
            write(f"{label}: ATLANDI — {exc.code}: {exc.message}")
            continue
        except DatabaseError as exc:  # cütün öz tranzaksiyası geri qayıdıb — qalanlar davam edir
            totals["error"] += 1
            write(f"{label}: ATLANDI — db_error: {str(exc).splitlines()[0][:200]}")
            continue
        totals["ok"] += 1
        write(f"{label}: BİRLƏŞDİRİLDİ {_moved(payload)} audit={result['audit_id']}")
    write(
        f"merge_plan: mode={'apply' if do_apply else 'dry_run'}{' current_only=1' if current_only else ''} "
        f"pairs={len(pairs)} ok={totals['ok']} "
        f"conflict={totals['conflict']} error={totals['error']}"
    )
    return totals


__all__ = ["MAX_PAIRS", "MAX_PLAN_LENGTH", "parse_plan", "run_plan"]
