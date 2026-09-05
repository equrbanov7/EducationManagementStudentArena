#!/usr/bin/env python
"""Rol × bölmə HTTP süpürgəsi (brauzersiz) — hər hesab üçün sidebar-dakı HƏR bölməni
həm AJAX fraqment, həm tam səhifə ucundan açır və evristik siqnalları JSON-a yazır.

    venv/bin/python -m scripts.qa_live.crawl_sections --all --out out.json
    venv/bin/python -m scripts.qa_live.crawl_sections --users qa.teacher,qa.student

Yalnız GET göndərir; bazaya yazmır.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time

from .accounts import ACCOUNTS, role_of
from .http_session import PROFILE_PATH, LoginError, fragment, full_page, login, sidebar_sections, timed_get

_H1_RE = re.compile(r"<h1\b", re.I)
_EMPTY_RE = re.compile(r'class="[^"]*\bems-empty\b')
_RAW_MSGID_RE = re.compile(r">\s*([a-z]{2,}(?:_[a-z0-9]{2,}){1,4})\s*<")
_TEMPLATE_LEAK_RE = re.compile(r"\{\{|\{%")
_NONE_LEAK_RE = re.compile(r">\s*None\s*<")
_TRACEBACK_RE = re.compile(r"Traceback \(most recent call last\)|Server Error \(500\)|Internal Server Error")
_INLINE_STYLE_RE = re.compile(r'\sstyle="')
_INLINE_SCRIPT_RE = re.compile(r"<script(?![^>]*\bsrc=)(?![^>]*\bnonce=)(?![^>]*application/(?:ld\+)?json)[^>]*>\s*\S")
_INVENTORY = {
    "tables": re.compile(r"<table\b", re.I),
    "forms": re.compile(r"<form\b", re.I),
    "buttons": re.compile(r"<button\b", re.I),
    "selects": re.compile(r"<select\b", re.I),
    "inputs": re.compile(r"<input\b(?![^>]*type=\"hidden\")", re.I),
    "file_inputs": re.compile(r'type="file"', re.I),
    "modals": re.compile(r'class="[^"]*\bmodal\b|<dialog\b', re.I),
    "pagination": re.compile(r'class="[^"]*pagination', re.I),
    "links": re.compile(r"<a\b[^>]*href=", re.I),
    "kpi_tiles": re.compile(r'class="[^"]*\bems-kpi', re.I),
    "status_badges": re.compile(r'class="[^"]*\bems-badge|\bbadge\b', re.I),
}
_KNOWN_RAW_OK = {"csrfmiddlewaretoken", "sessionid"}


def analyse(html: str) -> dict:
    raw = sorted(
        {m for m in _RAW_MSGID_RE.findall(html) if m not in _KNOWN_RAW_OK and not m.startswith(("qa", "staging"))}
    )
    return {
        "bytes": len(html.encode("utf-8", "ignore")),
        "h1_count": len(_H1_RE.findall(html)),
        "empty_states": len(_EMPTY_RE.findall(html)),
        "raw_msgids": raw[:20],
        "template_leak": bool(_TEMPLATE_LEAK_RE.search(html)),
        "none_leak": bool(_NONE_LEAK_RE.search(html)),
        "server_error_text": bool(_TRACEBACK_RE.search(html)),
        "inline_styles": len(_INLINE_STYLE_RE.findall(html)),
        "inline_scripts": len(_INLINE_SCRIPT_RE.findall(html)),
        "inventory": {name: len(rx.findall(html)) for name, rx in _INVENTORY.items()},
    }


def crawl_user(username: str, sections_filter: set[str] | None = None) -> dict:
    result = {"username": username, "role": role_of(username), "ok": False, "sections": []}
    try:
        session = login(username)
    except LoginError as exc:
        result["error"] = str(exc)
        return result
    result["portal"] = getattr(session, "qa_portal", "")
    shell, shell_ms = timed_get(session, PROFILE_PATH)
    result["shell_status"] = shell.status_code
    result["shell_ms"] = shell_ms
    result["shell_final_url"] = shell.url
    if shell.status_code != 200:
        result["error"] = f"shell {shell.status_code}"
        return result
    menu = sidebar_sections(shell.text)
    result["ok"] = True
    result["menu"] = menu
    for item in menu:
        section = item["section"]
        if sections_filter and section not in sections_filter:
            continue
        entry = {"section": section, "label": item["label"], "group": item["group"]}
        status, ms, html, error = fragment(session, section)
        entry["ajax"] = {"status": status, "ms": ms, "error": error}
        if html:
            entry["ajax"].update(analyse(html))
        status, ms, page = full_page(session, section)
        entry["page"] = {"status": status, "ms": ms}
        entry["page"].update(analyse(page))
        entry["page"]["section_denied"] = 'data-section-denied="1"' in page
        entry["page"]["active_marks_self"] = f'data-section="{section}"' in page and bool(
            re.search(rf'data-section="{section}"[^>]*class="[^"]*\bactive\b', page)
        )
        result["sections"].append(entry)
    return result


def summarise(results: list[dict]) -> str:
    lines = [
        "| rol | user | bölmə | ajax200 | ajax403 | ajax5xx | page5xx | ən yavaş | qeyd |",
        "|---|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for r in results:
        if not r.get("ok"):
            lines.append(f"| {r['role']} | {r['username']} | – | – | – | – | – | – | {r.get('error','')} |")
            continue
        secs = r["sections"]
        a200 = sum(1 for s in secs if s["ajax"]["status"] == 200)
        a403 = sum(1 for s in secs if s["ajax"]["status"] == 403)
        a5xx = sum(1 for s in secs if s["ajax"]["status"] >= 500)
        p5xx = sum(1 for s in secs if s["page"]["status"] >= 500)
        slowest = max(secs, key=lambda s: s["page"]["ms"], default=None)
        slow = f"{slowest['section']} {slowest['page']['ms']} ms" if slowest else ""
        notes = []
        for s in secs:
            flags = []
            if s["page"].get("template_leak"):
                flags.append("tpl")
            if s["page"].get("none_leak"):
                flags.append("None")
            if s["page"].get("server_error_text"):
                flags.append("err")
            if s["page"].get("h1_count", 0) > 1:
                flags.append(f"h1×{s['page']['h1_count']}")
            if flags:
                notes.append(f"{s['section']}:{'/'.join(flags)}")
        lines.append(
            f"| {r['role']} | {r['username']} | {len(secs)} | {a200} | {a403} | {a5xx} | {p5xx} | {slow} | {' '.join(notes)[:120]} |"
        )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--users", default="")
    parser.add_argument("--sections", default="", help="vergüllə bölmə açarları (filter)")
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    users = [u for u, _, _ in ACCOUNTS] if args.all else [u for u in args.users.split(",") if u]
    if not users:
        parser.error("--all və ya --users lazımdır")
    section_filter = {s for s in args.sections.split(",") if s} or None
    started = time.time()
    results = []
    for username in users:
        result = crawl_user(username, section_filter)
        results.append(result)
        status = "ok" if result.get("ok") else f"FAIL {result.get('error')}"
        print(f"[{username}] {status} — {len(result.get('sections', []))} bölmə", file=sys.stderr, flush=True)
    print(summarise(results))
    print(f"\n{len(results)} hesab, {round(time.time() - started)} s", file=sys.stderr)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(results, fh, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
