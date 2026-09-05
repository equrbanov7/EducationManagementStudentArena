"""requests əsaslı login + sidebar/fraqment köməkçiləri (brauzersiz, sürətli süpürgə)."""

from __future__ import annotations

import os
import re
import time
from html import unescape

import requests

from .accounts import STAFF, STUDENT, portal_for, qa_password, qa_sec_password

BASE_URL = os.environ.get("QA_BASE_URL", "http://127.0.0.1:8100").rstrip("/")
PORTAL_PATHS = {STAFF: "/accounts/login/muellim/", STUDENT: "/accounts/login/telebe/"}
PROFILE_PATH = "/accounts/profile/"
FRAGMENT_PATH = "/accounts/profile/api/sections/{section}/"
AJAX_HEADERS = {"X-Requested-With": "XMLHttpRequest", "Accept": "application/json, text/html"}

_CSRF_RE = re.compile(r'name="csrfmiddlewaretoken" value="([^"]+)"')
_LINK_RE = re.compile(
    r'<a\s+href="(?P<href>[^"]*)"[^>]*?data-section="(?P<section>[a-z0-9\-]+)"(?P<rest>[^>]*)>(?P<body>.*?)</a>',
    re.S,
)
_GROUP_RE = re.compile(r'sidebar-menu-group-label"[^>]*>\s*<span[^>]*>(.*?)</span>', re.S)
_TEXT_RE = re.compile(r'sidebar-menu-text"[^>]*>(.*?)</span>', re.S)
_BADGE_RE = re.compile(r'sidebar-menu-badge[^"]*"[^>]*>(.*?)</span>', re.S)
_TAG_RE = re.compile(r"<[^>]+>")


class LoginError(RuntimeError):
    pass


def _strip(html: str) -> str:
    return unescape(_TAG_RE.sub("", html)).strip()


def _try_login(session: requests.Session, portal: str, username: str, password: str) -> bool:
    url = BASE_URL + PORTAL_PATHS[portal]
    page = session.get(url, timeout=30)
    match = _CSRF_RE.search(page.text)
    if not match:
        return False
    resp = session.post(
        url,
        data={"csrfmiddlewaretoken": match.group(1), "username": username, "password": password, "next": ""},
        headers={"Referer": url},
        timeout=30,
        allow_redirects=False,
    )
    if resp.status_code not in (301, 302, 303):
        return False
    location = resp.headers.get("Location", "")
    if "/accounts/login" in location:
        return False
    probe = session.get(BASE_URL + PROFILE_PATH, timeout=30, allow_redirects=True)
    return probe.status_code == 200 and "/accounts/login" not in probe.url


def login(username: str, password: str | None = None, portal: str = "auto") -> requests.Session:
    """Portal qapısı rol-əsaslıdır: əvvəl hesabın öz portalı, sonra digəri sınanır."""
    session = requests.Session()
    session.headers["User-Agent"] = "EMSArena-QA-harness/1.0"
    portals = [portal] if portal in PORTAL_PATHS else [portal_for(username)]
    portals += [p for p in (STAFF, STUDENT) if p not in portals]
    passwords = [password] if password else [qa_password(username), qa_sec_password()]
    for pw in passwords:
        for p in portals:
            session.cookies.clear()
            if _try_login(session, p, username, pw):
                session.qa_portal = p  # type: ignore[attr-defined]
                return session
    raise LoginError(f"login uğursuz: {username}")


def timed_get(session: requests.Session, path: str, **kwargs):
    started = time.perf_counter()
    resp = session.get(BASE_URL + path, timeout=kwargs.pop("timeout", 120), **kwargs)
    return resp, round((time.perf_counter() - started) * 1000)


def fragment(session: requests.Session, section: str):
    """AJAX fraqment ucu → (status, ms, html|None, error|None)."""
    resp, ms = timed_get(session, FRAGMENT_PATH.format(section=section), headers=AJAX_HEADERS)
    if resp.headers.get("Content-Type", "").startswith("application/json"):
        try:
            payload = resp.json()
        except ValueError:
            return resp.status_code, ms, None, "invalid_json"
        return resp.status_code, ms, payload.get("html"), payload.get("error")
    return resp.status_code, ms, resp.text, None


def full_page(session: requests.Session, section: str):
    resp, ms = timed_get(session, f"{PROFILE_PATH}?section={section}")
    return resp.status_code, ms, resp.text


def sidebar_sections(html: str) -> list[dict]:
    """Sol menyudakı bölmə linklərini sıra ilə çıxarır (qrup etiketi daxil)."""
    sections: list[dict] = []
    group = ""
    events = []
    for match in _GROUP_RE.finditer(html):
        events.append((match.start(), "group", _strip(match.group(1))))
    for match in _LINK_RE.finditer(html):
        events.append((match.start(), "link", match))
    events.sort(key=lambda item: item[0])
    seen = set()
    for _, kind, payload in events:
        if kind == "group":
            group = payload
            continue
        section = payload.group("section")
        if section in seen:
            continue
        seen.add(section)
        body = payload.group("body")
        text = _TEXT_RE.search(body)
        badge = _BADGE_RE.search(body)
        rest = payload.group("rest")
        sections.append(
            {
                "section": section,
                "label": _strip(text.group(1)) if text else _strip(body),
                "group": group,
                "href": unescape(payload.group("href")),
                "badge": _strip(badge.group(1)) if badge else "",
                "force_navigation": 'data-force-navigation="true"' in rest,
                "active": "active" in (re.search(r'class="([^"]*)"', rest) or [None, ""])[1].split(),
            }
        )
    return sections
