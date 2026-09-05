#!/usr/bin/env python
"""İcazə matrisi: hər rol ÖZ menyusunda OLMAYAN bölmələri birbaşa URL ilə açır (tam səhifə + AJAX).

Gözlənilən: AJAX 403 (`forbidden_or_unknown_section`), tam səhifə 200 + `data-section-denied="1"`
(ana səhifəyə düşür) və hədəf bölmənin panel markup-u (`profile-section--<açar>`) HTML-də OLMAMALIDIR.

    venv/bin/python -m scripts.qa_live.security_matrix ~/EMSArena-backups/qa-2026-09-05/json/crawl_all.json --out sec.json
"""

from __future__ import annotations

import argparse
import json
import sys

from .http_session import LoginError, fragment, full_page, login

HEADERS_OF_INTEREST = (
    "Content-Security-Policy",
    "X-Frame-Options",
    "X-Content-Type-Options",
    "Referrer-Policy",
    "Strict-Transport-Security",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("crawl_json")
    parser.add_argument("--users", default="")
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    data = json.load(open(args.crawl_json, encoding="utf-8"))
    universe = sorted({s["section"] for r in data if r.get("ok") for s in r["sections"]})
    wanted = {u for u in args.users.split(",") if u}
    report = []
    for r in data:
        if not r.get("ok") or (wanted and r["username"] not in wanted):
            continue
        own = {s["section"] for s in r["sections"]}
        try:
            session = login(r["username"])
        except LoginError as exc:
            report.append({"username": r["username"], "error": str(exc)})
            continue
        rows = []
        leaks = []
        for section in universe:
            if section in own:
                continue
            a_status, _, a_html, a_err = fragment(session, section)
            p_status, _, page = full_page(session, section)
            denied = 'data-section-denied="1"' in page
            panel_present = f'data-profile-section-panel="{section}"' in page and f"profile-section--{section}" in page
            row = {
                "section": section,
                "ajax": a_status,
                "ajax_error": a_err,
                "page": p_status,
                "denied_notice": denied,
                "panel_present": panel_present,
            }
            rows.append(row)
            if a_status == 200 or panel_present or (p_status == 200 and not denied):
                leaks.append(row)
        # başlıqlar (bir cavabdan)
        _, _, sample = full_page(session, "dashboard")
        resp = session.get(
            session.qa_base if hasattr(session, "qa_base") else "http://127.0.0.1:8100/accounts/profile/", timeout=30
        )
        headers = {h: resp.headers.get(h, "") for h in HEADERS_OF_INTEREST}
        cookie_flags = {
            c.name: {
                "secure": c.secure,
                "httponly": "HttpOnly" in str(c._rest.keys()) or c.has_nonstandard_attr("HttpOnly"),
                "samesite": c._rest.get("SameSite", ""),
            }
            for c in session.cookies
        }
        report.append(
            {
                "username": r["username"],
                "role": r["role"],
                "checked": len(rows),
                "leaks": leaks,
                "headers": headers,
                "cookies": cookie_flags,
            }
        )
        print(
            f"[{r['username']}] {len(rows)} yad bölmə yoxlandı · sızma şübhəsi: {len(leaks)}",
            file=sys.stderr,
            flush=True,
        )
        for leak in leaks:
            print("    LEAK?", leak, file=sys.stderr)
    if args.out:
        json.dump(report, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    total_leaks = sum(len(r.get("leaks", [])) for r in report)
    print(f"\nYekun: {len(report)} hesab · sızma şübhəsi {total_leaks}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
