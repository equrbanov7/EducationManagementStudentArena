#!/usr/bin/env python
"""Headless-brauzer (Playwright) süpürgəsi — bir hesabla real login, sol menyudan HƏR
bölməni KLİKLƏ açır (AJAX yolu), konsol/JS/şəbəkə xətalarını, aktiv menyu vəziyyətini,
başlığı, üfüqi daşmanı və ekran görüntülərini toplayır.

    venv/bin/python -m scripts.qa_live.pw_crawl --user qa.teacher --out ~/EMSArena-backups/qa-2026-09-05/shots
    venv/bin/python -m scripts.qa_live.pw_crawl --user qa.student --viewports 1280x900,375x812 --sections dashboard,my-journal

Nəticə: <out>/<user>/<section>@<w>.png + <out>/<user>.json
"""

from __future__ import annotations

import argparse
import json
import pathlib
import time

from playwright.sync_api import Page, sync_playwright

from .accounts import STAFF, STUDENT, portal_for, qa_password, qa_sec_password
from .http_session import BASE_URL, PORTAL_PATHS


def _login(page: Page, username: str) -> str:
    portals = [portal_for(username)] + [p for p in (STAFF, STUDENT) if p != portal_for(username)]
    for password in (qa_password(username), qa_sec_password()):
        for portal in portals:
            page.goto(BASE_URL + PORTAL_PATHS[portal], wait_until="domcontentloaded")
            page.fill("input[name=username]", username)
            page.fill("input[name=password]", password)
            page.click("form.auth-form button[type=submit]")
            page.wait_for_load_state("domcontentloaded")
            if "/accounts/login" not in page.url:
                return portal
    raise SystemExit(f"login uğursuz: {username}")


def _attach_listeners(page: Page) -> tuple[list[dict], list[dict]]:
    """Konsol/JS/şəbəkə xətalarını toplayan siyahıları səhifəyə bağlayır."""
    console: list[dict] = []
    failed: list[dict] = []

    def on_console(msg):
        if msg.type in ("error", "warning"):
            console.append({"type": msg.type, "text": msg.text[:300]})

    def on_response(resp):
        if resp.status >= 400:
            failed.append({"url": resp.url[:200], "status": resp.status})

    page.on("console", on_console)
    page.on("pageerror", lambda e: console.append({"type": "pageerror", "text": str(e)[:300]}))
    page.on("requestfailed", lambda r: failed.append({"url": r.url[:200], "err": (r.failure or "")[:120]}))
    page.on("response", on_response)
    return console, failed


def _menu(page: Page) -> list[dict]:
    return page.evaluate("""() => Array.from(document.querySelectorAll('.sidebar-menu-link[data-section]')).map(a => ({
            section: a.dataset.section,
            label: (a.querySelector('.sidebar-menu-text') || a).textContent.trim(),
            force: a.dataset.forceNavigation === 'true',
            href: a.getAttribute('href'),
        }))""")


def _state(page: Page) -> dict:
    return page.evaluate("""() => ({
            title: document.title,
            h1: (document.getElementById('profileSectionTitle') || {}).textContent || '',
            h1_count: document.querySelectorAll('h1').length,
            active: Array.from(document.querySelectorAll('.sidebar-menu-link.active')).map(a => a.dataset.section),
            hscroll: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
            scrollWidth: document.documentElement.scrollWidth,
            clientWidth: document.documentElement.clientWidth,
            empty_states: document.querySelectorAll('.ems-empty').length,
            placeholder: !!document.querySelector('.profile-section-placeholder'),
            panel: Array.from(document.querySelectorAll('[data-profile-section-panel]')).map(p => p.dataset.profileSectionPanel),
            skeletons: document.querySelectorAll('.skeleton, .ems-skeleton, [data-skeleton]').length,
            tables: document.querySelectorAll('table').length,
            forms: document.querySelectorAll('form').length,
            buttons: document.querySelectorAll('button, a.btn').length,
            focusable_without_label: Array.from(document.querySelectorAll('button, a')).filter(el => !el.textContent.trim() && !el.getAttribute('aria-label') && !el.getAttribute('title')).length,
            imgs_without_alt: Array.from(document.querySelectorAll('img')).filter(i => !i.hasAttribute('alt')).length,
            inputs_without_label: Array.from(document.querySelectorAll('input:not([type=hidden]), select, textarea')).filter(el => !el.id || !document.querySelector('label[for="'+el.id+'"]')).filter(el => !el.getAttribute('aria-label') && !el.closest('label')).length,
        })""")


