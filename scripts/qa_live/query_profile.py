#!/usr/bin/env python
"""Bölmə-bölmə SQL sorğu sayı + müddət profili (in-process, Django test Client, force_login).

Serverə deyil, birbaşa klon bazaya qoşulur — ona görə canlı süpürgə ilə yarışmır.
ROL_MATRISI.md-dəki env dəsti ilə işlədilir:

    EMS_STAGING_INSPECT=1 DATABASE_URL="postgres://emsarena_staging:emsarena_staging_password@127.0.0.1:55433/emsarena_rehearsal_a0d170000901" \\
    EMS_STAGING_DB_NAME=emsarena_rehearsal_a0d170000901 EMS_STAGING_DB_PORT=55433 EMS_DB_ROLE_ENFORCE=off DEBUG=True \\
    USE_REDIS=False ENABLE_NGROK=False ALLOWED_HOSTS="localhost,127.0.0.1" \\
    venv/bin/python -m scripts.qa_live.query_profile --settings config.settings.staging_inspect --users qa.teacher --out q.json

Yalnız GET; heç nə yazmır.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys
import time

import django

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from scripts.qa_live.accounts import ACCOUNTS, role_of  # noqa: E402
from scripts.qa_live.http_session import sidebar_sections  # noqa: E402


def _bootstrap(settings_module: str) -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", settings_module)
    django.setup()
    from django.conf import settings

    settings.ALLOWED_HOSTS = ["*"]
    settings.DEBUG = True


def profile_user(username: str, sections_filter: set[str] | None) -> dict:
    from django.contrib.auth import get_user_model
    from django.db import connection, reset_queries
    from django.test import Client
    from django.test.utils import CaptureQueriesContext
    from django.urls import reverse

    user = get_user_model().objects.filter(username=username).first()
    result = {"username": username, "role": role_of(username), "sections": []}
    if user is None:
        result["error"] = "user not found"
        return result
    client = Client()
    client.force_login(user)
    reset_queries()
    with CaptureQueriesContext(connection) as ctx:
        started = time.perf_counter()
        shell = client.get(reverse("accounts:profile"), follow=True)
        shell_ms = round((time.perf_counter() - started) * 1000)
    result["shell"] = {"status": shell.status_code, "queries": len(ctx.captured_queries), "ms": shell_ms}
    html = shell.content.decode("utf-8", "replace")
    for item in sidebar_sections(html):
        section = item["section"]
        if sections_filter and section not in sections_filter:
            continue
        entry = {"section": section}
        for kind, url in (
            ("ajax", reverse("accounts:profile_section_fragment", args=[section])),
            ("page", reverse("accounts:profile") + f"?section={section}"),
        ):
            reset_queries()
            with CaptureQueriesContext(connection) as ctx:
                started = time.perf_counter()
                try:
                    resp = client.get(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest" if kind == "ajax" else "")
                    status = resp.status_code
                except Exception as exc:  # noqa: BLE001 — istisna da nəticədir
                    status = f"EXC {type(exc).__name__}: {exc}"[:200]
                ms = round((time.perf_counter() - started) * 1000)
            queries = ctx.captured_queries
            top = collections.Counter(q["sql"][:140] for q in queries).most_common(3)
            dup = sum(n - 1 for _, n in collections.Counter(q["sql"] for q in queries).items() if n > 1)
            entry[kind] = {
                "status": status,
                "queries": len(queries),
                "duplicate_queries": dup,
                "ms": ms,
                "top": [{"n": n, "sql": sql} for sql, n in top if n > 2],
            }
        result["sections"].append(entry)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--settings", default="config.settings.staging_inspect")
    parser.add_argument("--users", default="")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--sections", default="")
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    _bootstrap(args.settings)
    users = [u for u, _, _ in ACCOUNTS] if args.all else [u for u in args.users.split(",") if u]
    if not users:
        parser.error("--all və ya --users lazımdır")
    section_filter = {s for s in args.sections.split(",") if s} or None
    results = []
    for username in users:
        result = profile_user(username, section_filter)
        results.append(result)
        worst = max(result.get("sections", []), key=lambda s: s["page"]["queries"] if "page" in s else 0, default=None)
        note = (
            f"ən çox sorğu: {worst['section']} {worst['page']['queries']} q / {worst['page']['ms']} ms" if worst else ""
        )
        print(f"[{username}] {len(result.get('sections', []))} bölmə · {note}", file=sys.stderr, flush=True)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(results, fh, ensure_ascii=False, indent=1)
    rows = []
    for r in results:
        for s in r.get("sections", []):
            rows.append(
                (s["page"]["queries"], s["page"]["ms"], r["role"], s["section"], s["page"]["duplicate_queries"])
            )
    rows.sort(reverse=True)
    print("| sorğu | ms | rol | bölmə | dublikat |")
    print("|---:|---:|---|---|---:|")
    for q, ms, role, section, dup in rows[:40]:
        print(f"| {q} | {ms} | `{role}` | `{section}` | {dup} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
