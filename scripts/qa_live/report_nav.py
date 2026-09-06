#!/usr/bin/env python
"""crawl_sections JSON-undan naviqasiya matrisi + anomaliya siyahısı (Markdown) çıxarır.

venv/bin/python -m scripts.qa_live.report_nav ~/EMSArena-backups/qa-2026-09-05/json/crawl_all.json > docs/audits/2026-09-05/NAV_MATRIX.md
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict

SLOW_MS = 1500


def main(path: str) -> int:
    data = json.load(open(path, encoding="utf-8"))
    roles = [r for r in data if r.get("ok")]
    failed = [r for r in data if not r.get("ok")]
    all_sections = sorted({s["section"] for r in roles for s in r["sections"]})
    out = ["# Naviqasiya matrisi (avtomatik) — HTTP süpürgəsi", ""]
    out.append(
        f"Hesab: {len(data)} · uğurlu login: {len(roles)} · uğursuz: {len(failed)} · fərqli bölmə: {len(all_sections)}"
    )
    out.append("")
    out.append("## Rol üzrə yekun")
    out.append("")
    out.append("| rol | bölmə | ajax200 | ajax403 | ajax4xx-digər | 5xx | ən yavaş (tam səhifə) | qabıq ms |")
    out.append("|---|---:|---:|---:|---:|---:|---|---:|")
    anomalies: list[str] = []
    for r in roles:
        secs = r["sections"]
        a200 = sum(1 for s in secs if s["ajax"]["status"] == 200)
        a403 = sum(1 for s in secs if s["ajax"]["status"] == 403)
        a4xx = sum(1 for s in secs if 400 <= s["ajax"]["status"] < 500 and s["ajax"]["status"] != 403)
        e5 = sum(1 for s in secs if s["ajax"]["status"] >= 500 or s["page"]["status"] >= 500)
        slowest = max(secs, key=lambda s: s["page"]["ms"], default=None)
        slow = f"`{slowest['section']}` {slowest['page']['ms']} ms" if slowest else ""
        out.append(f"| `{r['role']}` | {len(secs)} | {a200} | {a403} | {a4xx} | {e5} | {slow} | {r.get('shell_ms')} |")
        for s in secs:
            page = s["page"]
            ajax = s["ajax"]
            tag = f"`{r['role']}` / `{s['section']}`"
            if page["status"] != 200:
                anomalies.append(f"- {tag}: tam səhifə **{page['status']}**")
            if ajax["status"] >= 500:
                anomalies.append(f"- {tag}: AJAX **{ajax['status']}** ({ajax.get('error')})")
            if page.get("server_error_text"):
                anomalies.append(f"- {tag}: səhifədə server xətası mətni")
            if page.get("template_leak"):
                anomalies.append(f"- {tag}: şablon sızması (`{{{{`/`{{%`)")
            if page.get("none_leak"):
                anomalies.append(f"- {tag}: `None` mətni sızır")
            if page.get("h1_count", 0) > 1:
                anomalies.append(f"- {tag}: {page['h1_count']} × `<h1>`")
            if page.get("section_denied"):
                anomalies.append(f"- {tag}: menyuda var, amma «icazəniz yoxdur»")
            if page["ms"] >= SLOW_MS:
                anomalies.append(f"- {tag}: yavaş — {page['ms']} ms (tam səhifə), AJAX {ajax['ms']} ms")
            if ajax.get("raw_msgids"):
                anomalies.append(f"- {tag}: xam msgid şübhəsi: {', '.join(ajax['raw_msgids'][:6])}")
            if ajax.get("inline_scripts"):
                anomalies.append(f"- {tag}: {ajax['inline_scripts']} inline `<script>` (CSP qaydası)")
    for r in failed:
        anomalies.append(f"- `{r['role']}` ({r['username']}): **login uğursuz** — {r.get('error')}")
    out.append("")
    out.append("## Anomaliyalar")
    out.append("")
    out.extend(anomalies or ["- yoxdur"])
    out.append("")
    out.append("## Rol × bölmə (✅ AJAX 200 · 🔒 AJAX 403 (tam səhifə 200) · ❌ xəta · · görünmür)")
    out.append("")
    role_names = [r["role"] for r in roles]
    out.append("| bölmə | " + " | ".join(f"`{n}`" for n in role_names) + " |")
    out.append("|---|" + "---|" * len(role_names))
    index = defaultdict(dict)
    for r in roles:
        for s in r["sections"]:
            index[s["section"]][r["role"]] = s
    for section in all_sections:
        cells = []
        for role in role_names:
            s = index[section].get(role)
            if not s:
                cells.append("·")
            elif s["page"]["status"] != 200 or s["ajax"]["status"] >= 500:
                cells.append("❌")
            elif s["ajax"]["status"] == 200:
                cells.append("✅")
            else:
                cells.append("🔒")
        out.append(f"| `{section}` | " + " | ".join(cells) + " |")
    out.append("")
    out.append("## İnventar (rol üzrə ən çox elementli bölmələr — funksional test hədəfləri)")
    out.append("")
    out.append("| rol | bölmə | cədvəl | forma | düymə | select | input | fayl | modal | səhifələmə |")
    out.append("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for r in roles:
        rows = sorted(
            r["sections"], key=lambda s: -sum((s["ajax"].get("inventory") or s["page"].get("inventory") or {}).values())
        )[:6]
        for s in rows:
            inv = s["ajax"].get("inventory") or s["page"].get("inventory") or {}
            out.append(
                f"| `{r['role']}` | `{s['section']}` | {inv.get('tables',0)} | {inv.get('forms',0)} | {inv.get('buttons',0)} | {inv.get('selects',0)} | {inv.get('inputs',0)} | {inv.get('file_inputs',0)} | {inv.get('modals',0)} | {inv.get('pagination',0)} |"
            )
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