def crawl(
    username: str, out_dir: pathlib.Path, viewports: list[tuple[int, int]], sections: set[str] | None, headed: bool
) -> dict:
    user_dir = out_dir / username
    user_dir.mkdir(parents=True, exist_ok=True)
    report = {"username": username, "sections": [], "viewports": viewports}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not headed)
        for width, height in viewports:
            context = browser.new_context(viewport={"width": width, "height": height}, locale="az-AZ")
            page = context.new_page()
            console, failed = _attach_listeners(page)
            portal = _login(page, username)
            report["portal"] = portal
            page.goto(BASE_URL + "/accounts/profile/", wait_until="networkidle")
            menu = _menu(page)
            report["menu"] = menu
            for item in menu:
                section = item["section"]
                if sections and section not in sections:
                    continue
                console.clear()
                failed.clear()
                entry = {"section": section, "label": item["label"], "viewport": f"{width}x{height}"}
                started = time.perf_counter()
                try:
                    if item["force"] or width < 768:
                        # Mobil görünüşdə sidebar bağlıdır; tam səhifə naviqasiyası kifayətdir.
                        page.goto(BASE_URL + item["href"], wait_until="networkidle")
                    else:
                        # Əvvəlki panelin `is-active` izini sil ki, gözləmə həqiqi swap-ı ölçsün;
                        # JS click bağlı (collapsed) menyu qrupundakı linki də işə salır.
                        page.evaluate(
                            "document.querySelectorAll('[data-profile-section-panel].is-active')"
                            ".forEach(p => p.classList.remove('is-active'))"
                        )
                        link = page.query_selector(f'.sidebar-menu-link[data-section="{section}"]')
                        entry["link_visible"] = bool(link and link.is_visible())
                        page.eval_on_selector(f'.sidebar-menu-link[data-section="{section}"]', "a => a.click()")
                        page.wait_for_selector(
                            f'[data-profile-section-panel="{section}"].is-active', state="attached", timeout=45000
                        )
                        page.wait_for_load_state("networkidle", timeout=45000)
                    entry["ms"] = round((time.perf_counter() - started) * 1000)
                    entry.update(_state(page))
                    entry["console"] = list(console)
                    entry["failed_requests"] = list(failed)
                    shot = user_dir / f"{section}@{width}.png"
                    page.screenshot(path=str(shot), full_page=False)
                    entry["screenshot"] = str(shot)
                except Exception as exc:  # noqa: BLE001
                    entry["error"] = str(exc)[:300]
                    entry["console"] = list(console)
                    entry["failed_requests"] = list(failed)
                report["sections"].append(entry)
            context.close()
        browser.close()
    (out_dir / f"{username}.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--user", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--viewports", default="1280x900")
    parser.add_argument("--sections", default="")
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()
    viewports = [tuple(int(x) for x in v.split("x")) for v in args.viewports.split(",") if v]
    sections = {s for s in args.sections.split(",") if s} or None
    report = crawl(args.user, pathlib.Path(args.out).expanduser(), viewports, sections, args.headed)
    errors = sum(len(s.get("console", [])) for s in report["sections"])
    fails = sum(len(s.get("failed_requests", [])) for s in report["sections"])
    broken = [s["section"] for s in report["sections"] if s.get("error")]
    print(f"{args.user}: {len(report['sections'])} açılış, konsol {errors}, şəbəkə≥400 {fails}, xəta {broken}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
