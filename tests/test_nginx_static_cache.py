"""nginx statik keş siyasəti (perf 2026-10-07).

* Manifest hash-li ad (`name.<12 hex>.ext`) → `public, max-age=31536000, immutable`;
  hash-siz ad → `public, no-cache` (deploy-da yerində dəyişir, revalidasiya olunmalıdır).
  Əvvəl HƏR fayl `expires 30d` + `immutable` alırdı və iki Cache-Control başlığı gedirdi.
* `gzip_types` `text/javascript`-i də əhatə edir; `gzip_static` + `open_file_cache` var.
* CI konfiqi eyni siyasəti daşıyır.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PROD = ROOT / "docker" / "nginx" / "nginx.conf"
CI = ROOT / "docker" / "nginx" / "nginx.ci.conf"


def _block(text: str, opener: str) -> str:
    start = text.index(opener)
    depth = 0
    for index in range(text.index("{", start), len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    raise AssertionError(opener)


def _cache_map(text: str) -> dict[str, str]:
    body = _block(text, "map $uri $ems_static_cache_control")
    return dict(re.findall(r'^\s*("?~?[^\s"]+"?|default)\s+"([^"]+)";', body, re.M))


@pytest.mark.parametrize("conf", [PROD, CI], ids=["prod", "ci"])
def test_static_cache_policy_splits_hashed_and_plain_names(conf):
    text = conf.read_text(encoding="utf-8")
    mapping = _cache_map(text)
    assert mapping["default"] == "public, no-cache"
    hashed = [value for key, value in mapping.items() if key != "default"]
    assert hashed == ["public, max-age=31536000, immutable"]

    static = re.sub(r"#[^\n]*", "", _block(text, "location /static/"))
    assert "add_header Cache-Control $ems_static_cache_control;" in static
    assert "expires" not in static, "expires ikinci Cache-Control başlığı yaradır"
    assert "immutable" not in static
    assert "gzip_static on;" in static


@pytest.mark.parametrize(
    "uri, immutable",
    [
        ("/static/css/main.3a2b1c4d5e6f.css", True),
        ("/static/vendor/chartjs/chart.umd.min.0123456789ab.js", True),
        ("/static/accounts/css/profile/sections/contact_messages/_part1.abcdef012345.css", True),
        ("/static/vendor/fontawesome/webfonts/fa-solid-900.0f1e2d3c4b5a.woff2", True),
        ("/static/css/main.css", False),
        ("/static/js/user_profile/entry.js", False),
        ("/static/vendor/katex/0.16.47/katex.min.js", False),
    ],
)
def test_hash_regex_matches_manifest_names_only(uri, immutable):
    pattern = next(key for key in _cache_map(PROD.read_text(encoding="utf-8")) if key != "default")
    regex = pattern.strip('"').lstrip("~")
    assert bool(re.search(regex, uri)) is immutable


def test_static_location_caches_file_descriptors_and_gzip_covers_javascript():
    text = PROD.read_text(encoding="utf-8")
    static = _block(text, "location /static/")
    assert "open_file_cache max=" in static
    assert "open_file_cache_errors off;" in static
    gzip_types = re.search(r"gzip_types([^;]+);", text).group(1).split()
    for mime in ("text/css", "text/javascript", "application/javascript", "application/json", "image/svg+xml"):
        assert mime in gzip_types, mime
    assert "http2 on;" in text
